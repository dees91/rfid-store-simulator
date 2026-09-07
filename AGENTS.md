# AGENTS.md

This file defines project-specific guidance for agents working in this
repository. The emulator is a generic BLE/NUR RFID scanner emulator; keep
changes contained to this tool and never copy external app source, data, or
captures into this repository.

## Project Snapshot

- Product name: **RFID Store Simulator** (Nordic ID, EXA, NUR only in
  compatibility statements; see the trademark note in `NOTICE.md`). The Python package, CLI, and
  module keep the technical name `scanner-emu` / `scanner_emu` (the scanner
  emulator engine). Use the product name in user-facing copy and the package
  name for commands and code.

- `scanner_emu` is a Python `3.10+` BLE emulator for EXA/NUR scanner behavior
  for testing RFID inventory software without hardware.
- It is not a mobile-app module and should remain runnable as a standalone
  Python package from this repository root.
- Runtime BLE dependency is `bumble` from PyPI.
- Two transports are supported operationally: `android-netsim` for the
  Android emulator and `usb:0` for a BLE host on a physical device through a
  dedicated USB HCI dongle (validated with ASUS USB-BT500 /
  Realtek RTL8761BU on macOS). See `README.md` "Physical device".
- Do not vendor Bumble or the NUR SDK into this repository; reference upstream
  instead.
- The operator UI is the browser-based 3D store simulator served by
  `scanner-emu-3d`. The CLI REPL is the supported headless mode; there is no
  separate GUI application.

## Documentation Routing

Start here:

- `README.md` - public orientation, install/run commands, operator commands.
- `docs/context.md` - compact current context and accepted working facts.
- `docs/README.md` - stable docs index.
- `docs/wiki/index.md` - LLM-maintained synthesis index.

For protocol and emulator behavior:

- `docs/nur-protocol.md` - BLE/NUR frame and command compatibility notes.
- `docs/emulator.md` - architecture, runtime behavior, known gaps, validation.
- `docs/wiki/topics/protocol-compatibility.md` - maintained synthesis of
  compatibility constraints and open questions.

For maintenance, releases, and public-readiness:

- `CHANGELOG.md` - user-facing changes.
- `docs/release-policy.md` - compatibility surfaces and release checklist.
- `NOTICE.md` - attribution and distribution constraints.
- `docs/decisions/` - ADRs for durable decisions.
## Wiki Maintenance

- Treat `docs/wiki/` as the persistent LLM-maintained knowledge layer.
- Read `docs/wiki/index.md` before answering reusable project-context
  questions or ingesting new source material.
- Update `docs/wiki/index.md` when pages are added, renamed, removed, or
  materially repurposed.
- Append to `docs/wiki/log.md` for source ingests, reusable query synthesis,
  ADR synchronization, and lint/maintenance passes.
- Wiki pages may contain accepted, inferred, rejected, deferred, and open
  claims, but must label claim status clearly.
- The wiki is not a decision authority. Durable accepted decisions belong in
  `docs/decisions/` and compact onboarding facts belong in `docs/context.md`.

## Architecture

- `scanner_emu.api` contains the shared public dataclasses used by both CLI and
  3D UI.
- `scanner_emu.controller.ScannerEmulatorController` is the main programmatic
  backend API.
- `scanner_emu.emulator.ScannerEmulator` owns the live emulator instance and
  composes BLE + NUR layers.
- `scanner_emu.ble_peripheral` owns Bumble transport, advertising, GATT
  service, and connection lifecycle.
- `scanner_emu.nur_session` owns NUR command parsing, response building, and
  unsolicited events.
- `scanner_emu.state` is the authoritative mutable device state model.
- `scanner_emu.cli` is a thin REPL over the controller.
- `scanner_emu.three_d` and `scanner_emu.web_3d` are the browser operator UI
  (Python HTTP/SSE bridge plus packaged Three.js assets) over the same
  controller.
