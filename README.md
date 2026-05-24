# SemanticScript

[![Version](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmonstercameron%2FSemanticScript%2Fmain%2Fversion.json&query=%24.version&label=version)](https://github.com/monstercameron/SemanticScript/blob/main/version.json)
[![CI](https://github.com/monstercameron/SemanticScript/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/monstercameron/SemanticScript/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

SemanticScript is a pre-release, agent-first application language and toolchain.

It is designed around explicit, line-addressable source records: operations
name their effects, capabilities, memory behavior, failure paths, runtime
edges, and review intent directly in the source. The goal is not terse code. The
goal is code that humans and agents can inspect, repair, and validate without
guessing.

Current release status: `0.0.1` pre-release. No stable public release has been
published yet.

## What Works

- Python reference compiler for `.sscript` and `.sem`.
- LLVM IR generation, JIT execution, and clang-linked native executables.
- Structured linter, formatter, and semantic diagnostics.
- `sem` CLI for validation, graph/slice retrieval, repair planning, patching,
  readiness checks, and test orchestration.
- VS Code extension for syntax, semantic highlighting, hovers, diagnostics, and
  compiler integration.
- Native runtime adapters for HTTP, SQLite, JSON, bcrypt, HTML templating, and
  selected GUI/terminal surfaces.
- Curated app and runtime demos under `apps/`.

SemanticScript is still evolving. Treat the compatibility boundary in
[docs/reference/compatibility.md](docs/reference/compatibility.md) and the
implementation inventory in
[docs/reference/syntax-inventory.md](docs/reference/syntax-inventory.md) as the
source of truth.

## Quickstart

From the repository root:

```powershell
python -m pip install -r requirements.txt -c constraints.txt
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py check --json SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py test --json SemanticScript\tests\agent_cli_demo.test.sem --skip-python-harnesses
```

Scaffold a small project:

```powershell
python SemanticScript\tools\sem.py new hello-world
python SemanticScript\tools\sem.py check --json hello-world
```

List the central validation lanes:

```powershell
python SemanticScript\tests\run_suite.py --list
```

Run the CI-equivalent fast lane:

```powershell
python SemanticScript\tests\run_suite.py ci-fast
```

## Language Shape

SemanticScript source is a semantic tape. Each row records one fact.

```semanticscript
operation createTodoHandler
input operation createTodoHandler request HttpRequest
input operation createTodoHandler response HttpResponse
output operation createTodoHandler Int32
effect createTodoHandler read http.request.body
effect createTodoHandler readWrite database
effect createTodoHandler write http.response
useCapability createTodoHandler httpRequestReader
useCapability createTodoHandler httpResponseWriter
useCapability createTodoHandler sqliteDatabaseReadWriter
memory createTodoHandler heap auto
async createTodoHandler no
purpose operation createTodoHandler "Create one todo owned by the authenticated session user."
invariant operation createTodoHandler "The user id comes from the session, never from request JSON."
```

That header is not decoration. It gives tools and reviewers a compact contract:
what the operation reads, writes, allocates, authorizes, and must preserve.

## Tooling Loop

Use `sem` before dropping to compiler or linter internals:

```powershell
python SemanticScript\tools\sem.py skills list --json
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py graph --kind summary --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py explain CODE --json
python SemanticScript\tools\sem.py fix --plan --json PATH
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py test --json PATH
```

The intended repair loop is:

```text
skills -> check -> graph/slice -> explain -> fix plan -> dry-run patch -> apply -> check -> test
```

## Repository Map

```text
SemanticScript/
  compiler/       Reference compiler
  linter/         Structured diagnostics linter
  formatter/      Source formatter
  runtime/        Native runtime adapters
  std/            Standard library modules
  tests/          Unit, component, integration, and e2e suites

apps/             Curated runnable demos and runtime harnesses
docs/             Maintained documentation
experiments/      Larger research and stress ports
packaging/        Release packaging definitions
vscode-semanticscript/
                  Local VS Code language extension
third_party/      Vendored native dependencies and notices
```

## Demos

- `apps/taskforge-tui/`: console todo app with JSON persistence.
- `apps/html-template-lab/`: compact HTML template and module-split rendering
  demo.
- `apps/http-runtime-gauntlet/`: native HTTP runtime conformance harness.
- `apps/taskforge-web/`: preview multi-user web app with native HTTP, SQLite,
  bcrypt, sessions, static assets, HTML pages, and JSON APIs.
- `apps/desktop-window-smoke/`: minimal Windows GUI smoke fixture.

TaskForge Web is a preview proof point, not a polished product surface. Its
current status is documented in [apps/taskforge-web/README.md](apps/taskforge-web/README.md).

## Documentation

- [docs/overview.md](docs/overview.md): language and toolchain overview.
- [docs/README.md](docs/README.md): developer documentation entry point.
- [docs/language/README.md](docs/language/README.md): language model.
- [docs/toolchain/compiler.md](docs/toolchain/compiler.md): compiler and
  backend behavior.
- [docs/toolchain/agent-workflows.md](docs/toolchain/agent-workflows.md):
  agent-facing command loop.
- [docs/toolchain/vscode-extension.md](docs/toolchain/vscode-extension.md):
  editor extension behavior.
- [docs/reference/compatibility.md](docs/reference/compatibility.md): public
  compatibility boundary.
- [docs/reference/roadmap.md](docs/reference/roadmap.md): pre-release roadmap
  and public status.
- [docs/reference/release-hygiene.md](docs/reference/release-hygiene.md):
  release repository-state and package metadata policy.

## Release And Extension Status

The repository is pre-release. The GitHub release workflow validates release
candidates, packages the local VS Code extension, and can attach release
artifacts for a matching `v*` tag.

The VS Code extension currently uses `publisher: semanticscript-local` for
local VSIX packaging. Choose a real Marketplace publisher before public
Marketplace distribution.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

- Keep changes scoped.
- Include validation commands in PRs.
- Do not commit generated binaries, `.vsix` files, caches, local databases, or
  build folders.
- Keep docs synchronized with compiler, linter, runtime, and editor behavior.

## Security

Do not report vulnerabilities in public issues. See
[SECURITY.md](SECURITY.md) for private reporting instructions.

## License

SemanticScript is distributed under the [MIT License](LICENSE). Third-party code
under `third_party/` keeps its upstream license terms.
