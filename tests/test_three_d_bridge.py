from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from scanner_emu.api import EmulatorSnapshot
from scanner_emu.product_catalog import Product, ProductCatalog
from scanner_emu.state import ScannerModel
from scanner_emu.store_3d import Store3DConfig, generate_store_session, load_store_session
from scanner_emu.three_d import (
    DEFAULT_SCAN_RATE,
    DEFAULT_SCANNER_POWER_LEVEL,
    MAX_SCANNER_POWER_LEVEL,
    MAX_TAGS_PER_POSE,
    MIN_SCANNER_POWER_LEVEL,
    Store3DBridge,
    Store3DHttpServer,
    build_parser,
    build_store_config,
    run,
)


VALID_PRODUCTS = (
    Product("4006381333931", "books", 12),
    Product("4012345358216", "kitchen", 8),
)


def valid_ean13(item_ref: int) -> str:
    body = "4012345%05d" % item_ref
    weighted = sum((3 if index % 2 else 1) * int(d) for index, d in enumerate(body))
    return body + str((10 - weighted % 10) % 10)


class ThreeDBridgeTests(unittest.TestCase):
    def test_entrypoint_help_runs_without_optional_modules(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "scanner_emu.three_d", "--help"],
            check=False,
            env={"PYTHONPATH": "src"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--catalog", result.stdout)
        self.assertNotIn("--shop-id", result.stdout)
        self.assertIn("--shelf-count", result.stdout)
        self.assertNotIn("--include-excluded-full-inventory", result.stdout)
        self.assertNotIn("SQLite", result.stdout)
        self.assertNotIn("--tag-target", result.stdout)
        self.assertNotIn("SQLite/CSV", result.stdout)
        self.assertIn("--standalone-inventory", result.stdout)

    def test_store_arguments_build_store_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            write_csv(
                catalog_path,
                "ean,category,quantity\n"
                "4006381333931,books,12\n"
                "4012345358216,kitchen,8\n",
            )
            args = build_parser().parse_args(
                [
                    "--catalog",
                    catalog_path.as_posix(),
                    "--shelf-count",
                    "8",
                    "--seed",
                    "4",
                ]
            )

            config = build_store_config(args)

        self.assertEqual(config.shelf_count, 8)
        self.assertEqual(config.seed, 4)

    def test_store_config_defaults_shelf_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            write_csv(
                catalog_path,
                "ean,category,quantity\n"
                "4006381333931,books,12\n"
                "4012345358216,kitchen,8\n",
            )
            args = build_parser().parse_args(
                ["--catalog", catalog_path.as_posix()]
            )

            config = build_store_config(args)

        self.assertEqual(config.shelf_count, 32)

    def test_store_config_rejects_non_positive_shelf_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            write_csv(
                catalog_path,
                "ean,category,quantity\n4006381333931,books,12\n",
            )
            args = build_parser().parse_args(
                ["--catalog", catalog_path.as_posix(), "--shelf-count", "0"]
            )

            with self.assertRaisesRegex(ValueError, "--shelf-count"):
                build_store_config(args)

    def test_tag_target_argument_is_removed(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(
                    [
                        "--catalog",
                        "catalog.sqlite",
                        "--tag-target",
                        "120",
                    ]
                )

    def test_status_endpoint_serves_with_fake_controller(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(controller, small_session())
        with running_server(bridge) as base_url:
            payload = get_json(base_url + "/api/status")

        self.assertTrue(payload["backend_running"])
        self.assertEqual(payload["generated_tag_count"], 20)
        self.assertEqual(payload["id_buffer_size"], 3)

    def test_scanner_power_defaults_to_medium_in_status_and_store(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())

        status = bridge.status()
        store = bridge.store_payload()

        self.assertEqual(DEFAULT_SCANNER_POWER_LEVEL, 3)
        self.assertEqual(status["scanner_power"], DEFAULT_SCANNER_POWER_LEVEL)
        self.assertEqual(store["scanner_power"], DEFAULT_SCANNER_POWER_LEVEL)
        self.assertEqual(
            status["scanner_power_effect"]["max_level"],
            MAX_SCANNER_POWER_LEVEL,
        )
        self.assertEqual(
            status["scanner_power_effect"]["min_level"],
            MIN_SCANNER_POWER_LEVEL,
        )
        self.assertEqual(status["scanner_power_effect"]["label"], "Medium")
        self.assertEqual(status["scanner_power_effect"]["effect"], "Previous max feel")
        self.assertEqual(status["scanner_power_effect"]["exposure_required"], 1)
        self.assertEqual(len(store["scanner_power_profiles"]), 5)

    def test_scanner_power_profiles_put_previous_max_at_level_three(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())

        profiles = {
            profile["level"]: profile
            for profile in bridge.store_payload()["scanner_power_profiles"]
        }

        self.assertEqual(profiles[3]["effect"], "Previous max feel")
        self.assertEqual(profiles[3]["main_cone_degrees"], 18.0)
        self.assertEqual(profiles[3]["side_cone_degrees"], 38.0)
        self.assertEqual(profiles[3]["main_range_meters"], 3.8)
        self.assertEqual(profiles[3]["side_range_meters"], 2.2)
        self.assertEqual(profiles[3]["per_pose_cap"], 25)
        self.assertEqual(profiles[5]["per_pose_cap"], 50)
        self.assertGreater(profiles[5]["main_range_meters"], profiles[3]["main_range_meters"])
        self.assertGreater(profiles[5]["side_cone_degrees"], profiles[3]["side_cone_degrees"])

    def test_scanner_power_endpoint_updates_without_inventory_side_effects(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(controller, small_session(), standalone_inventory=True)

        with running_server(bridge) as base_url:
            payload = post_json(base_url + "/api/scanner-power", {"level": 2})

        self.assertEqual(payload["status"]["scanner_power"], 2)
        self.assertEqual(payload["status"]["scanner_power_effect"]["label"], "Low")
        self.assertEqual(payload["message"], "scanner_power=2 Low")
        self.assertEqual(controller.trigger_calls, [])
        self.assertEqual(controller.start_inventory_calls, 0)
        self.assertEqual(controller.stop_inventory_calls, 0)
        self.assertEqual(controller.queue_calls, [])

    def test_scanner_power_endpoint_rejects_invalid_levels(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())
        invalid_payloads = (
            {},
            {"level": True},
            {"level": 2.0},
            {"level": float("nan")},
            {"level": "3"},
            {"level": 0},
            {"level": 6},
        )

        with running_server(bridge) as base_url:
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    request = urllib.request.Request(
                        base_url + "/api/scanner-power",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        urllib.request.urlopen(request, timeout=5)

                    self.assertEqual(raised.exception.code, 400)

    def test_progress_initializes_for_every_render_group(self) -> None:
        session = small_session()
        bridge = Store3DBridge(FakeController(), session)

        status = bridge.status()
        progress = status["group_progress"]
        aggregate = status["aggregate_progress"]

        self.assertEqual(set(progress), {group.group_id for group in session.render_groups})
        for group in session.render_groups:
            entry = progress[group.group_id]
            self.assertEqual(entry["group_id"], group.group_id)
            self.assertEqual(entry["total_tags"], group.tag_count)
            self.assertEqual(entry["scanned_tags"], 0)
            self.assertEqual(entry["remaining_tags"], group.tag_count)
            self.assertEqual(entry["progress_ratio"], 0)
            self.assertEqual(entry["visual_state"], "unscanned")
        self.assertEqual(aggregate["total_tags"], session.total_epc_count)
        self.assertEqual(aggregate["scanned_tags"], 0)
        self.assertEqual(aggregate["remaining_tags"], session.total_epc_count)
        self.assertEqual(aggregate["unscanned_group_count"], len(session.render_groups))

    def test_store_endpoint_does_not_dump_epcs(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())
        with running_server(bridge) as base_url:
            payload = get_json(base_url + "/api/store")

        rendered = json.dumps(payload)
        self.assertIn("render_groups", payload)
        self.assertIn("layout", payload)
        self.assertIn("position", payload["render_groups"][0])
        self.assertIn("group_progress", payload)
        self.assertIn("aggregate_progress", payload)
        self.assertNotIn("epc_hex", rendered)

    def test_status_progress_payload_does_not_dump_epcs(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())
        with running_server(bridge) as base_url:
            payload = get_json(base_url + "/api/status")

        rendered = json.dumps(payload)
        self.assertIn("group_progress", payload)
        self.assertIn("aggregate_progress", payload)
        self.assertNotIn("epc_hex", rendered)

    def test_vendor_three_module_is_served_from_allowlist(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())
        with running_server(bridge) as base_url:
            with urllib.request.urlopen(
                base_url + "/vendor/three.module.js",
                timeout=5,
            ) as response:
                raw = response.read(256).decode("utf-8")
                content_type = response.headers.get("Content-Type", "")

        self.assertIn("REVISION = '160'", raw)
        self.assertIn("javascript", content_type)

    def test_trigger_endpoint_calls_send_trigger(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(controller, small_session())

        with running_server(bridge) as base_url:
            press = post_json(base_url + "/api/trigger", {"pressed": True})
            release = post_json(base_url + "/api/trigger", {"pressed": False})

        self.assertEqual(controller.trigger_calls, [True, False])
        self.assertIn("trigger=pressed", press["message"])
        self.assertFalse(release["status"]["trigger_pressed"])

    def test_scan_endpoint_sends_trigger_pulse_and_latches_scan_gate(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(controller, small_session())

        with running_server(bridge) as base_url:
            start = post_json(base_url + "/api/scan", {"active": True})
            stop = post_json(base_url + "/api/scan", {"active": False})

        self.assertEqual(controller.trigger_calls, [True, False, True, False])
        self.assertTrue(start["status"]["scan_active"])
        self.assertFalse(start["status"]["trigger_pressed"])
        self.assertFalse(start["status"]["inventory_running"])
        self.assertFalse(stop["status"]["scan_active"])
        self.assertFalse(stop["status"]["trigger_pressed"])

    def test_scan_latch_queues_after_trigger_pulse_when_inventory_running(self) -> None:
        session = small_session()
        group = first_group_with_tag_count(session, minimum=2)
        tags = session.tags_for_group(group.group_id)[:2]
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=1,
            clock=StepClock(),
        )
        bridge._scan_points = [
            scan_point(tags[0].epc_hex, group.group_id),
            scan_point(tags[1].epc_hex, group.group_id),
        ]

        start = bridge.set_scan_active(True)
        bridge.update_pose(forward_pose())
        first_count = len(controller.queue_calls)
        stop = bridge.set_scan_active(False)
        bridge.update_pose(forward_pose())

        self.assertEqual(controller.trigger_calls, [True, False, True, False])
        self.assertTrue(start.status["scan_active"])
        self.assertFalse(start.status["trigger_pressed"])
        self.assertFalse(stop.status["scan_active"])
        self.assertFalse(stop.status["trigger_pressed"])
        self.assertEqual(first_count, 1)
        self.assertEqual(len(controller.queue_calls), first_count)

    def test_strict_trigger_does_not_call_inventory_controls(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(controller, small_session(), standalone_inventory=False)

        bridge.set_trigger(True)
        bridge.set_trigger(False)

        self.assertEqual(controller.start_inventory_calls, 0)
        self.assertEqual(controller.stop_inventory_calls, 0)
        self.assertEqual(bridge.status()["mode"], "strict")

    def test_standalone_trigger_calls_inventory_controls(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(controller, small_session(), standalone_inventory=True)

        bridge.set_trigger(True)
        self.assertTrue(controller.snapshot.inventory_running)
        bridge.set_trigger(False)

        self.assertEqual(controller.start_inventory_calls, 1)
        self.assertEqual(controller.stop_inventory_calls, 1)
        self.assertEqual(bridge.status()["mode"], "standalone")

    def test_standalone_scan_latch_calls_inventory_controls(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(controller, small_session(), standalone_inventory=True)

        bridge.set_scan_active(True)
        self.assertTrue(controller.snapshot.inventory_running)
        bridge.set_scan_active(False)

        self.assertEqual(controller.trigger_calls, [True, False, True, False])
        self.assertEqual(controller.start_inventory_calls, 1)
        self.assertEqual(controller.stop_inventory_calls, 1)
        self.assertFalse(bridge.status()["scan_active"])
        self.assertEqual(bridge.status()["mode"], "standalone")

    def test_pose_queues_only_while_trigger_and_inventory_running(self) -> None:
        controller = FakeController()
        bridge = Store3DBridge(
            controller,
            small_session(),
            max_scan_rate=5,
            clock=StepClock(),
        )
        pose = forward_pose()

        bridge.update_pose(pose)
        self.assertEqual(controller.queue_calls, [])

        bridge.set_trigger(True)
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge.update_pose(pose)
        first_count = len(controller.queue_calls)
        bridge.set_trigger(False)
        bridge.update_pose(pose)

        self.assertGreater(first_count, 0)
        self.assertLessEqual(first_count, 5)
        self.assertEqual(len(controller.queue_calls), first_count)

    def test_max_power_preserves_current_scan_budget_and_order(self) -> None:
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            small_session(),
            max_scan_rate=10,
            clock=FrozenClock(),
        )
        bridge._scan_points = [
            scan_point("%024X" % index, "group-%s" % index)
            for index in range(10)
        ]

        bridge.set_scanner_power(MAX_SCANNER_POWER_LEVEL)
        bridge.set_trigger(True)
        bridge.update_pose(close_pose())

        self.assertEqual(
            controller.queue_calls,
            ["%024X" % index for index in range(10)],
        )

    def test_low_power_accepts_fewer_candidates_from_same_pose_than_max(self) -> None:
        scan_points = [
            scan_point("%024X" % index, "group-%s" % index)
            for index in range(10)
        ]
        max_controller = FakeController()
        max_controller.snapshot = replace_snapshot(
            max_controller.snapshot,
            inventory_running=True,
        )
        max_bridge = Store3DBridge(
            max_controller,
            small_session(),
            max_scan_rate=10,
            clock=FrozenClock(),
        )
        max_bridge._scan_points = list(scan_points)
        low_controller = FakeController()
        low_controller.snapshot = replace_snapshot(
            low_controller.snapshot,
            inventory_running=True,
        )
        low_bridge = Store3DBridge(
            low_controller,
            small_session(),
            max_scan_rate=10,
            clock=FrozenClock(),
        )
        low_bridge._scan_points = list(scan_points)

        max_bridge.set_scanner_power(MAX_SCANNER_POWER_LEVEL)
        max_bridge.set_trigger(True)
        max_bridge.update_pose(close_pose())
        low_bridge.set_scanner_power(1)
        low_bridge.set_trigger(True)
        low_bridge.update_pose(close_pose())

        self.assertEqual(len(max_controller.queue_calls), 10)
        self.assertLess(len(low_controller.queue_calls), len(max_controller.queue_calls))
        self.assertEqual(low_controller.queue_calls, [])

    def test_low_power_misses_are_retryable_and_repeated_close_passes_complete(self) -> None:
        session = one_tag_session()
        group = session.render_groups[0]
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=10,
            clock=StepClock(),
        )
        bridge._scan_points = [scan_point(tag.epc_hex, group.group_id)]

        bridge.set_scanner_power(1)
        bridge.set_trigger(True)
        bridge.update_pose(close_pose())
        bridge.update_pose(close_pose())
        self.assertEqual(controller.queue_calls, [])

        bridge.update_pose(close_pose())
        status = bridge.status()

        self.assertEqual(controller.queue_calls, [tag.epc_hex])
        self.assertEqual(status["group_progress"][group.group_id]["scanned_tags"], 1)
        self.assertEqual(status["group_progress"][group.group_id]["visual_state"], "complete")

    def test_low_power_fractional_budget_accumulates_at_low_scan_rate(self) -> None:
        session = one_tag_session()
        group = session.render_groups[0]
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=1,
            clock=StepClock(),
        )
        bridge._scan_points = [scan_point(tag.epc_hex, group.group_id)]

        bridge.set_scanner_power(1)
        bridge.set_trigger(True)
        for _ in range(20):
            bridge.update_pose(close_pose())
            if controller.queue_calls:
                break

        self.assertEqual(controller.queue_calls, [tag.epc_hex])

    def test_low_power_accepted_tag_does_not_double_count_on_repeated_passes(self) -> None:
        session = one_tag_session()
        group = session.render_groups[0]
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController(deduplicate=True)
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=10,
            clock=StepClock(),
        )
        bridge._scan_points = [scan_point(tag.epc_hex, group.group_id)]

        bridge.set_scanner_power(1)
        bridge.set_trigger(True)
        for _ in range(6):
            bridge.update_pose(close_pose())
        status = bridge.status()

        self.assertEqual(controller.queue_calls, [tag.epc_hex])
        self.assertEqual(status["accepted_scan_count"], 1)
        self.assertEqual(status["duplicate_ignored_count"], 0)
        self.assertEqual(status["aggregate_progress"]["scanned_tags"], 1)

    def test_returning_to_max_power_restores_per_pose_budget(self) -> None:
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            small_session(),
            max_scan_rate=DEFAULT_SCAN_RATE,
            clock=FrozenClock(),
        )
        bridge._scan_points = [
            scan_point("%024X" % index, "group-%s" % index)
            for index in range(80)
        ]

        bridge.set_scanner_power(1)
        bridge.set_scanner_power(MAX_SCANNER_POWER_LEVEL)
        bridge.set_trigger(True)
        bridge.update_pose(close_pose())

        self.assertEqual(len(controller.queue_calls), MAX_TAGS_PER_POSE)

    def test_current_scan_rate_is_rolling_accepted_tags_per_second(self) -> None:
        clock = ManualClock(100.0)
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            small_session(),
            max_scan_rate=100,
            clock=clock,
        )
        bridge._scan_points = [
            scan_point("%024X" % index, "group-%s" % index)
            for index in range(120)
        ]

        bridge.set_scanner_power(MAX_SCANNER_POWER_LEVEL)
        bridge.set_trigger(True)
        bridge.update_pose(close_pose())
        clock.advance(0.5)
        status = bridge.update_pose(close_pose()).status

        self.assertEqual(len(controller.queue_calls), 100)
        self.assertEqual(status["current_scan_rate"], 100.0)

    def test_id_buffer_clear_resets_low_power_exposure_state(self) -> None:
        session = one_tag_session()
        group = session.render_groups[0]
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController()
        controller.snapshot = replace_snapshot(
            controller.snapshot,
            inventory_running=True,
            id_buffer_size=3,
        )
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=10,
            clock=StepClock(),
        )
        bridge._scan_points = [scan_point(tag.epc_hex, group.group_id)]

        bridge.set_scanner_power(1)
        bridge.set_trigger(True)
        bridge.update_pose(close_pose())
        self.assertEqual(bridge._low_power_exposures, {tag.epc_hex: 1})

        controller.snapshot = replace_snapshot(controller.snapshot, id_buffer_size=0)
        bridge.status()

        self.assertEqual(bridge._low_power_exposures, {})

    def test_accepted_scan_updates_matching_group_progress(self) -> None:
        session = small_session()
        group = first_group_with_tag_count(session, minimum=2)
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=1,
            clock=StepClock(),
        )
        bridge._scan_points = [scan_point(tag.epc_hex, group.group_id)]

        bridge.set_trigger(True)
        bridge.update_pose(forward_pose())
        status = bridge.status()
        progress = status["group_progress"][group.group_id]

        self.assertEqual(controller.queue_calls, [tag.epc_hex])
        self.assertEqual(progress["scanned_tags"], 1)
        self.assertEqual(progress["remaining_tags"], group.tag_count - 1)
        self.assertEqual(progress["visual_state"], "partial")
        self.assertEqual(status["aggregate_progress"]["scanned_tags"], 1)

    def test_duplicate_ignored_scan_does_not_update_group_progress(self) -> None:
        session = small_session()
        group = first_group_with_tag_count(session, minimum=2)
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController(deduplicate=True)
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=2,
            clock=StepClock(),
        )
        bridge._scan_points = [
            scan_point(tag.epc_hex, group.group_id),
            scan_point(tag.epc_hex, group.group_id),
        ]

        bridge.set_scanner_power(MAX_SCANNER_POWER_LEVEL)
        bridge.set_trigger(True)
        bridge.update_pose(forward_pose())
        status = bridge.status()
        progress = status["group_progress"][group.group_id]

        self.assertEqual(controller.queue_calls, [tag.epc_hex, tag.epc_hex])
        self.assertEqual(status["accepted_scan_count"], 1)
        self.assertEqual(status["duplicate_ignored_count"], 1)
        self.assertEqual(progress["scanned_tags"], 1)
        self.assertEqual(status["aggregate_progress"]["scanned_tags"], 1)

    def test_group_progress_is_clamped_to_total_tags(self) -> None:
        session = one_tag_session()
        group = session.render_groups[0]
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=2,
            clock=StepClock(),
        )
        bridge._scan_points = [
            scan_point(tag.epc_hex, group.group_id),
            scan_point(tag.epc_hex, group.group_id),
        ]

        bridge.set_scanner_power(MAX_SCANNER_POWER_LEVEL)
        bridge.set_trigger(True)
        bridge.update_pose(forward_pose())
        status = bridge.status()
        progress = status["group_progress"][group.group_id]

        self.assertEqual(status["accepted_scan_count"], 2)
        self.assertEqual(progress["total_tags"], 1)
        self.assertEqual(progress["scanned_tags"], 1)
        self.assertEqual(progress["remaining_tags"], 0)
        self.assertEqual(progress["progress_ratio"], 1)
        self.assertEqual(progress["visual_state"], "complete")

    def test_status_observes_id_buffer_clear_and_resets_progress(self) -> None:
        session = small_session()
        group = session.render_groups[0]
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=1,
            clock=StepClock(),
        )
        bridge._scan_points = [scan_point(tag.epc_hex, group.group_id)]

        bridge.set_trigger(True)
        bridge.update_pose(forward_pose())
        self.assertEqual(bridge.status()["aggregate_progress"]["scanned_tags"], 1)

        controller.snapshot = replace_snapshot(controller.snapshot, id_buffer_size=0)
        status = bridge.status()

        self.assertEqual(status["aggregate_progress"]["scanned_tags"], 0)
        self.assertEqual(status["group_progress"][group.group_id]["scanned_tags"], 0)
        self.assertEqual(status["group_progress"][group.group_id]["visual_state"], "unscanned")

    def test_trigger_release_does_not_reset_group_progress(self) -> None:
        session = small_session()
        group = session.render_groups[0]
        tag = session.tags_for_group(group.group_id)[0]
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            session,
            max_scan_rate=1,
            clock=StepClock(),
        )
        bridge._scan_points = [scan_point(tag.epc_hex, group.group_id)]

        bridge.set_trigger(True)
        bridge.update_pose(forward_pose())
        bridge.set_trigger(False)
        status = bridge.status()

        self.assertFalse(status["trigger_pressed"])
        self.assertEqual(status["group_progress"][group.group_id]["scanned_tags"], 1)

    def test_repeated_pose_updates_progress_past_duplicate_epcs(self) -> None:
        controller = FakeController(deduplicate=True)
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            small_session(),
            max_scan_rate=4,
            clock=StepClock(),
        )
        pose = forward_pose()

        bridge.set_trigger(True)
        bridge.update_pose(pose)
        first_unique = len(controller.accepted_epcs)
        bridge.update_pose(pose)
        second_unique = len(controller.accepted_epcs)

        self.assertGreater(first_unique, 0)
        self.assertGreater(second_unique, first_unique)
        self.assertEqual(len(controller.queue_calls), second_unique)

    def test_id_buffer_clear_allows_visible_candidates_to_be_attempted_again(self) -> None:
        controller = FakeController(deduplicate=True)
        controller.snapshot = replace_snapshot(
            controller.snapshot,
            inventory_running=True,
            id_buffer_size=1,
        )
        bridge = Store3DBridge(
            controller,
            small_session(),
            max_scan_rate=4,
            clock=StepClock(),
        )
        pose = forward_pose()

        bridge.set_trigger(True)
        bridge.update_pose(pose)
        first_attempts = len(controller.queue_calls)
        first_epcs = set(controller.queue_calls)
        bridge.update_pose(pose)
        second_attempts = len(controller.queue_calls)
        second_epcs = set(controller.queue_calls[first_attempts:second_attempts])

        controller.accepted_epcs.clear()
        controller.snapshot = replace_snapshot(controller.snapshot, id_buffer_size=0)
        bridge.update_pose(pose)
        retried_epcs = set(controller.queue_calls[second_attempts:])

        self.assertGreater(first_attempts, 0)
        self.assertGreater(second_attempts, first_attempts)
        self.assertFalse(first_epcs & second_epcs)
        self.assertGreater(len(controller.queue_calls), second_attempts)
        self.assertTrue(first_epcs & retried_epcs)

    def test_max_power_scan_budget_limits_initial_pose_attempts(self) -> None:
        controller = FakeController()
        controller.snapshot = replace_snapshot(controller.snapshot, inventory_running=True)
        bridge = Store3DBridge(
            controller,
            small_session(),
            clock=FrozenClock(),
        )
        bridge._scan_points = [
            {
                "epc_hex": "%024X" % index,
                "group_id": "test-%s" % index,
                "position": {"x": 0.0, "y": 0.8, "z": -1.5},
                "antenna_id": 0,
                "rssi": -42,
            }
            for index in range(140)
        ]

        bridge.set_scanner_power(MAX_SCANNER_POWER_LEVEL)
        bridge.set_trigger(True)
        for _ in range(4):
            bridge.update_pose(forward_pose())

        self.assertEqual(DEFAULT_SCAN_RATE, 120.0)
        self.assertEqual(MAX_TAGS_PER_POSE, 50)
        self.assertEqual(len(controller.queue_calls), int(DEFAULT_SCAN_RATE))

    def test_status_tolerates_missing_snapshot(self) -> None:
        controller = FakeController(snapshot=None, running=False)
        bridge = Store3DBridge(controller, small_session())

        status = bridge.status()

        self.assertFalse(status["backend_running"])
        self.assertEqual(status["peers"], [])
        self.assertFalse(status["inventory_running"])

    def test_invalid_json_returns_bad_request(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())
        with running_server(bridge) as base_url:
            request = urllib.request.Request(
                base_url + "/api/trigger",
                data=b"{bad",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=5)

        self.assertEqual(raised.exception.code, 400)

    def test_shutdown_stops_server_thread(self) -> None:
        bridge = Store3DBridge(FakeController(), small_session())
        server = Store3DHttpServer("127.0.0.1", 0, bridge)
        server.start()
        thread = server._thread

        server.stop()

        self.assertIsNotNone(thread)
        self.assertFalse(thread.is_alive())

    def test_load_store_session_uses_valid_catalog_for_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            write_csv(
                catalog_path,
                "ean,category,quantity\n"
                "4006381333931,books,12\n"
                "4012345358216,kitchen,8\n",
            )

            session = load_store_session(
                catalog_path.as_posix(),
                Store3DConfig(
                    shelf_count=2,
                    shelf_levels=1,
                    slots_per_level=3,
                    seed=4,
                ),
            )

        self.assertEqual(session.total_epc_count, 20)
        self.assertEqual(session.placed_product_count, 2)

    def test_run_stops_controller_when_http_bind_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            write_csv(
                catalog_path,
                "ean,category,quantity\n"
                "4006381333931,books,12\n"
                "4012345358216,kitchen,8\n",
            )
            occupied = Store3DHttpServer(
                "127.0.0.1",
                0,
                Store3DBridge(FakeController(), small_session()),
            )
            occupied.start()
            occupied_port = int(occupied.url.rsplit(":", 1)[1])
            created: list[FakeController] = []
            args = build_parser().parse_args(
                [
                    "--catalog",
                    catalog_path.as_posix(),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(occupied_port),
                ]
            )

            try:
                with self.assertRaises(OSError):
                    run(args, controller_factory=lambda: created_controller(created))
            finally:
                occupied.stop()

        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].is_running)

    def test_run_rejects_non_csv_catalog_before_starting_controller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.sqlite"
            write_csv(
                catalog_path,
                "ean,category,quantity\n"
                "4006381333931,books,12\n"
                "4012345358216,kitchen,8\n",
            )
            created: list[FakeController] = []
            args = build_parser().parse_args(
                ["--catalog", catalog_path.as_posix()]
            )

            with self.assertRaisesRegex(ValueError, "CSV"):
                run(args, controller_factory=lambda: created_controller(created))

        self.assertEqual(created, [])

    def test_run_rejects_too_small_shelf_count_before_starting_controller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            rows = "\n".join(
                "%s,books,1" % valid_ean13(10000 + index) for index in range(60)
            )
            write_csv(catalog_path, "ean,category,quantity\n" + rows + "\n")
            created: list[FakeController] = []
            args = build_parser().parse_args(
                [
                    "--catalog",
                    catalog_path.as_posix(),
                    "--shelf-count",
                    "1",
                ]
            )

            with self.assertRaisesRegex(ValueError, "--shelf-count"):
                run(args, controller_factory=lambda: created_controller(created))

        self.assertEqual(created, [])


