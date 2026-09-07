# Wiki Index

This is the content index for the RFID Store Simulator LLM wiki. Update it whenever
wiki pages are added, removed, renamed, or materially repurposed.

## Start Here

- `README.md` - wiki rules, workflows, and safety boundaries.
- `log.md` - chronological maintenance log.
- `../context.md` - compact current project context and accepted working facts.
- `../../AGENTS.md` - mandatory agent instructions, including wiki maintenance.

## Topics

- `topics/project-snapshot.md` - current architecture, module responsibilities,
  public surfaces, and validation commands.
- `topics/protocol-compatibility.md` - BLE/NUR compatibility synthesis, known
  gaps, and observation/reference source order.
- `topics/operator-workflows.md` - CLI, 3D, physical-device USB
  dongle setup, config, RFID/barcode/trigger workflows, and operator caveats.

## Sources

- `sources/repository-docs.md` - summary of current repository documentation
  ingested during wiki bootstrap.
- `sources/protocol-references.md` - summary of real-scanner observations, NUR
  SDK, Bumble, and host compatibility references.
- `sources/original/llm-wiki.md` - local source note for the LLM Wiki pattern
  requested by the user.

## Accepted Decisions

- `../decisions/0001-llm-wiki-knowledge-layer.md` - this wiki knowledge layer
  and maintenance contract.
- `../decisions/0002-3d-rfid-store-simulator.md` - first-person 3D RFID store
  simulator architecture.
- `../decisions/0003-3d-scan-progress-visualization.md` - backend-authoritative
  3D scan progress visualization.
- `../decisions/0004-csv-product-catalog-quantities.md` - CSV product catalog
  with per-product quantities.
- `../decisions/0005-ble-host-on-physical-device.md` - USB HCI dongle path
  for a BLE host on a physical device and the Python 3.10 floor.

## Related Project Docs

- `../README.md` - stable documentation index.
- `../nur-protocol.md` - protocol details.
- `../emulator.md` - emulator behavior and known gaps.
- `../release-policy.md` - release and compatibility policy.
- `../../CHANGELOG.md` - user-facing change history.
- `../../NOTICE.md` - attribution and distribution constraints.
