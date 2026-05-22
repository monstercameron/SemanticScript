import { createApiClient } from "./api.js";
import {
  applyEvent,
  applySnapshot,
  createInitialState,
  escapeHtml,
  formatDuration,
  formatMoney,
  millisecondsUntilClose,
  minimumAcceptedBid,
  normalizeEvent,
  toMinorUnits,
} from "./state.js";

const state = createInitialState();
const api = createApiClient(() => ({
  apiBaseUrl: state.apiBaseUrl,
  accessToken: state.accessToken,
}));

let eventSource = null;
let pollTimer = 0;
let countdownTimer = 0;

const dom = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheDom();
  loadPrefs();
  bindEvents();
  render();
  startCountdown();
});

function cacheDom() {
  for (const id of [
    "connectionPill", "connectionText", "auctionStatus", "auctionIdLabel",
    "auctionTitle", "auctionDescription", "itemImage", "currentBid",
    "currentWinner", "countdown", "serverTimeLabel", "timerBlock",
    "sessionRole", "sessionForm", "apiBaseUrl", "auctionIdInput",
    "displayNameInput", "accessTokenInput", "loginButton", "bidForm",
    "bidAmountInput", "bidButton", "minimumBidLabel", "lastRejectedBid",
    "chatMessages", "chatStatus", "chatForm", "chatInput", "chatButton",
    "eventFeed", "pollButton", "replayButton", "loginDialogTemplate",
  ]) {
    dom[id] = document.getElementById(id);
  }
}

function loadPrefs() {
  state.apiBaseUrl = localStorage.getItem("auction.apiBaseUrl") || "";
  state.auctionId = localStorage.getItem("auction.auctionId") || state.auctionId;
  state.displayName = localStorage.getItem("auction.displayName") || state.displayName;
  state.accessToken = sessionStorage.getItem("auction.accessToken") || "";

  dom.apiBaseUrl.value = state.apiBaseUrl;
  dom.auctionIdInput.value = state.auctionId;
  dom.displayNameInput.value = state.displayName;
  dom.accessTokenInput.value = state.accessToken;
}

function bindEvents() {
  dom.sessionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    updateConfigFromInputs();
    await connect();
  });

  dom.loginButton.addEventListener("click", showLoginDialog);
  dom.pollButton.addEventListener("click", () => pollSnapshot({ userInitiated: true }));
  dom.replayButton.addEventListener("click", () => reconnectSse({ replay: true }));

  dom.bidForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await placeBid();
  });

  dom.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendChat();
  });
}

async function connect() {
  setConnection("connecting", "Connecting");
  stopPolling();
  closeSse();

  try {
    await pollSnapshot({ userInitiated: true });
    openSse();
    startPolling();
  } catch (error) {
    setError(error);
    startPolling();
  }
}

async function pollSnapshot() {
  try {
    const snapshot = await api.getAuction(state.auctionId);
    applySnapshot(state, snapshot);
    setConnection(eventSource ? "live" : "polling", eventSource ? "Live" : "Polling");
    render();
  } catch (error) {
    setError(error);
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(pollSnapshot, 5000);
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = 0;
  }
}

function openSse({ replay = false } = {}) {
  closeSse();
  const lastId = replay ? state.lastEventId : "";
  const url = api.eventsUrl(state.auctionId, lastId);
  eventSource = new EventSource(url, { withCredentials: true });
  setConnection("connecting", "Streaming");

  eventSource.onopen = () => {
    setConnection("live", "Live");
    render();
  };

  eventSource.onerror = () => {
    setConnection("error", "Reconnecting");
    pollSnapshot();
  };

  eventSource.onmessage = (message) => {
    handleSseMessage(message);
  };

  for (const type of [
    "auction.created", "auction.started", "bid.accepted", "bid.rejected",
    "auction.extended", "auction.closed", "chat.message.created",
    "chat.message.deleted", "chat.message.reported", "heartbeat",
  ]) {
    eventSource.addEventListener(type, handleSseMessage);
  }
}

function reconnectSse({ replay = false } = {}) {
  openSse({ replay });
  pollSnapshot();
}

