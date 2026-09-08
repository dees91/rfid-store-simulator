# Repository Documentation Source Summary

## Status

Ingested on 2026-06-15 from the current standalone checkout; refreshed for
the 0.1.0 release on 2026-09-07 and documentation reorganization on 2026-09-08.

## Sources

- `../../../README.md`
- `../../../AGENTS.md`
- `../../README.md`
- `../../usage.md`
- `../../context.md`
- `../../nur-protocol.md`
- `../../emulator.md`
- `../../../pyproject.toml`
- `../../../src/scanner_emu/`

## Summary

The repository is a standalone Python package that emulates EXA/NUR BLE
scanner behavior for RFID inventory software development and testing. It
exposes a CLI REPL, a browser-based 3D store simulator, and a shared backend
controller.

The public README leads with a hardware-free demo using synthetic products.
Detailed setup, catalogs, REPL commands, and configuration live in the
operator guide (`docs/usage.md`).

The current implementation is intentionally narrow: scanner discovery,
connect/details, antenna configuration, RFID inventory, barcode reads, and
trigger events. It does not aim to implement the complete NUR SDK.

Product catalogs are CSV tables (`ean,category,quantity`) with per-product
quantities; the quantity sum is the generated 3D store tag count.

The main implementation layering is:

- `scanner_emu.api` - public dataclasses and event/snapshot types.
- `scanner_emu.controller` - thread-safe backend API for the CLI and 3D UI.
- `scanner_emu.emulator` - live emulator composition.
- `scanner_emu.ble_peripheral` - Bumble transport, advertising, GATT, and
  connection lifecycle.
- `scanner_emu.nur_session` - NUR frame parsing, command dispatch, replies,
  and unsolicited events.
- `scanner_emu.state` - mutable device state model.
- `scanner_emu.cli` - thin REPL.
- `scanner_emu.three_d` and `scanner_emu.web_3d` - 3D bridge and browser UI.
- `scanner_emu.epc` - retail SGTIN-96 EPC helper logic.
- `scanner_emu.config` - config loading and normalization.

## Accepted Working Facts

- Runtime target is Python `3.10+` (required by `bumble` from PyPI).
- Runtime BLE dependency is PyPI `bumble`.
- CLI and 3D UI behavior should stay aligned through
  `ScannerEmulatorController`.
- BLE/NUR protocol behavior should live in `nur_session` or
  `ble_peripheral`, not UI glue.
- Documented commands in this standalone checkout use `src/` and
  `pip install -e .`.

## Open Or Watch Items

- Some references depend on observed real-scanner captures, which are not
  part of this repository.
