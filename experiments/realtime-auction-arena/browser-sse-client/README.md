# Browser SSE Client

This subproject is the bidder-facing browser client. It should be a static
HTML/CSS/JavaScript app that renders server-owned auction events. The client is
intentionally not authoritative: it displays state and submits commands, but
the SemanticScript server decides every rule outcome.

## Responsibilities

- Render item name, current bid, current winner, countdown, and bid history.
- Connect to `GET /api/v1/auctions/:auctionId/events` with `EventSource`.
- Submit bids to `POST /api/v1/auctions/:auctionId/bids`.
- Submit chat messages to
  `POST /api/v1/auctions/:auctionId/chat/messages`.
- Show accepted and rejected bid events immediately.
- Render auction-floor chat messages and moderation events from the same SSE
  stream.
- Recover from reconnect by fetching `GET /api/v1/auctions/:auctionId`.
- Carry the server's JWT/session cookie on API calls once auth is enabled.
- Stay framework-free unless the demo clearly needs more structure.

## Internal Shape

```text
src/
  index.html                   bidder UI shell
  styles.css                   auction-floor visual design
  app.js                       EventSource connection and rendering
  api.js                       fetch wrappers for auth, snapshot, bids, chat
  state.js                     client-side render model

assets/
  item-placeholder.svg         temporary item art
  sound/                       optional bid/close notification sounds later

tests/
  client-render.test.js        lightweight DOM/render tests later
```

## Screens

- Live auction floor with large current price.
- Bid form with bidder name and amount.
- Login/session panel once JWT auth is enabled.
- Countdown timer with extension animation.
- Event feed with accepted, rejected, extended, and closed events.
- Chat panel with rate-limit and moderation feedback.
- Reconnect/offline state.

## Feature Pressure

The browser client should keep pressure on server/runtime features:

- SSE event IDs and replay since last event;
- heartbeat events and disconnect handling;
- stable JSON event schemas;
- JWT/cookie-authenticated browser requests;
- chat events multiplexed with auction events;
- replay after `Last-Event-ID`;
- static asset serving from the SemanticScript server;
- response errors that are useful enough for UI display;
- multiple simultaneous browser clients.

## First Milestone

Start with polling:

1. Load `GET /api/v1/auctions/:auctionId`.
2. Render snapshot state.
3. Submit bids.
4. Refresh snapshot after each bid.

Then switch to SSE once the server can hold streaming responses open and
broadcast events. After SSE is stable, add chat over POST plus the same SSE
stream.
