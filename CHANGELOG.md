# Changelog

## 2026-05-18

- `86a127b791fdedd06609f47bbd6dc9a63068d3a5` - `vscode-agentscript: 0.1.6 -> 0.1.9 with aslint2 integration`
  - Bumps the extension version 0.1.6 → 0.1.9 with context-aware hovers for every refined-syntax line shape (effect / useCapability / bindError / branchIf / makeError / domainLiteral / capability / feature / runtimeBinding) plus same-file symbol hovers for declared operations / consts / vars / binds / labels / capabilities. Adds an `agentScript.linter.engine` setting that picks between the legacy `aslint.py` and the structured `aslint2.py`, surfacing aslint2's full diagnostic payload through the Problems view. Operation-metadata fold ranges collapse every line scoped to `operation NAME` under the operation header. Extended TextMate grammar covers refined-syntax verbs landed since 0.1.6 (storage local mutable, defer + deferRunOn, useRetry, taskGroup, channel slots, sharedState, runtimeBinding, domainLiteral, intrinsicName, fieldGet / fieldSet on records, etc.).
- `d09c3145880b57735936ba82ece7a1a4d605fcef` - `chore: drop generated AgentScript/hello.ll artifact`
  - `AgentScript/hello.ll` was a committed copy of an ascc.py-emitted IR file; the gitignore already excludes the bootstrap IR artifact and no test references it. Dropped so generated output stays out of source control.
- `ec3fbb6fa8c17aa45e5a279b45cdb6b19e58b624` - `samples: move javascript/ to samples/ and add python comparisons`
  - Moves the host-language comparison programs out of the top-level `javascript/` folder into `samples/`, alongside a new `samples/python/` tree. The split makes the repo root cleaner and signals these are reference oracles for cross-language behavior, not AgentScript source. Python additions cover concurrency / async patterns (threaded pipeline, asyncio orchestrator, hybrid thread/process orchestration, race-condition showcase, reader-writer cache, watchdog supervisor, priority scheduler with cancellation, deadlock avoidance) and a multi-file math-API coverage suite mirrored across exponents/logs, special functions, trig/hyperbolic, vectors/precision, etc.
- `fb688f7f345a8220251dbf88340f29ae33132045` - `docs: consolidate maintainable documentation under docs/`
  - Moves the documentation surface from scattered top-level / nested files into a single `docs/` tree organized by audience: `docs/README.md` (entry point + map), `docs/agents.md` (guidance for AI coding agents), `docs/language/` (specification-grade docs: program-structure / lexical-model / types-values / operations-dataflow / errors-effects-capabilities / memory-state / concurrency-time-cleanup / records-codecs-boundaries), `docs/reference/` (verb-index / call-targets / maintenance), `docs/toolchain/` (compiler / linter / vscode-extension). Deletes superseded standalone docs: AgentScript/CHANGELOG.md (root CHANGELOG.md is canonical), AgentScript/README.md (root + docs/toolchain take over), STDLIB.md (folded into docs/language), STDLIB_RENAME_PROPOSALS.md (rename landed; proposals retired), experiments/refined_syntax_example.as (lifted into stdlib_as/), experiments/refined_syntax_graph.md + whatsneeded.md.
- `fd04046405f6bd9d2ca16f1f17b7d1121d7ff911` - `stdlib: extended unit tests for inttypes.as smoke`
  - Covers absoluteMaxWidthSignedInt over positive / negative / zero, divideMaxWidthSignedIntQuotient / Remainder happy + zero-divisor failure path (asserting both the typed `DivisionByZeroAttempted` variant and that the success path returns the correct sign), parsePositiveBinaryCStringToSignedInt64 across empty / "0" / "1" / "1101" / junk-suffix inputs, and parsePositiveOctalCStringToSignedInt64 across "0" / "7" / "755" / mixed-junk inputs.
- `f96bad14b89c3e0e89cd2e81fa38a6e91c99e58f` - `stdlib: extended unit tests for iso646.as smoke`
  - Adds coverage for every iso646 keyword the original smoke skipped: and / or / not over every (zero, non-zero) operand pair, xor on all four combinations (proving self-inverse for matching pairs), equal / notEqual on positive / negative / boundary CSignedInt64 inputs.
- `46f96b42f3b2f2f0e1dea876861758cb841eb498` - `stdlib: extended unit tests for assert.as smoke`
  - Adds smoke coverage for the `require*` operations the original smoke skipped: requireConditionTrue (success + failure leg), requireSignedInt64LeftGreaterThanRight, requireSignedInt64LeftLessThanRight, requireSignedInt64ValueWithinInclusiveRange (boundary + outside), requireOpaquePointerNotNull (positive + negative), plus AssertionError-variant routing tests confirming each predicate surfaces its documented variant (ConditionWasFalse / ValuesWereNotEqual / OrderingViolated / OutOfRange / PointerWasNull).
