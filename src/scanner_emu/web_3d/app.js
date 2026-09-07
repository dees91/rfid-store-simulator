import * as THREE from "./vendor/three.module.js";

const canvas = document.querySelector("#store-canvas");
const renderFallback = document.querySelector("#render-fallback");
const touchFallback = document.querySelector("#touch-fallback");
const progressLabel = document.querySelector("#progress-label");
const connectionPill = document.querySelector("#connection-pill");
const backendState = document.querySelector("#backend-state");
const peerState = document.querySelector("#peer-state");
const triggerState = document.querySelector("#trigger-state");
const inventoryState = document.querySelector("#inventory-state");
const mismatchBanner = document.querySelector("#mismatch-banner");
const scannerPowerInput = document.querySelector("#scanner-power");
const scannerPowerValue = document.querySelector("#scanner-power-value");
const scannerPowerEffect = document.querySelector("#scanner-power-effect");
const triggerButton = document.querySelector("#trigger-button");
const triggerButtonLabel = triggerButton.querySelector("[data-trigger-label]");
const metricEls = new Map(
  [...document.querySelectorAll("[data-field]")].map((el) => [el.dataset.field, el]),
);

const controls = {
  keys: new Set(),
  localScanActive: false,
  locked: false,
  yaw: Math.PI,
  pitch: -0.04,
  lastPoseAt: 0,
  lastPoseKey: "",
  poseInFlight: false,
  desiredScanActive: false,
  syncedScanActive: false,
  scanRequestInFlight: false,
  scannerPowerRequestInFlight: false,
  scannerPowerDirty: false,
  bounds: {
    minX: -4,
    maxX: 14,
    minZ: -7,
    maxZ: 9,
  },
};

const appState = {
  renderer: null,
  scene: null,
  camera: null,
  controls,
  sceneReady: false,
  lastStatus: null,
  renderGroups: [],
  productMesh: null,
  progressOverlayMesh: null,
  scanCones: null,
  scanConeSignature: "",
  scannerPowerProfiles: new Map(),
  groupProgress: new Map(),
  groupIdToInstanceIndex: new Map(),
  instanceIndexToGroupId: [],
  progressVersion: null,
};

window.__scannerEmu3D = appState;

let renderer;
let scene;
let camera;
let clock;
let statusPoll;
const viewDirection = new THREE.Vector3();
const moveVector = new THREE.Vector3();
const rightVector = new THREE.Vector3();
const forwardVector = new THREE.Vector3();
const matrix = new THREE.Matrix4();
const color = new THREE.Color();
const raycaster = new THREE.Raycaster();
const reticleNdc = new THREE.Vector2(0, 0);
const progressUnscannedColor = new THREE.Color(0xb43e34);
const progressPartialColor = new THREE.Color(0xd79b28);
const progressCompleteColor = new THREE.Color(0x21845a);
const progressOverlayColors = {
  unscanned: 0xff4a3d,
  partial: 0xffb02e,
  complete: 0x19d27f,
};

main().catch((error) => {
  console.error(error);
  setConnection("bad", "Local bridge offline");
  showFallback("Local bridge connection failed.");
});

async function main() {
  if (isCoarsePointer()) {
    touchFallback.hidden = false;
  }
  if (!webglAvailable()) {
    showFallback("WebGL is unavailable in this browser.");
    return;
  }

  const [store, status] = await Promise.all([
    fetchJson("/api/store"),
    fetchJson("/api/status"),
  ]);
  setConnection("ok", "Bridge online");
  initScene(store);
  renderStatus(status);
  bindInput();
  startStatusStream();
  sendPose(true);
}

function initScene(store) {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xdfe6dd);
  scene.fog = new THREE.Fog(0xdfe6dd, 22, 58);

  renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: "high-performance",
    preserveDrawingBuffer: true,
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  camera = new THREE.PerspectiveCamera(66, 1, 0.05, 120);
  camera.rotation.order = "YXZ";
  scene.add(camera);

  controls.bounds = computeBounds(store.render_groups);
  setStartPose(store.render_groups);
  appState.renderGroups = store.render_groups;
  appState.groupProgress = normalizeGroupProgress(store.group_progress);
  buildGroupIndex(store.render_groups);

  addLights(scene);
  addFloor(scene, controls.bounds);
  addShelves(scene, store.render_groups, store.layout);
  appState.productMesh = addProducts(scene, store.render_groups);
  appState.progressOverlayMesh = addProgressOverlays(scene, store.render_groups);
  addScannerModel(camera);
  appState.scannerPowerProfiles = normalizeScannerPowerProfiles(store.scanner_power_profiles);
  appState.scanCones = addScanCones(camera, store.scan_model);

  clock = new THREE.Clock();
  resizeRenderer();
  window.addEventListener("resize", resizeRenderer);
  renderer.render(scene, camera);

  appState.renderer = renderer;
  appState.scene = scene;
  appState.camera = camera;
  appState.sceneReady = true;
  canvas.dataset.ready = "true";
  requestAnimationFrame(animate);
}

