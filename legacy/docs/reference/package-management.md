# Package And Registry Policy

This page defines the package layout and dependency policy. Local, path, and
Git (`github`/`http`) dependency resolution is **implemented** in `sem deps`;
the registry, signing, and transitive-resolution sections remain reserved
design for future work and are marked as such.

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

Local development dependencies use the dependency alias plus a path source row:

```semanticscript
dependency demo localLib example.com/local-lib v0.0.0
dependencySource demo localLib path "../local-lib"
```

Git dependencies use a pinned ref and a strong integrity row:

```semanticscript
dependency demo semstd github.com/example/semstd v1.0.0
dependencyFetch demo semstd github example/semstd v1.0.0
dependencyIntegrity demo semstd sha256:<64-hex archive digest>
```

`commit:<sha>` integrity is accepted as a ref pin but is advisory only — it
selects a ref and is not cryptographically verified, so `sem deps` warns and
recommends a `sha256:` archive pin for tamper-proof reproducibility.

Versioned registry dependencies are **reserved** until the registry section
below is implemented. Feature flags are also reserved; a future design should
keep them in SemanticScript build or lock rows rather than introducing another
manifest format.

## Resolving Dependencies With `sem deps`

`sem deps` is the dependency driver. Fetching is build-time authority, so only
`sync` touches the network; `verify` and `list` are strictly offline, and so is
the compiler's import bridge.

```powershell
sem deps sync PATH      # fetch, verify integrity, populate the cache, write sem.lock
sem deps verify PATH    # offline: confirm the cache + lock agree with build.sem
sem deps list PATH      # offline: show declared dependencies and cache/lock state
sem deps cache PATH     # offline: inventory every materialized package (shared + project cache)
sem deps purge PATH     # remove this project's cached dependency source (add --lock to drop sem.lock)
sem deps sync --force PATH     # ignore the cache; re-fetch + re-verify (repairs a corrupt cache)
sem deps sync --offline PATH   # materialize only path/local deps and the existing cache
sem deps --json PATH    # machine-readable sem.deps.v1 payload with nextCommands
```

This is the package lifecycle (CRUD) for agents and humans: `sync` creates/updates,
`list`/`cache` read, `verify` detects corruption (content-hash mismatch),
`sync --force` repairs/redownloads, and `purge` deletes. `cache` works with or
without a `build.sem` — it inventories the shared machine cache plus the
project-local `.semcache`.

After `sem deps sync`, the compiler resolves `import ALIAS MODULE_PATH` against
the materialized cache. A declared-but-unsynced dependency raises an actionable
`sem deps sync` error only when the program actually imports it; an unused,
unsynced dependency never blocks an otherwise offline build.

## Build-Time Fetch Boundary

`dependencyFetch`/`dependencySource` are the build-time dependency API. They
prepare source trees for module import resolution before compiler codegen
starts; they are not a runtime network API.

`sem deps sync` belongs to the `sem` tool driver layer. It reads and updates
`build.sem`, the dependency cache, and `sem.lock`, but it is not a compiler
backend phase. Direct `semsc build.sem` invocation remains validation and
compile-only: it reports dependency rows and resolves imports against the
already-materialized cache, but it never performs network fetches. The import
bridge raises if a declared dependency is missing from the cache.

`sem deps sync` preparation order is:

1. Parse the active `build.sem`.
2. Read the prior `sem.lock` (for reuse and pin verification).
3. Resolve local/path dependencies (copied into the cache, pinned by tree hash).
4. Resolve remote dependencies through the cache and lock.
5. Fetch over https only when allowed (skipped when the cache already matches the lock).
6. Verify integrity, then extract atomically into the cache.
7. Write `sem.lock`.

The `sem deps --json` payload (`sem.deps.v1`) is agent-readable automation data;
it is not part of the lock format. It reports per-dependency `alias`,
`modulePath`, `version`, `sourceKind`, `status`, `resolved`, `integrity`,
`cacheDir`, and any `warnings`.

## GitHub Fetching

