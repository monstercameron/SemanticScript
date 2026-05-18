# Release Process

This file defines the repeatable validation path for SemanticScript release
candidates. Repository-state and artifact policies live in
`docs/reference/release-hygiene.md`.

## Release Blockers

- Confirm the root `LICENSE` remains MIT and package metadata that declares a
  license also uses `MIT`.
- Confirm the VS Code publisher target. `semanticscript-local` is valid only for
  local VSIX packaging.
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
python -m unittest SemanticScript/linter/test_semlint.py -v
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sscript --parse-only
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sem --parse-only
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sscript --summary
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sem --summary
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

Package the VS Code extension only after validation passes and the release owner
accepts the current extension metadata:

```powershell
npm --prefix vscode-semanticscript run check
Push-Location vscode-semanticscript
npx --yes @vscode/vsce package
Pop-Location
```

Do not commit the generated `.vsix` unless the project later decides to track
release artifacts.

## Repository Policy Checks

Before tagging, confirm the release hygiene policies:

- `samples/python/` is the canonical Python comparison-sample tree.
- top-level `python/` remains a 1.0 compatibility mirror and must stay aligned
  when mirrored files change.
- `.sem` files directly under `SemanticScript/sem/` are intentionally tracked
  alias fixtures, not generated outputs.
- `vscode-semanticscript/package.json` version matches the release tag.
- `vscode-semanticscript/package.json` license remains `MIT`.
- `vscode-semanticscript/package.json` publisher is changed away from
  `semanticscript-local` before any Marketplace publish.

Run the alias mirror check when `.sscript` / `.sem` examples change:

```powershell
python SemanticScript/tests/sem_alias_parity.py
```

## Release Checklist

1. Confirm `git status --short` contains only intentional release changes.
2. Install Python dependencies from `requirements.txt`.
3. Run focused CI parity commands.
4. Run full release validation commands when compiler, stdlib, bootstrap,
   extension, or sample behavior changed.
5. Confirm docs and command examples use current SemanticScript names.
6. Confirm package outputs are ignored or attached outside the repository.
7. Record skipped checks and the reason in the release notes.
8. Confirm `docs/reference/release-hygiene.md` still matches the release
   decision.
