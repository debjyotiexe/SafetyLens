const $ = (id) => document.getElementById(id);
const video = $("webcam"),
  canvas = $("overlay"),
  ctx = canvas.getContext("2d");
const logEl = $("log");

// ---- clock ----
setInterval(() => {
  $("clock").textContent = new Date().toLocaleTimeString("en-GB");
}, 1000);

// ---- audio alarm (autoplay-policy safe, no state gating) ----
let audioOn = true,
  actx = null;
function ensureAudio() {
  if (!actx) {
    try {
      actx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
      actx = null;
    }
  }
  if (actx && actx.state !== "running") actx.resume().catch(() => {});
}
window.addEventListener("pointerdown", ensureAudio);
window.addEventListener("keydown", ensureAudio);

function beep() {
  if (!audioOn) return;
  ensureAudio();
  if (!actx) return;
  const t = actx.currentTime;
  const o = actx.createOscillator(),
    g = actx.createGain();
  o.type = "square";
  o.frequency.setValueAtTime(880, t);
  o.frequency.exponentialRampToValueAtTime(440, t + 0.18);
  g.gain.setValueAtTime(0.08, t);
  g.gain.exponentialRampToValueAtTime(0.0001, t + 0.25);
  o.connect(g).connect(actx.destination);
  o.start(t);
  o.stop(t + 0.26);
}
function testAlarm() {
  ensureAudio();
  setTimeout(beep, 60);
}
function toggleSound(btn) {
  audioOn = !audioOn;
  btn.textContent = audioOn ? "SOUND: ON" : "SOUND: OFF";
  btn.classList.toggle("active", audioOn);
  if (audioOn) testAlarm();
}

// ---- event log ----
function log(src, msg, cls) {
  const row = document.createElement("div");
  row.className = "row " + (cls || "");
  row.textContent = `[${new Date().toLocaleTimeString("en-GB")}] ${src} :: ${msg}`;
  logEl.prepend(row);
  while (logEl.children.length > 60) logEl.removeChild(logEl.lastChild);
}

// ---- input sources ----
function stopCurrent() {
  if (video.srcObject) {
    video.srcObject.getTracks().forEach((t) => t.stop());
    video.srcObject = null;
  }
}
function startWebcam() {
  stopCurrent();
  navigator.mediaDevices
    .getUserMedia({ video: { width: 1280 } })
    .then((s) => {
      video.srcObject = s;
      log("SYS", "Webcam online", "ok");
    })
    .catch(() => log("SYS", "Webcam blocked or missing", "warn"));
}
$("file-input").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (!f) return;
  stopCurrent();
  video.src = URL.createObjectURL(f);
  video.play();
  log("SYS", "Feed loaded: " + f.name, "ok");
});
function startScreen() {
  stopCurrent();
  navigator.mediaDevices.getDisplayMedia({ video: true }).then((s) => {
    video.srcObject = s;
    log("SYS", "Screen share online", "ok");
  });
}

// ---- websocket + telemetry ----
let frames = 0,
  lastViolation = 0;
setInterval(() => {
  $("fps-tag").textContent = frames + " FPS";
  frames = 0;
}, 1000);

const ws = new WebSocket(`ws://${location.host}/ws/stream`);
ws.onopen = () => log("SYS", "Backend link established", "ok");
ws.onclose = () => log("SYS", "BACKEND LINK LOST", "warn");

const grab = document.createElement("canvas");
grab.width = 640;
grab.height = 480;
setInterval(() => {
  if (video.readyState < 2 || ws.readyState !== WebSocket.OPEN) return;
  grab.getContext("2d").drawImage(video, 0, 0, 640, 480);
  grab.toBlob((b) => ws.send(b), "image/jpeg", 0.8);
}, 200);

ws.onmessage = (e) => {
  const d = JSON.parse(e.data);
  frames++;
  $("lat-tag").textContent =
    Math.max(0, Math.round((Date.now() / 1000 - d.ts) * 1000)) + " ms";

  const img = new Image();
  img.onload = () => ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  img.src = "data:image/jpeg;base64," + d.frame;

  $("k-workers").textContent = d.detections.filter(
    (x) => (x.cls === "Person" || x.cls === "person") && x.conf >= 0.5,
  ).length;
  $("k-active").textContent = d.violations.length;

  d.violations.forEach((v) => {
    lastViolation = Date.now();
    log("CAM_01", `${v.type}  conf ${(v.conf * 100).toFixed(1)}%`, "warn");
    beep();
  });
};

// ---- threat level engine ----
setInterval(() => {
  const el = $("threat"),
    dt = Date.now() - lastViolation;
  if (dt < 10000) {
    el.textContent = "CRITICAL";
    el.className = "threat critical";
  } else if (dt < 60000) {
    el.textContent = "ELEVATED";
    el.className = "threat elevated";
  } else {
    el.textContent = "NOMINAL";
    el.className = "threat nominal";
  }
}, 1000);

// ---- snapshot modal ----
$("gallery").addEventListener("click", (e) => {
  const img = e.target.closest("img");
  if (!img) return;
  $("modal-img").src = img.src;
  $("modal").classList.add("open");
});

// ---- charts (fill their boxes fully) ----
Chart.defaults.color = "#6d7c8c";
Chart.defaults.font.family = "'ShareTechMono', monospace";
Chart.defaults.borderColor = "rgba(28,39,51,.8)";

const hourlyChart = new Chart($("chart-hourly"), {
  type: "bar",
  data: {
    labels: [],
    datasets: [{ data: [], backgroundColor: "#ffb400", borderWidth: 0 }],
  },
  options: {
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
  },
});
const typesChart = new Chart($("chart-types"), {
  type: "doughnut",
  data: {
    labels: [],
    datasets: [
      {
        data: [],
        backgroundColor: ["#ff3b30", "#ffb400", "#39c4f0"],
        borderColor: "#0d1218",
      },
    ],
  },
  options: {
    maintainAspectRatio: false,
    plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } },
  },
});

async function refresh() {
  try {
    const s = await (await fetch("/api/stats")).json();
    $("k-today").textContent = s.today;
    $("k-total").textContent = s.total;
    hourlyChart.data.labels = s.hourly.map((h) => h[0] + ":00");
    hourlyChart.data.datasets[0].data = s.hourly.map((h) => h[1]);
    hourlyChart.update("none");
    typesChart.data.labels = s.by_type.map((t) => t[0]);
    typesChart.data.datasets[0].data = s.by_type.map((t) => t[1]);
    typesChart.update("none");
    const snaps = await (await fetch("/api/snapshots")).json();
    $("gallery").innerHTML = snaps
      .map((x) => `<img src="${x.url}" alt="${x.name}">`)
      .join("");
  } catch (e) {}
}
refresh();
setInterval(refresh, 3000);

// ---- admin reset ----
async function resetAll() {
  if (!confirm("RESET all violations, logs and snapshots to zero?")) return;
  const r = await fetch("/api/reset", {
    method: "POST",
    headers: { Authorization: "Bearer " + TOKEN },
  });
  if (!r.ok) {
    log("SYS", "RESET DENIED — admin access required", "warn");
    return;
  }
  logEl.innerHTML = "";
  lastViolation = 0;
  log("SYS", "System reset — all records cleared", "ok");
  refresh();
}

log("SYS", "SafetyLens command center initialized", "ok");
