from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from .nur_protocol import (
    FLAG_UNSOL,
    STATUS_INVALID_COMMAND,
    STATUS_INVALID_LENGTH,
    STATUS_NOT_SUPPORTED,
    STATUS_SUCCESS,
    NurFrameDecoder,
    NurRequest,
    encode_reply,
    encode_u16,
    encode_u32,
    read_u16,
    read_u32,
)
from .state import (
    APP_PERM_SIG,
    QueuedTag,
    ScannerModel,
    SETUP_ANTMASK,
    SETUP_TXLEVEL,
    NurState,
)


NUR_CMD_PING = 1
NUR_CMD_GET_MODE = 4
NUR_CMD_CLEAR_ID_BUFFER = 5
NUR_CMD_READER_INFO = 9
NUR_CMD_DEV_CAPS = 11
NUR_CMD_LOAD_SETUP = 34
NUR_CMD_ANTENNA_EX = 37
NUR_CMD_INVENTORY_STREAM = 57
NUR_CMD_ACC_EXT = 85

NUR_CMD_NOTIFY_IO_CHANGE = 129
NUR_CMD_NOTIFY_INVENTORY = 130
NUR_CMD_NOTIFY_ACCESSORY = 144

ACC_EXT_GET_FWVERSION = 0x00
ACC_EXT_GET_CONFIG = 0x01
ACC_EXT_READ_BARCODE_ASYNC = 0x06
ACC_EXT_GET_BATTERY_INFO = 0x09
ACC_EXT_IMAGER = 0x0D
ACC_EXT_IMAGER_POWER = 0x05
ACC_EXT_IMAGER_AIM = 0x06
ACC_EXT_GET_MODEL_INFORMATION = 0x10
ACC_EXT_GET_CONNECTION_INFO = 0x12

ACC_EVENT_TYPE_BARCODE = 0x01
TRIGGER_SOURCE = 100
RAW_CANCEL_BARCODE = 0xFF

MODULE_SETUP_ALL_FLAGS = 0x7FFFFFFF
DEFAULT_LINK_FREQUENCY = 256000
DEFAULT_RX_DECODING = 2
DEFAULT_TX_MODULATION = 1
DEFAULT_REGION_ID = 0
DEFAULT_INVENTORY_Q = 0
DEFAULT_INVENTORY_SESSION = 0
DEFAULT_INVENTORY_ROUNDS = 0
DEFAULT_SCAN_SINGLE_TRIGGER_TIMEOUT_MS = 3000
DEFAULT_INVENTORY_TRIGGER_TIMEOUT_MS = 3000
DEFAULT_SELECTED_ANTENNA = 0xFF
DEFAULT_OP_FLAGS = 0
DEFAULT_INVENTORY_TARGET = 0
DEFAULT_INVENTORY_EPC_LENGTH = 0xFF
DEFAULT_TIMEOUT_MS = 1000
DEFAULT_PERIOD_SETUP_MS = 0
DEFAULT_POWER_OFFSET = 0
DEFAULT_AUTOTUNE_MODE = 0
DEFAULT_AUTOTUNE_THRESHOLD_DBM = -10
DEFAULT_RX_SENSITIVITY = 0
DEFAULT_RF_PROFILE = 1
DEFAULT_TO_SLEEP_TIME_MS = 500

READER_INFO_VERSION = 0x52444901
EXA81_READER_SERIAL = "K000000001"
EXA81_READER_ALT_SERIAL = "K000000002"
# Synthetic identity strings. The reply keeps the real reader-info layout
# (length-prefixed strings), but the values do not identify a certified
# device.
EXA81_READER_NAME = "EMU-RFID"
EXA81_READER_FCC_ID = "FCC: EMULATED / IC: EMULATED"
READER_HW_VERSION = "EMU0001"
READER_SW_MAJOR = 15
READER_SW_MINOR = 4
READER_SW_DEV = ord("E")
READER_NUM_GPIO = 0
READER_NUM_SENSORS = 0
READER_NUM_REGIONS = 26

