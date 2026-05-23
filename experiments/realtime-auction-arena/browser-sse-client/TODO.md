# Browser Client TODO (SemanticScript SSR)

This subproject is the bidder-facing client for the Realtime Auction Arena. It
is a **separate SemanticScript web application** that **server-renders** its
pages (the same pattern as `apps/taskforge-web`), not a static JS SPA. The point
of the experiment is to exercise SemanticScript's language/runtime — so the UI
is authored in `.sem` (`html template` / `html body template` + typed
`HtmlFragment` components), and JavaScript is used only for the small live-update
layer the server cannot push declaratively.

## Architecture (decided)

- **Separate `.sem` webServer** on `127.0.0.1:18090` (the API server stays on
  `:18083`). Built with `python SemanticScript/tools/sem.py build
  experiments/realtime-auction-arena/browser-sse-client`.
- **SSR from the shared SQLite database.** The native runtime exposes **no
  outbound HTTP client** (`standard.http` has only server + SSE primitives), so
  this app cannot call the API over HTTP from its handlers. Instead it opens the
  API server's `auction_arena.sqlite3` (via `standard.sqlite`, read-only) and
  renders current auction state directly — exactly how `taskforge-web` renders
  from its own SQLite. The two processes share the file (SQLite WAL allows
  concurrent readers + the API's single writer).
- **CDN Tailwind** in the page head (matching `taskforge-web`); a `vNext` refine
  can vendor it under `assets/`.
- **Thin JS live layer** (`assets/floor.js`, served via `/assets/:filename`):
  refreshes the price/winner/countdown/feed/chat by polling a **same-origin**
  live endpoint on this app that re-reads the DB, plus a local countdown ticker.
  No client framework.

```text
browser-sse-client/
  build.sem              webServer build plan (port 18090, modules below)
  main.sem               webServer decl, route table, capabilities, shared-DB
                         open, static asset handler, /health. (route wiring only)
  pages/main.sem         Lobby + Floor + 404 html templates and page handlers;
                         reads the shared DB and hydrates templates -> text/html.
  components/main.sem     HtmlFragment renderers (head/Tailwind, top bar, status
                         chip, auction card, stage, bid form, chat, feed).
  assets/floor.js        live-update layer (poll same-origin fragment + ticker).
  assets/styles.css      small custom CSS beyond Tailwind utilities (optional).
```

## Pages (server-rendered)

- [ ] **Lobby `GET /`** — server-renders the open-auction grid by querying
      `auctions` (id, title, status, current_bid_minor, closes_at). Each card
      links to `/floor/<auctionId>`. Header + connection note. Empty state when
      no rows.
- [ ] **Floor `GET /floor/:auctionId`** — server-renders the full current state
      for one auction: stage (title/description/status/current bid/winner),
      countdown seed (from `closes_at`), the most recent events
      (`auction_events`, newest first), and recent chat. Includes the bid + chat
      forms and loads `/assets/floor.js`.
- [ ] **404 `GET *`** — branded not-found page.
- [ ] **Live fragment `GET /floor/:auctionId/live`** — same-origin endpoint
      returning the current stage + feed + chat as JSON (or an HTML fragment)
      read fresh from the DB, for `floor.js` to patch the page between full
      loads.
- [ ] **`GET /health`** — readiness (DB open ok).

## Components (HtmlFragment renderers in components/main.sem)

- [ ] **Page head** — Tailwind CDN, font, `<title>`, inline theme tokens
      (floor-dark palette), shared `<meta>`.
- [ ] **Top bar** — brand + a connection indicator the JS toggles.
- [ ] **Status chip** — auction lifecycle (draft/running/closed/cancelled),
      colored by a `data-status` attribute (CSS-reactive).
- [ ] **Auction card** — lobby grid item (title, status, current bid, closes-in).
- [ ] **Auction stage** — item, status, current bid (mono, large), winner,
      countdown block.
- [ ] **Bid form** — amount + submit (posts to the API; see Interactivity gap).
- [ ] **Chat panel + message** — log + composer; deleted/reported states.
- [ ] **Event feed item** — type-colored row with amount + sequence + time.

## Live layer (assets/floor.js — minimal, well-commented)

- [ ] Countdown ticker from the server-seeded `closes_at` (no network).
- [ ] Poll `GET /floor/:id/live` every ~2.5s; patch price/winner/status/feed/chat
      DOM nodes in one rAF batch; flash price on increase, ripple on extend.
- [ ] Reduced-motion respected; stops when the auction is closed.

## Data mapping (shared DB columns -> view)

Read directly from the API server's schema. Amounts are integer **minor units**.
- `auctions`: `auction_id, title, description, status` (1 draft / 2 running /
  3 closed / 4 cancelled), `current_bid_minor, minimum_increment_minor,
  starting_bid_minor, revision, closes_at, accepted_bid_count,
  last_bidder_user_id, current_winner_user_id`.
- `auction_events`: `sequence, event_type, payload_json, created_at`.
- `chat_messages`: `message_id, author_user_id, status, body_text, created_at`.

## Verification

- [ ] `sem.py build` compiles clean; `ascc --lint --parse-only` passes for new
      `.sem` files (project rule).
- [ ] Run the API server (writes the DB), seed an auction, then run this app and
      confirm Lobby + Floor render the live state.
- [ ] Subagent review loop: SSR correctness, design/a11y, `.sem` spec compliance.

## Current state (2026-05-23)

- The SSR app **compiles, runs, and renders**: `GET /` (Lobby), `GET *` (404),
  `GET /health`, `GET /assets/:filename`, and `GET /probe-api` all return 200
  with Tailwind-styled server-rendered HTML.
- **NEW: outbound HTTP client added to `standard.http`** (`clientGet`/`clientPost`,
  backed by one minimal native `ss_http_client_fetch` socket primitive; zero
  compiler changes). This replaces the rejected shared-DB approach — the client
  now talks to the API over HTTP like a real client.
- **The Floor renders REAL auction data over HTTP.** `/floor/:auctionId` calls
  `ensureApiToken` (logs in once via `http.clientPost`, caches the bearer token),
  builds the `Authorization: Bearer <token>` header + `/api/v1/auctions/<id>`
  path with `c.snprintf`, fetches the snapshot via `http.clientGet`, parses
  `data.auction.title` with `standard.json`, and server-renders the stage.
  Verified: 15 rapid loads all render the real title (token caching avoids the
  API's 10/60s login limit); degrades to "Auction unavailable" if the API is
  down. The Lobby renders the live `/healthz` status the same way.
- **Reviewed + refined.** A review subagent audited the C client + SSR handlers;
  applied fixes: recv/connect timeout (no hang of the single thread), strict
  `HTTP/`-prefixed status parse, and the token cache (rate-limit fix). Confirmed
  clean: no socket/memory leaks, buffer-safe request building, all heap bodies
  freed via `defer`, no post-free/unguarded pointers.

- **Floor scalar view COMPLETE with real data.** `/floor/:id` now renders the
  real title, status (statusCode -> text via `floorStatusTextFromCode`), current
  bid (`cursorInt64` -> money-formatted with `c.snprintf` `$%lld.%02lld`), and
  description - all parsed from the fetched snapshot. Verified live:
  `Vintage Moog Synthesizer / running / $125.00 / "A rare analog classic."`.

- **Lobby grid renders the real auction list over HTTP.** `/` fetches
  `/api/v1/auctions` (authed via the cached token), then a `storage local
  mutable` index loop over `cursorArrayLength`/`arrayElementAt` reads each
  auction's id/title/currentBid and accumulates card HTML into a `pointer.offset`
  buffer with `c.snprintf` (offset tracked via `c.strlen`). Verified live: 3
  auctions render as cards with real titles, money-formatted prices
  ($100/$200/$300), and working `/floor/<id>` links. Capped at 20 cards.

- **Security hardened (review cycle 2).** A second review found + we fixed:
  (B1) the lobby card `snprintf` now bounds by remaining buffer capacity
  (`gridBufferCapacityI64 - lobbyOffset`) instead of a fixed size - no heap
  overflow; (B2) stored-XSS - the lobby escapes card titles via the new
  `http.escapeHtml` (raw `HtmlFragment` path), and the Floor relies on the
  hydrator's automatic String-hole escaping (manual escape there was removed
  after it caused double-escaping). Verified live with a `<script>` title:
  single-escaped on both surfaces, no raw injection, no double-escape.

### Remaining (smaller polish)

1. **Event feed + chat lists** on the Floor — same proven array-loop pattern as
   the Lobby grid; mechanical repeat.
2. **Winner + countdown.** `currentWinnerUserId` is absent from the snapshot JSON
   (server gap); seed `closesAtUtcMillis` into `data-closes-at` for `floor.js`.
3. **Re-login on 401** so an expired token self-heals without a restart.
4. **HTML-escape list text** — card titles are injected via `%s` without
   escaping; fine for server-controlled titles, but escape before untrusted input.

## Known gaps / risks (carried from the contract probe + this pivot)

- [ ] **No outbound HTTP client** in the runtime — this app reads the shared DB
      instead of calling the API. Interactive writes (bid/chat/login) still need
      the API server.
- [ ] **Interactivity + auth + CORS.** Bidding/chat/login are authenticated API
      actions on `:18083`; from this app's origin (`:18090`) the browser must do
      a cross-origin authenticated `fetch` (the API's CORS config must allow
      this origin). First milestone is read-only SSR + live refresh; wiring the
      authenticated write path is the next milestone.
- [ ] **Server: `rate_limited` masks DB-lock contention** (API
      `consumeLoginRateLimit` returns the same `false` for over-limit and a
      failed rate-limit transaction). Track as an API-side fix.
- [ ] **Server: single active session** — one access token process-wide; blocks
      a true multi-bidder demo until durable multi-session auth lands.
- [ ] **Server: chat event payload carries no text/author** — `chat.message.*`
      events persist only a stub, so chat content must be read from
      `chat_messages` directly (this app can, reading the shared DB).
