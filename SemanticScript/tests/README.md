# SemanticScript Test Suite

One global, lane-organized test surface for the compiler, tools, stdlib, and
runtime. Everything is registered in **`run_suite.py`** — the single place to
reference and run every check.

```powershell
python SemanticScript\tests\run_suite.py --list        # show every lane + command
python SemanticScript\tests\run_suite.py ci-fast       # default; cross-platform Python lane
python SemanticScript\tests\run_suite.py all --keep-going
python SemanticScript\tests\run_suite.py unit component # mix lanes / command keys
python SemanticScript\tests\run_suite.py stdlib.full    # a single command by key
```

## Lanes (test levels)

Every command is tagged with exactly one lane so the level is unambiguous:

| Lane | Meaning | Examples |
|------|---------|----------|
| **unit** | Isolated Python checks of one tool, no artifacts built | `formatter.unit`, `linter.unit`, `sem-cli.unit`, `sem-contracts.unit`, `python.compileall` |
| **component** | One tool exercised against a fixture / smoke; no full build | parser & linter `tiny` fixtures, `sem.*` JSON smokes, `async.lowering`, `syntax.migration`, `stdlib.coverage-guard`, `compiler.feature-corpus`, `vscode.check` |
| **integration** | Builds or runs real artifacts (compiler → IR/exe, stdlib, apps, native runtimes) | `compiler.full`, `stdlib.full`, `stdlib.native-smoke`, `event-runtime.native`, `async-runtime.native`, `app.runtime-smoke` |
| **e2e** | Compile to native exe and check the output | `golden.e2e`, `native.parity`, `reference.parity`, `sem-alias.parity` |

`all` = unit + component + integration + e2e.

The e2e lane has two complementary anchors, both compiling to a native
executable and running it:

- **`golden.e2e`** is *aspirational*: it asserts each program's stdout equals a
  checked-in, human-verified expected output in `tests/golden/<name>.golden`
  (factorial → 3628800, the FizzBuzz sequence, reconciled order-summary JSON
  totals, …). Because the expectation is independent of the compiler, a bug
  that corrupts both the JIT and native paths identically is still caught.
- **`native.parity`** is *self-contained*: it compiles each program both via
  the JIT (`--run`) and as a native exe and asserts the two agree, using the
  JIT as the oracle. This needs no golden corpus and covers the breadth of
  sample programs + every JIT-able stdlib self-test.

Both fail loudly without a C compiler (no silent no-op). `reference.parity` and
`sem-alias.parity` are the older JavaScript-oracle harnesses; they print
`[SKIP]` and pass when the optional `samples/javascript` corpus is absent.

### Standard-library suite

`stdlib` (alias `std`) groups all standard-library testing into one
reference: `stdlib.coverage-guard` (every `std/*` module parses and is
registered in an integration harness — a regression guard against a new module
escaping coverage), `stdlib.full` (per-module JIT smokes; http quarantined),
`stdlib.native-smoke` (native-exe smokes for log / bcrypt / jwt / net), and
`event-runtime.native` (the event/async native C runtime backing `std/event`).
Every JIT-runnable module additionally gets a native build+run e2e check via
`native.parity`.

```powershell
python SemanticScript\tests\run_suite.py stdlib   # or: std
```

## CI lanes (GitHub `.github/workflows/ci.yml`)

| Suite | Where it runs | Notes |
|-------|---------------|-------|
| **ci-fast** | Python 3.11 + 3.12 on Windows | Pure-Python validation; no native toolchain needed |
| **linux-validation** | Ubuntu + clang | `ci-fast` on Linux + `runtime.asan` (AddressSanitizer/UBSan over the C runtime) |
| **editor** | Node 20 | `vscode.check` only |
| **ci-release** | Windows | Builds/runs artifacts; needs a C compiler on PATH |

Aliases: `fast → ci-fast`, `release → ci-release`, `full → all`, `std → stdlib`.

## Quarantine policy

A module that is mid-revision can be quarantined so the suite stays
deterministically green cross-platform **without losing the signal**:
quarantined cases are still run and reported, but their failures do not fail
the suite unless strict mode is on.

- **`http`** (in `test_stdlib.py`) is currently quarantined: it passes at
  committed HEAD but fails under in-flight working-tree changes
  (`0xC0000409` on Windows). It is reported as `[QUAR]` / `QUARANTINE:` and
  excluded from the pass/fail count.
- Force quarantined cases to count: `SEM_STDLIB_STRICT=1`.

## Environment notes

- **Python**: 3.11 and 3.12 are the supported CI versions. Local 3.10 works for
  most lanes but is not a CI target.
- **Node**: CI uses Node 20 for the `editor` lane.
- **C compiler**: integration lanes that emit native executables need `clang`
  (or `zig cc`) reachable. If `clang` is not on `PATH`, set `SEMSC_CLANG` to its
  path; the native-runtime tests also honor `SEMSC_CLANG`.

## Test file map

