# 1.0 Compatibility Contract

This page defines the public SemanticScript 1.0 compatibility boundary for the
Python reference compiler and first-party tooling.

## Language Version

`languageVersion PROJECT "1.0"` declares that a `build.sem` project expects the
1.0 source and build-tape contract. It does not automatically enable
`languageMode strictExecutable`; strict mode remains an explicit opt-in.

Future compiler versions should warn before rejecting source that is valid under
the documented 1.0 contract, except for security fixes or cases where the source
already relied on `Partial`, `Proposed`, or metadata-only syntax.

## Stable Surface

Rows marked `Impl'd` in `SYNTAX.md` are the stable 1.0 executable surface for
the Python reference compiler unless a row explicitly scopes support to tooling
or metadata. This includes core project, operation, storage, call, argument,
branch, return, effect, capability, record, enum, error, build-tape, module,
import, export, native executable, native HTTP, SQLite, HTML, and implemented
JSON document/primitive APIs.

`build.sem` compatibility covers the documented project schema, strict
diagnostics for malformed rows, source-root and module registration behavior,
compiler-managed build folders, and CLI overrides described in
`docs/language/project-layout-build-sem.md`.

Module/import/export compatibility covers explicit `registerModule`,
`importModule`, singular import rows, and export rows documented for 1.0.
Imported private symbols remain private unless explicitly exported.

Native HTTP compatibility covers the documented first-party native HTTP call
targets and route metadata. Backend replacement work, including an H2O-backed
runtime, is outside the 1.0 guarantee until it is marked implemented.

SQLite compatibility covers native `sqlite.*` lowering, `SqlText`/`sql body`
source islands, and the resource-lifetime checks for database and statement
handles. Query schema and migration policy remain application source.

JSON compatibility covers implemented `JsonDocument` lifecycle, cursor,
navigation, mutation, serialization, and primitive `json.stringify.<TypeName>` /
`json.parse.<TypeName>` aliases. Record JSON codecs and record-typed `jsonBody`
lowering remain partial.

VS Code extension compatibility covers language registration, syntax
highlighting, semantic tokens, hovers, same-file navigation, lint integration,
and documented configuration keys in `vscode-semanticscript/package.json`.
Highlighting a proposed row does not make that row an executable compiler
guarantee.

## Source Extensions

`.sscript` is the canonical source extension. `.sem` is a supported 1.0 alias
for source and build tapes. Both extensions are parsed by the reference compiler
and tooling; `.sem` mirrors under `SemanticScript/sem/` are tracked fixtures, not
generated outputs.

## Preview And Partial Surface

Rows marked `Partial`, `Not impl'd`, or `Proposed` in `SYNTAX.md` are not stable
1.0 executable guarantees. They may be parser-only, linter-only, metadata-only,
or design targets for future compiler/runtime work.

Package fetching, language server, documentation generator, test runner,
installer/version manager, full registry workflow, record JSON codecs, and
declarative GUI top-level rows are preview or future work unless a narrower row
in `SYNTAX.md` says otherwise.

## Deprecation

Changing stable 1.0 syntax requires a documented deprecation path:

- document the replacement in `SYNTAX.md` and the owning language/toolchain doc;
- emit a warning before rejecting old valid 1.0 source when practical;
- keep compatibility examples or migration notes until the old form is removed;
- make security- or correctness-driven exceptions explicit in release notes.
