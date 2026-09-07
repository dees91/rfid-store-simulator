# Project Snapshot

## Status

Accepted current context as of 2026-09-07, based on repository docs and code
layout.

## Summary

RFID Store Simulator is a standalone Python tool (package `scanner-emu`) that emulates EXA/NUR BLE scanner
behavior for RFID inventory software development and testing. It is
intentionally scoped to the host flows currently covered by the emulator, not
the complete NUR SDK.

## Runtime

- Python `3.10+` (required by `bumble` from PyPI).
- Runtime BLE dependency: `bumble` from PyPI.
- Vendored browser asset: Three.js 0.160.0 for the local 3D store UI.
- Package source: `src/scanner_emu/`.
- Package version: `0.1.0`.

## Main Public Surfaces

- CLI: `scanner-emu run`.
- 3D store simulator: `scanner-emu-3d`.
- Programmatic backend: `ScannerEmulatorController`.
- Config: optional JSON loaded through `--config`.
- BLE/NUR behavior documented in `docs/nur-protocol.md`.

## Module Responsibilities

- `api` - public dataclasses used by the CLI and the 3D bridge.
- `controller` - thread-safe synchronous backend API over an async emulator
  thread.
- `emulator` - composes BLE peripheral, NUR session, and shared state.
- `ble_peripheral` - Bumble transport, advertising, GATT, connections, RX/TX.
- `nur_session` - NUR decoding, command dispatch, replies, unsolicited events.
- `state` - authoritative mutable scanner state.
- `cli` - thin REPL.
- `epc` - retail SGTIN-96 EPC helper and generic EAN-13 to SGTIN-96 conversion.
- `product_catalog` - CSV product catalog (`ean,category,quantity`) loading
  for tag feeds and quantity-driven 3D store generation.
- `tag_feed` - continuous synthetic RFID tag generation and feed statistics.
- `store_3d` - catalog-backed generated store sessions, grouped render
  metadata, and per-group scan data.
- `three_d` - local 3D bridge entrypoint, HTTP/SSE API, static asset serving,
  trigger/pose handling, and server-side scan selection.
- `web_3d` - packaged Three.js browser UI assets.
- `config` - config loading and normalization.

## Validation

```bash
.venv/bin/python -m compileall src
```

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from scanner_emu.config import build_config
from scanner_emu.controller import ScannerEmulatorController

config = build_config(transport_spec='android-netsim', model='exa51', log_level='INFO')
controller = ScannerEmulatorController(emit_events=False)
assert config.transport_spec == 'android-netsim'
assert not controller.is_running
print('smoke-ok')
PY
```

## Maintenance Notes

- Keep CLI and 3D UI aligned by adding backend functionality to the
  controller first.
- Route protocol changes to `nur_session` or `ble_peripheral`.
- Update `docs/context.md`, `CHANGELOG.md`, and this wiki when changing public
  workflows, compatibility behavior, or durable project assumptions.
