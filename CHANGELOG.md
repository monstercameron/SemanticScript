# Changelog

All notable changes to SemanticScript are recorded here. This file covers the
restructured `semanticscript/` package era; the detailed dated history from
before the repository reorganization (the AgentScript → EAV → SemanticScript
lineage, ~700 commits) lives in [`legacy/CHANGELOG.md`](legacy/CHANGELOG.md).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).
No versioned releases have been cut yet; the source compatibility contract is
tracked separately as `CONTRACT_VERSION` (currently `eav-0.3.1`).

## Unreleased

### Apps — all seven `apps/` now run end-to-end

The X-040…047 application ports went from "lints/lowers" to "actually runs",
each verified by `tests/test_apps.py` (run → assert real behavior, not just a
clean parse):

- **APP-RUN-0** `html-template-lab` — e2e-tested; established the extensible app
  harness (console / server-backed / webServer / CRUD / TUI runners).
- **APP-RUN-1** `taskforge-api-client` — a self-contained winsock HTTP-GET client
  (`net.fetchText`); runs against a local fixture server.
- **APP-RUN-2** `taskforge-tui` — the interactive TODO TUI renders its table and
  saves+exits cleanly under a scripted keystroke stream. `ss_c_terminalReadKey`
  reads one byte from stdin and reports Esc on EOF so the state machine runs
  headlessly.
- **APP-RUN-3** `event-stream-smoke` — an in-process pub/sub event runtime
  (`event.*`: stream queue + per-subscription cursor).
- **APP-RUN-4** `desktop-window-smoke` — a headless widget runtime (`gui.*`) so
  the control tree + event wiring run non-interactively.
- **APP-RUN-5** `http-runtime-gauntlet` — the `webServer` codegen target: the
  lowered `webServer` entity synthesizes the route table and serves real HTTP.
- **APP-RUN-6** `taskforge-web` — the full JSON REST API runs a live
  register → login → create-todo → list round-trip against real sqlite + bcrypt
  + json + log.

### Added

- **`webServer` codegen target** — a `webServer` entity lowers to an `i32()`
  entry that builds parallel method/path/handler route arrays and calls
  `ss_http_serve_routes`, which assembles the server config and runs the socket
  loop.
- **`pointer.*` intrinsics** — `pointer.offset` / `pointer.loadByte` /
  `pointer.storeByte`: byte-addressed reads/writes over an `OpaquePointer`
  (Int64 address).
- **`c.*` libc seam shims** (`semanticscript/runtime/ss_libc.c`) — `malloc`,
  `free`, `memset`, `memmove`, `strcmp`, `strlen`, `atoll`, `cString`,
  `putchar`, `puts`, `fflush`, `fopen`, `fclose`, `fgets`, `terminalReadKey`,
  plus variadic `printf` / `fprintf` / `snprintf` forwarding to their
  `v*`-counterparts. Declared with explicit `Int64` / `const char*` signatures
  so app types match exactly (no implicit coercion).
- **Family + low-level runtime shims** — direct-return shims over the native
  out-param APIs for JSON (`ss_json.c`) and structured logging, plus
  password-hashing / CSPRNG / base64url (`ss_bcrypt`), an event pub/sub runtime
  (`ss_event.c`), and a headless widget runtime (`ss_widget.c`).
- **`JsonText` `body json` islands** now embed their indented text as a String
  constant (static JSON response bodies).
- **App e2e harness** (`tests/test_apps.py`) — console, server-backed,
  webServer-probe, stateful CRUD round-trip, and scripted-TUI runners.

### Changed

- **Repository restructured** into a scalable layout: the compiler now lives in
  `semanticscript/{compiler,runtime,std,sigs,packaging}` with `examples/`,
  `apps/`, `tests/`, `docs/` as siblings. The previous implementation moved to
  `legacy/`.
- **Renamed throughout** — the tool/CLI/toolchain/env var `eavc` → `semanticscript`;
  the runtime symbol prefix `eav_` → `ss_`.
- **The native runtime is self-contained** — ported out of `legacy/` into
  `semanticscript/runtime/native_*` (sqlite, http, async, win32_gui, json,
  bcrypt, log) so the compiler no longer reaches into the deprecated tree (zero
  `legacy/` references in the runtime manifest).
- **"EAV" branding removed from all documentation** (kept in source code where
  it is the row model's name); docs say "SemanticScript".
- **GitHub Actions wired** to the new compiler; legacy-product workflows no
  longer auto-run.
- **`compare.<op>Int32`** resolves an enum-variant operand (e.g.
  `ScreenMode EditMode`) by its declared type → the i32 discriminant, instead of
  forcing the suffix `Int32` hint.

### Fixed

- **JIT runtime-DLL keepalive** — `_register_runtime_symbols` loaded each native
  library into a local `ctypes.CDLL` that was garbage-collected on return, so on
  Windows the DLL was unmapped before `finalize_object` baked the addresses into
  the call sites, leaving runtime symbols resolved to **null** (a webServer entry
  observably "called 0x0"). DLLs are now held for the process lifetime.
- **`c.snprintf` / `printf` / `fprintf` resolution on Windows** — the UCRT
  versions are header inlines with no exported symbol, so a direct MCJIT
  relocation could not resolve and its failure cascaded, zeroing nearby call
  sites. These now bind to exported `ss_c_*` shims.
- **`c.cString` symbol mismatch** — emitted as `ss_c_cString` but the shim was
  `ss_c_cstring`.
- **`ss_json_read_string`** returns `""` (never `NULL`) for an absent optional
  field, so an optional value can't propagate a null into a `NOT NULL` bind.
- **`return nil` on a `Result` op** returns the OK-type null sentinel rather than
  the Err value (which is a different IR type than the function result).
- **Owned-resource handles** are backed by an entry-block stack slot so a
  deferred cleanup re-emitted at multiple return points dominates every exit.
- **`fmt -` over a pipe** corrupted non-ASCII source on Windows (cp1252) because
  the child's `sys.stdin` was not UTF-8-reconfigured.

### Known gaps (pre-release)

- Validated on Windows/ARM64 only; the Linux/macOS test matrix and GitHub CI
  have not yet been run green.
- `build` (native exe) works for console targets; a `webServer` target fails to
  link (`subsystem must be defined`).
- No user-facing install/quickstart README (the root `README.md` is the language
  spec) and no packaging/distribution metadata yet.
- The broader language-completeness roadmap (crash-report tiers, non-bypassable
  compile gate + syscall sandbox, linter parity, the ≥150-app conformance
  corpus, the value-model free/move runtime) is tracked in
  [`docs/todos.md`](docs/todos.md).
