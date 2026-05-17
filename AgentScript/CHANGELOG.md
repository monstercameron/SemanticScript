# Changelog

All notable changes to the AgentScript reference compiler (`ascc`),
standalone linter (`aslint`), and bootstrap chain.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Compiler (`compiler/ascc.py`)

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

### Known out-of-scope language features

These are spec-defined and parsed (via `--parse-only`), but not yet
lowered to LLVM IR. The compiler refuses to silently drop them; using
one in a compiled program raises `NotImplementedError` with a spec
section reference (spec §2 law 5: hidden behavior is illegal).

- `defer*` cleanup verbs (spec §13)
- `taskGroup`, `startInGroup`, `awaitGroup`, `bindGroupError`,
  `branchIfGroupError` structured concurrency (spec §20)
- `send`, `receive`, `branchIfChannelClosed`, `lock`, `unlock`,
  `workerPool`, `submitWork`, `awaitWork` (spec §22)
- `interval`, `startInterval`, `awaitIntervalTick` (spec §23)
- `select`, `selectCase`, `runSelect`, `branchSelected` (spec §20 race)
- `new`, `fieldGet`, `fieldSet` record I/O (spec §21)
- `useRetry` retry-policy attachment

These slots are reserved by the AST and locked by the parser. They
will be implemented in subsequent minor releases without disturbing
the verbs frozen above.

### Stability promise

Programs that compile and run on `ascc 1.0.0` will continue to compile
and run on any `ascc 1.x.y` release. The line-oriented verb tape, the
declared call-target set, and the LLVM IR shape per construct will not
break in a minor version. Future minor releases may **add** verbs,
call targets, or CLI flags; they will not remove or repurpose existing
ones.
