"""Serve a Bumble virtual Bluetooth controller over TCP, optionally with a
fake BLE central peer.

Lets the emulator run without any Bluetooth hardware, which is what media
capture and CI-style smoke runs need. Start this first, then point the
emulator at it:

    python scripts/media/virtual_controller.py --port 9100 --peer
    scanner-emu-3d --transport tcp-client:127.0.0.1:9100 --standalone-inventory ...

With ``--peer`` a second virtual controller on the same radio link runs a
minimal BLE central that behaves like a host app at the GATT level: it scans
for an advertised name containing ``EXA``, connects, and subscribes to the
Nordic UART TX characteristic so the emulator has a peer to notify. It does
not speak the NUR protocol; use ``--standalone-inventory`` on the 3D UI so the
bridge starts inventory itself. No real device can reach a virtual controller.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from bumble import hci
from bumble.controller import Controller
from bumble.core import AdvertisingData
from bumble.device import Device, Peer
from bumble.link import LocalLink
from bumble.transport import open_transport

LOGGER = logging.getLogger("virtual_controller")
NUR_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


async def run_peer(link: LocalLink, name_fragment: str) -> None:
    controller = Controller("PEER-CTRL", link=link, public_address="F0:F1:F2:00:00:C2")
    central = Device.with_hci("DEMO-CENTRAL", hci.Address("F0:F1:F2:00:00:A1"), controller, controller)
    await central.power_on()
    notifications = 0

    while True:
        target = asyncio.get_running_loop().create_future()

        def on_advertisement(advertisement) -> None:
            local_name = advertisement.data.get(AdvertisingData.COMPLETE_LOCAL_NAME)
            if isinstance(local_name, bytes):
                local_name = local_name.decode("utf-8", "ignore")
            if local_name and name_fragment.lower() in local_name.lower() and not target.done():
                target.set_result(advertisement.address)

        central.on("advertisement", on_advertisement)
        await central.start_scanning()
        address = await target
        await central.stop_scanning()
        central.remove_listener("advertisement", on_advertisement)

        LOGGER.info("peer connecting to %s", address)
        connection = await central.connect(address)
        disconnected = asyncio.get_running_loop().create_future()
        connection.on("disconnection", lambda reason: disconnected.done() or disconnected.set_result(reason))
        peer = Peer(connection)
        await peer.discover_services()
        await peer.discover_characteristics()
        tx = peer.get_characteristics_by_uuid(NUR_TX_UUID)
        if not tx:
            LOGGER.warning("peer found no NUR TX characteristic; disconnecting")
            await connection.disconnect()
            continue

        def on_notify(value: bytes) -> None:
            nonlocal notifications
            notifications += 1
            if notifications % 50 == 1:
                LOGGER.info("peer received %d notifications (%d bytes latest)", notifications, len(value))

        await tx[0].subscribe(on_notify)
        LOGGER.info("peer connected and subscribed to NUR TX")
        reason = await disconnected
        LOGGER.info("peer disconnected (%s); rescanning", reason)


async def serve(host: str, port: int, with_peer: bool, name_fragment: str) -> None:
    spec = "tcp-server:%s:%s" % (host, port)
    link = LocalLink()
    async with await open_transport(spec) as transport:
        controller = Controller(
            "VIRTUAL-CTRL",
            host_source=transport.source,
            host_sink=transport.sink,
            link=link,
            public_address="F0:F1:F2:00:00:C1",
        )
        LOGGER.info("virtual controller %s listening on %s", controller.name, spec)
        if with_peer:
            asyncio.create_task(run_peer(link, name_fragment))
        await asyncio.Event().wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--peer", action="store_true", help="run a fake BLE central on the same link")
    parser.add_argument("--peer-name", default="EXA", help="advertised name fragment the peer connects to")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(serve(args.host, args.port, args.peer, args.peer_name))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
