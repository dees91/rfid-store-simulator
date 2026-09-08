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

## [2026-09-08] maintenance | Screenshots and browser video playback

Accepted presentation change: the README now shows the existing synthetic
aisle screenshots before scanning and after two passes. The walkthrough
remains a normal link that opens the browser's video player on a separate page.

Uploaded the unchanged release MP4 as a GitHub attachment associated with
this repository. Verified `video/mp4` without an attachment disposition,
1920x1080 playback for 34.17 seconds, and working browser playback controls.
The release MP4 remains the downloadable copy; neither copy is tracked in Git.

Verified GitHub rendering with repository context: a video link occupying a
whole paragraph becomes an embedded player even with a custom label. Keeping
the duration outside the watch link preserves a normal link. Updated media
and release instructions to retain this behavior and use the stable attachment
URL rather than its temporary signed redirect. Screenshots fit side by side
at 1280 pixels and stack without page overflow at 390 pixels.
