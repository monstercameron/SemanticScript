# Syntaxes

TextMate grammar assets for the SemanticScript VS Code extension.

## Contents

- `semanticscript.tm-language.json` defines syntax highlighting scopes.
  It includes embedded HTML/SSX, JSON, and SQL islands so first-class
  templates and structured text literals do not inherit normal tape tokenization.
  It also recognizes Windows GUI `gui.*` runtime targets used through normal
  `call` rows.

## Current Status

Active editor grammar surface. It should track the executable and refined syntax
that users are expected to read/write in VS Code.

## Maintenance

When syntax changes, update this grammar together with the docs and linter so
highlighting, validation, and references stay aligned.
