# Package And Registry Policy

This page defines the package layout and dependency policy until first-class
package resolution is implemented in `sem`.

## Package Layout

A package is a `build.sem` project with one canonical module path. The default
layout is:

```text
package-root/
  build.sem
  main.sem
  docs/
  runtime/
  module-a/
    main.sem
    main.test.sem
  module-b/
    main.sem
    main.test.sem
```

Package roots should use these build-tape rows consistently:

| Concern | Canonical location |
| --- | --- |
| Source root | `sourceRoot PROJECT "."` unless a package has a deliberate subdirectory source tree. |
| Test root | colocated `*.test.sem` files selected by `testPattern PROJECT "*.test.sem"`. |
| Generated output | ignored `build/` and `.semcache/` folders, never production source folders. |
| Documentation output | `docsOutput PROJECT "docs"` when generated docs are enabled. |
| Native runtime configuration | explicit build-tape/runtime rows plus adapter-owned files under `SemanticScript/runtime/` or a package-local `runtime/` folder. |

## Dependency Syntax

Dependency requests belong in `build.sem`, not in TOML, JSON, YAML, or ad hoc
sidecar files.

Local development dependencies use the dependency alias plus a local source row:

```semanticscript
dependency demo localLib github.com/example/local-lib local
dependencySource demo localLib local "../local-lib"
```

Git dependencies use a pinned ref. Commits are preferred for release builds;
tags are acceptable when the lock tape resolves them to immutable commits:

```semanticscript
dependency demo semstd github.com/example/semstd v1.0.0
dependencyFetch demo semstd github example/semstd v1.0.0
dependencyIntegrity demo semstd commit:abcdef1234567890
```

Versioned registry dependencies are reserved until local and Git dependency
workflows are stable. Feature flags are also reserved; a future design should
keep them in SemanticScript build or lock rows rather than introducing another
manifest format.

## Build-Time Fetch Boundary

`dependencyFetch` is the build-time dependency API. It prepares source trees for
module import resolution before compiler codegen starts; it is not a runtime
network API.

The future dependency update command shape is:

```text
sem get MODULE_PATH@VERSION_OR_REF
```

`sem get` belongs to the `sem` tool driver layer. It may read and update
`build.sem`, `.semcache/`, and `sem.lock`, but it must not become a compiler
backend phase. Direct `semsc build.sem` invocation remains validation and
compile-only behavior: it can report dependency rows and use already resolved
source roots, but it must not perform network fetches.

`sem build` dependency preparation order is:

1. Parse the active `build.sem`.
2. Resolve local path dependencies.
3. Resolve remote dependencies through the cache and lock tape.
4. Fetch only when allowed by the selected mode.
5. Load dependency build tapes and exported contracts.
6. Invoke `semsc` with the resolved source roots.

Agent-readable fetch logs should use stable JSON fields:

```json
{
  "alias": "semstd",
  "modulePath": "github.com/example/semstd",
  "requestedRef": "v1.0.0",
  "resolvedCommit": "abcdef1234567890",
  "cachePath": ".semcache/extracted/github/example/semstd/abcdef1234567890",
  "lockPath": "sem.lock",
  "failureReason": ""
}
```

These logs are diagnostics and automation data; they are not part of the lock
format.

Runtime outbound HTTP should use a separate future surface such as
`http.clientRequest`, `http.clientResponseText`, or `net.fetchText`. Those names
must not collide with server-side `http.request*` and `http.response*` APIs.
Future runtime fetch wrappers must export visible effects, such as
`network.http.client read` or `network.http.client write`, the same way imported
dependency operations expose their effects to callers.

The runtime-fetch MVP is compiled-program behavior that lowers to native runtime
calls and works without Python tooling at program execution time. Its first
scope should be blocking HTTP/1.1 plus HTTPS. HTTP/2 client support is deferred
until TLS, ALPN, and backend-library choices are settled.

## GitHub Fetching

GitHub is the first remote fetch kind, but the grammar stays generic:
`dependencyFetch PROJECT ALIAS KIND ...` carries the fetch kind separately from
the dependency request. `github` and `http` are reserved now; a future `git`
fetch kind can support generic Git URLs without changing the core dependency
row.

For `dependencyFetch PROJECT ALIAS github OWNER/REPO REF`, the resolver first
classifies `REF`:

