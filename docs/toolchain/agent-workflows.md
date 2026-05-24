# Agent Workflows

This page defines the stable `sem` command paths intended for agent-driven
SemanticScript work. Prefer these commands before using direct compiler or
linter internals.

## Core Loop

The intended semantic loop is:

```text
load matching rules
check
inspect graph or slice
explain diagnostics
propose repairs
preview patch
apply patch
re-check
```

The corresponding semantic-loop commands are:

```powershell
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py skills get sem sem-agent --json
python SemanticScript\tools\sem.py deps sync --json PATH
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py graph --kind summary --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py explain CODE --json
python SemanticScript\tools\sem.py fix --plan --json PATH
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py patch --apply --json PLAN.json
python SemanticScript\tools\sem.py check --json PATH
```

`skills get --json` now returns a summary/index payload by default. Use
`--full --json` only when an agent truly needs the raw skill source bodies.
Only auto-apply a patch plan after confirming `status: "actionable"` and
`planUsable: true` from `sem fix --plan --json`. If the plan reports
`status: "mixed"`, the machine edits only cover part of the surface; start
with `sem patch --dry-run` and keep the remaining diagnostics visible. If the
plan reports `status: "suggestions-only"`, there is no machine-applicable
patch. Compact fix payloads are review-only; use `--full` before saving a plan
for `sem patch`.

On large project surfaces, `check`, `fix`, `graph`, and `slice` are compact by
default. Add `--full` when you explicitly need the entire machine payload.

Harness loop, only after semantic preflight is clean:

```powershell
python SemanticScript\tools\sem.py test --json PATH
python SemanticScript\tools\sem.py dev --json PATH
```

## Why Each Tool Exists

For a long agent session, the important question is not only "what commands
exist?" but "what uncertainty does each command remove?"

- `skills get` removes rule uncertainty.
  It loads the repo-backed guidance for the exact tool version in use.
- `deps sync|verify|list|cache|purge` removes dependency-state uncertainty.
  It materializes external `dependency*` packages into the cache and lock so
  imports resolve, and is the full package lifecycle: `sync` creates/updates
  (only this and `sync --force` touch the network), `list`/`cache` read,
  `verify` detects a corrupt cache, `sync --force` redownloads/repairs, and
  `purge` deletes. Run `sync` before `check` on a project with external
  dependencies. `cache` inventories the shared machine cache + project cache.
- `check --json` removes source-state uncertainty.
  It is the main semantic gate before and after edits.
- `graph --json` removes architecture uncertainty.
  `summary` and `routes` are the cheap first hop; richer graph kinds are
  follow-up inspection, not the default starting point.
- `slice --json` removes local-context uncertainty.
  It gives the agent one semantic neighborhood to edit instead of forcing a
  whole-project grep and reassembly pass.
- `explain CODE --json` removes rule-meaning uncertainty.
  It tells the agent what the diagnostic means and why the rule exists.
- `fix --plan --json` removes repair-shape uncertainty.
  It converts diagnostics into candidate edits without mutating files.
- `patch --dry-run|--apply` removes execution uncertainty.
  It previews or applies a reviewed plan with stale-file and post-apply checks.
- `fmt --check` removes formatting uncertainty.
  It keeps diffs stable so repair plans and review output stay comparable.
- `test --json` removes behavior uncertainty.
  Use it after semantic preflight is clean; it is not the first gate on a red
  project surface.
- `dev --json` removes watch/restart uncertainty.
  It tells the agent what to watch, when restart is legal, and what follow-up
  steps make sense.
- `readiness --json` removes environment uncertainty.
  It separates code problems from toolchain/runtime/target problems. Keep it as
  a separate hop from `check` unless you explicitly need `--with-readiness`.
- `size --json` removes footprint uncertainty.
  It is the cheap probe before spending context on bigger graph surfaces.

That is the intended order of work:

```text
load rules
prove current source state
map the surface cheaply
pull one local neighborhood
understand the rule
propose a repair
preview/apply it
re-check
only then run behavior/watch loops
```

Green validation fixture:

```powershell
python SemanticScript\tools\sem.py check --json SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py fmt --check SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py test --json SemanticScript\tests\agent_cli_demo.test.sem --skip-python-harnesses
```

Copyable PowerShell repair loop on a disposable file:

