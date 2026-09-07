# Contributing

Issues and pull requests are welcome. Before opening a PR:

1. Read `AGENTS.md`; it is the working contract for humans and agents alike
   (layering rules, where BLE/NUR behavior lives, documentation upkeep).
2. Set up an environment as described in `README.md` "Install".
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