| Ref shape | Classification | Resolution |
| --- | --- | --- |
| `commit:<sha>` or a full SHA | immutable commit pin | Use the commit directly. |
| version tag such as `v1.2.3` | mutable tag until locked | Resolve through GitHub metadata, then lock the commit. |
| branch such as `main` | mutable branch | Development-only unless explicitly allowed. |
| local source row | local path | No network access. |

Tags and branches resolve to an exact commit before download. For branches, use
GitHub's refs endpoint for `heads/<branch>`. For tags, use `tags/<tag>` and
dereference annotated tag objects to the target commit. Commit pins skip mutable
ref resolution.

The deterministic archive URL is built from the resolved commit:

```text
https://codeload.github.com/OWNER/REPO/tar.gz/RESOLVED_COMMIT
```

The lock tape records both this URL and the archive SHA-256 because generated
archive bytes must still be verified before extraction.

Fetching uses anonymous HTTPS first. Optional token authentication may be added
later through environment or credential-helper configuration, but tokens must
never be stored in `build.sem`, `.semcache/` metadata, `sem.lock`, or fetch
logs. A reserved development-only escape hatch for intentionally floating refs
is:

```semanticscript
dependencyFloatingRef PROJECT ALIAS devOnly yes
```

Release and locked modes should reject branch refs unless a future policy gives
an explicit, auditable exception.

## Dependency Cache

`.semcache/` beside `build.sem` is the default project-local dependency and
build cache. It is ignored by Git and should not be placed under a production
source root.

Reserved cache layout:

```text
.semcache/
  archives/
  extracted/
  tmp/
  metadata/
  locks/
```

Rules for future dependency resolution:

- archive filenames are content-addressed so mutable refs cannot collide;
- GitHub extracted trees include the resolved commit in the path;
- local path dependencies remain external references during normal development
  builds instead of copied cache entries;
- cached dependency sources are read-only to normal builds;
- downloads and extraction write to `tmp/` first, then move atomically;
- concurrent builds coordinate through lock files under `.semcache/locks/`;
- cached archives and extracted trees are rehashed before reuse;
- corrupt cache entries are quarantined and diagnostics should include a repair
  command;
- a user-global cache can be added later, but project-local cache remains the
  reproducible default.

## Lock Tape

Lock data lives in `sem.lock`, a SemanticScript tape file sorted
deterministically by dependency alias and module path.

Reserved lock rows:

```semanticscript
lockProject PROJECT
lockFormatVersion PROJECT "1"
lockGeneratedBy PROJECT "sem 0.1.0"
lockGeneratedAt PROJECT "2026-05-20T00:00:00Z"
lockedDependency PROJECT ALIAS MODULE_PATH REQUESTED_REF
lockedDependencyCommit PROJECT ALIAS COMMIT
lockedDependencyFetch PROJECT ALIAS KIND SOURCE_URL
lockedDependencyArchive PROJECT ALIAS ARCHIVE_URL
lockedDependencyArchiveChecksum PROJECT ALIAS SHA256
lockedDependencyTreeDigest PROJECT ALIAS SHA256
lockedDependencyRoot PROJECT ALIAS "PATH"
lockedDependencyBuildTape PROJECT ALIAS "build.sem"
lockedDependencyLanguageVersion PROJECT ALIAS "1"
lockedDependencyBuildModulePath PROJECT ALIAS MODULE_PATH
lockedDependencyTransitive PROJECT ALIAS CHILD_ALIAS
```

Normal builds should use locked versions without hitting the network. A future
locked mode should fail when `sem.lock` is missing or stale; update mode may
rewrite it. Remote bytes, resolved commits, archive checksums, and extracted
tree digests must agree with the lock tape before dependency source enters
import resolution.

`lockGeneratedAt` is optional non-semantic metadata. Readers must ignore it for
resolution, and reproducible writers may omit it so regenerating the same lock
does not create timestamp-only diffs.

## Registry Deferral

Do not build a public registry until local path dependencies, Git dependencies,
cache layout, and lock tapes are stable.

Registry requirements before implementation:

- immutable package versions;
- checksums for every downloadable artifact;
- clear module-path ownership rules;
- namespace transfer and abandonment policy;
- support for private/internal registries before assuming one public host.

Package signing is deferred. Checksums are mandatory before signing: every
registry artifact must have a stable digest in the lock tape or release
manifest. A future signing design can layer signatures over those same
artifacts.

Ownership rules should follow module paths. A package owner controls a module
path prefix, and packages must not publish modules outside their owned prefix.
