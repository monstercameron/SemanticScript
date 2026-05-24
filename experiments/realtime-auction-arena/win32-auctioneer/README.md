# Win32 Auctioneer Console

This subproject is the native desktop operator console. It should be a separate
SemanticScript Win32 executable that controls the auction server over local HTTP
APIs. It exists to prove that SemanticScript can build both the server and a
native GUI client for the same domain.

## Responsibilities

- Start or reset an auction.
- Log in as an `auctioneer` or `admin` and store the access JWT in memory.
- Configure item name, starting bid, minimum increment, and duration.
- Extend the running auction.
- Close the auction manually.
- Display current status, connected clients, current winner, and audit events.
- Surface rejected bids so the auctioneer can see bad input or suspicious
  behavior.
- Moderate auction-floor chat messages.

## Internal Shape

```text
src/
  main.sem                     Win32 GUI entrypoint
  controls.sem                 control IDs and layout helpers
  auction_api.sem              authenticated calls to the server HTTP API
  auth.sem                     login, refresh, and bearer-token handling
  view_model.sem               GUI state and formatting
  event_polling.sem            polling first, SSE subscription later

resources/
  app.manifest                 Windows app manifest later
  icons/                       icon resources later

tests/
  api_contract_tests.sem       request/response contract checks later
```

## Feature Pressure

The Win32 console stresses a different runtime surface:

- GUI event loop integration;
- async-safe UI updates from background HTTP calls;
- native HTTP client usage from desktop code;
- JWT bearer-token handling and refresh;
- cancellation when closing the window;
- typed JSON request/response records shared with the server;
- authenticated moderation commands;
- packaging and resource embedding.

## First Milestone

Use polling and simple HTTP commands before attempting live streaming:

1. Start the server separately.
2. Launch the Win32 console.
3. Log in and receive a JWT access token.
4. Press Start Auction and verify `POST /api/v1/auctions/:id/start`.
5. Press Extend and Close.
6. Poll `GET /api/v1/auctions/:id` every second for status.

Later, replace polling with an SSE or event subscription model if the runtime
can support it cleanly from a Win32 message loop.
