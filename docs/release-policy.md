# Release And Compatibility Policy

This document defines how RFID Store Simulator is versioned, released, and kept
compatible for users.

## Versioning

Use semantic versioning:

- `MAJOR`: breaking changes to stable public contracts.
- `MINOR`: new features, compatibility improvements, or breaking changes during
  the `0.x` phase.
- `PATCH`: bug fixes, documentation updates, test fixes, and small compatible
  improvements.

During `0.x`, minor releases may include breaking changes, but every breaking
change must be called out in `CHANGELOG.md`.

## Compatibility Surface

### Stable Public Surface

- Documented CLI entrypoints and REPL commands.
- Documented `--config` JSON fields.
- `ScannerEmulatorController` as the shared programmatic backend for the CLI
  and the 3D UI.
- BLE advertising contract expected by connected hosts:
  - Nordic UART style service and characteristics;
  - full local name containing `EXA`;
  - EXA51 / EXA81 model selection.
- NUR command subset documented in `docs/nur-protocol.md`.

### Additive Or Migrated Surface

- Optional config JSON schema.
- 3D operator UI controls and bridge API.
- New controller methods for operator actions.
- New supported NUR commands when added as compatible subsets.

Prefer additive changes and tolerant config loading.

### Best-Effort Surface

- Synthetic EXA51 identity values.
- Compatibility placeholders in full setup and device capabilities payloads.
- Behavior inferred from SDK docs rather than confirmed captures.
- Host-specific EPC acceptance beyond syntactic EPC generation.

### Internal Surface

- Helper functions inside `scanner_emu.nur_session`.
- Internal scan-point ranking and budget details.
- Internal event names not documented as public API.
- Planning docs and wiki synthesis pages.

## Deprecation Policy

Before `v1.0.0`, breaking changes may happen in minor releases, but they must
be documented.

After `v1.0.0`, deprecate first, remove later, and reserve removals for major
releases unless behavior is unsafe or actively misleading.

## Release Checklist

1. Confirm the working tree is clean or intentionally staged.
2. Run `.venv/bin/python -m compileall src` and
   `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .`.
3. Run the lightweight API smoke test from `docs/context.md`.
4. Smoke-check the main CLI flow against `android-netsim` when available.
5. Smoke-check `scanner-emu-3d` and the browser smoke test when the 3D UI
   changed.
6. Check connected-host compatibility for BLE/NUR changes.
7. Review `CHANGELOG.md`.
8. Review `README.md`, `docs/usage.md`, `NOTICE.md`, license status, and
   redistribution notes.
9. Run public-safety checks for secrets, device captures, and local artifacts.
10. Tag the release (`vX.Y.Z`, annotated) and create GitHub release notes
    from the matching `CHANGELOG.md` section. Attach the sdist, the wheel,
    `SHA256SUMS.txt`, and the media assets `demo.gif` and `3d-store-demo.mp4`
    (they are not tracked in git; see `video/AGENTS.md`), then point the
    README media links at the new tag.
