from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from .api import EmulatorConfig, FirmwareConfig
from .state import ScannerModel


def load_config(path: Optional[str]) -> dict[str, Any]:
    if not path:
        return {}
    raw = Path(path).read_text(encoding="utf-8")
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("Config file must contain a JSON object")
    return loaded


def build_config(
    *,
    transport_spec: str,
    raw_config: Optional[Mapping[str, Any]] = None,
    model: Optional[str] = None,
    name: Optional[str] = None,
    address: Optional[str] = None,
    log_level: str = "INFO",
) -> EmulatorConfig:
    loaded = dict(raw_config or {})
    model_value = _parse_model(model or loaded.get("model", "exa51"))
    firmware = loaded.get("firmware") or {}

    return EmulatorConfig(
        transport_spec=transport_spec,
        model=model_value,
        name=name if name is not None else _optional_str(loaded.get("name")),
        address=address
        if address is not None
        else _optional_str(loaded.get("address")),
        connectable=_optional_bool(loaded.get("connectable"), True),
        battery_percent=_optional_int(loaded.get("battery_percent"), 100),
        charging=_optional_bool(loaded.get("charging"), False),
        voltage_mv=_optional_int(loaded.get("voltage_mv"), 4100),
        current_ma=_optional_int(loaded.get("current_ma"), 0),
        capacity_mah=_optional_int(loaded.get("capacity_mah"), 1000),
        tx_level=_optional_int(loaded.get("tx_level"), 0),
        antenna_mask=_optional_int(loaded.get("antenna_mask"), None),
        connection_info=_optional_str(loaded.get("connection_info"), "BLE"),
        firmware=FirmwareConfig(
            application_version=_optional_str(
                firmware.get("application_version"), "5.0.0"
            ),
            bootloader_version=_optional_str(
                firmware.get("bootloader_version"), "1.0.0"
            ),
        ),
        log_level=log_level,
    )


def _parse_model(raw: Any) -> ScannerModel:
    if isinstance(raw, ScannerModel):
        return raw
    return ScannerModel.parse(str(raw))


def _optional_str(raw: Any, default: Optional[str] = None) -> Optional[str]:
    if raw is None:
        return default
    return str(raw)


def _optional_bool(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    return bool(raw)


def _optional_int(raw: Any, default: Optional[int]) -> Optional[int]:
    if raw is None:
        return default
    return int(raw)
