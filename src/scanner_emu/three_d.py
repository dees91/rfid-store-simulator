from __future__ import annotations

import argparse
import json
import logging
import math
import mimetypes
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Callable, Optional
from urllib.parse import urlsplit

from .api import EmulatorSnapshot
from .config import build_config, load_config
from .controller import ScannerEmulatorController
from .product_catalog import load_catalog
from .store_3d import (
    Store3DConfig,
    StoreRenderGroup,
    StoreSession,
    load_store_session,
    minimum_shelf_count,
)

LOGGER = logging.getLogger("scanner_emu.3d")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_SCAN_RATE = 120.0
MAX_JSON_BYTES = 16384
STATIC_PACKAGE = "scanner_emu.web_3d"
STATIC_VENDOR_PACKAGE = "scanner_emu.web_3d.vendor"
STATIC_FILES = {
    "index.html": (STATIC_PACKAGE, "index.html"),
    "app.js": (STATIC_PACKAGE, "app.js"),
    "styles.css": (STATIC_PACKAGE, "styles.css"),
    "vendor/three.module.js": (STATIC_VENDOR_PACKAGE, "three.module.js"),
    "vendor/THREE-LICENSE.txt": (STATIC_VENDOR_PACKAGE, "THREE-LICENSE.txt"),
}
LAYOUT = {
    "shelf_spacing": 2.6,
    "level_height": 0.42,
    "slot_spacing": 0.42,
    "aisle_spacing": 3.2,
    "shelf_depth": 0.55,
    "slot_width": 0.34,
    "slot_height": 0.28,
    "floor_y": 0.0,
}
MAIN_CONE_DEGREES = 18.0
SIDE_CONE_DEGREES = 38.0
MAIN_RANGE_METERS = 3.8
SIDE_RANGE_METERS = 2.2
MAX_TAGS_PER_POSE = 50
SCAN_RATE_WINDOW_SECONDS = 1.0
MIN_SCANNER_POWER_LEVEL = 1
MAX_SCANNER_POWER_LEVEL = 5
DEFAULT_SCANNER_POWER_LEVEL = 3


@dataclass(frozen=True)
class ScannerPowerProfile:
    level: int
    label: str
    effect: str
    main_cone_degrees: float
    side_cone_degrees: float
    main_range_meters: float
    side_range_meters: float
    budget_multiplier: float
    exposure_required: int


SCANNER_POWER_PROFILES = {
    1: ScannerPowerProfile(
        level=1,
        label="Minimum",
        effect="Close repeated passes",
        main_cone_degrees=7.0,
        side_cone_degrees=12.0,
        main_range_meters=0.95,
        side_range_meters=0.45,
        budget_multiplier=0.15,
        exposure_required=3,
    ),
    2: ScannerPowerProfile(
        level=2,
        label="Low",
        effect="Close focused sweeps",
        main_cone_degrees=11.0,
        side_cone_degrees=22.0,
        main_range_meters=1.8,
        side_range_meters=1.0,
        budget_multiplier=0.3,
        exposure_required=2,
    ),
    3: ScannerPowerProfile(
        level=3,
        label="Medium",
        effect="Previous max feel",
        main_cone_degrees=MAIN_CONE_DEGREES,
        side_cone_degrees=SIDE_CONE_DEGREES,
        main_range_meters=MAIN_RANGE_METERS,
        side_range_meters=SIDE_RANGE_METERS,
        budget_multiplier=0.5,
        exposure_required=1,
    ),
    4: ScannerPowerProfile(
        level=4,
        label="High",
        effect="Wide fast sweeps",
        main_cone_degrees=21.0,
        side_cone_degrees=44.0,
        main_range_meters=4.35,
        side_range_meters=2.7,
        budget_multiplier=0.75,
        exposure_required=1,
    ),
    5: ScannerPowerProfile(
        level=5,
        label="Max",
        effect="Maximum throughput",
        main_cone_degrees=25.0,
        side_cone_degrees=52.0,
        main_range_meters=5.2,
        side_range_meters=3.25,
        budget_multiplier=1.0,
        exposure_required=1,
    ),
}


@dataclass(frozen=True)
class BridgeAction:
    message: str
    status: dict[str, object]


