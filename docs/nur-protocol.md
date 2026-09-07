# NUR Protocol

This document describes the BLE + NUR subset implemented by this emulator.

## Scope

The target is not full NUR coverage. The target is the subset needed by NUR hosts for:

- scanner discovery and connect
- scanner details
- antenna configuration
- RFID inventory
- barcode scan
- trigger events

## BLE Transport

Confirmed by observation and current host integration:

- BLE service UUID: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- RX characteristic UUID: `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
- TX characteristic UUID: `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
- RX is written by the connected host.
- TX is delivered through notifications.
- The standard CCCD is used for enabling notifications.

The transport behaves like Nordic UART Service, but the payload inside it is NUR framed binary.

Confirmed by emulator implementation:

- advertising includes `COMPLETE_LOCAL_NAME`
- device name must contain `EXA`
- notifications are chunked to `att_mtu - 3`

Operational consequence:

- large replies and unsolicited events are split across multiple BLE notifications
- host-side raw logs may show the first fragment as a valid NUR frame and the continuation fragments as `invalid`
- the host or SDK still reassembles and consumes the data correctly

## NUR Frame Format

Confirmed by implementation and accepted by the host:

Header is 6 bytes:

1. `0xA5` preamble
2. body length `u16 LE`
3. flags `u16 LE`
4. header checksum `u8`

Header checksum is:

- start from `0xFF`
- XOR the first 5 header bytes

Body differs slightly for requests vs replies.

Requests:

```text
[cmd: u8][payload...][crc16_ccitt: u16 LE]
```

Replies and unsolicited events:

```text
[cmd: u8][status: u8][payload...][crc16_ccitt: u16 LE]
```

CRC parameters:

- algorithm: CRC-16/CCITT
- init: `0xFFFF`
- polynomial: `0x1021`

Known flags:

- `0x0000`: normal request/reply
- `0x0001`: unsolicited event

Known status codes in current emulator:

- `0`: success
- `1`: invalid command
- `2`: invalid length
- `13`: not supported

## Observed Connect Handshake

Confirmed by an observed real-scanner handshake (recordings not included in this repository).

After BLE services are resolved and notifications are enabled, the connected host performs this sequence:

1. `cmd=1` `PING`
2. `cmd=9` `READER_INFO`
3. `cmd=4` `GET_MODE`
4. `cmd=34` `LOAD_SETUP` with empty payload
5. `cmd=37` `ANTENNA_EX`
6. `cmd=11` `DEV_CAPS`

After `NurApi.connect()` succeeds, the host follows with accessory queries:

1. `cmd=85 payload[0]=0x01` `GET_CONFIG`
2. `cmd=85 payload[0]=0x09` `GET_BATTERY_INFO`
3. `cmd=85 payload[0]=0x00` `GET_FWVERSION`

Depending on screen/flow, the host may call `GET_CONFIG`, `GET_BATTERY_INFO`, `GET_FWVERSION` again or immediately write setup flags.

## Supported Commands

### `cmd=1` `PING`

Observed request:

- payload length `4`
- in the observed handshake it is `00 00 00 00`

Observed real reply:

- status `0`
- payload `"OK"`

Confirmed by emulator implementation:

- request payload is not interpreted
- current emulator returns success immediately

Note:

- the current emulator implementation is more permissive than the observed scanner here
- if stricter parity is needed, real scanner behavior suggests `"OK"` is the canonical payload

### `cmd=4` `GET_MODE`

Observed reply payload:

- ASCII `"A"`

### `cmd=5` `CLEAR_ID_BUFFER`

Observed use:

- app sends it after inventory flows to clear NUR-side storage

Reply:

- success, empty payload

Confirmed by emulator implementation:

- clears the scanner ID buffer of normalized EPC values
- clears unsent queued RFID records that represent buffered inventory IDs
- does not stop inventory by itself
- allows the same EPC to be accepted again after the clear

3D bridge consequence:

- the 3D bridge keeps a local attempted-candidate set for accepted or
  duplicate queue attempts to avoid repeatedly trying the same visible tags
  before the scanner buffer changes
- simulated low-power misses are not added to the attempted-candidate set, so
  those candidates can be retried on later close/repeated passes
