from __future__ import annotations

import logging
from typing import Callable, Optional

from .api import EmulatorSnapshot
from .ble_peripheral import BleScannerPeripheral
from .nur_session import NurSession, QueueTagResult
from .state import (
    ScannerModel,
    NurState,
)
from .tag_feed import FeedConfig, FeedStats, TagFeed


class ScannerEmulator:
    def __init__(
        self,
        transport_spec: str,
        state: NurState,
        logger: Optional[logging.Logger] = None,
        on_state_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.state = state
        self._logger = logger or logging.getLogger("scanner_emu")
        self._on_state_changed = on_state_changed
        self._peripheral = BleScannerPeripheral(
            transport_spec,
            state,
            self._logger,
            on_state_changed=self._notify_state_changed,
        )
        self._session = NurSession(
            state,
            self._peripheral.send_bytes,
            self._logger,
            on_state_changed=self._notify_state_changed,
        )
        self._peripheral.set_rx_handler(self._session.feed_bytes)
        self._tag_feed = TagFeed(
            self._queue_rfid_result, state, self._logger
        )

    async def start(self) -> None:
        await self._peripheral.start()
        self._notify_state_changed()

    async def stop(self) -> None:
        if self._tag_feed.is_running:
            await self._tag_feed.stop()
        await self._session.disconnect_cleanup()
        await self._peripheral.stop()
        self._notify_state_changed()

    async def set_connectable(self, enabled: bool) -> str:
        self.state.connectable = enabled
        await self._peripheral.apply_state()
        self._notify_state_changed()
        return "connectable=%s" % ("on" if enabled else "off")

    async def set_model(self, model: ScannerModel) -> str:
        self.state.update_model(model)
        await self._peripheral.apply_state()
        self._notify_state_changed()
        return "model=%s antenna_mask=0b%s" % (
            self.state.model.label,
            format(self.state.antenna_mask or 0, "b"),
        )

    async def set_battery(self, percent: int) -> str:
        self.state.battery_percent = max(0, min(100, percent))
        self._notify_state_changed()
        return "battery=%s%%" % self.state.battery_percent

    async def set_firmware(self, app_version: str, bootloader_version: str) -> str:
        self.state.firmware.application_version = app_version
        self.state.firmware.bootloader_version = bootloader_version
        self._notify_state_changed()
        return "firmware=%s;%s" % (
            self.state.firmware.application_version,
            self.state.firmware.bootloader_version,
        )

    async def set_tx_level(self, tx_level: int) -> str:
        self.state.tx_level = max(0, min(19, tx_level))
        self._notify_state_changed()
        return "tx_level=%s" % self.state.tx_level

    async def send_trigger(self, pressed: bool) -> str:
        await self._session.send_trigger(pressed)
        self._notify_state_changed()
        return "trigger=%s" % ("pressed" if pressed else "released")

    async def queue_rfid(self, epc_hex: str, rssi: int, antenna_id: int) -> str:
        result = await self._queue_rfid_result(epc_hex, rssi, antenna_id)
        if not result.accepted:
            return "duplicate_ignored EPC=%s id_buffer_size=%s" % (
                result.epc_hex,
                result.id_buffer_size,
            )
        return "accepted EPC=%s rssi=%s antenna=%s flushed_tags=%s id_buffer_size=%s" % (
            result.epc_hex,
            rssi,
            antenna_id,
            result.flushed,
            result.id_buffer_size,
        )

    async def flush_rfid(self) -> str:
        flushed = await self._session.flush_tags()
        self._notify_state_changed()
        return "flushed_tags=%s" % flushed

    async def start_inventory(self) -> str:
        flushed = await self._session.start_inventory()
        self._notify_state_changed()
        return "inventory_running=true flushed_tags=%s" % flushed

    async def stop_inventory(self) -> str:
        await self._session.stop_inventory()
        self._notify_state_changed()
        return "inventory_running=false"

    async def emit_barcode(self, code: str) -> str:
        sent = await self._session.emit_barcode(code)
        self._notify_state_changed()
        return "barcode_%s=%s" % ("sent" if sent else "queued", code)

    async def start_feed(self, config: FeedConfig) -> str:
        await self._tag_feed.start(config)
        self._notify_state_changed()
        return "feed_started products=%s rate=%s" % (
            len(config.catalog),
            config.rate.describe() if hasattr(config.rate, "describe") else "custom",
        )

    async def stop_feed(self) -> str:
        total = self._tag_feed.stats.total_tags_fed
        await self._tag_feed.stop()
        self._notify_state_changed()
        return "feed_stopped total_tags=%s" % total

    async def get_feed_status(self) -> str:
        stats = self._tag_feed.stats
        return "feed_active=%s total_tags=%s rate=%.1f/s elapsed=%.1fs" % (
            self._tag_feed.is_running,
            stats.total_tags_fed,
            stats.current_rate,
            stats.elapsed_seconds,
        )

    def feed_stats(self) -> Optional[FeedStats]:
        if not self._tag_feed.is_running:
            return None
        return self._tag_feed.stats

    async def disconnect(self) -> str:
        await self._session.disconnect_cleanup()
        await self._peripheral.disconnect_all()
        self._notify_state_changed()
        return "disconnect_requested"

    def snapshot(self) -> EmulatorSnapshot:
        stats = self._tag_feed.stats
        return EmulatorSnapshot.from_state(
            self.state,
            self._peripheral.connected_addresses(),
            feed_active=self._tag_feed.is_running,
            feed_total_tags=stats.total_tags_fed,
            feed_current_rate=stats.current_rate,
        )

    def describe_state(self) -> str:
        return self.snapshot().describe()

    async def _queue_rfid_result(
        self, epc_hex: str, rssi: int, antenna_id: int
    ) -> QueueTagResult:
        return await self._session.queue_tag(epc_hex, rssi, antenna_id)

    def _notify_state_changed(self) -> None:
        if self._on_state_changed is not None:
            self._on_state_changed()
