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

function getAuthToken() {
  if (typeof TOKEN !== "undefined" && TOKEN) return TOKEN;
  return localStorage.getItem("sl_token") || "";
}

function showErrorPanel(msg) {
  const panel = $("analytics-error");
  const msgEl = $("analytics-error-msg");
  if (panel && msgEl) {
    msgEl.textContent = msg;
    panel.style.display = "block";
  }
}

function hideErrorPanel() {
  const panel = $("analytics-error");
  if (panel) panel.style.display = "none";
}

function setEmptyState(isEmpty) {
  const banner = $("no-data-banner");
  if (banner) banner.style.display = isEmpty ? "block" : "none";
}

function formatDateInput(d) {
  return d.toISOString().split("T")[0];
}

function setPreset(preset) {
  const btn24 = $("btn-24h");
  const btn7d = $("btn-7d");
  const btn30 = $("btn-30d");
  if (btn24) btn24.classList.toggle("active", preset === "24h");
  if (btn7d) btn7d.classList.toggle("active", preset === "7d");
  if (btn30) btn30.classList.toggle("active", preset === "30d");

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

  const fromInput = $("filter-from");
  const toInput = $("filter-to");
  if (fromInput) fromInput.value = formatDateInput(fromDate);
  if (toInput) toInput.value = toStr;

  loadAnalytics();
}

function applyCustomRange() {
  const btn24 = $("btn-24h");
  const btn7d = $("btn-7d");
  const btn30 = $("btn-30d");
  if (btn24) btn24.classList.remove("active");
  if (btn7d) btn7d.classList.remove("active");
  if (btn30) btn30.classList.remove("active");
  loadAnalytics();
}

async function loadAnalytics() {
  hideErrorPanel();

  const fromInput = $("filter-from");
  const toInput = $("filter-to");
  const from = fromInput ? fromInput.value : "";
  const to = toInput ? toInput.value : "";

  const params = new URLSearchParams();
  if (from) params.append("from_date", from);
  if (to) params.append("to_date", to);

  const token = getAuthToken();
  if (!token) {
    showErrorPanel("AUTHENTICATION REQUIRED // Session token missing. Please log in to view analytics.");
    if (window.toast) toast("AUTH REQUIRED // PLEASE LOGIN");
    return;
  }

  try {
    const res = await fetch(`/api/analytics/summary?${params.toString()}`, {
      headers: { Authorization: "Bearer " + token },
    });

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body && body.detail) detail += ` (${body.detail})`;
      } catch (_) {}
      showErrorPanel(`FAILED TO FETCH ANALYTICS // ${detail}`);
      if (window.toast) toast(`ANALYTICS LOAD FAILED // ${detail}`);
      return;
    }

    const data = await res.json();
    const kpis = data.kpis || {};
    const range = data.range || {};

    const totalViolations = kpis.total_violations || 0;
    const isEmpty = totalViolations === 0;

    setEmptyState(isEmpty);
    renderKPIs(kpis, range);
    renderCharts(data, isEmpty);
  } catch (err) {
    console.error("Analytics fetch/render error:", err);
    showErrorPanel(`ANALYTICS EXCEPTION // ${err.message}`);
    if (window.toast) toast(`ANALYTICS LOAD FAILED // ${err.message}`);
  }
}

function renderKPIs(kpis, range) {
  const total = kpis.total_violations != null ? kpis.total_violations : 0;
  const open = kpis.open_violations != null ? kpis.open_violations : 0;
  const resolved = kpis.resolved_violations != null ? kpis.resolved_violations : 0;
  const resRate = kpis.resolution_rate != null ? kpis.resolution_rate : (total === 0 ? 100.0 : 0);

  const elTotal = $("k-total");
  const elOpen = $("k-open");
  const elResolved = $("k-resolved");
  const elResRate = $("k-res-rate");
  if (elTotal) elTotal.textContent = total.toLocaleString();
  if (elOpen) elOpen.textContent = open.toLocaleString();
  if (elResolved) elResolved.textContent = resolved.toLocaleString();
  if (elResRate) elResRate.textContent = `${resRate}%`;

  const busiest = kpis.busiest_camera || { camera_id: "NONE", count: 0 };
  const elBusiest = $("k-busiest");
  const elBusiestCount = $("k-busiest-count");
  if (elBusiest) elBusiest.textContent = busiest.camera_id || "NONE";
  if (elBusiestCount) elBusiestCount.textContent = (busiest.count || 0).toLocaleString();

  const score = typeof kpis.compliance_score === "number" ? kpis.compliance_score : 100.0;
  const scoreEl = $("k-score");
  if (scoreEl) {
    scoreEl.textContent = `${score.toFixed(1)}%`;
    if (score >= 90) {
      scoreEl.className = "val green";
    } else if (score >= 75) {
      scoreEl.className = "val amber";
    } else {
      scoreEl.className = "val red";
    }
  }

  const formulaEl = $("k-formula");
  if (formulaEl && kpis.compliance_formula) {
    formulaEl.textContent = `FORMULA: ${kpis.compliance_formula}`;
  }

  // Task 2: Compliance Index Context
  const totalHours = (range && range.total_hours != null)
    ? (Number.isInteger(range.total_hours) ? range.total_hours : Math.round(range.total_hours))
    : (kpis.total_hours != null ? kpis.total_hours : "--");
  const dirtyHours = kpis.dirty_hours != null ? kpis.dirty_hours : 0;
  const density = kpis.violations_per_dirty_hour != null ? kpis.violations_per_dirty_hour : 0;

  const ctxHoursEl = $("k-context-hours");
  const ctxDensityEl = $("k-context-density");
  if (ctxHoursEl) ctxHoursEl.textContent = `${dirtyHours} of ${totalHours} monitored hours contained violations`;
  if (ctxDensityEl) ctxDensityEl.textContent = `DENSITY: ${density} violations / dirty hour`;
}

