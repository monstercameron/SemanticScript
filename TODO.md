# SemanticScript 1.0 Release TODO

This file tracks the release-readiness gaps found in the 2026-05-18 project
review. A task is only done when the linked command or artifact is clean.

## P0 - Todo Web Native Webserver Effort

- [x] Add a granular root TODO section for the Todo Web native webserver work.
- [x] Preserve existing release TODO items without marking unrelated work done.
- [x] Keep the Todo Web effort scoped away from unrelated dirty app files.
- [x] Review current `webServer`, `serverHost`, `serverPort`, and `route`
      parser support.
- [x] Review current `target webServer` codegen behavior.
- [x] Review current opaque input handling for `HttpRequest`.
- [x] Review current type lowering for `HttpRequest` and `HttpResponse`.
- [x] Review the native HTTP adapter ABI in `sem_http_runtime.h`.
- [x] Review the default runtime adapter implementation in
      `sem_http_runtime.c`.
- [x] Review native executable linking in `semsc.py`.
- [x] Add LLVM type support for `HttpRequest`.
- [x] Add LLVM type support for `HttpResponse`.
- [x] Preserve `HttpRequest` route-handler inputs in the webserver ABI.
- [x] Preserve `HttpResponse` route-handler inputs in the webserver ABI.
- [x] Keep ordinary opaque dependency inputs skipped outside the web ABI.
- [x] Detect routed `webServer` declarations during no-entry codegen.
- [x] Collect route handler operation names before declaring user op functions.
- [x] Validate that route handlers declare `HttpRequest` then `HttpResponse`.
- [x] Validate that route handlers return `CSignedInt32` / i32.
- [x] Emit a real native `main` for routed webserver programs.
- [x] Emit an in-memory route table from `route` metadata.
- [x] Emit native server config from `serverHost`, `serverPort`, and routes.
- [x] Emit handler function pointers into the route table.
- [x] Declare `ss_http_server_run` in generated LLVM.
- [x] Call `ss_http_server_run` from generated `main`.
- [x] Lower `http.responseText` to `ss_http_response_text`.
- [x] Lower `http.requestMethod` to `ss_http_request_method`.
- [x] Lower `http.requestPath` to `ss_http_request_path`.
- [x] Preserve content type defaulting in the runtime adapter.
- [x] Link `sem_http_runtime.c` automatically for routed webserver executables.
- [x] Link Winsock automatically for routed webserver executables on Windows.
- [x] Replace the runtime stub backend with a blocking HTTP/1.1 socket backend.
- [x] Validate route tables before binding a socket.
- [x] Bind the configured server host.
- [x] Bind the configured server port.
- [x] Listen with a fixed connection backlog.
- [x] Accept client connections in a blocking loop.
- [x] Parse the HTTP request line.
- [x] Extract request method.
- [x] Extract request path.
- [x] Strip query strings before exact-route matching.
- [x] Match route methods case-insensitively.
- [x] Match route paths exactly.
- [x] Dispatch matched routes to generated SemanticScript handlers.
- [x] Pass `SSHttpRequest` into handlers.
- [x] Pass `SSHttpResponse` into handlers.
- [x] Send handler-written text responses.
- [x] Send `400 bad request` for malformed request lines.
- [x] Send `404 not found` for missing routes.
- [x] Send `500 handler failed` for handler status failures.
- [x] Send `500 handler did not write a response` for empty handler responses.
- [x] Emit `Content-Type`.
- [x] Emit `Content-Length`.
- [x] Emit `Connection: close`.
- [x] Close client sockets after each response.
- [x] Update runtime CMake to link Winsock on Windows.
- [x] Update native HTTP runtime docs for the new fallback backend.
- [x] Update native HTTP language docs for real native `main` support.
- [x] Update Todo Web to use a less collision-prone local port.
- [x] Add a Todo Web HTTP test harness.
- [x] Test Todo Web parse and compiler lint.
- [x] Test Todo Web standalone linter summary.
- [x] Test Todo Web LLVM IR emission.
- [x] Inspect emitted IR for the route handler signature.
- [x] Inspect emitted IR for `ss_http_response_text`.
- [x] Inspect emitted IR for `ss_http_server_run`.
- [x] Test native executable emission.
- [x] Test server startup from the native executable.
- [x] Test `GET /` returns HTTP 200.
- [x] Test `GET /` returns `hello from todo web`.
- [x] Test `GET /?sample=1` still routes to `/`.
- [x] Test `GET /missing` returns HTTP 404.
- [x] Test 404 body is `not found`.
- [x] Test headers include `Content-Type`.
- [x] Test headers include correct `Content-Length`.
- [x] Test the server through Python `http.client`.
- [x] Test the server through external `curl.exe`.
- [x] Test runtime CMake build after socket backend changes.
- [x] Run compiler unit tests after codegen changes.