function addLights(targetScene) {
  const hemi = new THREE.HemisphereLight(0xffffff, 0xa6b19e, 1.9);
  targetScene.add(hemi);

  const key = new THREE.DirectionalLight(0xffffff, 2.1);
  key.position.set(-6, 9, -4);
  targetScene.add(key);

  const fill = new THREE.DirectionalLight(0xcfe8ff, 0.7);
  fill.position.set(9, 5, 8);
  targetScene.add(fill);
}

function addFloor(targetScene, bounds) {
  const width = bounds.maxX - bounds.minX + 2;
  const depth = bounds.maxZ - bounds.minZ + 2;
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerZ = (bounds.minZ + bounds.maxZ) / 2;

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(width, depth),
    new THREE.MeshStandardMaterial({
      color: 0xe9eee6,
      roughness: 0.88,
      metalness: 0,
    }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(centerX, 0, centerZ);
  floor.receiveShadow = true;
  targetScene.add(floor);

  const aisle = new THREE.Mesh(
    new THREE.PlaneGeometry(width, Math.min(depth, 3.3)),
    new THREE.MeshStandardMaterial({
      color: 0xf4f1df,
      roughness: 0.92,
      metalness: 0,
    }),
  );
  aisle.rotation.x = -Math.PI / 2;
  aisle.position.set(centerX, 0.01, centerZ);
  targetScene.add(aisle);

  const grid = new THREE.GridHelper(Math.max(width, depth), 32, 0x8b968d, 0xc5cec5);
  grid.position.set(centerX, 0.018, centerZ);
  targetScene.add(grid);
}

function addShelves(targetScene, groups, layout) {
  const shelfLevels = new Map();
  const shelves = new Map();

  for (const group of groups) {
    const pos = group.position;
    const key = `${group.shelf_index}:${group.level_index}`;
    const shelfKey = `${group.shelf_index}`;
    const level = shelfLevels.get(key) || {
      shelfIndex: group.shelf_index,
      x: pos.x,
      y: pos.y - 0.22,
      minZ: pos.z,
      maxZ: pos.z,
    };
    level.minZ = Math.min(level.minZ, pos.z);
    level.maxZ = Math.max(level.maxZ, pos.z);
    shelfLevels.set(key, level);

    const shelf = shelves.get(shelfKey) || {
      x: pos.x,
      minZ: pos.z,
      maxZ: pos.z,
      minY: pos.y,
      maxY: pos.y,
    };
    shelf.minZ = Math.min(shelf.minZ, pos.z);
    shelf.maxZ = Math.max(shelf.maxZ, pos.z);
    shelf.minY = Math.min(shelf.minY, pos.y);
    shelf.maxY = Math.max(shelf.maxY, pos.y);
    shelves.set(shelfKey, shelf);
  }

  const levelEntries = [...shelfLevels.values()];
  const plankMesh = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({ color: 0x52645b, roughness: 0.64 }),
    levelEntries.length,
  );
  levelEntries.forEach((level, index) => {
    const span = level.maxZ - level.minZ + (layout.slot_spacing || 0.42) * 1.35;
    matrix.compose(
      new THREE.Vector3(level.x, level.y, (level.minZ + level.maxZ) / 2),
      new THREE.Quaternion(),
      new THREE.Vector3((layout.shelf_depth || 0.55) + 0.2, 0.06, span),
    );
    plankMesh.setMatrixAt(index, matrix);
  });
  targetScene.add(plankMesh);

  const postCount = shelves.size * 4;
  const postMesh = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({ color: 0x3d4b44, roughness: 0.58 }),
    postCount,
  );
  let index = 0;
  shelves.forEach((shelf) => {
    const height = shelf.maxY + 0.32;
    const halfDepth = ((layout.shelf_depth || 0.55) + 0.16) / 2;
    const minZ = shelf.minZ - (layout.slot_spacing || 0.42) * 0.7;
    const maxZ = shelf.maxZ + (layout.slot_spacing || 0.42) * 0.7;
    for (const xOffset of [-halfDepth, halfDepth]) {
      for (const z of [minZ, maxZ]) {
        matrix.compose(
          new THREE.Vector3(shelf.x + xOffset, height / 2, z),
          new THREE.Quaternion(),
          new THREE.Vector3(0.055, height, 0.055),
        );
        postMesh.setMatrixAt(index, matrix);
        index += 1;
      }
    }
  });
  targetScene.add(postMesh);
}

function addProducts(targetScene, groups) {
  const productMesh = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.78,
      metalness: 0.02,
      vertexColors: true,
    }),
    groups.length,
  );

  groups.forEach((group, index) => {
    setProductMatrix(productMesh, index, group, 1);
    productMesh.setColorAt(index, progressColor(progressForGroup(group)));
  });
  productMesh.instanceMatrix.needsUpdate = true;
  if (productMesh.instanceColor) {
    productMesh.instanceColor.needsUpdate = true;
  }
  targetScene.add(productMesh);
  return productMesh;
}

