let currentPage = 1;
const PAGE_SIZE = 50;

function loadIncidents() {
  const type = document.getElementById("filter-type").value;
  const status = document.getElementById("filter-status").value;
  const cam = document.getElementById("filter-cam").value;
  const from = document.getElementById("filter-from").value;
  const to = document.getElementById("filter-to").value;

  const params = new URLSearchParams({
    page: currentPage,
    limit: PAGE_SIZE
  });
  if (type) params.append("type", type);
  if (status) params.append("status", status);
  if (cam) params.append("camera", cam);
  if (from) params.append("from_date", from + "T00:00:00");
  if (to) params.append("to_date", to + "T23:59:59");

  fetch(`/api/incidents?${params.toString()}`, { headers: { Authorization: "Bearer " + TOKEN } })
    .then(r => {
      if (!r.ok) throw r.status;
      return r.json();
    })
    .then(data => {
      renderTable(data.incidents);
      document.getElementById("page-info").textContent = `PAGE ${data.page} / ${data.pages || 1}`;
    })
    .catch(err => {
      renderTable([]);
      toast(`INCIDENTS LOAD FAILED // HTTP ${err}`);
    });
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderTable(incidents) {
  const tbody = document.querySelector("#incident-table tbody");
  tbody.innerHTML = "";
  const isAdmin = localStorage.getItem('sl_role') === 'admin';
  
  if (!Array.isArray(incidents) || incidents.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:24px;">NO INCIDENTS LOGGED</td></tr>`;
    return;
  }

  for (const inc of incidents) {
    const tr = document.createElement("tr");
    
    let statusClass = inc.status === "resolved" ? "status-online" : "status-error";
    
    let actions = "";
    if (isAdmin) {
      if (inc.status !== "resolved") {
        actions = `<button class="btn" onclick="resolveInc(${inc.id})">RESOLVE</button>`;
      } else {
        actions = `<span style="font-size:10px; color:var(--muted)">BY ${esc(inc.resolved_by)}</span>`;
      }
    }

    let thumb = inc.snapshot ? `<img class="cam-thumb" src="/${inc.snapshot}" onclick="showModal('/${inc.snapshot}')" style="cursor:pointer;" />` : "-";

    const date = inc.created_at ? new Date(inc.created_at.replace(" ", "T")).toLocaleString() : "-";

    tr.innerHTML = `
      <td>${inc.id}</td>
      <td>${esc(inc.type)}</td>
      <td>${esc(inc.camera_id)}</td>
      <td>${Number(inc.confidence).toFixed(2)}</td>
      <td>${thumb}</td>
      <td><span class="status-badge ${statusClass}">${String(inc.status).toUpperCase()}</span></td>
      <td style="font-size: 11px;">${date}</td>
      ${isAdmin ? `<td>${actions}</td>` : ""}
    `;
    tbody.appendChild(tr);
  }
}

function resolveInc(id) {
  fetch(`/api/incidents/${id}/resolve`, {
    method: "POST",
    headers: { Authorization: "Bearer " + TOKEN }
  }).then(r => {
    if (r.ok) {
      toast("Incident resolved");
      loadIncidents();
    } else {
      toast(`RESOLVE FAILED // HTTP ${r.status}`);
    }
  });
}

function applyFilters() {
  currentPage = 1;
  loadIncidents();
}

function prevPage() {
  if (currentPage > 1) {
    currentPage--;
    loadIncidents();
  }
}

function nextPage() {
  currentPage++;
  loadIncidents();
}

function exportCSV() {
  const type = document.getElementById("filter-type").value;
  const status = document.getElementById("filter-status").value;
  const cam = document.getElementById("filter-cam").value;
  const from = document.getElementById("filter-from").value;
  const to = document.getElementById("filter-to").value;

  const params = new URLSearchParams();
  if (type) params.append("type", type);
  if (status) params.append("status", status);
  if (cam) params.append("camera", cam);
  if (from) params.append("from_date", from + "T00:00:00");
  if (to) params.append("to_date", to + "T23:59:59");

  fetch(`/api/incidents/export?${params.toString()}`, { headers: { Authorization: "Bearer " + TOKEN } })
    .then(r => {
      if (!r.ok) throw r.status;
      return r.blob();
    })
    .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "incidents.csv";
        a.click();
        URL.revokeObjectURL(url);
    })
    .catch(status => toast(`EXPORT FAILED // HTTP ${status}`));
}

function showModal(src) {
  const modal = document.getElementById('modal');
  document.getElementById('modal-img').src = src;
  modal.classList.add('open');
}

loadIncidents();
