# Architecture Decision Records

This directory contains durable decisions about this repository.

Use ADRs for decisions that are expensive to reverse, such as public API shape,
dependency direction, release compatibility policy, major protocol strategy, or
documentation architecture.

## Index

- `0001-llm-wiki-knowledge-layer.md` - accepted wiki maintenance layer.
- `0002-3d-rfid-store-simulator.md` - accepted 3D RFID store simulator architecture.
- `0003-3d-scan-progress-visualization.md` - accepted 3D scan progress visualization.
- `0004-csv-product-catalog-quantities.md` - accepted CSV product catalog with per-product quantities.
- `0005-ble-host-on-physical-device.md` - accepted USB HCI dongle path for a BLE host on a physical device and the Python 3.10 floor.

## ADR Format

```markdown
# ADR 0000: Decision Title

## Status

Proposed | Accepted on YYYY-MM-DD | Superseded by ADR 0000

## Context

## Decision

## Alternatives Considered

## Consequences

## Related
```

Do not delete old ADRs. Supersede them with a newer ADR when the decision
changes.