function addProgressOverlays(targetScene, groups) {
  const overlayGroup = new THREE.Group();
  overlayGroup.userData.meshes = {
    unscanned: buildProgressOverlayMesh(progressOverlayColors.unscanned, groups.length),
    partial: buildProgressOverlayMesh(progressOverlayColors.partial, groups.length),
    complete: buildProgressOverlayMesh(progressOverlayColors.complete, groups.length),
  };

  Object.values(overlayGroup.userData.meshes).forEach((mesh) => {
    overlayGroup.add(mesh);
  });
  groups.forEach((group, index) => {
    setProgressOverlayState(overlayGroup, index, group, progressForGroup(group));
  });
  Object.values(overlayGroup.userData.meshes).forEach((mesh) => {
    mesh.instanceMatrix.needsUpdate = true;
  });
  targetScene.add(overlayGroup);
  return overlayGroup;
}

function buildProgressOverlayMesh(overlayColor, count) {
  const overlayMesh = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial({
      color: overlayColor,
      transparent: true,
      opacity: 0.78,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    }),
    count,
  );
  overlayMesh.renderOrder = 3;
  overlayMesh.frustumCulled = false;
  return overlayMesh;
}

function setProgressOverlayState(overlayGroup, index, group, progress) {
  const meshes = overlayGroup.userData.meshes;
  const activeState = progressOverlayState(progress);
  for (const [state, mesh] of Object.entries(meshes)) {
    if (state === activeState) {
      setProductMatrix(mesh, index, group, 1.045);
    } else {
      setHiddenMatrix(mesh, index);
    }
  }
}

function progressOverlayState(progress) {
  const state = String(progress?.visual_state || "");
  if (state === "complete" || state === "partial") {
    return state;
  }
  return "unscanned";
}

function setProductMatrix(mesh, index, group, scaleMultiplier) {
  const pos = group.position;
  const scale = productScaleForGroup(group);
  matrix.compose(
    new THREE.Vector3(pos.x, pos.y, pos.z),
    new THREE.Quaternion(),
    new THREE.Vector3(
      scale.x * scaleMultiplier,
      scale.y * scaleMultiplier,
      scale.z * scaleMultiplier,
    ),
  );
  mesh.setMatrixAt(index, matrix);
}

function setHiddenMatrix(mesh, index) {
  matrix.compose(
    new THREE.Vector3(0, -1000, 0),
    new THREE.Quaternion(),
    new THREE.Vector3(0, 0, 0),
  );
  mesh.setMatrixAt(index, matrix);
}

function productScaleForGroup(group) {
  const dims = group.dimensions;
  const mass = Math.min(1.35, 0.72 + Math.log2(group.tag_count + 1) / 7);
  return new THREE.Vector3(
    Math.max(0.08, dims.width * mass),
    Math.max(0.08, dims.height * (0.9 + mass * 0.22)),
    Math.max(0.08, dims.depth * (0.56 + mass * 0.2)),
  );
}

function addScannerModel(parentCamera) {
  const scanner = new THREE.Group();
  scanner.position.set(0.34, -0.31, -0.64);
  scanner.rotation.set(-0.12, -0.22, 0.04);

  const bodyMaterial = new THREE.MeshStandardMaterial({
    color: 0x293832,
    roughness: 0.52,
    metalness: 0.08,
  });
  const accentMaterial = new THREE.MeshStandardMaterial({
    color: 0x1f6f57,
    roughness: 0.46,
  });
  const lensMaterial = new THREE.MeshStandardMaterial({
    color: 0xf0c14b,
    emissive: 0x3f2c08,
    roughness: 0.34,
  });

  const body = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.16, 0.44), bodyMaterial);
  body.position.set(0, 0, -0.12);
  scanner.add(body);

  const nose = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.12, 0.16), accentMaterial);
  nose.position.set(0, 0.01, -0.42);
  scanner.add(nose);

  const lens = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.055, 0.018), lensMaterial);
  lens.position.set(0, 0.015, -0.51);
  scanner.add(lens);

  const handle = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.34, 0.13), bodyMaterial);
  handle.position.set(0.02, -0.22, -0.05);
  handle.rotation.x = -0.2;
  scanner.add(handle);

  parentCamera.add(scanner);
}

function addScanCones(parentCamera, scanModel) {
  const sideCone = buildCone(
    scanModel.side_range_meters,
    scanModel.side_cone_degrees,
    0x4f8fb1,
    0.1,
  );
  const mainCone = buildCone(
    scanModel.main_range_meters,
    scanModel.main_cone_degrees,
    0xf0c14b,
    0.18,
  );
  parentCamera.add(sideCone);
  parentCamera.add(mainCone);
  return { main: mainCone, side: sideCone };
}

