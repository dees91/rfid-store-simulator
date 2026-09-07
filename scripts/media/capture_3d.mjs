// Capture 3D store simulator screenshots and a screen recording with Playwright.
//
// Expects a running `scanner-emu-3d --standalone-inventory` server with a
// connected peer (see virtual_controller.py --peer). The camera follows a
// scripted, deterministic tour through one aisle so the recording is
// reproducible: walk the aisle scanning the left shelf, turn, walk back
// scanning the right shelf at a higher scanner power, stop.
//
// Usage:
//   NODE_PATH=<dir with playwright> SCANNER_EMU_3D_URL=http://127.0.0.1:8777 \
//     node scripts/media/capture_3d.mjs docs/media/raw
import { mkdirSync, renameSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const url = process.env.SCANNER_EMU_3D_URL;
if (!url) throw new Error("SCANNER_EMU_3D_URL must point at a running scanner-emu-3d server");
const outDir = resolve(process.argv[2] || "docs/media/raw");
const stills = resolve(outDir, "stills");
const videoDir = resolve(outDir, "video3d");
mkdirSync(stills, { recursive: true });
mkdirSync(videoDir, { recursive: true });

const width = 1920;
const height = 1080;
const EYE_HEIGHT = 1.55;

// Aisle geometry from the generated store: shelves are rows of groups sharing
// an x coordinate; the camera walks between the first two rows.
const store = await (await fetch(`${url}/api/store`)).json();
const xs = [...new Set(store.render_groups.map((g) => Math.round(g.position.x * 100) / 100))].sort((a, b) => a - b);
const zs = store.render_groups.map((g) => g.position.z);
const aisleX = (xs[0] + xs[1]) / 2;
const zMin = Math.min(...zs) + 0.4;
const zMax = Math.max(...zs) - 0.4;
console.log("aisle", { aisleX, zMin, zMax, shelfRows: xs.length, groups: store.render_groups.length });

const browser = await chromium.launch({
  headless: true,
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const context = await browser.newContext({
  viewport: { width, height },
  deviceScaleFactor: 1,
  recordVideo: { dir: videoDir, size: { width, height } },
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

const status = () =>
  page.evaluate(() => {
    const s = window.__scannerEmu3D.lastStatus;
    return {
      scanned: s?.aggregate_progress?.scanned_tags,
      total: s?.aggregate_progress?.total_tags,
      inventory: s?.inventory_running,
      scanning: s?.scan_active,
      peers: s?.peers?.length,
      power: s?.scanner_power,
    };
  });

const setPose = (x, z, yaw, pitch) =>
  page.evaluate(
    ({ x, z, yaw, pitch, eye }) => {
      const app = window.__scannerEmu3D;
      app.controls.locked = true;
      app.controls.yaw = yaw;
      app.controls.pitch = pitch;
      app.camera.position.set(x, eye, z);
      app.camera.rotation.y = yaw;
      app.camera.rotation.x = pitch;
    },
    { x, z, yaw, pitch, eye: EYE_HEIGHT },
  );

const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

// Glide the camera between two poses over `ms`, with an optional pitch wobble
// so the beam sweeps shelf levels the way a person moves a handheld reader.
const glide = async (from, to, ms, wobble = 0) => {
  const steps = Math.max(2, Math.round(ms / 40));
  for (let i = 0; i <= steps; i += 1) {
    const t = ease(i / steps);
    const pitch = from.pitch + (to.pitch - from.pitch) * t + wobble * Math.sin((i / steps) * Math.PI * 6);
    await setPose(
      from.x + (to.x - from.x) * t,
      from.z + (to.z - from.z) * t,
      from.yaw + (to.yaw - from.yaw) * t,
      pitch,
    );
    await page.waitForTimeout(40);
  }
};

const setPower = (level) =>
  page.evaluate((value) => {
    const input = document.querySelector("#scanner-power");
    input.value = String(value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, level);

const LOOK_LEFT = Math.PI / 2; // toward the lower-x shelf row
const LOOK_RIGHT = -Math.PI / 2; // toward the higher-x shelf row

try {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__scannerEmu3D?.sceneReady === true, null, { timeout: 30000 });
  await page.waitForFunction(() => window.__scannerEmu3D?.lastStatus?.aggregate_progress?.total_tags > 0, null, { timeout: 10000 });
  await page.locator("#store-canvas[data-ready='true']").waitFor({ timeout: 10000 });
  await page.waitForFunction(() => (window.__scannerEmu3D?.lastStatus?.peers?.length ?? 0) > 0, null, { timeout: 20000 });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: resolve(stills, "3d-store-idle.png") });

  // Walk to the aisle entrance while looking down the aisle.
  const start = await page.evaluate(() => ({
    x: window.__scannerEmu3D.camera.position.x,
    z: window.__scannerEmu3D.camera.position.z,
    yaw: window.__scannerEmu3D.controls.yaw,
    pitch: window.__scannerEmu3D.controls.pitch,
  }));
  const entrance = { x: aisleX, z: zMin, yaw: Math.PI, pitch: -0.04 };
  await glide(start, entrance, 2200);
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(stills, "3d-store-aisle.png") });

  // Turn to the left shelf and start scanning.
  await glide(entrance, { ...entrance, yaw: LOOK_LEFT, pitch: -0.12 }, 900);
  await page.keyboard.press("Space");
  await page.waitForFunction(() => window.__scannerEmu3D?.lastStatus?.scan_active === true, null, { timeout: 5000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(stills, "3d-store-scan-start.png") });

  // First pass: down the aisle, left shelf, default power.
  await glide({ x: aisleX, z: zMin, yaw: LOOK_LEFT, pitch: -0.12 }, { x: aisleX, z: zMax, yaw: LOOK_LEFT + 0.12, pitch: -0.2 }, 9000, 0.22);
  await page.screenshot({ path: resolve(stills, "3d-store-scanning.png") });
  console.log("after first pass", JSON.stringify(await status()));

  // Turn around and raise scanner power for the return pass.
  await glide({ x: aisleX, z: zMax, yaw: LOOK_LEFT + 0.12, pitch: -0.2 }, { x: aisleX, z: zMax, yaw: LOOK_RIGHT, pitch: -0.1 }, 1400);
  await setPower(5);
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(stills, "3d-store-power-max.png") });
  await glide({ x: aisleX, z: zMax, yaw: LOOK_RIGHT, pitch: -0.1 }, { x: aisleX, z: zMin, yaw: LOOK_RIGHT - 0.1, pitch: -0.22 }, 8000, 0.2);
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(stills, "3d-store-progress.png") });
  console.log("after second pass", JSON.stringify(await status()));

  // Look back down the aisle at the colored shelves, then stop scanning.
  await glide({ x: aisleX, z: zMin, yaw: LOOK_RIGHT - 0.1, pitch: -0.22 }, { x: aisleX, z: zMin, yaw: Math.PI, pitch: -0.05 }, 1600);
  await page.keyboard.press("Space");
  await page.waitForFunction(() => window.__scannerEmu3D?.lastStatus?.scan_active === false, null, { timeout: 5000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: resolve(stills, "3d-store-final.png") });
  console.log("final", JSON.stringify(await status()));
  if (errors.length) console.log("page errors", JSON.stringify(errors));
} finally {
  await context.close();
  await browser.close();
}

for (const file of readdirSync(videoDir)) {
  if (file.endsWith(".webm")) {
    renameSync(resolve(videoDir, file), resolve(videoDir, "3d-store.webm"));
    console.log("video", resolve(videoDir, "3d-store.webm"));
  }
}
