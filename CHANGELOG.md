# Changelog

All notable changes to SemanticScript are recorded here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### The runtime in SemanticScript, stage 1

- The primitive layer (D-120 to D-124): the `use` effect verb; the standard
  modules `machine` (addresses, loads and stores, `copy`, `fill`,
  `compare`, a static state block) and `system` (kernel32 functions, called
  directly), each granted like any authority (`use machine.memory`,
  `use system.calls`); and `abi c "<symbol>"`, which exports an operation
  to C.
- `semanticscript/runtime`: the first slice of the runtime written in
  SemanticScript (entry, output, traps with stack traces, recursion depth,
  regions, integer text, `memcpy` and the like), with its own tests.
- `refined build --kind executable --runtime semanticscript` links a program
  with it and no C library; the executable imports from KERNEL32.dll alone.
  42 of the suite's 76 running programs build this way and behave exactly
  as under `refined run`; the others are refused, naming what they need.
  The C runtime stays the default.

### The runtime in SemanticScript, stage 2

- Floating-point text in SemanticScript (D-125, D-129): `refined_write_float`,
  `refined_format_float`, and `refined_parse_float` write a Float64 exactly as
  `refined run` does (Python's repr: the shortest digits that read back,
  nearest the value) and read text correctly rounded, computed exactly with a
  new bignum module. Checked over a table of thousands of values against
  Python.
- The host library in SemanticScript (D-126, D-128, D-130): `refined_host`
  and its targets for byte buffers, maps, sets, `string.fromBytes`, and log
  lines, with handles that trap when used after their region is released,
  and `refined_handle_region`. New runtime modules `heap`, `tables`,
  `handles`, `bignum`, `floats`, and `host`.
- `convert.float64BitsToUInt64` and `convert.uint64BitsToFloat64` (D-127);
  `system` rows for the process heap (`GetProcessHeap`, `HeapAlloc`,
  `HeapReAlloc`, `HeapFree`).
- 49 of the suite's 76 running programs now build with the runtime in
  SemanticScript and no C library; a program calling a host target that
  runtime lacks is refused (R901), naming it.
- Fixed: the C runtime wrote `100.0` as `1e+02`, `1e15` as `1e+15`, NaN as
  `-nan(ind)`, and 17 digits for some values next to powers of two; it now
  writes what `refined run` writes. Host targets whose names hold digits
  (`buffer.appendInt64`) are now seen by the executable's R901 check.

### The runtime in SemanticScript, stages 3 and 4

- Files, directories, claims, and scopes (D-132): every `fs` target, paths
  resolved as Python's `normcase(realpath())` resolves them, one writer per file
  by path and by file identity, and the D-38 scope check inside `refined_host`;
  the environment, the program's arguments (split as `CommandLineToArgvW` splits
  them, written in SemanticScript), `console.readLine`, child processes with
  `process.run` and `runCaptured`, deadlines, the clocks, and sleep.
- Tasks on fibers (D-131, D-133): a task runs when started until it waits or
  ends, then the next; groups, `awaitSlot`, a group's first error, cancellation
  that cuts a waiting task short, and deadlocks that trap with `refined run`'s
  message. Channels are host targets of this runtime (D-136). The test
  callbacks and `refined_block` are there too (D-134). `machine.taskEntry` and
  40 kernel32 `system` rows are new in the compiler.
- An executable is one LLVM module, the runtime and the program, with what the
  entry never reaches dropped (D-135): `hello` is 23 KB (145 KB before).
- Secrets, SHA-256 and HMAC-SHA-256, and foreign libraries (`ffi`), which the C
  runtime refuses, in SemanticScript too (D-137).
- 71 of the suite's 76 running programs, every conformance program that runs,
  every stage0 sample, the warehouse example on all its paths, and stage0
  itself build with `--runtime semanticscript`, import KERNEL32.dll alone, and
  behave exactly as under `refined run`; the other five need `net`, `http`,
  `json`, `random`, or `signal` (D-137).
- New runtime modules `slots`, `wide`, `tasks`, `files`, `processes`, and
  `hashes`; a trap now also stops child processes the program started (D-51).

### The runtime in SemanticScript, stage 5: the only runtime

