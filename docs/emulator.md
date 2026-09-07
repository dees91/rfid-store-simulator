# Emulator Notes

This document describes the current emulator architecture and its practical compatibility limits.

## Goals

The emulator is intentionally narrow:

- behave like an EXA/NUR scanner over BLE
- satisfy the flows connected NUR hosts currently use
- be operator-friendly through the CLI REPL and the browser 3D UI

It is not trying to implement the entire Nordic ID SDK surface.

## Main Components

### `scanner_emu.state`

Holds the mutable device state:

- model
- name and BLE address
- connectable flag
- battery state
- firmware versions
- TX level
- antenna mask
- inventory state
- queued RFID tags
- queued barcodes

### `scanner_emu.ble_peripheral`

Owns:

- Bumble transport opening
- BLE advertising
- GATT service / characteristics
- active BLE connections
- RX writes from the connected host
- TX notifications back to the connected host

Key behavior:

- notification payloads are chunked by `att_mtu - 3`
- advertising restarts when runtime state changes
- device name changes are reflected in BLE advertising

### `scanner_emu.nur_session`

Owns:

- NUR frame decoding
- command dispatch
- response building
- unsolicited event building
- inventory record encoding
- barcode event encoding

This is the protocol core of the emulator.

### `scanner_emu.product_catalog`

Loads products with valid EAN-13 values from CSV catalog input for
operator-driven tag feeds and generated 3D store sessions.

CSV format is `ean,category,quantity` (utf-8-sig, case/space-tolerant
headers):

- `ean` (required): validated and normalized EAN-13
- `category` (optional shelf label, defaults to `Uncategorized`)
- `quantity` (optional per-product unit count, defaults to 1)

Rows with missing or invalid EANs are skipped with a warning; duplicate EANs
merge by summing quantities; negative or non-numeric quantities fail with a
row number. `ProductCatalog.categories` stays keyed by display label for feed
weighting, and `total_quantity` is the generated tag count.

### `scanner_emu.tag_feed`

Owns continuous synthetic RFID tag generation.

It samples products from a `ProductCatalog`, converts EAN-13 values to
SGTIN-96 EPCs, assigns RSSI/antenna metadata, and queues tags through the same
backend path as manual RFID queueing.

Supported rate profiles:

- constant
- wave
- burst

### `scanner_emu.store_3d`

Owns catalog-backed generated store sessions for the 3D simulator.

It loads the same CSV product catalogs as the backend feed, assigns a
session-stable shelf layout, generates unique SGTIN-96 EPC values with the
shared EPC helpers, and separates grouped render metadata from per-EPC scan
metadata.

Default behavior:

- each product's `quantity` is the tag target for that product; products with
  quantity 0 are not placed
- the quantity sum is the generated EPC count (`total_epc_count`)
- quantities that do not fit the shelf slots fail with the minimum
  `--shelf-count` that fits
- session layout is stable for the generated seed
- render groups are shelf/product groups, not individual EPC meshes
- summaries avoid dumping full catalog, product, or EPC lists
- summaries report per-label tag counts (`category_tag_counts`) without EANs
- generation fails if no product has a quantity greater than 0

### `scanner_emu.three_d`

Owns the local 3D bridge entrypoint and HTTP/SSE API.

It starts the existing `ScannerEmulatorController`, generates a `StoreSession`,
serves packaged Three.js assets, accepts browser scan/pose updates, and
selects scan candidates server-side from the generated store data.

Important runtime behavior:

- strict mode is default and never starts or stops inventory from browser
  scan actions
- standalone development mode is explicit through `--standalone-inventory`
- browser scan input is latched separately from scanner trigger IO; each click
  or Space press sends a short trigger press/release pulse
- scan candidate generation requires both the latched scan state and
  `inventory_running=True`
- stopping the latched scan state stops candidate generation immediately
- scanner power is a 3D-only simulation setting exposed through the browser HUD
  and bridge status; level 3 is the default previous max-power range/cone feel,
  while level 5 is the opt-in high-throughput setting
- lower simulated scanner power narrows the effective cone/range, lowers the
  per-pass scan budget, and uses deterministic per-EPC exposure counters so
  missed low-power candidates can be retried on later passes
- default max scan budget is `120` candidates per second, with a per-pose cap
  of `50`; level 3 keeps the older `60` candidates per second and `25`
  per-pose budget shape
