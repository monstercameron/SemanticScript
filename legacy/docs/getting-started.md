# Getting Started

This is the first map for humans and agents entering a SemanticScript checkout
or a new SemanticScript project. Load it before choosing narrower language,
toolchain, package, or runtime guidance.

## First Commands

From an installed release executable:

```powershell
sem.exe version --json
sem.exe bootstrap --json
sem.exe skills list --json
sem.exe skills get sem-start sem sem-agent sem-syntax --full --json
```

From a source checkout:

```powershell
python SemanticScript/tools/sem.py --version --json
python SemanticScript/tools/sem.py bootstrap --json
python SemanticScript/tools/sem.py skills list --json
python SemanticScript/tools/sem.py skills get sem-start sem sem-agent sem-syntax --full --json
```

## MCP Bootstrap

An MCP-capable agent starting from a plain installed executable should not need
repo paths or prior docs. Start the stdio server:

```powershell
sem.exe mcp
```

Register it with an MCP client using this shape:

```json
{"command":"sem.exe","args":["mcp"],"cwd":"<project-root>"}
```

The MCP initialize handshake repeats the startup calls. If the client does not
surface handshake instructions, call these tools manually:

```json
agent_docs {"path":"."}
skills_get {"names":["sem-start","sem","sem-agent","sem-syntax"],"full":true}
help {"path":"."}
```

Use `sem mcp --help` or `sem bootstrap --json` when a client only exposes the
executable and command-line help.

Optional zero-project language smoke through MCP:

```json
eval {"code":"error ConsoleWriteError\nerrorCase ConsoleWriteError ConsoleWriteFailed Int32\nstorage local immutable greetingText String \"semantic tools ready\"\ncall greetingWriteCall console.writeLine\nargument greetingWriteCall text String greetingText\nrun greetingWriteCall\nignore void source greetingWriteCall\nbind error greetingWriteError ConsoleWriteError greetingWriteCall\nbranch error source greetingWriteCall target greetingWriteFailed\njump target greetingDone\nlabel greetingWriteFailed\nmakeError greetingWriteFailure ConsoleWriteError.ConsoleWriteFailed greetingWriteError\nlabel greetingDone"}
```

## Repository Map

| Path | Purpose |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | Compact agent contract and dense language reference. |
| `SemanticScript/tools/sem.py` | Stable wrapper for validation, retrieval, repair, deps, test, MCP, and project scaffolding. |
| `SemanticScript/compiler/semsc.py` | Reference parser, AST, lowering, runtime wiring, and raw compiler CLI. |
| `SemanticScript/linter/semlint.py` | Canonical structured linter and diagnostic rules. |
| `SemanticScript/formatter/semfmt.py` | Canonical formatter. |
| `SemanticScript/std/` | Standard library contracts and self-tests. |
| `SemanticScript/runtime/` | Native runtime adapters used by compiler-lowered calls. |
| `SemanticScript/tests/` | Compiler, linter, CLI, package, stdlib, and release-contract tests. |
| `docs/` | Maintained explanation layer and reference map. |
| `docs/reference/syntax-inventory.md` | Complete syntax inventory and implementation status table. |
| `docs/toolchain/` | Compiler, linter, formatter, MCP, and editor behavior. |
| `docs/language/` | Source rows, project shape, operations, effects, records, memory, and runtime boundaries. |
| `vscode-semanticscript/` | VS Code syntax, hover, semantic token, symbol, and packaging support. |
| `packaging/` | PyInstaller, MCP bundle, registry, Scoop, winget, and release manifest support. |
| `apps/` / `experiments/` | Runnable demos and active larger-surface experiments. |

## New Project Start

Create a small project and immediately inspect it through the public wrapper:

```powershell
sem new hello-world
sem check --json hello-world
sem graph --kind summary --json hello-world
sem test --json hello-world
```

For source-checkout development, replace `sem` with
`python SemanticScript/tools/sem.py`.

## Existing Project Start

Start with the project root, a `build.sem`, or a `.sem` file:

```powershell
sem help --json PATH
sem check --json --with-readiness PATH
sem deps list --json PATH
sem graph --kind summary --json PATH
```

Use `sem slice --operation NAME --json PATH` or
`sem slice --route METHOD:/path --json PATH` once the graph identifies the
local area to edit.

## Capability And API Discovery

When a call target, capability, failure mode, cleanup row, or argument name is
not already known, ask the docs surface before generating source. `docs search`
is for discovery; `docs get` is the authoritative usage payload.

CLI:

```powershell
sem docs index --path PATH --include-std --embedding-provider none --json
sem docs search "sqlite open database capability" --path PATH --json
sem docs get sqlite.openDatabase --json
sem docs get SqliteOpenMode --json
```

MCP:

```json
docs_search {"query":"sqlite open database capability","path":".","watch":true,"include_std":true}
docs_get {"operation":"sqlite.openDatabase"}
docs_get {"operation":"SqliteOpenMode"}
```

Prefer the returned `usage.call.rows`, `usage.failureHandling.rows`,
`usage.cleanup.rows`, `usage.requiredCallerEffects`,
`usage.requiredCapabilities`, and `usage.localCapabilityRows` over guessing
from names.

CLI `docs search` reads a SQLite index. If it reports `status:
"index-missing"`, run `docs index` first. MCP `docs_search` with `watch: true`
starts or reuses the background index worker.

## Skill Loading Order

Use `sem-start` first for orientation, then load the narrow skill for the work:

| Alias | Skill | Use When |
|---|---|---|
| `sem-start` / `sem-getting-started` | `getting-started` | You need the project map and first commands. |
| `sem` / `sem-language` | `language-core` | You are editing source rows, operations, calls, types, or dataflow. |
| `sem-agent` / `sem-testing` | `graph-and-slice` | You need retrieval, graph, slice, check, and test workflow rules. |
| `sem-syntax` / `sem-grammar` / `sem-verbs` | `syntax-reference` | You need the compact verb index, current row schemas, or implementation status table. |
| `sem-diagnostics` / `sem-builds` | `patch-and-repair` | You are resolving diagnostics or applying repair plans. |
| `sem-deps` / `sem-packages` | `package-dependencies` | You are working with `build.sem`, dependencies, cache, or lock files. |
| `sem-stdlib` | `sqlite-patterns` | You need SQLite, records, JSON CRUD, or stdlib call-target context. |

## Change Surface Rule

Language behavior changes move together:

1. Syntax/reference docs.
2. Parser/lowering in `semsc.py`.
3. Linter known verbs and diagnostics in `semlint.py`.
4. Editor grammar, hovers, semantic tokens, and indexing.
5. Focused tests and narrow docs.
6. Agent contract docs when workflows or skill aliases change.

Do not add editor-only support for language syntax. Parser, linter, docs, and
tests must move with it.