- Linux (D-138 to D-140): the runtime reaches the kernel through raw system
  calls on x86_64 (`system.read`, `system.openat`, `system.mmap`,
  `system.fork`, ...; `system.linux()` is a constant of the target), with
  its own stacks (`machine.switchStack`, `startStack`, `runEntryOnStack`),
  its own heap over mmap, and a `_start` that hands `refined_entry` the
  kernel's stack. Executables are static, with no dynamic section and no C
  library. A new runtime module, `kernel`, holds what the Windows and Linux
  paths share.
- `refined build --kind executable` links the runtime in SemanticScript on
  Windows and Linux; it is the only runtime (D-141). `--runtime
  semanticscript` is still accepted; `--runtime c` and
  `semanticscript/compiler/refined/native_runtime.c` are gone. macOS is
  refused with R901 (no system layer yet).
- `refined build semanticscript/runtime --kind runtime --output runtime.o`
  writes the runtime as an object; stage0's C defines `refined_program_main`,
  calls no C library function, and links with it and no C library (D-142).
  The bootstrap fixed point holds.
- Tests that read the C runtime read the runtime's `hostTargets` table and
  its error constants instead (D-143); every conformance program, the
  cancellation check included, runs as an executable.

### The runtime in SemanticScript, stage 8: the whole C library

- stdio (D-156 to D-160): the runtime's C library has FILE streams buffered as
  glibc buffers them (fopen, freopen, fclose, fflush, fread, fwrite, fgetc, getc,
  getchar, fgets, ungetc, fputc, putc, putchar, fputs, puts, fseek, ftell,
  fgetpos, fsetpos, rewind, feof, ferror, clearerr, setvbuf, setbuf, remove,
  rename, tmpfile, tmpnam, perror), the printf family (every conversion, flag,
  and length, floating values with their exact digits, `%a`, `%n$`), and the
  scanf family with glibc's `__isoc99_` names. `abi library` rows may be
  `variadic`; on x86_64 calls through references are made as variadic calls, so
  printf works through `ffi` with doubles. The runtime's DSL takes expressions.
  Known gap: strerror gives `Unknown error N` for every number for now.
- Exit handlers (atexit, at_quick_exit, quick_exit, `_Exit`), ldiv and its kin returning a pair, setjmp and
  longjmp (routines the compiler emits), signal and raise, abort through SIGABRT, and system (D-162 to D-164).

### The runtime in SemanticScript: `ffi` everywhere