function buildCone(length, degrees, coneColor, opacity) {
  const geometry = buildConeGeometry(length, degrees);
  const material = new THREE.MeshBasicMaterial({
    color: coneColor,
    transparent: true,
    opacity,
    wireframe: true,
    depthWrite: false,
  });
  const cone = new THREE.Mesh(geometry, material);
  cone.rotation.x = Math.PI / 2;
  return cone;
}

function buildConeGeometry(length, degrees) {
  const radius = Math.tan(THREE.MathUtils.degToRad(degrees)) * length;
  const geometry = new THREE.ConeGeometry(radius, length, 48, 1, true);
  geometry.translate(0, -length / 2, 0);
  return geometry;
}

function bindInput() {
  canvas.tabIndex = 0;
  canvas.addEventListener("click", () => {
    canvas.focus();
    if (!isCoarsePointer() && canvas.requestPointerLock) {
      const lockRequest = canvas.requestPointerLock();
      if (lockRequest && lockRequest.catch) {
        lockRequest.catch(() => {});
      }
    }
  });

  document.addEventListener("pointerlockchange", () => {
    controls.locked = document.pointerLockElement === canvas;
  });

  document.addEventListener("mousemove", (event) => {
    if (!controls.locked) {
      return;
    }
    controls.yaw -= event.movementX * 0.0022;
    controls.pitch -= event.movementY * 0.0022;
    controls.pitch = THREE.MathUtils.clamp(controls.pitch, -1.08, 0.72);
  });

  window.addEventListener("keydown", (event) => {
    const key = movementKey(event);
    if (key) {
      controls.keys.add(key);
      event.preventDefault();
    }
    if (event.code === "Space" && !event.repeat) {
      toggleTrigger();
      event.preventDefault();
    }
  });

  window.addEventListener("keyup", (event) => {
    const key = movementKey(event);
    if (key) {
      controls.keys.delete(key);
      event.preventDefault();
    }
    if (event.code === "Space") {
      event.preventDefault();
    }
  });

  triggerButton.addEventListener("click", (event) => {
    event.preventDefault();
    toggleTrigger();
  });

  if (scannerPowerInput) {
    scannerPowerInput.addEventListener("input", () => {
      const level = Number(scannerPowerInput.value);
      controls.scannerPowerDirty = true;
      renderScannerPower(level, profileForPowerLevel(level));
    });
    scannerPowerInput.addEventListener("change", () => {
      setScannerPower(Number(scannerPowerInput.value));
    });
    scannerPowerInput.addEventListener("blur", () => {
      controls.scannerPowerDirty = false;
      if (appState.lastStatus) {
        renderScannerPower(
          appState.lastStatus.scanner_power,
          appState.lastStatus.scanner_power_effect,
        );
      }
    });
  }

  window.addEventListener("blur", () => releaseTrigger("blur"));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      releaseTrigger("visibility");
    }
  });
}

function animate() {
  requestAnimationFrame(animate);
  const delta = Math.min(clock.getDelta(), 0.05);
  updateCamera(delta);
  updateProgressLabel();
  renderer.render(scene, camera);
  sendPose(false);
}

function updateCamera(delta) {
  camera.rotation.y = controls.yaw;
  camera.rotation.x = controls.pitch;
  camera.rotation.z = 0;

  moveVector.set(0, 0, 0);
  if (controls.keys.has("forward")) {
    moveVector.z -= 1;
  }
  if (controls.keys.has("backward")) {
    moveVector.z += 1;
  }
  if (controls.keys.has("left")) {
    moveVector.x -= 1;
  }
  if (controls.keys.has("right")) {
    moveVector.x += 1;
  }
  if (moveVector.lengthSq() === 0) {
    return;
  }

  moveVector.normalize();
  const speed = controls.keys.has("fast") ? 4.2 : 2.35;
  forwardVector.set(-Math.sin(controls.yaw), 0, -Math.cos(controls.yaw));
  rightVector.set(Math.cos(controls.yaw), 0, -Math.sin(controls.yaw));
  camera.position.addScaledVector(forwardVector, -moveVector.z * speed * delta);
  camera.position.addScaledVector(rightVector, moveVector.x * speed * delta);
  camera.position.x = THREE.MathUtils.clamp(
    camera.position.x,
    controls.bounds.minX,
    controls.bounds.maxX,
  );
  camera.position.z = THREE.MathUtils.clamp(
    camera.position.z,
    controls.bounds.minZ,
    controls.bounds.maxZ,
  );
  camera.position.y = 1.55;
}

async function toggleTrigger() {
  const nextActive = !triggerIsActive();
  if (nextActive && !canToggleTriggerOn(appState.lastStatus)) {
    setConnection("warn", "Waiting for peer");
    return;
  }
  controls.desiredScanActive = nextActive;
  controls.localScanActive = nextActive;
  updateTriggerButton(appState.lastStatus);
  await flushScanState();
}

