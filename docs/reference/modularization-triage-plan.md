# Oversized File Modularization and TODO Triage Plan

This plan defines how to reduce the maintenance risk in the current large
implementation and planning files without mixing behavior changes into file
movement. It covers these known hot spots:

| File | Current size | Primary responsibility |
|---|---:|---|
| `SemanticScript/compiler/semsc.py` | about 19.7k lines | Parse, validate, lower, link, emit, and produce agent metadata. |
| `SemanticScript/linter/semlint.py` | about 18.9k lines | Parse lint facts, run independent checks, render diagnostics. |
| `vscode-semanticscript/extension.js` | about 5.7k lines | Extension constants, tokenization, navigation, hovers, lint, compiler commands. |
| `TODO.md` | about 5.3k lines | Mixed release blockers, research backlog, hygiene notes, and future ideas. |

The goal is not to make files small for its own sake. The goal is to create
stable ownership boundaries, smaller review surfaces, and testable extraction
steps that preserve current behavior.

## Ownership Boundaries

Assign future refactors by subsystem, not by line ranges:

| Area | Owner boundary | Non-owner contract |
|---|---|---|
| Compiler front end | Tokenization, parser state, `Program` model, build tape ingestion, import resolution. | Exposes parsed `Program` data and diagnostics; does not know LLVM/codegen details. |
| Compiler semantic validation | Strict executable checks, HTTP contracts, SQL/body literal validation, resource cleanup checks. | Accepts `Program`; returns diagnostics or raises existing compiler diagnostic types. |
| Compiler lowering and codegen | `Codegen`, LLVM type mapping, operation lowering, runtime call emission. | Depends on validated `Program`; does not parse source or inspect raw build tape text. |
| Compiler build/link/runtime inputs | build directory resolution, native runtime link inputs, resources, CPU flags, executable emission. | Consumes generated IR and build metadata; does not mutate parser/codegen state except through explicit config. |
| Compiler agent output | fingerprints, trace maps, route/function summaries, agent JSON payload writing. | Observes compiled program/codegen results; must not influence generated binary behavior. |
| Linter fact model | `Token`, `SourceLine`, `ProgramFacts`, `ExtendedFacts`, standard module surface. | Produces immutable-enough facts for checks; does not emit final user output. |
| Linter rule families | Independent `check_*` diagnostics grouped by language/runtime domain. | Each check consumes `ExtendedFacts` and returns diagnostics; no global mutation or cross-check ordering assumptions. |
| Linter output and CLI | path collection, diagnostic sorting, human/json/agent/sem rendering, exit codes. | Does not contain rule logic beyond selection and rendering policy. |
| VS Code language model | verb/target/type tables, tokenization helpers, document symbol indexes. | Shared by hover, semantic token, completion, and definition providers. |
| VS Code UI providers | decorations, semantic tokens, hover, definition, document symbols, completion. | Use the language model; do not shell out to compiler/linter. |
| VS Code tool adapters | configuration sync, linter process, compiler process, diagnostics, status bars. | Owns process management only; does not duplicate semantic rules already in Python. |
| Release backlog | One GitHub issue per independently shippable outcome. | `TODO.md` becomes an index and migration ledger, not a long-lived primary tracker. |

## Extraction Rules

Every extraction PR should follow these rules:

1. Move code before changing behavior.
2. Keep old public CLI entry points and extension activation behavior working.
3. Add imports through narrow module names that describe ownership, not generic
   buckets like `utils.py` or `helpers.js`.
4. Preserve diagnostics codes, messages, span roles, JSON keys, and exit codes
   unless the PR is explicitly a behavior-change PR.
5. Put one subsystem extraction and its tests in one PR. Do not combine compiler,
   linter, extension, and TODO migration work in a single patch.
6. Land compatibility shims temporarily when needed, then remove them in a
   follow-up after downstream imports are updated.
7. Stop and write a design note before extracting shared code between compiler
   and linter. Duplication is safer than an unstable shared API.

## Safe Extraction Order

Use this order because it starts with low-coupling data and rendering code,
then moves toward parser and codegen internals.

### Stage 0: Baseline and Freeze Points

- Record current line counts and public commands in the issue before editing.
- Capture golden outputs for representative parse, lint, compile, VS Code lint,
  and TODO search workflows.
- Add temporary "moved only" labels to extraction PRs and reject unrelated
  behavior changes during review.
- Identify downstream import assumptions in tests, scripts, docs, and extension
  configuration before moving files.

Gate:

