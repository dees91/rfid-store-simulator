# Changelog

All notable user-facing changes are documented in this file.

## [Unreleased]

### Added

- Issue templates for bug reports and compatibility reports, both stating
  that catalogs, captures, and inventory data must be synthetic.

### Changed

- Shorter README with a hardware-free demo quick start; detailed Bluetooth
  setup, catalog instructions, REPL commands, and configuration now live in
  the [operator guide](docs/usage.md).
- README screenshots show scan progress before and after two passes; the
  walkthrough link opens browser video playback instead of a file download.

## [0.1.0] - 2026-09-07

### Added

- Product name RFID Store Simulator; `scanner-emu` is the package and CLI
  name of the scanner emulator engine. Nordic ID, EXA, and NUR appear only in
  compatibility statements, with a trademark notice in `NOTICE.md` and the
  README.
- Synthetic reader identity strings (module name, FCC/IC ids, hardware
  version) in the reader-info reply; the reply layout matches real readers.
- BLE peripheral over Bumble with a Nordic UART-style service: advertising,
  GATT service, connection lifecycle, and a NUR session layer implementing a
  compatible command subset (inventory streaming, barcode reads, trigger
  events, ID buffer with duplicate suppression).
- CLI REPL (`scanner-emu run`) over the shared controller backend.
- `scanner-emu-3d`: a first-person 3D store simulator over the same backend,
  driven by CSV product catalogs (`ean,category,quantity`) with per-product
  quantities; scan-progress visualization, scanner power simulation, and an
  HTTP/SSE bridge with status, store, trigger, scan, power, and pose
  endpoints.
- Retail SGTIN-96 EPC helpers (`scanner_emu.epc`), including an
  EAN-13 to SGTIN-96 encoder with a configurable GS1 company prefix.
- Transports: `android-netsim`, `usb:0` (validated with ASUS USB-BT500), and
  `tcp-client` with a virtual controller for hardware-free runs.
- `scripts/media/`: reproducible media pipeline with a synthetic CSV catalog
  generator, a virtual controller with a fake BLE central, and Playwright
  capture.
- `video/`: Remotion source for the demo GIF and social preview. The GIF
  and the walkthrough MP4 are published as release assets rather than
  tracked files.
- Documentation: operator guide, NUR protocol and emulator notes, ADRs, and
  an LLM-maintained wiki. CI runs compile and unit checks.

### Compatibility Notes

- BLE advertising contract: Nordic UART-style service and characteristics,
  local name containing `EXA`, EXA51/EXA81 runtime model behavior.
- NUR behavior targets observations from real EXA scanners; see
  `docs/nur-protocol.md` for the exact supported command subset.

### Known Limitations

- Validated on macOS; Linux exposes the same Bumble transports but is
  untested here, Windows is untested.
- Only the documented NUR subset is implemented; unsupported commands fail
  explicitly instead of hanging.
- No BLE bonding; hosts remember the scanner by BLE address, so re-pair
  after changing `--address` or the model.