DEV_CAPS_RESPONSE_SIZE = 56
DEV_CAPS_FLAG_SET_1 = 0x176E83CF
DEV_CAPS_FLAG_SET_2 = 0x00000000
DEV_CAPS_MAX_TX_DBM = 30
DEV_CAPS_TX_ATTN_STEP = 1
DEV_CAPS_MAX_TX_MW = 1000
DEV_CAPS_TX_STEPS = 30
DEV_CAPS_TAG_BUFFER_SIZE = 589
DEV_CAPS_CUR_CFG_MAX_GPIO = 0
DEV_CAPS_CHIP_VERSION = 7
DEV_CAPS_MODULE_TYPE = 9
DEV_CAPS_MODULE_CONFIG_FLAGS = 0x00020020
DEV_CAPS_V2_LEVEL = 0
DEV_CAPS_PADDING_BYTES = 72


@dataclass(frozen=True)
class QueueTagResult:
    accepted: bool
    epc_hex: str
    flushed: int
    id_buffer_size: int


class NurSession:
    def __init__(
        self,
        state: NurState,
        send_bytes: Callable[[bytes], Awaitable[None]],
        logger: Optional[logging.Logger] = None,
        on_state_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.state = state
        self._send_bytes = send_bytes
        self._decoder = NurFrameDecoder()
        self._lock = asyncio.Lock()
        self._logger = logger or logging.getLogger("scanner_emu.nur")
        self._on_state_changed = on_state_changed
        self._inventory_round = 0
        self._timestamp = 0

    async def feed_bytes(self, data: bytes) -> None:
        async with self._lock:
            offset = 0
            while (
                offset < len(data)
                and data[offset] == RAW_CANCEL_BARCODE
                and not self._decoder.has_pending_data()
            ):
                self._logger.info("RX raw cancel barcode")
                self._cancel_barcode_locked()
                offset += 1

            for request in self._decoder.feed(data[offset:]):
                await self._handle_request_locked(request)

    async def send_trigger(self, pressed: bool) -> None:
        async with self._lock:
            payload = bytes((TRIGGER_SOURCE, 1 if pressed else 0))
            await self._send_event_locked(NUR_CMD_NOTIFY_IO_CHANGE, 0, payload)
            self._logger.info(
                "Trigger event sent: state=%s source=%s",
                "pressed" if pressed else "released",
                TRIGGER_SOURCE,
            )

    async def queue_tag(
        self, epc_hex: str, rssi: int, antenna_id: int
    ) -> QueueTagResult:
        async with self._lock:
            normalized_epc = normalize_epc(epc_hex)
            if normalized_epc in self.state.id_buffer:
                self._logger.info(
                    "RFID duplicate ignored: id_buffer_size=%s queued_tags=%s",
                    len(self.state.id_buffer),
                    len(self.state.queued_tags),
                )
                return QueueTagResult(
                    accepted=False,
                    epc_hex=normalized_epc,
                    flushed=0,
                    id_buffer_size=len(self.state.id_buffer),
                )

            tag = QueuedTag(
                epc_hex=normalized_epc,
                rssi=rssi,
                antenna_id=antenna_id,
            )
            self.state.id_buffer.add(normalized_epc)
            self.state.queued_tags.append(tag)
            flushed = 0
            if self.state.inventory_running:
                flushed = await self._flush_inventory_locked()
            self._logger.info(
                "RFID accepted: antenna=%s rssi=%s flushed=%s id_buffer_size=%s",
                antenna_id,
                rssi,
                flushed,
                len(self.state.id_buffer),
            )
            self._notify_state_changed()
            return QueueTagResult(
                accepted=True,
                epc_hex=normalized_epc,
                flushed=flushed,
                id_buffer_size=len(self.state.id_buffer),
            )

    async def flush_tags(self) -> int:
        async with self._lock:
            if not self.state.inventory_running:
                return 0
            flushed = await self._flush_inventory_locked()
            self._notify_state_changed()
            return flushed

    async def start_inventory(self) -> int:
        async with self._lock:
            self.state.inventory_running = True
            flushed = await self._flush_inventory_locked()
            self._logger.info(
                "Inventory started: flushed_tags=%s queued_tags=%s id_buffer_size=%s",
                flushed,
                len(self.state.queued_tags),
                len(self.state.id_buffer),
            )
            self._notify_state_changed()
            return flushed

    async def stop_inventory(self) -> None:
        async with self._lock:
            self.state.inventory_running = False
            await self._send_inventory_event_locked([], stopped=True)
            self._logger.info(
                "Inventory stopped: queued_tags=%s id_buffer_size=%s",
                len(self.state.queued_tags),
                len(self.state.id_buffer),
            )
            self._notify_state_changed()

    async def emit_barcode(self, code: str) -> bool:
        async with self._lock:
            if self.state.barcode_reads_pending:
                await self._send_barcode_event_locked(code)
                self._notify_state_changed()
                return True
            self.state.queued_barcodes.append(code)
            self._notify_state_changed()
            return False

    async def disconnect_cleanup(self) -> None:
        async with self._lock:
            self.state.barcode_reads_pending = False
            self.state.imager_aim_on = False
            self.state.inventory_running = False
            self._notify_state_changed()

    async def _handle_request_locked(self, request: NurRequest) -> None:
        self._logger.info(
            "RX packet cmd=%s flags=0x%04X payload_len=%s",
            request.command,
            request.flags,
            len(request.payload),
        )

        if request.command == NUR_CMD_PING:
            await self._send_reply_locked(
                NUR_CMD_PING, STATUS_SUCCESS, self.state.name.encode("utf-8")
            )
            return

        if request.command == NUR_CMD_GET_MODE:
            await self._send_reply_locked(NUR_CMD_GET_MODE, STATUS_SUCCESS, b"A")
            return

        if request.command == NUR_CMD_CLEAR_ID_BUFFER:
            changed = bool(self.state.id_buffer or self.state.queued_tags)
            cleared_buffer = len(self.state.id_buffer)
            cleared_queued = len(self.state.queued_tags)
            self.state.id_buffer.clear()
            self.state.queued_tags.clear()
            if changed:
                self._logger.info(
                    "Cleared scanner ID buffer: ids=%s queued_tags=%s",
                    cleared_buffer,
                    cleared_queued,
                )
            await self._send_reply_locked(NUR_CMD_CLEAR_ID_BUFFER, STATUS_SUCCESS, b"")
            if changed:
                self._notify_state_changed()
            return

        if request.command == NUR_CMD_READER_INFO:
            await self._send_reply_locked(
                NUR_CMD_READER_INFO,
                STATUS_SUCCESS,
                self._build_reader_info_reply(),
            )
            return

        if request.command == NUR_CMD_DEV_CAPS:
            await self._send_reply_locked(
                NUR_CMD_DEV_CAPS,
                STATUS_SUCCESS,
                self._build_dev_caps_reply(),
            )
            return

        if request.command == NUR_CMD_LOAD_SETUP:
            await self._handle_load_setup_locked(request.payload)
            return

        if request.command == NUR_CMD_ANTENNA_EX:
            await self._handle_antenna_ex_locked()
            return

        if request.command == NUR_CMD_INVENTORY_STREAM:
            await self._handle_inventory_stream_locked(request.payload)
            return

        if request.command == NUR_CMD_ACC_EXT:
            await self._handle_accessory_command_locked(request.payload)
            return

        self._logger.warning("Unsupported NUR command: %s", request.command)
        await self._send_reply_locked(
            request.command,
            STATUS_INVALID_COMMAND,
            b"",
        )

    async def _handle_load_setup_locked(self, payload: bytes) -> None:
        if len(payload) == 0:
            await self._send_reply_locked(
                NUR_CMD_LOAD_SETUP,
                STATUS_SUCCESS,
                self._build_full_setup_reply(),
            )
            return

        if len(payload) not in (0, 4, 5, 6):
            await self._send_reply_locked(
                NUR_CMD_LOAD_SETUP,
                STATUS_INVALID_LENGTH,
                b"",
            )
            return

        setup_flags = 0
        cursor = 0
        if len(payload) >= 4:
            setup_flags = read_u32(payload, 0)
            cursor = 4

        supported_flags = SETUP_TXLEVEL | SETUP_ANTMASK
        if setup_flags & ~supported_flags:
            self._logger.warning(
                "Unsupported setup flags requested: 0x%08X", setup_flags
            )
            await self._send_reply_locked(
                NUR_CMD_LOAD_SETUP,
                STATUS_NOT_SUPPORTED,
                b"",
            )
            return

        if cursor < len(payload) and (setup_flags & SETUP_TXLEVEL):
            self.state.tx_level = payload[cursor] & 0xFF
            cursor += 1

        if cursor < len(payload) and (setup_flags & SETUP_ANTMASK):
            self.state.antenna_mask = payload[cursor] & 0xFF
            cursor += 1

        response = bytearray()
        response.extend(encode_u32(setup_flags))
        if setup_flags & SETUP_TXLEVEL:
            response.append(self.state.tx_level & 0xFF)
        if setup_flags & SETUP_ANTMASK:
            response.append((self.state.antenna_mask or 0) & 0xFF)

        await self._send_reply_locked(
            NUR_CMD_LOAD_SETUP,
            STATUS_SUCCESS,
            bytes(response),
        )
        if cursor > 4:
            self._notify_state_changed()

    async def _handle_antenna_ex_locked(self) -> None:
        payload = bytearray()
        mappings = self.state.antenna_mapping()
        payload.append(len(mappings) & 0xFF)
        for antenna_id, name in mappings:
            encoded_name = name.encode("ascii")
            payload.append(antenna_id & 0xFF)
            payload.append((len(encoded_name) + 1) & 0xFF)
            payload.extend(encoded_name)
            payload.append(0)

        await self._send_reply_locked(NUR_CMD_ANTENNA_EX, STATUS_SUCCESS, bytes(payload))

    async def _handle_inventory_stream_locked(self, payload: bytes) -> None:
        if payload == b"":
            self.state.inventory_running = False
            await self._send_reply_locked(
                NUR_CMD_INVENTORY_STREAM, STATUS_SUCCESS, b""
            )
            await self._send_inventory_event_locked([], stopped=True)
            self._logger.info(
                "Inventory stopped by NUR command: queued_tags=%s id_buffer_size=%s",
                len(self.state.queued_tags),
                len(self.state.id_buffer),
            )
            self._notify_state_changed()
            return

        if payload != b"\x01":
            await self._send_reply_locked(
                NUR_CMD_INVENTORY_STREAM,
                STATUS_INVALID_LENGTH,
                b"",
            )
            return

        self.state.inventory_running = True
        await self._send_reply_locked(NUR_CMD_INVENTORY_STREAM, STATUS_SUCCESS, b"")
        flushed = await self._flush_inventory_locked()
        self._logger.info(
            "Inventory started by NUR command: flushed_tags=%s queued_tags=%s "
            "id_buffer_size=%s",
            flushed,
            len(self.state.queued_tags),
            len(self.state.id_buffer),
        )
        self._notify_state_changed()

    async def _handle_accessory_command_locked(self, payload: bytes) -> None:
        if not payload:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT, STATUS_INVALID_LENGTH, b""
            )
            return

        command = payload[0]

        if command == ACC_EXT_GET_FWVERSION:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT,
                STATUS_SUCCESS,
                self._build_accessory_fw_version_reply(),
            )
            return

        if command == ACC_EXT_GET_CONFIG:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT,
                STATUS_SUCCESS,
                self._build_accessory_config_reply(),
            )
            return

        if command == ACC_EXT_GET_BATTERY_INFO:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT,
                STATUS_SUCCESS,
                self._build_battery_reply(),
            )
            return

        if command == ACC_EXT_GET_MODEL_INFORMATION:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT,
                STATUS_SUCCESS,
                self.state.model.label.encode("utf-8"),
            )
            return

        if command == ACC_EXT_GET_CONNECTION_INFO:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT,
                STATUS_SUCCESS,
                self.state.connection_info.encode("utf-8"),
            )
            return

        if command == ACC_EXT_IMAGER:
            await self._handle_imager_command_locked(payload)
            return

        if command == ACC_EXT_READ_BARCODE_ASYNC:
            if len(payload) != 3:
                await self._send_reply_locked(
                    NUR_CMD_ACC_EXT,
                    STATUS_INVALID_LENGTH,
                    b"",
                )
                return

            timeout_ms = read_u16(payload, 1)
            self._logger.info("Barcode read requested with timeout=%sms", timeout_ms)
            self.state.barcode_reads_pending = True
            await self._send_reply_locked(NUR_CMD_ACC_EXT, STATUS_SUCCESS, b"")

            if self.state.queued_barcodes:
                barcode = self.state.queued_barcodes.popleft()
                await self._send_barcode_event_locked(barcode)
            self._notify_state_changed()
            return

        self._logger.warning("Unsupported accessory command: %s", command)
        await self._send_reply_locked(NUR_CMD_ACC_EXT, STATUS_NOT_SUPPORTED, b"")

    async def _handle_imager_command_locked(self, payload: bytes) -> None:
        if len(payload) != 3:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT,
                STATUS_INVALID_LENGTH,
                b"",
            )
            return

        operation = payload[1]
        enabled = payload[2] != 0

        if operation == ACC_EXT_IMAGER_POWER:
            self.state.imager_powered = enabled
        elif operation == ACC_EXT_IMAGER_AIM:
            self.state.imager_aim_on = enabled
        else:
            await self._send_reply_locked(
                NUR_CMD_ACC_EXT,
                STATUS_NOT_SUPPORTED,
                b"",
            )
            return

        await self._send_reply_locked(NUR_CMD_ACC_EXT, STATUS_SUCCESS, b"")
        self._notify_state_changed()

    async def _flush_inventory_locked(self) -> int:
        if not self.state.inventory_running or not self.state.queued_tags:
            return 0

        tags = list(self.state.queued_tags)
        self.state.queued_tags.clear()
        await self._send_inventory_event_locked(tags, stopped=False)
        return len(tags)

    async def _send_inventory_event_locked(
        self, tags: List[QueuedTag], stopped: bool
    ) -> None:
        self._inventory_round = (self._inventory_round + 1) % 256

        payload = bytearray()
        payload.append(1 if stopped else 0)
        payload.append(self._inventory_round)
        payload.extend(encode_u16(0))
        payload.append(0)

        for tag in tags:
            payload.extend(self._build_inventory_record(tag))

        await self._send_event_locked(
            NUR_CMD_NOTIFY_INVENTORY,
            STATUS_SUCCESS,
            bytes(payload),
        )

    async def _send_barcode_event_locked(self, code: str) -> None:
        self.state.barcode_reads_pending = False
        payload = bytearray()
        payload.append(ACC_EVENT_TYPE_BARCODE)
        payload.extend(code.encode("utf-8"))
        payload.append(0)
        await self._send_event_locked(
            NUR_CMD_NOTIFY_ACCESSORY,
            STATUS_SUCCESS,
            bytes(payload),
        )
        self._notify_state_changed()

    def _cancel_barcode_locked(self) -> None:
        self.state.barcode_reads_pending = False
        self.state.imager_aim_on = False
        self._notify_state_changed()

    def _build_accessory_config_reply(self) -> bytes:
        payload = bytearray()
        payload.extend(encode_u32(APP_PERM_SIG))
        payload.extend(encode_u32(self.state.accessory_config_value))
        payload.extend(encode_u32(self.state.accessory_flags))

        name_bytes = self.state.name.encode("utf-8")[:31]
        payload.extend(name_bytes)
        payload.extend(b"\x00" * (32 - len(name_bytes)))

        payload.extend(encode_u16(5000))
        payload.extend(encode_u16(8000))
        payload.extend(encode_u16(50))
        return bytes(payload)

    def _build_battery_reply(self) -> bytes:
        flags = 1 if self.state.charging else 0
        payload = bytearray()
        payload.extend(encode_u16(flags))
        payload.append(self.state.battery_percent & 0xFF)
        payload.extend(encode_u16(self.state.voltage_mv))
        payload.extend(encode_u16(self.state.current_ma & 0xFFFF))
        payload.extend(encode_u16(self.state.capacity_mah))
        return bytes(payload)

    def _build_inventory_record(self, tag: QueuedTag) -> bytes:
        epc = bytes.fromhex(tag.epc_hex)
        pc = tag.pc if tag.pc is not None else default_pc_for_epc(epc)
        channel = 0

        self._timestamp = (self._timestamp + 1) % 65536
        record = bytearray()
        record.append(signed_byte(tag.rssi))
        record.append(signed_byte(tag.rssi))
        record.extend(encode_u16(self._timestamp))
        record.extend(encode_u32(tag.frequency_khz))
        record.extend(encode_u16(pc))
        record.append(channel & 0xFF)
        record.append(tag.antenna_id & 0xFF)
        record.extend(epc)
        return bytes((len(record) & 0xFF,)) + bytes(record)

    async def _send_reply_locked(self, command: int, status: int, payload: bytes) -> None:
        await self._send_bytes(encode_reply(command, status, payload))

    async def _send_event_locked(self, command: int, status: int, payload: bytes) -> None:
        await self._send_bytes(encode_reply(command, status, payload, flags=FLAG_UNSOL))

    def _build_accessory_fw_version_reply(self) -> bytes:
        reply = "%s 0 Jan 01 2024;%s;0" % (
            self.state.firmware.application_version,
            self.state.firmware.bootloader_version,
        )
        return reply.encode("utf-8")

    def _notify_state_changed(self) -> None:
        if self._on_state_changed is not None:
            self._on_state_changed()

    def _build_reader_info_reply(self) -> bytes:
        if self.state.model == ScannerModel.EXA81:
            serial = EXA81_READER_SERIAL
            alt_serial = EXA81_READER_ALT_SERIAL
        else:
            serial = "EXA51EMU01"
            alt_serial = "EXA51-EMU"

        payload = bytearray()
        payload.extend(encode_u32(READER_INFO_VERSION))
        for value in (
            serial,
            alt_serial,
            EXA81_READER_NAME,
            EXA81_READER_FCC_ID,
            READER_HW_VERSION,
        ):
            encoded = value.encode("utf-8")
            payload.append(len(encoded) & 0xFF)
            payload.extend(encoded)

        payload.append(READER_SW_MAJOR & 0xFF)
        payload.append(READER_SW_MINOR & 0xFF)
        payload.append(READER_SW_DEV & 0xFF)
        payload.append(READER_NUM_GPIO & 0xFF)
        payload.append(READER_NUM_SENSORS & 0xFF)
        payload.append(READER_NUM_REGIONS & 0xFF)
        payload.append(len(self.state.antenna_mapping()) & 0xFF)
        payload.append(len(self.state.antenna_mapping()) & 0xFF)
        return bytes(payload)

    def _build_dev_caps_reply(self) -> bytes:
        payload = bytearray()
        payload.extend(encode_u32(DEV_CAPS_RESPONSE_SIZE))
        payload.extend(encode_u32(DEV_CAPS_FLAG_SET_1))
        payload.extend(encode_u32(DEV_CAPS_FLAG_SET_2))
        payload.extend(encode_u32(DEV_CAPS_MAX_TX_DBM))
        payload.extend(encode_u32(DEV_CAPS_TX_ATTN_STEP))
        payload.extend(encode_u16(DEV_CAPS_MAX_TX_MW))
        payload.extend(encode_u16(DEV_CAPS_TX_STEPS))
        payload.extend(encode_u16(DEV_CAPS_TAG_BUFFER_SIZE))
        payload.extend(encode_u16(len(self.state.antenna_mapping())))
        payload.extend(encode_u16(DEV_CAPS_CUR_CFG_MAX_GPIO))
        payload.extend(encode_u16(DEV_CAPS_CHIP_VERSION))
        payload.extend(encode_u16(DEV_CAPS_MODULE_TYPE))
        payload.extend(encode_u32(DEV_CAPS_MODULE_CONFIG_FLAGS))
        payload.extend(encode_u16(DEV_CAPS_V2_LEVEL))
        payload.extend(encode_u32(0))
        payload.extend(encode_u32(0))
        payload.extend(encode_u32(0))
        payload.extend(encode_u32(0))
        payload.extend(b"\x00" * DEV_CAPS_PADDING_BYTES)
        return bytes(payload)

    def _build_full_setup_reply(self) -> bytes:
        antenna_mask = (self.state.antenna_mask or 0) & 0xFF

        payload = bytearray()
        payload.extend(encode_u32(MODULE_SETUP_ALL_FLAGS))
        payload.extend(encode_u32(DEFAULT_LINK_FREQUENCY))
        payload.append(DEFAULT_RX_DECODING & 0xFF)
        payload.append(self.state.tx_level & 0xFF)
        payload.append(DEFAULT_TX_MODULATION & 0xFF)
        payload.append(DEFAULT_REGION_ID & 0xFF)
        payload.append(DEFAULT_INVENTORY_Q & 0xFF)
        payload.append(DEFAULT_INVENTORY_SESSION & 0xFF)
        payload.append(DEFAULT_INVENTORY_ROUNDS & 0xFF)
        payload.append(antenna_mask)
        payload.extend(encode_u16(DEFAULT_SCAN_SINGLE_TRIGGER_TIMEOUT_MS))
        payload.extend(encode_u16(DEFAULT_INVENTORY_TRIGGER_TIMEOUT_MS))
        payload.append(DEFAULT_SELECTED_ANTENNA & 0xFF)
        payload.extend(encode_u32(DEFAULT_OP_FLAGS))
        payload.append(DEFAULT_INVENTORY_TARGET & 0xFF)
        payload.append(DEFAULT_INVENTORY_EPC_LENGTH & 0xFF)
        payload.extend(b"\x00\x00")
        payload.extend(b"\x00\x00")
        payload.extend(b"\x00\x00")
        payload.extend(encode_u16(DEFAULT_TIMEOUT_MS))
        payload.extend(encode_u16(DEFAULT_TIMEOUT_MS))
        payload.extend(encode_u16(DEFAULT_TIMEOUT_MS))
        payload.extend(encode_u16(DEFAULT_TIMEOUT_MS))
        payload.extend(encode_u16(DEFAULT_PERIOD_SETUP_MS))
        payload.extend(b"\xFF\xFF\xFF\xFF")
        payload.extend(bytes((signed_byte(DEFAULT_POWER_OFFSET), 0x00, 0x00, 0x00)))
        payload.extend(encode_u32(antenna_mask))
        payload.append(DEFAULT_AUTOTUNE_MODE & 0xFF)
        payload.append(signed_byte(DEFAULT_AUTOTUNE_THRESHOLD_DBM))
        payload.extend(b"\xFF" * 32)
        payload.append(DEFAULT_RX_SENSITIVITY & 0xFF)
        payload.append(DEFAULT_RF_PROFILE & 0xFF)
        payload.extend(encode_u16(DEFAULT_TO_SLEEP_TIME_MS))
        return bytes(payload)


def normalize_epc(epc_hex: str) -> str:
    compact = "".join(epc_hex.strip().split()).upper()
    if not compact:
        raise ValueError("EPC cannot be empty")
    if len(compact) % 2 != 0:
        raise ValueError("EPC hex must have an even number of characters")
    try:
        bytes.fromhex(compact)
    except ValueError:
        raise ValueError("EPC must be valid hexadecimal")
    return compact


def signed_byte(value: int) -> int:
    return value & 0xFF


def default_pc_for_epc(epc: bytes) -> int:
    epc_words = len(epc) // 2
    return 0x3000 | ((epc_words & 0x1F) << 11)
