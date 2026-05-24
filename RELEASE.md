# Release Process

This file defines the repeatable validation path for SemanticScript release
candidates. Repository-state and artifact policies live in
`docs/reference/release-hygiene.md`. The public 1.0 compatibility contract
lives in `docs/reference/compatibility.md`.

## Current Status

SemanticScript is currently `0.0.1` pre-release software. No stable public
release has been published yet. Treat this file as the release-candidate
playbook until the first tagged release is created.

## Release Blockers

- Confirm the root `LICENSE` remains MIT and package metadata that declares a
  license also uses `MIT`.
- Confirm the VS Code publisher target. The initial release is local VSIX only;
  `semanticscript-local` is valid only for local VSIX packaging.
- CI must pass on the release commit.
- Generated files must not be committed unless they are intentionally tracked
  source artifacts.
- No public command, source extension, or documentation should refer to removed
  legacy tool names.

## Version Policy

SemanticScript uses a repository-wide semantic version from `version.json`.
`semsc`, `semlint`, `semfmt`, `sem`, and the VS Code extension are expected to
stay synchronized to that shared version. The release version check prints the
matrix and fails when the package metadata drifts from `version.json`.

| Component | Version | Source |
| --- | --- | --- |
| `semsc` | `0.0.1` | `version.json` |
| `semlint` | `0.0.1` | `version.json` |
| `semfmt` | `0.0.1` | `version.json` |
| `sem` | `0.0.1` | `version.json` |
| `semanticscript-vscode` | `0.0.1` | `version.json` -> `vscode-semanticscript/package.json` |

```powershell
python SemanticScript\tools\release_versions.py
python SemanticScript\tools\release_versions.py --json
python SemanticScript\tools\bump_version.py --check
```

## Release Manifest

Each public release should have a manifest at
`releases/<TAG>/manifest.json`. Commit the manifest with release notes and attach
the same JSON to the GitHub release when publishing externally. The manifest
should record the release tag, commit SHA, release date, tool versions,
validation environments, exact commands, skipped checks, generated artifacts,
checksums, signature status, deferred features, and known limitations.

The GitHub release workflow at `.github/workflows/release.yml` performs the
Windows release validation path, builds the single-file `sem` executable,
packages the VS Code extension, generates the same manifest shape as a release
artifact, and creates or updates the GitHub release for `v*` tags. Manual
dispatches require an explicit existing tag that matches `version.json`; keep
this manual policy section and the workflow in sync when release commands or
artifact rules change.

## Environment

Minimum release validation environment:

- Python 3.11 or 3.12
- dependencies from `requirements.txt`; use `constraints.txt` when you need the
  same pinned dependency floor as CI/release validation
- PyInstaller 6.20.0 for the single-file Windows executable
- Node.js 20 or newer for VS Code extension syntax checks
- LLVM/clang for native emit, stdlib, and parity checks

On Windows, set `SEMSC_CLANG` when clang is not on PATH:

```powershell
$env:SEMSC_CLANG = "C:\Program Files\LLVM\bin\clang.exe"
```

## Focused CI Parity

