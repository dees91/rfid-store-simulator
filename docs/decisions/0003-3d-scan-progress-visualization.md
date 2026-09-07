# ADR 0003: 3D Scan Progress Visualization

## Status

Accepted on 2026-06-16.

## Context

The 3D RFID store simulator lets an operator walk between generated store
shelves, hold a scanner trigger, and feed generated EPCs through the real
BLE/NUR emulator. The current UI exposes global counts such as generated tags,
accepted scans, duplicates, rate, and scanner ID buffer size. It does not make
the spatial state obvious while walking: an operator cannot quickly see which
shelves have already been scanned, which shelves are partially complete, and
which shelves still contain tags to scan.

The user requested a strongly visible in-scene indication of where scanning has
happened and where tags remain. The feature should help the operator navigate
the store in first-person view without watching logs or global counters.

Accepted requirements:

- Visual state must be visible directly in the 3D store while walking between
  shelves.
- The marking should show both scanned areas and areas that still need
  scanning.
- Progress should be gradual, not just binary scanned/unscanned.
- Main progress should reset when scanner storage is reset, matching
  `CLEAR_ID_BUFFER` and backend restart semantics.
- Labels with exact counts should not be shown over every shelf all the time;
  they should be limited to the currently aimed or nearby shelf groups.

## Decision

Add per-store-group scan progress visualization to the 3D simulator.

The Python bridge remains the authoritative owner of scan progress. For each
generated render group, it should track:

- `group_id`
- `total_tags`
- `scanned_tags`
- `remaining_tags`
- `progress_ratio`
- a coarse visual state such as `unscanned`, `partial`, or `complete`

Progress should be derived from accepted scan results, not from browser-only
aiming state. Duplicate-ignored queue attempts must not increase scanned count.
This keeps the visualization aligned with scanner storage and Android-facing
inventory behavior.

The progress model should reset when the scanner ID buffer is cleared. The 3D
bridge already observes `id_buffer_size` transitions to reset attempted scan
candidates; the same reset boundary should reset per-group visual progress.
Trigger release does not reset progress.

The browser should use the existing grouped render model. It should update
`InstancedMesh` colors or related per-group materials rather than creating
one mesh per EPC tag. The default visual language is:

- unscanned or mostly remaining: red/dark high-contrast state;
- partially scanned: orange/yellow gradient;
- complete: green state;
- optional subtle glow or overlay to make state readable from normal aisle
  distance.

Exact numeric counts should be contextual. The scene may show a compact label
for the currently aimed group or a small number of nearby visible groups, but
it should not create permanent labels for every shelf slot. The HUD may include
an aggregate remaining/scanned summary and a compact legend, but the primary
signal must stay in the 3D scene.

## Alternatives Considered

### Global HUD Counts Only

- Pros: simple to implement and already close to existing status metrics.
- Cons: does not help an operator know where to walk or aim next.
- Rejected because the requested value is spatial awareness in the first-person
  store view.

### Browser-Local Progress Only

- Pros: easy to compute from aimed groups and local pose updates.
- Cons: can drift from backend duplicate suppression, `CLEAR_ID_BUFFER`, and
  Android-facing scan behavior.
- Rejected because progress should reflect scanner/backend truth.

### Permanent Labels Over Every Shelf Slot

- Pros: exact counts are always visible.
- Cons: about 1,500 render groups would create visual clutter and hurt
  readability/performance.
- Rejected in favor of global color state plus contextual labels.

### Binary Complete/Incomplete Marking

- Pros: simpler state model.
- Cons: does not show useful progress for high-count product groups.
- Rejected because the user explicitly accepted gradual progress.

### Minimap-First Visualization

- Pros: can summarize the whole store at once.
- Cons: less natural for first-person shelf scanning and extra UI complexity.
- Deferred. The first implementation should color shelves/product groups
  directly.

## Consequences

- The 3D bridge API will grow a progress data surface for render groups.
- The browser UI needs a stable mapping from `group_id` to rendered instance
  index.
- Status/SSE or polling updates must include enough progress information to
  update colors without exposing raw EPC lists to the browser.
- Tests should cover progress accounting, duplicate handling, reset behavior,
  no EPC leakage, and visible color changes in the browser.
- Future UI controls can tune colors, glow, label count, or legend behavior
  without changing the backend progress contract.

## Related

- `docs/decisions/0002-3d-rfid-store-simulator.md`
- `src/scanner_emu/three_d.py`
- `src/scanner_emu/store_3d.py`
- `src/scanner_emu/web_3d/app.js`
