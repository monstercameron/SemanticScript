// Todo Web Pro — dashboard interactivity.
//
// Served at /assets/dashboard.js by the staticAssetHandler. Loaded by
// the DashboardPageTemplate in pages/main.sem. Drives:
//   - the welcome line, user pill, and avatar initial (fetches /api/auth/me)
//   - the open/done stat tiles and todo list (fetches /api/todos)
//   - the "New todo" composer (POST /api/todos)
//   - the "Sign out" button (POST /api/auth/logout, then redirect home)

(function () {
  const welcomeLine = document.getElementById("welcomeLine");
  const todoCountLine = document.getElementById("todoCountLine");
  const todoList = document.getElementById("todoList");
  const newTodoButton = document.getElementById("newTodoButton");
  const newTodoForm = document.getElementById("newTodoForm");
  const cancelNewTodoButton = document.getElementById("cancelNewTodoButton");
  const newTodoResult = document.getElementById("newTodoResult");
  const logoutButton = document.getElementById("logoutButton");
  const userPill = document.getElementById("userPill");
  const userPillLabel = document.getElementById("userPillLabel");
  const userAvatar = document.getElementById("userAvatar");
  const statOpen = document.getElementById("statOpen");
  const statDone = document.getElementById("statDone");

  function setText(element, message) {
    if (element) element.textContent = message;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options || {}));
    let body = null;
    try { body = await response.json(); } catch (_) { body = null; }
    return { status: response.status, body };
  }

  function setResult(message, kind) {
    if (!newTodoResult) return;
    const palette = {
      info:    "min-h-[1.25rem] text-sm text-ink-500",
      success: "min-h-[1.25rem] text-sm font-medium text-emerald-700",
      error:   "min-h-[1.25rem] text-sm font-medium text-rose-700",
    };
    newTodoResult.className = palette[kind] || palette.info;
    newTodoResult.textContent = message;
  }

  async function loadMe() {
    const result = await fetchJson("/api/auth/me");
    if (result.status === 401) {
      window.location.href = "/";
      return null;
    }
    if (result.status !== 200 || !result.body || !result.body.user) {
      setText(welcomeLine, "Could not load your account.");
      return null;
    }
    const user = result.body.user;
    const friendly = user.displayName && user.displayName.length > 0 ? user.displayName : user.username;
    setText(welcomeLine, "Hi, " + friendly + ".");
    if (userPill && userPillLabel && userAvatar) {
      userPill.classList.remove("hidden");
      userPill.classList.add("flex");
      userPillLabel.textContent = friendly + " (#" + user.id + ")";
      userAvatar.textContent = friendly.charAt(0).toUpperCase();
    }
    return user;
  }

  function priorityLabel(value) {
    if (value === 1) return "High";
    if (value === 3) return "Low";
    return "Medium";
  }

  function priorityClass(value) {
    if (value === 1) return "bg-rose-100 text-rose-700 ring-rose-200/60";
    if (value === 3) return "bg-ink-100 text-ink-600 ring-ink-200/60";
    return "bg-amber-100 text-amber-700 ring-amber-200/60";
  }

  function renderEmptyState() {
    todoList.innerHTML =
      '<li class="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-ink-200 bg-white/40 px-6 py-12 text-center">' +
      '  <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700">' +
      '    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>' +
      '  </div>' +
      '  <div class="text-base font-semibold text-ink-800">All caught up</div>' +
      '  <div class="max-w-xs text-sm text-ink-500">Nothing here yet. Click <span class="font-semibold text-brand-700">New todo</span> to add your first item.</div>' +
      "</li>";
  }

  function renderTodos(todos) {
    if (!todos || todos.length === 0) {
      renderEmptyState();
      return;
    }
    todoList.innerHTML = todos.map((todo) => {
      const done = todo.done === true || todo.done === 1;
      const doneAttr = done ? "true" : "false";
      const titleEsc = escapeHtml(todo.title);
      const priClass = priorityClass(todo.priority);
      const priLabel = priorityLabel(todo.priority);
      // Open todos: empty circle → POST /complete (mark done).
      // Done todos: green check circle → POST /uncomplete (mark open).
      // Both states are buttons so the toggle is a single mental model.
      const dotMarkup = done
        ? '<button type="button" class="js-uncomplete-btn check-dot flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white shadow-sm transition hover:bg-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-200" aria-label="Mark open"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></button>'
        : '<button type="button" class="js-complete-btn check-dot flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-ink-300 bg-white text-emerald-600 transition hover:border-emerald-400 hover:bg-emerald-50 focus:outline-none focus:ring-2 focus:ring-emerald-200" aria-label="Mark complete"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 opacity-0 transition group-hover:opacity-70" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></button>';
      return (
        '<li class="check-card group flex items-center gap-4 rounded-2xl border border-ink-200/70 bg-white/80 px-4 py-3.5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md" data-done="' + doneAttr + '" data-id="' + todo.id + '">' +
        dotMarkup +
        '<div class="min-w-0 flex-1">' +
        '  <div class="check-title text-sm font-medium text-ink-900">' + titleEsc + '</div>' +
        '  <div class="mt-0.5 text-xs text-ink-400">#' + todo.id + '</div>' +
        '</div>' +
        '<span class="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ' + priClass + '">' + priLabel + '</span>' +
        '<button type="button" class="js-delete-btn ml-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-400 opacity-0 transition hover:bg-rose-50 hover:text-rose-600 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-rose-200 group-hover:opacity-100" aria-label="Delete todo">' +
        '  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        '</button>' +
        "</li>"
      );
    }).join("");
  }

  // Event delegation — single listener on the <ul> handles both
  // mark-complete and delete clicks so we don't have to re-wire after
  // every loadTodos() re-render.
  if (todoList) {
    todoList.addEventListener("click", async (event) => {
      const completeBtn = event.target.closest(".js-complete-btn");
      const uncompleteBtn = event.target.closest(".js-uncomplete-btn");
      const deleteBtn = event.target.closest(".js-delete-btn");
      const card = event.target.closest(".check-card");
      if (!card) return;
      const todoId = card.dataset.id;
      if (!todoId) return;
      if (completeBtn) {
        completeBtn.disabled = true;
        card.classList.add("opacity-60");
        const result = await fetchJson("/api/todos/" + encodeURIComponent(todoId) + "/complete", {
          method: "POST",
        });
        if (result.status === 200) {
          await loadTodos();
        } else {
          card.classList.remove("opacity-60");
          completeBtn.disabled = false;
          setText(todoCountLine, "Could not mark complete (status " + result.status + ").");
        }
        return;
      }
      if (uncompleteBtn) {
        uncompleteBtn.disabled = true;
        card.classList.add("opacity-60");
        const result = await fetchJson("/api/todos/" + encodeURIComponent(todoId) + "/uncomplete", {
          method: "POST",
        });
        if (result.status === 200) {
          await loadTodos();
        } else {
          card.classList.remove("opacity-60");
          uncompleteBtn.disabled = false;
          setText(todoCountLine, "Could not mark open (status " + result.status + ").");
        }
        return;
      }
      if (deleteBtn) {
        deleteBtn.disabled = true;
        card.classList.add("scale-95", "opacity-0", "transition");
        const result = await fetchJson("/api/todos/" + encodeURIComponent(todoId), {
          method: "DELETE",
        });
        if (result.status === 200) {
          // brief animation pause so the card visibly slides out
          setTimeout(loadTodos, 150);
        } else {
          card.classList.remove("scale-95", "opacity-0");
          deleteBtn.disabled = false;
          setText(todoCountLine, "Could not delete (status " + result.status + ").");
        }
        return;
      }
    });
  }

  function updateStats(todos) {
    if (!statOpen || !statDone) return;
    const total = todos.length;
    const done = todos.filter((t) => t.done === true || t.done === 1).length;
    const open = total - done;
    statOpen.textContent = String(open);
    statDone.textContent = String(done);
  }

  async function loadTodos() {
    const result = await fetchJson("/api/todos");
    if (result.status !== 200) {
      setText(todoCountLine, "Could not load todos (status " + result.status + ").");
      return;
    }
    const todos = (result.body && result.body.todos) || [];
    const count = (result.body && typeof result.body.count === "number") ? result.body.count : todos.length;
    setText(
      todoCountLine,
      count === 0
        ? "You're all caught up."
        : count + " todo" + (count === 1 ? "" : "s") + " on your plate."
    );
    updateStats(todos);
    renderTodos(todos);
  }

  if (newTodoButton) {
    newTodoButton.addEventListener("click", () => {
      newTodoForm.classList.remove("hidden");
      document.getElementById("newTodoTitle").focus();
    });
  }
  if (cancelNewTodoButton) {
    cancelNewTodoButton.addEventListener("click", () => {
      newTodoForm.classList.add("hidden");
      newTodoForm.reset();
      setResult("", "info");
    });
  }
  if (newTodoForm) {
    newTodoForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      const payload = {
        title: form.get("title"),
        body: form.get("body") || "",
        priority: parseInt(form.get("priority") || "2", 10),
      };
      setResult("Saving...", "info");
      const result = await fetchJson("/api/todos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (result.status === 201) {
        setResult("", "info");
        newTodoForm.classList.add("hidden");
        newTodoForm.reset();
        loadTodos();
      } else {
        setResult(
          result.body && result.body.error
            ? result.body.error.message
            : "Error " + result.status,
          "error"
        );
      }
    });
  }
  if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
      logoutButton.disabled = true;
      logoutButton.textContent = "Signing out...";
      try {
        await fetchJson("/api/auth/logout", { method: "POST" });
      } catch (_) { /* ignore */ }
      window.location.href = "/";
    });
  }

  (async function init() {
    const user = await loadMe();
    if (user) {
      await loadTodos();
    }
  })();
})();
