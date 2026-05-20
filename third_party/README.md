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
- Current pinned commit:
  `9e7f283e5801bd0707cc5d48d0188c4c162fe7b3`.

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

## crypt_blowfish (vendored bcrypt)

- Path: `third_party/bcrypt`
- Upstream: https://www.openwall.com/crypt/
- Purpose: bcrypt password hashing for the `SemanticScript/runtime/native_bcrypt/`
  adapter (used by the `app/todo-web-pro` web app for user passwords + session-token
  salt + base64url helpers).
- License: public domain (with fallback permissive terms — see
  [`bcrypt/README.AgentScript.md`](bcrypt/README.AgentScript.md)).
- Pinned version: **crypt_blowfish 1.3** (Solar Designer / Openwall).
- Compatibility: produces / validates `$2b$NN$…` hashes per the OpenBSD bcrypt
  convention.

Vendored because the source is ~40 KB of pure C with no transitive dependencies;
a submodule would add no value and slow down fresh clones.

## Release review summary

Review this table before tagging a release that packages source or binaries
including `third_party/`.

| Path | Upstream project | Upstream URL | Pin | License |
| --- | --- | --- | --- | --- |
| `third_party/h2o` | H2O | `https://github.com/h2o/h2o.git` | Git submodule commit `9e7f283e5801bd0707cc5d48d0188c4c162fe7b3` | MIT, with bundled dependency notices under the H2O tree |
| `third_party/sqlite` | SQLite amalgamation | `https://sqlite.org/` | SQLite `3.53.1`, `SQLITE_SOURCE_ID` `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` | Public domain |
| `third_party/bcrypt` | crypt_blowfish | `https://www.openwall.com/crypt/` | crypt_blowfish `1.3` | Public domain with fallback permissive terms |

Source archives that include `third_party/` must preserve each upstream license
or notice file already present in the vendored tree. Binary releases that link
against vendored code must carry the same review result in the release notes or
release manifest. Source-only releases do not need an additional root `NOTICE`
file or machine-readable SBOM for the current dependency set; binary releases
should reconsider those decisions if the dependency set or distribution model
changes.
