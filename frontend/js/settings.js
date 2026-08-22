if (localStorage.getItem("sl_role") !== "admin") location.replace("index.html");
const $ = (id) => document.getElementById(id);

async function load() {
  const r = await fetch("/api/settings", {
    headers: { Authorization: "Bearer " + TOKEN },
  });
  if (!r.ok) return;
  const d = await r.json();

  for (const k of [
    "confidence",
    "negative_confidence",
    "person_conf",
    "gear_conf",
    "cooldown_sec",
    "min_frames",
  ]) {
    const el = $("s-" + k);
    el.value = d.settings[k];
    $("v-" + k).textContent = d.settings[k];
    el.addEventListener("input", () => ($("v-" + k).textContent = el.value));
  }
  $("t-check_vest").classList.toggle("on", d.settings.check_vest);
  $("t-check_vest").addEventListener("click", () =>
    $("t-check_vest").classList.toggle("on"),
  );

  $("s-model").innerHTML = d.models
    .map(
      (m) =>
        `<option value="${m.id}" ${m.id === d.active ? "selected" : ""} ${m.available ? "" : "disabled"}>${m.name}${m.available ? "" : " (Unavailable)"}</option>`,
    )
    .join("");

  if (localStorage.getItem("sl_role") !== "admin") {
    document
      .querySelectorAll("input, select, .switch, #save-btn")
      .forEach((el) => (el.disabled = true));
    $("ro-tag").hidden = false;
  }
}

$("save-btn").addEventListener("click", async () => {
  const payload = {
    confidence: parseFloat($("s-confidence").value),
    negative_confidence: parseFloat($("s-negative_confidence").value),
    person_conf: parseFloat($("s-person_conf").value),
    gear_conf: parseFloat($("s-gear_conf").value),
    cooldown_sec: parseInt($("s-cooldown_sec").value),
    min_frames: parseInt($("s-min_frames").value),
    check_vest: $("t-check_vest").classList.contains("on"),
    model: $("s-model").value,
  };
  const r = await fetch("/api/settings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + TOKEN,
    },
    body: JSON.stringify({ settings: payload }),
  });
  const d = await r.json().catch(() => ({}));
  toast("SETTINGS " + (d.status || "DENIED").toUpperCase());
});

load();