These commands mirror the lightweight CI workflow:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m compileall -q SemanticScript apps experiments
python SemanticScript/tools/release_versions.py
python SemanticScript/tools/sem.py --version --json
python SemanticScript/tools/sem.py skills list --json
python SemanticScript/tools/sem.py readiness --json SemanticScript/tests/agent_cli_demo.test.sem
python SemanticScript/tools/sem.py check --json SemanticScript/tests/agent_cli_demo.test.sem
python SemanticScript/tools/sem.py fmt --check SemanticScript/tests/agent_cli_demo.test.sem
python SemanticScript/tools/sem.py test --json SemanticScript/tests/agent_cli_demo.test.sem --skip-python-harnesses
python -m unittest SemanticScript.tests.test_sem_cli -v
python -m unittest SemanticScript.tests.test_command_contracts -v
python -m unittest SemanticScript/formatter/test_semfmt.py -v
python SemanticScript/formatter/semfmt.py --check SemanticScript/tests/tiny.sem
python -m unittest SemanticScript/linter/test_semlint.py -v
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sscript --parse-only
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sem --parse-only
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sscript --summary
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sem --summary
npm --prefix vscode-semanticscript run check
```

## Single-File CLI Artifact

The release workflow builds `dist\sem.exe` with PyInstaller onefile mode and
publishes it as `semanticscript-sem-windows-x64-<TAG>.exe`. The executable
embeds the Python launcher, compiler, formatter, linter, `sem` CLI, bundled
standard library, selected docs, and the runtime/vendor files needed by the
toolchain. Users distribute one `.exe`; no adjacent folder is required.

PyInstaller onefile executables still extract their embedded payload into a
temporary `_MEI...` directory while running, then remove it on normal exit. This
means the executable requires writable temp space, but it does not require a
user-managed install directory.

```powershell
python -m pip install pyinstaller==6.20.0
python -m PyInstaller --noconfirm --clean packaging/pyinstaller/sem.spec
.\dist\sem.exe version --json
.\dist\sem.exe check --json SemanticScript\tests\agent_cli_demo.test.sem
.\dist\sem.exe fmt --check SemanticScript\tests\agent_cli_demo.test.sem
.\dist\sem.exe lint SemanticScript\tests\tiny.sem -- --summary
.\dist\sem.exe emit-ir SemanticScript\tests\agent_cli_demo.test.sem --quiet
.\dist\sem.exe run SemanticScript\tests\agent_cli_demo.test.sem
```

Native AOT compilation still depends on a working platform compiler such as
clang. Set `SEMSC_CLANG` when clang is not discoverable on `PATH`.

## Full Release Validation

Run the focused commands first, then run the broader checks:

```powershell
python SemanticScript/tests/test_compiler.py
python SemanticScript/tests/test_stdlib.py
python SemanticScript/tests/compare.py
python SemanticScript/tests/sem_alias_parity.py
```

Package the VS Code extension for local VSIX distribution only after validation
passes and the release owner accepts the current extension metadata:

```powershell
npm --prefix vscode-semanticscript run check
Push-Location vscode-semanticscript
npx --yes @vscode/vsce package
Pop-Location
```

Do not commit the generated `.vsix` unless the project later decides to track
release artifacts.

Do not commit generated `.exe` artifacts. The release workflow attaches the
single-file executable and records its SHA-256 checksum in the release manifest.

The PyInstaller entry point and spec live under `packaging/pyinstaller/`.
Do not reintroduce a top-level `python/` packaging folder.

## Repository Policy Checks

Before tagging, confirm the release hygiene policies:

- `.sem` files directly under `SemanticScript/sem/` are intentionally tracked
  alias fixtures, not generated outputs.
- `python SemanticScript/tools/release_versions.py` prints the component matrix
  expected for the release notes.
- `third_party/README.md` records the vendored dependency inventory, pins,
  licenses, and packaging notice policy for artifacts that include third-party
  code.
- `vscode-semanticscript/package.json` license remains `MIT`.
- `vscode-semanticscript/package.json` publisher remains `semanticscript-local`
  for local VSIX releases only. Change it away from `semanticscript-local`
  before any Marketplace publish.

Run the alias mirror check when `.sscript` / `.sem` examples change:

```powershell
python SemanticScript/tests/sem_alias_parity.py
```

Scan history non-destructively for generated artifacts that should not appear in
public release history:

```powershell
$artifactHistory = git log --all --name-only --pretty=format: -- `
  "*.exe" "*.ll" "*.bc" "*.obj" "*.o" "*.pdb" "*.res" "*.rc" "*.vsix" `
  "apps/taskforge-tui/todos.json"
if ($artifactHistory) {
  $artifactHistory | Sort-Object -Unique
  throw "Generated artifacts were found in Git history."
}
```

The local all-branches scan on 2026-05-19 returned no generated-artifact paths,
so no history rewrite is required for the current release state. If a future
scan finds disallowed artifacts, prefer `git filter-repo` or another repeatable
non-interactive history rewrite tool and record the exact command before
tagging.

## Manual Validation

The CI workflow intentionally leaves some checks manual because they require
local native toolchains, long-running app processes, or release-owner approval:

- app webserver harnesses such as
  `apps/http-runtime-gauntlet/scripts/test_http_runtime_gauntlet.py` and
  `apps/taskforge-web/scripts/test_taskforge_web.py`;
- native runtime CMake builds when a runner lacks the required compiler,
  pthreads, SQLite, or JSON runtime dependency shape;
- VSIX packaging with `npm --prefix vscode-semanticscript run package:vsix`.
- local smoke validation of the generated
  `semanticscript-sem-windows-x64-<TAG>.exe` on a machine without a checked-out
  source tree, before publishing a public release.

## Release Checklist

1. Confirm `git status --short` contains only intentional release changes.
2. Install Python dependencies from `requirements.txt` with `constraints.txt`
   for repeatable validation.
3. Run focused CI parity commands.
4. Run full release validation commands when compiler, stdlib, extension, or
   sample behavior changed.
5. Confirm docs and command examples use current SemanticScript names.
6. Confirm package outputs are ignored or attached outside the repository.
7. Confirm formatter output is clean with `python
   SemanticScript/formatter/semfmt.py --check SemanticScript/tests/tiny.sem`.
8. Record skipped checks and the reason in the release notes.
9. Confirm `docs/reference/release-hygiene.md` still matches the release
   decision.
10. Confirm CI is green on the exact commit being tagged.
11. Confirm any release artifact that includes `third_party/` has a recorded
    third-party license/SBOM review.
12. Confirm `releases/<TAG>/manifest.json` exists before tagging a public
    release.