| File | Lane(s) | Covers |
|------|---------|--------|
| `formatter/test_semfmt.py` | unit | formatter behavior |
| `linter/test_semlint.py` | unit | linter rules / diagnostics |
| `tests/test_sem_cli.py` | unit | `sem` CLI surface + JSON contracts |
| `tests/test_command_contracts.py` | unit | `sem` command contract stability |
| `tests/test_cli_errors.py` | unit | `semsc`/`sem` CLI error contracts (clean failure, no traceback) |
| `tests/test_async_wait_sets.py` | component | async lowering / wait-set shape |
| `tests/test_syntax_migration.py` | component | legacy → current syntax migration |
| `tests/test_app_syntax_cutover.py` | component | app syntax cutover |
| `tests/test_stdlib_coverage_guard.py` | component | every `std/*` module parses + is registered in an integration harness |
| `tests/feature_corpus.py` | component | compile-gates all 168 `feature_tests/*.sscript` to IR (XFAIL-tracked) |
| `tests/test_tooling_corpus_smoke.py` | component | `semlint` no-crash + `semfmt` idempotency over every shipped stdlib/sample source |
| `tests/fuzz_parser.py` | component | parser never-crash fuzzer (deterministic; `SEM_FUZZ_ITERS`/`SEM_FUZZ_SEED`) |
| `tests/test_spec_inventory.py` | component | syntax-inventory table integrity + headline Impl'd features compile (proof-test map) |
| `tests/differential.py` | component | opt-level differential: every sample is O0=O1=O2=O3 invariant (JIT) |
| `tests/test_compiler.py` | integration | parser, codegen, diagnostics, native emit |
| `tests/test_stdlib.py` | integration | stdlib JIT smokes (http quarantined) |
| `tests/test_native_stdlib_smoke.py` | integration | native-exe stdlib smokes (log, bcrypt, jwt, net) |
| `tests/test_event_runtime_native.py` | integration | event/async native C runtime |
| `tests/test_native_async_runtime.py` | integration | native async C runtime (`sem_async_runtime.c`) direct harness |
| `tests/feature_runtime.py` | integration | runs feature_tests natively, asserts stdout/exit match declared `# expect` oracles (7 tracked discrepancies) |
| `tests/test_asan.py` | integration | ASan/UBSan over the hand-written C runtime demos (capability-gated; runs on the Linux/clang lane) |
| `tests/test_app_runtime_smoke.py` | integration | app builds/runs (desktop, html, tui, http, web) |
| `tests/golden_e2e.py` | e2e | compile each sample (both `.sscript` + `.sem` forms) to native exe + assert stdout == verified golden (`tests/golden/*.golden`) |
| `tests/native_parity.py` | e2e | JIT ↔ native-exe parity: sample programs + every JIT-able stdlib self-test |
| `tests/compare.py` | e2e | reference output parity (optional JS oracle; skips when absent) |
| `tests/sem_alias_parity.py` | e2e | `.sem` source/JS output parity (optional JS oracle; skips when absent) |

Fixtures: `tiny.sem`, `tiny.sscript`, `agent_cli_demo.test.sem`, and the
`*.sscript` runtime smokes are minimal inputs used by the component lane.

## Coverage measurement

The compiler/tools Python surface is measured with `coverage.py` (subprocess
capture is required because most tests spawn `semsc`/`sem`). The `.coveragerc-audit`
config at the repo root has the parallel + source settings; the procedure:

```powershell
pip install coverage
# make subprocesses self-instrument:
"import coverage; coverage.process_startup()" | Out-File -Encoding ascii `
  (Join-Path (python -c "import sysconfig;print(sysconfig.get_path('purelib'))") coverage_subprocess.pth)
$env:COVERAGE_PROCESS_START = (Resolve-Path .coveragerc-audit)
python SemanticScript\tests\run_suite.py all --keep-going
python -m coverage combine; python -m coverage report
# IMPORTANT: delete the .pth afterward — it instruments every future python subprocess.
```

Baseline (line+branch, 2026-05-24): ~80% overall; every tool ≥ 74%
(call_contracts 100, release_versions 91, semfmt 90, semlint 88, libc_registry 86,
syntax_migration 82, bump_version 81, sem 77, semsc 75). Remaining gaps are
fragmented error/branch paths, not whole untested surfaces.

## Web And Property Testing Boundaries

There is no synthetic web-handler fixture yet: route handlers are exercised by
building a routed `target webServer` executable, launching it, and sending real
HTTP requests to the native adapter. That is deliberate for now because
`HttpRequest` / `HttpResponse` are opaque runtime handles, not plain records.

`sem run` is still a console/JIT proof loop. For web targets, use
`sem build`/`sem test` or the app-specific smoke harness so the native HTTP
runtime is linked and a real port is bound.

There is no first-class parametric/property-test syntax in SemanticScript
source today. Use Python or JS harness loops around generated fixtures when a
property-style test is needed, and register that harness in `run_suite.py` so it
is visible in the component/e2e lanes.

When testing a frozen `sem.exe`, Python harnesses are launched with a real
Python interpreter (`SEM_TEST_PYTHON`, `PYTHON`, or `python`/`python3`/`py -3`
on PATH), not by recursively invoking the frozen executable.

## Known-unwired suites

These test suites live outside the global runner and are **not** in any CI lane.
They target experiment/sample code with heavy runtime dependencies (servers,
libuv, network), so they are run manually from their own directories rather
than gating the toolchain:

- `apps/taskforge-api-client/scripts/test_taskforge_async_client.py`
- `experiments/kilo-port/scripts/test_kilo_port.py`
- `experiments/realtime-auction-arena/server/tests/*.py` (api, e2e smoke,
  enterprise/sse contracts, sqlite persistence)

The numbered `feature_tests/*.sscript` corpus, by contrast, *is* now gated by
`compiler.feature-corpus` (compile-to-IR with an XFAIL list for the 15 files
the current front end / codegen cannot yet handle).

## Maintenance

When adding a test file, register it in `run_suite.py` with the right lane (and
add it to `ci-release` if it builds/runs artifacts) so it is reachable from the
one global runner. Run the narrow lane during iteration; run `ci-release`
(or `all`) before landing changes that touch lowering, stdlib, or runtimes.
When adding a **stdlib module**, wire it into an integration harness
(`test_stdlib.py` `OK_MODULES`/`QUARANTINED_MODULES`, or
`test_native_stdlib_smoke.py` + `NATIVE_SMOKE_MODULES`); `stdlib.coverage-guard`
fails until you do.
