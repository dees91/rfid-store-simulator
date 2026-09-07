import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const url = process.env.SCANNER_EMU_3D_URL;
if (!url) {
  throw new Error("SCANNER_EMU_3D_URL must point at a running scanner-emu-3d server");
}

const screenshotPath = resolve(
  process.env.SCANNER_EMU_3D_SCREENSHOT || `${tmpdir()}/scanner-emu-3d-smoke.png`,
);
const narrowScreenshotPath = resolve(
  process.env.SCANNER_EMU_3D_NARROW_SCREENSHOT ||
    `${tmpdir()}/scanner-emu-3d-smoke-narrow.png`,
);
mkdirSync(dirname(screenshotPath), { recursive: true });
mkdirSync(dirname(narrowScreenshotPath), { recursive: true });

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1366, height: 768 },
    deviceScaleFactor: 1,
  });
  const consoleErrors = [];
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__scannerEmu3D?.sceneReady === true, null, {
    timeout: 15000,
  });
  await page.waitForFunction(
    () => window.__scannerEmu3D?.lastStatus?.aggregate_progress?.total_tags > 0,
    null,
    { timeout: 5000 },
  );
  await page.locator("#store-canvas[data-ready='true']").waitFor({ timeout: 5000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: screenshotPath, fullPage: false });

  const initialProgress = await page.evaluate(() => {
    const aggregate = window.__scannerEmu3D.lastStatus.aggregate_progress;
    return {
      scannedTags: aggregate.scanned_tags,
      remainingTags: aggregate.remaining_tags,
      unscannedGroups: aggregate.unscanned_group_count,
      legend: document.querySelector(".progress-legend")?.textContent || "",
      labelHidden: document.querySelector("#progress-label")?.hidden,
    };
  });

  if (
    initialProgress.scannedTags !== 0 ||
    initialProgress.remainingTags <= 0 ||
    initialProgress.unscannedGroups <= 0 ||
    !initialProgress.legend.includes("Unscanned") ||
    initialProgress.labelHidden !== true
  ) {
    throw new Error(`Initial progress UI is wrong: ${JSON.stringify(initialProgress)}`);
  }

  const initialPowerUi = await readPowerUi(page);
  if (
    initialPowerUi.statusPower !== 3 ||
    initialPowerUi.inputValue !== "3" ||
    !initialPowerUi.valueText.includes("Medium") ||
    !initialPowerUi.effectText.includes("Previous max feel")
  ) {
    throw new Error(`Initial scanner power UI is wrong: ${JSON.stringify(initialPowerUi)}`);
  }

  const initialConeSignature = initialPowerUi.coneSignature;
  await setPowerLevel(page, 2);
  const lowPowerUi = await readPowerUi(page);
  if (
    lowPowerUi.statusPower !== 2 ||
    lowPowerUi.inputValue !== "2" ||
    !lowPowerUi.valueText.includes("Low") ||
    !lowPowerUi.effectText.includes("Close focused") ||
    lowPowerUi.scanActive ||
    lowPowerUi.inventoryRunning ||
    lowPowerUi.coneSignature === initialConeSignature
  ) {
    throw new Error(`Scanner power control did not update cleanly: ${JSON.stringify(lowPowerUi)}`);
  }
  await setPowerLevel(page, 5);
  const restoredPowerUi = await readPowerUi(page);
  if (
    restoredPowerUi.statusPower !== 5 ||
    restoredPowerUi.scanActive ||
    restoredPowerUi.inventoryRunning
  ) {
    throw new Error(`Scanner power did not restore to max: ${JSON.stringify(restoredPowerUi)}`);
  }

  const pixelStats = await canvasPixelStats(page, 160, 90);

  if (!pixelStats.webgl || pixelStats.variedPixels < 100) {
    throw new Error(`3D canvas appears blank: ${JSON.stringify(pixelStats)}`);
  }

  await page.setViewportSize({ width: 390, height: 720 });
  await page.waitForTimeout(250);
  await page.screenshot({ path: narrowScreenshotPath, fullPage: false });
  const narrowPixelStats = await canvasPixelStats(page, 120, 180);
  const narrowLayout = await page.evaluate(() => {
    const hud = document.querySelector(".hud")?.getBoundingClientRect();
    const button = document.querySelector("#trigger-button")?.getBoundingClientRect();
    const power = document.querySelector(".power-control")?.getBoundingClientRect();
    return {
      hud: hud && {
        left: Math.round(hud.left),
        right: Math.round(hud.right),
        bottom: Math.round(hud.bottom),
        width: Math.round(hud.width),
      },
      buttonTop: button ? Math.round(button.top) : null,
      powerBottom: power ? Math.round(power.bottom) : null,
    };
  });
  if (
    !narrowPixelStats.webgl ||
    narrowPixelStats.variedPixels < 80 ||
    !narrowLayout.hud ||
    narrowLayout.hud.left < 0 ||
    narrowLayout.hud.right > 390 ||
    narrowLayout.powerBottom > narrowLayout.buttonTop
  ) {
    throw new Error(
      `Narrow viewport smoke failed: ${JSON.stringify({ narrowPixelStats, narrowLayout })}`,
    );
  }
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.waitForTimeout(250);

  if (process.env.SCANNER_EMU_3D_EXPECT_BACKEND_STOPPED === "1") {
    const backendLabel = await page.locator("#backend-state").innerText();
    if (!backendLabel.includes("stopped")) {
      throw new Error(`Expected backend stopped state, got ${backendLabel}`);
    }
  }

  const initialPose = await page.evaluate(() => ({
    x: window.__scannerEmu3D.camera.position.x,
    z: window.__scannerEmu3D.camera.position.z,
    yaw: window.__scannerEmu3D.camera.rotation.y,
    pitch: window.__scannerEmu3D.camera.rotation.x,
  }));
  await page.keyboard.down("w");
  await page.waitForTimeout(350);
  await page.keyboard.up("w");
  const walkedPose = await page.evaluate(() => ({
    x: window.__scannerEmu3D.camera.position.x,
    z: window.__scannerEmu3D.camera.position.z,
  }));
  const walkDistance = Math.hypot(walkedPose.x - initialPose.x, walkedPose.z - initialPose.z);
  if (walkDistance < 0.15) {
    throw new Error(`Camera did not walk far enough: ${walkDistance}`);
  }

  let pointerLockGranted = true;
  await page.click("#store-canvas", { position: { x: 320, y: 240 } });
  try {
    await page.waitForFunction(() => document.pointerLockElement?.id === "store-canvas", null, {
      timeout: 5000,
    });
  } catch {
    pointerLockGranted = false;
    await page.evaluate(() => {
      window.__scannerEmu3D.controls.locked = true;
    });
  }
  await page.mouse.move(360, 260);
  await page.mouse.move(520, 310);
  await page.waitForTimeout(150);
  const aimedPose = await page.evaluate(() => ({
    yaw: window.__scannerEmu3D.camera.rotation.y,
    pitch: window.__scannerEmu3D.camera.rotation.x,
  }));
  if (
    Math.abs(aimedPose.yaw - initialPose.yaw) < 0.01 &&
    Math.abs(aimedPose.pitch - initialPose.pitch) < 0.01
  ) {
    throw new Error(`Camera aim did not change: ${JSON.stringify({ initialPose, aimedPose })}`);
  }
  if (pointerLockGranted) {
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !document.pointerLockElement, null, { timeout: 5000 });
  } else {
    await page.evaluate(() => {
      window.__scannerEmu3D.controls.locked = false;
    });
  }

  const trigger = page.locator("#trigger-button");
  const box = await trigger.boundingBox();
  if (!box) {
    throw new Error("Trigger button was not visible");
  }
  const initialTriggerUi = await page.evaluate(() => ({
    disabled: document.querySelector("#trigger-button")?.disabled,
    label: document.querySelector("[data-trigger-label]")?.textContent,
    pressed: document.querySelector("#trigger-button")?.getAttribute("aria-pressed"),
  }));
  if (
    initialTriggerUi.disabled ||
    initialTriggerUi.label !== "Start Scan" ||
    initialTriggerUi.pressed !== "false"
  ) {
    throw new Error(`Initial trigger toggle UI is wrong: ${JSON.stringify(initialTriggerUi)}`);
  }
  await page.evaluate(() => {
    const state = window.__scannerEmu3D;
    const targetGroup = state.renderGroups[0];
    const side = targetGroup.position.z < 0 ? -1 : 1;
    state.camera.position.set(
      targetGroup.position.x,
      1.55,
      targetGroup.position.z - side * 1.45,
    );
    state.camera.lookAt(
      targetGroup.position.x,
      targetGroup.position.y,
      targetGroup.position.z,
    );
    state.controls.yaw = state.camera.rotation.y;
    state.controls.pitch = state.camera.rotation.x;
    state.camera.updateMatrixWorld(true);
    state.renderer.render(state.scene, state.camera);
  });
  await page.waitForTimeout(250);
  const visibleProgressBeforeScan = await countCanvasProgressPixels(page);
  if (visibleProgressBeforeScan.redPixels < 80) {
    throw new Error(
      `Unscanned progress overlay is not visible: ${JSON.stringify(visibleProgressBeforeScan)}`,
    );
  }
  await trigger.click();
  await page.waitForFunction(
    () => window.__scannerEmu3D?.lastStatus?.scan_active === true,
    null,
    { timeout: 5000 },
  );
  await page.waitForTimeout(350);
  const latchedScanUi = await page.evaluate(() => ({
    desired: window.__scannerEmu3D?.controls?.desiredScanActive,
    localActive: window.__scannerEmu3D?.controls?.localScanActive,
    synced: window.__scannerEmu3D?.controls?.syncedScanActive,
    statusActive: window.__scannerEmu3D?.lastStatus?.scan_active,
    statusPressed: window.__scannerEmu3D?.lastStatus?.trigger_pressed,
    inventoryRunning: window.__scannerEmu3D?.lastStatus?.inventory_running,
    label: document.querySelector("[data-trigger-label]")?.textContent,
    pressed: document.querySelector("#trigger-button")?.getAttribute("aria-pressed"),
  }));
  if (
    !latchedScanUi.desired ||
    !latchedScanUi.localActive ||
    !latchedScanUi.synced ||
    !latchedScanUi.statusActive ||
    latchedScanUi.statusPressed ||
    !latchedScanUi.inventoryRunning ||
    latchedScanUi.label !== "Stop Scan" ||
    latchedScanUi.pressed !== "true"
  ) {
    throw new Error(
      `Scan did not stay latched after trigger pulse: ${JSON.stringify(latchedScanUi)}`,
    );
  }
  await page.waitForFunction(
    () => window.__scannerEmu3D?.lastStatus?.aggregate_progress?.scanned_tags > 0,
    null,
    { timeout: 5000 },
  );
  const scanProgress = await page.evaluate(() => {
    const state = window.__scannerEmu3D;
    const aggregate = state.lastStatus.aggregate_progress;
    const scannedGroups = [...state.groupProgress.values()].filter(
      (entry) => entry.scanned_tags > 0,
    ).length;
    const colors = state.productMesh.instanceColor.array;
    const uniqueColors = new Set();
    for (let index = 0; index < colors.length; index += 3) {
      uniqueColors.add(
        `${Math.round(colors[index] * 255)}:${Math.round(colors[index + 1] * 255)}:${Math.round(
          colors[index + 2] * 255,
        )}`,
      );
    }
    return {
      scannedTags: aggregate.scanned_tags,
      remainingTags: aggregate.remaining_tags,
      scannedGroups,
      uniqueColorCount: uniqueColors.size,
    };
  });
  if (scanProgress.scannedTags <= 0 || scanProgress.scannedGroups <= 0) {
    throw new Error(`Scanning did not update progress: ${JSON.stringify(scanProgress)}`);
  }
  if (scanProgress.uniqueColorCount < 2) {
    throw new Error(`Progress colors did not change: ${JSON.stringify(scanProgress)}`);
  }
  await page.evaluate(() => {
    const state = window.__scannerEmu3D;
    const targetGroup =
      state.renderGroups.find((group) => state.groupProgress.get(group.group_id)?.scanned_tags > 0) ||
      state.renderGroups[0];
    const side = targetGroup.position.z < 0 ? -1 : 1;
    state.camera.position.set(
      targetGroup.position.x,
      1.55,
      targetGroup.position.z - side * 1.45,
    );
    state.camera.lookAt(
      targetGroup.position.x,
      targetGroup.position.y,
      targetGroup.position.z,
    );
    state.controls.yaw = state.camera.rotation.y;
    state.controls.pitch = state.camera.rotation.x;
    state.camera.updateMatrixWorld(true);
    state.renderer.render(state.scene, state.camera);
  });
  await page.waitForTimeout(250);
  const visibleProgressAfterScan = await countCanvasProgressPixels(page);
  const visibleScannedBefore =
    visibleProgressBeforeScan.greenPixels + visibleProgressBeforeScan.amberPixels;
  const visibleScannedAfter =
    visibleProgressAfterScan.greenPixels + visibleProgressAfterScan.amberPixels;
  if (visibleScannedAfter < visibleScannedBefore + 80) {
    throw new Error(
      `Scanned progress overlay is not visible: ${JSON.stringify({
        before: visibleProgressBeforeScan,
        after: visibleProgressAfterScan,
      })}`,
    );
  }

  const labelState = await page.evaluate(() => {
    const state = window.__scannerEmu3D;
    const targetGroup =
      state.renderGroups.find((group) => state.groupProgress.get(group.group_id)?.scanned_tags > 0) ||
      state.renderGroups[0];
    state.camera.lookAt(
      targetGroup.position.x,
      targetGroup.position.y,
      targetGroup.position.z,
    );
    state.camera.updateMatrixWorld(true);
    state.productMesh.updateMatrixWorld(true);
    state.updateProgressLabel();
    const label = document.querySelector("#progress-label");
    return {
      hidden: label.hidden,
      text: label.textContent,
    };
  });
  if (labelState.hidden || !labelState.text.includes("scanned -")) {
    throw new Error(`Progress label did not appear for aimed group: ${JSON.stringify(labelState)}`);
  }
  await trigger.click();
  await page.waitForFunction(
    () => window.__scannerEmu3D?.lastStatus?.scan_active === false,
    null,
    { timeout: 5000 },
  );
  await page.waitForFunction(
    () =>
      window.__scannerEmu3D?.lastStatus?.scan_active === false &&
      window.__scannerEmu3D?.lastStatus?.trigger_pressed === false &&
      window.__scannerEmu3D?.controls?.desiredScanActive === false &&
      window.__scannerEmu3D?.controls?.localScanActive === false &&
      window.__scannerEmu3D?.controls?.syncedScanActive === false &&
      document.querySelector("[data-trigger-label]")?.textContent === "Start Scan",
    null,
    { timeout: 5000 },
  );

  if (consoleErrors.length) {
    throw new Error(`Browser console errors: ${consoleErrors.join(" | ")}`);
  }

  console.log(
    JSON.stringify({
      screenshotPath,
      narrowScreenshotPath,
      pixelStats,
      narrowPixelStats,
      walkDistance,
      pointerLockGranted,
      triggerToggle: true,
      initialProgress,
      initialPowerUi,
      lowPowerUi,
      scanProgress,
      visibleProgressBeforeScan,
      visibleProgressAfterScan,
      labelState,
    }),
  );
} finally {
  await browser.close();
}

