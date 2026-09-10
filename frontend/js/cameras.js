let pollInterval;
const snapFails = {};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function loadCameras() {
  fetch("/api/cameras", { headers: { Authorization: "Bearer " + TOKEN } })
    .then(r => {
      if (!r.ok) throw r.status;
      return r.json();
    })
    .then(renderTable)
    .then(pollThumbnails); // initial fetch
}

function renderTable(cameras) {
  const tbody = document.querySelector("#cam-table tbody");
  tbody.innerHTML = "";
  const isAdmin = localStorage.getItem('sl_role') === 'admin';
  
  for (const cam of cameras) {
    const tr = document.createElement("tr");
    
    let statusClass = "status-offline";
    if (cam.status === "online" || cam.status === "starting") statusClass = "status-online";
    else if (cam.status === "error") statusClass = "status-error";

    let actions = "";
    if (isAdmin) {
      actions = `
        <button class="btn" onclick="actCam('${cam.id}', 'start')">START</button>
        <button class="btn danger" onclick="actCam('${cam.id}', 'stop')">STOP</button>
        <button class="btn danger" onclick="deleteCam('${cam.id}')">DELETE</button>
      `;
    }

    let thumb = "";
    if (cam.status === "online" || cam.status === "starting") {
      thumb = `<img class="cam-thumb" data-cam-id="${cam.id}" src="" alt="Live" />`;
    } else {
      thumb = `<div class="cam-thumb" style="background:#000;display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--muted)">NO SIGNAL</div>`;
      delete snapFails[cam.id];
    }

    const errLine = cam.status === "error" && cam.error_msg
      ? `<div class="cam-err">${esc(cam.error_msg)}</div>`
      : "";

    tr.innerHTML = `
      <td>${cam.id}</td>
      <td>${esc(cam.name)}</td>
      <td>${cam.type}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(cam.uri)}">${esc(cam.uri)}</td>
      <td><span class="status-badge ${statusClass}">${String(cam.status).toUpperCase()}</span>${errLine}</td>
      ${isAdmin ? `<td><div style="display:flex;gap:4px;">${actions}</div></td>` : ""}
      <td>${thumb}</td>
    `;
    tbody.appendChild(tr);
  }
}

function noSignalThumb(id, lastUrl) {
  const imgs = document.querySelectorAll(`img.cam-thumb[data-cam-id="${id}"]`);
  imgs.forEach(img => {
    if (lastUrl && img.dataset.lastUrl) URL.revokeObjectURL(img.dataset.lastUrl);
    img.outerHTML = `<div class="cam-thumb" style="background:#000;display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--muted)">NO SIGNAL</div>`;
  });
}

function addCamera() {
  const name = document.getElementById("cam-name").value;
  const type = document.getElementById("cam-type").value;
  const uri = document.getElementById("cam-uri").value;
  if (!name || !uri) return toast("Missing fields");

  fetch("/api/cameras", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
    body: JSON.stringify({ name, type, uri })
  }).then(r => r.json().then(d => ({ ok: r.ok, d }))).then(({ ok, d }) => {
    if (!ok) {
      toast((d && d.detail) || "Error adding camera");
      return;
    }
    toast("Camera added");
    document.getElementById("cam-name").value = "";
    document.getElementById("cam-uri").value = "";
    loadCameras();
  });
}

function actCam(id, action) {
  fetch(`/api/cameras/${id}/${action}`, {
    method: "POST",
    headers: { Authorization: "Bearer " + TOKEN }
  }).then(() => {
    toast(`Camera ${action}ed`);
    loadCameras();
  });
}

function deleteCam(id) {
  if(!confirm("Delete camera?")) return;
  fetch(`/api/cameras/${id}`, {
    method: "DELETE",
    headers: { Authorization: "Bearer " + TOKEN }
  }).then(() => {
    toast("Camera deleted");
    loadCameras();
  });
}

const SNAPSHOT_MAX_404 = 3;

function pollThumbnails() {
  // Only img.cam-thumb elements exist for cameras whose status is online/starting;
  // error/offline rows render a static NO SIGNAL placeholder instead.
  const imgs = document.querySelectorAll("img.cam-thumb");
  imgs.forEach(img => {
    const id = img.dataset.camId;
    fetch(`/api/cameras/${id}/snapshot`, { headers: { Authorization: "Bearer " + TOKEN } })
      .then(r => {
        if (!r.ok) throw r.status;
        return r.blob();
      })
      .then(blob => {
        snapFails[id] = 0;
        if (!document.body.contains(img)) return;
        if (img.dataset.lastUrl) URL.revokeObjectURL(img.dataset.lastUrl);
        const url = URL.createObjectURL(blob);
        img.dataset.lastUrl = url;
        img.src = url;
      })
      .catch(status => {
        if (status === 404 || status === 0) {
          snapFails[id] = (snapFails[id] || 0) + 1;
          if (snapFails[id] >= SNAPSHOT_MAX_404) {
            noSignalThumb(id, true);
            toast(`CAM ${id} // NO SIGNAL`);
          }
        }
      });
  });
}

loadCameras();
pollInterval = setInterval(pollThumbnails, 2000);
