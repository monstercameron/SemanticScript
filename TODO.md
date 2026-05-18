# SemanticScript Migration Status

The repo-wide SemanticScript migration has been applied.

Completed scope:

- Language, documentation, and editor-facing names now use `SemanticScript`.
- Source files use `.sscript`, with `.sem` accepted as an alias by the toolchain.
- The compiler entry point is `semsc`.
- The linter entry points are `semlint` and `semlint2`.
- Implementation sources live under `SemanticScript/`.
- Example sources live under `SemanticScript/sem/`.
- Standard library sources live under `SemanticScript/stdlib_sem/`.
- The VS Code extension lives under `vscode-semanticscript/`.
- The internal source-model wording uses `semantic tape`.

Remaining routine work:

- Keep new docs and examples aligned with these names.
- Keep generated build outputs out of source control.
- Regenerate packaged editor artifacts only from the renamed extension.
- Continue using the legacy-string scans in CI or release prep before publishing.
