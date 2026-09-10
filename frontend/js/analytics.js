// ===== SafetyLens Analytics Controller =====
const $ = (id) => document.getElementById(id);

// Live clock
setInterval(() => {
  const clockEl = $("clock");
  if (clockEl) clockEl.textContent = new Date().toLocaleTimeString("en-GB");
}, 1000);

// Chart references for memory clean-up
let chartTrend = null;
let chartHourly = null;
let chartType = null;
let chartCamera = null;

// Chart.js Theme Defaults
if (window.Chart) {
  Chart.defaults.color = "#6d7c8c";
  Chart.defaults.font.family = "'ShareTechMono', monospace";
  Chart.defaults.borderColor = "rgba(28, 39, 51, 0.8)";
}

function formatDateInput(d) {
  return d.toISOString().split("T")[0];
}

function setPreset(preset) {
  $("btn-24h").classList.toggle("active", preset === "24h");
  $("btn-7d").classList.toggle("active", preset === "7d");
  $("btn-30d").classList.toggle("active", preset === "30d");

  const now = new Date();
  const toStr = formatDateInput(now);
  let fromDate = new Date();

  if (preset === "24h") {
    fromDate.setDate(now.getDate() - 1);
  } else if (preset === "7d") {
    fromDate.setDate(now.getDate() - 6);
  } else if (preset === "30d") {
    fromDate.setDate(now.getDate() - 29);
  }

  $("filter-from").value = formatDateInput(fromDate);
  $("filter-to").value = toStr;

  loadAnalytics();
}

function applyCustomRange() {
  $("btn-24h").classList.remove("active");
  $("btn-7d").classList.remove("active");
  $("btn-30d").classList.remove("active");
  loadAnalytics();
}

