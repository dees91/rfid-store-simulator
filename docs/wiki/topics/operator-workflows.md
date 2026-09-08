# Operator Workflows

## Status

Current synthesis from the operator guide, emulator docs, and CLI/3D UI
structure as of 2026-09-07 (CSV catalog with per-product quantities).
Documentation links refreshed on 2026-09-08; runtime behavior is unchanged.

## CLI

Run directly from this checkout:

```bash
PYTHONPATH=src .venv/bin/python -m scanner_emu run --transport android-netsim --model exa51
```

Or use the installed entrypoint (Python `3.10+`, see the
[README installation steps](../../../README.md#1-install)):

```bash
.venv/bin/scanner-emu run --transport android-netsim --model exa51
```

The CLI is a thin REPL over `ScannerEmulatorController`.

## Physical Device

Status: accepted; transport side validated locally and host-side E2E with
a BLE host on a physical device confirmed by the user on the target
machine, both on 2026-09-07.

A BLE host on a physical device needs a dedicated USB HCI controller because
Bumble cannot use the Mac's built-in Bluetooth. The validated controller is
ASUS USB-BT500 (Realtek RTL8761BU, USB `0b05:190e`), used as
`--transport usb:0` with every entrypoint (`scanner-emu`, `scanner-emu-3d`).

Operator sequence (details in the
[physical-device guide](../../usage.md#physical-device)):

- once: `sudo nvram bluetoothHostControllerSwitchBehavior="never"`, re-plug;
- once: download `rtl8761bu_fw.bin` into Bumble's Realtek firmware directory
  (`bumble-rtk-fw-download` is broken in Bumble 0.0.234, use the direct
  linux-firmware download from the operator guide);
- check: `bumble-usb-probe`, then `bumble-controller-info usb:0`;
- run any entrypoint with `--transport usb:0`;
- on the host: search for `EXA51-EMU`, pair; re-pair after any `--address`
  or model change because the host remembers the stored address.

No `sudo` was needed on macOS 26.5 / Apple Silicon. Fallbacks when libusb
reports access/busy errors: re-check nvram, re-plug, run as root. With more
than one dongle use `usb:0B05:190E`. A conda-based install may need libusb
installed separately when `libusb-package` provides no library; see
`docs/emulator.md` "Common Failure Modes".

## 3D Store Simulator

Run the local 3D simulator after installing the package with Python 3.10+:

```bash
.venv/bin/scanner-emu-3d --transport android-netsim --model exa51 --catalog path/to/catalog.csv
```

Status: accepted behavior from the 3D RFID store simulator implementation.

The 3D simulator starts the same BLE/NUR backend as the CLI,
loads a CSV product catalog, generates a session-scoped store, and serves a
local Three.js browser UI. Each product's `quantity` is the tag target for
that product; the quantity sum is the generated EPC count. Quantities that do
not fit the shelf slots fail with the minimum `--shelf-count` that fits. The
browser receives grouped render metadata; individual EPC scan data stays
server-side in the Python bridge.

`--shelf-count` changes how many shelf fixtures are generated; when omitted
it defaults to the larger of 32 and the minimum fitting shelf count. For
the same generated tag count, lower shelf counts increase visual density on
each shelf. Session summaries report per-label tag counts
(`category_tag_counts`) without EAN lists.

The 3D UI shows spatial scanner-session progress per shelf/product group.
Progress increments only for accepted backend RFID queue results, not
duplicate-ignored attempts. Groups remain grouped render instances; the browser
updates progress visuals by stable `group_id`, shows aggregate progress in the
HUD, and shows exact counts only for the aimed group. The visible in-scene
progress affordance is an unlit overlay on product groups, separate from the
base product material, so unscanned, partial, and complete states remain
visible even when shelf lighting makes product meshes dark. Clearing the
scanner ID buffer or restarting the backend resets spatial progress; trigger
release does not.

The HUD also exposes simulated `Scanner Power`. The default `3 Medium` setting
keeps the previous max-power cone/range feel and older scan-budget shape. Level
`5 Max` is the opt-in high-throughput path, tuned for much faster accepted-tag
sweeps when the host/backend can keep up. Lower settings are local 3D simulation
only: they shrink effective scan cone/range, reduce per-pass budget, and
require closer or repeated passes before missed EPC candidates are queued. They
do not change the host-facing NUR `tx_level` state or backend feed behavior.
The HUD `Rate` metric is a rolling accepted-tags-per-second value, not accepted
tags per browser pose update.

Strict mode is the host compatibility path:

- browser scan input is latched separately from scanner trigger IO; each click
  or Space press sends a short scanner trigger press/release pulse;
- the connected host remains responsible for sending inventory start/stop NUR
  commands;
- scan candidates are queued only while the latched scan state is active and
  backend inventory is running.

Standalone development mode is explicit:

```bash
scanner-emu-3d --transport android-netsim --catalog path/to/catalog.csv --standalone-inventory
```

Use standalone mode for local browser testing without a connected host; do not
treat it as the protocol compatibility path.

## Config

Use `--config path/to/state.json` to override initial state. Known fields are
documented in `docs/usage.md`; keep loading tolerant when adding fields.

## Operator Actions

Current actions include:

- start and stop the BLE emulator;
- set connectable mode;
- switch EXA51 / EXA81 model;
- update battery, firmware, TX level, and connection info;
- queue and flush RFID tags;
- start and stop inventory stream;
- start and stop a continuous RFID tag feed from a CSV product catalog
  (programmatic controller API);
- run a first-person 3D generated store simulator from a CSV product
  catalog;
- emit barcode results;
- send trigger press/release events;
- disconnect active BLE peers.

## Caveats

- `rfid queue` only proves that the emulator emits a tag. The connected host
  may still ignore it if the EPC does not decode into an expected inventory
  item.
- Feed status reports the feed task state. Tags are emitted only while inventory
  is active.
- Very high feed rates can produce enough events to make the controller event
  stream noisy.
- Generic SGTIN-96 feed EPCs use a default 7-digit company prefix partition;
  host-side product matching still depends on the active inventory dataset.
- `barcode emit` returns immediately when an async barcode read is pending;
  otherwise it queues the value for the next read.
- Trigger events do not automatically start inventory or barcode reads inside
  the emulator.
- Re-reading the same 3D shelf does not emit already buffered EPCs until the
  scanner ID buffer is cleared by backend restart or `CLEAR_ID_BUFFER`.
- Low 3D scanner power misses are retryable; accepted/duplicate queue attempts
  still follow scanner ID buffer semantics and local retry state resets when the
  scanner ID buffer is observed clearing.
- 3D spatial progress uses the same scanner ID-buffer-clear reset boundary as
  repeated shelf scanning, but it is separate from the connected host's
  inventory display.
- Real-host discovery/connect/tag receipt through the 3D flow was
  manually validated by the user on 2026-06-16. The validated strict-mode flow
  includes host discovery/connect, 3D trigger IO, host-driven inventory
  start/stop, and generated shelf-tag receipt.
