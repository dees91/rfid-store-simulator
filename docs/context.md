# RFID Store Simulator Context

This document captures current project facts for future agents. Keep it compact
and update it when accepted working facts change. Use `docs/wiki/` for richer
maintained synthesis and open questions.

## Project Facts

- This checkout is a standalone Python package named `scanner-emu`.
- The package emulates EXA/NUR BLE scanner behavior for testing RFID
  inventory software without hardware.
- The runtime target is Python `3.10+` (required by `bumble` from PyPI).
- Runtime BLE uses `bumble` from PyPI.
- A BLE host on a physical device needs a dedicated USB HCI controller; the
  validated one is ASUS USB-BT500 (Realtek RTL8761BU, USB `0b05:190e`) on
  macOS with `--transport usb:0`. The Mac's built-in controller is not usable
  by Bumble.
- The operator UI is the browser-based 3D store simulator (`scanner-emu-3d`);
  the CLI REPL is the supported headless mode.
- Hardware-free runs use `scripts/media/virtual_controller.py` (Bumble
  virtual controller over `tcp-server`, optional fake BLE central peer) with
  `--transport tcp-client:127.0.0.1:9100`. README media is captured that way.
- The backend can run a continuous RFID tag feed from CSV product catalogs
  through `ScannerEmulatorController` (programmatic API).
- The 3D store simulator can generate a catalog-backed local store from CSV
  product catalogs and serve a Three.js browser UI through
  `scanner-emu-3d`.
- Catalog eligibility is based on valid EAN-13 values only.
- The current source package lives under `src/scanner_emu/`.
- Bumble and the Nordic ID NUR SDK are referenced upstream, not vendored.
- Current package version in `pyproject.toml` is `0.1.0`.

## Accepted Working Decisions

- Connected-host behavior and real-scanner observations are the
  compatibility target.
- The emulator should stay narrower than the full NUR SDK surface.
- CLI and 3D UI behavior must stay aligned through
  `ScannerEmulatorController`.
- New operator actions should be exposed through the controller first.
- BLE/NUR behavior belongs in `scanner_emu.ble_peripheral` and
  `scanner_emu.nur_session`, not in UI glue.
- Unsupported NUR commands should fail explicitly instead of hanging.
- BLE advertising must keep a name containing `EXA`.
- Nordic UART style service/characteristic UUIDs are part of the compatibility
  contract.
- Inventory record byte layout is compatibility-sensitive and should be changed
  only with capture/host verification.
- Continuous feed tags should use the existing controller and inventory queue
  path rather than a UI-only protocol shortcut.
- The 3D RFID store simulator is a local Three.js web surface served by a
  Python HTTP/SSE bridge over `ScannerEmulatorController`, not a visual-only
  prototype.
- In 3D strict mode, browser scan input is latched separately from scanner
  trigger IO: each click or Space press sends a short trigger press/release
  pulse, while the connected host remains responsible for starting and
  stopping inventory.
- Scanner ID buffer behavior should live in shared backend/NUR state and be
  cleared by backend restart or `CLEAR_ID_BUFFER`, not by per-UI cooldowns.
- The 3D bridge resets its local attempted-candidate set only after observing
  scanner `id_buffer_size` transition from nonzero to zero.
- The 3D HUD scanner power control is a local simulation setting, not NUR
  `tx_level`. Level 3 is the default and keeps the previous max-power
  range/cone feel; level 5 is opt-in high-throughput. Lower levels narrow the
  effective scan cone/range, lower scan budget, and use retryable low-power
  exposure counters that reset with the local attempted-candidate state after
  scanner ID buffer clear. The 3D HUD `Rate` metric is a rolling
  accepted-tags-per-second value.
- The 3D bridge tracks backend-authoritative scan progress per shelf/product
  group. It increments progress only for accepted RFID queue results, ignores
  duplicate-suppressed results, exposes aggregate and per-group totals without
  EPC lists, colors groups in the browser by progress ratio, shows exact counts
  only for the aimed group, and resets progress with scanner ID buffer clearing.
- CSV product catalogs (`ean,category,quantity`) are the product catalog
  input. `quantity` is the per-product unit count placed on the shelves; the
  quantity sum is the generated tag count. Generation fails with the minimum
  fitting `--shelf-count` when quantities exceed the shelf slots.
- `scanner-emu-3d --shelf-count` changes the generated shelf fixture count; for
  the same generated EPC count, lower values increase visual shelf density.
- Manual end-to-end validation reported by the user on 2026-06-16 completed
  the strict-mode 3D flow: host discovery/connect, 3D trigger IO event,
  host-driven inventory start/stop, and generated shelf-tag receipt.
- Physical-device transport (`--transport usb:0` with ASUS USB-BT500) was
  validated locally and confirmed end-to-end by the user with a BLE host on
  a physical device on 2026-09-07. Details: `CHANGELOG.md`,
  `docs/wiki/log.md`, ADR `docs/decisions/0005-ble-host-on-physical-device.md`.
- Host-side scanner discovery facts (name-based filtering, connectable-only,
  no bonding, address-based pairing memory) are recorded in `docs/usage.md`
  (Host discovery notes).
- The repo uses `docs/wiki/` as an LLM-maintained synthesis layer. Future
  agents should update the wiki index and log when adding reusable synthesis or
  ingesting new source material.

## Current Public Surfaces

- CLI entrypoint: `scanner-emu run`.
- 3D store entrypoint: `scanner-emu-3d`.
- Python backend API: `scanner_emu.controller.ScannerEmulatorController`.
- Feed/catalog API: `scanner_emu.product_catalog` and `scanner_emu.tag_feed`.
- 3D store/session API: `scanner_emu.store_3d` and `scanner_emu.three_d`.
- Config input: optional JSON passed with `--config`.
- Documented REPL commands in `docs/usage.md`.
- BLE/NUR behavior documented in `docs/nur-protocol.md`.

## Validation Commands

```bash
.venv/bin/python -m compileall src
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
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

## Source Material

- `README.md`
- `docs/usage.md`
- `AGENTS.md`
- `docs/nur-protocol.md`
- `docs/emulator.md`
- `https://github.com/google/bumble` and `https://github.com/NordicID/nur_sdk`
- `src/scanner_emu/`
- Host compatibility facts: `docs/usage.md` (Host discovery notes)

Some docs cite an observed real-scanner handshake. No packet captures are
part of this repository; use a task-provided capture when available.

## Public Safety Notes

- Do not commit real user, inventory, barcode, product, or scanner
  capture data unless explicitly approved.
- Treat real-device addresses, logs, host datasets, and capture files as
  sensitive until reviewed.
- Treat real product catalogs as sensitive input; do not commit them
  unless explicitly approved.
- Do not vendor the Nordic ID NUR SDK; it carries no license.
- Keep generated caches and bytecode out of commits.