```powershell
Copy-Item SemanticScript\tests\tiny.sem .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
python SemanticScript\tools\sem.py explain SS3104 --json
python SemanticScript\tools\sem.py slice --operation main --json .\scratch.sem
python SemanticScript\tools\sem.py fix --plan --json .\scratch.sem | Out-File plan.json -Encoding utf8
python SemanticScript\tools\sem.py patch --dry-run --json plan.json
python SemanticScript\tools\sem.py patch --apply --json plan.json
python SemanticScript\tools\sem.py fmt --check .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
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

## Tooling Smoke

Run the smallest useful validation set before and after focused edits:

```powershell
python -m py_compile SemanticScript\compiler\semsc.py SemanticScript\linter\semlint.py SemanticScript\tools\sem.py
python SemanticScript\tools\sem.py check --json SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py fmt --check SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py test --json SemanticScript\tests\agent_cli_demo.test.sem --skip-python-harnesses
```

Use the broader release commands in `RELEASE.md` when changing compiler,
runtime, stdlib, package, or editor behavior.

## Machine-Readable Commands

Primary agent-loop surfaces:

```powershell
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py doctor --json
python SemanticScript\tools\sem.py readiness --json PATH
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py graph --kind summary --json PATH
python SemanticScript\tools\sem.py graph --kind routes --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py slice --route METHOD:/path --json PATH
python SemanticScript\tools\sem.py size --json PATH
python SemanticScript\tools\sem.py explain CODE --json
python SemanticScript\tools\sem.py fix --plan --json PATH
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py patch --apply --json PLAN.json
python SemanticScript\tools\sem.py dev --json PATH
python SemanticScript\tools\sem.py test --json PATH
```

Lower-level fallback surfaces:

```powershell
python SemanticScript\tools\sem.py context --json PATH
python SemanticScript\tools\sem.py symbols --json PATH
python SemanticScript\tools\sem.py graph --kind calls --json PATH
python SemanticScript\tools\sem.py graph --kind effects --json PATH
python SemanticScript\tools\sem.py graph --kind capabilities --json PATH
python SemanticScript\tools\sem.py graph --kind dataflow --json PATH
python SemanticScript\tools\sem.py slice --effect database --json PATH
python SemanticScript\tools\sem.py slice --capability session.user --json PATH
```

These payloads should not stop at facts. The core agent surfaces also return a
`nextCommands` list with concrete follow-up CLI steps and reasons. Treat
`command` as display text and `argv` as the replay-safe machine surface. Each
follow-up can also carry:

- `cwd` for the intended working directory
- `replayable` to distinguish exact follow-ups from templates
- `requiredArgs` for missing user/project path inputs
- `artifactInputs` for steps that depend on a saved prior payload such as a fix
  plan file

Current stable `v1` schema versions:

- `sem.version.v1`
- `sem.skills.v1`
- `sem.readiness.v1`
- `sem.context.v1`
- `sem.symbols.v1`
- `sem.check.v1`
- `sem.graph.v1`
- `sem.slice.v1`
- `sem.size.v1`
- `sem.docs.v1`
- `sem.explain.v1`
- `sem.fixPlan.v1`
- `sem.patch.v1`
- `sem.dev.v1`
- `sem.test.v1`

Current provisional machine surface:

- `sem.doctor.v0`

For project-surface `sem test --json`, read these fields together:

- `preflightStatus`
- `runtimeHarnessStatus`
- `compositeStatus`

This keeps semantic-red/runtime-green surfaces explicit instead of collapsing
them into one ambiguous top-level status.

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
python SemanticScript\tools\sem.py slice --route POST:/api/todos --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --symbol serverPortNumber --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --effect database --json apps\taskforge-web
```

Use `context --json` for project envelope facts and `symbols --json` for the
full source graph when `graph` or `slice` is too narrow. They remain public,
but `graph` and `slice` are the primary agent-repair retrieval surfaces.

Use `docs` when an agent needs API help for standard-library operations or
compiler-owned targets without scanning the whole std tree:

```powershell
python SemanticScript\tools\sem.py docs list --module http --json
python SemanticScript\tools\sem.py docs get http.clientGet --json
python SemanticScript\tools\sem.py docs get gui.applicationCreate --json
python SemanticScript\tools\sem.py docs get json.createDocument --json
python SemanticScript\tools\sem.py docs get console.writeLine --json
```

