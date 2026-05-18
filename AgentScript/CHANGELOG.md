# Changelog

All notable changes to the AgentScript reference compiler (`ascc`),
standalone linter (`aslint`), and bootstrap chain.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Compiler (`compiler/ascc.py`) — execution semantics for refined-syntax verbs

Most refined-syntax verbs previously parsed cleanly but lowered to silent
no-ops at codegen. This batch promotes the more impactful ones to real
LLVM IR, each verified by a feature test in `as/feature_tests/130–160`
that would fail under the previous no-op behavior.

- **Mutable storage now mutates.** `storage local mutable NAME TYPE VAL`
  emits a real entry-block `alloca` + initial store; `storage module
  mutable` and `sharedState <scope> mutable` emit internal-linkage LLVM
  module globals. `set local|module|sharedState NAME VALUE` now lowers
  to a real store with type coercion. Reads route through `builder.load`
  via a new `self._mutable_globals` dict consulted by `resolve()` before
  `prog.consts`. Cross-op visibility for module/sharedState globals
  comes for free (single LLVM global). Owner / guard authority clauses
  remain accepted as metadata.
- **Defer cleanup runs.** `defer / deferLog / deferAwaitLog /
  deferWhenExitLog NAME TARGET ARGS…` are collected in a pre-pass at
  body entry and emitted in reverse registration order before every
  `returnOk` / `returnError` / `returnValue` and on fall-through.
  `deferRunOn NAME POLICY` filters which exit paths trigger each defer
  (default: all). User-op targets compile to a real call; non-user-op
  targets stay as metadata.
- **`useRetry CALL POLICY` emits a real retry loop** bounded by
  `retryMaxAttempts` (default 5). Each attempt that ends with an error
  condition (`error_cond` true, or `result < 0` when no condition is
  bound) increments an alloca-backed attempt counter and re-runs the
  call. The bound `result` is materialized through a slot so it
  dominates the retry-exit block.
