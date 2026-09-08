# RFID Store Simulator Docs

Start with the [README quick start](../README.md#quick-start) to try the 3D
store without hardware. These guides cover app integration, the supported
EXA/NUR protocol subset, and emulator internals.

## Documents

- [Operator Guide](./usage.md)
  - Android emulator and physical-device setup
  - CSV catalogs, 3D controls, and scan behavior
  - REPL commands, JSON configuration, and troubleshooting links

- [Context](./context.md)
  - compact current project facts
  - accepted working decisions
  - source material and public-safety notes

- [NUR Protocol](./nur-protocol.md)
  - BLE transport
  - NUR packet framing
  - observed connect handshake
  - supported commands and events
  - inventory and barcode payload layouts

- [Emulator Notes](./emulator.md)
  - local architecture
  - runtime behavior
  - known differences vs a real scanner
  - supported scope and known gaps

- [LLM Wiki](./wiki/README.md)
  - maintained synthesis layer for future agents
  - index, log, topic pages, and source summaries
  - open questions and contradictions that should not be lost in chat history

- [Architecture Decision Records](./decisions/README.md)
  - durable accepted decisions
  - ADR naming and status rules

- [Release Policy](./release-policy.md)
  - compatibility surfaces
  - release checklist
  - deprecation policy

## Confidence Levels

The docs intentionally distinguish between:

- confirmed by observation:
  observed on a real EXA scanner (recordings not included here)
- confirmed by implementation:
  present in `src/scanner_emu`
- inferred:
  strong working assumption from observation + SDK + host behavior, but not yet fully verified against more devices

## Main References

- observed real-scanner captures, when a task provides them
- Nordic ID NUR SDK: `https://github.com/NordicID/nur_sdk`
- Bumble: `https://github.com/google/bumble`
- `src/scanner_emu/`
- [Host discovery notes](./usage.md#host-discovery-notes)
