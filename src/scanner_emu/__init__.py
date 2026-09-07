"""scanner-emu: BLE EXA/NUR scanner emulator, the engine of the RFID Store Simulator."""

from .api import (
    EmulatorConfig,
    EmulatorEvent,
    EmulatorLogRecord,
    EmulatorSnapshot,
    FirmwareConfig,
)
from .controller import ScannerEmulatorController
from .epc import ean13_to_retail_epc, ean13_to_sgtin96
from .product_catalog import Product, ProductCatalog, load_catalog
from .tag_feed import BurstRate, ConstantRate, FeedConfig, FeedStats, TagFeed, WaveRate

__all__ = [
    "__version__",
    "BurstRate",
    "ConstantRate",
    "EmulatorConfig",
    "EmulatorEvent",
    "EmulatorLogRecord",
    "EmulatorSnapshot",
    "FeedConfig",
    "FeedStats",
    "FirmwareConfig",
    "Product",
    "ProductCatalog",
    "ScannerEmulatorController",
    "TagFeed",
    "WaveRate",
    "ean13_to_retail_epc",
    "ean13_to_sgtin96",
    "load_catalog",
]

__version__ = "0.1.0"
