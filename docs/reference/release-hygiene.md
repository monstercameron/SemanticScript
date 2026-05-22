# Release Hygiene Policy

Release hygiene covers repository state, generated artifacts, local package
metadata, component versions, and intentionally duplicated fixtures. It records
the chosen project license but does not choose a public marketplace identity.

## License Posture

The root `LICENSE` file grants the MIT License for first-party SemanticScript
source, documentation, samples, and tooling.

Third-party code under `third_party/` keeps its upstream license terms. Preserve
those notices when packaging or redistributing artifacts that include
third-party code.

The current dependency inventory and packaging notice policy are recorded in
`third_party/README.md`. Source archives that include `third_party/` must keep
the upstream license and notice files already present in those trees. Binary
releases that link vendored code must record the third-party review result in
release notes or `releases/<TAG>/manifest.json`. The current source-only policy
does not add a root `NOTICE` file or machine-readable SBOM.

Package metadata that declares a license must use `MIT` unless a release owner
explicitly chooses a different license for that package.

## Version Policy

SemanticScript uses component-local versions for the initial public release.
Release checks record the component matrix instead of requiring all tools to
share one product version. A version mismatch is acceptable when it is
documented in the matrix; a missing or unreadable version blocks release.

| Component | Version | Source |
| --- | --- | --- |
| `semsc` | `1.0.0` | `SemanticScript/compiler/semsc.py` |
| `semlint` | `0.3.0` | `SemanticScript/linter/semlint.py` |
| `semfmt` | `0.1.0` | `SemanticScript/formatter/semfmt.py` |
| `sem` | `0.1.0` | `SemanticScript/tools/sem.py` |
| `semanticscript-vscode` | `1.0.5` | `vscode-semanticscript/package.json` |

Print the matrix before tagging:

```powershell
python SemanticScript\tools\release_versions.py
```

## Release Manifests

Public release manifests live at `releases/<TAG>/manifest.json`. They should be
committed with the release notes and attached to external release artifacts when
publishing outside the repository.

## VS Code Extension Metadata

`vscode-semanticscript/package.json` uses version `1.0.5` for the current
SemanticScript local VSIX build.

The publisher remains `semanticscript-local`. That value is for local packaging
and development-host installs only. Do not publish to the VS Code Marketplace
until a real publisher account is selected and the `publisher` field is changed.

Generated `.vsix` files are ignored and should be attached outside the repo or
rebuilt from the release tag.

## Python Sample Policy

`python/` is the canonical location for Python comparison samples.

Run the sample aggregator after changing comparison programs:

```powershell
python python/run_all.py
```

## `.sem` Mirror Policy

`.sscript` is the canonical SemanticScript source extension. `.sem` is an
accepted alias.

The `.sem` files directly under `SemanticScript/sem/` are intentionally tracked
alias fixtures for 1.0, not generated build outputs. Keep each mirror aligned
with its `.sscript` counterpart, and run the alias parity check after changing
mirrored examples:

```powershell
python SemanticScript/tests/sem_alias_parity.py
```

Do not add `.sem` mirrors inside focused feature-test directories unless the
test specifically validates alias behavior.

## Clean Worktree Rules

Do not tag a release unless `git status --short` contains only intentional
release changes. Generated artifacts must stay ignored and untracked, including:

- `.exe`, `.ll`, `.bc`, object files, and native build folders;
- Python caches and test build directories;
- packaged `.vsix` files;
- local todo app data such as `apps/taskforge-tui/todos.json`.

Use a dry run before removing ignored local artifacts:

```powershell
git clean -Xdn
```

Only run the destructive cleanup form after reviewing the dry-run list:

```powershell
git clean -Xdf
```

## History Artifact Policy

Public release history should not contain generated `.exe`, `.ll`, `.bc`,
`.obj`, `.o`, `.pdb`, `.res`, `.rc`, `.vsix`, native build-folder output, or
local app data such as `apps/taskforge-tui/todos.json`. Use the non-destructive history
scan in `RELEASE.md` before deciding whether a history scrub is needed. If a
scrub is required, prefer `git filter-repo` or another repeatable
non-interactive tool and record the exact command in release notes.