async function releaseTrigger() {
  if (!triggerIsActive()) {
    return;
  }
  controls.desiredScanActive = false;
  controls.localScanActive = false;
  updateTriggerButton(appState.lastStatus);
  await flushScanState();
}

async function flushScanState() {
  if (controls.scanRequestInFlight) {
    return;
  }
  while (scanNeedsSync()) {
    const nextActive = controls.desiredScanActive;
    controls.scanRequestInFlight = true;
    const posted = await postScan(nextActive);
    controls.scanRequestInFlight = false;
    if (!posted) {
      if (nextActive) {
        controls.desiredScanActive = false;
        controls.localScanActive = false;
        updateTriggerButton(appState.lastStatus);
      }
      break;
    }
    controls.syncedScanActive = nextActive;
  }
}

function scanNeedsSync() {
  if (controls.syncedScanActive !== controls.desiredScanActive) {
    return true;
  }
  return !controls.desiredScanActive && Boolean(appState.lastStatus?.scan_active);
}

async function postScan(active) {
  try {
    const payload = await postJson("/api/scan", { active });
    setConnection("ok", "Bridge online");
    renderStatus(payload.status);
    return true;
  } catch (error) {
    console.error(error);
    setConnection("bad", "Local bridge offline");
    return false;
  }
}

async function sendPose(force) {
  if (!appState.sceneReady || controls.poseInFlight) {
    return;
  }
  const now = performance.now();
  const active = force || controls.locked || controls.localScanActive || controls.keys.size > 0;
  if (!active || (!force && now - controls.lastPoseAt < 100)) {
    return;
  }

  const pose = currentPose();
  const poseKey = JSON.stringify(pose);
  if (!force && poseKey === controls.lastPoseKey && !controls.localScanActive) {
    return;
  }

  controls.lastPoseAt = now;
  controls.lastPoseKey = poseKey;
  controls.poseInFlight = true;
  try {
    const payload = await postJson("/api/pose", pose);
    setConnection("ok", "Bridge online");
    renderStatus(payload.status);
  } catch (error) {
    console.error(error);
    setConnection("warn", "Bridge reconnecting");
  } finally {
    controls.poseInFlight = false;
  }
}

function currentPose() {
  camera.getWorldDirection(viewDirection).normalize();
  return {
    position: {
      x: roundPose(camera.position.x),
      y: roundPose(camera.position.y),
      z: roundPose(camera.position.z),
    },
    direction: {
      x: roundPose(viewDirection.x),
      y: roundPose(viewDirection.y),
      z: roundPose(viewDirection.z),
    },
  };
}

function startStatusStream() {
  if ("EventSource" in window) {
    const source = new EventSource("/api/events");
    source.onopen = () => setConnection("ok", "Bridge online");
    source.onmessage = (event) => {
      setConnection("ok", "Bridge online");
      renderStatus(JSON.parse(event.data));
    };
    source.onerror = () => setConnection("warn", "Bridge reconnecting");
  }

  statusPoll = window.setInterval(refreshStatus, 3000);
}

async function refreshStatus() {
  try {
    const status = await fetchJson("/api/status");
    setConnection("ok", "Bridge online");
    renderStatus(status);
  } catch (error) {
    console.error(error);
    setConnection("bad", "Local bridge offline");
  }
}

function renderStatus(status) {
  appState.lastStatus = status;
  const triggerActive = triggerIsActive();
  setChip(
    backendState,
    status.backend_running ? "Backend on" : "Backend stopped",
    status.backend_running ? "ok" : "bad",
  );
  const peerCount = Array.isArray(status.peers) ? status.peers.length : 0;
  setChip(peerState, `${peerCount} peer${peerCount === 1 ? "" : "s"}`, peerCount ? "ok" : "warn");
  setChip(
    triggerState,
    triggerActive ? "Scan active" : "Scan stopped",
    triggerActive ? "ok" : "warn",
  );
  setChip(
    inventoryState,
    status.inventory_running ? "Inventory on" : "Inventory stopped",
    status.mismatch_inventory_after_release ? "warn" : status.inventory_running ? "ok" : "warn",
  );

  setMetric("generated_tag_count", formatNumber(status.generated_tag_count));
  setMetric("accepted_scan_count", formatNumber(status.accepted_scan_count));
  setMetric("duplicate_ignored_count", formatNumber(status.duplicate_ignored_count));
  setMetric("current_scan_rate", `${formatNumber(status.current_scan_rate)}/s`);
  setMetric("id_buffer_size", formatNumber(status.id_buffer_size));
  setMetric("mode", String(status.mode || "strict"));
  renderScannerPower(status.scanner_power, status.scanner_power_effect);
  updateScanCones(status.scanner_power_effect);
  renderAggregateProgress(status.aggregate_progress);
  if (status.progress_version !== appState.progressVersion) {
    appState.progressVersion = status.progress_version;
    updateGroupProgress(status.group_progress);
  }
  mismatchBanner.hidden = !status.mismatch_inventory_after_release;
  updateTriggerButton(status);
}

