// ===== SafetyLens shell: auth guard + sidebar + role gating =====
const TOKEN = localStorage.getItem("sl_token");
if (!TOKEN) location.replace("login.html");

fetch("/api/me", { headers: { Authorization: "Bearer " + TOKEN } })
  .then((r) => {
    if (!r.ok) throw 0;
    return r.json();
  })
  .then(buildShell)
  .catch(() => {
    localStorage.clear();
    location.replace("login.html");
  });

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

function buildShell(me) {
  const page = document.body.dataset.page || "command";

  const items = [
    ["command", "COMMAND", "index.html"],
    ...(me.role === "admin" ? [["settings", "SETTINGS", "settings.html"]] : []),
  ];
  const soon = ["INCIDENTS", "CAMERAS", "ZONES", "REPORTS", "ANALYTICS"];

  const nav = document.createElement("aside");
  nav.className = "sidebar";
  nav.innerHTML = `
        ${items
          .map(
            ([id, label, href]) =>
              `<a class="side-item ${page === id ? "active" : ""}" href="${href}">▸ ${label}</a>`,
          )
          .join("")}
        ${soon
          .map(
            (s) =>
              `<a class="side-item soon" href="#" data-soon="${s}">▸ ${s}<em>SOON</em></a>`,
          )
          .join("")}
        <div class="side-user">
            ${me.username} <b>// ${me.role.toUpperCase()}</b>
            <button class="btn danger" onclick="localStorage.clear();location.replace('login.html')">LOGOUT</button>
        </div>`;
  document.body.prepend(nav);
  document.body.classList.add("shelled");

  nav.querySelectorAll("[data-soon]").forEach((a) =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      toast(`MODULE "${a.dataset.soon}" OFFLINE — SPRINT B+`);
    }),
  );

  if (me.role !== "admin") {
    document.querySelectorAll("[data-admin]").forEach((el) => el.remove());
  }
}