class Store3DBridge:
    def __init__(
        self,
        controller,
        session: StoreSession,
        *,
        standalone_inventory: bool = False,
        max_scan_rate: float = DEFAULT_SCAN_RATE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.controller = controller
        self.session = session
        self.standalone_inventory = standalone_inventory
        self.max_scan_rate = max(0.0, float(max_scan_rate))
        self._clock = clock
        self._lock = threading.RLock()
        self._trigger_pressed = False
        self._scan_active = False
        self._latest_pose: Optional[dict[str, object]] = None
        self._accepted_scan_count = 0
        self._duplicate_ignored_count = 0
        self._current_scan_rate = 0.0
        self._scan_rate_samples: deque[tuple[float, int]] = deque()
        self._last_action = ""
        self._scan_tokens = self.max_scan_rate
        self._last_refill = self._clock()
        self._scanner_power_level = DEFAULT_SCANNER_POWER_LEVEL
        self._low_power_exposures: dict[str, int] = {}
        self._scan_points = _build_scan_points(session)
        self._attempted_epcs: set[str] = set()
        self._last_id_buffer_size = 0
        self._group_totals = {
            group.group_id: max(0, int(group.tag_count))
            for group in self.session.render_groups
        }
        self._group_scanned = {group_id: 0 for group_id in self._group_totals}
        self._epc_group_ids = {
            tag.epc_hex: group_id
            for group_id, tags in self.session.scan_groups
            for tag in tags
        }
        self._progress_version = 0

    def status(self) -> dict[str, object]:
        with self._lock:
            snapshot = self.controller.get_state()
            if snapshot is not None:
                self._observe_id_buffer_size(snapshot.id_buffer_size)
            return {
                "backend_running": bool(getattr(self.controller, "is_running", False)),
                "ble_running": bool(getattr(self.controller, "is_running", False)),
                "peers": list(snapshot.connected_peers) if snapshot else [],
                "trigger_pressed": self._trigger_pressed,
                "scan_active": self._scan_gate_active(),
                "inventory_running": bool(snapshot.inventory_running) if snapshot else False,
                "generated_tag_count": self.session.total_epc_count,
                "accepted_scan_count": self._accepted_scan_count,
                "duplicate_ignored_count": self._duplicate_ignored_count,
                "current_scan_rate": self._scan_rate_per_second(),
                "id_buffer_size": snapshot.id_buffer_size if snapshot else 0,
                "queued_tags": snapshot.queued_tags if snapshot else 0,
                "mode": "standalone" if self.standalone_inventory else "strict",
                "store_seed": self.session.seed,
                "scanner_power": self._scanner_power_level,
                "scanner_power_effect": _scanner_power_payload(
                    self._scanner_power_profile()
                ),
                "last_action": self._last_action,
                "progress_version": self._progress_version,
                "aggregate_progress": self._aggregate_progress_payload(),
                "group_progress": self._group_progress_payload(),
                "mismatch_inventory_after_release": bool(
                    snapshot and snapshot.inventory_running and not self._scan_gate_active()
                ),
            }

    def store_payload(self) -> dict[str, object]:
        with self._lock:
            return {
                "summary": self.session.summary(),
                "layout": dict(LAYOUT),
                "scan_model": {
                    "main_cone_degrees": MAIN_CONE_DEGREES,
                    "side_cone_degrees": SIDE_CONE_DEGREES,
                    "main_range_meters": MAIN_RANGE_METERS,
                    "side_range_meters": SIDE_RANGE_METERS,
                },
                "scanner_power": self._scanner_power_level,
                "scanner_power_effect": _scanner_power_payload(
                    self._scanner_power_profile()
                ),
                "scanner_power_profiles": [
                    _scanner_power_payload(SCANNER_POWER_PROFILES[level])
                    for level in sorted(SCANNER_POWER_PROFILES)
                ],
                "render_groups": [
                    {
                        **group.summary(),
                        "position": _group_position(group),
                        "dimensions": _group_dimensions(group),
                    }
                    for group in self.session.render_groups
                ],
                "progress_version": self._progress_version,
                "aggregate_progress": self._aggregate_progress_payload(),
                "group_progress": self._group_progress_payload(),
            }

    def set_trigger(self, pressed: bool) -> BridgeAction:
        with self._lock:
            self._trigger_pressed = bool(pressed)
            messages = [self.controller.send_trigger(bool(pressed))]
            if self.standalone_inventory:
                if pressed:
                    messages.append(self.controller.start_inventory())
                else:
                    messages.append(self.controller.stop_inventory())
            self._last_action = "; ".join(messages)
            LOGGER.info(
                "3D trigger=%s mode=%s",
                "pressed" if pressed else "released",
                "standalone" if self.standalone_inventory else "strict",
            )
            return BridgeAction(self._last_action, self.status())

    def set_scan_active(self, active: bool) -> BridgeAction:
        with self._lock:
            self._scan_active = bool(active)
            messages = [
                self.controller.send_trigger(True),
                self.controller.send_trigger(False),
            ]
            self._trigger_pressed = False
            if self.standalone_inventory:
                if active:
                    messages.append(self.controller.start_inventory())
                else:
                    messages.append(self.controller.stop_inventory())
            self._last_action = "scan=%s; %s" % (
                "active" if active else "stopped",
                "; ".join(messages),
            )
            LOGGER.info(
                "3D scan=%s trigger=pulse mode=%s",
                "active" if active else "stopped",
                "standalone" if self.standalone_inventory else "strict",
            )
            return BridgeAction(self._last_action, self.status())

    def set_scanner_power(self, level: int) -> BridgeAction:
        with self._lock:
            profile = SCANNER_POWER_PROFILES[level]
            previous = self._scanner_power_level
            self._scanner_power_level = level
            if level < previous:
                self._scan_tokens = min(self._scan_tokens, self._scan_token_capacity(profile))
            elif level > previous:
                self._scan_tokens = self._scan_token_capacity(profile)
            self._last_action = "scanner_power=%s %s" % (level, profile.label)
            if previous != level:
                LOGGER.info(
                    "3D scanner power level=%s label=%s effect=%s",
                    level,
                    profile.label,
                    profile.effect,
                )
            return BridgeAction(self._last_action, self.status())

    def update_pose(self, payload: dict[str, object]) -> BridgeAction:
        pose = _parse_pose(payload)
        with self._lock:
            self._latest_pose = pose
            queued = 0
            accepted = 0
            duplicates = 0
            snapshot = self.controller.get_state()
            scan_id_buffer_size = snapshot.id_buffer_size if snapshot is not None else 0
            self._observe_id_buffer_size(
                scan_id_buffer_size
            )
            can_scan = bool(
                self._scan_gate_active()
                and snapshot is not None
                and snapshot.inventory_running
            )
            if can_scan:
                profile = self._scanner_power_profile()
                budget = self._consume_scan_budget(profile)
                ranked_points = [
                    point
                    for point in _rank_scan_points(self._scan_points, pose, profile)
                    if point["epc_hex"] not in self._attempted_epcs
                ]
                for point in ranked_points[:budget]:
                    epc_hex = str(point["epc_hex"])
                    if not self._candidate_ready_for_power(epc_hex, profile):
                        continue
                    self._attempted_epcs.add(epc_hex)
                    result = self.controller.queue_rfid(
                        epc_hex,
                        int(point["rssi"]),
                        int(point["antenna_id"]),
                    )
                    queued += 1
                    if result.startswith("accepted "):
                        accepted += 1
                        self._record_accepted_epc(epc_hex)
                    elif result.startswith("duplicate_ignored "):
                        duplicates += 1
                self._accepted_scan_count += accepted
                self._duplicate_ignored_count += duplicates
                if accepted:
                    self._record_scan_rate_sample(accepted)
                self._current_scan_rate = self._scan_rate_per_second()
                updated_snapshot = self.controller.get_state()
                scan_id_buffer_size = (
                    updated_snapshot.id_buffer_size
                    if updated_snapshot is not None
                    else scan_id_buffer_size
                )
                self._observe_id_buffer_size(
                    scan_id_buffer_size
                )
            else:
                self._current_scan_rate = self._scan_rate_per_second()
            self._last_action = (
                "pose_updated queued=%s accepted=%s duplicates=%s"
                % (queued, accepted, duplicates)
            )
            if queued or accepted or duplicates:
                LOGGER.info(
                    "3D scan candidates=%s queued=%s accepted=%s duplicates=%s "
                    "id_buffer_size=%s scan_rate=%s",
                    len(ranked_points) if can_scan else 0,
                    queued,
                    accepted,
                    duplicates,
                    scan_id_buffer_size,
                    self._current_scan_rate,
                )
            return BridgeAction(self._last_action, self.status())

    def _scan_gate_active(self) -> bool:
        return bool(self._scan_active or self._trigger_pressed)

    def _record_scan_rate_sample(self, accepted: int) -> None:
        self._scan_rate_samples.append((self._clock(), int(accepted)))
        self._prune_scan_rate_samples()

    def _scan_rate_per_second(self) -> float:
        self._prune_scan_rate_samples()
        if not self._scan_rate_samples:
            return 0.0
        accepted = sum(count for _, count in self._scan_rate_samples)
        return round(float(accepted) / SCAN_RATE_WINDOW_SECONDS, 1)

    def _prune_scan_rate_samples(self) -> None:
        cutoff = self._clock() - SCAN_RATE_WINDOW_SECONDS
        while self._scan_rate_samples and self._scan_rate_samples[0][0] < cutoff:
            self._scan_rate_samples.popleft()

    def _scanner_power_profile(self) -> ScannerPowerProfile:
        return SCANNER_POWER_PROFILES[self._scanner_power_level]

    def _effective_scan_rate(self, profile: ScannerPowerProfile) -> float:
        return self.max_scan_rate * profile.budget_multiplier

    def _scan_token_capacity(self, profile: ScannerPowerProfile) -> float:
        if self.max_scan_rate <= 0:
            return 0.0
        return max(1.0, self._effective_scan_rate(profile))

    def _consume_scan_budget(self, profile: ScannerPowerProfile) -> int:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._last_refill = now
        effective_rate = self._effective_scan_rate(profile)
        self._scan_tokens = min(
            self._scan_token_capacity(profile),
            self._scan_tokens + elapsed * effective_rate,
        )
        max_tags_per_pose = max(1, int(MAX_TAGS_PER_POSE * profile.budget_multiplier))
        budget = int(min(self._scan_tokens, max_tags_per_pose))
        self._scan_tokens -= budget
        return max(0, budget)

    def _candidate_ready_for_power(
        self, epc_hex: str, profile: ScannerPowerProfile
    ) -> bool:
        if profile.exposure_required <= 1:
            return True
        exposures = self._low_power_exposures.get(epc_hex, 0) + 1
        self._low_power_exposures[epc_hex] = exposures
        return exposures >= profile.exposure_required

    def _observe_id_buffer_size(self, size: int) -> None:
        size = max(0, int(size))
        if self._last_id_buffer_size > 0 and size == 0:
            attempted = len(self._attempted_epcs)
            exposures = len(self._low_power_exposures)
            scanned = sum(self._group_scanned.values())
            if attempted or exposures or scanned:
                LOGGER.info(
                    "3D reset scan progress after scanner ID buffer clear: "
                    "attempted=%s low_power_exposures=%s scanned=%s",
                    attempted,
                    exposures,
                    scanned,
                )
            self._attempted_epcs.clear()
            self._low_power_exposures.clear()
            self._reset_group_progress()
        self._last_id_buffer_size = size

    def _record_accepted_epc(self, epc_hex: str) -> None:
        group_id = self._epc_group_ids.get(epc_hex)
        if group_id is None:
            return
        total = self._group_totals.get(group_id, 0)
        scanned = self._group_scanned.get(group_id, 0)
        if scanned >= total:
            return
        self._group_scanned[group_id] = scanned + 1
        self._progress_version += 1

    def _reset_group_progress(self) -> None:
        if not any(self._group_scanned.values()):
            return
        for group_id in self._group_scanned:
            self._group_scanned[group_id] = 0
        self._progress_version += 1

    def _group_progress_payload(self) -> dict[str, dict[str, object]]:
        return {
            group_id: self._progress_entry(group_id)
            for group_id in self._group_totals
        }

    def _aggregate_progress_payload(self) -> dict[str, object]:
        scanned_tags = sum(self._group_scanned.values())
        complete_groups = 0
        partial_groups = 0
        unscanned_groups = 0
        for group_id in self._group_totals:
            state = self._progress_entry(group_id)["visual_state"]
            if state == "complete":
                complete_groups += 1
            elif state == "partial":
                partial_groups += 1
            else:
                unscanned_groups += 1
        total_tags = self.session.total_epc_count
        return {
            "total_tags": total_tags,
            "scanned_tags": scanned_tags,
            "remaining_tags": max(0, total_tags - scanned_tags),
            "complete_group_count": complete_groups,
            "partial_group_count": partial_groups,
            "unscanned_group_count": unscanned_groups,
            "total_group_count": len(self._group_totals),
        }

    def _progress_entry(self, group_id: str) -> dict[str, object]:
        total = self._group_totals.get(group_id, 0)
        scanned = min(total, self._group_scanned.get(group_id, 0))
        remaining = max(0, total - scanned)
        ratio = float(scanned) / float(total) if total else 0.0
        if total and scanned >= total:
            visual_state = "complete"
        elif scanned > 0:
            visual_state = "partial"
        else:
            visual_state = "unscanned"
        return {
            "group_id": group_id,
            "total_tags": total,
            "scanned_tags": scanned,
            "remaining_tags": remaining,
            "progress_ratio": round(ratio, 4),
            "visual_state": visual_state,
        }


class Store3DServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Store3DHttpServer:
    def __init__(self, host: str, port: int, bridge: Store3DBridge) -> None:
        self.host = host
        self.port = int(port)
        self.bridge = bridge
        self._shutdown_event = threading.Event()
        self._server: Optional[Store3DServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        if self._server is None:
            return "http://%s:%s" % (self.host, self.port)
        host, port = self._server.server_address[:2]
        return "http://%s:%s" % (host, port)

    def start(self) -> None:
        handler = self._make_handler()
        self._server = Store3DServer((self.host, self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="scanner-emu-3d-http",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._shutdown_event.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._server = None
        self._thread = None

    def _make_handler(self):
        bridge = self.bridge
        shutdown_event = self._shutdown_event
        bind_host = self.host

        class Handler(BaseHTTPRequestHandler):
            server_version = "scanner-emu-3d/0.1"

            def do_OPTIONS(self) -> None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_common_headers()
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self) -> None:
                path = urlsplit(self.path).path
                if path in ("/", "/index.html"):
                    self._send_static("index.html")
                    return
                if path in (
                    "/app.js",
                    "/styles.css",
                    "/vendor/three.module.js",
                    "/vendor/THREE-LICENSE.txt",
                ):
                    self._send_static(path.lstrip("/"))
                    return
                if path == "/api/status":
                    self._send_json(bridge.status())
                    return
                if path == "/api/store":
                    self._send_json(bridge.store_payload())
                    return
                if path == "/api/events":
                    self._send_events()
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "not found")

            def do_POST(self) -> None:
                try:
                    payload = self._read_json()
                    if self.path == "/api/trigger":
                        pressed = payload.get("pressed")
                        if not isinstance(pressed, bool):
                            self._send_error(HTTPStatus.BAD_REQUEST, "pressed must be boolean")
                            return
                        action = bridge.set_trigger(pressed)
                        self._send_json({"message": action.message, "status": action.status})
                        return
                    if self.path == "/api/scan":
                        active = payload.get("active")
                        if not isinstance(active, bool):
                            self._send_error(HTTPStatus.BAD_REQUEST, "active must be boolean")
                            return
                        action = bridge.set_scan_active(active)
                        self._send_json({"message": action.message, "status": action.status})
                        return
                    if self.path == "/api/scanner-power":
                        level = _parse_scanner_power_level(payload)
                        action = bridge.set_scanner_power(level)
                        self._send_json({"message": action.message, "status": action.status})
                        return
                    if self.path == "/api/pose":
                        action = bridge.update_pose(payload)
                        self._send_json({"message": action.message, "status": action.status})
                        return
                    self._send_error(HTTPStatus.NOT_FOUND, "not found")
                except ValueError as error:
                    self._send_error(HTTPStatus.BAD_REQUEST, str(error))

            def _read_json(self) -> dict[str, object]:
                content_type = self.headers.get("Content-Type", "")
                if "application/json" not in content_type:
                    raise ValueError("Content-Type must be application/json")
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_JSON_BYTES:
                    raise ValueError("JSON body too large")
                raw = self.rfile.read(length)
                try:
                    loaded = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError as error:
                    raise ValueError("Invalid JSON") from error
                if not isinstance(loaded, dict):
                    raise ValueError("JSON body must be an object")
                return loaded

            def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
                raw = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self._send_common_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _send_events(self) -> None:
                self.send_response(HTTPStatus.OK)
                self._send_common_headers()
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                while not shutdown_event.is_set():
                    try:
                        raw = "data: %s\n\n" % json.dumps(bridge.status(), sort_keys=True)
                        self.wfile.write(raw.encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    time.sleep(0.25)

            def _send_static(self, name: str) -> None:
                if name not in STATIC_FILES:
                    self._send_error(HTTPStatus.NOT_FOUND, "not found")
                    return
                package, resource_name = STATIC_FILES[name]
                try:
                    raw = resources.read_binary(package, resource_name)
                except (FileNotFoundError, ModuleNotFoundError):
                    self._send_error(HTTPStatus.NOT_FOUND, "not found")
                    return
                content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self._send_common_headers()
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    return

            def _send_error(self, status: int, message: str) -> None:
                self._send_json({"error": message}, status)

            def _send_common_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", _cors_origin(bind_host))
                self.send_header("X-Content-Type-Options", "nosniff")

            def log_message(self, fmt: str, *args) -> None:
                LOGGER.debug("HTTP %s", fmt % args)

        return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RFID Store Simulator: 3D store UI over the scanner emulator")
    parser.add_argument("--transport", default="android-netsim", help="Bumble transport spec")
    parser.add_argument("--model", choices=["exa51", "exa81"], default=None)
    parser.add_argument(
        "--catalog",
        required=True,
        help="Path to CSV product catalog with ean,category,quantity columns",
    )
    parser.add_argument("--config", default=None, help="Optional JSON config file")
    parser.add_argument("--host", default=DEFAULT_HOST, help="HTTP bind host")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="HTTP bind port")
    parser.add_argument("--seed", default=None, type=int, help="Store generation seed")
    parser.add_argument(
        "--shelf-count",
        default=None,
        type=int,
        help=(
            "Number of generated shelf fixtures; when omitted, the larger of "
            "32 and the minimum that fits the catalog quantities is used; "
            "lower values increase visual density for the same generated "
            "tag count"
        ),
    )
    parser.add_argument(
        "--scan-rate",
        default=DEFAULT_SCAN_RATE,
        type=float,
        help="Maximum scan candidates per second",
    )
    parser.add_argument(
        "--standalone-inventory",
        action="store_true",
        help="Development mode: browser scan toggle also starts/stops inventory",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Python log level",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        parser.exit(
            1,
            "scanner-emu-3d requires Python 3.10+ because bumble from PyPI "
            "requires it.\n",
        )

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        parser.exit(1, "error: %s\n" % error)


def run(
    args: argparse.Namespace,
    *,
    controller_factory: Callable[[], ScannerEmulatorController] = ScannerEmulatorController,
) -> int:
    config = build_config(
        transport_spec=args.transport,
        raw_config=load_config(args.config),
        model=args.model,
        log_level=args.log_level,
    )
    store_config = build_store_config(args)
    session = load_store_session(args.catalog, store_config)
    controller = controller_factory()
    server = None
    try:
        controller.start(config)
        bridge = Store3DBridge(
            controller,
            session,
            standalone_inventory=args.standalone_inventory,
            max_scan_rate=args.scan_rate,
        )
        server = Store3DHttpServer(args.host, args.port, bridge)
        server.start()
        print("scanner-emu-3d running at %s" % server.url, flush=True)
        while True:
            time.sleep(3600)
    finally:
        if server is not None:
            server.stop()
        if getattr(controller, "is_running", False):
            controller.stop()
    return 0


def build_store_config(args: argparse.Namespace) -> Store3DConfig:
    if args.shelf_count is not None and args.shelf_count < 1:
        raise ValueError("--shelf-count must be positive")
    defaults = Store3DConfig()
    catalog = load_catalog(args.catalog)
    minimum = minimum_shelf_count(
        catalog,
        defaults.shelf_levels,
        defaults.slots_per_level,
        defaults.distribution,
    )
    if args.shelf_count is None:
        shelf_count = max(32, minimum)
    elif args.shelf_count < minimum:
        raise ValueError(
            "--shelf-count %s is too small for this catalog; "
            "pass --shelf-count %s or higher" % (args.shelf_count, minimum)
        )
    else:
        shelf_count = args.shelf_count
    return Store3DConfig(shelf_count=shelf_count, seed=args.seed)


def _parse_scanner_power_level(payload: dict[str, object]) -> int:
    if "level" not in payload:
        raise ValueError("level is required")
    level = payload["level"]
    if type(level) is not int:
        raise ValueError("level must be an integer from 1 to 5")
    if level not in SCANNER_POWER_PROFILES:
        raise ValueError("level must be between 1 and 5")
    return level


def _scanner_power_payload(profile: ScannerPowerProfile) -> dict[str, object]:
    return {
        "level": profile.level,
        "min_level": MIN_SCANNER_POWER_LEVEL,
        "max_level": MAX_SCANNER_POWER_LEVEL,
        "label": profile.label,
        "effect": profile.effect,
        "main_cone_degrees": profile.main_cone_degrees,
        "side_cone_degrees": profile.side_cone_degrees,
        "main_range_meters": profile.main_range_meters,
        "side_range_meters": profile.side_range_meters,
        "budget_multiplier": profile.budget_multiplier,
        "per_pose_cap": max(1, int(MAX_TAGS_PER_POSE * profile.budget_multiplier)),
        "exposure_required": profile.exposure_required,
    }


def _parse_pose(payload: dict[str, object]) -> dict[str, object]:
    position = payload.get("position")
    direction = payload.get("direction")
    if not isinstance(position, dict) or not isinstance(direction, dict):
        raise ValueError("pose must include position and direction objects")
    parsed_position = {
        "x": _float_field(position, "x"),
        "y": _float_field(position, "y"),
        "z": _float_field(position, "z"),
    }
    parsed_direction = _normalize_vector(
        {
            "x": _float_field(direction, "x"),
            "y": _float_field(direction, "y"),
            "z": _float_field(direction, "z"),
        }
    )
    return {"position": parsed_position, "direction": parsed_direction}


def _float_field(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError("%s must be numeric" % key)
    return float(value)


def _normalize_vector(vector: dict[str, float]) -> dict[str, float]:
    length = math.sqrt(
        vector["x"] * vector["x"]
        + vector["y"] * vector["y"]
        + vector["z"] * vector["z"]
    )
    if length <= 0:
        raise ValueError("direction vector must not be zero")
    return {key: value / length for key, value in vector.items()}


def _build_scan_points(session: StoreSession) -> list[dict[str, object]]:
    points = []
    for group in session.render_groups:
        position = _group_position(group)
        for tag in session.tags_for_group(group.group_id):
            points.append(
                {
                    "epc_hex": tag.epc_hex,
                    "group_id": group.group_id,
                    "position": position,
                    "antenna_id": group.shelf_index % 2,
                    "rssi": -42 - min(30, group.level_index * 3 + group.slot_index % 5),
                }
            )
    return points


def _rank_scan_points(
    points: list[dict[str, object]],
    pose: dict[str, object],
    profile: ScannerPowerProfile,
):
    position = pose["position"]
    direction = pose["direction"]
    ranked = []
    for point in points:
        target = point["position"]
        vector = {
            "x": target["x"] - position["x"],
            "y": target["y"] - position["y"],
            "z": target["z"] - position["z"],
        }
        distance = math.sqrt(vector["x"] ** 2 + vector["y"] ** 2 + vector["z"] ** 2)
        if distance <= 0:
            distance = 0.001
        unit = {key: value / distance for key, value in vector.items()}
        dot = max(-1.0, min(1.0, sum(unit[key] * direction[key] for key in unit)))
        angle = math.degrees(math.acos(dot))
        if angle <= profile.main_cone_degrees and distance <= profile.main_range_meters:
            ranked.append((angle + distance, point))
        elif angle <= profile.side_cone_degrees and distance <= profile.side_range_meters:
            ranked.append((100.0 + angle + distance, point))
    ranked.sort(key=lambda item: item[0])
    return [point for _, point in ranked]


def _group_position(group: StoreRenderGroup) -> dict[str, float]:
    aisle = group.shelf_index % 2
    row = group.shelf_index // 2
    side = -1.0 if aisle == 0 else 1.0
    return {
        "x": row * LAYOUT["shelf_spacing"],
        "y": LAYOUT["floor_y"] + 0.45 + group.level_index * LAYOUT["level_height"],
        "z": side * LAYOUT["aisle_spacing"] + group.slot_index * LAYOUT["slot_spacing"],
    }


def _group_dimensions(group: StoreRenderGroup) -> dict[str, float]:
    return {
        "width": LAYOUT["slot_width"],
        "height": LAYOUT["slot_height"],
        "depth": LAYOUT["shelf_depth"],
    }


def _cors_origin(host: str) -> str:
    if host in ("127.0.0.1", "localhost", "::1"):
        return "*"
    return "null"


if __name__ == "__main__":
    raise SystemExit(main())