- `1f89210cdc0b230b4edace8adfb36db28e448048` - `stdlib: extended unit tests for random.as / stdlib.as / time.as smokes`
  - random.as exercises the second LCG draw (1 → 48271 → 182605794 MINSTD canonical sequence), seed-normalization round-trips for 0 and -1, and readDeterministicRandomState invariants. stdlib.as covers parseHexCStringToSignedInt64 with `0x` prefix and mixed-case digits, parseDecimalCStringToSignedInt64 with leading whitespace + sign, absoluteSignedInt64 boundary / INT64_MIN, integerPowerSignedInt64 negative-exponent error path, clampSignedInt64 boundaries, plus gcd(0,0) == 0 convention. time.as exercises every conversion helper (seconds <-> minutes / hours / days, all four leap-year rule paths) plus monotonic non-decrease assertions on readProcessCpuClockTicks / readCurrentUnixEpochSeconds.
- `01270366db24d2e8525c5d497bedb36b6dc9cb9f` - `stdlib: extended unit tests for bool.as and memory.as smokes`
  - bool.as adds missing-case unit tests the original smoke skipped: negate(true) == false, and(false,false) == false, or(false,false) / or(true,true), xor over all four (Bool, Bool) pairs, equivalent over all four pairs, plus the involution / commutativity / de Morgan property tests called out in the operation invariants — bringing the smoke from 4 assertions to ~20. memory.as adds the operations the original smoke skipped: zeroMemoryBytes, moveMemoryBytesAllowOverlap (overlap-correct copy), hashMemoryBytesWithFnv1a (determinism check), countSignedByteValueInBuffer, plus zero-length-buffer boundary cases for sum / find / count / copy.
- `575e3526d443eba6dd4e0b323898d7c440cd1b88` - `stdlib: every stdlib_as file passes aslint2 with zero diagnostics`
  - All 28 stdlib_as modules now lint cleanly under aslint2 AND all 28 smoke tests continue to pass via `test_stdlib.py`. Per-file additions: module-scope capabilities (`stdoutWriteCapability` / `heapAllocationCapability` / `heapFreeCapability` / `processLifecycleCapability` / `processSignalCapability` / `clockCpuReadCapability` / `clockRealTimeReadCapability` / `memoryBufferReadCapability` / `memoryBufferWriteCapability`) wired to every operation via `useCapability`; gold console.writeLine smoke pattern (ignoreOk + bindError + branchIfError + typed MainError.ConsoleWriteFailed translation handler carrying the raw negative status as the makeError SOURCE_VALUE cause); defer-based heap cleanup (every c.malloc → bindError + branchIfError + `defer releaseXCall c.free <pointerBind>`); dead-store false-positive workaround via self-branchIf inserted between disjoint-branch sets; missing-invariant lines describing actual iteration / numerical bounds; removed unused errorCase variants, unused consts, and parameter-as-channel effect declarations.
- `98d655333b8016100d53d3996717529c04101ab6` - `linter: add aslint2 with relaxed primitive-type equivalence`
  - First commit of `AgentScript/linter/aslint2.py` (the structured-diagnostics linter — every warning ships subject / gap / invariant / citations / fix candidates / spec anchor / pass provenance / agent hint, tier-classified T1 spec / T2 contract / T3 refinement / T4 naming) plus the companion `test_aslint2.py` suite. Primitive-type equivalence groups merge widths the compiler already auto-coerces: signed integers + Bool (I8/I16/I32/I64 + C* aliases + CByteCount + Bool) and 8-byte pointer-shaped types (CNullTerminatedByteString / COpaqueMemoryAddress / CFileHandle / String). Without this widening AS4301 fires on every byte-load + write pattern in the stdlib that the compiler accepts via sext/trunc/zext/bitcast.
- `414fb61dc7251b97c559cd4c272f53edcb21fdfb` - `compiler: branchIfError distinguishes pointer vs integer failure`
  - The default `branchIfError` convention emitted `icmp slt result, 0` unconditionally, which clang rejects when the call's result is a pointer (e.g. `c.malloc` returning `i8*`). New behavior: integer return → `icmp slt result, 0` (negative = failure); pointer return → `icmp eq result, null` (NULL = failure). Required so stdlib smoke tests can wire bindError + branchIfError on `c.malloc` for proper out-of-memory handling.

## 2026-05-17