## P0 - Release Validation Must Be Green

- [x] Fix `python SemanticScript\tests\compare.py`.
  - [x] Fix `string_analyzer.sscript` parity: JS reports `characters: 104`
        and SemanticScript reports `characters: 101`; top-word ordering also
        differs (`favors` vs `semanticscript` in the fifth slot).
- [x] Fix `python SemanticScript\tests\sem_compiler_parity.py`.
  - [x] Fix `string_analyzer.sscript` parity under `bootstrap_general`.
  - [x] Fix `webserver_console.sscript` long-running parity under
        `bootstrap_general`.
- [x] Fix unexpected failures in `python SemanticScript\tests\feature_coverage.py`.
  - [x] `121_cross_file_import.sscript`: emitted IR contains
        `%addSevenCall_res = add i64 35, %`.
  - [x] `88_string_byte_scan_loop.sscript`: expected `14\n`, actual `17\n`.
  - [x] `89_pointer_returning_recursion.sscript`: expected `ipt\n`, actual
        `script\n`.
  - [x] `92_c_fopen_fclose.sscript`: expected `opened\n` and exit `0`, actual
        empty stdout and exit `1`.
- [x] Decide how to treat the 30 `expect.xfail` feature tests before 1.0.
  - [ ] Either close the bootstrap gaps and remove the xfail markers.
  - [x] Or explicitly scope 1.0 to the Python reference compiler and document
        `bootstrap_general.sscript` as experimental/self-hosting progress.

## P1 - Runtime And Syntax Scope

- [x] Resolve or explicitly defer the 7 `Partial` rows in `SYNTAX.md`.
  - [x] `codec NAME [ATTRS...]`.
  - [x] `jsonCodec NAME`.
  - [x] `webServer NAME`.
  - [x] `route SERVER METHOD PATH HANDLER`.
  - [x] `collectionOperation COLLECTION.OP`.
  - [x] `json.encode.RecordTypeName` / `json.decode.RecordTypeName`.
  - [x] `TaskList.append` / `TaskMap.get`.
- [x] Make the 1.0 support matrix explicit:
  - [x] Python reference compiler support.
  - [x] Self-hosting/bootstrap support.
  - [x] VS Code extension support.
  - [x] Refined syntax support.
  - [x] Web/HTTP runtime support.

## P1 - Full 1.0 Product Surface Gap Backlog

This section tracks the larger "complete product surface" gaps. These are not
all blockers for the scoped 1.0 release unless the release definition changes
from "honest scoped compiler/tooling release" to "complete language/runtime
product".

### Compiler And Language Strictness

- [x] Decide whether self-hosting is a 1.0 requirement.
  - [ ] If yes, make the SemanticScript-written bootstrap compiler compile the
        full documented language.
  - [x] If no, keep documenting `semsc.py` as the production 1.0 compiler and
        bootstrap as preview.
- [x] Replace unknown/missing operation output fallback-to-`i32` with a stricter
      diagnostic for release-mode builds, or document the fallback as a scoped
      compiler compatibility behavior.
- [ ] Add module namespace enforcement beyond import inlining and metadata.
  - [x] Validate `module NAME` as a dotted namespace.
  - [x] Reject conflicting module declarations in one resolved source.
  - [ ] Detect duplicate operation names across imported modules.
  - [ ] Detect ambiguous unqualified references when imports expose the same
        symbol.
  - [ ] Define whether `importModule X as Y` creates a real namespace boundary.
- [x] Add runtime capability/authority enforcement, or explicitly keep
      capability enforcement as linter/spec-only for 1.0.
  - [x] Add strict lint/compiler diagnostics for missing capability or inline
        authority coverage.
  - [x] Document runtime authority enforcement as out of scope for scoped 1.0.
  - [ ] Decide how capability tokens are represented in generated binaries.
  - [ ] Decide whether authority failures are compile-time errors, runtime
        traps, or typed runtime errors.
  - [ ] Add tests proving unauthorized runtime effects cannot execute if runtime
        enforcement is in scope.
