# Syntaxes

TextMate grammar assets for the SemanticScript VS Code extension.

## Contents

- `semanticscript.tmLanguage.json` defines syntax highlighting scopes.
  It includes a small HTML/SSX island for `htmlBody` blocks so first-class
  templates do not inherit normal tape tokenization.
  It also recognizes Windows GUI `gui.*` runtime targets used through normal
  `call` rows.

## Current Status

Active editor grammar surface. It should track the executable and refined syntax
that users are expected to read/write in VS Code.

## Maintenance

When syntax changes, update this grammar together with the docs and linter so
highlighting, validation, and references stay aligned.