function renderCharts(data, isEmpty) {
  if (typeof Chart === "undefined") {
    throw new Error("Chart.js is not defined in window scope.");
  }

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

  const trends = data.trends || {};
  const breakdown = data.breakdown || {};

  // 2. Trend Line Chart
  const dailyList = Array.isArray(trends.daily) ? trends.daily : [];
  const trendLabels = dailyList.map((d) => d.date);
  const trendValues = dailyList.map((d) => (isEmpty ? 0 : d.count));
  const ctxTrend = $("chart-trend");
  if (ctxTrend) {
    chartTrend = new Chart(ctxTrend, {
      type: "line",
      data: {
        labels: trendLabels.length ? trendLabels : ["NO DATA"],
        datasets: [
          {
            label: "Violations",
            data: trendValues.length ? trendValues : [0],
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
  const hourlyList = Array.isArray(trends.hourly) ? trends.hourly : [];
  const hourlyLabels = hourlyList.map((h) => `${h.hour}:00`);
  const hourlyValues = hourlyList.map((h) => (isEmpty ? 0 : h.count));
  const ctxHourly = $("chart-hourly");
  if (ctxHourly) {
    chartHourly = new Chart(ctxHourly, {
      type: "bar",
      data: {
        labels: hourlyLabels.length ? hourlyLabels : Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`),
        datasets: [
          {
            label: "Incidents",
            data: hourlyValues.length ? hourlyValues : Array(24).fill(0),
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
  const typeList = Array.isArray(breakdown.by_type) ? breakdown.by_type : [];
  const typeLabels = typeList.map((t) => t.type);
  const typeValues = typeList.map((t) => t.count);
  const typeColors = [
    "#ff3b30",
    "#ffb400",
    "#39c4f0",
    "#00e07f",
    "#a277ff",
    "#ff8533",
  ];
  const hasTypeData = !isEmpty && typeLabels.length > 0;
  const ctxType = $("chart-type");
  if (ctxType) {
    chartType = new Chart(ctxType, {
      type: "doughnut",
      data: {
        labels: hasTypeData ? typeLabels : ["NO DATA IN RANGE"],
        datasets: [
          {
            data: hasTypeData ? typeValues : [1],
            backgroundColor: hasTypeData
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
  const camList = Array.isArray(breakdown.by_camera) ? breakdown.by_camera : [];
  const camLabels = camList.map((c) => c.camera_id);
  const camValues = camList.map((c) => c.count);
  const hasCamData = !isEmpty && camLabels.length > 0;
  const ctxCamera = $("chart-camera");
  if (ctxCamera) {
    chartCamera = new Chart(ctxCamera, {
      type: "bar",
      data: {
        labels: hasCamData ? camLabels : ["NO DATA IN RANGE"],
        datasets: [
          {
            label: "Violations",
            data: hasCamData ? camValues : [0],
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

// Global Exception-Safe Initialization
function init() {
  try {
    if (typeof Chart === "undefined") {
      throw new Error("Chart.js engine not loaded. Verify js/chart.umd.js availability.");
    }
    setPreset("7d");
  } catch (err) {
    console.error("Critical error in analytics init:", err);
    showErrorPanel(`INITIALIZATION FAILURE // ${err.message}`);
    if (window.toast) toast(`INIT FAILED // ${err.message}`);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