- [ ] Audit refined syntax rows that are parser/linter-only and ensure each one
      is marked metadata, synchronous fallback, partial, or implemented.

### Native HTTP / Webserver Completeness

- [ ] Wire the H2O / HTTP2 backend behind an explicit backend flag.
  - [ ] Build H2O reproducibly on Windows or document the supported toolchain.
  - [ ] Link H2O outputs from `semsc.py --emit-exe`.
  - [ ] Add HTTP/2 smoke coverage once TLS/ALPN setup exists.
- [x] Add request body APIs.
  - [x] Add source-level call targets for reading request body text and length.
  - [x] Preserve body lifetime and size limits in the native adapter.
  - [x] Add POST tests that inspect actual body content.
- [x] Add request header APIs.
  - [x] Add source-level call targets for header lookup.
  - [x] Preserve header names and values in the native adapter.
  - [ ] Add case-insensitive header lookup tests.
- [x] Add response header APIs.
  - [x] Add source-level call targets for setting headers.
  - [x] Add tests for `Allow`, `Content-Type`, and custom middleware headers.
- [x] Add query parameter APIs.
  - [x] Preserve raw query string while still matching routes by path.
  - [x] Add source-level call target for simple query parameter lookup.
  - [ ] Add decoding/validation rules for repeated and missing params.
- [ ] Add path parameter routing such as `/todos/:todoId`.
  - [ ] Define route precedence between exact routes and parameter routes.
  - [ ] Add tests for path parameter extraction and invalid routes.
- [x] Execute `routeMiddleware` metadata in the native runtime.
  - [x] Define one path-scoped middleware slot before the route handler.
  - [x] Define non-zero middleware status as a request failure.
  - [x] Add tests proving middleware can inspect request state and set headers.
- [ ] Enforce `routeTimeout` metadata in the native runtime.
  - [ ] Define timeout behavior for blocking handlers.
  - [ ] Add tests for timeout failure response or trap behavior.
- [ ] Add persistent web app state/storage helpers.
  - [ ] Define safe mutable process state for request handlers.
  - [ ] Add tests for sequential request state changes.
- [ ] Add static-file serving helper.
  - [ ] Define root directory safety and path traversal behavior.
  - [ ] Add MIME/content-length tests.
- [ ] Add graceful shutdown hook.
  - [ ] Define signal/control API.
  - [ ] Add tests that server processes stop without forced termination.

### Data, Codec, And Collection Runtime

- [ ] Implement real JSON codec runtime for records.
  - [ ] Lower `json.encode.RecordTypeName`.
  - [ ] Lower `json.decode.RecordTypeName`.
  - [ ] Enforce required fields, unknown-field policy, and limits.
  - [ ] Add tests for valid JSON, malformed JSON, missing fields, and escaping.
- [x] Implement generic `codec` runtime or keep it as explicit metadata-only
      syntax for 1.0.
- [ ] Implement typed collection runtime for `TaskList.append`, `TaskMap.get`,
      and related collection operations.
  - [ ] Define allocation ownership for list/map storage.
  - [ ] Define bounds and missing-key behavior.
  - [ ] Add tests for append/get/update failure paths.
- [ ] Replace dotted-target zero-result fallback for partial collection/codec
      calls with diagnostics when a source claims runtime behavior.
  - [x] Add semlint2 diagnostics for record JSON codec, generic codec, and
        typed collection runtime fallbacks.

### Concurrency, Async, And State Runtime

- [x] Decide whether a real scheduler/event loop is in scope for 1.0.
  - [ ] If yes, implement scheduler-backed `start`, `await`, groups, and worker
        pools.
  - [x] If no, keep synchronous lowering documented and tested.
- [x] Replace single-thread mutex no-op semantics with runtime locking, or keep
      them documented as single-thread fallback only.
- [x] Implement cross-process shared state, or explicitly scope `sharedState`
      to same-process globals for 1.0.
- [x] Add runtime guard-token ownership enforcement, or keep guard tokens as
      linter/spec contracts for 1.0.
- [x] Add tests that concurrency/time/cleanup docs match actual lowering.

### Release, Packaging, And Repository Policy

