# SemanticScript standard library (`std/`)

This directory contains the SemanticScript standard library. It is a library
tree, not a buildable project, so it does not own a `build.sem` file.
`module.sem` is the top-level `standard` relay, and each child module owns a
linker/import entry at `std/<module>/main.sem`.

Most helper logic is written in SemanticScript: byte loops, classifiers,
integer math, float helpers, memory walks, table lookups, and small container
algorithms. A few operations intentionally bottom out in host C calls where
there is no useful pure-SemanticScript substitute yet, such as `c.putchar`, `c.malloc`,
`c.free`, `c.clock`, `c.time`, `c.getenv`, `c.exit`, `c.abort`, and
`c.raise`.

## Contents

Each module folder has the same shape: `main.sem` is the module entry and
`main.test.sem` is its companion smoke or unit-style test.

Namespaced standard modules live under matching folders. `html/main.sem` owns
the official `standard.html` import path for first-class HTML template syntax;
`gui/main.sem` owns the official metadata module for declarative Windows GUI
row vocabulary, handler types, handles, closed token sets, runtime target
names, status constants, and `gui.*` capability contracts; `http/main.sem`,
`json/main.sem`, `net/main.sem`, and `sqlite/main.sem` own the official
metadata modules for compiler-owned `http.*`, `json.*`, `net.fetch*`, and
`sqlite.*` intrinsic namespaces.
App modules import them with rows such as `import html standard.html`,
`import gui standard.gui`, `import http standard.http`,
`import json standard.json`, and `import net standard.net`.
The compiler resolves `standard.<module>` directly to `std/<module>/main.sem`.

`standard.json` currently exports the implemented builder/finder aliases
(`JsonBuilder`, `JsonText`, `JsonFieldName`, `JsonStringValue`,
`JsonScratchBuffer`, `JsonCapacityBytes`) plus the public document CRUD
contracts (`JsonDocument`, `JsonCursor`, `JsonPath`, `JsonValueKind`,
`JsonAccessError`, `JsonEncodeError`, and `JsonDecodeError`). The document
CRUD, `jsonBody`, and typed `json.stringify.<TypeName>` /
`json.parse.<TypeName>` entry points are documented in
`docs/language/json-crud.md`; check `docs/reference/syntax-inventory.md` for the current lowering
status before using a surface in executable code.

`standard.net` currently owns the prototype outbound client contract. It
reserves `net.fetchText`, `net.fetchBytes`, request/response records such as
`HttpGetRequest` and `HttpTextResponse`, role types, and the
`networkHttpClient` capability so source can be modeled without exposing libuv
or libcurl. The current compiler lowers `net.fetch*` through
`native_http_client` and links `native_async` as the adapter dependency; real
network behavior still depends on the opt-in libcurl/libuv runtime build.

## API comment extraction

Std modules can include typed comment blocks intended for agents and future
documentation extractors. The semantic rows remain the source of truth;
comments summarize API usage, ownership, failure, and trust-boundary guidance
without inventing behavior that is not present in the rows.

Suggested compact shape inside `main.sem`:

```text
# rationale: use this module for route handlers, response writers, SSE, or outbound client calls.
# invariant: exported SemanticScript operations are the public API; direct runtimeBinding targets are internal hooks.
# memory: returned heap-owned values, cleanup rules, and scratch-buffer requirements.
# failure: null sentinels, non-zero status codes, or Result error domains.
# security: caller validation expected at trust boundaries.
```

A simple extractor can read contiguous typed comments above a `module`, `type`,
`capability`, `storage`, or `operation` row, then join them with nearby
`purpose`, `invariant`, `typeInvariant`, `runtimeBindingPrecondition`,
`export*`, `effect`, `memory`, and `useCapability` rows.

The `sem` wrapper exposes this as a standard-library documentation surface:

```powershell
python SemanticScript\tools\sem.py docs list --module http --json
python SemanticScript\tools\sem.py docs list --module http --summary-tag failure
python SemanticScript\tools\sem.py docs get http.clientGet --json
python SemanticScript\tools\sem.py docs get gui.applicationCreate --json
python SemanticScript\tools\sem.py docs get json.createDocument --json
python SemanticScript\tools\sem.py docs get http.clientFetchNative --all --json
```

