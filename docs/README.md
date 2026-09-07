# RFID Store Simulator Docs

This directory collects the current state of knowledge about the EXA/NUR BLE protocol subset used by connected NUR hosts and about the local emulator implementation.

## Documents

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
- `README.md` (Host discovery notes)