- `--shelf-count` changes the generated shelf fixture count; for the same
  generated EPC count, lower values increase visual shelf density
- browser payloads expose grouped render data, not raw EPC lists
- the bridge resets its local attempted-candidate filter when it observes the
  scanner ID buffer transition from nonzero to zero, allowing the same visible
  shelf candidates to be attempted again after `CLEAR_ID_BUFFER`
- the bridge also clears low-power exposure counters on the same observed
  ID-buffer-clear boundary
- the bridge tracks per-group spatial progress from accepted RFID queue
  results only; duplicate-ignored results do not advance progress
- spatial progress resets on the same observed ID-buffer-clear boundary as the
  attempted-candidate filter, and stopping the scan latch does not reset it

### `scanner_emu.web_3d`

Contains the packaged browser UI.

The UI imports vendored Three.js, renders a first-person store, streams
normalized camera pose to the bridge, sends scan toggle requests, and
shows backend, peer, trigger, inventory, generated tag, accepted scan,
duplicate, rolling accepted-tags-per-second scan rate, ID-buffer, and spatial
scan progress status. Product
groups are one `InstancedMesh`; progress is updated by `group_id` without
rendering one mesh per EPC, with a separate unlit overlay for visible
unscanned/partial/complete states. Exact group counts appear only for the aimed
group near the reticle.

### `scanner_emu.emulator`

Composes:

- `BleScannerPeripheral`
- `NurSession`
- `TagFeed`
- shared `NurState`

It exposes async operations like:

- connectability changes
- model changes
- battery and firmware updates
- RFID queueing
- continuous RFID feed start/stop
- barcode emission
- disconnect

### `scanner_emu.controller`

This is the preferred programmatic API.

It runs the emulator on a dedicated background thread with its own `asyncio` loop and provides:

- thread-safe synchronous calls for UI and CLI
- structured events
- state snapshots
- backend lifecycle management

Rule:

- new operator actions should be added here first
- CLI and the 3D bridge should remain thin wrappers over this controller

### `scanner_emu.cli`

Provides the REPL operator shell.

It should stay as:

- a thin command parser
- minimal formatting
- no duplicated backend logic

## Current Supported Scope

The current implementation supports:

- discovery by BLE name
- BLE connect and disconnect
- `NurApi.connect()` handshake
- scanner type/config lookup
- battery and firmware reads
- antenna mapping reads
- antenna mask and TX-level writes
- inventory streaming
- backend continuous RFID tag feed from CSV product catalogs
  (programmatic controller API)
- generated 3D store sessions from CSV product catalogs
- local Three.js first-person 3D store UI through `scanner-emu-3d`
- trigger press/release events
- barcode aim / async scan / barcode result

## Known Real-World Compatibility

Confirmed by local testing:

- a connected host can discover the emulator
- a connected host can connect successfully
- scanner details flow works
- RFID inventory flow works when the EPC matches host expectations
- barcode flow works with accessory events

Confirmed on 2026-09-07 for the physical-device transport (macOS 26.5, Apple
Silicon, Bumble 0.0.234, ASUS USB-BT500 / Realtek RTL8761BU):

- `bumble-controller-info usb:0` loads `rtl8761bu_fw.bin` on the first start
  after plugging the dongle in and reports a Bluetooth 5.1 Realtek controller
- CLI and 3D entrypoints start on `--transport usb:0` without `sudo`
- all `HCI_LE_SET_*ADVERTISING*` commands return `SUCCESS` with legacy
  connectable PDUs and the `EXA51-EMU` complete local name
- host-side discovery, pairing, and the 3D flow with a BLE host on a
  physical device were confirmed by the user on the target macOS machine the
  same day

Confirmed after local implementation:

- full host discovery/connect/tag receipt through the new
  `scanner-emu-3d` flow was manually validated by the user on 2026-06-16,
  including 3D trigger IO, host-driven inventory start/stop, and generated
  shelf-tag receipt.

Inventory caveat:

- a tag reaching NUR storage is not enough for the host's inventory view
- the EPC must decode to an EAN that exists in the current inventory data set

## Known Differences Vs Real Hardware

These are important when debugging parity issues.

### Ping reply

Observed on a real EXA scanner:

- `PING` reply payload is `"OK"`

Current emulator:

- more permissive behavior is used
- if future parity problems appear, aligning this to `"OK"` is a cheap first fix

