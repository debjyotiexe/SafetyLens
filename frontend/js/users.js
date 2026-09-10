// ===== SafetyLens: Operator Management =====
(function () {
  const token = localStorage.getItem("sl_token");
  const role = localStorage.getItem("sl_role");

  // Client-side role guard
  if (!token || role !== "admin") {
    location.replace("index.html");
    return;
  }

  const tbody = document.getElementById("users-body");

  function notify(msg) {
    if (typeof toast === "function") {
      toast(msg);
    } else {
      const t = document.createElement("div");
      t.className = "toast";
      t.textContent = msg;
      document.body.appendChild(t);
      setTimeout(() => t.remove(), 2500);
    }
  }

  async function loadUsers() {
    try {
      const res = await fetch("/api/users", {
        headers: { Authorization: "Bearer " + token },
      });
      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          location.replace("login.html");
          return;
        }
        throw new Error("Failed to fetch operators");
      }
      const users = await res.json();
      renderUsers(users);
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--red); padding: 24px;">
            FAILED TO LOAD OPERATORS — ${err.message}
          </td>
        </tr>`;
    }
  }

  function renderUsers(users) {
    if (!users || users.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--muted); padding: 24px;">
            NO OPERATORS REGISTERED
          </td>
        </tr>`;
      return;
    }

    tbody.innerHTML = users
      .map((u) => {
        const isActive = u.is_active === 1;
        const statusBadge = isActive
          ? `<span class="status-badge status-online">ACTIVE</span>`
          : `<span class="status-badge status-error">DISABLED</span>`;

        const actionBtn = isActive
          ? `<button class="btn danger btn-toggle" data-admin onclick="handleToggleActive(${u.id}, '${u.username}')">DISABLE</button>`
          : `<button class="btn btn-toggle" style="border-color: var(--green); color: var(--green);" data-admin onclick="handleToggleActive(${u.id}, '${u.username}')">ENABLE</button>`;

        return `
          <tr data-id="${u.id}">
            <td style="color: var(--muted); font-size: 11px;">#${u.id}</td>
            <td style="font-weight: 700; color: var(--amber);">${escapeHtml(u.username)}</td>
            <td style="color: var(--muted);">${u.email ? escapeHtml(u.email) : "—"}</td>
            <td>
              <select class="role-select" data-admin data-prev="${u.role}" onchange="handleRoleChange(${u.id}, this)">
                <option value="admin" ${u.role === "admin" ? "selected" : ""}>ADMIN</option>
                <option value="viewer" ${u.role === "viewer" ? "selected" : ""}>VIEWER</option>
              </select>
            </td>
            <td>${statusBadge}</td>
            <td data-admin>${actionBtn}</td>
          </tr>
        `;
      })
      .join("");
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  window.handleRoleChange = async function (id, selectEl) {
    const newRole = selectEl.value;
    const prevRole = selectEl.dataset.prev || (newRole === "admin" ? "viewer" : "admin");

    try {
      const res = await fetch(`/api/users/${id}/role`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + token,
        },
        body: JSON.stringify({ role: newRole }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        selectEl.value = prevRole; // Revert
        notify(errData.detail || "ROLE UPDATE FAILED");
        return;
      }

      selectEl.dataset.prev = newRole;
      notify(`OPERATOR #${id} ROLE UPDATED TO ${newRole.toUpperCase()}`);
    } catch (err) {
      selectEl.value = prevRole; // Revert
      notify("NETWORK ERROR — role update failed");
    }
  };

  window.handleToggleActive = async function (id, username) {
    try {
      const res = await fetch(`/api/users/${id}/toggle-active`, {
        method: "POST",
        headers: { Authorization: "Bearer " + token },
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        notify(errData.detail || "STATUS UPDATE FAILED");
        return;
      }

      const data = await res.json();
      const statusText = data.is_active === 1 ? "ACTIVATED" : "DISABLED";
      notify(`OPERATOR ${username.toUpperCase()} ${statusText}`);
      loadUsers(); // Refresh row statuses
    } catch (err) {
      notify("NETWORK ERROR — status update failed");
    }
  };

  loadUsers();
})();
