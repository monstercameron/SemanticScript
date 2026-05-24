# Install And Version Policy

SemanticScript installation is intentionally conservative until the compiler,
tool driver, and release artifacts are stable.

## Install Strategy

The first supported public install shape should be a single versioned release
archive containing:

- `SemanticScript/` Python tools, stdlib, and runtime sources;
- `requirements.txt`;
- docs and release manifest;
- optional VS Code VSIX attached outside Git.

A Python package wrapper may be added later to expose console entry points such
as `sem`, but it should wrap the same release archive layout rather than invent
a second package format. Native launchers and platform package managers are
deferred until the Python toolchain contract and artifact manifest are stable.

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