### Reader identity

EXA81 is modeled using strings and sizes that match observed real-scanner behavior reasonably closely.

EXA51 is more synthetic:

- serials
- reader identity strings
- some metadata fields

That is acceptable for current host flows but not a full hardware clone.

### Full setup and device capabilities

The emulator returns host-compatible payloads for:

- `cmd=34` full setup
- `cmd=11` device capabilities

This does not mean every field is fully understood semantically. Some fields are compatibility placeholders.

### Accessory subset only

Only the accessory commands currently used by connected hosts are implemented.

Unsupported commands should:

- fail explicitly
- never block the session

### Synthetic continuous feed

The continuous tag feed is an operator convenience, not a real hardware model.
It generates EPCs from catalog EAN-13 values and pushes them through the
existing inventory queue path.

Current caveats:

- feed status means the async feed task is running, not necessarily that tags
  are being emitted at that instant
- no tags are emitted while inventory is stopped
- the default generic SGTIN-96 conversion assumes a 7-digit company prefix
  partition
- host-side inventory display still depends on the decoded EAN matching the
  active product dataset
- high configured rates can create enough state-change events to make the
  controller event stream noisy

### 3D generated store

The 3D store simulator is an operator surface over the same BLE/NUR backend,
not a separate scanner implementation.

Current caveats:

- real-host end-to-end discovery and tag receipt has been manually
  validated, but future repeat validation still requires a compatible NUR
  host app plus a verified BLE emulator/device setup
- store sessions are generated at startup and are not persisted or regenerated
  through the browser API
- the RF model is intentionally simple: distance, main cone, weaker side cone,
  server-side scan rate limiting, and a 3D-only scanner power control
- simulated scanner power is separate from the NUR `tx_level` runtime
  state; lowering 3D power makes local generated-store scans less effective but
  does not change scanner config replies or TX-level commands
- scan selection is server-side, but host-side inventory display still depends
  on generated EPCs decoding to products present in the host dataset
- the bridge keeps a local attempted-candidate set for accepted or duplicate
  queue attempts so repeated poses progress through visible candidates. Missed
  low-power candidates are not added to that set and remain retryable. The
  attempted set and low-power exposure counters reset only after observing the
  scanner ID buffer clear to zero
- spatial progress is scanner-session progress in the emulator, not the
  connected host's inventory display. It advances for accepted backend scan
  results, ignores duplicate-suppressed attempts, and resets when the scanner ID
  buffer is cleared or the backend restarts.

## Operator Notes

### Inventory

When inventory is active:

- queued tags are flushed immediately as unsolicited inventory events
- accepted tags are added to the scanner ID buffer and duplicate normalized
  EPCs are ignored until the buffer is cleared

When inventory is inactive:

- tags stay queued until inventory starts or a manual flush happens

`CLEAR_ID_BUFFER` clears the scanner ID buffer and unsent queued RFID records.
Disconnect cleanup does not clear the buffer.

### Continuous tag feed

`ScannerEmulatorController.start_feed()` loads a CSV product catalog
(`scanner_emu.product_catalog.load_catalog`) and emits a continuous synthetic
RFID stream with constant, wave, or burst rate profiles
(`scanner_emu.tag_feed`). It is a programmatic API; no UI exposes it today.

Operational sequence:

- start the backend
- load the product catalog
- start inventory from the connected host or the REPL
- start the feed

The feed may be started before inventory, but it will wait and emit no tags
until `inventory_running` is true.

### Barcode

If the host has already requested `READ_BARCODE_ASYNC`:

- `barcode emit <code>` produces the result immediately

If not:

- the code is queued and delivered when the next async read starts

### Trigger

Trigger events are purely event notifications:

- press sends `direction=1`
- release sends `direction=0`

The trigger does not automatically start inventory or barcode reads inside the emulator.

In `scanner-emu-3d` strict mode, browser scan toggles send trigger IO pulses
only. The connected host remains responsible for sending inventory start and stop
commands. Standalone mode is only for local UI testing.

## Common Failure Modes

### `bumble-usb-probe` fails with `cannot find a suitable libusb-1.0`

The `libusb1` Python binding found no `libusb-1.0.dylib`. Normally the
`libusb-package` dependency ships one; check with:

```bash
.venv/bin/python -c "import libusb_package; print(libusb_package.get_library_path())"
```

