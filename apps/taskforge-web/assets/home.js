// Todo Web Pro — home page interactivity.
//
// Served at /assets/home.js by the staticAssetHandler in main.sem
// (which routes through http.responseFile with `assets/` as the root
// directory). The HTML page (rendered by pages/main.sem's
// HomePageTemplate) references this file via a <script src="..."> tag.
//
// Behaviors:
//   - Tab switching between Login and Register cards (with active-state
//     classes that match the modern AuthCard styling).
//   - Login form POSTs JSON to /api/auth/login; on 200 redirects to
//     /dashboard, on 401 shows a generic "invalid credentials" warning.
//   - Register form POSTs JSON to /api/auth/register; on 201 redirects
//     to /dashboard, on 409 shows the conflict message.
//   - One-click demo sign-in via the "Use demo account" button.
//
// Guard against the fallback-GET-leak: the script wires onsubmit
// listeners synchronously and calls event.preventDefault() so the
// browser's default form submission (which would put credentials in
// the URL on a GET) never fires.

(function () {
  const loginTab = document.getElementById("tab-login");
  const registerTab = document.getElementById("tab-register");
  const loginPanel = document.getElementById("panel-login");
  const registerPanel = document.getElementById("panel-register");

  // Tab class strings match the AuthCardComponent template exactly so
  // toggling stays visually consistent with the server-rendered state.
  const activeTabClass =
    "rounded-xl bg-white px-3 py-2 text-sm font-semibold text-brand-700 shadow-sm ring-1 ring-ink-200/40 transition";
  const idleTabClass =
    "rounded-xl px-3 py-2 text-sm font-medium text-ink-500 transition hover:text-ink-700";

  function showLogin() {
    loginTab.dataset.active = "true";
    registerTab.dataset.active = "false";
    loginTab.className = activeTabClass;
    registerTab.className = idleTabClass;
    loginPanel.classList.remove("hidden");
    registerPanel.classList.add("hidden");
  }

  function showRegister() {
    loginTab.dataset.active = "false";
    registerTab.dataset.active = "true";
    loginTab.className = idleTabClass;
    registerTab.className = activeTabClass;
    loginPanel.classList.add("hidden");
    registerPanel.classList.remove("hidden");
  }

  if (loginTab && registerTab) {
    loginTab.addEventListener("click", showLogin);
    registerTab.addEventListener("click", showRegister);
  }

  function setResult(elementId, message, kind) {
    const element = document.getElementById(elementId);
    if (!element) return;
    const palette = {
      info:    "min-h-[1.25rem] text-sm text-ink-500",
      success: "min-h-[1.25rem] text-sm font-medium text-emerald-700",
      warn:    "min-h-[1.25rem] text-sm font-medium text-amber-700",
      error:   "min-h-[1.25rem] text-sm font-medium text-rose-700",
    };
    element.className = palette[kind] || palette.info;
    element.textContent = message;
  }

  async function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    });
  }

  document
    .getElementById("loginForm")
    .addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      setResult("loginResult", "Signing in...", "info");
      try {
        const response = await postJson("/api/auth/login", {
          username: form.get("username"),
          password: form.get("password"),
        });
        if (response.status === 200) {
          setResult("loginResult", "Welcome back. Redirecting...", "success");
          window.location.href = "/dashboard";
          return;
        }
        if (response.status === 401) {
          setResult("loginResult", "Invalid username or password.", "warn");
          return;
        }
        const payload = await response.json().catch(() => ({}));
        setResult(
          "loginResult",
          payload.error ? payload.error.message : "Error " + response.status,
          "error"
        );
      } catch (err) {
        setResult("loginResult", "Network error: " + err.message, "error");
      }
    });

  document
    .getElementById("registerForm")
    .addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      setResult("registerResult", "Creating account...", "info");
      try {
        const response = await postJson("/api/auth/register", {
          username: form.get("username"),
          password: form.get("password"),
        });
        if (response.status === 201) {
          setResult("registerResult", "Account created. Redirecting...", "success");
          window.location.href = "/dashboard";
          return;
        }
        if (response.status === 409) {
          setResult("registerResult", "That username is already taken.", "warn");
          return;
        }
        const payload = await response.json().catch(() => ({}));
        setResult(
          "registerResult",
          payload.error ? payload.error.message : "Error " + response.status,
          "error"
        );
      } catch (err) {
        setResult("registerResult", "Network error: " + err.message, "error");
      }
    });

  // One-click demo login.
  const demoButton = document.getElementById("useDemoAccount");
  if (demoButton) {
    demoButton.addEventListener("click", async () => {
      setResult("loginResult", "Signing in as demo...", "info");
      showLogin();
      try {
        const response = await postJson("/api/auth/login", {
          username: "demo",
          password: "demo1234",
        });
        if (response.status === 200) {
          window.location.href = "/dashboard";
        } else {
          setResult(
            "loginResult",
            "Could not sign in as demo (status " + response.status + ").",
            "error"
          );
        }
      } catch (err) {
        setResult("loginResult", "Network error: " + err.message, "error");
      }
    });
  }
})();
