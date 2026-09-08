# Contributing

Issues and pull requests are welcome. Before opening a PR:

1. Read `AGENTS.md`; it is the working contract for humans and agents alike
   (layering rules, where BLE/NUR behavior lives, documentation upkeep).
2. Set up an environment as described in [README quick start](README.md#1-install).
3. Run the checks:

   ```bash
   .venv/bin/python -m compileall src
   PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
   ```

4. Keep changes small and focused, add or update tests for behavior changes,
   and add a `CHANGELOG.md` entry under "Unreleased" for user-facing changes.

Do not include real device captures, product catalogs, or
anything copied from external repositories. Test data must be synthetic.

By contributing you agree that your contribution is licensed under the MIT
License in `LICENSE`.

## Repository layout

```text
src/scanner_emu/
|-- cli.py             # scanner-emu run: REPL over the controller
|-- three_d.py         # scanner-emu-3d: HTTP/SSE bridge, store session, scan selection
|-- web_3d/            # Three.js first-person store UI (vendored three r160)
|-- controller.py      # thread-safe backend API shared by both entrypoints
|-- emulator.py        # composes BLE peripheral, NUR session, tag feed, state
|-- ble_peripheral.py  # Bumble transport, advertising, GATT, connections
|-- nur_session.py     # NUR frame parsing, replies, inventory/barcode events
|-- store_3d.py        # catalog-backed store generation
`-- epc.py             # EAN-13 to SGTIN-96 helpers
scripts/media/         # synthetic catalog, virtual controller, 3D capture
video/                 # Remotion source for the README demo and social preview
docs/                  # protocol notes, emulator internals, ADRs, wiki
```

CI runs the compile and unit checks above on Python 3.10 and 3.13.