async function loadAnalytics() {
  const from = $("filter-from").value;
  const to = $("filter-to").value;

  const params = new URLSearchParams();
  if (from) params.append("from_date", from);
  if (to) params.append("to_date", to);

  try {
    const res = await fetch(`/api/analytics/summary?${params.toString()}`, {
      headers: { Authorization: "Bearer " + TOKEN },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderKPIs(data.kpis);
    renderCharts(data);
  } catch (err) {
    if (window.toast) toast(`ANALYTICS LOAD FAILED // ${err.message}`);
  }
}

function renderKPIs(kpis) {
  $("k-total").textContent = kpis.total_violations.toLocaleString();
  $("k-open").textContent = kpis.open_violations.toLocaleString();
  $("k-resolved").textContent = kpis.resolved_violations.toLocaleString();
  $("k-res-rate").textContent = `${kpis.resolution_rate}%`;

  const busiest = kpis.busiest_camera;
  $("k-busiest").textContent = busiest.camera_id;
  $("k-busiest-count").textContent = busiest.count.toLocaleString();

  const scoreEl = $("k-score");
  scoreEl.textContent = `${kpis.compliance_score.toFixed(1)}%`;
  if (kpis.compliance_score >= 90) {
    scoreEl.className = "val green";
  } else if (kpis.compliance_score >= 75) {
    scoreEl.className = "val amber";
  } else {
    scoreEl.className = "val red";
  }

  if (kpis.compliance_formula) {
    $("k-formula").textContent = `FORMULA: ${kpis.compliance_formula}`;
  }
}

function renderCharts(data) {
  // 1. Destroy existing instances to prevent canvas memory leaks
  if (chartTrend) {
    chartTrend.destroy();
    chartTrend = null;
  }
  if (chartHourly) {
    chartHourly.destroy();
    chartHourly = null;
  }
  if (chartType) {
    chartType.destroy();
    chartType = null;
  }
  if (chartCamera) {
    chartCamera.destroy();
    chartCamera = null;
  }

  // 2. Trend Line Chart
  const trendLabels = data.trends.daily.map((d) => d.date);
  const trendValues = data.trends.daily.map((d) => d.count);
  const ctxTrend = $("chart-trend");
  if (ctxTrend) {
    chartTrend = new Chart(ctxTrend, {
      type: "line",
      data: {
        labels: trendLabels,
        datasets: [
          {
            label: "Violations",
            data: trendValues,
            borderColor: "#ffb400",
            backgroundColor: "rgba(255, 180, 0, 0.08)",
            borderWidth: 2,
            pointBackgroundColor: "#ffb400",
            pointBorderColor: "#0d1218",
            pointRadius: 4,
            pointHoverRadius: 6,
            fill: true,
            tension: 0.25,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#0d1218",
            borderColor: "#ffb400",
            borderWidth: 1,
            titleFont: { family: "'ShareTechMono', monospace" },
            bodyFont: { family: "'ShareTechMono', monospace" },
          },
        },
        scales: {
          x: {
            grid: { color: "rgba(28, 39, 51, 0.6)" },
            ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 },
          },
          y: {
            beginAtZero: true,
            ticks: { stepSize: 1 },
            grid: { color: "rgba(28, 39, 51, 0.6)" },
          },
        },
      },
    });
  }

  // 3. Hourly Bar Chart (24 Hours)
  const hourlyLabels = data.trends.hourly.map((h) => `${h.hour}:00`);
  const hourlyValues = data.trends.hourly.map((h) => h.count);
  const ctxHourly = $("chart-hourly");
  if (ctxHourly) {
    chartHourly = new Chart(ctxHourly, {
      type: "bar",
      data: {
        labels: hourlyLabels,
        datasets: [
          {
            label: "Incidents",
            data: hourlyValues,
            backgroundColor: "#39c4f0",
            borderRadius: 2,
            borderWidth: 0,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#0d1218",
            borderColor: "#39c4f0",
            borderWidth: 1,
            titleFont: { family: "'ShareTechMono', monospace" },
            bodyFont: { family: "'ShareTechMono', monospace" },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 },
          },
          y: {
            beginAtZero: true,
            ticks: { stepSize: 1 },
            grid: { color: "rgba(28, 39, 51, 0.6)" },
          },
        },
      },
    });
  }

  // 4. Type Breakdown Doughnut Chart
  const typeLabels = data.breakdown.by_type.map((t) => t.type);
  const typeValues = data.breakdown.by_type.map((t) => t.count);
  const typeColors = [
    "#ff3b30",
    "#ffb400",
    "#39c4f0",
    "#00e07f",
    "#a277ff",
    "#ff8533",
  ];
  const ctxType = $("chart-type");
  if (ctxType) {
    chartType = new Chart(ctxType, {
      type: "doughnut",
      data: {
        labels: typeLabels.length ? typeLabels : ["NO DATA"],
        datasets: [
          {
            data: typeValues.length ? typeValues : [1],
            backgroundColor: typeValues.length
              ? typeColors.slice(0, typeLabels.length)
              : ["#1c2733"],
            borderColor: "#0d1218",
            borderWidth: 2,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              boxWidth: 12,
              padding: 12,
              font: { size: 11 },
            },
          },
          tooltip: {
            backgroundColor: "#0d1218",
            borderColor: "#ffb400",
            borderWidth: 1,
          },
        },
      },
    });
  }

  // 5. Camera Comparison Bar Chart
  const camLabels = data.breakdown.by_camera.map((c) => c.camera_id);
  const camValues = data.breakdown.by_camera.map((c) => c.count);
  const ctxCamera = $("chart-camera");
  if (ctxCamera) {
    chartCamera = new Chart(ctxCamera, {
      type: "bar",
      data: {
        labels: camLabels.length ? camLabels : ["NO DATA"],
        datasets: [
          {
            label: "Violations",
            data: camValues.length ? camValues : [0],
            backgroundColor: "#00e07f",
            borderRadius: 2,
            borderWidth: 0,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#0d1218",
            borderColor: "#00e07f",
            borderWidth: 1,
            titleFont: { family: "'ShareTechMono', monospace" },
            bodyFont: { family: "'ShareTechMono', monospace" },
          },
        },
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: { stepSize: 1 },
            grid: { color: "rgba(28, 39, 51, 0.6)" },
          },
        },
      },
    });
  }
}

// Initial setup
setPreset("7d");
