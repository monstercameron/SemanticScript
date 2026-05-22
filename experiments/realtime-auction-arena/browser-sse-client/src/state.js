const DEFAULT_MAX_EVENTS = 80;
const DEFAULT_MAX_CHAT = 80;

export function createInitialState() {
  return {
    apiBaseUrl: "",
    auctionId: "A1",
    displayName: "Browser Bidder",
    accessToken: "",
    session: { role: "viewer", userId: "", displayName: "" },
    connection: "offline",
    lastError: "",
    snapshot: null,
    auction: null,
    lastEventId: "",
    lastSequence: 0,
    events: [],
    chat: [],
    rejectedBids: [],
    extendedAt: 0,
    serverTimeOffsetMs: 0,
  };
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function unwrapEnvelope(response) {
  if (!response || typeof response !== "object") {
    return response;
  }

  if (Object.prototype.hasOwnProperty.call(response, "ok")) {
    if (response.ok === false) {
      const message = response.error?.message || response.error?.code || "Request failed";
      const error = new Error(message);
      error.code = response.error?.code || "api_error";
      error.details = response.error?.details;
      throw error;
    }

    return response.data ?? response;
  }

  return response.data ?? response;
}

export function normalizeSnapshot(raw) {
  const data = unwrapEnvelope(raw);
  const auction = data?.auction ?? data;
  const item = auction?.item ?? {};
  const policy = auction?.policy ?? {};
  const timing = auction?.timing ?? {};
  const currentBid = toMinorUnits(auction?.currentBid ?? auction?.currentBidMinor ?? auction?.startingBid ?? 0);
  const minimumIncrement = toMinorUnits(policy.minimumIncrement ?? policy.minimumIncrementMinor ?? 0);

  return {
    auction: {
      auctionId: String(auction?.auctionId ?? data?.auctionId ?? "A1"),
      revision: Number(auction?.revision ?? 0),
      status: String(auction?.status ?? "unknown"),
      item: {
        title: String(item.title ?? item.name ?? "Untitled auction item"),
        description: String(item.description ?? ""),
        imageUrl: String(item.imageUrl ?? ""),
      },
      policy: {
        minimumIncrement,
        currency: String(policy.currency ?? "USD"),
      },
      timing: {
        closesAt: Number(timing.closesAt ?? auction?.closesAt ?? 0),
        startedAt: Number(timing.startedAt ?? auction?.startedAt ?? 0),
        closedAt: Number(timing.closedAt ?? auction?.closedAt ?? 0),
      },
      startingBid: toMinorUnits(auction?.startingBid ?? 0),
      currentBid,
      minimumAcceptedBid: toMinorUnits(auction?.minimumAcceptedBid ?? currentBid + minimumIncrement),
      currentWinner: String(auction?.currentWinnerDisplayName ?? auction?.currentWinner ?? auction?.winner ?? ""),
      lastBidder: String(auction?.lastBidder ?? ""),
    },
    lastEventSequence: Number(data?.lastEventSequence ?? data?.sequence ?? 0),
    serverTime: Number(data?.serverTime ?? Date.now()),
    activeClientCount: Number(data?.activeClientCount ?? 0),
  };
}

export function applySnapshot(state, rawSnapshot) {
  const snapshot = normalizeSnapshot(rawSnapshot);
  state.snapshot = snapshot;
  state.auction = snapshot.auction;
  state.auctionId = snapshot.auction.auctionId;
  state.lastSequence = Math.max(state.lastSequence, snapshot.lastEventSequence || 0);
  if (snapshot.serverTime > 0) {
    state.serverTimeOffsetMs = snapshot.serverTime - Date.now();
  }
  return state;
}

export function normalizeEvent(raw) {
  const event = unwrapEnvelope(raw);
  const payload = event?.payload && typeof event.payload === "object" ? event.payload : event ?? {};
  const type = String(event?.type ?? event?.eventType ?? payload.type ?? "message");

  return {
    eventId: String(event?.eventId ?? event?.id ?? payload.eventId ?? ""),
    auctionId: String(event?.auctionId ?? payload.auctionId ?? ""),
    sequence: Number(event?.sequence ?? payload.sequence ?? 0),
    schemaVersion: String(event?.schemaVersion ?? "1"),
    type,
    occurredAt: Number(event?.occurredAt ?? payload.occurredAt ?? Date.now()),
    payload: { ...payload, type },
  };
}

export function applyEvent(state, rawEvent) {
  const event = normalizeEvent(rawEvent);
  if (event.eventId && state.events.some((existing) => existing.eventId === event.eventId)) {
    return state;
  }

  state.events.unshift(event);
  state.events = state.events.slice(0, DEFAULT_MAX_EVENTS);
  state.lastEventId = event.eventId || state.lastEventId;
  state.lastSequence = Math.max(state.lastSequence, event.sequence || 0);

  if (event.type === "bid.accepted") {
    applyBidAccepted(state, event.payload);
  } else if (event.type === "bid.rejected") {
    applyBidRejected(state, event.payload);
  } else if (event.type === "auction.extended") {
    applyAuctionExtended(state, event.payload);
  } else if (event.type === "auction.closed") {
    applyAuctionClosed(state, event.payload);
  } else if (event.type === "auction.started" || event.type === "auction.created") {
    applyAuctionLifecycle(state, event);
  } else if (event.type === "chat.message.created") {
    applyChatCreated(state, event.payload);
  } else if (event.type === "chat.message.deleted") {
    applyChatDeleted(state, event.payload);
  } else if (event.type === "chat.message.reported") {
    applyChatModeration(state, event.payload, "reported");
  }

  return state;
}

export function minimumAcceptedBid(state) {
  return toMajorUnits(state.auction?.minimumAcceptedBid ?? state.auction?.currentBid ?? 0);
}

export function formatMoney(minorUnits, currency = "USD") {
  const amount = toMajorUnits(minorUnits);
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

export function nowWithServerOffset(state) {
  return Date.now() + (state.serverTimeOffsetMs || 0);
}

export function millisecondsUntilClose(state) {
  const closesAt = Number(state.auction?.timing?.closesAt ?? 0);
  if (!closesAt) return 0;
  return Math.max(0, closesAt - nowWithServerOffset(state));
}

export function formatDuration(ms) {
  if (!ms) return "00:00";
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts = hours > 0 ? [hours, minutes, seconds] : [minutes, seconds];
  return parts.map((part) => String(part).padStart(2, "0")).join(":");
}

export function toMinorUnits(value) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return 0;
  return Math.round(number);
}

export function toMajorUnits(minorUnits) {
  const number = Number(minorUnits ?? 0);
  if (!Number.isFinite(number)) return 0;
  return number / 100;
}

function applyBidAccepted(state, payload) {
  ensureAuction(state);
  state.auction.currentBid = toMinorUnits(payload.amount ?? state.auction.currentBid);
  state.auction.currentWinner = String(payload.bidderDisplayName ?? payload.bidder ?? payload.bidderId ?? "");
  state.auction.lastBidder = String(payload.bidderId ?? payload.bidder ?? "");
  state.auction.revision = Number(payload.newRevision ?? state.auction.revision);
  if (payload.closesAt) {
    state.auction.timing.closesAt = Number(payload.closesAt);
  }
  const increment = state.auction.policy.minimumIncrement || 0;
  state.auction.minimumAcceptedBid = state.auction.currentBid + increment;
}

function applyBidRejected(state, payload) {
  state.rejectedBids.unshift({
    bidder: String(payload.bidderDisplayName ?? payload.bidder ?? payload.bidderId ?? ""),
    amount: toMinorUnits(payload.amount ?? 0),
    reason: String(payload.reason ?? "rejected"),
    currentBid: toMinorUnits(payload.currentBid ?? 0),
    minimumAcceptedBid: toMinorUnits(payload.minimumAcceptedBid ?? 0),
  });
  state.rejectedBids = state.rejectedBids.slice(0, 12);
}

function applyAuctionExtended(state, payload) {
  ensureAuction(state);
  state.extendedAt = Date.now();
  if (payload.closesAt) {
    state.auction.timing.closesAt = Number(payload.closesAt);
  } else if (payload.seconds) {
    state.auction.timing.closesAt = Math.max(state.auction.timing.closesAt, nowWithServerOffset(state)) + Number(payload.seconds) * 1000;
  }
}

function applyAuctionClosed(state, payload) {
  ensureAuction(state);
  state.auction.status = "closed";
  state.auction.timing.closedAt = Number(payload.closedAt ?? nowWithServerOffset(state));
  if (payload.amount !== undefined) {
    state.auction.currentBid = toMinorUnits(payload.amount);
  }
  if (payload.winner || payload.winnerDisplayName) {
    state.auction.currentWinner = String(payload.winnerDisplayName ?? payload.winner);
  }
}

function applyAuctionLifecycle(state, event) {
  ensureAuction(state);
  state.auction.status = event.type === "auction.started" ? "running" : state.auction.status;
  if (event.payload.item) {
    state.auction.item.title = String(event.payload.item.title ?? event.payload.item.name ?? state.auction.item.title);
    state.auction.item.description = String(event.payload.item.description ?? state.auction.item.description);
    state.auction.item.imageUrl = String(event.payload.item.imageUrl ?? state.auction.item.imageUrl);
  }
  if (event.payload.startingBid !== undefined) {
    state.auction.startingBid = toMinorUnits(event.payload.startingBid);
    state.auction.currentBid = Math.max(state.auction.currentBid, state.auction.startingBid);
  }
}

function applyChatCreated(state, payload) {
  state.chat.push({
    messageId: String(payload.messageId ?? cryptoRandomId()),
    user: String(payload.user ?? payload.displayName ?? payload.userId ?? "Anonymous"),
    text: String(payload.text ?? ""),
    occurredAt: Number(payload.occurredAt ?? Date.now()),
    deleted: false,
    moderation: "",
  });
  state.chat = state.chat.slice(-DEFAULT_MAX_CHAT);
}

function applyChatDeleted(state, payload) {
  const messageId = String(payload.messageId ?? "");
  const message = state.chat.find((entry) => entry.messageId === messageId);
  if (message) {
    message.deleted = true;
    message.moderation = String(payload.reason ?? "moderated");
  } else {
    state.chat.push({
      messageId,
      user: "moderator",
      text: "Message removed",
      occurredAt: Date.now(),
      deleted: true,
      moderation: String(payload.reason ?? "moderated"),
    });
  }
}

function applyChatModeration(state, payload, action) {
  state.chat.push({
    messageId: String(payload.reportId ?? cryptoRandomId()),
    user: "moderation",
    text: `Message ${String(payload.messageId ?? "")} ${action}`,
    occurredAt: Date.now(),
    deleted: false,
    moderation: action,
  });
  state.chat = state.chat.slice(-DEFAULT_MAX_CHAT);
}

function ensureAuction(state) {
  if (state.auction) return;
  state.auction = normalizeSnapshot({ auctionId: state.auctionId }).auction;
}

function cryptoRandomId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `local_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}