For code generation, prefer `docs get --json` over `list`: the full payload
includes `purpose`, `invariants`, `usage.call.rows`,
`usage.requiredCallerEffects`, `usage.requiredCapabilities`,
`usage.failureMode`, `usage.failureHandling`, `usage.cleanup`,
`capabilityDetails`, and runtime binding preconditions. Treat
`usage.call.rows` as call-and-bind rows, not the whole safe integration; append
`usage.failureHandling.rows` and `usage.cleanup.rows` whenever their `required`
flags are true, and satisfy `usage.preconditions` before the call when present.
Cleanup payloads for `c.free` include required heap-free effect and authority
guidance. When a required capability is not exported, prefer
`usage.authorityRows` or the complete local declaration/use pairs in
`usage.localCapabilityRows` over std-internal capability names. Public lookup hides runtimeBinding helpers by default; pass `--all`
only when intentionally inspecting std internals. Modules that expose
compiler-owned targets instead of operation rows report `moduleDocs` and
`moduleDocs[].callTargets`; `docs get TARGET --json` returns a focused
target payload for lowered `gui.*`, known `json.*`, `console.*`, `math.*`,
`pointer.*`, and selected `c.*` targets. Compiler-owned target payloads set
`usage.importRequired: false` and an empty `usage.importRow`. Get payloads keep
`moduleDocs` compact; use `list` for the broad inventory. Reserved targets
carry `loweringStatus: "reserved"` and should not be used for generated code.

## Repair And Patch

`sem fix --plan --json` is the proposal step. It should be reviewed or
transformed before `sem patch`. By default it is blocker-first; add
`--include-warnings` only when you want cleanup guidance on an already
buildable surface. When the payload reports `status: "mixed"` together with
`planUsable: true`, the plan is still a valid next step and the command exits
success so an agent can continue into review or dry-run patching.

```powershell
Copy-Item SemanticScript\tests\tiny.sem .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
python SemanticScript\tools\sem.py explain SS3104 --json
python SemanticScript\tools\sem.py slice --operation main --json .\scratch.sem
python SemanticScript\tools\sem.py fix --plan --json .\scratch.sem | Out-File plan.json -Encoding utf8
python SemanticScript\tools\sem.py patch --dry-run --json plan.json
python SemanticScript\tools\sem.py patch --apply --json plan.json
python SemanticScript\tools\sem.py fmt --check .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
```

Only auto-apply a plan when the fix payload reports `status: "actionable"` and
`planUsable: true`. A `mixed` plan is review-first and should begin with
`sem patch --dry-run`, but it is still a usable machine contract. A compact
fix payload is not a valid patch input; emit `--full` before saving a plan.

`patch` rejects stale plans when file hashes no longer match the generation
time state. On apply, it normalizes touched files through `semfmt` and re-runs
`sem check`. A patch plan that cannot be loaded or validated now returns a
structured `sem.patch.v1` error payload instead of a raw Python traceback.

## Readiness, Dev, And Test

Use readiness when a failure might be environment or backend related instead of
source-related:

```powershell
python SemanticScript\tools\sem.py readiness --json apps\taskforge-web
```

`sem check --json` is the source lane. `sem readiness --json` is the
environment/target lane. If you need one payload for both, use
`sem check --json --with-readiness PATH`; that call now fails when the embedded
readiness payload is not `ok`.

Use the dev payload to hand an agent a stable watch-plan contract:

```powershell
python SemanticScript\tools\sem.py dev --json apps\taskforge-web
python SemanticScript\tools\sem.py dev --trace --json apps\taskforge-web
```

For the current TaskForge checkout, this is a blocked watch-plan example, not a
restart-ready loop. It is useful for inspecting watch scope, readiness, and
follow-up commands while the project is diagnostic-red.

Use the test payload to discover SemanticScript tests and Python app harnesses:

```powershell
python SemanticScript\tools\sem.py test --json apps\taskforge-web
python SemanticScript\tools\sem.py test --json SemanticScript\tests\agent_cli_demo.test.sem --skip-python-harnesses
```

Passing a non-test source path is still legal, but it now reports
`status: "no-tests"` and exits nonzero instead of pretending a validation run
happened.

When the requested surface has semantic diagnostics, `sem test --json PATH`
surfaces that preflight state in `status`, `preflightCheck`, and
`preflightStatus` even if a Python app harness succeeds. Agents should treat
`check` as the source-of-truth gate and use `--skip-python-harnesses` only to
suppress process-level harness work. For project-surface semantic validation,
use `sem check --json PATH`. Skipping Python harnesses does not hide preflight
source diagnostics on project surfaces, and project-surface Python harnesses
are deferred until semantic preflight is clean. Use
`--allow-red-preflight-harnesses` when runtime-harness signal is still
valuable on a semantic-red project. In that mode, runtime harnesses are
prioritized and project-surface semantic contract files are deferred.

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
