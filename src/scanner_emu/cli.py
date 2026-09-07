from __future__ import annotations

import argparse
import logging
import shlex
import sys
from typing import List, Optional

from .config import build_config, load_config
from .controller import ScannerEmulatorController
from .state import ScannerModel


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if sys.version_info < (3, 10):
        parser.exit(
            1,
            "scanner-emu requires Python 3.10+ because bumble from PyPI "
            "requires it.\n",
        )

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = build_config(
            transport_spec=args.transport,
            raw_config=load_config(args.config),
            model=args.model,
            name=args.name,
            address=args.address,
            log_level=args.log_level,
        )
        return run_repl(config)
    except KeyboardInterrupt:
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="scanner-emu: BLE emulator of Nordic ID EXA/NUR scanners (engine of the RFID Store Simulator)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the emulator")
    run_parser.add_argument("--transport", required=True, help="Bumble transport spec")
    run_parser.add_argument(
        "--model",
        choices=["exa51", "exa81"],
        default=None,
        help="Scanner model to emulate",
    )
    run_parser.add_argument("--name", default=None, help="Advertised device name")
    run_parser.add_argument(
        "--address",
        default=None,
        help="BLE address, for example F0:F1:F2:51:00:01",
    )
    run_parser.add_argument(
        "--config",
        default=None,
        help="Optional JSON config file with initial state",
    )
    run_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Python log level",
    )

    return parser


def run_repl(config) -> int:
    controller = ScannerEmulatorController(emit_events=False)
    snapshot = controller.start(config)

    print(
        "scanner-emu running on %s via %s"
        % (snapshot.name, config.transport_spec)
    )
    print("type `help` for commands")

    try:
        while True:
            try:
                line = input("scanner-emu> ")
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue

            try:
                should_exit, message = handle_command(controller, line)
                if message:
                    print(message)
                if should_exit:
                    break
            except Exception as error:
                print("error: %s" % error)
    finally:
        controller.stop()

    return 0


def handle_command(controller: ScannerEmulatorController, line: str):
    tokens = shlex.split(line)
    if not tokens:
        return False, None

    command = tokens[0].lower()
    if command in ("quit", "exit"):
        return True, "shutting down"

    if command == "help":
        return False, HELP_TEXT

    if command == "disconnect":
        return False, controller.disconnect()

    if command == "device":
        return False, handle_device_command(controller, tokens[1:])

    if command == "trigger":
        if len(tokens) != 2 or tokens[1] not in ("press", "release"):
            raise ValueError("usage: trigger press|release")
        return False, controller.send_trigger(tokens[1] == "press")

    if command == "rfid":
        return False, handle_rfid_command(controller, tokens[1:])

    if command == "barcode":
        if len(tokens) < 3 or tokens[1] != "emit":
            raise ValueError("usage: barcode emit <code>")
        return False, controller.emit_barcode(" ".join(tokens[2:]))

    raise ValueError("unknown command: %s" % command)


def handle_device_command(
    controller: ScannerEmulatorController, args: List[str]
) -> str:
    if args == ["show"]:
        return controller.describe_state()

    if len(args) == 2 and args[0] == "connectable":
        if args[1] not in ("on", "off"):
            raise ValueError("usage: device connectable on|off")
        return controller.set_connectable(args[1] == "on")

    if len(args) == 2 and args[0] == "model":
        return controller.set_model(ScannerModel.parse(args[1]))

    if len(args) == 2 and args[0] == "battery":
        return controller.set_battery(int(args[1]))

    if len(args) == 3 and args[0] == "fw":
        return controller.set_firmware(args[1], args[2])

    if len(args) == 2 and args[0] == "tx":
        return controller.set_tx_level(int(args[1]))

    raise ValueError(
        "usage: device show | device connectable on|off | "
        "device model exa51|exa81 | device battery <0-100> | "
        "device fw <app> <boot> | device tx <0-19>"
    )


def handle_rfid_command(
    controller: ScannerEmulatorController, args: List[str]
) -> str:
    if not args:
        raise ValueError("usage: rfid queue|flush|start|stop ...")

    if args[0] == "queue":
        if len(args) < 2 or len(args) > 4:
            raise ValueError("usage: rfid queue <epc_hex> [rssi] [antenna]")
        epc_hex = args[1]
        rssi = int(args[2]) if len(args) >= 3 else -45
        antenna = int(args[3]) if len(args) >= 4 else 0
        return controller.queue_rfid(epc_hex, rssi, antenna)

    if args == ["flush"]:
        return controller.flush_rfid()

    if args == ["start"]:
        return controller.start_inventory()

    if args == ["stop"]:
        return controller.stop_inventory()

    raise ValueError(
        "usage: rfid queue <epc_hex> [rssi] [antenna] | "
        "rfid flush | rfid start | rfid stop"
    )


HELP_TEXT = """\
help
device show
device connectable on|off
device model exa51|exa81
device battery <0-100>
device fw <app_version> <bootloader_version>
device tx <0-19>
trigger press|release
rfid queue <epc_hex> [rssi] [antenna]
rfid flush
rfid start
rfid stop
barcode emit <code>
disconnect
quit
"""
