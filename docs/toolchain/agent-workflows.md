# Agent Workflows

This page defines the stable `sem` command paths intended for agent-driven
SemanticScript work. Prefer these commands before using direct compiler or
linter internals.

## Core Loop

The intended multi-step loop is:

```text
load matching rules
check
inspect graph or slice
explain diagnostics
propose repairs
preview patch
apply patch
re-check and re-test
```

The corresponding commands are:

```powershell
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py skills get sem sem-agent --json
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py graph --kind calls --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py explain CODE --json
python SemanticScript\tools\sem.py fix --plan --json PATH
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py patch --apply --json PLAN.json
python SemanticScript\tools\sem.py test --json PATH
```

## Version-Matched Skills

Agents should load repo-backed guidance from the same `sem` binary that will
validate the project.

```powershell
python SemanticScript\tools\sem.py skills list --json
python SemanticScript\tools\sem.py skills get sem --json
python SemanticScript\tools\sem.py skills get sem-agent sem-diagnostics --json
```

The current public aliases map to canonical bundled skills:

- `sem` -> `language-core`
- `sem-agent` -> `graph-and-slice`
- `sem-language` -> `language-core`
- `sem-diagnostics` -> `patch-and-repair`
- `sem-stdlib` -> `sqlite-patterns`
- `sem-builds` -> `patch-and-repair`
- `sem-packages` -> `patch-and-repair`
- `sem-testing` -> `graph-and-slice`

Use `skills list --json` to discover the exact file set and alias index shipped
with the current tool version.

## Fast Validation

Run the smallest useful validation set before and after focused edits:

```powershell
python -m py_compile SemanticScript\compiler\semsc.py SemanticScript\linter\semlint.py SemanticScript\tools\sem.py
python SemanticScript\tools\sem.py check --json SemanticScript\tests\tiny.sem
python SemanticScript\tools\sem.py fmt --check SemanticScript\tests\tiny.sem
python SemanticScript\tools\sem.py test --json SemanticScript\tests\tiny.sem --skip-python-harnesses
```

Use the broader release commands in `RELEASE.md` when changing compiler,
runtime, stdlib, package, or editor behavior.

## Machine-Readable Commands

These commands are the current agent-first JSON surfaces:

```powershell
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py doctor --json
python SemanticScript\tools\sem.py readiness --json PATH
python SemanticScript\tools\sem.py context --json PATH
python SemanticScript\tools\sem.py symbols --json PATH
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py graph --kind calls --json PATH
python SemanticScript\tools\sem.py graph --kind effects --json PATH
python SemanticScript\tools\sem.py graph --kind capabilities --json PATH
python SemanticScript\tools\sem.py graph --kind routes --json PATH
python SemanticScript\tools\sem.py graph --kind dataflow --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py slice --route METHOD:/path --json PATH
python SemanticScript\tools\sem.py slice --effect database --json PATH
python SemanticScript\tools\sem.py slice --capability session.user --json PATH
python SemanticScript\tools\sem.py size --json PATH
python SemanticScript\tools\sem.py explain CODE --json
python SemanticScript\tools\sem.py fix --plan --json PATH
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py patch --apply --json PLAN.json
python SemanticScript\tools\sem.py dev --json PATH
python SemanticScript\tools\sem.py test --json PATH
```

Current schema versions:

- `sem.version.v1`
- `sem.skills.v1`
- `sem.readiness.v1`
- `sem.context.v1`
- `sem.symbols.v1`
- `sem.check.v1`
- `sem.graph.v1`
- `sem.slice.v1`
- `sem.size.v1`
- `sem.explain.v1`
- `sem.fixPlan.v1`
- `sem.patch.v1`
- `sem.dev.v1`
- `sem.test.v1`

Representative `sem check --json` diagnostic shape:

```json
{
  "code": "SS3104",
  "severity": "warning",
  "message": "declared effect lacks capability or authority coverage",
  "span": {
    "file": "C:/repo/apps/taskforge-web/main.sem",
    "line": 42,
    "column": 1,
    "role": "subject"
  },
  "expected": "capability or authority covering the declared effect",
  "actual": "no matching useCapability or authority row was found",
  "repair": {
    "id": "add-missing-capability",
    "safe": true,
    "fixSafety": "behavior-preserving"
  },
  "explain": {
    "code": "SS3104",
    "command": "sem explain SS3104 --json"
  }
}
```

## Semantic Retrieval

Prefer graph and slice output to ad hoc grep when an edit touches architecture,
authority, or runtime behavior.

Examples:

```powershell
python SemanticScript\tools\sem.py graph --kind calls --json apps\taskforge-web
python SemanticScript\tools\sem.py graph --kind routes --json apps\taskforge-web
python SemanticScript\tools\sem.py graph --kind capabilities --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --operation createTodoHandler --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --route POST:/todos --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --symbol TodoRecord --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --effect database --json apps\taskforge-web
```

Use `context --json` for project envelope facts and `symbols --json` for the
full source graph when `graph` or `slice` is too narrow.

## Repair And Patch

`sem fix --plan --json` is the proposal step. It should be reviewed or
transformed before `sem patch`.

```powershell
python SemanticScript\tools\sem.py fix --plan --json SemanticScript\tests\tiny.sem
python SemanticScript\tools\sem.py patch --dry-run --json plan.json
python SemanticScript\tools\sem.py patch --apply --json plan.json
```

`patch` rejects stale plans when file hashes no longer match the generation
time state. On apply, it normalizes touched files through `semfmt` and re-runs
`sem check`.

## Readiness, Dev, And Test

Use readiness when a failure might be environment or backend related instead of
source-related:

```powershell
python SemanticScript\tools\sem.py readiness --json apps\taskforge-web
```

Use the dev payload to hand an agent a stable watch-plan contract:

```powershell
python SemanticScript\tools\sem.py dev --json apps\taskforge-web
python SemanticScript\tools\sem.py dev --trace --json apps\taskforge-web
```

Use the test payload to discover SemanticScript tests and Python app harnesses:

```powershell
python SemanticScript\tools\sem.py test --json apps\taskforge-web
python SemanticScript\tools\sem.py test --json SemanticScript\tests\tiny.sem --skip-python-harnesses
```

## Contract Validation

The agent-facing commands are covered by:

- `python -m unittest SemanticScript.tests.test_sem_cli`
- `python -m unittest SemanticScript.tests.test_command_contracts`

These tests assert schema versions, required fields, and representative repair
metadata so prose-only regressions are caught early.

## Updating Generated Docs

Generated documentation should be updated only by the tool that owns it. When
no generator exists, edit the source documentation directly and do not invent a
generated output file. Keep regenerated files in the same change as the source
that caused them to change.

## Ignored Artifacts

Do not patch ignored build output. Use a dry run before cleanup:

```powershell
python SemanticScript\tools\sem.py clean
```

Expected ignored locations include `build/`, `.semcache/`, native executable
and object output, LLVM IR output, packaged VSIX files, Python caches, and
local app data such as `apps/taskforge-tui/todos.json`. Pass `--force` only
after reviewing the dry run.
