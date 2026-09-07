# Protocol Compatibility

## Status

Current synthesis as of 2026-09-07. Treat connected-host behavior and
real-scanner observations as higher priority than theoretical NUR
completeness.

## Accepted Compatibility Contract

- BLE transport behaves like Nordic UART Service.
- Service UUID: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`.
- RX characteristic UUID: `6e400002-b5a3-f393-e0a9-e50e24dcca9e`.
- TX characteristic UUID: `6e400003-b5a3-f393-e0a9-e50e24dcca9e`.
- Advertising includes a full local name containing `EXA`.
- Notifications are chunked by `att_mtu - 3`.
- EXA51 and EXA81 model behavior should remain supported.

## Supported Flow Scope

The known target flows are:

- scanner discovery and connect;
- scanner details;
- antenna mask and TX level setup;
- RFID inventory scans;
- barcode scans;
- trigger IO events.
- 3D generated-store scans through the same trigger and inventory event
  surfaces, with the connected host still owning inventory start/stop in
  strict mode.

## Compatibility-Sensitive Areas

- Inventory records are byte-layout sensitive. The `channel` byte before
  `antenna_id` matters for host-side EPC parsing.
- Antenna mapping replies need exact string-length and trailing NUL behavior.
- Accessory replies are consumed by host code that expects exact formats.
- `PING` behavior differs from the observed scanner according to existing
  docs; the observed reply payload is `OK`, while the emulator is currently
  more permissive.
- Not every syntactically valid EPC appears in the host's inventory view;
  the host expects retail SGTIN-96 EPC semantics (7-digit company prefix,
  partition 5, filter 1) and an EAN present in its data set.
- Scanner ID buffer behavior is shared backend/NUR state: duplicate normalized
  EPCs are suppressed until backend restart or `CLEAR_ID_BUFFER`.
- `CLEAR_ID_BUFFER` clears both the scanner ID buffer and pending unsent RFID
  records. The 3D bridge resets its attempted-candidate filter only after
  observing `id_buffer_size` transition from nonzero to zero. Simulated
  low-power misses in the 3D HUD are not host/NUR events; they remain
  retryable until an EPC is actually queued and accepted or duplicate-ignored.

## Source Priority

1. Connected-host behavior.
2. Real-scanner observations when a task provides them.
3. `docs/nur-protocol.md`.
4. `docs/emulator.md`.
5. The upstream Nordic ID NUR SDK (`https://github.com/NordicID/nur_sdk`).
6. Current implementation under `src/scanner_emu/`.

## Open Questions

- Whether `PING` should always reply with the observed `OK` payload.
- Whether EXA51 should expose different reader-info identity strings.
- Whether additional accessory subcommands appear in other host modules.
- Whether some full setup or device capability fields need stricter parity for
  programming flows.
- Whether the implemented `scanner-emu-3d` strict-mode flow has been validated
  against another host in a real device or netsim environment.
