# Wiki Log

Append-only log for RFID Store Simulator wiki maintenance.

## [2026-09-07] maintenance | Initial public release

Rebuilt the knowledge layer for the 0.1.0 release: CSV product catalog with
per-product quantities, host-neutral wording, and current ADR references
across topics and sources.

## [2026-09-08] maintenance | README and operator guide

Reorganized the README around a hardware-free first run with synthetic data,
a short explanation of the scanner flow, and links to app integration setup.
Moved full USB firmware instructions, catalog and scan behavior, REPL
commands, and JSON configuration to `docs/usage.md`; moved the repository
map to `CONTRIBUTING.md`. Updated documentation routing and source links,
including ADR references. Accepted protocol and runtime behavior is unchanged.

Verified the documented venv/pip install in a clean tracked-file export on
macOS with Python 3.14.7. Compile checks, all 106 unit tests, and the API smoke
test passed. The virtual-controller demo connected, accepted shelf scans,
and stopped inventory from the browser. Reviewed rendered Markdown at 1280
and 390 pixels; changed the flow diagram to a vertical layout for readability.
