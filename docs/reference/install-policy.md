# Install And Version Policy

SemanticScript installation is intentionally conservative until the compiler,
tool driver, and release artifacts are stable.

## Install Strategy

The current pre-release user install path is the GitHub Releases page:

<https://github.com/monstercameron/SemanticScript/releases>

Main-branch prereleases are tagged `main-<SHORT_SHA>` and attach:

- `semanticscript-sem-windows-x64-main-<SHORT_SHA>.exe`, the standalone Windows
  `sem` CLI;
- `semanticscript-vscode-main-<SHORT_SHA>.vsix`, the local VS Code extension;
- `semanticscript-merge-release-manifest-main-<SHORT_SHA>.json`, the generated
  checksum and metadata manifest.

The source-checkout Python command remains a contributor workflow, not the
primary user install path.

The first stable public install shape may still become a single versioned
release archive containing:

- `SemanticScript/` Python tools, stdlib, and runtime sources;
- `requirements.txt`;
- docs and release manifest;
- optional VS Code VSIX attached outside Git.

A Python package wrapper may be added later to expose console entry points such
as `sem`, but it should wrap the same release archive layout rather than invent
a second package format. Native launchers and platform package managers are
deferred until the Python toolchain contract and artifact manifest are stable.

Native executable builds require a host LLVM/clang installation. See
[docs/toolchain/llvm-compiler-install.md](../toolchain/llvm-compiler-install.md).

## Version Manager Plan

A future `semup` or equivalent version manager should:

- install a named SemanticScript version from a release manifest;
- update to the latest stable version only after validating checksums;
- select an active version per user;
- select an active version per project when a project pins one;
- print installed versions and the active selection source.

The version manager should not be required for source checkout development.
Running `python SemanticScript/tools/sem.py ...` from a checkout remains the
source checkout workflow.

## Artifact Checks

Every release archive and VSIX attached outside Git should have a checksum
recorded in `releases/<TAG>/manifest.json`. Signatures are deferred until the
release process has stable artifact names, checksum generation, and ownership
for signing keys.