async function setScannerPower(level) {
  if (!Number.isInteger(level) || controls.scannerPowerRequestInFlight) {
    return;
  }
  controls.scannerPowerRequestInFlight = true;
  if (scannerPowerInput) {
    scannerPowerInput.disabled = true;
  }
  try {
    const payload = await postJson("/api/scanner-power", { level });
    setConnection("ok", "Bridge online");
    controls.scannerPowerDirty = false;
    renderStatus(payload.status);
  } catch (error) {
    console.error(error);
    setConnection("warn", "Power sync failed");
    if (appState.lastStatus) {
      controls.scannerPowerDirty = false;
      renderStatus(appState.lastStatus);
    }
  } finally {
    controls.scannerPowerRequestInFlight = false;
    if (scannerPowerInput) {
      scannerPowerInput.disabled = false;
    }
  }
}

function renderScannerPower(levelValue, effect) {
  if (!scannerPowerInput || !scannerPowerValue || !scannerPowerEffect) {
    return;
  }
  const profile = normalizeScannerPowerProfile(effect || profileForPowerLevel(levelValue));
  const level = Number.isFinite(Number(levelValue)) ? Number(levelValue) : profile.level || 5;
  const minLevel = Number(profile.min_level || scannerPowerInput.min || 1);
  const maxLevel = Number(profile.max_level || scannerPowerInput.max || 5);
  scannerPowerInput.min = String(minLevel);
  scannerPowerInput.max = String(maxLevel);
  const label = profile.label || `Level ${level}`;
  const effectLabel = profile.effect || "";
  if (
    !controls.scannerPowerDirty ||
    document.activeElement !== scannerPowerInput ||
    Number(scannerPowerInput.value) === level
  ) {
    scannerPowerInput.value = String(level);
  }
  scannerPowerValue.textContent = `${scannerPowerInput.value} ${label}`;
  scannerPowerEffect.textContent = effectLabel;
  scannerPowerInput.setAttribute("aria-valuetext", `${scannerPowerInput.value} ${label}`);
}

function updateScanCones(effect) {
  if (!appState.scanCones || !effect) {
    return;
  }
  const profile = normalizeScannerPowerProfile(effect);
  const signature = [
    profile.main_range_meters,
    profile.main_cone_degrees,
    profile.side_range_meters,
    profile.side_cone_degrees,
  ].join(":");
  if (signature === appState.scanConeSignature) {
    return;
  }
  appState.scanConeSignature = signature;
  replaceConeGeometry(
    appState.scanCones.main,
    profile.main_range_meters,
    profile.main_cone_degrees,
  );
  replaceConeGeometry(
    appState.scanCones.side,
    profile.side_range_meters,
    profile.side_cone_degrees,
  );
}

function replaceConeGeometry(cone, length, degrees) {
  if (!cone || !Number.isFinite(length) || !Number.isFinite(degrees)) {
    return;
  }
  cone.geometry.dispose();
  cone.geometry = buildConeGeometry(Math.max(0.1, length), Math.max(1, degrees));
}

function triggerIsActive() {
  return Boolean(
    controls.desiredScanActive ||
    controls.localScanActive ||
    controls.syncedScanActive ||
    appState.lastStatus?.scan_active,
  );
}

function canToggleTriggerOn(status) {
  const peerCount = Array.isArray(status?.peers) ? status.peers.length : 0;
  return Boolean(status?.backend_running && peerCount > 0);
}

function updateTriggerButton(status) {
  const active = triggerIsActive();
  const canStart = canToggleTriggerOn(status);
  triggerButton.classList.toggle("is-held", active);
  triggerButton.disabled = !active && !canStart;
  triggerButton.setAttribute("aria-pressed", active ? "true" : "false");
  if (triggerButtonLabel) {
    if (active) {
      triggerButtonLabel.textContent = "Stop Scan";
    } else if (!status?.backend_running) {
      triggerButtonLabel.textContent = "Backend Offline";
    } else if (!canStart) {
      triggerButtonLabel.textContent = "Waiting for Peer";
    } else {
      triggerButtonLabel.textContent = "Start Scan";
    }
  }
}

function renderAggregateProgress(progress) {
  const aggregate = progress || {};
  const scanned = Number(aggregate.scanned_tags || 0);
  const total = Number(aggregate.total_tags || 0);
  const remaining = Number(aggregate.remaining_tags || Math.max(0, total - scanned));
  const completeGroups = Number(aggregate.complete_group_count || 0);
  const partialGroups = Number(aggregate.partial_group_count || 0);
  const totalGroups = Number(aggregate.total_group_count || 0);
  setMetric("progress_scanned_tags", `${formatNumber(scanned)} / ${formatNumber(total)}`);
  setMetric("progress_remaining_tags", formatNumber(remaining));
  setMetric(
    "progress_group_summary",
    `${formatNumber(completeGroups + partialGroups)} / ${formatNumber(totalGroups)}`,
  );
  setMetric("progress_complete_groups", formatNumber(completeGroups));
}

