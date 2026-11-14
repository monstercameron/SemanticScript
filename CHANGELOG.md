# Changelog

All notable changes to SemanticScript are recorded here. This file covers the
restructured `semanticscript/` package era; the detailed dated history from
before the repository reorganization (the AgentScript → EAV → SemanticScript
lineage, ~700 commits) lives in [`legacy/CHANGELOG.md`](legacy/CHANGELOG.md).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).
No versioned releases have been cut yet; the source compatibility contract is
tracked separately as `CONTRACT_VERSION` (currently `eav-0.3.1`).

## 0.4.0-beta.1 (unreleased)

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
- **Release engineering** — `version.json` (release version source-of-truth,
  distinct from the `CONTRACT_VERSION` source-compat contract),
  `THIRD_PARTY_LICENSES.md` (SQLite / libuv / crypt_blowfish / llvmlite+LLVM /
  CPython attribution), and this `CHANGELOG.md`.
- **Agentic toolchain (TOOL-0…8)** — the legacy `sem` agent tools ported and
  upgraded to the EAV language: `emit-ir`/`inspect-ir`, `status`/`clean`,
  `index`, `bench`, `repin`, and a unified **`search`** — relevance-ranked
  (TF-IDF) retrieval across the diagnostics, skills, task templates, the language
  guide, and a project's entities (the real agentic-coding search). Every agent
  surface returns a versioned `sem.<tool>.v1` JSON envelope (the legacy response
  structures, preserved).
- **MCP server expanded to 19 tools** — the stdio JSON-RPC server now exposes
  `search`, `explain`, `graph`, `query`, `index`, and `status` alongside the
  original set; the registry is data-driven so the advertised `inputSchema` and
  the argv it builds can't drift. Driven by `tests/test_mcp.py`.
- **Test gates** — `tests/test_cli_surface.py` (all 49 commands run + emit their
  documented shape), `tests/test_agent_tools.py` (the agent JSON tools), and
  `tests/test_mcp.py`, all wired into CI alongside the example/pytest/app suites.

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
- **Docs restructured around a front-door README** — `README.md` is now a
  user-facing landing page (the pitch, a runnable hello-world, core-concept
  intros, an ideas section, quickstart, and an honest beta-status block); the
  full language specification moved to [`docs/LANGUAGE.md`](docs/LANGUAGE.md).
  The search corpus, governance map, grammar pointer, and drift-guard test were
  repointed accordingly.
- **GitHub Actions wired** to the new compiler; legacy-product workflows no
  longer auto-run.
- **Release pipeline consolidated** to a single cross-platform `release.yml`
  (build the PyInstaller binary per-OS via `package.py`, smoke-test, publish with
  `SHA256SUMS`), replacing the legacy `prepare-release`/`publish-release`/`release`
  workflows that targeted the removed `vscode-semanticscript`/`sem.spec`/`mcpb`
  toolchain.
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
- **Native `build` of a `webServer` target** failed with `subsystem must be
  defined` — the entry isn't named `main`, so the linker couldn't infer the
  console subsystem. `build_executable` now emits a tiny C `main` that tail-calls
  the named entry.
- **Native `build` of console programs that print integers/floats** failed with
  `undefined symbol: printf` — Windows UCRT exposes `printf` only as a header
  inline (no exported symbol), so the IR's direct call was unresolved. A small
  always-linked anchor (`ss_native_libc.c`) provides a real `printf` that
  delegates to the exported `__stdio_common_vfprintf` (JIT path unaffected).

### Known gaps (pre-release)

- Validated on Windows/ARM64 only; the Linux/macOS test matrix has not been run.
  CI is Windows-only and has not yet run green on GitHub (the branch needs a push
  with the `workflow` scope). The runtime workarounds are Windows-toolchain
  specific (UCRT inlines `printf`/`snprintf`); POSIX exports them, so they are
  harmless no-ops there, but this is unverified.
- The single-file release pipeline (`release.yml` → `package.py`, with
  `version.json` + `SHA256SUMS` + `THIRD_PARTY_LICENSES.md`) is wired but has not
  yet run on a tag. There is no `pip`-installable package (the distribution model
  is the frozen single-file binary).
- Toolchain parity with the legacy `sem` is functionally complete (TOOL-0..8:
  MCP + agentic CLI tools, `emit-ir`/`inspect-ir`, `status`/`clean`,
  `index`/`search`, `bench`, `repin`). Of the legacy-only commands, `get`/`list`/
  `help`/`reference`/`bootstrap` are superseded by better-shaped new surfaces
  (`docs --get`/`describe`, `index`/`symbols`, `agent-docs`/`task`,
  `skills`/`search`), and `migrate-syntax` is obsolete. Still genuinely open: the
  **network/registry ops** (`download`/`latest`/`self`/`update`) — they need a
  package registry that doesn't exist yet; the offline pieces (`deps`,
  `repin`/`mod_tidy` with MVS + a lock) are in place — plus two niche utilities
  (`compare-profiles`, `literal`).
- The broader language-completeness roadmap (crash-report tiers, non-bypassable
  compile gate + syscall sandbox, linter parity, the ≥150-app conformance
  corpus, the value-model free/move runtime) is tracked in
  [`docs/todos.md`](docs/todos.md).
