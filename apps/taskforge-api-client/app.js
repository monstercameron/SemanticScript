(function () {
  const state = {
    user: null,
    todos: [],
    filter: "all",
    search: "",
    loading: false,
  };

  const elements = {
    apiVersion: document.getElementById("apiVersion"),
    sessionPill: document.getElementById("sessionPill"),
    refreshButton: document.getElementById("refreshButton"),
    logoutButton: document.getElementById("logoutButton"),
    loginPanel: document.getElementById("loginPanel"),
    composerPanel: document.getElementById("composerPanel"),
    loginForm: document.getElementById("loginForm"),
    demoButton: document.getElementById("demoButton"),
    loginMessage: document.getElementById("loginMessage"),
    createForm: document.getElementById("createForm"),
    createMessage: document.getElementById("createMessage"),
    countLine: document.getElementById("countLine"),
    openCount: document.getElementById("openCount"),
    doneCount: document.getElementById("doneCount"),
    todoList: document.getElementById("todoList"),
    errorBanner: document.getElementById("errorBanner"),
    filterButtons: Array.from(document.querySelectorAll(".filter-button")),
    searchInput: document.getElementById("searchInput"),
    newTitle: document.getElementById("newTitle"),
  };

  function setText(node, text) {
    if (node) node.textContent = text;
  }

  function setMessage(node, message, kind) {
    if (!node) return;
    node.className = "status-line" + (kind ? " " + kind : "");
    node.textContent = message;
  }

  function setError(message) {
    if (!elements.errorBanner) return;
    if (!message) {
      elements.errorBanner.classList.add("hidden");
      elements.errorBanner.textContent = "";
      return;
    }
    elements.errorBanner.textContent = message;
    elements.errorBanner.classList.remove("hidden");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function requestJson(path, options) {
    const requestOptions = Object.assign({ credentials: "same-origin" }, options || {});
    const response = await fetch(path, requestOptions);
    const text = await response.text();
    let body = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch (error) {
        body = { raw: text };
      }
    }
    return { status: response.status, ok: response.ok, body };
  }

  async function postJson(path, payload) {
    return requestJson(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function priorityLabel(value) {
    if (value === 1) return "High";
    if (value === 3) return "Low";
    return "Medium";
  }

  function priorityClass(value) {
    if (value === 1) return "high";
    if (value === 3) return "low";
    return "medium";
  }

  function isDone(todo) {
    return todo.done === true || todo.done === 1;
  }

  function visibleTodos() {
    const needle = state.search.trim().toLowerCase();
    return state.todos.filter((todo) => {
      const done = isDone(todo);
      if (state.filter === "open" && done) return false;
      if (state.filter === "done" && !done) return false;
      if (!needle) return true;
      const haystack = [todo.title, todo.body, todo.id].join(" ").toLowerCase();
      return haystack.includes(needle);
    });
  }

  function updateSessionView() {
    const signedIn = Boolean(state.user);
    elements.loginPanel.classList.toggle("hidden", signedIn);
    elements.composerPanel.classList.toggle("hidden", !signedIn);
    elements.logoutButton.classList.toggle("hidden", !signedIn);

    if (signedIn) {
      const label = state.user.displayName || state.user.username;
      setText(elements.sessionPill, label + " #" + state.user.id);
    } else {
      setText(elements.sessionPill, "Signed out");
      setText(elements.countLine, "Sign in to load todos.");
    }
  }

  function updateCounts() {
    const done = state.todos.filter(isDone).length;
    const open = state.todos.length - done;
    setText(elements.openCount, String(open));
    setText(elements.doneCount, String(done));
    setText(
      elements.countLine,
      state.todos.length === 0
        ? "No todos returned by the API."
        : state.todos.length + " todo" + (state.todos.length === 1 ? "" : "s") + " returned by the API."
    );
  }

  function renderEmpty(text) {
    elements.todoList.innerHTML =
      '<li class="empty-state">' +
      '<span>' + escapeHtml(text) + '</span>' +
      "</li>";
  }

  function renderTodos() {
    updateCounts();
    const todos = visibleTodos();
    if (!state.user) {
      renderEmpty("No active session.");
      return;
    }
    if (state.todos.length === 0) {
      renderEmpty("No todos yet.");
      return;
    }
    if (todos.length === 0) {
      renderEmpty("No matching todos.");
      return;
    }

    elements.todoList.innerHTML = todos.map((todo) => {
      const done = isDone(todo);
      const id = encodeURIComponent(todo.id);
      const title = escapeHtml(todo.title || "Untitled");
      const body = todo.body ? '<span>' + escapeHtml(todo.body) + '</span>' : "";
      const priority = Number(todo.priority || 2);
      const toggleTitle = done ? "Mark open" : "Mark complete";
      const togglePath = done ? "uncomplete" : "complete";
      return (
        '<li class="todo-item' + (done ? " done" : "") + '" data-id="' + id + '">' +
        '  <button class="todo-button toggle-button" type="button" data-action="' + togglePath + '" title="' + toggleTitle + '" aria-label="' + toggleTitle + '">' +
        '    <svg viewBox="0 0 24 24" focusable="false"><path d="M5 12.5 9.2 16 19 6" /></svg>' +
        "  </button>" +
        '  <div class="todo-content">' +
        '    <div class="todo-title">' + title + "</div>" +
        '    <div class="todo-meta">' +
        '      <span>#' + escapeHtml(todo.id) + "</span>" +
        '      <span class="priority ' + priorityClass(priority) + '">' + priorityLabel(priority) + "</span>" +
        body +
        "    </div>" +
        "  </div>" +
        '  <div class="todo-actions">' +
        '    <button class="todo-button danger-button" type="button" data-action="delete" title="Delete todo" aria-label="Delete todo">' +
        '      <svg viewBox="0 0 24 24" focusable="false"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 15h10l1-15" /></svg>' +
        "    </button>" +
        "  </div>" +
        "</li>"
      );
    }).join("");
  }

  async function loadVersion() {
    try {
      const result = await requestJson("/api/version");
      if (result.status !== 200 || !result.body) {
        setText(elements.apiVersion, "API unavailable");
        return;
      }
      const name = result.body.app || result.body.name || "TaskForge API";
      const version = result.body.version || "unknown";
      setText(elements.apiVersion, name + " " + version);
    } catch (error) {
      setText(elements.apiVersion, "API unavailable");
    }
  }

  async function loadMe() {
    try {
      const result = await requestJson("/api/auth/me");
      if (result.status === 401) {
        state.user = null;
        state.todos = [];
        updateSessionView();
        renderTodos();
        return false;
      }
      if (result.status !== 200 || !result.body || !result.body.user) {
        throw new Error("Unexpected /api/auth/me status " + result.status);
      }
      state.user = result.body.user;
      updateSessionView();
      return true;
    } catch (error) {
      state.user = null;
      state.todos = [];
      updateSessionView();
      renderTodos();
      setError(error.message);
      return false;
    }
  }

  async function loadTodos() {
    if (!state.user || state.loading) return;
    state.loading = true;
    setError("");
    elements.refreshButton.disabled = true;
    try {
      const result = await requestJson("/api/todos");
      if (result.status === 401) {
        state.user = null;
        state.todos = [];
        updateSessionView();
        renderTodos();
        return;
      }
      if (result.status !== 200 || !result.body) {
        throw new Error("Unexpected /api/todos status " + result.status);
      }
      state.todos = Array.isArray(result.body.todos) ? result.body.todos : [];
      renderTodos();
    } catch (error) {
      setError(error.message);
    } finally {
      state.loading = false;
      elements.refreshButton.disabled = false;
    }
  }

  async function signIn(username, password) {
    setMessage(elements.loginMessage, "Signing in...", "");
    setError("");
    try {
      const result = await postJson("/api/auth/login", { username, password });
      if (result.status === 200) {
        setMessage(elements.loginMessage, "", "");
        await loadMe();
        await loadTodos();
        elements.newTitle.focus();
        return;
      }
      if (result.status === 401) {
        setMessage(elements.loginMessage, "Invalid username or password.", "warn");
        return;
      }
      const message = result.body && result.body.error ? result.body.error.message : "Status " + result.status;
      setMessage(elements.loginMessage, message, "error");
    } catch (error) {
      setMessage(elements.loginMessage, error.message, "error");
    }
  }

  async function createTodo(form) {
    const payload = {
      title: String(form.get("title") || "").trim(),
      body: String(form.get("body") || ""),
      priority: Number(form.get("priority") || 2),
    };
    if (!payload.title) {
      setMessage(elements.createMessage, "Title is required.", "warn");
      return;
    }
    setMessage(elements.createMessage, "Saving...", "");
    try {
      const result = await postJson("/api/todos", payload);
      if (result.status !== 201) {
        const message = result.body && result.body.error ? result.body.error.message : "Status " + result.status;
        setMessage(elements.createMessage, message, "error");
        return;
      }
      elements.createForm.reset();
      setMessage(elements.createMessage, "Saved.", "ok");
      await loadTodos();
      setTimeout(() => setMessage(elements.createMessage, "", ""), 1200);
    } catch (error) {
      setMessage(elements.createMessage, error.message, "error");
    }
  }

  async function mutateTodo(todoId, action, button) {
    if (!todoId || !action) return;
    button.disabled = true;
    setError("");
    try {
      const path =
        action === "delete"
          ? "/api/todos/" + todoId
          : "/api/todos/" + todoId + "/" + action;
      const result = await requestJson(path, { method: action === "delete" ? "DELETE" : "POST" });
      if (result.status !== 200) {
        throw new Error("Todo update failed with status " + result.status);
      }
      await loadTodos();
    } catch (error) {
      setError(error.message);
    } finally {
      button.disabled = false;
    }
  }

  elements.loginForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    signIn(form.get("username"), form.get("password"));
  });

  elements.demoButton.addEventListener("click", () => {
    signIn("demo", "demo1234");
  });

  elements.createForm.addEventListener("submit", (event) => {
    event.preventDefault();
    createTodo(new FormData(event.currentTarget));
  });

  elements.logoutButton.addEventListener("click", async () => {
    elements.logoutButton.disabled = true;
    try {
      await requestJson("/api/auth/logout", { method: "POST" });
    } finally {
      elements.logoutButton.disabled = false;
      state.user = null;
      state.todos = [];
      updateSessionView();
      renderTodos();
    }
  });

  elements.refreshButton.addEventListener("click", async () => {
    if (!state.user) {
      await loadMe();
    }
    await loadTodos();
  });

  elements.todoList.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    const item = event.target.closest(".todo-item");
    if (!button || !item) return;
    mutateTodo(item.dataset.id, button.dataset.action, button);
  });

  elements.filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter || "all";
      elements.filterButtons.forEach((candidate) => {
        candidate.classList.toggle("active", candidate === button);
      });
      renderTodos();
    });
  });

  elements.searchInput.addEventListener("input", () => {
    state.search = elements.searchInput.value;
    renderTodos();
  });

  (async function init() {
    await loadVersion();
    if (await loadMe()) {
      await loadTodos();
    }
  })();
})();