- [x] Add root `LICENSE`.
- [x] Align `vscode-semanticscript/package.json` license with root `LICENSE`.
- [ ] Decide VS Code publisher identity before marketplace publishing.
- [x] Align VS Code extension version with the release plan.
- [ ] Get to a release-clean worktree before tagging.
  - [ ] Commit or intentionally discard modified source/docs.
  - [ ] Commit or intentionally remove untracked README/doc files.
  - [ ] Confirm generated `.exe`, `.ll`, `__pycache__`, `todos.json`, and
        `.vsix` artifacts are ignored and absent from source control.
- [x] Decide whether duplicate top-level `python/` and `samples/python/`
      folders should both remain.
- [x] Decide whether `.sem` mirror files under `SemanticScript/sem/` should be
      tracked alias fixtures or generated artifacts.
- [x] Run and record aggressive validation before any 1.0 tag.
  - [x] Compiler unit tests.
  - [x] Standalone linter tests.
  - [x] Structured linter tests.
  - [x] Feature coverage tests.
  - [x] Bootstrap parity tests.
  - [x] Native HTTP webserver tests.
  - [x] Runtime CMake build.
  - [x] VS Code extension syntax/package checks.

## P1 - Packaging, Install, And CI

- [x] Add dependency metadata for Python tooling.
  - [x] Document Python version requirements.
  - [x] Document `llvmlite` requirement.
  - [x] Document `clang` / `SEMSC_CLANG` requirement.
- [x] Add a repeatable release validation entrypoint.
  - [x] CI workflow or script for compiler unit tests.
  - [x] CI workflow or script for stdlib tests.
  - [x] CI workflow or script for semlint2 tests.
  - [x] CI workflow or script for extension syntax check.
  - [x] CI workflow or script for parity/feature coverage once green.
- [x] Add release process documentation.
  - [x] Required local commands.
  - [x] Artifact cleanup rules.
  - [x] Version bump rules.
  - [x] VSIX packaging rule.
- [x] Decide license before publishing.
  - [x] Add root `LICENSE`.
  - [x] Align `vscode-semanticscript/package.json` license.
- [ ] Decide VS Code publisher/marketplace identity.
  - [ ] Replace `publisher: semanticscript-local` if publishing externally.
  - [x] Align extension version with release plan.

## P2 - Documentation Cleanup

- [x] Remove stale `experiments/` references from current docs.
  - [x] `README.md`.
  - [x] `SYNTAX.md`.
  - [x] `SemanticScript/AST.md`.
  - [x] `docs/toolchain/vscode-extension.md`.
  - [x] `SemanticScript/compiler/semsc.py` comments if they refer to deleted
        paths rather than current refined examples.
- [x] Fix stale documentation map entries.
  - [x] Replace `SemanticScript/CHANGELOG.md` with root `CHANGELOG.md`.
  - [x] Remove references to retired `experiments/whatsneeded.md`.
  - [x] Remove references to retired `experiments/refined_syntax_graph.md`.
- [x] Fix bad linter command examples.
  - [x] Replace `SemanticScript/as` with a real path such as
        `SemanticScript/sem`.
- [x] Fix grammar issues found during review.
  - [x] `An SemanticScript file` -> `A SemanticScript file`.
- [x] Update docs for recently added compiler flags.
  - [x] `--build-profile dev|prod`.
  - [x] `--runtime-checks off|traps|panic`.
  - [x] `--persist-llvm-ir auto|yes|no`.
  - [x] `SSRUN001` runtime panic output.
  - [x] `SSOK000` / `SSOK001` success output.

## P2 - Repository Hygiene

- [ ] Get to a release-clean worktree before tagging.
  - [ ] Commit or intentionally discard modified source/docs.
  - [ ] Commit or intentionally remove untracked README/doc files.
  - [x] Keep generated `.exe`, `.ll`, `__pycache__`, `todos.json`, and `.vsix`
        artifacts ignored and out of source control.
- [x] Run legacy-name scans before release.
  - [x] Confirm no `AgentScript` branding remains except the repository folder
        name or intentionally documented local paths.
  - [x] Confirm no stale `experiments/` paths remain after docs cleanup.

## P3 - Nice-To-Have Before 1.0

- [x] Add `SECURITY.md`.
- [x] Add `CONTRIBUTING.md`.
- [x] Add a top-level release checklist command block in `README.md`.
- [x] Decide whether the duplicate top-level `python/` and `samples/python/`
      folders should both remain.
- [x] Decide whether `.sem` mirror files under `SemanticScript/sem/` should be
      tracked as alias fixtures or generated artifacts.
