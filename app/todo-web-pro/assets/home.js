// Todo Web Pro — home page interactivity.
//
// Served at /assets/home.js by the staticAssetHandler in main.sem
// (which routes through http.responseFile with `assets` as the root
// directory). The HTML page (rendered by pages/main.sem's
// HomePageTemplate) references this file via a <script src="..."> tag
// in its <body>.

document.getElementById("registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const resultElement = document.getElementById("registerResult");
  const formData = new FormData(event.target);
  resultElement.className = "mt-3 text-sm text-slate-500";
  resultElement.textContent = "Creating account...";
  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password"),
      }),
    });
    const payload = await response.json();
    if (response.status === 201) {
      resultElement.className = "mt-3 text-sm font-medium text-emerald-700";
      resultElement.textContent = "Welcome, " + payload.user.username + "! Session cookie set.";
    } else if (response.status === 409) {
      resultElement.className = "mt-3 text-sm font-medium text-amber-700";
      resultElement.textContent = "That username is already taken.";
    } else {
      resultElement.className = "mt-3 text-sm font-medium text-rose-700";
      resultElement.textContent = payload.error ? payload.error.message : ("Error " + response.status);
    }
  } catch (err) {
    resultElement.className = "mt-3 text-sm font-medium text-rose-700";
    resultElement.textContent = "Network error: " + err.message;
  }
});
