# Contributing

SemanticScript is pre-release and changes without backwards compatibility. Keep
changes scoped, and prefer commands that work from PowerShell on Windows as well
as POSIX shells.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt pytest
```

On POSIX shells, call `.venv/bin/python` instead.

## Validation

Run the test suite and check the worked examples before sending a change:

```powershell
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python semanticscript\compiler\refined check docs\refined-examples\selfhost
```

A change to a rule follows the notes: record the decision in
`docs/language-refinement.md`, change the shape table or the checker, add a
negative case to `tests/suite/mutations.py` that breaks a passing case and gets
the rule's code, and regenerate the references. A new behavior gets a program
case in `tests/suite/programs` (see `tests/suite/README.md`); after changing
cases, regenerate the coverage map:

```powershell
.\.venv\Scripts\python tests\suite\coverage_map.py --write
```

Then regenerate the grammar references:

```powershell
.\.venv\Scripts\python semanticscript\compiler\refined grammar --output docs\refined-grammar.md
.\.venv\Scripts\python semanticscript\compiler\refined grammar --textmate --output vscode-semanticscript\syntaxes\semanticscript.tm-language.json
```

CI fails if either generated file is out of date. The editor extension check
needs Node.js 20 or newer: `npm run check` in `vscode-semanticscript/`.

## Branch Naming

Branches follow a `type/short-description` structure (Conventional-Branch
style), where `type` mirrors our commit types and `short-description` is
lowercase kebab-case:

```text
type/short-description
```

Allowed types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`,
`build`, `ci`.

The exact rule (the same regex CI enforces):

```text
^(feat|fix|docs|chore|refactor|test|perf|build|ci)/[a-z0-9]+(-[a-z0-9]+)*$
```

Examples:

```text
feat/crash-metadata
fix/null-deref-guard
docs/branch-naming
chore/bump-llvmlite
refactor/codegen-emit
```

Enforcement is two-layered:

- **CI** — `.github/workflows/branch-name.yml` validates the head branch of
  every pull request and fails non-conforming names. Automation branches
  (`dependabot/**`) and the protected `main`/`master`/`release/**` branches are
  exempt.
- **Local (optional)** — install the pre-push hook so a bad name is caught
  before it reaches the remote:

  ```powershell
  git config core.hooksPath .githooks
  ```

  The hook lives at `.githooks/pre-push` and applies the same regex.

## Pull Request Notes

- Include the commands you ran and any skipped checks.
- Do not commit generated outputs such as `.exe`, `.ll`, `.pyc`, build folders,
  packaged `.vsix` files, or `__pycache__/`.
- Do not change the project license without a release-owner decision.
- Follow the project [Code of Conduct](CODE_OF_CONDUCT.md) in issues, pull
  requests, discussions, and other project spaces.

## Review Policy

`main` is protected with strict required checks and resolved conversations. The
approving-review count is intentionally zero in solo-maintainer mode, and
CODEOWNER review, stale-review dismissal, and last-push approval are disabled so
the single maintainer is not blocked waiting for a second account. Release tag
creation for `v*` is restricted to the maintainer, and existing `v*` tags are
protected against update and deletion unless the tag ruleset is deliberately
changed for recovery.

## License

SemanticScript is distributed under the MIT License. See the root `LICENSE` file
for the full license text.