function updateGroupProgress(payload) {
  if (!payload) {
    return;
  }
  const nextProgress = normalizeGroupProgress(payload);
  nextProgress.forEach((entry, groupId) => {
    appState.groupProgress.set(groupId, entry);
  });
  updateProgressVisuals();
}

function updateProgressVisuals() {
  const productMesh = appState.productMesh;
  const overlayGroup = appState.progressOverlayMesh;
  if ((!productMesh && !overlayGroup) || !appState.instanceIndexToGroupId.length) {
    return;
  }
  appState.instanceIndexToGroupId.forEach((groupId, index) => {
    const progress = appState.groupProgress.get(groupId);
    const nextColor = progressColor(progress);
    if (productMesh) {
      productMesh.setColorAt(index, nextColor);
    }
    if (overlayGroup) {
      setProgressOverlayState(overlayGroup, index, appState.renderGroups[index], progress);
    }
  });
  if (productMesh?.instanceColor) {
    productMesh.instanceColor.needsUpdate = true;
  }
  if (overlayGroup?.userData?.meshes) {
    Object.values(overlayGroup.userData.meshes).forEach((mesh) => {
      mesh.instanceMatrix.needsUpdate = true;
    });
  }
}

function updateProductColors() {
  updateProgressVisuals();
}

function setConnection(state, label) {
  connectionPill.textContent = label;
  connectionPill.classList.toggle("is-ok", state === "ok");
  connectionPill.classList.toggle("is-warn", state === "warn");
  connectionPill.classList.toggle("is-bad", state === "bad");
}

function setChip(element, label, state) {
  element.textContent = label;
  element.classList.toggle("is-ok", state === "ok");
  element.classList.toggle("is-warn", state === "warn");
  element.classList.toggle("is-bad", state === "bad");
}

