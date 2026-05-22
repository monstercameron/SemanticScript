import { unwrapEnvelope } from "./state.js";

export function createApiClient(getConfig) {
  async function request(path, options = {}) {
    const config = getConfig();
    const url = buildUrl(config.apiBaseUrl, path);
    const headers = new Headers(options.headers || {});

    if (options.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    if (config.accessToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${config.accessToken}`);
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
      body: options.body !== undefined && typeof options.body !== "string"
        ? JSON.stringify(options.body)
        : options.body,
    });

    const text = await response.text();
    const payload = text ? parseJson(text) : null;

    if (!response.ok) {
      const errorData = payload?.error ?? payload;
      const message = errorData?.message || errorData?.code || `${response.status} ${response.statusText}`;
      const error = new Error(message);
      error.status = response.status;
      error.code = errorData?.code || "http_error";
      error.details = errorData?.details;
      throw error;
    }

    return unwrapEnvelope(payload);
  }

  return {
    getSession() {
      return request("/api/v1/session");
    },
    login(username, password) {
      return request("/api/v1/auth/login", {
        method: "POST",
        body: { username, password },
      });
    },
    getAuction(auctionId) {
      return request(`/api/v1/auctions/${encodeURIComponent(auctionId)}`);
    },
    placeBid(auctionId, amountMinor, bidderDisplayName, expectedRevision) {
      return request(`/api/v1/auctions/${encodeURIComponent(auctionId)}/bids`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("bid") },
        body: {
          amount: amountMinor,
          bidderDisplayName,
          expectedRevision,
        },
      });
    },
    sendChatMessage(auctionId, text, displayName) {
      return request(`/api/v1/auctions/${encodeURIComponent(auctionId)}/chat/messages`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("chat") },
        body: { text, displayName },
      });
    },
    eventsUrl(auctionId, lastEventId = "") {
      const params = new URLSearchParams();
      if (lastEventId) params.set("after", lastEventId);
      const suffix = params.toString() ? `?${params}` : "";
      return buildUrl(getConfig().apiBaseUrl, `/api/v1/auctions/${encodeURIComponent(auctionId)}/events${suffix}`);
    },
  };
}

export function buildUrl(apiBaseUrl, path) {
  const base = (apiBaseUrl || globalThis.location?.origin || "").replace(/\/$/, "");
  if (!base) return path;
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch (error) {
    const parseError = new Error("Server returned invalid JSON");
    parseError.cause = error;
    parseError.raw = text;
    throw parseError;
  }
}

function idempotencyKey(prefix) {
  if (globalThis.crypto?.randomUUID) {
    return `${prefix}_${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}