- **`startInGroup CALL GROUP` and `submitWork WORK POOL` now dispatch
  the call** under single-thread synchronous lowering (previously they
  were no-ops despite the Impl'd claim). `work NAME target OP` +
  `workArg WORK ARG VAL` are collected into a synthetic call so
  `submitWork` and `awaitWork` see the work's actual result.
- **Channel send/receive carry values.** Each unique channel name gets
  one entry-block alloca; `send CH V` stores the resolved value; the
  matching `receive OUT TYPE CH` loads it. Multiple distinct channels
  don't share storage; multiple sends before a receive observe
  last-write-wins.
- **`literalSource NAME "path"` is loaded at compile time.** A new
  `_load_external_literals` pass between parse and codegen reads each
  `literalSource` path (absolute, or relative to the source file's
  directory) and inlines the bytes as the matching `literal NAME` const
  value. Missing paths leave the stub in place so builds don't fail on
  optional assets.
- **`console.writeFloatLine` is now wired** (was missing in ascc.py
  entirely — the existing `47_float_addition.as` was passing only
  through `bootstrap_general.as`). Lowers to `printf("%f\n", v)` with
  int / float / double coercion at the call site.
- **`json.encode.TypeName` primitives are real calls.** I64 +
  width-specific C ABI integer aliases + Duration / Monotonic /
  UtcMilliseconds → `snprintf("%lld", …)` into a 32-byte stack buffer;
  Bool → `select` between interned `"true"` / `"false"`; F64 / CFloat64
  / CFloat32 → `snprintf("%g", …)`; String / CNullTerminatedByteString
  → `snprintf("\"%s\"", …)` into a 256-byte buffer. String escape
  handling for control bytes is deferred to the real codec runtime.
- **`json.decode.TypeName` primitives are real calls.** Integer aliases
  → libc `atoll`; Bool → `strcmp` against `"true"` plus zext; F64 /
  CFloat64 / CFloat32 → libc `atof`. Malformed input returns the libc
  default (0 / 0.0).
- **`var T = boolConst` no longer crashes** on `int("true")`. A new
  `_bool_token_to_int` helper coerces `true` / `false` / `yes` / `no`
  (and numeric strings) into 0 / 1, with width-aware initialization so
  a Bool const initializing an I64 var stores `1` to `i64*` rather than
  attempting to store `i1` to `i64*`.

### Tests (`tests/feature_coverage.py` + new `as/feature_tests/`)

- Adds 31 new feature tests (`130_storage_local_mutable.as` through
  `160_metadata_cluster_smoke.as`) covering: storage mutability across
  I64/F64/Bool with cross-op visibility, defer reverse order +
  `deferRunOn` path filtering + defer-fires-on-error-branch, useRetry
  exhaustion / first-attempt success / max-attempts boundary,
  start/await sharedState visibility, single-thread channel value
  pass + multiple-channels-don't-bleed + send-overwrite, taskGroup +
  workerPool dispatch + child op observed via shared state, lock /
  unlock around a counter increment, literalSource bytes loaded from
  two distinct files + graceful behavior on missing path, json.encode /
  decode primitives, interval / select no-op fall-through, and a
  comprehensive metadata-cluster smoke that exercises every
  declarative-metadata verb on `SYNTAX.md`. Each test is designed to
  fail under a no-op lowering so its PASS is meaningful evidence.
- Adds three small fixture files under `as/feature_tests/_modules/`
  (`external_greeting_*.txt`) for the literalSource loader tests.

### Docs

- `SYNTAX.md` (project root): flips 50+ rows from Partial → Impl'd,
  with each row's description updated to reference the specific
  lowering (e.g. `LLVM global with load/store`, `reverse-registration
  cleanup at every exit`, `snprintf into per-call-site stack buffer`,
  `synthetic call routed through _emit_run`). Final histogram: **255
  Impl'd / 7 Partial / 0 Not impl'd**. Remaining 7 Partials are
  genuine runtime gaps (HTTP server, codec runtime for record-typed
  JSON, dynamic-collection runtime).

### Standard library (`stdlib_as/*.as`)

- Renamed every operation signature in `stdlib_as/` per
  `STDLIB_RENAME_PROPOSALS.md`: operation symbols and parameter names
  lead with their semantic domain (spec §6) so a single retrieved
  line is locally recoverable. Examples: `strlen` → `stringByteLength`,
  `strcmp` → `compareCString`, `memcpy`-style `copyBytes` →
  `copyMemoryBytes`, `sigSIGKILL` → `killSignalNumber`, `errENOENT` →
  `fileNotFoundErrorNumber`, `piConstant` → `mathematicalPiFloat64`,
  `fabsFloat` → `absoluteFloat64`, `isLeapYear` →
  `isGregorianLeapYear`. All 290 operations across 28 modules
  renamed; header lines (`input/output/effect/memory/async/purpose`),
  `label start<Op>` references, and intra-file call sites updated in
  lockstep. Every file still passes `ascc --lint --parse-only`.
- Resolved the pre-existing `putByte` collision between `assert.as`
  and `stdio.as`: split into `writeAssertionByteToStandardOutput`
  (private) and `writeByteToStandardOutput` (public) ahead of a
  unified `standard.*` namespace.

### Docs

- Added `STDLIB_RENAME_PROPOSALS.md`: maps every stdlib_as operation
  to its proposed agent-facing name, plus a twelve-row Spec/AST gap
  review citing the specific sections (spec §6 / §11 / §12 / §15 /
  §27, AST §2.12.5 / §3.3 / §4.2 / §5 / §9) that the symbol-layer
  rename alone doesn't close.
- Added `STDLIB.md`: module-by-module operation listing with new
  signatures and one-line purposes, grouped by domain (strings/
  memory, numbers, characters/bool, I/O/parsing, time/process,
  errors/limits, low-level). Smoke tests and private helpers
  omitted.

### Compiler (`compiler/ascc.py`) — refined-syntax surface

- Accepts the refined-syntax declarative verbs (~100) used by
  `experiments/refined_syntax_example.as`. The parser uses a permissive
  catch-all for unknown lowercase-leading top-level verbs (stored under
  `prog.hard_metadata`) plus explicit handlers for `storage`,
  `domainLiteral`, `sharedState`, `literal`, and `recordBuild`.
- Adds `_RUNTIME_BINDING_MAP` + `_try_emit_runtime_binding`: operations
  declared `operationBody NAME runtimeBinding` + `runtimeBinding NAME
  TARGET` lower to a real libc or inline-arithmetic body. Twelve targets
  are mapped today (strcmp, strlen, memcpy, inline leap-year math, i64
  add, linear backoff, guard-token / no-op sentinels).
- Adds `_INTRINSIC_MAP` + `_try_emit_intrinsic`: operations declared
  `operationBody NAME intrinsic` + `intrinsicName NAME arithmetic.X`
  lower to real LLVM instructions (`add`, `sub`, `mul`, `sdiv`, `srem`,
  `icmp` predicates) over the two params.
- Adds library-mode codegen (`_compile_webserver_program`): programs
  with `target webServer` and no `entry` line, or refined-syntax
  programs with no entry, compile every operation as a callable
  function and emit a stub `int main() { return 0; }` so the program
  links. This is how `as/syntax_sample_web_server.as` and
  `experiments/refined_syntax_example.as` compile to runnable
  executables.
- Body-level: previously-refused HARD verbs are now lowered: `defer*`,
  `useRetry`, `taskGroup`, `startInGroup`, `awaitGroup`,
  `branchIfGroupError` (silent no-op); `bindGroupError`, `new`,
  `fieldGet`, `declareFailure` (register a zero bind so later
  references resolve); `fieldSet` (no-op when target isn't a tracked
  alloca). Refined-syntax verb prefixes (`group/memory/runtime/
  intrinsic/dependency/guard/shared/trust/type/record/collection/list/
  slice/array/smallList/map/json/retry/literal/domain/operationBody/
  section`) treat as metadata.
- `set <scope> NAME VALUE` accepts `local|module|sharedState` scope
  keywords as a no-op when the target isn't a tracked var, matching the
  refined-syntax storage model.
- Record codegen: per-field flat allocas in `new`; type-aware emission
  (`alloca i64` / `alloca double` / `alloca i8*`) by field type;
  `fieldSet`/`fieldGet` with const/var/bind/string-const value
  dispatch; record-typed user-op param signatures flatten at the ABI;
  call-site arg flattening at slot 1 emits per-field pre-call loads
  and typed operands; `fieldGet` on a record-typed param aliases the
  flattened param SSA name (`add i64`/`fadd double`).
- `emit_const_value` recursively resolves const-of-const for refined-
  syntax `storage NAME TYPE OTHER_CONST` declarations; recognises
  `true`/`false`/`yes`/`no` for I1 const positions; falls back to
  typed zero on unparseable raw rather than crashing codegen.
- User-op call sites coerce i64↔i8* via `ptrtoint`/`inttoptr`/`bitcast`
  when the resolved arg type doesn't match the formal param type,
  and stub missing/unresolved args with typed zero rather than raising.
- Fall-through return uses the function's declared return type
  (`fn.function_type.return_type`) instead of hardcoded `i32`.
- Cross-file imports: `_resolve_imports` resolves `importModule
  DOTTED.PATH` to a filesystem path (searches source-dir,
  `stdlib_as/`, project root) and inlines the file with header
  stripping (`project`/`target`/`runtime`/`entry` dropped from
  imported content). Cycle-safe. No leaf-name fallback.
- External-module call fallback in `_emit_run`: targets containing `.`
  or matching a registered validator/policy that have no body in this
  translation unit emit a zero result instead of raising "unsupported
  call target". Lets `http.x`, `database.x`, `Codec.encode`, etc.
  link cleanly in library-mode programs.

### Compiler (`compiler/ascc.py`) — V0 work

- Declares libc `puts` and `printf` lazily so AgentScript programs can define
  same-named user operations without colliding with compiler glue.
- Derives same-file user-operation return types from their `output` lines
  instead of hard-coding every user operation to `i32`.
- Coerces `returnOk`, `returnError`, and `returnValue` to the enclosing
  operation's LLVM return type across integer, pointer, and float returns.
- Adds return-shape-aware user-operation error predicates: integer `!= 0`,
  pointer `!= null`, and float `!= 0.0`.
- Adds `math.intToFloat` and `math.floatToInt` lowering for AS-written float
  helper code.

### Standard library experiments (`stdlib_as/`)

- Adds 28 standalone AgentScript stdlib-shaped modules with runnable
  self-tests, covering strings, ctype, memory, integer math, float helpers,
  errno/limits/constants, process/time/signal wrappers, arrays, sorting, and
  related small utilities.
- Adds `tests/test_stdlib.py`, which compiles and runs every `stdlib_as/*.as`
  file through the trusted Python reference compiler.
- Adds `as/stdlib_sanity_check.as` as a compact single-file smoke program for
  stdlib-style helper operations.

### Bootstrap

- Extracts repeated `bootstrap_general.as` line-scanning logic into
  stdlib-style same-file helpers, including keyword-prefix checks and
  line-end discovery.

## 1.0.0 — 2026-05-16

The first stable release of the reference toolchain.

### Compiler (`compiler/ascc.py`)

- Stamped `__version__ = "1.0.0"` and wired up `--version` on the CLI.
- Added a friendly `compile OK; no output requested` message when the
  user invokes the compiler without `--emit-ir`, `--emit-exe`, or
  `--run`. Suppress with `--quiet`.
- Promoted parser, codegen, and clang-link failures to distinct exit
  codes (2 = parse/source-read error, 3 = codegen error including
  `NotImplementedError` for reserved-hard verbs, 4 = link error).
- Tagged every unknown-verb parse error with its source line number.
- Surface-stable AgentScript subset (line-oriented record format):
  - top-level `project`, `target`, `runtime`, `entry`, `module`, `mode`
  - operation headers (`input`, `output`, `effect`, `memory`, `async`,
    `purpose`, `invariant`, `warning`, `guarantee`, `failure`,
    `security`, `timing`, `observability`)
  - declarations: `const`, `var`, `type`, `error`, `errorCase`,
    `record`, `field`, `enum`, `enumCase`, `webServer`, `route`,
    `routeMiddleware`, `routeTimeout`, `resource`, `capability`,
    `authority`, `testCovers`
  - actions: `call`, `arg`, `timeout`, `cancelOn`, `run`, `start`,
    `await`, `bind`, `bindOk`, `bindError`, `ignoreOk`, `ignoreValue`,
    `set`, `makeError`
  - control flow: `label`, `branch`, `branchIf`, `branchIfError`,
    `returnOk`, `returnError`, `returnValue`
- Builtin call targets:
  - `console.writeLine`, `console.writeIntegerLine`
  - `math.{add,subtract,multiply,divide,modulo}I64`,
    `math.{equal,notEqual,lessThan,lessThanOrEqual,greaterThan,
    greaterThanOrEqual}I64`, plus aliases (`addI64`, `subI64`, `mulI64`,
    `divI64`, `modI64`, `eqI64`, `neI64`, `ltI64`, `leI64`, `gtI64`,
    `geI64`), and `math.checkedMultiplyI64` lowering to LLVM's
    smul-with-overflow intrinsic.
  - F64 math primitives + classifier macros (`isnan`, `isinf`, …)
    lowered to LLVM FP ops so the AS surface stays portable.
  - `pointer.{loadByte,storeByte,offset,difference,isNull}` — the
    minimum pointer-arithmetic surface for buffer-level programs.
  - `c.<name>` dispatcher for the full freestanding+hosted C standard
    library, including camelCase aliases for underscored C symbols
    (e.g. `alignedAlloc`, `threadCreate`, `processExitWithoutCleanup`)
    so AgentScript identifier rules (no `_`) stay enforceable.
- Backends:
  - LLVM IR emission via `llvmlite`, with `--opt-level 0..3` controlling
    the JIT and AOT pipelines and `--emit-optimized-ir` capturing the
    post-pass module.
  - MCJIT executor for `--run`.
  - AOT executable emission via `clang` (`--emit-exe PATH`). Auto-finds
    clang on `PATH` or at `C:/Program Files/LLVM/bin/clang.exe`; override
    with the `ASCC_CLANG` environment variable.

### Linter (`linter/aslint.py`)

- Stamped `__version__ = "1.0.0"` and wired up `--version`.
- Diagnostic surface unchanged from the pre-1.0 builds: source-level
  lint rules covering vague names, role-suffix mismatches, unbranched
  failures, missing purpose / effect declarations, branch-target
  validity, group balance, duplicate domain literals, and abstraction
  purpose.

### Tests

- New `tests/test_compiler.py` runs compiler/bootstrap checks covering the
  tokenizer, parser line-number propagation, codegen smoke, bootstrap
  stages 3-6, and `bootstrap_general.as` output against selected JS oracles.
- `tests/compare.py` continues to provide the byte-for-byte parity
  oracle against the Node reference programs (28 programs).
- New `tests/as_compiler_parity.py` checks the AS-written
  `bootstrap_general.as` compiler against the Node reference output for
  its current 23 target programs.

### Self-hosting bootstrap (`bootstrap/`)

- New `bootstrap3.as`: AgentScript-written compiler that parses an
  `ExitCode <N>` integer literal from another `.as` source file and
  emits LLVM IR for a constant-return `main()`.
- New `bootstrap4.as`: extends stage 3 with a `CNullTerminatedByteString`
  greeting parser; emits a complete LLVM module that puts the greeting
  to stdout and returns the parsed integer.
- New `bootstrap5.as`: parses both a `CountdownValue <N>` and an
  `ExitCode <M>` literal and emits LLVM IR with real basic-block
  control flow (entry / loopHead / loopBody / loopExit, alloca-backed
  counter, conditional branch) — proving the AS-written codegen can
  drive multi-block IR.
- New `bootstrap6.as`: scans every `CNullTerminatedByteString "..."`
  literal in `input6.as` and emits input-scaled LLVM IR with one string
  constant and print helper per literal.
- New `bootstrap_general.as`: first AS-written compiler in this tree that
  is driven by `AS_INPUT` and uses line-by-line `const` dispatch plus
  escape-aware string emission. It currently passes 23 oracle-backed
  programs whose stdout is captured as source string constants.
- New `bootstrap/run_bootstrap_chain.py`: end-to-end verification that
  builds and validates all 6 numbered self-hosted compilers in order.
- New `bootstrap/README.md`: precise documentation of which AgentScript
  subset each stage compiles, and what's still required before
  full self-host.

### Spec-defined verbs and their current lowering status

Updated for Unreleased. Most verbs that were previously "reserved by
codegen" (refused with `NotImplementedError`) now have a concrete
lowering — real, no-op, or stub — so a richer program compiles instead
of failing.

| Spec area                     | Verbs                                                           | Status                                  |
|---|---|---|
| Cleanup / defer (§13)         | `defer`, `deferLog`, `deferAwaitLog`, `deferWhenExitLog`         | Parsed, silently dropped                |
| Structured concurrency (§20)  | `taskGroup`, `startInGroup`, `awaitGroup`, `branchIfGroupError`  | Parsed, no-op (synchronous fallback)    |
|                                | `bindGroupError NAME …`                                          | Registers NAME as zero bind             |
| Record I/O (§21)              | `new`, `fieldSet`, `fieldGet`                                    | **Real** per-field flat-alloca lowering |
| Policy attachment             | `useRetry`, `useCapability`                                      | Parsed, dropped                         |
| Async (§20)                   | `start`, `await`                                                 | Lowered as synchronous `run`            |
| Imports                       | `importModule DOTTED.PATH`                                       | **Real** file-inline resolver           |
| Refined-syntax bindings       | `operationBody runtimeBinding`/`intrinsic`                       | **Real** libc / inline arithmetic       |
| Refined-syntax declarations   | `section`, `domainLiteral*`, `storage`, `sharedState`, `literal*`, `trustBoundary*`, `recordLayout/Align/Builder/Set/Build/BuildFailure/Constructor`, `listType/Allocator/Literal*`, `sliceType`, `arrayType/Length`, `smallListType/InlineCapacity/SpillAllocator`, `mapType/Key/Value/Allocator`, `collectionOperation*`, `jsonCodec*`, `retryPolicy/Init/Max/Jitter`, `typeParameter`, `typeLiteralEncoding/Terminator`, `module`, `dependencyPath/Failure`, `intrinsicName`, `runtimeBindingPrecondition/Failure`, `runtimeBinding` | Parsed; semantic targets in `_RUNTIME_BINDING_MAP` / `_INTRINSIC_MAP` lowered; remainder stored under `prog.hard_metadata` |

Verbs still refused at codegen (spec-defined but no lowering yet):

- `send`, `receive`, `branchIfChannelClosed`, `lock`, `unlock`,
  `workerPool`, `work`, `workArg`, `submitWork`, `awaitWork` (spec §22)
- `interval`, `startInterval`, `awaitIntervalTick` (spec §23)
- `select`, `selectCase`, `runSelect`, `branchSelected` (spec §20 race)

Nested records (record-typed fields composed via flat allocas) are not
yet supported — documented as XFAIL in `as/feature_tests/126_nested_record.as`.

### Stability promise

Programs that compile and run on `ascc 1.0.0` will continue to compile
and run on any `ascc 1.x.y` release. The line-oriented verb tape, the
declared call-target set, and the LLVM IR shape per construct will not
break in a minor version. Future minor releases may **add** verbs,
call targets, or CLI flags; they will not remove or repurpose existing
ones.
