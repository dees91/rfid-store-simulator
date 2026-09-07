from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Dict, Iterable, Optional

from bumble import hci
from bumble.core import AdvertisingData
from bumble.device import AdvertisingType, Connection, Device, DeviceConfiguration
from bumble.gatt import Characteristic, CharacteristicValue, Service
from bumble.transport import open_transport

from .state import NurState


NUR_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUR_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUR_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


class BleScannerPeripheral:
    def __init__(
        self,
        transport_spec: str,
        state: NurState,
        logger: Optional[logging.Logger] = None,
        on_state_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.transport_spec = transport_spec
        self.state = state
        self._logger = logger or logging.getLogger("scanner_emu.ble")
        self._on_state_changed = on_state_changed
        self._rx_handler = None  # type: Optional[Callable[[bytes], Awaitable[None]]]
        self._transport_cm = None
        self._transport = None
        self.device = None  # type: Optional[Device]
        self.rx_characteristic = None  # type: Optional[Characteristic]
        self.tx_characteristic = None  # type: Optional[Characteristic]
        self._connections = {}  # type: Dict[int, object]

    def set_rx_handler(
        self, handler: Callable[[bytes], Awaitable[None]]
    ) -> None:
        self._rx_handler = handler

    async def start(self) -> None:
        if self._rx_handler is None:
            raise RuntimeError("RX handler must be set before starting BLE peripheral")

        self._transport_cm = await open_transport(self.transport_spec)
        entered = await self._transport_cm.__aenter__()
        self._transport = entered

        if hasattr(entered, "source") and hasattr(entered, "sink"):
            hci_source = entered.source
            hci_sink = entered.sink
        else:
            hci_source, hci_sink = entered

        config = DeviceConfiguration()
        config.name = self.state.name
        config.address = hci.Address(self.state.address)
        config.advertising_data = self._build_advertising_data()
        config.scan_response_data = b""
        config.connectable = self.state.connectable
        config.discoverable = True

        self.device = Device.from_config_with_hci(config, hci_source, hci_sink)
        # Bumble dispatches events through its emitter API; the older
        # ``device.listener`` attribute is no longer consulted.
        self.device.on(Device.EVENT_CONNECTION, self.on_connection)

        self.rx_characteristic = Characteristic(
            NUR_RX_UUID,
            Characteristic.Properties.WRITE
            | Characteristic.Properties.WRITE_WITHOUT_RESPONSE,
            Characteristic.WRITEABLE,
            CharacteristicValue(write=self._on_rx_write),
        )
        self.tx_characteristic = Characteristic(
            NUR_TX_UUID,
            Characteristic.Properties.NOTIFY,
            Characteristic.READABLE,
        )

        self.device.add_services(
            [
                Service(
                    NUR_SERVICE_UUID,
                    [self.rx_characteristic, self.tx_characteristic],
                )
            ]
        )

        await self.device.power_on()
        await self.apply_state()
        self._notify_state_changed()
        self._logger.info(
            "BLE peripheral started on transport=%s address=%s name=%s",
            self.transport_spec,
            self.state.address,
            self.state.name,
        )

    async def stop(self) -> None:
        try:
            await self.disconnect_all()
            if self.device is not None:
                await self.device.stop_advertising()
        finally:
            self._connections.clear()
            self.device = None
            self.rx_characteristic = None
            self.tx_characteristic = None
            if self._transport_cm is not None:
                await self._transport_cm.__aexit__(None, None, None)
                self._transport_cm = None
                self._transport = None
            self._notify_state_changed()

    async def apply_state(self) -> None:
        if self.device is None:
            return
        self.device.name = self.state.name
        await self.device.start_advertising(
            auto_restart=True,
            advertising_type=self._advertising_type(),
            advertising_data=self._build_advertising_data(),
            scan_response_data=b"",
        )
        self._notify_state_changed()

    async def send_bytes(self, payload: bytes) -> None:
        if self.device is None or self.tx_characteristic is None:
            return

        connections = self._active_connections()
        if not connections:
            self._logger.warning(
                "Dropping TX payload because there are no active BLE connections"
            )
            return

        self._logger.info(
            "TX %s bytes over notify to %s connection(s)",
            len(payload),
            len(connections),
        )
        for connection in connections:
            mtu = max(1, getattr(connection, "att_mtu", 23) - 3)
            for start in range(0, len(payload), mtu):
                chunk = payload[start : start + mtu]
                await self.device.notify_subscriber(
                    connection,
                    self.tx_characteristic,
                    chunk,
                )

    async def disconnect_all(self) -> None:
        for connection in self._active_connections():
            try:
                await connection.disconnect()
            except Exception as error:
                self._logger.warning("Disconnect failed: %s", error)

    def connected_addresses(self) -> Iterable[str]:
        for connection in self._active_connections():
            yield str(connection.peer_address)

    def connection_count(self) -> int:
        return len(self._connections)

    def on_connection(self, connection) -> None:
        self._connections[connection.handle] = connection
        connection.on(Connection.EVENT_DISCONNECTION, self.on_disconnection)
        self._logger.info("BLE connected: %s", connection.peer_address)
        self._notify_state_changed()

    def on_disconnection(self, reason) -> None:
        if self.device is not None:
            self._connections = dict(self.device.connections)
        else:
            self._connections.clear()
        self._logger.info("BLE disconnected, reason=%s", reason)
        self._notify_state_changed()

    def _on_rx_write(self, _connection, value: bytes) -> None:
        if self._rx_handler is None:
            return
        self._logger.info("RX %s bytes over GATT write", len(value))
        asyncio.create_task(self._rx_handler(bytes(value)))

    def _active_connections(self):
        if self.device is not None and self.device.connections:
            return list(self.device.connections.values())
        return list(self._connections.values())

    def _advertising_type(self) -> AdvertisingType:
        if self.state.connectable:
            return AdvertisingType.UNDIRECTED_CONNECTABLE_SCANNABLE
        return AdvertisingType.UNDIRECTED_SCANNABLE

    def _build_advertising_data(self) -> bytes:
        flags = int(
            AdvertisingData.Flags.LE_GENERAL_DISCOVERABLE_MODE
            | AdvertisingData.Flags.BR_EDR_NOT_SUPPORTED
        )
        return bytes(
            AdvertisingData(
                [
                    (AdvertisingData.FLAGS, bytes((flags,))),
                    (
                        AdvertisingData.COMPLETE_LOCAL_NAME,
                        self.state.name.encode("utf-8"),
                    ),
                ]
            )
        )

    def _notify_state_changed(self) -> None:
        if self._on_state_changed is not None:
            self._on_state_changed()