- `scanner_emu.epc` contains the retail SGTIN-96 EPC helpers. Keep RFID conversion
  logic there, not in UI code.
- `scanner_emu.config` is the shared config loading and normalization layer.
- `scripts/media/` holds the reproducible media pipeline (synthetic catalog,
  virtual controller with fake peer, Playwright capture); `video/` holds the
  Remotion source for the README GIF and social preview. Both use synthetic
  data only; see their READMEs before regenerating assets.

## Design Rules

- Keep CLI and 3D UI behavior aligned by adding backend functionality to the
  controller first.
- Do not add UI-only logic by parsing CLI stdout or by launching the CLI as a
  subprocess.
- New device mutations should update shared state and trigger state-change
  notifications.
- If a change affects BLE/NUR behavior, prefer implementing it in `nur_session`
  or `ble_peripheral`, not in UI or controller glue.
- Preserve the BLE contract expected by connected hosts:
  - Nordic UART style service/characteristics.
  - advertising name containing `EXA`.
  - current EXA51 / EXA81 runtime model behavior.
- Preserve protocol compatibility with NUR hosts and with observations from
  real EXA scanners when a task provides them. No packet captures are part
  of this repository.
- If a new NUR command is needed, implement the smallest compatible subset and
  keep unsupported commands explicit.

## Source Of Truth

- Treat connected-host behavior and real-scanner observations as the
  compatibility target, not theoretical NUR completeness.
- Treat a task-provided real-scanner handshake capture, when available, as
  the quickest reference for real scanner behavior. `docs/nur-protocol.md`
  records what earlier captures confirmed.
- Treat the public Nordic ID NUR SDK (`https://github.com/NordicID/nur_sdk`)
  as protocol reference material when frame layout or semantics are unclear.
  It carries no license and is not vendored here.
- Treat upstream Bumble (`https://github.com/google/bumble`, PyPI `bumble`) as
  BLE reference material; runtime imports use the PyPI dependency.

## Editing Rules

- Always check `git status --short` before and after non-trivial work.
- Do not commit unless the user explicitly asks.
- Do not revert user changes or use destructive git commands unless explicitly
  requested.
- Do not commit or rely on `__pycache__` changes.
- Keep ASCII unless the file already requires something else.
- Prefer small, local changes. This tool is already split into clear layers.
- If adding logs, route them through the existing `scanner_emu` logger so the
  3D bridge can surface them.
- If adding a new operator action, expose it through
  `ScannerEmulatorController` and only then wire it into the CLI or 3D UI.

## Validation

Use these checks after non-trivial changes:

```bash
.venv/bin/python -m compileall src
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

For lightweight API smoke testing:

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

For manual runs:

```bash
PYTHONPATH=src .venv/bin/python -m scanner_emu run --transport android-netsim --model exa51
```

BLE host on a physical device through the USB dongle (setup steps in `README.md`):

```bash
.venv/bin/scanner-emu run --transport usb:0 --model exa51
```

3D operator UI:

```bash
.venv/bin/scanner-emu-3d --transport android-netsim --model exa51 --catalog path/to/catalog.csv
```

## Common Pitfalls

- The host-side compatibility target is stricter than the protocol docs
  alone. Real captures matter.
- Inventory records are sensitive to byte layout. Small field shifts break
  downstream parsing.
- Antenna mappings and accessory replies are consumed by host code that expects
  exact formats.
- 3D UI work must not fork backend behavior away from CLI behavior.
- If Bumble import fails, check the Python version before changing code;
  `bumble` from PyPI needs Python `3.10+`.
- `usb:0` failing with a Realtek dongle usually means the firmware file is
  missing from Bumble's firmware directory, or macOS still owns the dongle.
  Check `bumble-controller-info usb:0` before suspecting emulator code.
- Hosts typically find scanners by device name containing `exa` and remember
  the paired scanner by BLE address. Keep `EXA` in the name and expect a
  re-pair after changing `--address` or model.