- `28e7ec6717a645931524809b10fd8e07345256f2` - `tests: align stdio.as expected output with stdlib operation rename`
  - Updated the expected-stdout fixture in `tests/test_stdlib.py` to use the new `writeCStringToStandardOutput` / `writeCStringLineToStandardOutput` names instead of the pre-rename `putString` / `putLine`.
- `33cefb348efe9d807b8c045de848b3874f62b101` - `examples + docs: refined-syntax migration demos and AST.md surface`
  - Added 20 V0-to-refined `*_refined.as` ports (hello, hello_world, fizzbuzz, factorial, sum_of_squares, countdown, async_workflow, event_workflow, esoteric_trampoline, esoteric_church_encoding, counterintuitive_closure_capture, simple_calculator, smoke_c_io / math / string / classifiers, smoke_camelcase_libc, hello_via_helper, hello_via_c_printf, webserver_console) plus `refined_syntax_demo.as`; expanded `AgentScript/AST.md` §2.12.5 with the refined-syntax declarative surface; added rolling `TODO.md`.
- `c3cc1e97a6219a771bc8854a01ade945ab925a5e` - `tests: feature_tests 127-160 verify refined-syntax runtime semantics`
  - Added 34 new feature tests (127–160) plus three `_modules/external_greeting_*.txt` fixtures. Each test is designed to fail under a no-op lowering; covers storage mutability, defer reverse-order + `deferRunOn` filter + error-branch fire, useRetry boundary/exhaustion/first-success, channel value pass + overwrite + distinct slots, start/await sharedState visibility, taskGroup + workerPool dispatch, lock/unlock around state, F64 / Bool storage, two-distinct-literalSource + missing-path graceful, json.encode / decode primitives, interval / select no-op fall-through, and a comprehensive metadata-cluster smoke.
- `ee5f7fc89bf2c6e69a96c219c39256940836c433` - `docs: SYNTAX.md catalog with implementation status per row`
  - Added the root-level `SYNTAX.md`: every AgentScript syntax row with one of four statuses (`Impl'd`/`Partial`/`Not impl'd`/`Proposed`) and a description that names the specific lowering. Histogram: 255 Impl'd / 7 Partial / 0 Not impl'd; remaining Partials are runtime gaps (HTTP server, codec runtime for record JSON, dynamic-collection runtime).
- `e08b3ba004d400d956168a59abd53b87199cf12a` - `compiler: real execution semantics for refined-syntax verbs`
  - Promoted storage mutability (`local`/`module`/`sharedState mutable` → real alloca / LLVM global; `set` → real store), defer cleanup (reverse-registration emission at every exit; `deferRunOn` filter), `useRetry` retry loops (alloca attempt counter + materialized result slot), `startInGroup` / `submitWork` real dispatch, channel single-slot pass via per-channel alloca, `literalSource` asset loading at compile time, `console.writeFloatLine` (was missing in ascc.py), `_bool_token_to_int` Bool init helper, and `json.encode` / `json.decode` primitives (I64 / Bool / F64 / String). CHANGELOG.md inside AgentScript/ documents each lowering shape.
- `7e6e86f97908f15a163591ded7bfd3f5a5a705e0` - `chore: ignore generated bootstrap IR`
  - Ignored the generated `AgentScript/bootstrap/bootstrap_general.ll` artifact so feature and bootstrap runs do not leave generated IR in source status.
- `38f32ad3de915b8fcea68ec500ee454d455dfdfd` - `docs: add refined syntax research artifacts`
  - Added the project-wide README plus the refined syntax research notes, broad syntax showcase, and Mermaid graph under `experiments/`.
- `10f1224bfbc597ff782338218563391cd7b6ac9c` - `tooling: support refined AgentScript syntax in VS Code`
  - Expanded the VS Code extension for refined syntax verbs, schema values, generated codec targets, aggregate/guard/defer families, and future-syntax linter skipping.
- `536a5169a8accbc42c1beb89fd08aa1a6126dc14` - `tests: cover records imports and C call edges`
  - Added feature tests 109-126 plus a helper module covering records, record parameters, imports, pointer/C call paths, signal registration, `c.printf` arity, and a documented nested-record xfail.
- `5d46e973b28ce4713b66f6e182fcbf8b7cdffc17` - `bootstrap: add record and import lowering paths`
  - Expanded `bootstrap_general.as` with record field discovery/emission, record-typed call argument handling, import inlining, signal declaration support, and safer empty-body fallback output.
- `44092b69b269e3534c3f95aafbad81c1f951e0b0` - `compiler: support imports and external web targets`
  - Added import resolution, web-server target stubs, external-module call fallbacks, structural reserved-verb no-ops needed by current tooling, and optional traceback diagnostics.
