/*
 * floor.js - the thin live-update layer for the server-rendered Floor page.
 *
 * The page arrives fully server-rendered. This script does only what SSR
 * cannot: (1) tick the countdown every second, and (2) keep the live regions
 * fresh by re-fetching this same SSR page and patching a few nodes in place.
 * Re-fetching the server's own HTML (rather than a bespoke JSON API) keeps the
 * server as the single source of truth and needs no extra endpoint.
 *
 * No framework, no build step. Loaded with `defer`.
 */
(() => {
  "use strict";

  const POLL_MS = 2500;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const countdown = document.getElementById("countdown");
  const currentBid = document.getElementById("currentBid");

  /* ---- Countdown ticker (no network) ----------------------------------- */
  function tickCountdown() {
    if (!countdown) return;
    const closesAt = Number(countdown.dataset.closesAt || 0);
    const status = document.getElementById("auctionStatus")?.dataset.status;
    if (status === "closed" || status === "cancelled") {
      countdown.dataset.phase = "closed";
      countdown.textContent = status === "cancelled" ? "Cancelled" : "Closed";
      return;
    }
    const remaining = Math.max(0, closesAt - Date.now());
    countdown.dataset.phase = remaining > 0 && remaining <= 60000 ? "warning" : "normal";
    countdown.textContent = formatDuration(remaining);
  }

  function formatDuration(ms) {
    const total = Math.max(0, Math.ceil(ms / 1000));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  /* ---- Live patch: re-fetch this SSR page, swap the live regions -------- */
  // Patch text/attributes from a freshly-fetched copy; flash the price on rise.
  async function refresh() {
    let doc;
    try {
      const res = await fetch(location.href, { headers: { "X-Live-Refresh": "1" } });
      if (!res.ok) return;
      doc = new DOMParser().parseFromString(await res.text(), "text/html");
    } catch {
      return; // transient; the next tick retries
    }

    patchText("auctionStatus", doc, (el, next) => { el.dataset.status = next.dataset.status; });
    patchText("currentWinner", doc);
    patchText("auctionDescription", doc);
    patchHtml("eventFeed", doc);
    patchHtml("chatMessages", doc);

    // Price: compare before swapping so we can flash on an increase.
    const nextBid = doc.getElementById("currentBid");
    if (currentBid && nextBid) {
      const before = parseMoney(currentBid.textContent);
      const after = parseMoney(nextBid.textContent);
      currentBid.textContent = nextBid.textContent;
      if (!reduceMotion && after > before) {
        currentBid.dataset.flash = "up";
        setTimeout(() => { delete currentBid.dataset.flash; }, 950);
      }
    }

    // Re-seed the countdown target (anti-snipe can push it out).
    const nextCountdown = doc.getElementById("countdown");
    if (countdown && nextCountdown) countdown.dataset.closesAt = nextCountdown.dataset.closesAt || "0";
  }

  function patchText(id, doc, after) {
    const el = document.getElementById(id);
    const next = doc.getElementById(id);
    if (!el || !next) return;
    el.textContent = next.textContent;
    after?.(el, next);
  }

  function patchHtml(id, doc) {
    const el = document.getElementById(id);
    const next = doc.getElementById(id);
    // next.innerHTML is server-rendered + server-escaped, so this is safe.
    if (el && next) el.innerHTML = next.innerHTML;
  }

  function parseMoney(text) {
    const n = Number(String(text || "").replace(/[^0-9.]/g, ""));
    return Number.isFinite(n) ? n : 0;
  }

  /* ---- Bid + chat: best-effort POST to the API server ------------------ *
   * These are authenticated API actions on another origin. Without a token
   * the API returns 401; we surface that rather than failing silently. Wiring
   * the cross-origin authenticated session is the next milestone. */
  wireForm("bidForm", "lastRejectedBid", (form) => {
    const amount = Number(document.getElementById("bidAmountInput").value);
    if (!Number.isFinite(amount) || amount <= 0) return null;
    return {
      url: `${form.dataset.api}/api/v1/auctions/${encodeURIComponent(form.dataset.auction)}/bids`,
      body: { amount: Math.round(amount * 100), expectedRevision: 0 },
    };
  });

  wireForm("chatForm", null, (form) => {
    const text = document.getElementById("chatInput").value.trim();
    if (!text) return null;
    return {
      url: `${form.dataset.api}/api/v1/auctions/${encodeURIComponent(form.dataset.auction)}/chat/messages`,
      body: { text },
    };
  });

  function wireForm(formId, errorId, build) {
    const form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const plan = build(form);
      if (!plan) return;
      try {
        const res = await fetch(plan.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": idem() },
          body: JSON.stringify(plan.body),
        });
        if (!res.ok) showError(errorId, `Server returned ${res.status} (sign-in required)`);
        else { showError(errorId, ""); await refresh(); }
      } catch {
        showError(errorId, "Could not reach the auction API");
      }
    });
  }

  function showError(id, message) {
    if (!id) return;
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = !message;
    el.textContent = message;
  }

  function idem() {
    return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }

  /* ---- Boot ------------------------------------------------------------- */
  tickCountdown();
  setInterval(tickCountdown, 1000);
  setInterval(refresh, POLL_MS);
})();
