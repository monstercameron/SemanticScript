# Release Hygiene Policy

Release hygiene covers repository state, generated artifacts, local package
metadata, and intentionally duplicated fixtures. It does not choose an
open-source license or a public marketplace identity.

## License Posture

The root `LICENSE` file is a no-license notice for the 1.0 release candidate.
It reserves rights and does not grant open-source reuse permission.

Public publishing is blocked until the release owner either:

- accepts private/source-available distribution under the current no-license
  notice; or
- replaces `LICENSE` and all package metadata with the chosen license.

The VS Code extension keeps `"license": "UNLICENSED"` while the root notice is
in force.

## VS Code Extension Metadata

`vscode-semanticscript/package.json` uses version `1.0.0` for the SemanticScript
1.0 local VSIX build.

The publisher remains `semanticscript-local`. That value is for local packaging
and development-host installs only. Do not publish to the VS Code Marketplace
until a real publisher account is selected and the `publisher` field is changed.

Generated `.vsix` files are ignored and should be attached outside the repo or
rebuilt from the release tag.

## Python Sample Policy

`samples/python/` is the canonical location for Python comparison samples.

The top-level `python/` directory remains tracked for 1.0 as a compatibility
mirror for existing scripts and docs. When a mirrored sample changes, update both
copies in the same change. New Python comparison samples should be added under
`samples/python/`; add a top-level mirror only when compatibility requires it.

Run both sample aggregators after changing mirrored files:

```powershell
python samples/python/run_all.py
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
- local todo app data such as `app/todo/todos.json`.

Use a dry run before removing ignored local artifacts:

```powershell
git clean -Xdn
```

Only run the destructive cleanup form after reviewing the dry-run list:

```powershell
git clean -Xdf
```