class running_server:
    def __init__(self, bridge: Store3DBridge) -> None:
        self.server = Store3DHttpServer("127.0.0.1", 0, bridge)

    def __enter__(self) -> str:
        self.server.start()
        return self.server.url

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.stop()


class StepClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


class FrozenClock:
    def __call__(self) -> float:
        return 100.0


class ManualClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


_DEFAULT_SNAPSHOT = object()


class FakeController:
    def __init__(
        self,
        snapshot: EmulatorSnapshot | None | object = _DEFAULT_SNAPSHOT,
        running: bool = True,
        deduplicate: bool = False,
    ) -> None:
        self.snapshot = fake_snapshot() if snapshot is _DEFAULT_SNAPSHOT else snapshot
        self.is_running = running
        self.deduplicate = deduplicate
        self.accepted_epcs: set[str] = set()
        self.trigger_calls: list[bool] = []
        self.queue_calls: list[str] = []
        self.start_inventory_calls = 0
        self.stop_inventory_calls = 0

    def start(self, config) -> EmulatorSnapshot:
        self.is_running = True
        if self.snapshot is None:
            self.snapshot = fake_snapshot()
        return self.snapshot

    def stop(self) -> None:
        self.is_running = False

    def get_state(self) -> EmulatorSnapshot | None:
        return self.snapshot

    def send_trigger(self, pressed: bool) -> str:
        self.trigger_calls.append(pressed)
        return "trigger=%s" % ("pressed" if pressed else "released")

    def start_inventory(self) -> str:
        self.start_inventory_calls += 1
        self.snapshot = replace_snapshot(self.snapshot, inventory_running=True)
        return "inventory_running=true flushed_tags=0"

    def stop_inventory(self) -> str:
        self.stop_inventory_calls += 1
        self.snapshot = replace_snapshot(self.snapshot, inventory_running=False)
        return "inventory_running=false"

    def queue_rfid(self, epc_hex: str, rssi: int, antenna_id: int) -> str:
        self.queue_calls.append(epc_hex)
        if self.deduplicate and epc_hex in self.accepted_epcs:
            return "duplicate_ignored EPC=%s id_buffer_size=3" % epc_hex
        self.accepted_epcs.add(epc_hex)
        return "accepted EPC=%s rssi=%s antenna=%s flushed_tags=1 id_buffer_size=3" % (
            epc_hex,
            rssi,
            antenna_id,
        )