- when the bridge observes `id_buffer_size` transition from nonzero to zero, it
  resets that attempted-candidate set and any low-power exposure counters so
  the same shelf candidates can be attempted again after `CLEAR_ID_BUFFER`

### `cmd=9` `READER_INFO`

Observed real EXA81 reply payload structure:

1. version `u32 LE`
2. length-prefixed serial
3. length-prefixed alternate serial
4. length-prefixed reader name
5. length-prefixed FCC / IC string
6. length-prefixed hardware version
7. software major `u8`
8. software minor `u8`
9. software dev `u8`
10. number of GPIO `u8`
11. number of sensors `u8`
12. number of regions `u8`
13. antenna count `u8`
14. antenna count again `u8`

Confirmed by emulator:

- EXA81 uses values aligned with observed real-scanner values
- EXA51 uses synthetic but app-compatible values

### `cmd=11` `DEV_CAPS`

Observed real payload size:

- `128` bytes

Confirmed by emulator:

- payload layout is modeled from the current app and local SDK expectations
- antenna count is derived from the active model

This command is needed during connect and details flows.

### `cmd=34` `LOAD_SETUP`

Two currently relevant usages are confirmed.

Read all setup:

- request payload: empty
- reply payload: full module setup block

Write selected setup flags:

- request starts with `setup_flags: u32 LE`
- currently relevant flags:
  - `0x00000004` `SETUP_TXLEVEL`
  - `0x00000100` `SETUP_ANTMASK`

Observed examples:

- EXA81 range antennas: `flags=0x00000100`, value `0x03`
- TX level write: `flags=0x00000004`, value `0x00`

Confirmed by emulator:

- empty payload returns the full setup block
- selective writes currently support only `TXLEVEL` and `ANTMASK`
- unsupported flags return `status=13`

### `cmd=37` `ANTENNA_EX`

Reply payload structure confirmed by observation and emulator:

```text
[count: u8]
repeat count times:
  [antenna_id: u8]
  [name_len_with_nul: u8]
  [name bytes]
  [0x00]
```

Observed real EXA81 names:

- `CrossDipole.X`
- `CrossDipole.Y`

Current emulator names:

- EXA81: `CrossDipoleX`, `CrossDipoleY`
- EXA51:
  - `range antenna 0`
  - `range antenna 1`
  - `PROXIMITY`
  - `range antenna 3`
  - `range antenna 4`

Important detail:

- the trailing NUL byte matters
- omitting it breaks host-side antenna mapping parsing

### `cmd=57` `INVENTORY_STREAM`

Observed request forms:

- start: payload `01`
- stop: empty payload

Reply:

- success, empty payload

After start:

- the scanner emits unsolicited `cmd=130` inventory events

After stop:

- a final unsolicited `cmd=130` event is emitted with `stopped=1`

Strict 3D mode:

- browser scan input is latched separately from scanner trigger IO; each click
  or Space press sends a short trigger press/release pulse
- browser scan actions do not call inventory start/stop
- the connected host remains responsible for sending this command after it reacts
  to trigger events
- the 3D bridge queues no scan candidates unless the latched scan state is active
  and this command has put the backend into `inventory_running=True`

### `cmd=85` `ACC_EXT`

Accessory subcommands currently established:

- `0x00` `GET_FWVERSION`
- `0x01` `GET_CONFIG`
- `0x06` `READ_BARCODE_ASYNC`
- `0x09` `GET_BATTERY_INFO`
- `0x0D` `IMAGER`
- `0x10` `GET_MODEL_INFORMATION`
- `0x12` `GET_CONNECTION_INFO`

Unsupported subcommands should fail explicitly, not hang.

## Accessory Subcommands

### `ACC_EXT 0x01` `GET_CONFIG`

Observed and implemented payload layout:

1. `APP_PERM_SIG` `u32 LE`
2. config value `u32 LE`
3. accessory flags `u32 LE`
4. scanner name as fixed 32-byte, NUL-padded string
5. `u16 LE`
6. `u16 LE`
7. `u16 LE`

Confirmed constants in current implementation:

- signature: `553883655`
- EXA51 config value: `1`
- EXA81 config value: `4`

### `ACC_EXT 0x09` `GET_BATTERY_INFO`

Confirmed payload layout:

