# Protocol Reference Source Summary

## Status

Synthesis from repository docs and local reference material, refreshed for
the 0.1.0 release on 2026-09-07.

## Source Order

For compatibility questions, use this order:

1. Connected-host behavior and observed real-scanner captures.
2. `docs/nur-protocol.md` and `docs/emulator.md`.
3. The upstream Nordic ID NUR SDK (`https://github.com/NordicID/nur_sdk`)
   when frame layout or semantics are unclear.
4. Upstream Bumble (`https://github.com/google/bumble`) for BLE transport
   behavior only.
5. Current implementation under `src/scanner_emu/`.

## Observation Notes

Repository docs cite an observed real-scanner handshake. No recordings are
part of this repository. When a task provides one, treat it as higher
priority than theoretical protocol completeness.

## Local Host Compatibility

Host-side compatibility facts (device-name filtering, connectable-only
advertisements, no bonding, address-based pairing memory) are recorded in
`README.md` (Host discovery notes). Keep this repo focused on the emulator
and record only the compatibility assumptions needed here.

## Protocol Notes

- BLE uses Nordic UART style service/characteristics.
- Advertising full local name must contain `EXA`.
- NUR payloads are framed binary over BLE notifications/writes.
- Large replies and unsolicited events are chunked by `att_mtu - 3`.
- The host side may log continuation chunks as invalid while still
  reassembling data correctly.
- Unsupported commands/subcommands should fail explicitly.

## Distribution Notes

- Bumble is Apache-2.0 and consumed from PyPI, not vendored.
- The Nordic ID NUR SDK carries no license and is not vendored.