```powershell
python SemanticScript/compiler/semsc.py --help
python SemanticScript/linter/semlint.py --help
cd vscode-semanticscript
npm run check
```

If `npm run check` is not available in the local package, run the closest
existing package script and record the substitution in the PR.

### Stage 1: Compiler Peripheral Extraction

Start with code that has minimal parser/codegen coupling:

- Move agent JSON/fingerprint/trace-map helpers from the tail of `semsc.py` into
  `SemanticScript/compiler/agent_payload.py`.
- Move build directory, build metadata, CPU feature, and resource path resolution
  into `SemanticScript/compiler/build_config.py`.
- Move native runtime link input discovery into
  `SemanticScript/compiler/native_links.py`, keeping `libc_registry.py` as the
  existing low-level registry boundary.
- Move Windows resource rendering and icon packing into
  `SemanticScript/compiler/windows_resources.py`.

Do not move `Program`, parser functions, `Codegen`, or strict validation in this
stage.

Gate:

```powershell
python SemanticScript/compiler/semsc.py SemanticScript/sem/feature_tests/<representative>.sscript --parse-only
python SemanticScript/tests/test_compiler.py
python SemanticScript/tests/test_stdlib.py
```

Where a representative feature test is not obvious, use one basic call/bind
case and one case that exercises build metadata or native runtime linking.

### Stage 2: Compiler Validation Extraction

Extract validators after peripheral modules are stable:

- Move HTTP route, middleware, nullable body, and response-forwarder checks into
  `SemanticScript/compiler/validators/http_contracts.py`.
- Move strict executable resource cleanup checks into
  `SemanticScript/compiler/validators/resources.py`.
- Move SQL and JSON body validation helpers into
  `SemanticScript/compiler/validators/body_literals.py` only after confirming
  no parsing state is hidden in closure variables.
- Keep `validate_strict_executable(prog)` as the public orchestrator until all
  call sites are updated.

Gate:

```powershell
python SemanticScript/compiler/semsc.py SemanticScript/sem/feature_tests/<strict-negative>.sscript --parse-only
python SemanticScript/compiler/semsc.py SemanticScript/sem/feature_tests/<strict-positive>.sscript --parse-only
python SemanticScript/tests/test_compiler.py
```

The negative fixture must prove compiler rejection without relying on
`semlint.py`.

### Stage 3: Compiler Front End and Codegen Split

Only split the high-coupling core after stages 1 and 2 have landed:

- Move tokenization and syntax row canonicalization into
  `SemanticScript/compiler/parser_tokens.py`.
- Move dataclasses and the `Program` model into
  `SemanticScript/compiler/model.py`.
- Move `parse(...)`, top-level handlers, build tape source conversion, import
  resolution, and external literal loading into
  `SemanticScript/compiler/parser.py`.
- Move LLVM type helpers and `OutputContract` into
  `SemanticScript/compiler/types.py` only if the `Codegen` dependency graph is
  clear.
- Move `Codegen` last, preferably unchanged, into
  `SemanticScript/compiler/codegen.py`.

Gate:

```powershell
python SemanticScript/compiler/semsc.py SemanticScript/sem/feature_tests/<case>.sscript --parse-only
python SemanticScript/compiler/semsc.py SemanticScript/sem/feature_tests/<case>.sscript --emit-llvm-ir
python SemanticScript/tests/test_compiler.py
python SemanticScript/tests/test_stdlib.py
```

Require a before/after IR comparison for at least one stable fixture. Ignore
expected path or timestamp differences only if they are documented.

### Stage 4: Linter Framework Extraction

Extract framework pieces before rule families:

- Move dataclasses, enums, and diagnostic rendering types into
  `SemanticScript/linter/model.py`.
- Move `tokenize_line`, source row part parsers, and `parse_file` into
  `SemanticScript/linter/parser.py`.
- Move standard module discovery and built-in surface registration into
  `SemanticScript/linter/stdlib_surface.py`.
- Move `gather_extended` and fact derivation helpers into
  `SemanticScript/linter/facts.py`.
- Move renderer functions into `SemanticScript/linter/renderers.py`.
- Keep `semlint.py` as the CLI orchestration shell until imports are stable.

