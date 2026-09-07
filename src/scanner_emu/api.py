from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional, Tuple

from .state import NurState, ScannerModel, build_default_state


SUPPORTED_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True)
class FirmwareConfig:
    application_version: str = "5.0.0"
    bootloader_version: str = "1.0.0"


@dataclass(frozen=True)
class EmulatorConfig:
    transport_spec: str
    model: ScannerModel = ScannerModel.EXA51
    name: Optional[str] = None
    address: Optional[str] = None
    connectable: bool = True
    battery_percent: int = 100
    charging: bool = False
    voltage_mv: int = 4100
    current_ma: int = 0
    capacity_mah: int = 1000
    tx_level: int = 0
    antenna_mask: Optional[int] = None
    connection_info: str = "BLE"
    firmware: FirmwareConfig = field(default_factory=FirmwareConfig)
    log_level: str = "INFO"

    def normalized_log_level(self) -> str:
        normalized = self.log_level.upper()
        if normalized not in SUPPORTED_LOG_LEVELS:
            raise ValueError(
                "Unsupported log level: %s" % self.log_level
            )
        return normalized

    def build_state(self) -> NurState:
        state = build_default_state(
            model=self.model,
            name=self.name,
            address=self.address,
        )
        state.connectable = bool(self.connectable)
        state.battery_percent = int(self.battery_percent)
        state.charging = bool(self.charging)
        state.voltage_mv = int(self.voltage_mv)
        state.current_ma = int(self.current_ma)
        state.capacity_mah = int(self.capacity_mah)
        state.tx_level = int(self.tx_level)
        if self.antenna_mask is not None:
            state.antenna_mask = int(self.antenna_mask)
        state.connection_info = str(self.connection_info)
        state.firmware.application_version = self.firmware.application_version
        state.firmware.bootloader_version = self.firmware.bootloader_version
        return state


@dataclass(frozen=True)
class EmulatorSnapshot:
    name: str
    address: str
    model: ScannerModel
    connectable: bool
    battery_percent: int
    charging: bool
    voltage_mv: int
    current_ma: int
    capacity_mah: int
    application_version: str
    bootloader_version: str
    connection_info: str
    tx_level: int
    antenna_mask: int
    inventory_running: bool
    barcode_reads_pending: bool
    imager_powered: bool
    imager_aim_on: bool
    id_buffer_size: int
    queued_tags: int
    queued_barcodes: int
    connected_peers: Tuple[str, ...]
    feed_active: bool = False
    feed_total_tags: int = 0
    feed_current_rate: float = 0.0

    @classmethod
    def from_state(
        cls,
        state: NurState,
        connected_peers: Iterable[str],
        feed_active: bool = False,
        feed_total_tags: int = 0,
        feed_current_rate: float = 0.0,
    ) -> "EmulatorSnapshot":
        peers = tuple(connected_peers)
        return cls(
            name=state.name,
            address=state.address,
            model=state.model,
            connectable=state.connectable,
            battery_percent=state.battery_percent,
            charging=state.charging,
            voltage_mv=state.voltage_mv,
            current_ma=state.current_ma,
            capacity_mah=state.capacity_mah,
            application_version=state.firmware.application_version,
            bootloader_version=state.firmware.bootloader_version,
            connection_info=state.connection_info,
            tx_level=state.tx_level,
            antenna_mask=state.antenna_mask or 0,
            inventory_running=state.inventory_running,
            barcode_reads_pending=state.barcode_reads_pending,
            imager_powered=state.imager_powered,
            imager_aim_on=state.imager_aim_on,
            id_buffer_size=len(state.id_buffer),
            queued_tags=len(state.queued_tags),
            queued_barcodes=len(state.queued_barcodes),
            connected_peers=peers,
            feed_active=feed_active,
            feed_total_tags=feed_total_tags,
            feed_current_rate=feed_current_rate,
        )

    @property
    def firmware(self) -> str:
        return "%s;%s" % (
            self.application_version,
            self.bootloader_version,
        )

    def describe(self) -> str:
        peers = self.connected_peers or ("-",)
        return "\n".join(
            [
                "name=%s address=%s model=%s connectable=%s peers=%s"
                % (
                    self.name,
                    self.address,
                    self.model.label,
                    self.connectable,
                    ",".join(peers),
                ),
                "battery=%s%% charging=%s voltage_mv=%s current_ma=%s capacity_mah=%s"
                % (
                    self.battery_percent,
                    self.charging,
                    self.voltage_mv,
                    self.current_ma,
                    self.capacity_mah,
                ),
                "firmware=%s connection_info=%s tx_level=%s antenna_mask=0b%s"
                % (
                    self.firmware,
                    self.connection_info,
                    self.tx_level,
                    format(self.antenna_mask, "b"),
                ),
                "inventory_running=%s barcode_reads_pending=%s imager_powered=%s imager_aim_on=%s"
                % (
                    self.inventory_running,
                    self.barcode_reads_pending,
                    self.imager_powered,
                    self.imager_aim_on,
                ),
                "queued_tags=%s queued_barcodes=%s id_buffer=%s"
                % (self.queued_tags, self.queued_barcodes, self.id_buffer_size),
                "feed_active=%s feed_total_tags=%s feed_rate=%.1f/s"
                % (self.feed_active, self.feed_total_tags, self.feed_current_rate),
            ]
        )


@dataclass(frozen=True)
class EmulatorLogRecord:
    created_at: datetime
    level_name: str
    logger_name: str
    message: str

    @classmethod
    def create(
        cls,
        *,
        created_ts: float,
        level_name: str,
        logger_name: str,
        message: str,
    ) -> "EmulatorLogRecord":
        created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc).astimezone()
        return cls(
            created_at=created_at,
            level_name=level_name,
            logger_name=logger_name,
            message=message,
        )


@dataclass(frozen=True)
class EmulatorEvent:
    kind: str
    snapshot: Optional[EmulatorSnapshot] = None
    message: Optional[str] = None
    log_record: Optional[EmulatorLogRecord] = None

    @classmethod
    def backend_started(cls, snapshot: EmulatorSnapshot) -> "EmulatorEvent":
        return cls(kind="backend_started", snapshot=snapshot)

    @classmethod
    def backend_stopped(
        cls, snapshot: Optional[EmulatorSnapshot]
    ) -> "EmulatorEvent":
        return cls(kind="backend_stopped", snapshot=snapshot)

    @classmethod
    def state_changed(cls, snapshot: EmulatorSnapshot) -> "EmulatorEvent":
        return cls(kind="state_changed", snapshot=snapshot)

    @classmethod
    def action_result(cls, message: str) -> "EmulatorEvent":
        return cls(kind="action_result", message=message)

    @classmethod
    def error(
        cls, message: str, snapshot: Optional[EmulatorSnapshot] = None
    ) -> "EmulatorEvent":
        return cls(kind="error", message=message, snapshot=snapshot)

    @classmethod
    def log_event(cls, log_record: EmulatorLogRecord) -> "EmulatorEvent":
        return cls(kind="log_record", log_record=log_record)