If it prints `None`, reinstall the version Bumble pins (do not upgrade past
it, Bumble declares an exact pin):

```bash
.venv/bin/python -m pip install --force-reinstall --no-deps libusb-package==1.0.26.4
```

If the path is still `None`, install libusb separately
(`conda install -c conda-forge libusb` or `brew install libusb`) and export
`DYLD_FALLBACK_LIBRARY_PATH` pointing at its `lib` directory before running
any emulator command. In a conda environment drop the `.venv/bin/` prefix.
Seen on a target machine with a conda-based install. This is the canonical
description; README and the wiki link here.

### Emulator fails to start on `usb:0`

Check, in order:

- `bumble-usb-probe` lists the dongle as a Bluetooth HCI device
  (`ID 0B05:190E` for ASUS USB-BT500)
- the Realtek firmware file `rtl8761bu_fw.bin` exists in Bumble's firmware
  directory (macOS: `~/Library/Application Support/com.google.bumble/firmware/realtek`)
- `bumble-controller-info usb:0` succeeds; a libusb access or busy error
  means macOS owns the dongle: run
  `sudo nvram bluetoothHostControllerSwitchBehavior="never"`, re-plug, or as a
  last resort run as root with `BUMBLE_RTK_FIRMWARE_DIR` set (README
  "Physical device")
- with several dongles attached, address it as `usb:0B05:190E`

### Host does not list the emulator at all

Most likely causes, from the host's discovery rules:

- host Bluetooth is off or the host lacks permission to scan
- advertised name does not contain `exa`; the host filters by device name,
  so the name must be in the advertising payload
- `device connectable off` is active; the host drops non-connectable results

### Host keeps connecting to an old address

The host typically stores the paired scanner by BLE address. After changing
`--address` or the model, pair again from the host's scanner search screen.

### Host sees the device but cannot connect

Check:

- BLE notifications are enabled
- RX writes reach `NurSession`
- `PING` reply is emitted
- replies are not dropped due to missing active connections

### `GetInfoCommand` crashes on antenna mapping

Most likely cause:

- malformed `cmd=37` payload
- especially wrong string length or missing trailing NUL byte

### Inventory event reaches the host but product does not appear in the host's inventory view

Most likely cause:

- EPC is syntactically valid but not in the retail SGTIN-96 profile the host
  expects (7-digit company prefix, partition 5, filter 1)
- decoded EAN is not present in the current inventory dataset

Use `scanner_emu.epc.ean13_to_retail_epc()` for generating compatible test EPCs.

### Continuous feed is running but the host shows no products

Most likely causes:

- inventory has not been started yet
- the catalog has no valid EAN-13 values
- generated EPCs decode to EANs outside the host's current inventory dataset
- the default SGTIN-96 partition does not match the product namespace expected
  by the host

### Raw logs show `invalid` chunks after a valid inventory or setup packet

Most likely cause:

- the packet is simply fragmented across BLE notifications
- the transport layer is still behaving correctly

## Recommended Validation After Changes

Minimum:

```bash
.venv/bin/python -m compileall src
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

Basic smoke test:

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

Manual emulator run (Android emulator, or `--transport usb:0` for a BLE host
on a physical device after the README "Physical device" setup):

```bash
PYTHONPATH=src .venv/bin/python -m scanner_emu run --transport android-netsim --model exa51
```

3D local UI run:

```bash
.venv/bin/scanner-emu-3d --transport android-netsim --model exa51 --catalog path/to/catalog.csv
```

3D browser smoke checks used by this repository:

```bash
SCANNER_EMU_3D_TAG_TARGET=15000 PYTHONPATH=src:. python3 tests/web_3d_smoke_server.py
```

Then run `tests/web_3d_playwright_smoke.mjs` against the printed URL with
Playwright available. This smoke verifies screenshot capture, nonblank canvas
pixels, walking, aiming, trigger toggle behavior, visible progress pixels, and
the contextual aimed-group progress label.

## Open Questions

Still worth validating against a real scanner:

- whether `PING` should always reply with `"OK"`
- whether EXA51 should expose different reader-info identity strings
- whether any additional accessory subcommands appear in other host modules
- whether some setup fields need stricter parity for programming flows
- whether the generic SGTIN-96 feed should support per-catalog company prefix
  partition settings
- whether the 3D strict-mode trigger-to-inventory sequence matches every
  host screen once a device or netsim environment is available
