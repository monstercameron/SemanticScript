# Release Process

This file defines the repeatable validation path for SemanticScript release
candidates. It does not choose a legal license.

## Release Blockers

- TODO: choose and document the project license before publishing public release
  artifacts.
- CI must pass on the release commit.
- Generated files must not be committed unless they are intentionally tracked
  source artifacts.
- No public command, source extension, or documentation should refer to removed
  legacy tool names.

## Environment

Minimum release validation environment:

- Python 3.11 or 3.12
- dependencies from `requirements.txt`
- Node.js 20 or newer for VS Code extension syntax checks
- LLVM/clang for native emit, stdlib, bootstrap, and parity checks

On Windows, set `SEMSC_CLANG` when clang is not on PATH:

```powershell
$env:SEMSC_CLANG = "C:\Program Files\LLVM\bin\clang.exe"
```

## Focused CI Parity

These commands mirror the lightweight CI workflow:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m compileall -q SemanticScript python samples
python -m unittest SemanticScript/linter/test_semlint2.py -v
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sscript --parse-only
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sem --parse-only
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sscript --fail-on none --summary
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sem --fail-on none --summary
npm --prefix vscode-semanticscript run check
```

## Full Release Validation

Run the focused commands first, then run the broader checks:

```powershell
python SemanticScript/tests/test_compiler.py
python SemanticScript/tests/test_stdlib.py
python SemanticScript/tests/compare.py
python SemanticScript/tests/sem_alias_parity.py
python SemanticScript/tests/sem_compiler_parity.py
python SemanticScript/tests/feature_coverage.py
python SemanticScript/bootstrap/run_bootstrap_chain.py
```

Package the VS Code extension only after validation passes and the license TODO
is resolved:

```powershell
npm --prefix vscode-semanticscript run check
Push-Location vscode-semanticscript
npx --yes @vscode/vsce package
Pop-Location
```

Do not commit the generated `.vsix` unless the project later decides to track
release artifacts.

## Release Checklist

1. Confirm `git status --short` contains only intentional release changes.
2. Install Python dependencies from `requirements.txt`.
3. Run focused CI parity commands.
4. Run full release validation commands when compiler, stdlib, bootstrap,
   extension, or sample behavior changed.
5. Confirm docs and command examples use current SemanticScript names.
6. Confirm package outputs are ignored or attached outside the repository.
7. Record skipped checks and the reason in the release notes.