async function readPowerUi(page) {
  return page.evaluate(() => ({
    statusPower: window.__scannerEmu3D?.lastStatus?.scanner_power,
    inputValue: document.querySelector("#scanner-power")?.value,
    valueText: document.querySelector("#scanner-power-value")?.textContent || "",
    effectText: document.querySelector("#scanner-power-effect")?.textContent || "",
    scanActive: window.__scannerEmu3D?.lastStatus?.scan_active,
    inventoryRunning: window.__scannerEmu3D?.lastStatus?.inventory_running,
    coneSignature: window.__scannerEmu3D?.scanConeSignature || "",
  }));
}

async function setPowerLevel(page, level) {
  await page.locator("#scanner-power").evaluate((element, nextLevel) => {
    element.value = String(nextLevel);
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, level);
  await page.waitForFunction(
    (expectedLevel) => window.__scannerEmu3D?.lastStatus?.scanner_power === expectedLevel,
    level,
    { timeout: 5000 },
  );
}

async function canvasPixelStats(page, width, height) {
  return page.evaluate(
    ({ width: sampleWidth, height: sampleHeight }) => {
      const canvas = document.querySelector("#store-canvas");
      const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
      if (!gl) {
        return { webgl: false, variedPixels: 0 };
      }
      const sample = document.createElement("canvas");
      sample.width = sampleWidth;
      sample.height = sampleHeight;
      const context = sample.getContext("2d");
      context.drawImage(canvas, 0, 0, sample.width, sample.height);
      const pixels = context.getImageData(0, 0, sample.width, sample.height).data;
      let variedPixels = 0;
      const firstR = pixels[0];
      const firstG = pixels[1];
      const firstB = pixels[2];
      for (let index = 0; index < pixels.length; index += 4) {
        if (
          pixels[index] !== firstR ||
          pixels[index + 1] !== firstG ||
          pixels[index + 2] !== firstB
        ) {
          variedPixels += 1;
        }
      }
      return {
        webgl: true,
        variedPixels,
        width: sample.width,
        height: sample.height,
      };
    },
    { width, height },
  );
}

async function countCanvasProgressPixels(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector("#store-canvas");
    const sample = document.createElement("canvas");
    sample.width = 240;
    sample.height = 160;
    const context = sample.getContext("2d");
    const sourceWidth = Math.max(1, Math.floor(canvas.width * 0.34));
    const sourceHeight = Math.max(1, Math.floor(canvas.height * 0.42));
    const sourceX = Math.max(0, Math.floor((canvas.width - sourceWidth) / 2));
    const sourceY = Math.max(0, Math.floor((canvas.height - sourceHeight) / 2));
    context.drawImage(
      canvas,
      sourceX,
      sourceY,
      sourceWidth,
      sourceHeight,
      0,
      0,
      sample.width,
      sample.height,
    );
    const pixels = context.getImageData(0, 0, sample.width, sample.height).data;
    let redPixels = 0;
    let greenPixels = 0;
    let amberPixels = 0;
    for (let index = 0; index < pixels.length; index += 4) {
      const red = pixels[index];
      const green = pixels[index + 1];
      const blue = pixels[index + 2];
      if (red >= 85 && red > green * 1.35 && red > blue * 1.25) {
        redPixels += 1;
      }
      if (green >= 65 && green > red * 1.25 && green > blue * 1.12) {
        greenPixels += 1;
      }
      if (red >= 95 && green >= 60 && red > blue * 1.4 && green > blue * 1.2) {
        amberPixels += 1;
      }
    }
    return {
      redPixels,
      greenPixels,
      amberPixels,
      sampleWidth: sample.width,
      sampleHeight: sample.height,
    };
  });
}