`docs list` returns public operations by default. Public means an operation
is exported or is a normal SemanticScript helper; runtimeBinding helpers and
`*Native` operations are hidden unless `--all` is passed. `docs get` uses
the same visibility rule. Operation payloads promote `purpose` and `invariants`
to predictable top-level fields, resolve capability declarations, include
runtime binding preconditions, and provide a `usage` object with call rows,
required caller effects/capabilities, explicit `failureHandling` rows, cleanup
rows, and failure-mode guidance. `usage.call.rows` are the call-and-bind core;
also apply `usage.failureHandling.rows` and `usage.cleanup.rows` when their
`required` flags are true. If `usage.preconditions.required` is true, validate
the named caller precondition before emitting the call. Cleanup payloads for
`c.free` include the caller's required heap-free effect and authority guidance.
For non-exported capabilities, `usage.useCapabilityRows` stays empty and the
payload provides `usage.authorityRows` plus complete local
`usage.localCapabilityRows` declaration/use pairs instead of encouraging
callers to reference std-internal capability names.
Unexported helpers report `visibility.apiTier:
"helper"` and `agentWarnings` so agents know they are less stable than exported
APIs.
Modules without operation docs still appear in `moduleDocs` with
`operationDocStatus: "no-operation-docs"`; compiler-owned call targets such as
`gui.*`, known `json.*`, `console.*`, `math.*`, `pointer.*`, and selected `c.*`
targets appear under `moduleDocs[].callTargets` and can be retrieved directly
with `docs get TARGET --json`. Compiler-owned modules use an empty
`usage.importRow` because they do not require source imports. Reserved targets
carry `loweringStatus: "reserved"`; lowered targets report
`visibility.apiTier: "compiler-lowered"`.

The same docs objects can be cached for project/user code with
`docs index --path PATH --db .sem/docs.sqlite --json` and searched with
`docs search QUERY --db .sem/docs.sqlite --json`. The SQLite cache stores FTS
text plus real sentence-transformer vector blobs; it uses `sqlite-vec` when
available and otherwise falls back to in-process cosine ranking over the stored
semantic vectors. Install `requirements-docs.txt` before indexing with the
default embedding provider, then pre-cache `BAAI/bge-small-en-v1.5` or pass
`--allow-model-download` on the first trusted-network index. New projects can opt in with
`sem new --enable-docs-index PATH`; otherwise this stays off. MCP mode exposes
the same list/get/search surfaces and can run a path-scoped background docs
worker so changed `.sem` files are re-indexed without blocking search requests.

This library tree intentionally has no `build.sem`. Add standard modules under
`std/<module>/main.sem` and relay them from `std/module.sem`.

For GUI specifically, `standard.gui` is intended to keep the compiler small:
parser, linter, and codegen may mirror the row names and numeric IDs for fast
validation and lowering, but the user-facing vocabulary and semantic contracts
belong in `std/gui/main.sem`.

Stdlib/runtime ownership rule: when a compiler target branch adds or changes a
native adapter, the branch must name the owning standard module or compiler
runtime surface in the compiler link registry, update the module contract here,
and add an executable or intentional-unsupported test for that target.

## Current Status

Active stdlib implementation surface. Low-level `c.*` calls are still accepted
here as bootstrap/runtime implementation details; app-facing code should move
toward SemanticScript API operations as they become available.

## Coverage

The current tree has 36 standard modules plus the top-level `standard` relay.

| file | category | operation blocks |
| --- | --- | ---: |
| `module.sem` | top-level `standard` relay | 0 |
| `<module>/main.sem` | standard module entry and exported surface | varies |
| `<module>/main.test.sem` | companion self-test | 1 |

## Running the self-tests

From `SemanticScript/`:

```powershell
python tests/test_stdlib.py
```

The harness compiles every file through the trusted Python reference compiler
(`compiler/semsc.py`) and runs it. Most files must print exactly `OK`; `stdio`
prints a fixed multiline smoke-test transcript.

Each file can also be run directly:

```powershell
python compiler/semsc.py std/string/main.test.sem --run --quiet
python compiler/semsc.py std/math_float/main.test.sem --run --quiet
python compiler/semsc.py std/stdio/main.test.sem --run --quiet
```

## Compiler support this depends on

The stdlib files use a few compiler capabilities beyond the original 1.0.0
surface:

- lazy `puts` / `printf` extern declarations, so SemanticScript code can define user
  operations with those names without colliding with libc glue;
- typed user-operation returns derived from `output` lines, including pointer,
  integer, and float success values;
- typed `return ok`, `return error`, and `return value` coercion;
- user-operation error predicates that match the return shape (`0`, null, or
  `0.0` as the success sentinel);
- `math.convertInt64ToFloat64` and `math.convertFloat64ToInt64` lowering for pure-SemanticScript float helpers.

## Still missing

This is not a complete C standard library. The large remaining surfaces are
formatted input/output, full file streams, complete transcendental math with
IEEE edge cases, locale, wide characters, complex numbers, floating-point
environment controls, setjmp/longjmp, atomics, and true cross-file linking.

The current value of this directory is narrower and concrete: it gives the
compiler real SemanticScript library code to compile, run, and regress-test.