1. flags `u16 LE`
2. battery percent `u8`
3. voltage mV `u16 LE`
4. current mA `u16 LE`
5. capacity mAh `u16 LE`

Charging is represented through flags.

### `ACC_EXT 0x00` `GET_FWVERSION`

Observed real reply:

```text
1.0.0 0 Jan 18 2024;3;0
```

Current emulator reply format:

```text
<app_version> 0 Jan 01 2024;<bootloader_version>;0
```

The host parses this into:

- application version
- bootloader version

### `ACC_EXT 0x0D` `IMAGER`

Observed operations:

- `[0x0D, 0x05, 0|1]` power off/on
- `[0x0D, 0x06, 0|1]` aim off/on

Reply:

- success, empty payload

### `ACC_EXT 0x06` `READ_BARCODE_ASYNC`

Observed request:

```text
[0x06][timeout_ms: u16 LE]
```

Example observed on a real EXA scanner:

- `0x1388` = `5000 ms`

Reply:

- success, empty payload

Behavior:

- scanner arms an asynchronous barcode read
- result arrives later as unsolicited `cmd=144`

### Raw `0xFF` cancel barcode

Confirmed by emulator implementation:

- a raw byte `0xFF` outside a framed request is treated as cancel
- this clears pending barcode-read state and aim state

This behavior is inferred from SDK / host expectations rather than directly proven by current observations.

## Unsolicited Events

### `cmd=129` `NOTIFY_IO_CHANGE`

Observed payload:

```text
[source: u8][direction: u8]
```

Known trigger values:

- source `100`
- direction `1` = pressed
- direction `0` = released

Confirmed by 3D bridge behavior:

- strict mode sends these trigger events only
- standalone development mode may also start/stop inventory, but that mode is
  visibly separate and is not the host compatibility path

### `cmd=130` `NOTIFY_INVENTORY`

Observed event header:

1. `stopped: u8`
2. `rounds_done: u8`
3. `collisions: u16 LE`
4. `Q: u8`

After the header comes a sequence of tag records.

Current emulator record layout:

```text
[record_len: u8]
[rssi: s8]
[scaled_rssi: s8]
[timestamp: u16 LE]
[frequency_khz: u32 LE]
[pc: u16 LE]
[channel: u8]
[antenna_id: u8]
[epc bytes...]
```

Important detail:

- the `channel` byte must be present before `antenna_id`
- omitting it shifts the EPC and breaks host-side EPC parsing

Default EPC PC value in the emulator:

```text
0x3000 | ((epc_byte_length / 2) << 11)
```

### `cmd=144` `NOTIFY_ACCESSORY`

Observed barcode payload:

```text
[event_type: u8][utf8 barcode][0x00]
```

Known value:

- `event_type = 0x01` for barcode

The trailing NUL byte is part of the observed format.

## Inventory-Specific Notes

Confirmed by host behavior:

- not every syntactically valid EPC becomes a product in the host's
  inventory view
- the connected host expects retail SGTIN-96 EPC semantics for the RFID
  inventory flow: a 7-digit GS1 company prefix, partition 5, filter value 1
- the resulting EAN must exist in the current inventory dataset

Current working assumptions confirmed by code/tests:

- company prefix: 7 digits (the real prefix is a `company_prefix` parameter
  of `ean13_to_retail_epc()`, not part of this repository)
- partition: `PAR_5`

The helper in `scanner_emu.epc` generates host-compatible EPC values from:

- `EAN-13`
- serial

Example:

- EAN `4012345358216` (synthetic, GS1 documentation prefix)
- serial `123456789`
- EPC `3034F4E4E422FB40075BCD15`

Scanner ID buffer behavior confirmed by code/tests:

- normalized EPCs are added to the scanner ID buffer when accepted
- duplicate normalized EPCs are ignored until `CLEAR_ID_BUFFER` or backend
  restart
- disconnect cleanup does not clear the ID buffer
- `CLEAR_ID_BUFFER` clears pending unsent RFID records as well as the buffer

## Known Gaps

The following are still out of scope or only partially understood:

- full NUR command set beyond the current host flows
- tag programming flows
- single-tag operations outside inventory
- deeper meaning of all `DEV_CAPS` and full setup fields
- exact behavior of every accessory subcommand on real hardware
