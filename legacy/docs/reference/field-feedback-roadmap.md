# Field Feedback Roadmap

This page tracks keep/change decisions and larger wishlist items that came out
of the Ops Dashboard full-build field report. It is intentionally narrower than
the public roadmap: each item here maps to concrete friction observed while
building a real web/SQLite app.

## Shipped Or Verified

| Item | Current decision |
|---|---|
| Redirect reason phrase | Shipped. The native HTTP reason table maps `303` to `See Other` and covers the common redirect family instead of falling back to `OK`. |
| Header ordering | Shipped. `semlint` reports `SS3619` when `http.responseHeader` runs after a response body/file/redirect writer. |
| Request value presence | Shipped. `http.requestValueIsEmpty` and `http.requestValueLength` cover nullable cookie/header/query values and treat `NULL` as empty. |
| Eval native-runtime refusal | Shipped. `sem eval` reports `native-runtime-unavailable` with `execution.ran: false` before launching snippets that call native adapters. |
| Packaged component paths | Shipped. Packaged `sem version --json` reports logical `packaged://SemanticScript/...` component paths instead of PyInstaller extraction paths. |
| WAL sidecars | Shipped. `sem new` `.gitignore` includes `*.db-wal` and `*.db-shm`. |
| Server-wide route opt-outs | Shipped. `routeTimeoutOptOut SERVER "*"` and `routeMiddlewareOptOut SERVER "*"` suppress per-route coverage drift for intentional app-wide defaults. |
| Enum comparisons | Shipped. `EnumName.equal` and sibling comparison methods dispatch through the enum representation and preserve named cases in executable code. |
| SQLite changed-row signal | Shipped. `sqlite.changedRowCount` is documented, and `SS3641` nudges mutation paths that do not inspect it. |
| Static routes | Shipped. `staticRoute` serves a directory with traversal protection, cache headers, and conditional 304 handling. |
| Redirect helper | Shipped. `http.redirect` combines `Location` plus the empty response body pattern. |
| SQLite scalar read helper | Shipped. `sqlite.queryScalarInt64` owns prepare/step/column/finalize for static no-parameter scalar reads. |
| WAL project policy | Shipped. `sqliteJournalMode PROJECT wal` applies WAL after `sqlite.openDatabase`. |
| Checked fallible run | Shipped. `runChecked CALL ok VALUE TYPE error ERROR TYPE else LABEL` covers the compact checked-call form that still preserves success and error names. |

## Documented Decisions

| Item | Decision |
|---|---|
| Webserver entrypoints | Keep. Routed webserver programs omit `entry`; routes and startup/shutdown hooks are the entry surface. |
| Build tape precedence | Keep and document. When compiling through `build.sem`, build-tape rows own project selection and registered module source wins over standalone source headers. |
| `SqliteOpenMode` values | Keep as pre-composed flag choices for now. The public cases are the common SQLite flag combinations, not arbitrary enum ordinals. |
| `releaseMemoryBytes` result | Keep infallible. Free/release is a cleanup action; invalid/double-free remains a programming error caught by ordering/lifetime checks rather than a recoverable Result. |
| Hydrated template whitespace | Keep for now. Island trailing whitespace is source data and folded fragments preserve it; trimming requires an explicit formatter/runtime policy. |
| `c.snprintf` varargs | Keep current call shape but document it as variadic. The fixed inputs are `buffer`, `bufferSize`, and `format`; additional argument rows follow the format string. |
| `sem build .` output | Keep pass-through explicitness for now. Use `sem build PATH -- --emit-exe` when the desired artifact is a linked executable; `sem build` remains a compiler-driver wrapper. |
| Docs result shape | Change later. Consolidating `name`, `fullName`, `qualifiedName`, and empty `operation` fields needs a schema version bump or compatibility bridge. |
| HTTP status constants | Change later. Add named `HttpStatusCode` constants such as `httpStatusOk` and `httpStatusSeeOther` so handlers stop carrying raw integers. |
| Server startup banner | Change later. Route framework-owned startup output through the future logging/observability surface and allow project-level opt-out. |

## Planned Dev-Loop Tools

| Proposal | Intended shape |
|---|---|
| `sem serve [PATH] [--watch] [--port N]` | Build, launch, and restart a `webServer` target on source changes. |
| `sem db [PATH] [--sql "..."] [--schema] [--counts]` | Inspect a project's SQLite database without adding an app endpoint. |
| `sem fix --apply-conventions` | Apply safe naming convention repairs from `SS4001`, `SS4002`, `SS4003`, and future mechanical rules. |
| `sem effects --suggest OP` | Generate applyable `effect`/`authority` rows from called target contracts. |
| `sem doctor --target webServer --linkability` | Report call targets that check syntactically but will not link for the selected target. |
| `sem new --add-resource NAME` | Generate a CRUD slice with table, list, create, toggle, JSON, and smoke-test scaffolding. |

## Planned Discovery And Recipe Tools

| Proposal | Intended shape |
|---|---|
| `sem recipes list|get NAME` | Curated, verified end-to-end patterns for row loops, fragment folding, form posts, session auth, JSON arrays, and transactions. |
| `sem docs how "intent"` | Intent-keyed search that returns recipes and patterns, not only target docstrings. |
| `sem docs get TYPE --members` | Return enum cases and record fields for type lookups. |

## Planned Web And HTTP APIs

| Proposal | Intended shape |
|---|---|
| `http.setCookie` | Typed cookie writer with `HttpOnly`, `SameSite`, `Secure`, `Max-Age`, and `Path` attributes. |
| `http.form` / `form.field` | Form reader that owns scratch, URL-decodes fields, and can require non-empty values. |
| `requireSession SERVER ROUTE lookupOp` | Declarative session gate that short-circuits unauthorized requests and exposes the authenticated user. |
| Bounded body reader | Configurable `http.requestBodyText`/`requestBodyBytes` limit with a handler-visible 413 path. |

## Planned SQLite APIs

| Proposal | Intended shape |
|---|---|
| `sqlite.queryText` | One-shot text scalar reader with the same ownership clarity as `sqlite.queryScalarInt64`. |
| `sqlite.queryRows` | Iterator/callback helper that owns prepare/bind/step/finalize for row loops. |
| Transaction scope | First-class `BEGIN IMMEDIATE`/`COMMIT`/rollback-on-error block that linter transaction checks understand. |
| `expectChangedRows` | Fallible mutation assertion for "exactly N rows changed" flows. |

## Planned Language And Testing Work

| Proposal | Intended shape |
|---|---|
| `branch case VALUE is ENUM_TOKEN target LABEL` | Branch directly on enum cases without constructing an explicit comparison call. |
| Template loops and `html.join` | First-class repeated HTML rendering instead of hand-folded nested hydration. |
| `text.format`, `text.fromInt64`, `text.concat` | Native bounded string building that avoids raw `c.snprintf` in app code. |
| Generated JSON record codecs | `json.stringify.Record` and `json.parse.Record` from record metadata, with real validation and cleanup rows. |
| Effect inference or helper inheritance | Reduce pass-through helper boilerplate without hiding observable authority. |
| Web-handler test fixture | In-process `HttpRequest`/`TestResponse` helpers and assertions under `sem test`. |
