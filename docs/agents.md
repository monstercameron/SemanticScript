# Agent Contract

This page is the compact bridge between the repo-level `AGENTS.md` contract and
the machine-readable `sem` tool surfaces. Load it with `sem-agent` when an
agent needs retrieval, repair, testing, or MCP guidance.

## First Moves

For a plain installed executable:

```powershell
sem.exe bootstrap --json
sem.exe mcp
```

For an MCP client, start with:

```json
agent_docs {"path":"."}
skills_get {"names":["sem-start","sem","sem-agent","sem-syntax"]}
help {"path":"."}
docs_search {"query":"<capability, API, type, syntax, or runtime need>","path":".","watch":true,"include_std":true}
```

Use `agent_docs` to load project-local `AGENTS.md` / `CLAUDE.md` directly from
the MCP server cwd before relying on built-in skills.
Use `docs_get` on the selected operation, target, type, or enum before
generating calls.
The `docs_get` payload is the source for exact argument names, required
effects, capabilities, failure handling, cleanup rows, and preconditions.

## Retrieval Loop

Use the public wrapper before raw compiler or linter internals:

```powershell
sem check --json PATH
sem graph --kind summary --json PATH
sem graph --kind routes --json PATH
sem slice --operation NAME --json PATH
sem explain CODE --json
sem fix --plan --json PATH
sem patch --dry-run --json PLAN.json
sem test --json PATH
```

`nextCommands` are machine-facing. Prefer `argv` over `command`, honor `cwd`,
and replay only entries where `replayable` is true. MCP-capable agents should
prefer `mcpTool` and `mcpArgs` when present; `sem fix --plan` maps to the MCP
`fix_plan` tool.

## Workflow Modes

`sem help --json PATH` and `sem bootstrap --json PATH` include a `workflows`
array. Use it to choose the right modality instead of forcing every task into
the repair loop. Current modes cover:

- `bootstrap-orient`
- `create-project`
- `learn-language-syntax`
- `discover-apis-capabilities-runtime`
- `dependencies`
- `inspect-understand`
- `author-edit-validate`
- `diagnose-repair`
- `build-run-debug`
- `test-dev-loop`
- `migrate-modernize`
- `clean-profile-maintain`

Each workflow step carries the same command contract as `nextCommands`,
including `mcpTool` and `mcpArgs` when an MCP-native tool exists.
