from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

SETUP_TXLEVEL = 4
SETUP_ANTMASK = 256
APP_PERM_SIG = 553883655
APP_ALLOW_PAIRING = 32
APP_HID_RFID = 2


class ScannerModel(Enum):
    EXA51 = "exa51"
    EXA81 = "exa81"

    @classmethod
    def parse(cls, raw: str) -> "ScannerModel":
        normalized = raw.strip().lower()
        for candidate in cls:
            if candidate.value == normalized:
                return candidate
        raise ValueError("Unsupported scanner model: %s" % raw)

    @property
    def label(self) -> str:
        return self.name


@dataclass
class FirmwareVersion:
    application_version: str = "5.0.0"
    bootloader_version: str = "1.0.0"


@dataclass
class QueuedTag:
    epc_hex: str
    rssi: int = -45
    antenna_id: int = 0
    frequency_khz: int = 865700
    pc: Optional[int] = None


@dataclass
class NurState:
    model: ScannerModel
    name: str
    address: str
    connectable: bool = True
    battery_percent: int = 100
    charging: bool = False
    voltage_mv: int = 4100
    current_ma: int = 0
    capacity_mah: int = 1000
    tx_level: int = 0
    antenna_mask: Optional[int] = None
    connection_info: str = "BLE"
    firmware: FirmwareVersion = field(default_factory=FirmwareVersion)
    barcode_reads_pending: bool = False
    imager_powered: bool = False
    imager_aim_on: bool = False
    inventory_running: bool = False
    id_buffer: Set[str] = field(default_factory=set)
    queued_tags: Deque[QueuedTag] = field(default_factory=deque)
    queued_barcodes: Deque[str] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.antenna_mask is None:
            self.antenna_mask = default_antenna_mask_for_model(self.model)
        self.battery_percent = clamp(self.battery_percent, 0, 100)
        self.tx_level = clamp(self.tx_level, 0, 19)

    @property
    def accessory_config_value(self) -> int:
        if self.model == ScannerModel.EXA51:
            return 1
        return 4

    @property
    def accessory_flags(self) -> int:
        return APP_ALLOW_PAIRING | APP_HID_RFID

    def antenna_mapping(self) -> List[Tuple[int, str]]:
        return antenna_mappings_for_model(self.model)

    def update_model(self, model: ScannerModel) -> None:
        previous_default_name = default_name_for_model(self.model)
        self.model = model
        self.antenna_mask = default_antenna_mask_for_model(model)
        if self.name == previous_default_name:
            self.name = default_name_for_model(model)

    def snapshot(self, connected_peers: Iterable[str]) -> Dict[str, object]:
        peers = list(connected_peers)
        return {
            "name": self.name,
            "address": self.address,
            "model": self.model.label,
            "connectable": self.connectable,
            "battery_percent": self.battery_percent,
            "charging": self.charging,
            "voltage_mv": self.voltage_mv,
            "current_ma": self.current_ma,
            "capacity_mah": self.capacity_mah,
            "tx_level": self.tx_level,
            "antenna_mask": self.antenna_mask,
            "firmware": "%s;%s"
            % (
                self.firmware.application_version,
                self.firmware.bootloader_version,
            ),
            "connection_info": self.connection_info,
            "inventory_running": self.inventory_running,
            "barcode_reads_pending": self.barcode_reads_pending,
            "imager_powered": self.imager_powered,
            "imager_aim_on": self.imager_aim_on,
            "id_buffer_size": len(self.id_buffer),
            "queued_tags": len(self.queued_tags),
            "queued_barcodes": len(self.queued_barcodes),
            "connected_peers": peers,
        }


def build_default_state(
    model: ScannerModel,
    name: Optional[str] = None,
    address: Optional[str] = None,
) -> NurState:
    return NurState(
        model=model,
        name=name or default_name_for_model(model),
        address=address or default_address_for_model(model),
    )


def default_name_for_model(model: ScannerModel) -> str:
    return "%s-EMU" % model.label


def default_address_for_model(model: ScannerModel) -> str:
    if model == ScannerModel.EXA51:
        return "F0:F1:F2:51:00:01"
    return "F0:F1:F2:81:00:01"


def default_antenna_mask_for_model(model: ScannerModel) -> int:
    if model == ScannerModel.EXA51:
        return int("11011", 2)
    return int("11", 2)


def antenna_mappings_for_model(model: ScannerModel) -> List[Tuple[int, str]]:
    if model == ScannerModel.EXA51:
        return [
            (0, "range antenna 0"),
            (1, "range antenna 1"),
            (2, "PROXIMITY"),
            (3, "range antenna 3"),
            (4, "range antenna 4"),
        ]
    return [
        (0, "CrossDipoleX"),
        (1, "CrossDipoleY"),
    ]


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