- A C standard library written in SemanticScript (D-153), the runtime module
  `clibrary`: ctype.h (glibc's class bits and tables), string.h, stdlib.h
  (`strtol` and its kin, `strtod`, `atoi`, `malloc` and its kin, `qsort`,
  `bsearch`, `getenv`, `exit`, `abort`, `div`), math.h's basics, and stdio.h's
  writes, each as glibc behaves in the C locale. `ffi.open("c")` binds it in
  an executable on Windows and on Linux alike (on Linux also `libc.so.6` and
  glibc's other parts); on Windows `c` no longer loads ucrtbase.
- A loader of ELF shared libraries for Linux (D-154), the runtime module
  `loader`: `ffi.open` of any other name finds, maps, relocates (RELATIVE,
  GLOB_DAT, JUMP_SLOT, 64; RELA, JMPREL, RELR), and initializes the library
  as `dlopen(RTLD_NOW)` would, resolving its C imports against the runtime's
  C library. Thread-local storage, ifuncs, text relocations, and symbols
  nothing defines are refused with a trap that says why.
- `ffi` is no longer refused on Linux (D-145): all 76 of the suite's running
  programs build as executables on Windows and Linux.
- The compiler (D-155): `abi library "<name>"` rows, `machine.cLibrary`,
  `machine.callComparison`, `machine.squareRoot`, and `system.archPrctl`.
- Tests: tests/ctour.py (the C library against glibc's results, and on Linux
  against `refined run`), tests/loadtour.py (a probe library compiled on the
  Linux runner, thousands of probes against the same library under ctypes and
  glibc, and the loader's refusals).

## 1.0.0 (2026-11-14)

### The language compiles its own compiler

- `docs/refined-examples/stage0` is a compiler written in SemanticScript: it
  reads a project, checks it is in its subset, writes C that links the
  native runtime, and builds it. Built once by the Python compiler, it
  compiles its own six modules (171 operations); the compiler that produces
  compiles them again to byte-identical C (`tests/test_bootstrap.py`).
- Everything it builds behaves as under `refined run`, and everything outside
  its subset is refused with a located message (`tests/test_stage0.py`,
  `tests/test_selfhost_suite.py`). An independent audit reproduced each
  claim. The bar and its evidence are in `docs/self-hosting-plan.md` (D-119).
- The safety analyses stay in `refined check`, which every program passes
  first.

### The refined compiler replaces the earlier toolchain

- The language was redesigned around two principles: nothing is implied, and
  every stated fact is checked. The design and every decision are in
  `docs/language-refinement.md`.
- New compiler in `semanticscript/compiler/refined/`: a lexer, one shape table
  for every row, a checker that enforces the whole design (diagnostic codes
  R101-R605), its own LLVM backend and JIT runtime, a test runner, a staleness
  flag for context rows, and a grammar generator for the docs and the editor.
- Worked example projects in `docs/refined-examples/`; `hello`, `sum`, and
  `factorial` run, and the self-hosting lexer and tokenizer pass their tests.
- The VS Code extension was rewritten around the refined compiler: generated
  highlighting, snippets, and check-on-save diagnostics.
- **Removed, with no backwards compatibility:** the earlier compiler
  (`semanticscript.py`), its standard library, signatures, C runtime, and
  packaging; the examples, apps, and experiments in the earlier syntax; the
  `legacy/` tree; vendored third-party C sources; the earlier test suite; the
  earlier docs (`LANGUAGE.md`, `GRAMMAR.md`, `ROADMAP.md`, `GOVERNANCE.md`, and
  others); and the CI workflows that built and released them. All of it remains
  in git history before this change.

### The self-hosted compiler compiles itself

- `docs/refined-examples/stage0`, a SemanticScript-to-C compiler written in
  SemanticScript, compiles projects of several modules (build.sem, names
  spelled `<module>.<name>`), maps with String keys, `forEach` over a map,
  `string.Position`, operation references, `<Record>.with`, `list.set`,
  operations raising standard errors, and scoped host targets (`fs`,
  `process.run`) given their capability scopes.
- It compiles its own source: built by `refined build --kind executable`, it
  builds a second compiler that compiles the samples to the same C and
  compiles stage0 again to byte-identical C (`tests/test_bootstrap.py`).
  Decisions D-114 to D-118.

### The checklist closed

- Library modules `random`, `crypto`, `log`, `json`, `secret`, `signal`, and
  `ffi`; file locks, append mode, directory operations, and process pipes.
- Stack traces on traps.
- Tools: `refined fmt`, `repl`, `lsp`, `bench`, a build cache, and
  `run --trace`, `--coverage`, `--profile`, and `--debug` with breakpoints.
- `refined build` emits objects, assembly, or WebAssembly for any LLVM target,
  or links a standalone executable with a C runtime.
- build.sem states version, language, and standard-library versions, and
  requires local packages with version constraints.

### Everything compiles and runs

- The backend now compiles generic operations, cleanups and `defer`, tasks,
  task groups, channels, async operations, maps, sets, and the host library
  (`fs`, `net`, `http`, `process`, `environment`, `clock`, `time`, `buffer`,
  `console.readLine`) through one runtime callback.
- The server example runs and answers HTTP on `127.0.0.1:8080`; every program
  case in the suite runs, and a test keeps it that way.
- `refined run PATH -- <arguments>` passes arguments to the program.
- Tasks run in parallel, each on its own thread, with task-group limits,
  blocking channels, cooperative cancellation that reaches child tasks, and
  deadlock reports that name every wait. `fs` gains append mode and directory
  operations.
- Enums may carry any payload (text, records, lists, other enums), and
  `equals` compares every type structurally. Nothing a clean program can
  contain is refused; tests prove every operation of every program compiles
  and every standard-library target runs.

### Test suite

- `tests/suite`: program cases for every section of the language checklist
  (positive, negative, and edge), a table of one-mistake negative cases with the
  exact rule codes they must produce, and generated stress, fuzz, differential,
  determinism, and source-location tests. `docs/test-suite.md` is a generated
  coverage map of all 456 checklist items with status and evidence.
- Fixed what it found: a checker crash on malformed rows; an out-of-bounds
  `string.slice` when `start + length` overflowed; a native stack overflow
  instead of a trap under deep recursion; `math.powerInt64` running one step per
  unit of exponent; nested counted loops that could not restart their counter;
  `math.saturating*Int64` refused by the backend; project modules named like
  standard modules; and three misleading diagnostics.

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
