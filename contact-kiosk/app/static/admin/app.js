(() => {
  "use strict";

  // Always send/receive the session cookie on same-origin requests. Some
  // older WebKit/Chromium builds default fetch()'s `credentials` option to
  // "omit" rather than the modern spec default of "same-origin" - without
  // this, a login can succeed and the cookie comes back in the response,
  // but the browser never stores it, so the very next request looks
  // unauthenticated.
  function apiFetch(url, options = {}) {
    return fetch(url, { ...options, credentials: "same-origin" });
  }

  const loginView = document.getElementById("view-login");
  const mainView = document.getElementById("view-main");

  // Visibility is set directly via style.display, not a CSS class. A
  // previous version of this file used a `.view.active` class toggle, and
  // a separate ID-selector CSS rule ended up permanently overriding it
  // (ID selectors always beat class selectors, regardless of source
  // order) - the login screen was stuck visible no matter what the JS
  // did. Setting style.display directly here can't be out-specificity'd
  // by any stylesheet rule, so that failure mode isn't possible anymore.
  function showLogin() {
    loginView.style.display = "flex";
    mainView.style.display = "none";
  }
  function showMain() {
    loginView.style.display = "none";
    mainView.style.display = "block";
  }

  function showModal(overlay) { overlay.classList.add("active"); }
  function hideModal(overlay) { overlay.classList.remove("active"); }

  const editOverlay = document.getElementById("edit-modal-overlay");
  const settingsOverlay = document.getElementById("settings-modal-overlay");

  let currentStatus = "pending";
  let editingContactId = null;

  // --- Login ---
  document.getElementById("login-btn").addEventListener("click", login);
  document.getElementById("login-pin").addEventListener("keydown", (e) => {
    if (e.key === "Enter") login();
  });

  async function login() {
    const pin = document.getElementById("login-pin").value;
    const errorEl = document.getElementById("login-error");
    errorEl.hidden = true;
    try {
      const res = await apiFetch("/api/admin/login", {
        method: "POST",
        body: new URLSearchParams({ pin }),
      });
      if (res.ok) {
        showMain();
        loadContacts();
      } else {
        errorEl.textContent = "Incorrect PIN.";
        errorEl.hidden = false;
      }
    } catch (err) {
      console.error("login() failed:", err);
      errorEl.textContent = "Could not reach the server. Please try again.";
      errorEl.hidden = false;
    }
  }

  document.getElementById("open-kiosk").addEventListener("click", async () => {
    await apiFetch("/api/admin/logout", { method: "POST" });
    
  });

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await apiFetch("/api/admin/logout", { method: "POST" });
    showLogin();
  });

  // --- Tabs ---
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      currentStatus = tab.dataset.status;
      loadContacts();
    });
  });

  // --- Load + render contacts ---
  async function loadContacts() {
    const listEl = document.getElementById("contact-list");
    try {
      const res = await apiFetch(`/api/admin/contacts?status_filter=${currentStatus}`);
      if (res.status === 401) { showLogin(); return; }
      const contacts = await res.json();

      if (contacts.length === 0) {
        listEl.innerHTML = `<p class="empty-state">No ${currentStatus === "all" ? "" : currentStatus} entries.</p>`;
        return;
      }

      listEl.innerHTML = contacts.map(renderCard).join("");

      listEl.querySelectorAll("[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => handleAction(btn.dataset.action, Number(btn.dataset.id)));
      });
    } catch (err) {
      console.error("loadContacts() failed:", err);
      listEl.innerHTML = `<p class="empty-state">Could not load contacts (see console for details).</p>`;
    }
  }

  function renderCard(c) {
    const photo = c.photo_path
      ? `<img src="/api/photos/${c.photo_path}" alt="">`
      : `<div class="placeholder"></div>`;
    const metaParts = [c.phone_mobile, c.email].filter(Boolean).join(" &middot; ");

    const actionButtons = [];
    if (c.status !== "approved") {
      actionButtons.push(`<button class="btn-primary" data-action="approve" data-id="${c.id}">Approve</button>`);
    }
    if (c.status !== "rejected") {
      actionButtons.push(`<button class="btn-secondary" data-action="reject" data-id="${c.id}">Reject</button>`);
    }
    actionButtons.push(`<button class="btn-secondary" data-action="edit" data-id="${c.id}">Edit</button>`);
    actionButtons.push(`<button class="btn-danger" data-action="delete" data-id="${c.id}">Delete</button>`);

    return `
      <div class="contact-card">
        ${photo}
        <div class="info">
          <div class="name">${escapeHtml(c.full_name)}<span class="badge ${c.status}">${c.status}</span></div>
          <div class="meta">${metaParts || "&nbsp;"}</div>
        </div>
        <div class="actions">${actionButtons.join("")}</div>
      </div>`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  async function handleAction(action, id) {
    if (action === "approve") return patchContact(id, { status: "approved" });
    if (action === "reject") return patchContact(id, { status: "rejected" });
    if (action === "delete") return deleteContact(id);
    if (action === "edit") return openEditModal(id);
  }

  async function patchContact(id, payload) {
    await apiFetch(`/api/admin/contacts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    loadContacts();
  }

  async function deleteContact(id) {
    if (!confirm("Delete this contact permanently? This cannot be undone.")) return;
    await apiFetch(`/api/admin/contacts/${id}`, { method: "DELETE" });
    loadContacts();
  }

  // --- Edit modal ---
  async function openEditModal(id) {
    const res = await apiFetch(`/api/admin/contacts?status_filter=all`);
    const allContacts = await res.json();
    const c = allContacts.find((x) => x.id === id);
    if (!c) return;
    editingContactId = id;
    document.getElementById("edit-name").value = c.full_name || "";
    document.getElementById("edit-phone").value = c.phone_mobile || "";
    document.getElementById("edit-email").value = c.email || "";
    document.getElementById("edit-address").value = c.home_address || "";
    document.getElementById("edit-city").value = c.city || "";
    document.getElementById("edit-state").value = c.state || "";
    document.getElementById("edit-zip").value = c.zip || "";
    showModal(editOverlay);
  }

  document.getElementById("edit-cancel").addEventListener("click", () => hideModal(editOverlay));
  document.getElementById("edit-save").addEventListener("click", async () => {
    await patchContact(editingContactId, {
      full_name: document.getElementById("edit-name").value.trim(),
      phone_mobile: document.getElementById("edit-phone").value.trim(),
      email: document.getElementById("edit-email").value.trim(),
      home_address: document.getElementById("edit-address").value.trim(),
      city: document.getElementById("edit-city").value.trim(),
      state: document.getElementById("edit-state").value.trim(),
      zip: document.getElementById("edit-zip").value.trim(),
    });
    hideModal(editOverlay);
  });

  // --- Settings / directory modal ---
  document.getElementById("open-settings").addEventListener("click", async () => {
    const res = await apiFetch("/api/admin/settings");
    const settings = await res.json();
    document.getElementById("setting-include-address").checked = settings.include_home_address_default;
    document.getElementById("generate-include-address").checked = settings.include_home_address_default;
    document.getElementById("settings-error").hidden = true;
    document.getElementById("settings-success").hidden = true;
    showModal(settingsOverlay);
  });
  document.getElementById("settings-close").addEventListener("click", () => hideModal(settingsOverlay));

  document.getElementById("setting-include-address").addEventListener("change", async (e) => {
    await apiFetch("/api/admin/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_home_address_default: e.target.checked }),
    });
  });

  document.getElementById("generate-pdf-btn").addEventListener("click", () => {
    const includeAddress = document.getElementById("generate-include-address").checked;
    window.open(`/api/admin/directory.pdf?include_home_address=${includeAddress}`, "_blank");
  });

  document.getElementById("change-pin-btn").addEventListener("click", async () => {
    const newPin = document.getElementById("new-pin").value;
    const errorEl = document.getElementById("settings-error");
    const successEl = document.getElementById("settings-success");
    errorEl.hidden = true;
    successEl.hidden = true;
    const res = await apiFetch("/api/admin/change-pin", {
      method: "POST",
      body: new URLSearchParams({ new_pin: newPin }),
    });
    if (res.ok) {
      document.getElementById("new-pin").value = "";
      successEl.textContent = "PIN updated.";
      successEl.hidden = false;
    } else {
      const body = await res.json().catch(() => ({}));
      errorEl.textContent = body.detail || "Could not update PIN.";
      errorEl.hidden = false;
    }
  });

  // --- Init: check if already logged in ---
  (async () => {
    try {
      const res = await apiFetch("/api/admin/contacts?status_filter=pending");
      if (res.ok) {
        showMain();
        loadContacts();
      } else {
        showLogin();
      }
    } catch (err) {
      console.error("initial auth check failed:", err);
      showLogin();
    }
  })();
})();
