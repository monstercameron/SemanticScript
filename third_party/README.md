# Third-Party Dependencies

This folder contains externally maintained source trees. Each dependency is
pinned in one of two ways:

- **Submodule** — git submodule pointing at an upstream repository. Required
  for projects with their own build system or vendored dependencies (H2O).
- **Vendored amalgamation** — source files committed directly into this
  tree. Appropriate for projects that publish a self-contained single-file
  distribution and would otherwise need a recursive submodule fetch (SQLite).

Do not edit files inside any third-party tree directly. Put SemanticScript-
specific adapter code in the owning source tree under
`SemanticScript/runtime/<name>/`, then link against the pinned upstream build.

## H2O (submodule)

- Path: `third_party/h2o`
- Upstream: https://github.com/h2o/h2o.git
- Purpose: native HTTP/1.x and HTTP/2 runtime candidate for SemanticScript
  `webServer` / `route` support.
- License: MIT, with TLS dependencies carrying their own licenses.
- Current pinned commit: see `git submodule status third_party/h2o`.

Clone/update with nested upstream dependencies:

```powershell
git submodule update --init --recursive third_party/h2o
```

## SQLite (vendored amalgamation)

- Path: `third_party/sqlite`
- Upstream: https://sqlite.org/ (single-file amalgamation distribution)
- Purpose: embedded SQL storage backing the SemanticScript `sqlite` runtime
  adapter at `SemanticScript/runtime/native_sqlite/`.
- License: public domain.
- Current pinned version and `SQLITE_SOURCE_ID`: see
  [`sqlite/README.md`](sqlite/README.md).

Vendored rather than submoduled because the amalgamation is a single ~9 MB
unpacked drop with no transitive deps, and we want `git clone` of AgentScript
to be usable without `git submodule update`.
