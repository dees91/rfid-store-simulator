# ADR 0002: 3D RFID Store Simulator

## Status

Accepted on 2026-06-15.

## Context

The project (package `scanner-emu`) currently provides a Python BLE/NUR emulator, a CLI with a
scriptable tag feed, and no spatial representation. The tag feed supplies RFID
tags from a CSV product catalog, but that feed is abstract: it does not
represent a worker walking through a store, aiming a scanner at shelves,
pressing a physical trigger, or discovering tags based on position.

The requested feature is a first-person 3D store simulation that controls the
current emulator for real. The connected host must receive the same BLE
and NUR signals it expects from an EXA/NUR scanner. The 3D view is therefore
not a visual-only prototype; it is another operator surface over the existing
backend compatibility layer. The 3D UI is the operator interface; the REPL
is the headless mode.

Accepted requirements:

- The 3D simulator must drive the current BLE/RFID emulator and feed the
  connected host with RFID inventory events.
- It should run as a local web experience using Three.js, controlled by a
  Python HTTP/realtime bridge.
- A new entrypoint should start the BLE backend and serve the 3D UI, rather
  than embedding 3D inside the PySide6 desktop app.
- The worker's trigger in the 3D view represents the scanner's physical
  trigger.
- In protocol-strict mode, trigger press/release sends NUR IO trigger events;
  the connected host remains responsible for starting and stopping inventory by
  sending the inventory stream command.
- Products are loaded from the shared CSV catalog path used by the
  current tag feed.
- A generated store session should create a stable shelf layout with about
  15,000 unique EPC tags for that session.
- The product-to-tag distribution must include both products with exactly one
  tag and products with many tags. Distribution weights should be modeled in a
  way that later UI controls can edit them.
- 3D rendering should show product groups or shelf slots, not every individual
  EPC tag as a separate mesh.
- RFID discovery should use a simple but plausible scan model: a main cone,
  weaker side coverage, distance, angle, and RSSI jitter.
- The scanner's internal ID storage should be represented in the backend, not
  only in the 3D UI. It is cleared by scanner restart or `CLEAR_ID_BUFFER`.

## Decision

Add a 3D RFID store simulator as a web-based operator surface over
`ScannerEmulatorController`.

The 3D simulator will be launched through a new entrypoint, tentatively
`scanner-emu-3d`. The entrypoint will:

- start the existing emulator backend with the requested transport, model, and
  config;
- load a product catalog with the existing catalog loading path;
- generate a session-scoped store layout and unique EPC set;
- serve a Three.js first-person store UI;
- expose a local HTTP/SSE bridge between the UI and the backend.

The connected host remains the compatibility target and the source of inventory
stream state in protocol-strict mode. A 3D trigger press sends
`send_trigger(True)`, and trigger release sends `send_trigger(False)`. The 3D
simulator queues candidate RFID tags only while the trigger is held and the
backend reports `inventory_running=True`, which should happen after the host
reacts to the trigger and sends the NUR inventory stream start command.
Trigger release stops 3D candidate generation immediately, but it does not call
`stop_inventory()` in protocol-strict mode; the host should send the
stop command. A standalone development mode may exist for UI testing without a
connected host, but it must be visibly separate from strict mode.

The generated store session is owned by the Python bridge/backend layer. The UI
receives enough layout metadata to render shelves and product groups, while the
backend keeps the authoritative product, tag, EPC, and scan-selection data.
This keeps real catalog-derived data and EPC assignment out of ad hoc browser
logic and allows the backend to apply scanner semantics consistently.

The store generator will use the existing `ProductCatalog` and EPC helpers. It
will create about 15,000 EPC tags by default, assigned to fixed product groups
and shelf slots for the lifetime of the generated session. The distribution of
tags per product will be long-tailed and represented as structured settings,
with default buckets such as single-tag products, normal products, and high
quantity products. The exact defaults may be tuned during implementation, but
the configuration shape must make later UI controls straightforward.

The scanner ID buffer belongs in shared emulator state and NUR session logic.
When a tag is accepted for inventory, its normalized EPC is added to the
scanner's internal ID buffer. Repeated candidate reads of an EPC already in the
buffer are ignored until the buffer is cleared. Backend restart and
`NUR_CMD_CLEAR_ID_BUFFER` clear the buffer. This behavior applies to every
operator surface, including CLI, scripted feeds, and the new
3D simulator.

## Alternatives Considered

### Visual-only 3D prototype

- Pros: fastest to build and easy to iterate on visual design.
- Cons: would not verify BLE/NUR behavior, host integration, trigger
  semantics, or inventory event handling.
- Rejected because the requested goal is to drive the current emulator and feed
  the host with real tag events.

### Embed 3D inside the PySide6 desktop app

- Pros: one desktop process and one existing UI entrypoint.
- Cons: adds heavy 3D concerns to the Qt operator app, complicates packaging,
  and risks forking desktop behavior away from the shared backend.
- Rejected because a local web UI is a better fit for Three.js and keeps Qt
  focused on the existing operator panel.

### Let the 3D trigger directly start and stop inventory

- Pros: easier standalone behavior and fewer timing issues during demos.
- Cons: bypasses the host behavior that the emulator is meant to test.
- Rejected for protocol-strict mode. A clearly marked standalone development
  mode may call inventory controls for UI testing only.

### Keep duplicate-read handling in the 3D UI

- Pros: no NUR/backend state change required.
- Cons: duplicates would behave differently across 3D, scripted feeds, CLI,
  and manual RFID, and `CLEAR_ID_BUFFER` would not reflect scanner storage.
- Rejected because internal ID storage is scanner behavior and belongs in the
  backend.

### Render every EPC tag as its own 3D object

- Pros: simple mental mapping between data and visuals.
- Cons: about 15,000 individual objects is unnecessary visual detail and a
  likely browser performance problem.
- Rejected in favor of rendering grouped products or shelf slots while keeping
  individual EPC tags in backend data.

### Reuse the current continuous random feed unchanged

- Pros: existing feature, already integrated with `ScannerEmulatorController`.
- Cons: it emits catalog-derived tags over time without spatial location,
  trigger aiming, or fixed shelf inventory.
- Rejected because the 3D simulator needs a stable generated store and
  position-based discovery.

## Consequences

- A new public entrypoint and documentation surface will be added for the 3D
  simulator.
- The 3D simulator will likely add optional web-server/browser-asset
  packaging while keeping the core BLE emulator and desktop extra separate.
- `NurState` and `NurSession` will gain scanner ID buffer behavior, changing
  duplicate EPC handling for all operator surfaces.
- `CLEAR_ID_BUFFER` will become behaviorally meaningful instead of only
  returning success.
- Store generation and scan selection need focused tests because mistakes can
  silently change host-side inventory behavior.
- Performance must be validated with catalog-driven store sizes.
- The connected host remains the compatibility target; no host changes are
  assumed by this ADR.
- If Three.js assets are vendored for offline/local operation, `NOTICE.md` and
  release documentation must be updated accordingly.

## Related

- `docs/nur-protocol.md`
- `docs/emulator.md`
- `docs/context.md`
- `src/scanner_emu/controller.py`
- `src/scanner_emu/nur_session.py`
- `src/scanner_emu/product_catalog.py`
- `src/scanner_emu/epc.py`
