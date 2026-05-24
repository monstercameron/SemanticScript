# Contributing

SemanticScript is in an active migration and tooling-hardening phase. Keep
changes scoped, preserve unrelated working-tree edits, and prefer commands that
work from PowerShell on Windows as well as POSIX shells.

## Setup

From the repository root, create an isolated Python environment and install the
project dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt -c constraints.txt
```

Use the environment's Python explicitly in commands, or activate it first. On
POSIX shells, use `. .venv/bin/activate` or call `.venv/bin/python` directly.

Confirm the agent-facing wrapper is available:

```powershell
.\.venv\Scripts\python SemanticScript\tools\sem.py --version --json
.\.venv\Scripts\python SemanticScript\tools\sem.py check --json SemanticScript\tests\agent_cli_demo.test.sem
```

The VS Code extension check uses Node.js. Install Node 20 or newer when working
on `vscode-semanticscript/`.

Install `pre-commit` separately if you want local hygiene hooks. The repo keeps
the hook config optional so normal compiler/runtime installs stay small.

## Focused Validation

Run a focused check for narrow documentation-only changes:

```powershell
.\.venv\Scripts\python SemanticScript\tools\sem.py --version --json
```

Run the fast suite before sending a narrow tooling or SemanticScript source
change:

```powershell
.\.venv\Scripts\python SemanticScript\tests\run_suite.py ci-fast
```

Use broader checks when changing compiler lowering, stdlib behavior, sample
programs, or source-file extension handling:

```powershell
.\.venv\Scripts\python SemanticScript\tests\run_suite.py ci-release
```

List all unit, component, integration, and e2e lanes with:

```powershell
.\.venv\Scripts\python SemanticScript\tests\run_suite.py --list
```

Some broader checks require Node.js, LLVM/clang, and a working native compiler
toolchain. Set `SEMSC_CLANG` if clang is not discoverable on PATH.

## Pull Request Notes

- Include the commands you ran and any skipped checks.
- Do not commit generated outputs such as `.exe`, `.ll`, `.pyc`, build folders,
  packaged `.vsix` files, or `__pycache__/`.
- Do not introduce public `.as` source-extension support.
- Do not change the project license without a release-owner decision.

## License

SemanticScript is distributed under the MIT License. See the root `LICENSE` file
for the full license text. Third-party code under `third_party/` keeps its own
upstream license terms.