function setMetric(name, value) {
  const element = metricEls.get(name);
  if (element) {
    element.textContent = value;
  }
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function resizeRenderer() {
  const width = canvas.clientWidth || window.innerWidth;
  const height = canvas.clientHeight || window.innerHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / Math.max(1, height);
  camera.updateProjectionMatrix();
}

function computeBounds(groups) {
  const xs = groups.map((group) => group.position.x);
  const zs = groups.map((group) => group.position.z);
  return {
    minX: Math.min(...xs) - 3,
    maxX: Math.max(...xs) + 3,
    minZ: Math.min(...zs) - 3,
    maxZ: Math.max(...zs) + 3,
  };
}

function setStartPose(groups) {
  const bounds = controls.bounds;
  const center = new THREE.Vector3(
    (bounds.minX + bounds.maxX) / 2,
    1.2,
    (bounds.minZ + bounds.maxZ) / 2,
  );
  const start = new THREE.Vector3(bounds.minX + 1.6, 1.55, bounds.minZ + 1.25);
  const direction = center.sub(start);
  controls.yaw = Math.atan2(direction.x, -direction.z);
  controls.pitch = -0.02;
  if (groups.length === 0) {
    controls.yaw = Math.PI;
  }
  camera.position.copy(start);
  camera.rotation.y = controls.yaw;
  camera.rotation.x = controls.pitch;
}

function buildGroupIndex(groups) {
  appState.groupIdToInstanceIndex = new Map();
  appState.instanceIndexToGroupId = [];
  groups.forEach((group, index) => {
    appState.groupIdToInstanceIndex.set(group.group_id, index);
    appState.instanceIndexToGroupId[index] = group.group_id;
  });
}

function normalizeScannerPowerProfiles(payload) {
  const profiles = new Map();
  if (!Array.isArray(payload)) {
    return profiles;
  }
  payload.forEach((entry) => {
    const profile = normalizeScannerPowerProfile(entry);
    if (profile.level) {
      profiles.set(profile.level, profile);
    }
  });
  return profiles;
}

function normalizeScannerPowerProfile(entry) {
  const level = Number(entry?.level || 0);
  return {
    level,
    min_level: Number(entry?.min_level || 1),
    max_level: Number(entry?.max_level || 5),
    label: String(entry?.label || ""),
    effect: String(entry?.effect || ""),
    main_cone_degrees: Number(entry?.main_cone_degrees || 18),
    side_cone_degrees: Number(entry?.side_cone_degrees || 38),
    main_range_meters: Number(entry?.main_range_meters || 3.8),
    side_range_meters: Number(entry?.side_range_meters || 2.2),
  };
}

function profileForPowerLevel(level) {
  return appState.scannerPowerProfiles.get(Number(level)) || null;
}

function normalizeGroupProgress(payload) {
  const progress = new Map();
  if (!payload) {
    return progress;
  }
  if (Array.isArray(payload)) {
    payload.forEach((entry) => {
      if (entry && entry.group_id) {
        progress.set(entry.group_id, normalizeProgressEntry(entry.group_id, entry));
      }
    });
    return progress;
  }
  Object.entries(payload).forEach(([groupId, entry]) => {
    progress.set(groupId, normalizeProgressEntry(groupId, entry));
  });
  return progress;
}

function normalizeProgressEntry(groupId, entry) {
  const total = Number(entry?.total_tags || 0);
  const scanned = Math.min(total, Number(entry?.scanned_tags || 0));
  const remaining = Math.max(0, Number(entry?.remaining_tags ?? total - scanned));
  const progressRatio = total > 0 ? THREE.MathUtils.clamp(scanned / total, 0, 1) : 0;
  return {
    group_id: String(entry?.group_id || groupId),
    total_tags: total,
    scanned_tags: scanned,
    remaining_tags: remaining,
    progress_ratio: Number.isFinite(Number(entry?.progress_ratio))
      ? THREE.MathUtils.clamp(Number(entry.progress_ratio), 0, 1)
      : progressRatio,
    visual_state: String(entry?.visual_state || visualStateFor(scanned, total)),
  };
}

function progressForGroup(group) {
  return (
    appState.groupProgress.get(group.group_id) ||
    normalizeProgressEntry(group.group_id, {
      group_id: group.group_id,
      total_tags: group.tag_count,
      scanned_tags: 0,
    })
  );
}

function progressColor(progress) {
  return progressGradientColor(
    progress,
    progressUnscannedColor,
    progressPartialColor,
    progressCompleteColor,
  );
}

function progressGradientColor(progress, unscannedColor, partialColor, completeColor) {
  const ratio = THREE.MathUtils.clamp(Number(progress?.progress_ratio || 0), 0, 1);
  if (ratio >= 1) {
    color.copy(completeColor);
  } else if (ratio <= 0) {
    color.copy(unscannedColor);
  } else if (ratio < 0.5) {
    color.copy(unscannedColor).lerp(partialColor, ratio / 0.5);
  } else {
    color.copy(partialColor).lerp(completeColor, (ratio - 0.5) / 0.5);
  }
  return color;
}

function updateProgressLabel() {
  if (!progressLabel || !appState.productMesh || !camera) {
    return;
  }
  raycaster.setFromCamera(reticleNdc, camera);
  const hits = raycaster.intersectObject(appState.productMesh, false);
  if (!hits.length || hits[0].instanceId === undefined) {
    progressLabel.hidden = true;
    return;
  }
  const groupId = appState.instanceIndexToGroupId[hits[0].instanceId];
  const progress = appState.groupProgress.get(groupId);
  if (!progress) {
    progressLabel.hidden = true;
    return;
  }
  const percent = Math.round(THREE.MathUtils.clamp(progress.progress_ratio, 0, 1) * 100);
  progressLabel.textContent = `${formatNumber(progress.scanned_tags)}/${formatNumber(
    progress.total_tags,
  )} scanned - ${formatNumber(progress.remaining_tags)} left - ${percent}%`;
  progressLabel.dataset.state = progress.visual_state;
  progressLabel.hidden = false;
}

function visualStateFor(scanned, total) {
  if (total > 0 && scanned >= total) {
    return "complete";
  }
  if (scanned > 0) {
    return "partial";
  }
  return "unscanned";
}

function movementKey(event) {
  if (event.code === "KeyW" || event.code === "ArrowUp") {
    return "forward";
  }
  if (event.code === "KeyS" || event.code === "ArrowDown") {
    return "backward";
  }
  if (event.code === "KeyA" || event.code === "ArrowLeft") {
    return "left";
  }
  if (event.code === "KeyD" || event.code === "ArrowRight") {
    return "right";
  }
  if (event.code === "ShiftLeft" || event.code === "ShiftRight") {
    return "fast";
  }
  return "";
}

function webglAvailable() {
  try {
    const testCanvas = document.createElement("canvas");
    return Boolean(
      window.WebGLRenderingContext &&
        (testCanvas.getContext("webgl2") || testCanvas.getContext("webgl")),
    );
  } catch {
    return false;
  }
}

function isCoarsePointer() {
  return window.matchMedia("(pointer: coarse)").matches || navigator.maxTouchPoints > 0;
}

function showFallback(message) {
  renderFallback.textContent = message;
  renderFallback.hidden = false;
}

function formatNumber(value) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? numeric.toLocaleString() : "0";
}

function roundPose(value) {
  return Math.round(value * 1000) / 1000;
}

appState.applyStatus = renderStatus;
appState.updateProductColors = updateProductColors;
appState.updateProgressVisuals = updateProgressVisuals;
appState.updateProgressLabel = updateProgressLabel;
appState.toggleTrigger = toggleTrigger;
appState.releaseTrigger = releaseTrigger;
appState.setScannerPower = setScannerPower;

window.addEventListener("beforeunload", () => {
  if (statusPoll) {
    window.clearInterval(statusPoll);
  }
  releaseTrigger("unload");
});
