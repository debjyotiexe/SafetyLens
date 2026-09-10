// ===== SafetyLens Reports Controller =====
const $ = (id) => document.getElementById(id);

// Live clock
setInterval(() => {
  const clockEl = $("clock");
  if (clockEl) clockEl.textContent = new Date().toLocaleTimeString("en-GB");
}, 1000);

function formatDateInput(d) {
  return d.toISOString().split("T")[0];
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

async function loadCameras() {
  try {
    const res = await fetch("/api/cameras", {
      headers: { Authorization: "Bearer " + TOKEN },
    });
    if (res.ok) {
      const cams = await res.json();
      const sel = $("filter-cam");
      sel.innerHTML = '<option value="">ALL CAMERAS</option>';
      cams.forEach((cam) => {
        const opt = document.createElement("option");
        opt.value = cam.id;
        opt.textContent = `${cam.name || cam.id} (${cam.id})`;
        sel.appendChild(opt);
      });
    }
  } catch (e) {}
}

async function generateReport() {
  const from = $("filter-from").value;
  const to = $("filter-to").value;
  const cam = $("filter-cam").value;
  const type = $("filter-type").value;

  const params = new URLSearchParams();
  if (from) params.append("from_date", from);
  if (to) params.append("to_date", to);
  if (cam) params.append("camera", cam);
  if (type) params.append("type", type);

  try {
    const res = await fetch(`/api/reports/generate?${params.toString()}`, {
      headers: { Authorization: "Bearer " + TOKEN },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderReport(data);
    $("report-view").style.display = "block";
    if (window.toast) toast("REPORT GENERATED");
  } catch (err) {
    if (window.toast) toast(`REPORT GENERATION FAILED // ${err.message}`);
  }
}

function renderReport(data) {
  const meta = data.metadata;
  $("rep-range").textContent = `${meta.from_date} ➔ ${meta.to_date}`;
  $("rep-date").textContent = meta.generated_at;
  $("rep-user").textContent = meta.generated_by || "Operator";

  const filters = [];
  if (meta.filters.camera) filters.push(`Camera: ${meta.filters.camera}`);
  if (meta.filters.type) filters.push(`Type: ${meta.filters.type}`);
  $("rep-filters").textContent = filters.length ? filters.join(" | ") : "ALL INCIDENTS (NO RESTRICTIONS)";

  // Summary KPIs
  const s = data.summary;
  $("rep-k-total").textContent = s.total_violations.toLocaleString();
  $("rep-k-open").textContent = s.open_violations.toLocaleString();
  $("rep-k-resolved").textContent = s.resolved_violations.toLocaleString();
  $("rep-k-res-rate").textContent = `${s.resolution_rate}%`;

  const scoreEl = $("rep-k-score");
  scoreEl.textContent = `${s.compliance_score.toFixed(1)}%`;
  if (s.compliance_score >= 90) scoreEl.className = "rep-val green";
  else if (s.compliance_score >= 75) scoreEl.className = "rep-val amber";
  else scoreEl.className = "rep-val red";

  // Table by Type
  const tbodyType = document.querySelector("#rep-table-type tbody");
  tbodyType.innerHTML = "";
  if (!data.by_type || data.by_type.length === 0) {
    tbodyType.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--muted);padding:14px;">NO VIOLATIONS IN RANGE</td></tr>';
  } else {
    data.by_type.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><b>${esc(row.type)}</b></td>
        <td style="text-align: right; font-family: var(--mono);">${row.count.toLocaleString()}</td>
        <td style="text-align: right; font-family: var(--mono); color: var(--amber);">${row.percentage}%</td>
      `;
      tbodyType.appendChild(tr);
    });
  }

  // Table by Camera
  const tbodyCam = document.querySelector("#rep-table-camera tbody");
  tbodyCam.innerHTML = "";
  if (!data.by_camera || data.by_camera.length === 0) {
    tbodyCam.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--muted);padding:14px;">NO VIOLATIONS IN RANGE</td></tr>';
  } else {
    data.by_camera.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><b>${esc(row.camera_id)}</b></td>
        <td style="text-align: right; font-family: var(--mono);">${row.count.toLocaleString()}</td>
        <td style="text-align: right; font-family: var(--mono); color: var(--cyan);">${row.percentage}%</td>
      `;
      tbodyCam.appendChild(tr);
    });
  }

  // Evidence Gallery
  const grid = $("rep-evidence-grid");
  grid.innerHTML = "";
  if (!data.top_evidence || data.top_evidence.length === 0) {
    grid.innerHTML = '<div style="grid-column: 1 / -1; text-align:center; color:var(--muted); padding: 20px;">NO EVIDENCE SNAPSHOTS RECORDED IN THIS WINDOW</div>';
  } else {
    data.top_evidence.forEach((ev) => {
      const card = document.createElement("div");
      card.className = "evidence-card";
      const thumb = ev.snapshot_url
        ? `<img src="${ev.snapshot_url}" alt="Incident #${ev.id}" onclick="showModal('${ev.snapshot_url}')" style="cursor: pointer;" />`
        : '<div style="height:120px;display:flex;align-items:center;justify-content:center;color:var(--muted);">NO SNAPSHOT</div>';

      const statusBadge = ev.status === "resolved" ? "status-online" : "status-error";
      card.innerHTML = `
        ${thumb}
        <div class="evidence-info">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <b>#${ev.id} :: ${esc(ev.type)}</b>
            <span class="status-badge ${statusBadge}">${String(ev.status).toUpperCase()}</span>
          </div>
          <div style="margin-top: 6px; font-size: 11px; color: var(--muted); font-family: var(--mono);">
            CAMERA: <span style="color:var(--text);">${esc(ev.camera_id)}</span> | CONF: <span style="color:var(--amber);">${(ev.confidence * 100).toFixed(0)}%</span>
          </div>
          <div style="font-size: 10px; color: var(--muted); font-family: var(--mono); margin-top: 3px;">
            ${esc(ev.created_at)}
          </div>
        </div>
      `;
      grid.appendChild(card);
    });
  }
}

async function exportReportCSV() {
  const from = $("filter-from").value;
  const to = $("filter-to").value;
  const cam = $("filter-cam").value;
  const type = $("filter-type").value;

  const params = new URLSearchParams();
  if (from) params.append("from_date", from);
  if (to) params.append("to_date", to);
  if (cam) params.append("camera", cam);
  if (type) params.append("type", type);

  try {
    const res = await fetch(`/api/reports/export?${params.toString()}`, {
      headers: { Authorization: "Bearer " + TOKEN },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "safetylens_report.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (window.toast) toast("CSV EXPORT DOWNLOADED");
  } catch (err) {
    if (window.toast) toast(`CSV EXPORT FAILED // ${err.message}`);
  }
}

function printReport() {
  const reportView = $("report-view");
  if (!reportView || reportView.style.display === "none") {
    if (window.toast) toast("GENERATE REPORT BEFORE PRINTING");
    return;
  }
  window.print();
}

function showModal(src) {
  const modal = $("modal");
  const modalImg = $("modal-img");
  if (modal && modalImg) {
    modalImg.src = src;
    modal.classList.add("open");
  }
}

// Initialization: set default 7-day range, load cameras, generate initial report
(function init() {
  const now = new Date();
  const past = new Date();
  past.setDate(now.getDate() - 6);

  $("filter-from").value = formatDateInput(past);
  $("filter-to").value = formatDateInput(now);

  loadCameras().then(() => {
    generateReport();
  });
})();
