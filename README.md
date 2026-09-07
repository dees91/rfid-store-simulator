# RFID Store Simulator

Walk a virtual store. Scan it with a virtual RFID scanner. Built on
`scanner-emu`, a Python emulator compatible with Nordic ID EXA51 / EXA81
handhelds over Bluetooth Low Energy: your app connects to it exactly as it
would to the real scanner, and a first-person 3D store lets you walk past
shelves and scan them with the mouse.

<p align="center">
  <img src="https://github.com/dees91/rfid-store-simulator/releases/download/v0.1.0/demo.gif" width="960" alt="RFID Store Simulator demo: a diagram of a host app talking to the emulator over BLE, then the 3D store simulator scanning shelves that turn green, and the CLI REPL">
</p>

[Full-length 3D walkthrough (MP4, 34 s)](https://github.com/dees91/rfid-store-simulator/releases/download/v0.1.0/3d-store-demo.mp4)

The GIF and MP4 are release assets, not tracked files, so the repository
stays small; screenshots below live in `docs/media/`.

## Why

Your app talks to the scanner over BLE using Nordic ID's NUR protocol.
Testing it meant having a scanner on the desk, a tagged product to wave in
front of it, and a matching catalog. The emulator removes the first two: it
advertises as `EXA51-EMU`, answers the NUR handshake, and streams inventory
records for tags you queue from a script or "scan" in the 3D store. The
catalog stays yours; the emulator generates its tags from your CSV product
catalog.

```mermaid
flowchart LR
    App["Your app<br/>(any BLE host)"]
    Emu["scanner-emu<br/>NUR session + BLE peripheral<br/>(Bumble)"]
    UI["3D store simulator<br/>or CLI REPL"]
    App <-- "BLE · Nordic UART service · NUR frames" --> Emu
    UI -- "queue tags, trigger, barcode" --> Emu
    Emu -. "USB Bluetooth dongle (host on a physical device)<br/>android-netsim (Android emulator)<br/>virtual controller (no hardware)" .-> Radio["HCI controller"]
```

What the emulator covers, and nothing more: scanner search and connect,
scanner details, antenna mask and TX level, RFID inventory streaming, barcode
reads, and trigger events. `docs/nur-protocol.md` lists the exact commands.

## What it looks like

| Walk into an aisle | Scan a shelf | See what is left |
| --- | --- | --- |
| ![Aisle with unscanned red shelves](docs/media/3d-store-aisle.png) | ![Scanning a shelf, groups turning green](docs/media/3d-store-scanning.png) | ![Aisle after two passes, mostly green](docs/media/3d-store-final.png) |

Red groups are unscanned, amber are partial, green are complete. The HUD
shows totals, the accepted-tag rate, the scanner ID buffer, and a
`Scanner Power` slider that narrows or widens the simulated read cone.

## Install

Python `3.10` or newer. The BLE stack is
[Bumble](https://github.com/google/bumble) from PyPI.

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e .
```

Or with plain `pip`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

A conda environment works the same way with `pip install -e .`; then drop
the `.venv/bin/` prefix from the commands below.

## Quick start

Pick a radio. The `--transport` value goes straight to Bumble, so any
[Bumble transport](https://google.github.io/bumble/transports/index.html)
works; these three are the ones this project uses.

| You have | `--transport` | Notes |
| --- | --- | --- |
| Android emulator | `android-netsim` | Nothing to set up. |
| A BLE host on a physical device | `usb:0` | Needs a USB Bluetooth dongle, see [Physical device](#physical-device). |
| No Bluetooth at all | `tcp-client:127.0.0.1:9100` | Virtual controller, see [Try it without hardware](#try-it-without-hardware). |

Then start the 3D store from your CSV product catalog:

```bash
.venv/bin/scanner-emu-3d --transport android-netsim --model exa51 --catalog path/to/catalog.csv
```

Open the printed URL, connect your app to `EXA51-EMU`, click `Start Scan` (or
press Space), and aim at shelves. Or skip the browser and drive the emulator
from the REPL:

```bash
.venv/bin/scanner-emu run --transport android-netsim --model exa51
```

The emulator advertises with a local name containing `EXA` and a fixed
static random address (`F0:F1:F2:51:00:01` for EXA51, `F0:F1:F2:81:00:01`
for EXA81, `--address` overrides both).

## Physical device

Validated on macOS on Apple Silicon with an **ASUS USB-BT500** dongle
(Realtek RTL8761BU, USB ID `0b05:190e`). A Mac's built-in Bluetooth is not
usable by Bumble, hence the dongle. Bumble's Realtek driver loads the
firmware into the dongle the first time it is used after being plugged in.

### One-time setup

1. Tell macOS never to take over an external USB Bluetooth controller, then
   unplug and re-plug the dongle:

   ```bash
   sudo nvram bluetoothHostControllerSwitchBehavior="never"
   ```

2. Download the Realtek firmware into the directory Bumble searches. On
   macOS that is `~/Library/Application Support/com.google.bumble/firmware/realtek`.
   If `BUMBLE_RTK_FIRMWARE_DIR` is set, Bumble looks only there; otherwise
   it checks that directory and then the current directory. The files are
   pinned to the linux-firmware `20260810` release and verified by checksum:

   ```bash
   FW_DIR="$HOME/Library/Application Support/com.google.bumble/firmware/realtek"
   mkdir -p "$FW_DIR"
   BASE="https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/rtl_bt"
   TAG=20260810
   curl -fsSL -o "$FW_DIR/rtl8761bu_fw.bin" "$BASE/rtl8761bu_fw.bin?h=$TAG"
   curl -fsSL -o "$FW_DIR/rtl8761bu_config.bin" "$BASE/rtl8761bu_config.bin?h=$TAG"
   cd "$FW_DIR" && shasum -a 256 -c <<'SUMS' && cd -
   1d7a9597349ad89344fa16c1913d3e39e9a12e966e417ca16871bc79bbe59edb  rtl8761bu_fw.bin
   6c28a3f07c6a30ed208c4b64862a23f02b7d93543ea980edd24df16bab45095f  rtl8761bu_config.bin
   SUMS
   ```

   `bumble-rtk-fw-download --single rtl8761bu` is the intended tool for
   this. If it fails with `ModuleNotFoundError: No module named 'tools'`
   (seen in Bumble 0.0.234), use the direct download above.

3. Check that Bumble sees the dongle and can initialize it:

   ```bash
   .venv/bin/bumble-usb-probe
   .venv/bin/bumble-controller-info usb:0
   ```

   `bumble-usb-probe` must list `ID 0B05:190E` with transport names `usb:0`
   and `usb:0B05:190E`. `bumble-controller-info` must print
   `Manufacturer: Realtek Semiconductor Corporation`. On the first start
   after plugging the dongle in it also logs
   `loaded FW image rtl8761bu_fw.bin`; later starts skip the download
   because the firmware stays loaded until the dongle is unplugged. A
   warning `Firmware file rtl8761bu_fw.bin not found` means step 2 was
   skipped or used a different directory. If `bumble-usb-probe` fails with
   `cannot find a suitable libusb-1.0`, see the failure modes in
   [`docs/emulator.md`](./docs/emulator.md).

### Run

```bash
.venv/bin/scanner-emu-3d --transport usb:0 --model exa51 --catalog path/to/catalog.csv
# or
.venv/bin/scanner-emu run --transport usb:0 --model exa51
```

The startup log must contain
`BLE peripheral started on transport=usb:0 address=F0:F1:F2:51:00:01 name=EXA51-EMU`.
With `--log-level DEBUG` every `HCI_LE_SET_*ADVERTISING*` command should
report `status: SUCCESS`.

If several HCI dongles are attached, use `usb:0B05:190E` instead of `usb:0`.
If Bumble reports a libusb access or busy error, macOS still owns the
dongle: re-check the `nvram` setting, re-plug the dongle, and as a last
resort run the same command as root (libusb can only detach the macOS driver
as root). Pass the firmware directory explicitly so root does not depend on
your `HOME`:

```bash
BUMBLE_RTK_FIRMWARE_DIR="$FW_DIR" sudo -E .venv/bin/scanner-emu run --transport usb:0 --model exa51
```

### Host discovery notes

What matters when pairing a host with the emulator:

- Filter scan results by device name containing `exa` (case-insensitive)
  and by the advertisement being connectable. The default names
  `EXA51-EMU` / `EXA81-EMU` pass; keep `EXA` in any custom `--name`.
- The emulator uses a stable static random address
  (`F0:F1:F2:51:00:01` for EXA51, `F0:F1:F2:81:00:01` for EXA81 unless
  `--address` overrides it). Hosts typically remember the scanner by BLE
  address, so after changing `--address`, or switching model, pair again
  from the host's scanner search screen.
- No BLE bonding is used, so no pairing dialog appears on the host.

## 3D store simulator

`scanner-emu-3d` starts the emulator, generates a session-scoped store from
a CSV product catalog, and serves a local Three.js UI bound to `127.0.0.1`.
The browser gets grouped render data for shelves and products; the
individual EPCs stay in the Python bridge.

Options:

```text
--catalog <path>          CSV product catalog (ean,category,quantity columns)
--seed <int>              reproduce a generated store layout
--shelf-count <count>     number of shelf fixtures; defaults to the larger of
                          32 and the minimum that fits the catalog quantities
--scan-rate <rate>        max scan candidates per second, default 120
--standalone-inventory    browser scan toggle also starts/stops inventory for local UI testing
```

How the store is generated. The catalog is a CSV table with
`ean,category,quantity` columns. Empty categories fall back to
`Uncategorized` and empty quantities default to 1; `quantity` is the number
of units of that product placed on the shelves, and the sum of all
quantities is the number of RFID tags generated. If the quantities do not
fit the shelf slots, generation fails with the minimum `--shelf-count`
that fits.

The host-facing flow (strict mode, the default):

1. Start `scanner-emu-3d` and open the printed URL in a desktop browser.
2. Connect your app to the advertised EXA scanner.
3. Click `Start Scan` or press Space once. This latches local scan intent on
   and sends one trigger press/release pulse to the host.
4. Your app starts inventory in response to the trigger, as it would with a
   real scanner.
5. Aim at shelves. Matching generated EPCs go through the normal NUR
   inventory path to your app.
6. Click `Stop Scan` or press Space again. This clears the scan intent and
   sends another pulse so the host can stop inventory.

`--standalone-inventory` is for browser-only testing: the scan toggle then
also starts and stops inventory itself. It is not the compatibility path.

Two behaviors worth knowing before you wonder why a shelf stopped counting:

- Re-reading the same shelf does not emit already buffered EPCs until the
  scanner ID buffer is cleared, by a backend restart or the host sending
  `NUR_CMD_CLEAR_ID_BUFFER`. Spatial progress resets on the same boundary;
  stopping the scan does not reset it.
- `Scanner Power` is a local simulation control, not the NUR `tx_level`.
  Level `3 Medium` (default) keeps the original cone, range, and roughly 60
  candidates per second. Level `5 Max` is an opt-in sweep mode near 100
  accepted tags per second when the host and backend keep up. Lower levels
  shrink the cone and range and need closer or repeated passes; missed
  candidates stay retryable. The HUD `Rate` is a rolling accepted-tags-per-
  second value.

## Try it without hardware

`scripts/media/virtual_controller.py` serves a Bumble virtual controller over
TCP and, with `--peer`, a fake BLE central that scans for `EXA`, connects,
and subscribes to the notification characteristic. No real device can reach
it; it exists so the emulator boots, advertises, and streams to a peer on a
machine with no Bluetooth, which is how this README's media was captured.

```bash
.venv/bin/python scripts/media/make_demo_catalog.py demo.csv
.venv/bin/python scripts/media/virtual_controller.py --port 9100 --peer &
.venv/bin/scanner-emu-3d --transport tcp-client:127.0.0.1:9100 --catalog demo.csv --standalone-inventory
```

`make_demo_catalog.py` writes a synthetic catalog (invented categories,
EAN-13 values under the GS1 documentation prefix `4012345`). Real product
data is never part of this repository.

## REPL commands

`scanner-emu run` opens an interactive prompt on top of the same backend the
3D UI uses:

```text
help
device show
device connectable on|off
device model exa51|exa81
device battery <0-100>
device fw <app_version> <bootloader_version>
device tx <0-19>
trigger press|release
rfid queue <epc_hex> [rssi] [antenna]
rfid flush
rfid start
rfid stop
barcode emit <code>
disconnect
quit
```

- `rfid queue` stores EPCs and flushes them immediately while inventory
  streaming is active. A repeated queue of the same normalized EPC is
  ignored until the scanner ID buffer is cleared.
- `barcode emit` returns the code immediately if the host is waiting in
  `readBarcodeAsync()`; otherwise it is queued for the next read.
- `disconnect` drops the BLE connection without stopping the emulator.

`scanner_emu.epc.ean13_to_retail_epc()` builds an EPC your app will decode:
the retail SGTIN-96 profile with a 7-digit GS1 company prefix, partition 5,
filter 1, and an optional prefix restriction. The decoded EAN still has to
exist in your app's current dataset for the item to show up in inventory.

## Config file

`--config path/to/state.json` overrides the initial device state:

```json
{
  "model": "exa81",
  "name": "EXA81-EMU",
  "connectable": true,
  "battery_percent": 78,
  "charging": false,
  "voltage_mv": 4010,
  "current_ma": 0,
  "capacity_mah": 1100,
  "tx_level": 0,
  "connection_info": "BLE",
  "firmware": {
    "application_version": "5.0.0",
    "bootloader_version": "1.0.0"
  }
}
```

## Repository map

```text
src/scanner_emu/
├── cli.py             # scanner-emu run: REPL over the controller
├── three_d.py         # scanner-emu-3d: HTTP/SSE bridge, store session, scan selection
├── web_3d/            # Three.js first-person store UI (vendored three r160)
├── controller.py      # thread-safe backend API shared by both entrypoints
├── emulator.py        # composes BLE peripheral, NUR session, tag feed, state
├── ble_peripheral.py  # Bumble transport, advertising, GATT, connections
├── nur_session.py     # NUR frame parsing, replies, inventory/barcode events
├── store_3d.py        # catalog-backed store generation
└── epc.py             # EAN-13 to SGTIN-96 helpers
scripts/media/         # synthetic catalog, virtual controller, 3D capture
video/                 # Remotion source for the README demo and social preview
docs/                  # protocol notes, emulator internals, ADRs, wiki
```

## Checks

```bash
.venv/bin/python -m compileall src
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

CI runs the same two commands on Python 3.10 and 3.13.

## Status, support, license

Alpha, `0.x`; minor releases may still change public surfaces, and every
breaking change is called out in [`CHANGELOG.md`](./CHANGELOG.md). Hosts:
macOS validated, Linux has the same Bumble transports but is untested here,
Windows untested. The emulator runs locally, stores nothing outside the
process, and makes no network requests of its own; the only download is the
firmware step above. Security reports go through
[`SECURITY.md`](./SECURITY.md), contributions through
[`CONTRIBUTING.md`](./CONTRIBUTING.md). MIT License; third-party notices in
[`NOTICE.md`](./NOTICE.md).

Deeper reading: [`docs/nur-protocol.md`](./docs/nur-protocol.md) for the
frames, [`docs/emulator.md`](./docs/emulator.md) for internals and failure
modes, [`docs/decisions/`](./docs/decisions/README.md) for why things are
the way they are.

Nordic ID, EXA, and NUR are trademarks of their respective owners. This
project is an independent, unofficial emulator and is not affiliated with or
endorsed by Nordic ID.
