# Browser SSE Client TODO

This checklist belongs to the browser bidder client. The server TODO tracks only
server behavior.

## Verified Scaffold

- [x] Create `src/index.html`, `src/styles.css`, `src/app.js`, `src/api.js`,
      and `src/state.js`.
- [x] Add login/session, auction snapshot, bid form, price/winner/countdown,
      event feed, and chat panel UI scaffolds.
- [x] Add client-side EventSource/reconnect/replay code paths against the
      planned versioned SSE route.
- [x] Add a lightweight browser smoke-test artifact.

## Not Working Until Server APIs Exist

- [ ] Authenticate against real `POST /api/v1/auth/login`.
- [ ] Display authenticated `GET /api/v1/session`.
- [ ] Load real auction snapshots from persisted server state.
- [ ] Submit real bids through `POST /api/v1/auctions/:auctionId/bids`.
- [ ] Render live SSE events from `GET /api/v1/auctions/:auctionId/events`.
- [ ] Send and receive persisted chat messages.
- [ ] Validate browser reconnect and replay against the live server.
