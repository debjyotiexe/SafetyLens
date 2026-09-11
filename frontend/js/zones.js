// ===== SafetyLens Geofencing Zones Controller =====
const canvas = document.getElementById("zone-canvas");
const ctx = canvas.getContext("2d");
const cameraSelect = document.getElementById("camera-select");
const formPanel = document.getElementById("zone-form-panel");
const zoneNameInput = document.getElementById("zone-name");
const zoneReqSelect = document.getElementById("zone-req");
const canvasStatus = document.getElementById("canvas-status");
const coordDisplay = document.getElementById("coord-display");
const zoneCountEl = document.getElementById("zone-count");
const cancelBtn = document.getElementById("btn-cancel-draw");
const saveZoneLeftBtn = document.getElementById("btn-save-zone-left");

let selectedCameraId = null;
let currentSnapshotBlobUrl = null;
let currentSnapshotImg = null;
let hasSnapshot = false;
let configuredZones = [];

// Drawing State Machine
let isDrawing = false;
let isPolygonClosed = false;
let currentPoints = []; // Array of [normX, normY]
let currentMouseNorm = null; // [normX, normY]

const ZONE_PALETTE = {
  RESTRICTED: { stroke: "#ff3b30", fill: "rgba(255, 59, 48, 0.20)", label: "RESTRICTED" },
  HELMET:     { stroke: "#ffb400", fill: "rgba(255, 180, 0, 0.18)", label: "HELMET" },
  VEST:       { stroke: "#ffb400", fill: "rgba(255, 180, 0, 0.18)", label: "VEST" },
  ANY_PPE:    { stroke: "#ffb400", fill: "rgba(255, 180, 0, 0.18)", label: "ANY_PPE" },
  GLOVES:     { stroke: "#39c4f0", fill: "rgba(57, 196, 240, 0.18)", label: "GLOVES" },
  BOOTS:      { stroke: "#39c4f0", fill: "rgba(57, 196, 240, 0.18)", label: "BOOTS" },
  GOGGLES:    { stroke: "#39c4f0", fill: "rgba(57, 196, 240, 0.18)", label: "GOGGLES" }
};