function closeSse() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function handleSseMessage(message) {
  if (!message.data) return;
  try {
    const parsed = JSON.parse(message.data);
    const event = normalizeEvent(parsed);
    if (message.lastEventId && !event.eventId) {
      event.eventId = message.lastEventId;
    }
    if (event.type !== "heartbeat") {
      applyEvent(state, event);
      render();
    }
    setConnection("live", "Live");
  } catch (error) {
    setError(error);
  }
}

async function placeBid() {
  const amount = Number(dom.bidAmountInput.value);
  if (!Number.isFinite(amount) || amount <= 0) return;

  dom.bidButton.disabled = true;
  try {
    const response = await api.placeBid(
      state.auctionId,
      Math.round(amount * 100),
      state.displayName,
      state.auction?.revision ?? 0,
    );
    applyCommandResponse(response);
    await pollSnapshot();
  } catch (error) {
    renderCommandError("bid.rejected", error);
  } finally {
    dom.bidButton.disabled = false;
  }
}

async function sendChat() {
  const text = dom.chatInput.value.trim();
  if (!text) return;

  dom.chatButton.disabled = true;
  try {
    const response = await api.sendChatMessage(state.auctionId, text, state.displayName);
    dom.chatInput.value = "";
    applyCommandResponse(response);
  } catch (error) {
    dom.chatStatus.textContent = error.message || "rejected";
  } finally {
    dom.chatButton.disabled = false;
  }
}

function applyCommandResponse(response) {
  if (!response) return;
  if (response.event || response.type || response.payload) {
    applyEvent(state, response.event ?? response);
  }
  render();
}

function renderCommandError(type, error) {
  applyEvent(state, {
    type,
    eventId: `local_${Date.now()}`,
    occurredAt: Date.now(),
    payload: {
      bidderDisplayName: state.displayName,
      amount: toMinorUnits(Number(dom.bidAmountInput.value) * 100),
      reason: error.code || error.message || "rejected",
      currentBid: state.auction?.currentBid ?? 0,
      minimumAcceptedBid: state.auction?.minimumAcceptedBid ?? 0,
    },
  });
  render();
}

function showLoginDialog() {
  const dialog = dom.loginDialogTemplate.content.firstElementChild.cloneNode(true);
  const form = dialog.querySelector("form");
  const button = dialog.querySelector("#confirmLoginButton");
  document.body.append(dialog);
  dialog.showModal();

  form.addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault();
    button.disabled = true;
    try {
      const result = await api.login(form.elements.username.value, form.elements.password.value);
      state.accessToken = result.accessToken || result.token || "";
      state.session = {
        role: result.role || result.user?.role || "bidder",
        userId: result.userId || result.user?.userId || "",
        displayName: result.displayName || result.user?.displayName || state.displayName,
      };
      dom.accessTokenInput.value = state.accessToken;
      sessionStorage.setItem("auction.accessToken", state.accessToken);
      render();
      dialog.close();
    } catch (error) {
      button.disabled = false;
      form.dataset.error = error.message || "Login failed";
    }
  });

  dialog.addEventListener("close", () => dialog.remove());
}

function updateConfigFromInputs() {
  state.apiBaseUrl = dom.apiBaseUrl.value.trim();
  state.auctionId = dom.auctionIdInput.value.trim() || "A1";
  state.displayName = dom.displayNameInput.value.trim() || "Browser Bidder";
  state.accessToken = dom.accessTokenInput.value.trim();

  localStorage.setItem("auction.apiBaseUrl", state.apiBaseUrl);
  localStorage.setItem("auction.auctionId", state.auctionId);
  localStorage.setItem("auction.displayName", state.displayName);
  sessionStorage.setItem("auction.accessToken", state.accessToken);
}

function render() {
  const auction = state.auction;
  const currency = auction?.policy?.currency || "USD";

  dom.connectionPill.dataset.status = state.connection;
  dom.connectionText.textContent = state.lastError && state.connection === "error"
    ? state.lastError
    : connectionLabel(state.connection);
  dom.sessionRole.textContent = state.session.role || "viewer";
  dom.auctionIdLabel.textContent = auction?.auctionId || state.auctionId;
  dom.auctionStatus.textContent = auction?.status || "Loading";
  dom.auctionTitle.textContent = auction?.item?.title || "Waiting for auction snapshot";
  dom.auctionDescription.textContent = auction?.item?.description || "Connect to a server auction to begin.";
  dom.itemImage.src = auction?.item?.imageUrl || "../assets/item-placeholder.svg";
  dom.currentBid.textContent = formatMoney(auction?.currentBid ?? 0, currency);
  dom.currentWinner.textContent = auction?.currentWinner || "No bids yet";
  dom.minimumBidLabel.textContent = `${formatMoney(auction?.minimumAcceptedBid ?? 0, currency)} min`;
  dom.bidAmountInput.placeholder = minimumAcceptedBid(state).toFixed(2);
  dom.bidButton.disabled = auction?.status === "closed" || auction?.status === "cancelled";

  renderCountdown();
  renderRejectedBid(currency);
  renderEvents(currency);
  renderChat();
}

