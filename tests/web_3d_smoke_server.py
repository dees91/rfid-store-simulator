from __future__ import annotations

import os
import time

from scanner_emu.product_catalog import Product, ProductCatalog
from scanner_emu.store_3d import Store3DConfig, generate_store_session
from scanner_emu.three_d import Store3DBridge, Store3DHttpServer
from tests.test_three_d_bridge import FakeController


def main() -> int:
    target = int(os.environ.get("SCANNER_EMU_3D_TAG_TARGET", "20"))
    seed = int(os.environ.get("SCANNER_EMU_3D_SEED", "9"))
    running = os.environ.get("SCANNER_EMU_3D_BACKEND_RUNNING", "1").lower()
    backend_running = running not in ("0", "false", "no")
    if target <= 1:
        products = [Product("4006381333931", "books", 1)]
    else:
        first = max(1, min(target * 6 // 10, target - 1))
        products = [
            Product("4006381333931", "books", first),
            Product("4012345358216", "kitchen", target - first),
        ]
    session = generate_store_session(
        ProductCatalog(products=products),
        Store3DConfig(seed=seed),
    )
    bridge = Store3DBridge(
        FakeController(running=backend_running),
        session,
        standalone_inventory=True,
        max_scan_rate=20,
    )
    server = Store3DHttpServer("127.0.0.1", 0, bridge)
    server.start()
    print(server.url, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