function esc(str) {
  return String(str == null ? "" : str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// -------------------------------------------------------------
// Initialization & Camera Selection
// -------------------------------------------------------------
async function init() {
  await loadCameraDropdown();
  setupCanvasListeners();
  renderCanvas();
}

async function loadCameraDropdown() {
  try {
    const res = await fetch("/api/cameras", {
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw res.status;
    const cameras = await res.json();

    cameraSelect.innerHTML = "";
    if (!cameras || cameras.length === 0) {
      cameraSelect.innerHTML = `<option value="">NO REGISTERED CAMERAS</option>`;
      return;
    }

    cameras.forEach((cam) => {
      const opt = document.createElement("option");
      opt.value = cam.id;
      opt.textContent = `${cam.name} [${cam.id}] (${cam.status.toUpperCase()})`;
      cameraSelect.appendChild(opt);
    });

    // Auto-select first camera or previously selected
    if (selectedCameraId && cameras.some(c => c.id === selectedCameraId)) {
      cameraSelect.value = selectedCameraId;
    } else {
      selectedCameraId = cameras[0].id;
      cameraSelect.value = selectedCameraId;
    }

    onCameraChange();
  } catch (err) {
    toast("Failed to load camera list");
  }
}

cameraSelect.addEventListener("change", () => {
  selectedCameraId = cameraSelect.value;
  cancelDrawing();
  onCameraChange();
});

async function onCameraChange() {
  if (!selectedCameraId) return;
  await Promise.all([refreshSnapshot(), loadZones()]);
}

// -------------------------------------------------------------
// Snapshot Fetching
// -------------------------------------------------------------
async function refreshSnapshot() {
  if (!selectedCameraId) return;
  canvasStatus.textContent = "FETCHING CAMERA SNAPSHOT...";

  try {
    const res = await fetch(`/api/cameras/${selectedCameraId}/snapshot`, {
      headers: { Authorization: "Bearer " + TOKEN }
    });

    if (res.ok) {
      const blob = await res.blob();
      if (currentSnapshotBlobUrl) URL.revokeObjectURL(currentSnapshotBlobUrl);
      currentSnapshotBlobUrl = URL.createObjectURL(blob);

      const img = new Image();
      img.onload = () => {
        currentSnapshotImg = img;
        hasSnapshot = true;
        canvasStatus.textContent = "STREAM READY // CLICK TO DRAW POLYGON VERTICES";
        renderCanvas();
      };
      img.src = currentSnapshotBlobUrl;
    } else {
      // 404 or offline: fallback to synthetic calibration grid
      hasSnapshot = false;
      currentSnapshotImg = null;
      canvasStatus.textContent = "NO SIGNAL // SYNTHETIC CALIBRATION GRID READY";
      renderCanvas();
    }
  } catch (e) {
    hasSnapshot = false;
    currentSnapshotImg = null;
    canvasStatus.textContent = "NO SIGNAL // SYNTHETIC CALIBRATION GRID READY";
    renderCanvas();
  }
}

// -------------------------------------------------------------
// Zone CRUD
// -------------------------------------------------------------
async function loadZones() {
  if (!selectedCameraId) return;
  try {
    const res = await fetch(`/api/zones?camera=${encodeURIComponent(selectedCameraId)}`, {
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw res.status;
    configuredZones = await res.json();
    renderZonesTable();
    renderCanvas();
  } catch (e) {
    toast("Error loading zones");
  }
}

function renderZonesTable() {
  const tbody = document.querySelector("#zones-table tbody");
  tbody.innerHTML = "";
  zoneCountEl.textContent = `${configuredZones.length} ZONE${configuredZones.length === 1 ? "" : "S"}`;

  if (configuredZones.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:16px;">NO GEOFENCED ZONES CONFIGURED</td></tr>`;
    return;
  }

  configuredZones.forEach((z) => {
    const tr = document.createElement("tr");

    let badgeClass = "badge-helmet";
    if (z.requirement === "RESTRICTED") badgeClass = "badge-restricted";
    else if (z.requirement === "HELMET") badgeClass = "badge-helmet";
    else if (z.requirement === "VEST") badgeClass = "badge-vest";
    else if (z.requirement === "ANY_PPE") badgeClass = "badge-any_ppe";
    else if (z.requirement === "GLOVES") badgeClass = "badge-gloves";
    else if (z.requirement === "BOOTS") badgeClass = "badge-boots";
    else if (z.requirement === "GOGGLES") badgeClass = "badge-goggles";

    const enabledLabel = z.enabled ? "ACTIVE" : "OFFLINE";
    const statusClass = z.enabled ? "status-online" : "status-offline";

    tr.innerHTML = `
      <td><b>${esc(z.name)}</b></td>
      <td><span class="badge-req ${badgeClass}">${esc(z.requirement)}</span></td>
      <td><span class="status-badge ${statusClass}">${enabledLabel}</span></td>
      <td data-admin>
        <div style="display:flex;gap:4px;">
          <button class="btn ${z.enabled ? "" : "active"}" onclick="toggleZone(${z.id})">
            ${z.enabled ? "DISABLE" : "ENABLE"}
          </button>
          <button class="btn danger" onclick="deleteZone(${z.id})">DELETE</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function toggleZone(zoneId) {
  try {
    const res = await fetch(`/api/zones/${zoneId}/toggle`, {
      method: "POST",
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw res.status;
    toast("Zone status updated");
    await loadZones();
  } catch (e) {
    toast("Failed to toggle zone");
  }
}

async function deleteZone(zoneId) {
  if (!confirm("Are you sure you want to delete this zone?")) return;
  try {
    const res = await fetch(`/api/zones/${zoneId}`, {
      method: "DELETE",
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw res.status;
    toast("Zone deleted");
    await loadZones();
  } catch (e) {
    toast("Failed to delete zone");
  }
}

async function saveCurrentZone() {
  const name = zoneNameInput.value.trim();
  const req = zoneReqSelect.value;

  if (!name) {
    toast("Please enter a zone name");
    zoneNameInput.focus();
    return;
  }

  if (currentPoints.length < 3) {
    toast("Polygon must contain at least 3 vertices");
    return;
  }

  try {
    const payload = {
      camera_id: selectedCameraId,
      name: name,
      points: currentPoints,
      requirement: req
    };

    const res = await fetch("/api/zones", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + TOKEN
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      toast(data.detail || "Error creating zone");
      return;
    }

    toast(`Zone "${name}" saved`);
    cancelDrawing();
    await loadZones();
  } catch (e) {
    toast("Network error creating zone");
  }
}

// -------------------------------------------------------------
// Canvas Drawing & State Machine
// -------------------------------------------------------------
function getCanvasNormalizedCoord(e) {
  const rect = canvas.getBoundingClientRect();
  const normX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const normY = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
  return [normX, normY];
}

function setupCanvasListeners() {
  canvas.addEventListener("mousemove", (e) => {
    const [nx, ny] = getCanvasNormalizedCoord(e);
    coordDisplay.textContent = `CURSOR: [${nx.toFixed(3)}, ${ny.toFixed(3)}]`;

    if (isDrawing && !isPolygonClosed) {
      currentMouseNorm = [nx, ny];
      renderCanvas();
    }
  });

  canvas.addEventListener("click", (e) => {
    if (!selectedCameraId) {
      toast("Please select a camera first");
      return;
    }

    if (isPolygonClosed) {
      // If already closed, clicking again resets and starts fresh
      cancelDrawing();
    }

    const [nx, ny] = getCanvasNormalizedCoord(e);

    // Prevent duplicate points if clicking rapidly
    if (currentPoints.length > 0) {
      const last = currentPoints[currentPoints.length - 1];
      const dist = Math.hypot(nx - last[0], ny - last[1]);
      if (dist < 0.005) return;
    }

    currentPoints.push([nx, ny]);
    isDrawing = true;
    cancelBtn.style.display = "inline-block";
    canvasStatus.textContent = `POINT ${currentPoints.length} ADDED &middot; DOUBLE-CLICK OR ENTER TO CLOSE`;
    renderCanvas();
  });

  canvas.addEventListener("dblclick", (e) => {
    e.preventDefault();
    closePolygon();
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      closePolygon();
    } else if (e.key === "Escape") {
      cancelDrawing();
    }
  });
}

function closePolygon() {
  if (currentPoints.length < 3) {
    if (currentPoints.length > 0) toast("Need at least 3 points to close polygon");
    return;
  }

  isDrawing = false;
  isPolygonClosed = true;
  currentMouseNorm = null;
  formPanel.style.display = "block";
  if (saveZoneLeftBtn) saveZoneLeftBtn.style.display = "inline-block";
  zoneNameInput.focus();
  canvasStatus.textContent = "POLYGON CLOSED // SPECIFY NAME AND REQUIREMENT ON RIGHT";
  renderCanvas();
}

function cancelDrawing() {
  isDrawing = false;
  isPolygonClosed = false;
  currentPoints = [];
  currentMouseNorm = null;
  formPanel.style.display = "none";
  cancelBtn.style.display = "none";
  if (saveZoneLeftBtn) saveZoneLeftBtn.style.display = "none";
  zoneNameInput.value = "";
  canvasStatus.textContent = hasSnapshot
    ? "STREAM READY // CLICK TO DRAW POLYGON VERTICES"
    : "NO SIGNAL // SYNTHETIC CALIBRATION GRID READY";
  renderCanvas();
}

// -------------------------------------------------------------
// Canvas Rendering Pipeline
// -------------------------------------------------------------
function renderCanvas() {
  const cw = canvas.width;
  const ch = canvas.height;

  ctx.clearRect(0, 0, cw, ch);

  // 1. Draw Background (Snapshot or Synthetic Grid)
  if (hasSnapshot && currentSnapshotImg) {
    ctx.drawImage(currentSnapshotImg, 0, 0, cw, ch);
  } else {
    drawSyntheticGrid(cw, ch);
  }

  // 2. Draw Configured Zones for this camera
  configuredZones.forEach((zone) => {
    if (!zone.points || zone.points.length < 3) return;

    const style = ZONE_PALETTE[zone.requirement] || ZONE_PALETTE.ANY_PPE;
    const pts = zone.points.map(([x, y]) => [x * cw, y * ch]);

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i][0], pts[i][1]);
    }
    ctx.closePath();

    // Fill
    ctx.fillStyle = zone.enabled ? style.fill : "rgba(100, 110, 120, 0.12)";
    ctx.fill();

    // Outline
    ctx.strokeStyle = zone.enabled ? style.stroke : "#6d7c8c";
    ctx.lineWidth = zone.enabled ? 2 : 1;
    if (!zone.enabled) ctx.setLineDash([4, 4]);
    ctx.stroke();

    // Badge label
    const lx = pts[0][0];
    const ly = pts[0][1];
    ctx.font = "bold 11px 'ShareTechMono', monospace";
    const labelText = `[${zone.requirement}] ${zone.name}`;
    const tm = ctx.measureText(labelText);
    const tw = tm.width;

    ctx.fillStyle = "#0d1218";
    ctx.fillRect(lx, Math.max(0, ly - 18), tw + 8, 16);
    ctx.strokeStyle = zone.enabled ? style.stroke : "#6d7c8c";
    ctx.strokeRect(lx, Math.max(0, ly - 18), tw + 8, 16);

    ctx.fillStyle = zone.enabled ? style.stroke : "#6d7c8c";
    ctx.fillText(labelText, lx + 4, Math.max(12, ly - 6));
    ctx.restore();
  });

  // 3. Draw In-Progress Polygon
  if (currentPoints.length > 0) {
    ctx.save();
    const pixelPts = currentPoints.map(([x, y]) => [x * cw, y * ch]);

    ctx.beginPath();
    ctx.moveTo(pixelPts[0][0], pixelPts[0][1]);
    for (let i = 1; i < pixelPts.length; i++) {
      ctx.lineTo(pixelPts[i][0], pixelPts[i][1]);
    }

    if (isPolygonClosed) {
      ctx.closePath();
      ctx.fillStyle = "rgba(255, 180, 0, 0.25)";
      ctx.fill();
    } else if (currentMouseNorm) {
      ctx.lineTo(currentMouseNorm[0] * cw, currentMouseNorm[1] * ch);
    }

    ctx.strokeStyle = "#ffb400";
    ctx.lineWidth = 2;
    ctx.setLineDash(isPolygonClosed ? [] : [6, 4]);
    ctx.stroke();

    // Draw vertex circles
    pixelPts.forEach(([px, py], idx) => {
      ctx.beginPath();
      ctx.arc(px, py, 4, 0, Math.PI * 2);
      ctx.fillStyle = idx === 0 ? "#00e07f" : "#ffb400";
      ctx.fill();
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 1;
      ctx.setLineDash([]);
      ctx.stroke();
    });

    ctx.restore();
  }
}

function drawSyntheticGrid(w, h) {
  ctx.save();
  ctx.fillStyle = "#07090c";
  ctx.fillRect(0, 0, w, h);

  // Fine grid lines
  ctx.strokeStyle = "rgba(28, 39, 51, 0.7)";
  ctx.lineWidth = 1;
  const gridSize = 40;

  for (let x = 0; x <= w; x += gridSize) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  for (let y = 0; y <= h; y += gridSize) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  // Crosshairs in center
  ctx.strokeStyle = "rgba(57, 196, 240, 0.4)";
  ctx.beginPath();
  ctx.moveTo(w / 2 - 20, h / 2);
  ctx.lineTo(w / 2 + 20, h / 2);
  ctx.moveTo(w / 2, h / 2 - 20);
  ctx.lineTo(w / 2, h / 2 + 20);
  ctx.stroke();

  // Watermark text
  ctx.font = "14px 'ShareTechMono', monospace";
  ctx.fillStyle = "rgba(109, 124, 140, 0.8)";
  ctx.textAlign = "center";
  ctx.fillText("NO SIGNAL - DRAWING ON CALIBRATION GRID", w / 2, h / 2 - 28);
  ctx.font = "11px 'ShareTechMono', monospace";
  ctx.fillText("POLYGONS ARE NORMALIZED [0.0, 1.0] AND PRESERVED ACROSS RESOLUTIONS", w / 2, h / 2 + 36);

  ctx.restore();
}

// Start
init();
