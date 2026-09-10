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
      .querySelectorAll("input, select, .switch, #save-btn, #test-alert-btn")
      .forEach((el) => (el.disabled = true));
    $("ro-tag").hidden = false;
  }

  const ar = await fetch("/api/settings/alerts", { headers: { Authorization: "Bearer " + TOKEN } });
  if (ar.ok) {
    const alerts = await ar.json();
    $("t-alert_email").classList.toggle("on", alerts.email.enabled);
    $("email-host").value = alerts.email.smtp_host || "";
    $("email-port").value = alerts.email.smtp_port || "";
    $("email-from").value = alerts.email.from_addr || "";
    $("email-to").value = alerts.email.to_addrs || "";
    $("email-user").value = alerts.email.username || "";
    $("email-pass").value = alerts.email.password || "";
    
    $("t-alert_webhook").classList.toggle("on", alerts.webhook.enabled);
    $("webhook-url").value = alerts.webhook.url || "";
    
    toggleAlertOpts();
  }
  
  $("t-alert_email").addEventListener("click", () => { $("t-alert_email").classList.toggle("on"); toggleAlertOpts(); });
  $("t-alert_webhook").addEventListener("click", () => { $("t-alert_webhook").classList.toggle("on"); toggleAlertOpts(); });
}

function toggleAlertOpts() {
  $("email-opts").style.display = $("t-alert_email").classList.contains("on") ? "flex" : "none";
  $("webhook-opts").style.display = $("t-alert_webhook").classList.contains("on") ? "block" : "none";
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

  const alertPayload = {
    email: {
      enabled: $("t-alert_email").classList.contains("on"),
      smtp_host: $("email-host").value,
      smtp_port: parseInt($("email-port").value) || 587,
      from_addr: $("email-from").value,
      to_addrs: $("email-to").value,
      username: $("email-user").value,
      password: $("email-pass").value
    },
    webhook: {
      enabled: $("t-alert_webhook").classList.contains("on"),
      url: $("webhook-url").value
    }
  };
  await fetch("/api/settings/alerts", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
    body: JSON.stringify({ settings: alertPayload })
  });

  toast("SETTINGS " + (d.status || "DENIED").toUpperCase());
});

window.testAlerts = async function() {
  toast("Sending test alerts...");
  const r = await fetch("/api/settings/alerts/test", { method: "POST", headers: { Authorization: "Bearer " + TOKEN } });
  const data = await r.json();
  let msg = "Test results: ";
  if (data.results.email) msg += `Email: ${data.results.email}. `;
  if (data.results.webhook) msg += `Webhook: ${data.results.webhook}. `;
  if (!data.results.email && !data.results.webhook) msg += "No external handlers enabled.";
  toast(msg);
};

load();