Gate:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem/feature_tests/<case>.sscript --format human
python SemanticScript/linter/semlint.py SemanticScript/sem/feature_tests/<case>.sscript --format json
python SemanticScript/linter/test_semlint.py
```

### Stage 5: Linter Rule Family Extraction

Move checks by domain, preserving each function name where practical:

- `rules/metadata.py`: unused calls, labels, capabilities, error cases,
  metadata gaps, vague names.
- `rules/dataflow.py`: bind disposition, unresolved references, duplicate
  declarations, dead stores, branch semantics, argument arity/type checks.
- `rules/resources.py`: heap allocation, locks, file handles, SQLite cleanup,
  guard tokens, stack limits.
- `rules/async_runtime.py`: task groups, submit work, select/wait-set, start and
  await rules.
- `rules/json_sql.py`: JSON body/path/string checks, SQL body/literal/transaction
  and returning checks.
- `rules/http.py`: route coverage, route methods, middleware effects, guarded
  HTTP input, response body forwarders.
- `rules/build_modules.py`: build tape schema, registered modules, import
  contracts, export contract tape.

Use an explicit rule registry such as `RULES = (...)` rather than scanning
modules dynamically. Dynamic discovery makes rule order harder to review.

Gate:

```powershell
python SemanticScript/linter/test_semlint.py
python SemanticScript/linter/semlint.py SemanticScript/sem/feature_tests/<case>.sscript --format agent
python SemanticScript/linter/semlint.py SemanticScript/sem/feature_tests/<case>.sscript --format sem
```

### Stage 6: VS Code Extension Extraction

Split the extension after Python CLI behavior is stable:

- Move static data tables and generated hover text maps into `src/languageData.js`.
- Move tokenization, line classification, symbol indexes, and build tape helpers
  into `src/languageModel.js`.
- Move semantic token provider and decorations into `src/semanticTokens.js` and
  `src/decorations.js`.
- Move hover, definition, symbols, and completions into `src/navigation.js`.
- Move linter process, compiler process, configuration, and status bars into
  `src/tooling.js`.
- Keep `extension.js` as `activate`/`deactivate` registration glue.

Do not duplicate linter semantics in JavaScript while extracting. The extension
may provide editor convenience checks, but Python remains the diagnostic source
of truth for linter behavior.

Gate:

```powershell
cd vscode-semanticscript
npm run check
```

If tests are added later, include activation smoke tests for command
registration, linter path resolution, diagnostic parsing, and semantic token
coverage.

### Stage 7: TODO.md Migration

Treat `TODO.md` as a migration source, not the permanent tracker.

1. Create GitHub labels before filing issues:
   `area/compiler`, `area/linter`, `area/vscode`, `area/docs`,
   `area/runtime`, `area/stdlib`, `kind/bug`, `kind/refactor`,
   `kind/research`, `kind/release-blocker`, `priority/P0`, `priority/P1`,
   `priority/P2`, `needs/design`, `needs/test`, `tracking`.
2. Convert each top-level TODO section into either a tracking issue or a
   milestone epic. Keep P0 release blockers separate from research or
   nice-to-have work.
3. Split checklist items into child issues only when they can land
   independently with their own tests.
4. Preserve the original TODO heading, copied acceptance criteria, and source
   link back to the TODO commit or line range in every migrated issue.
5. Mark migrated checklist entries in `TODO.md` with the issue number instead
   of deleting them in the same PR.
6. After a complete section is migrated, replace the section body with a short
   pointer to the tracking issue and milestone.
7. Keep `TODO.md` under 500 lines after migration by making it an index:
   release blockers, active tracking issues, and archival migration notes.

Suggested issue template:

```markdown
## Source

- Migrated from `TODO.md`, heading: `<exact heading>`
- Original priority: `P0|P1|P2|P3`

## Problem

<one concrete user or maintainer impact>

## Scope

- In scope: <files/subsystems>
- Out of scope: <explicit exclusions>

## Acceptance Criteria

- [ ] <observable outcome>
- [ ] <test or command gate>

## Dependencies

- Blocks: <issue or none>
- Blocked by: <issue or none>
```

## PR Review Checklist

Use this checklist for every modularization PR:

- The PR title says `move-only` when behavior is intended to be unchanged.
- Changed files stay inside the declared owner boundary.
- Public commands, exit codes, and JSON payload shapes are unchanged.
- Tests or golden outputs cover the moved code path.
- Imports are acyclic and do not create a new shared "misc" module.
- `TODO.md` edits only migrate or link items; they do not silently delete work.
- The PR description names the next safe extraction step.

## Stop Conditions

Pause the refactor and open a design issue if any of these happen:

- A move requires changing diagnostic behavior to pass tests.
- Compiler and linter extraction need a shared abstraction that neither side
  already owns.
- VS Code extraction requires changing extension activation or command names.
- TODO migration uncovers duplicate or conflicting release criteria.
- A proposed module would exceed roughly 3k lines immediately after extraction.