function renderCountdown() {
  const remaining = millisecondsUntilClose(state);
  const status = state.auction?.status || "";
  dom.countdown.textContent = status === "closed" ? "Closed" : formatDuration(remaining);
  dom.serverTimeLabel.textContent = state.snapshot?.serverTime
    ? new Date(state.snapshot.serverTime).toLocaleTimeString()
    : "Server time unknown";

  if (Date.now() - state.extendedAt < 1200) {
    dom.timerBlock.classList.add("extended");
  } else {
    dom.timerBlock.classList.remove("extended");
  }
}

function renderRejectedBid(currency) {
  const rejection = state.rejectedBids[0];
  if (!rejection) {
    dom.lastRejectedBid.hidden = true;
    dom.lastRejectedBid.textContent = "";
    return;
  }

  dom.lastRejectedBid.hidden = false;
  dom.lastRejectedBid.textContent = `${rejection.bidder || "Bidder"} rejected: ${humanizeReason(rejection.reason)} at ${formatMoney(rejection.amount, currency)}`;
}

function renderEvents(currency) {
  dom.eventFeed.replaceChildren(...state.events.map((event) => {
    const li = document.createElement("li");
    li.dataset.kind = event.type;

    const title = document.createElement("strong");
    title.textContent = eventTitle(event, currency);

    const meta = document.createElement("p");
    meta.textContent = `${event.type} - ${new Date(event.occurredAt).toLocaleTimeString()}${event.sequence ? ` - #${event.sequence}` : ""}`;

    li.append(title, meta);
    return li;
  }));
}

function renderChat() {
  dom.chatMessages.replaceChildren(...state.chat.map((message) => {
    const article = document.createElement("article");
    article.className = "chat-message";

    const author = document.createElement("strong");
    author.textContent = message.deleted ? "moderated" : message.user;

    const text = document.createElement("p");
    text.textContent = message.deleted ? `Message removed: ${message.moderation}` : message.text;

    article.append(author, text);
    return article;
  }));
}

function startCountdown() {
  if (countdownTimer) window.clearInterval(countdownTimer);
  countdownTimer = window.setInterval(renderCountdown, 1000);
}

function setConnection(connection, label) {
  state.connection = connection;
  state.lastError = label || "";
  render();
}

function setError(error) {
  state.connection = "error";
  state.lastError = error.message || "Connection error";
  render();
}

function connectionLabel(connection) {
  if (connection === "live") return "Live";
  if (connection === "polling") return "Polling";
  if (connection === "connecting") return "Connecting";
  if (connection === "error") return state.lastError || "Error";
  return "Offline";
}

function eventTitle(event, currency) {
  const payload = event.payload || {};
  switch (event.type) {
    case "bid.accepted":
      return `${payload.bidderDisplayName || payload.bidder || "Bidder"} bid ${formatMoney(payload.amount, currency)}`;
    case "bid.rejected":
      return `${payload.bidderDisplayName || payload.bidder || "Bidder"} rejected: ${humanizeReason(payload.reason)}`;
    case "auction.extended":
      return `Auction extended${payload.seconds ? ` by ${payload.seconds}s` : ""}`;
    case "auction.closed":
      return `Closed with ${payload.winner || payload.winnerDisplayName || "no winner"}`;
    case "chat.message.created":
      return `${payload.user || payload.displayName || "User"} posted chat`;
    case "chat.message.deleted":
      return `Chat removed: ${payload.reason || "moderated"}`;
    case "auction.started":
      return "Auction started";
    case "auction.created":
      return "Auction created";
    default:
      return event.type;
  }
}

function humanizeReason(reason) {
  return escapeHtml(reason || "rejected").replaceAll("_", " ");
}