GitHub is the first remote fetch kind, but the grammar stays generic:
`dependencyFetch PROJECT ALIAS KIND ...` carries the fetch kind separately from
the dependency request. `github` and `http` are implemented; a future `git`
fetch kind can support generic Git URLs without changing the core dependency
row.

For `dependencyFetch PROJECT ALIAS github OWNER/REPO REF`:

- `OWNER`/`REPO` are validated to `[A-Za-z0-9._-]` with no `.`/`..` segment.
- `REF` is validated to `[A-Za-z0-9._/-]` with no `..` segment and URL-encoded
  as a path segment, so it can never inject a host, scheme, query, or fragment.
- The archive is fetched from the deterministic codeload URL:

```text
https://codeload.github.com/OWNER/REPO/tar.gz/REF
```

- The downloaded bytes are verified against the `sha256:` pin (or the locked
  digest, or recorded trust-on-first-use) **before** extraction.

Fetching uses anonymous HTTPS. Connections are https-only (including across
redirects), the resolved host must be a public address (loopback, private,
link-local, reserved, and multicast addresses are refused to prevent SSRF), and
TLS certificates are verified by the default trust store. Optional token
authentication may be added later, but tokens must never be stored in
`build.sem`, the cache, `sem.lock`, or logs.

**Reserved (future):** resolving a mutable tag/branch to an exact commit through
GitHub metadata before download, a `dependencyFloatingRef` development escape
hatch, and rejecting branch refs in locked/release modes. Today a mutable ref is
made reproducible by the archive `sha256` recorded in `sem.lock`: a later sync
that fetches different bytes for the same ref hard-errors against the lock.

## GitHub Package Format

A GitHub repository is consumable as a SemanticScript package when its **repo
root** is a `build.sem` project. `sem deps sync` downloads the codeload tarball
(`OWNER/REPO/tar.gz/REF`), strips the single top-level `REPO-REF/` directory,
and treats the result as the package root. The resolver then reads the package's
own `build.sem` to decide which module paths are importable.

A publishable package repo must contain at its root:

```text
my-semscript-lib/                 # repo root == package root
  build.sem
  main.sem                        # root module source
  json/
    main.sem                      # a submodule source
```

`build.sem` declares the canonical module path and registers every importable
module. The `registerModule` **MODULE_PATH is exactly what consumers import**,
so it should be the public GitHub-style path:

```semanticscript
buildProject mySemscriptLib
modulePath        mySemscriptLib github.com/OWNER/my-semscript-lib
languageVersion   mySemscriptLib "1.0"
projectVersion    mySemscriptLib "1.0.0"
projectLicense    mySemscriptLib MIT
sourceRoot        mySemscriptLib "."
registerModule    mySemscriptLib github.com/OWNER/my-semscript-lib "."
registerModule    mySemscriptLib github.com/OWNER/my-semscript-lib/json "json"
```

Module sources declare their module and **export** the public surface (only
exported symbols are importable):

```semanticscript
module github.com/OWNER/my-semscript-lib
exportOperation github.com/OWNER/my-semscript-lib parseConfigLine
operation parseConfigLine
purpose operation parseConfigLine "..."
```

Rules and constraints (enforced by the resolver):

- `registerModule` folders must stay **inside** the package; a path containing
  `..` or an absolute path is rejected (a fetched package may not point the
  compiler at files outside its cache directory).
- If a package ships no `build.sem`, the resolver maps the consumer-declared
  module path to the root `main.sem` / `index.sem` / the sole `.sem` file — fine
  for a single-module package, but multi-module packages must ship a `build.sem`
  with `registerModule` rows.
- Use Git **tags or commits** for `REF` so releases are stable; consumers should
  pin `dependencyIntegrity sha256:<archive-digest>` (printed by the first
  `sem deps sync`). `commit:` pins select a ref but are advisory only.
- The package's `.semcache/`, `build/`, `.git/`, and `__pycache__/` are ignored
  when the source is materialized.

A consumer then depends on and imports the registered paths:

