# Win32 Auctioneer TODO

This checklist belongs to the Win32 auctioneer control app. The server TODO
tracks only server behavior.

## Verified Scaffold

- [x] Create `src/main.sem`, `src/controls.sem`, `src/auth.sem`,
      `src/auction_api.sem`, `src/view_model.sem`, and
      `src/event_polling.sem`.
- [x] Add login, item configuration, start/extend/close, status, event/audit,
      rejected-bid, chat moderation, and HTTP error display contracts.
- [x] Add build and `*.test.sem` coverage markers.
- [x] Add packaging/resource plan.

## Not Working Until Runtime And Server APIs Exist

- [ ] Build a real Win32 window from the contracts.
- [ ] Authenticate against real JWT login.
- [ ] Create/start/extend/close persisted auctions.
- [ ] Poll real snapshot/event routes.
- [ ] Moderate real persisted chat messages.
- [ ] Add GUI smoke test.
- [ ] Add async-safe HTTP and SSE/event subscription support if the Win32
      runtime exposes it cleanly.