def small_session():
    return generate_store_session(
        ProductCatalog(products=list(VALID_PRODUCTS)),
        Store3DConfig(
            shelf_count=2,
            shelf_levels=1,
            slots_per_level=3,
            seed=9,
        ),
    )


def one_tag_session():
    return generate_store_session(
        ProductCatalog(products=[Product("4006381333931", "books", 1)]),
        Store3DConfig(
            shelf_count=1,
            shelf_levels=1,
            slots_per_level=1,
            seed=1,
        ),
    )


def first_group_with_tag_count(session, minimum: int):
    for group in session.render_groups:
        if group.tag_count >= minimum:
            return group
    raise AssertionError("session has no group with at least %s tags" % minimum)


def scan_point(epc_hex: str, group_id: str) -> dict[str, object]:
    return {
        "epc_hex": epc_hex,
        "group_id": group_id,
        "position": {"x": 0.0, "y": 0.8, "z": -1.5},
        "antenna_id": 0,
        "rssi": -42,
    }


def fake_snapshot(**overrides) -> EmulatorSnapshot:
    values = dict(
        name="EXA51-EMU",
        address="F0:F1:F2:51:00:01",
        model=ScannerModel.EXA51,
        connectable=True,
        battery_percent=100,
        charging=False,
        voltage_mv=4100,
        current_ma=0,
        capacity_mah=1000,
        application_version="5.0.0",
        bootloader_version="1.0.0",
        connection_info="BLE",
        tx_level=0,
        antenna_mask=0,
        inventory_running=False,
        barcode_reads_pending=False,
        imager_powered=False,
        imager_aim_on=False,
        id_buffer_size=3,
        queued_tags=0,
        queued_barcodes=0,
        connected_peers=("peer-1",),
    )
    values.update(overrides)
    return EmulatorSnapshot(**values)


def replace_snapshot(snapshot: EmulatorSnapshot | None, **overrides) -> EmulatorSnapshot:
    values = snapshot.__dict__.copy() if snapshot is not None else fake_snapshot().__dict__.copy()
    values.update(overrides)
    return EmulatorSnapshot(**values)


def forward_pose() -> dict[str, object]:
    return {
        "position": {"x": 0.0, "y": 0.8, "z": -3.4},
        "direction": {"x": 0.0, "y": 0.0, "z": 1.0},
    }


def close_pose() -> dict[str, object]:
    return {
        "position": {"x": 0.0, "y": 0.8, "z": -2.2},
        "direction": {"x": 0.0, "y": 0.0, "z": 1.0},
    }


def get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def write_csv(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def created_controller(sink: list[FakeController]) -> FakeController:
    controller = FakeController()
    sink.append(controller)
    return controller