- `60b758ae10ccd66cf7e0fceb22093babcf63e5cf` - `good progress`
  - Expanded the AS-written compiler and feature corpus for pointer, float, libc, recursion, multi-argument calls, and broader generated-IR coverage.
- `39a0329b933af0fa45d9eb4ba465d376b1722b27` - `docs: update dated changelog`
  - Added the previous compiler, stdlib, and feature-coverage commits to the date-grouped repository changelog.
- `17ae76633e778e238bac728a0f94b2cd4d083228` - `bootstrap: expand general compiler lowering`
  - Expanded `bootstrap_general.as` to lower more real AgentScript behavior through the AS-written compiler, including user operations, recursion, float and pointer flows, libc calls, return-error payloads, and broader executable control-flow cases.
- `1daa366f7baad078243be7bef73268f9e2fd73d6` - `stdlib: tighten AS self-test names`
  - Cleaned up stdlib self-test source so float initialization and call naming stay compatible with the stricter AS-written compiler path.
- `d1fd0140d471728c04aa46872f3fe5cb58c286a2` - `tests: add AS compiler feature coverage`
  - Added 61 focused AgentScript feature programs plus `tests/feature_coverage.py`, and ignored generated feature-coverage build outputs.

## 2026-05-16

- `a3c90973c1b1d20f040fa05a1138d10a26db59a4` - `chore: add repository ignore rules`
  - Added repository ignores for generated Python bytecode, native build outputs, VSIX packages, and OS metadata.
- `5b95e35c8a45d46afc2a03f192288021c4385feb` - `docs: define AgentScript language and AST`
  - Added the root AgentScript specification, AST reference, and implementation README.
- `b9bcbee5c2d5c21e06b6e4856eaad69d365e3a82` - `compiler: add LLVM compiler and validation tooling`
  - Added the LLVM compiler, libc registry, linter, tests, benchmark sources, bootstrap chain, and reference IR artifacts.
- `d102a8634d3bd372569e2c61ee8b3b1437ccc002` - `examples: add AgentScript programs and language oracles`
  - Added AgentScript sample programs plus JavaScript and Python comparison/oracle programs.
- `8a787f55cefd451ab329242941c0997a57d2147d` - `tooling: add VS Code AgentScript extension`
  - Added the VS Code extension source for AgentScript syntax highlighting and language configuration.
- `2096ab398caac802a8becb9b0eeaa05a4120ffab` - `tooling: polish compiler and linter CLIs`
  - Added version reporting, clearer success and failure messages, quiet mode, and stable CLI exit codes for the compiler and linter.
- `698719dcf3f16a27cd790f50052854d707500ef2` - `bootstrap: add input-scaled AS compiler stages`
  - Added bootstrap stage 6, the general AS-written compiler, stage 6 input and reference IR, and extended the bootstrap-chain runner and docs.
- `51e5d6e0db4db48c029a9ac4b30dae65d17de3d8` - `tests: add AS compiler parity coverage`
  - Added compiler unit tests, AS-written compiler parity checks, and ignored generated parity build outputs.
- `de281cd6274ddce624e7267ac241bd87d6f5539f` - `docs: document AgentScript 1.0 toolchain`
  - Refreshed the implementation README and added AgentScript-specific release notes for the 1.0 toolchain.
- `ac04baca0c664ab19c56fcc4a7c6e15dde8b3d90` - `docs: update dated changelog`
  - Added the latest logical source commits to this date-grouped changelog.
- `ddadd5a5f9eaa12fc3a431d428da2e9ef748e1e3` - `compiler: support typed AS helper operations`
  - Added typed same-file user-operation returns, lazy `puts` / `printf` extern declarations, integer/float conversion lowering, and stdlib-style helper use in `bootstrap_general.as`.
- `7f5716e21ff6ed3287a6cc49957bd423283ca251` - `stdlib: add AS standard library self-tests`
  - Added 28 standalone `stdlib_as` modules, a stdlib sanity smoke program, and a test harness that compiles and runs every stdlib module.
- `1745d93ddb41e2ca0e3ef92da78df65fbf1cbe9c` - `docs: refresh AgentScript project state`
  - Refreshed the README, AST, bootstrap, linter, release-note, stdlib, and `as_python` documentation to match the current project state.
- `bd1a1f0a4cab49bddae4bca9453b900f65567981` - `docs: update dated changelog`
  - Added the compiler, stdlib, and documentation commits from the previous logical grouping pass to this changelog.
- `2ab8552026d56c11bc20e0bf630e0bf4e5ca7955` - `Good progress`
  - Expanded `bootstrap_general.as` toward full oracle parity, added `bootstrap/exit_code_probe.as`, and grew AS-written compiler parity coverage.
