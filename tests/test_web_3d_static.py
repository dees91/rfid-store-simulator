from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "src" / "scanner_emu" / "web_3d"


class Web3DStaticTests(unittest.TestCase):
    def test_index_loads_browser_app_as_module(self) -> None:
        html = read_asset("index.html")

        self.assertIn('type="module"', html)
        self.assertIn('src="/app.js"', html)
        self.assertIn("data-trigger-label", html)
        self.assertLess(html.index('id="store-canvas"'), html.index('class="hud"'))

    def test_app_imports_local_three_module(self) -> None:
        app = read_asset("app.js")

        self.assertIn('from "./vendor/three.module.js"', app)
        self.assertIn("new THREE.WebGLRenderer", app)
        self.assertIn("new THREE.InstancedMesh", app)
        self.assertIn("mismatch_inventory_after_release", app)
        self.assertIn("position:", app)
        self.assertIn("direction:", app)

    def test_app_updates_instance_colors_from_group_progress(self) -> None:
        app = read_asset("app.js")

        self.assertIn("groupIdToInstanceIndex", app)
        self.assertIn("instanceIndexToGroupId", app)
        self.assertIn("normalizeGroupProgress", app)
        self.assertIn("updateGroupProgress(status.group_progress)", app)
        self.assertIn("updateProgressVisuals", app)
        self.assertIn("productMesh.setColorAt(index, progressColor", app)
        self.assertIn("progress_ratio", app)

    def test_app_renders_visible_progress_overlay_mesh(self) -> None:
        app = read_asset("app.js")

        self.assertIn("progressOverlayMesh", app)
        self.assertIn("addProgressOverlays", app)
        self.assertIn("buildProgressOverlayMesh", app)
        self.assertIn("setProgressOverlayState", app)
        self.assertIn("new THREE.MeshBasicMaterial", app)
        self.assertIn("transparent: true", app)
        self.assertIn("overlayMesh.frustumCulled = false", app)
        self.assertIn("progressOverlayColors", app)
        self.assertIn("progressOverlayState", app)

    def test_contextual_progress_label_uses_single_aimed_instance(self) -> None:
        html = read_asset("index.html")
        app = read_asset("app.js")

        self.assertIn('id="progress-label"', html)
        self.assertIn("raycaster.intersectObject(appState.productMesh, false)", app)
        self.assertIn("hits[0].instanceId", app)
        self.assertIn("progressLabel.hidden = true", app)
        self.assertIn("scanned -", app)

    def test_hud_includes_progress_summary_and_legend(self) -> None:
        html = read_asset("index.html")
        css = read_asset("styles.css")

        for field in (
            "progress_scanned_tags",
            "progress_remaining_tags",
            "progress_group_summary",
            "progress_complete_groups",
        ):
            with self.subTest(field=field):
                self.assertIn(field, html)
        self.assertIn("progress-legend", html)
        self.assertIn("legend-swatch is-unscanned", html)
        self.assertIn(".legend-swatch.is-complete", css)

    def test_hud_includes_scanner_power_control(self) -> None:
        html = read_asset("index.html")
        css = read_asset("styles.css")

        self.assertIn('id="scanner-power"', html)
        self.assertIn('type="range"', html)
        self.assertIn('min="1"', html)
        self.assertIn('max="5"', html)
        self.assertIn('value="3"', html)
        self.assertIn("3 Medium", html)
        self.assertIn("Previous max feel", html)
        self.assertIn('id="scanner-power-value"', html)
        self.assertIn('id="scanner-power-effect"', html)
        self.assertIn(".power-control", css)
        self.assertIn("accent-color: var(--button)", css)

    def test_app_posts_and_renders_scanner_power_state(self) -> None:
        app = read_asset("app.js")

        self.assertIn('postJson("/api/scanner-power"', app)
        self.assertIn("setScannerPower", app)
        self.assertIn("renderScannerPower(status.scanner_power", app)
        self.assertIn("scanner_power_effect", app)
        self.assertIn("scannerPowerRequestInFlight", app)
        self.assertIn("aria-valuetext", app)

    def test_app_updates_scan_cones_from_scanner_power_effect(self) -> None:
        app = read_asset("app.js")

        self.assertIn("scanCones", app)
        self.assertIn("updateScanCones(status.scanner_power_effect)", app)
        self.assertIn("replaceConeGeometry", app)
        self.assertIn("buildConeGeometry", app)
        self.assertIn("profile.main_range_meters", app)
        self.assertIn("profile.side_cone_degrees", app)

    def test_trigger_toggle_and_safety_cleanup_events_are_bound(self) -> None:
        app = read_asset("app.js")

        self.assertIn("toggleTrigger", app)
        self.assertIn("canToggleTriggerOn", app)
        self.assertIn('postJson("/api/scan"', app)
        self.assertIn("desiredScanActive", app)
        self.assertIn("localScanActive", app)
        self.assertIn("triggerButton.disabled", app)
        self.assertIn("aria-pressed", app)
        self.assertIn("!event.repeat", app)
        self.assertNotIn("desiredTriggerPressed", app)
        self.assertNotIn("localTriggerActive", app)
        for event_name in (
            "blur",
            "visibilitychange",
            "pointerlockchange",
        ):
            with self.subTest(event_name=event_name):
                self.assertIn(event_name, app)

    def test_movement_vectors_match_three_camera_yaw(self) -> None:
        app = read_asset("app.js")

        self.assertIn("forwardVector.set(-Math.sin(controls.yaw), 0, -Math.cos(controls.yaw));", app)
        self.assertIn("rightVector.set(Math.cos(controls.yaw), 0, -Math.sin(controls.yaw));", app)

    def test_browser_assets_do_not_reference_raw_epc_fields(self) -> None:
        for name in ("index.html", "app.js", "styles.css"):
            with self.subTest(asset=name):
                self.assertNotIn("epc_hex", read_asset(name))

    def test_operator_sources_advertise_csv_catalogs(self) -> None:
        source_paths = (
            ROOT / "src" / "scanner_emu" / "three_d.py",
            ROOT / "src" / "scanner_emu" / "product_catalog.py",
        )

        for path in source_paths:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("SQLite/CSV", source)
                self.assertNotIn("SQLite / CSV", source)
                self.assertNotIn("SQLite", source)
                self.assertIn("ean,category,quantity", source)

    def test_vendored_three_assets_are_packaged(self) -> None:
        module_path = WEB_DIR / "vendor" / "three.module.js"
        license_path = WEB_DIR / "vendor" / "THREE-LICENSE.txt"
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertGreater(module_path.stat().st_size, 1_000_000)
        self.assertIn("REVISION = '160'", module_path.read_text(encoding="utf-8")[:512])
        self.assertIn("Permission is hereby granted", license_path.read_text(encoding="utf-8"))
        self.assertIn('"scanner_emu.web_3d.vendor" = ["*.js", "*.txt"]', pyproject)

    def test_notice_records_three_source_and_license(self) -> None:
        notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")

        self.assertIn("Three.js 0.160.0", notice)
        self.assertIn("MIT License", notice)
        self.assertIn("https://registry.npmjs.org/three/-/three-0.160.0.tgz", notice)
        self.assertIn(
            "sha512-DLU8lc0zNIPkM7rH5/e1Ks1Z8tWCGRq6g8mPowdDJpw1CFBJMU7UoJjC6PefXW7z//SSl0b2+GCw14LB+uDhng==",
            notice,
        )
        self.assertIn("cd1e4dbd01aee0719280a9086d75545db52b7a8f", notice)


def read_asset(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")
