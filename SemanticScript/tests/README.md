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
| **component** | One tool exercised against a fixture / smoke; no full build | parser & linter `tiny` fixtures, `sem.*` JSON smokes, `async.lowering`, `syntax.migration`, `vscode.check` |
| **integration** | Builds or runs real artifacts (compiler → IR/exe, stdlib, apps, native runtimes) | `compiler.full`, `stdlib.full`, `stdlib.native-smoke`, `event-runtime.native`, `app.runtime-smoke` |
| **e2e** | End-to-end parity of generated output and `.sem` source aliases | `reference.parity`, `sem-alias.parity` |

`all` = unit + component + integration + e2e.

### Standard-library suite

`stdlib` (alias `std`) groups all standard-library testing into one
reference: `stdlib.full` (per-module JIT smokes; http quarantined),
`stdlib.native-smoke` (native-exe smokes for log / bcrypt / jwt / net), and
`event-runtime.native` (the event/async native C runtime backing `std/event`).

```powershell
python SemanticScript\tests\run_suite.py stdlib   # or: std
```

## CI lanes (GitHub `.github/workflows/ci.yml`)

| Suite | Where it runs | Notes |
|-------|---------------|-------|
| **ci-fast** | Python 3.11 + 3.12 on Windows | Pure-Python validation; no native toolchain needed |
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
| `tests/test_async_wait_sets.py` | component | async lowering / wait-set shape |
| `tests/test_syntax_migration.py` | component | legacy → current syntax migration |
| `tests/test_app_syntax_cutover.py` | component | app syntax cutover |
| `tests/test_compiler.py` | integration | parser, codegen, diagnostics, native emit |
| `tests/test_stdlib.py` | integration | stdlib JIT smokes (http quarantined) |
| `tests/test_native_stdlib_smoke.py` | integration | native-exe stdlib smokes (log, bcrypt, jwt, net) |
| `tests/test_event_runtime_native.py` | integration | event/async native C runtime |
| `tests/test_app_runtime_smoke.py` | integration | app builds/runs (desktop, html, tui, http, web) |
| `tests/compare.py` | e2e | reference output parity |
| `tests/sem_alias_parity.py` | e2e | `.sem` source/JS output parity |

Fixtures: `tiny.sem`, `tiny.sscript`, `agent_cli_demo.test.sem`, and the
`*.sscript` runtime smokes are minimal inputs used by the component lane.

## Maintenance

When adding a test file, register it in `run_suite.py` with the right lane (and
add it to `ci-release` if it builds/runs artifacts) so it is reachable from the
one global runner. Run the narrow lane during iteration; run `ci-release`
(or `all`) before landing changes that touch lowering, stdlib, or runtimes.