```semanticscript
# consumer build.sem
dependency        app lib github.com/OWNER/my-semscript-lib v1.0.0
dependencyFetch   app lib github OWNER/my-semscript-lib v1.0.0
dependencyIntegrity app lib sha256:<archive-digest>

# consumer module source
import lib     github.com/OWNER/my-semscript-lib
import libJson github.com/OWNER/my-semscript-lib/json
```

## Dependency Cache

Fetched dependencies use a shared, version-keyed cache so multiple projects
share one download per pinned version while versions coexist. The shared root is
`SEMANTICSCRIPT_CACHE` (or `SEMSC_CACHE`), falling back to a per-user cache
directory. `.semcache/` beside `build.sem` is the project-local cache used for
`path`/`local` dependencies and whenever a `dependencyCache PROJECT "PATH"` row
is present (which pins all dependencies project-local). `.semcache/` is ignored
by Git and must not sit under a production source root.

Cache key layout:

```text
<cache-root>/
  github.com/OWNER/REPO/REF/      # fetched github packages, version-keyed
  http/<url-hash>/                # fetched https archives
  path/<module/path/segments>/    # copied path/local packages
```

Implemented cache rules:

- keys are version/content-addressed so mutable refs and multiple versions never collide;
- downloads and copies are built in a sibling temp directory and swapped into
  place atomically, so a crashed or concurrent `sync` never leaves a
  half-populated cache;
- fetched archives are SHA-256-verified before extraction; extraction refuses
  path-traversal (`..`) and symlink/hardlink members, neutralizes absolute
  paths and rejects any entry that would escape the cache dir, rejects Windows
  reserved/trailing-dot names, and bounds decompression bombs (compressed and
  uncompressed size caps);
- `verify` rehashes the cached tree against `sem.lock` before reuse.

**Reserved (future):** quarantine of corrupt entries with a repair command, and
per-key lock files under the cache for stronger cross-process coordination
(today concurrent syncs are made safe by atomic temp-swap, last-writer-wins).

## Lock File

Lock data lives in `sem.lock`, a JSON file (schema `sem.lock.v1`) sorted
deterministically by key. Each dependency records identity plus the resolved
content so locked builds are reproducible and offline:

```json
{
  "schemaVersion": "sem.lock.v1",
  "project": "demo",
  "dependencies": [
    {
      "alias": "semstd",
      "modulePath": "github.com/example/semstd",
      "version": "v1.0.0",
      "sourceKind": "github",
      "resolved": "<archive sha256 or path tree hash>",
      "integrity": "sha256:<...>",
      "contentHash": "<tree hash of the materialized cache dir>"
    }
  ]
}
```

`contentHash` is the offline integrity anchor: `verify` and idempotent re-sync
compare the cached tree against it (the archive bytes are gone after
extraction). Normal builds use the locked content without hitting the network;
`verify` reports drift when `build.sem` changes a dependency's module path,
version, or source kind while the lock is stale.

**Reserved (future):** richer per-dependency lock rows for transitive
dependencies (`lockedDependencyTransitive`), resolved commits distinct from the
archive digest, and dependency build-tape/language-version capture.

## Registry Deferral

**Reserved (future).** Do not build a public registry until local path
dependencies, Git dependencies, cache layout, lock tapes, and transitive
resolution are stable.

Registry requirements before implementation:

- immutable package versions;
- checksums for every downloadable artifact;
- clear module-path ownership rules;
- namespace transfer and abandonment policy;
- support for private/internal registries before assuming one public host.

Package signing is deferred. Checksums are mandatory before signing: every
registry artifact must have a stable digest in the lock or release manifest. A
future signing design can layer signatures over those same artifacts.

Ownership rules should follow module paths. A package owner controls a module
path prefix, and packages must not publish modules outside their owned prefix.

## Runtime Outbound HTTP

Runtime outbound HTTP is a separate, unrelated surface from build-time
dependency fetching. It should use names such as `http.clientRequest`,
`http.clientResponseText`, or `net.fetchText` that do not collide with
server-side `http.request*`/`http.response*` APIs, and must export visible
effects (for example `network.http.client read`). Its first scope is blocking
HTTP/1.1 plus HTTPS; HTTP/2 client support is deferred until TLS, ALPN, and
backend-library choices are settled.
