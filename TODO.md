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
  - [x] Add semlint diagnostics for record JSON codec, generic codec, and
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

## P1 - Project Layout, Build Tape, Modules, Imports, And Exports

This section captures the post-discussion direction for project structure:
no TOML manifest, `build.sem` as the project/build/comptime surface,
`main.sem` as the default executable entry, build-owned module registry,
module-owned import/export contracts, colocated `*.test.sem` files, Go-style
dependency fetching, and SemanticScript-native export/import contracts.

### Parallel Workstream Split For 6 Agents

Use these ownership boundaries when running this effort with six simultaneous
agents. Each workstream should update its owned files only, record completed
items in this section, and leave integration notes for the final coordinator.

#### Agent 1 - Build Tape And Project Discovery

Owned scope: `build.sem` grammar, project-root discovery, build configuration
validation, and compiler project-mode entry.

- [ ] Define and implement the build-tape parser surface.
  - [x] Add parser support for `buildProject`.
  - [x] Add parser support for `modulePath`.
  - [x] Add parser support for `languageVersion`.
  - [x] Add parser support for `projectVersion`.
  - [x] Add parser support for `projectLicense`.
  - [x] Add parser support for `sourceRoot`.
  - [x] Add parser support for `mainFile`.
  - [x] Add parser support for `mainOperation`.
  - [x] Add parser support for `testPattern`.
  - [ ] Add parser support for `dependency`.
  - [x] Add parser support for `dependencySource`.
  - [x] Add parser support for `dependencyIntegrity`.
  - [x] Add parser support for `buildProfile`.
  - [x] Add parser support for `optLevel`.
  - [x] Add parser support for `runtimeChecks`.
  - [x] Add parser support for `persistLlvmIr`.
  - [x] Add parser support for `nativeOutput`.
  - [x] Add parser support for `targetRuntime`.
  - [x] Reserve but do not execute `comptimeOperation`.
- [ ] Implement build project discovery.
  - [ ] Search current directory and ancestors for `build.sem`.
  - [ ] Support single-file mode when no `build.sem` exists.
  - [ ] Reject ambiguous nested project roots with a source-located diagnostic.
  - [ ] Preserve source locations for every build-tape row.
- [ ] Implement build-tape validation.
  - [x] Require one active `buildProject`.
  - [x] Validate singleton rows.
  - [x] Validate source roots.
  - [x] Validate target runtime choices.
  - [x] Validate `mainFile` / `mainOperation` requirements per target.
  - [ ] Validate dependency aliases and module paths.
  - [ ] Validate release builds do not use floating dependency refs without a
        lock.
- [ ] Wire project mode into compiler/build flow.
  - [ ] Add compiler project-mode entrypoint.
  - [x] Pass build profile from `build.sem` into existing compiler options.
  - [x] Pass runtime checks from `build.sem` into existing compiler options.
  - [x] Pass LLVM IR persistence from `build.sem` into existing compiler
        options.
  - [x] Resolve native output from `build.sem`.
  - [ ] Add focused tests for valid and invalid build tapes.
- [ ] Agent 1 handoff notes.
  - [ ] Document public parser/validation helpers for Agent 2 and Agent 6.
  - [ ] List any build verbs intentionally parser-only for 1.x.

#### Agent 2 - Build-Owned Modules And Entry Rules

Owned scope: folder-owned module model declared in `build.sem`, root/main entry
resolution, and module metadata validation.

- [ ] Implement folder-module discovery.
  - [ ] Detect folders containing production `.sem` files.
  - [ ] Require each production source folder to be registered with
        `registerModule` in `build.sem`.
  - [x] Treat `*.test.sem` as test files, not production module triggers by
        themselves.
  - [ ] Normalize folder paths across Windows and POSIX.
- [ ] Enforce folder/module consistency.
  - [ ] Validate `moduleFolder MODULE_PATH PATH_TEXT`.
  - [ ] Validate folder module path equals root module path plus folder path
        unless explicit override is designed.
  - [ ] Reject conflicting module rows in `build.sem`.
  - [ ] Reject source files that declare a module different from the
        `build.sem` folder contract.
  - [ ] Decide and implement whether source files may repeat the exact folder
        module row for local context.
- [ ] Implement module metadata checks.
  - [x] Parse `modulePurpose`.
  - [x] Parse `moduleOwns`.
  - [x] Parse `moduleDoesNotOwn`.
  - [x] Parse `moduleDependency`.
  - [x] Parse `moduleWarning`.
  - [x] Parse `moduleInvariant`.
  - [x] Parse `moduleSecurity`.
  - [x] Parse `moduleObservability`.
  - [ ] Require `modulePurpose` for folder modules.
  - [ ] Warn when ownership context is missing.
  - [ ] Warn when declared module dependencies are unused.
  - [ ] Warn when used module dependencies are not declared.
- [ ] Implement entry rules.
  - [ ] Default to `main.sem` when `mainFile` is omitted.
  - [ ] Default to `operation main` when `mainOperation` is omitted.
  - [ ] Reject ambiguous multiple app entries.
  - [ ] Reject executable entry requirements for library targets.
  - [ ] Validate webserver target entry ambiguity.
- [ ] Add module/entry tests.
  - [ ] Missing module contract rows in `build.sem`.
  - [ ] Conflicting module declaration.
  - [ ] Root plus folder module happy path.
  - [ ] Default `main.sem` and `operation main`.
  - [ ] Explicit main file and operation.
  - [ ] Library target with no main.
  - [ ] Webserver target with ambiguous servers.
- [ ] Agent 2 handoff notes.
  - [ ] Document module index API for Agent 3 and Agent 4.
  - [ ] List any migration compatibility assumptions for Agent 6.

#### Agent 3 - Export Contract Tape

Owned scope: exports as public semantic contracts, contract extraction, export
validation, and diagnostics for public API quality.

- [x] Implement export rows.
  - [x] Add `exportType MODULE_PATH TYPE_NAME`.
  - [x] Add `exportError MODULE_PATH ERROR_TYPE`.
  - [x] Add `exportOperation MODULE_PATH OPERATION_NAME`.
  - [x] Add `exportCapability MODULE_PATH CAPABILITY_NAME`.
  - [x] Add `exportConstant MODULE_PATH CONSTANT_NAME`.
  - [x] Decide `exportRecord` / `exportEnum` are redundant; use `exportType`
        for aliases, records, and enums.
- [ ] Enforce export visibility rules.
  - [ ] Treat symbols as private unless exported.
  - [x] Restrict export rows to module source files.
  - [x] Require exported symbols to belong to the same registered module.
  - [x] Reject unknown exports.
  - [ ] Reject duplicate exports.
  - [ ] Reject mutable module storage exports.
  - [ ] Reject local/shared state exports.
  - [x] Allow immutable module storage through `exportConstant`.
- [ ] Build exported operation contracts.
  - [ ] Extract inputs.
  - [ ] Extract outputs.
  - [ ] Extract effects.
  - [ ] Extract capability or authority coverage.
  - [ ] Extract failure types and error cases.
  - [ ] Extract async/timing metadata.
  - [ ] Extract memory metadata.
  - [ ] Preserve source locations for every exported contract edge.
- [ ] Build exported type/error/capability contracts.
  - [ ] Extract record fields and invariants for exported record types.
  - [ ] Extract enum cases for exported enum types.
  - [ ] Extract error cases for exported error types.
  - [ ] Extract capability effect path and access mode.
  - [ ] Extract constant type and value/trust metadata.
- [ ] Add export quality diagnostics.
  - [ ] Warn when exported operations lack `purpose`.
  - [ ] Warn when exported operations have hidden or undeclared effects.
  - [ ] Warn when exported operations wrap dependency behavior without
        ownership/purpose context.
  - [ ] Warn when exported names are overly generic.
- [ ] Add export tests.
  - [x] Exported operation happy path.
  - [ ] Private symbol rejected from external module.
  - [x] Exported immutable constant accepted.
  - [ ] Mutable storage export rejected.
  - [ ] Exported error cases visible to consumers.
  - [ ] Exported capability visible to consumers.
- [ ] Agent 3 handoff notes.
  - [ ] Document contract tape shape for Agent 4 and Agent 5.
  - [ ] Document export diagnostics for Agent 6 docs.

#### Agent 4 - Imports, Qualified Names, And Singular Imports

Owned scope: module imports, qualified access, singular import aliases, shadowing
rules, and imported contract lookup.

- [ ] Refine module import syntax.
  - [x] Decide compatibility path for current `importModule DOTTED.PATH [as
        ALIAS]`.
  - [ ] Define preferred `importModule ALIAS MODULE_PATH` shape if adopted.
  - [ ] Require aliases for external dependency modules.
  - [ ] Reject alias collisions.
  - [x] Reject imports not reachable from `build.sem`.
- [ ] Implement qualified references.
  - [ ] Resolve `moduleAlias.operationName` call targets.
  - [ ] Resolve `moduleAlias.TypeName` type references.
  - [ ] Resolve `moduleAlias.ErrorType` error references.
  - [ ] Resolve `moduleAlias.CapabilityName` capability references.
  - [ ] Reject qualified access to private symbols.
  - [ ] Reject qualified access to mutable storage.
  - [ ] Preserve qualified source names in diagnostics.
- [ ] Implement singular import rows.
  - [ ] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [ ] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [ ] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [ ] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [ ] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [ ] Reject wildcard imports.
  - [ ] Reject implicit singular imports.
- [ ] Enforce alias and shadowing rules.
  - [ ] Reject singular imports that shadow local declarations.
  - [ ] Reject singular imports that shadow other imports.
  - [ ] Reject ambiguous unqualified references.
  - [ ] Warn when many singular imports from one module reduce clarity.
  - [ ] Warn when local alias hides provider domain context.
- [ ] Carry imported contracts through call checking.
  - [ ] Imported operation calls use exported input contract.
  - [ ] Imported operation calls use exported output contract.
  - [ ] Imported operation calls expose exported effect contract.
  - [ ] Imported types carry record/enum metadata.
  - [ ] Imported errors carry error cases.
  - [ ] Imported capabilities carry effect path/access metadata.
- [ ] Add import tests.
  - [ ] Qualified operation call happy path.
  - [ ] Qualified type/error/capability references.
  - [ ] Singular operation/type/error/capability/constant imports.
  - [ ] Private symbol rejected.
  - [ ] Alias collision rejected.
  - [ ] Wildcard import rejected.
  - [ ] Import cycle rejected.
- [ ] Agent 4 handoff notes.
  - [ ] Document import resolution API for Agent 5 dependency cache work.
  - [ ] Document compatibility edge cases for Agent 6 migration docs.

#### Agent 5 - Dependency Fetching, Cache, Locking, And Cross-Module Authority

Owned scope: Go-style dependency fetching, `.semcache/`, lock behavior,
dependency contract loading, and cross-module effect/capability propagation.

- [ ] Define dependency fetch model.
  - [ ] Add `sem get MODULE_PATH@VERSION_OR_REF` design notes.
  - [ ] Support GitHub module paths first.
  - [ ] Keep grammar generic enough for non-GitHub Git paths.
  - [ ] Support local path dependencies.
  - [ ] Support pinned tags.
  - [ ] Support pinned commits.
  - [ ] Reject floating branches in release builds unless explicitly allowed.
- [ ] Implement `.semcache/` behavior.
  - [ ] Store cloned dependencies outside source roots.
  - [x] Keep `.semcache/` ignored by git.
  - [ ] Never mutate cached dependency source during normal builds.
  - [ ] Detect cache corruption.
  - [ ] Support cache refresh through explicit update commands.
- [ ] Define and implement lock data.
  - [ ] Decide between `sem.lock`, `build.lock.sem`, or another SemanticScript
        lock tape.
  - [ ] Record module path.
  - [ ] Record requested version/ref.
  - [ ] Record resolved commit.
  - [ ] Record checksum.
  - [ ] Record dependency module root.
  - [ ] Record transitive dependencies.
  - [ ] Make locked builds avoid network access.
- [ ] Load dependency contract tapes.
  - [ ] Read dependency `build.sem`.
  - [ ] Read dependency module registry rows from `build.sem`.
  - [ ] Read dependency module-source export rows and exported contract tape.
  - [ ] Reject dependencies missing required module metadata.
  - [ ] Surface dependency diagnostics with dependency source paths.
- [ ] Implement cross-module effect and authority propagation.
  - [ ] Caller diagnostics cite imported operation effects.
  - [ ] Caller declares effects triggered by imported calls.
  - [ ] Caller proves capability or authority coverage.
  - [ ] Imported capabilities preserve hierarchy.
  - [ ] Warn on broad capability re-export without rationale.
  - [ ] Ensure file/network/database/observability effects do not disappear
        through wrappers.
- [ ] Add dependency/effect tests.
  - [ ] Local path dependency.
  - [ ] GitHub tag/commit dependency if network tests are allowed.
  - [ ] Locked build avoids network.
  - [ ] Missing dependency `build.sem`.
  - [ ] Missing dependency module contract rows in `build.sem`.
  - [ ] Imported operation with filesystem effect.
  - [ ] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
- [ ] Agent 5 handoff notes.
  - [ ] Document lock format for Agent 6 docs.
  - [ ] Document cache/authority APIs for final integration.

#### Agent 6 - Tests, Migration, Docs, VS Code, And Integration Harness

Owned scope: user-facing docs, migration guidance, colocated `*.test.sem`
behavior, VS Code syntax/tooling updates, and integration tests spanning all
workstreams.

- [ ] Define colocated test semantics.
  - [x] `*.test.sem` belongs to the same folder module as sibling source.
  - [x] Exclude `*.test.sem` from normal production builds.
  - [ ] Include `*.test.sem` in `sem test`.
  - [ ] Decide same-folder private symbol access for tests.
  - [ ] Reject test files with conflicting module declarations.
  - [ ] Ensure test-only helpers are excluded from production exports.
- [ ] Update documentation.
  - [ ] Update root `README.md` project layout section.
  - [x] Update `docs/language/program-structure.md`.
  - [x] Update `SYNTAX.md` rows for new verbs.
  - [x] Update `docs/reference/verb-index.md`.
  - [x] Add build/module/import/export examples.
  - [x] Document no-TOML/no-sidecar-manifest decision.
  - [x] Document migration from current `importModule` behavior.
- [ ] Update examples.
  - [x] Add minimal console project using `build.sem` and `main.sem`.
  - [ ] Add multi-module project with module registry in `build.sem` and
        contracts in module source files.
  - [ ] Add library export/import sample.
  - [ ] Add singular import sample.
  - [ ] Add dependency sample using a local path dependency.
  - [ ] Add colocated test sample.
- [ ] Update VS Code extension.
  - [x] Highlight build-tape verbs.
  - [x] Highlight module metadata verbs.
  - [x] Highlight export/import verbs.
  - [x] Add hover text for new verbs.
  - [ ] Add completions for new verbs.
  - [x] Add document symbols for `buildProject`, `module`, exports, and
        imports.
  - [x] Add linter/diagnostic support when new diagnostics exist.
- [ ] Add migration checks.
  - [ ] Audit existing `module` rows.
  - [ ] Audit existing `importModule` rows.
  - [ ] Identify samples needing `build.sem`.
  - [ ] Identify stdlib modules needing module contracts in `build.sem`.
  - [ ] Add staged compatibility warnings before hard errors.
- [ ] Build integration harness.
  - [x] End-to-end console project build.
  - [ ] End-to-end web project build.
  - [x] End-to-end module import/export build.
  - [ ] End-to-end singular import build.
  - [ ] End-to-end colocated test run.
  - [ ] End-to-end dependency cache/lock run using local path dependency.
  - [x] VS Code extension `npm run check`.
- [ ] Agent 6 handoff notes.
  - [ ] Summarize changed docs and examples.
  - [ ] Summarize compatibility warnings users will see.
  - [ ] Provide final integration checklist for coordinator.

### Source Layout Contract

- [x] Define the canonical project layout in the language docs.
  - [x] Document `build.sem` as the required project build tape.
  - [x] Document `main.sem` as the default executable source entry file.
  - [x] Document `*.sem` as normal source files.
  - [x] Document `*.test.sem` as colocated test source files.
  - [x] Document that module folders are registered in `build.sem` and module
        contracts live in module source files.
  - [x] Document that separate `module.sem` files are intentionally not part of
        the project model.
  - [x] Document `build/` as ignored build output.
  - [x] Document `.semcache/` as ignored dependency/build cache.
  - [x] Document that TOML/YAML/JSON manifests are intentionally not part of
        the SemanticScript project model.
- [ ] Add a project layout section to `README.md`.
  - [ ] Show a minimal console app tree.
  - [ ] Show a native web app tree.
  - [ ] Show a multi-module library tree.
  - [ ] Show colocated `*.test.sem` files beside the modules they test.
- [ ] Add a project layout section to `docs/language/program-structure.md`.
  - [ ] Explain how root source files differ from folder modules.
  - [ ] Explain how `main.sem` and `build.sem` interact.
  - [ ] Explain how tests are discovered from `*.test.sem`.
  - [ ] Explain how generated artifacts stay outside source control.
- [ ] Add examples under `samples/` or `app/`.
  - [x] Minimal `build.sem` plus `main.sem` console sample.
  - [ ] Multi-folder module sample with every module registered in `build.sem`.
  - [ ] Webserver sample using `build.sem`, `main.sem`, and folder modules.
  - [ ] Library sample with exports and import consumers.
  - [ ] Tests using `*.test.sem` next to the source folder they validate.

### `build.sem` Build Tape

- [ ] Define the `build.sem` grammar as SemanticScript source, not a sidecar
      config format.
  - [x] Add `buildProject PROJECT_NAME`.
  - [x] Add `modulePath PROJECT_NAME MODULE_PATH`.
  - [x] Add `languageVersion PROJECT_NAME VERSION_TEXT`.
  - [x] Add `projectVersion PROJECT_NAME VERSION_TEXT`.
  - [x] Add `projectLicense PROJECT_NAME LICENSE_TEXT`.
  - [x] Add `sourceRoot PROJECT_NAME PATH_TEXT`.
  - [x] Add `mainFile PROJECT_NAME PATH_TEXT`.
  - [x] Add `mainOperation PROJECT_NAME OPERATION_NAME`.
  - [x] Add `testPattern PROJECT_NAME GLOB_TEXT`.
  - [ ] Add `dependency PROJECT_NAME ALIAS MODULE_PATH VERSION_OR_REF`.
  - [x] Add `dependencySource PROJECT_NAME ALIAS SOURCE_KIND SOURCE_TEXT`.
  - [x] Add `dependencyIntegrity PROJECT_NAME ALIAS INTEGRITY_TEXT`.
  - [x] Add `buildProfile PROJECT_NAME dev|prod`.
  - [x] Add `optLevel PROJECT_NAME 0|1|2|3`.
  - [x] Add `runtimeChecks PROJECT_NAME off|traps|panic`.
  - [x] Add `persistLlvmIr PROJECT_NAME auto|yes|no`.
  - [x] Add `nativeOutput PROJECT_NAME PATH_TEXT`.
  - [x] Add `targetRuntime PROJECT_NAME nativeExe|webServer|library`.
  - [x] Reserve `comptimeOperation PROJECT_NAME OPERATION_NAME` for 2.0.
- [ ] Decide whether `build.sem` accepts only build verbs or the full language.
  - [ ] If restricted, reject executable body rows in `build.sem`.
  - [ ] If full language, define which rows execute at compile time.
  - [x] Document that 1.x treats `build.sem` as declarative build tape.
  - [x] Document that 2.0 can widen this into comptime execution.
- [ ] Implement `build.sem` discovery.
  - [ ] Search current directory and ancestors for `build.sem`.
  - [ ] Stop at repository root if detectable.
  - [ ] Emit a clear diagnostic when multiple candidate project roots compete.
  - [ ] Support single-file mode when no `build.sem` exists.
  - [ ] Never silently create `build.sem`.
- [ ] Implement `build.sem` parsing.
  - [x] Add parser rows for every current build-tape verb.
  - [ ] Preserve source locations for build diagnostics.
  - [ ] Reject unknown build-tape verbs with a suggestion.
  - [ ] Reject missing project names.
  - [ ] Reject duplicate `buildProject` names in one build file.
  - [x] Reject duplicate singleton rows such as `modulePath`, `mainFile`, and
        `mainOperation` unless overriding is explicitly designed.
  - [x] Validate paths without requiring referenced files to exist until the
        project discovery pass.
- [ ] Implement build-tape validation.
  - [x] Require exactly one `buildProject` for normal project builds.
  - [x] Require `modulePath`.
  - [x] Require `languageVersion` or define a default.
  - [x] Require `sourceRoot` or default to `"."`.
  - [x] Require `mainFile` only for executable targets.
  - [x] Require `mainOperation` or default to `main`.
  - [ ] Require dependency aliases to be valid identifiers.
  - [ ] Require dependency module paths to be canonical.
  - [ ] Require dependency versions/refs to be pinned for release builds.
  - [ ] Reject network dependency refs in prod/release builds unless locked.
- [ ] Integrate `build.sem` with `semsc.py`.
  - [ ] Add `semsc.py build.sem --project-build` or equivalent project mode.
  - [x] Make `sem build` call compiler project mode once the `sem` driver
        exists.
  - [ ] Resolve all source roots before parsing application modules.
  - [x] Resolve build profile from `build.sem`.
  - [x] Resolve runtime checks from `build.sem`.
  - [x] Resolve LLVM IR persistence from `build.sem`.
  - [x] Resolve native output path from `build.sem`.
  - [ ] Emit diagnostics in terms of `build.sem` rows when build config fails.
- [ ] Add build-tape tests.
  - [ ] Minimal valid `build.sem`.
  - [ ] Missing `modulePath`.
  - [ ] Duplicate `mainFile`.
  - [ ] Invalid dependency alias.
  - [ ] Invalid module path.
  - [ ] Missing `main.sem`.
  - [ ] Missing `operation main`.
  - [ ] Webserver target with route handlers.
  - [ ] Library target with no `main.sem`.

### `main.sem` Entry Rules

- [ ] Define default executable entry behavior.
  - [ ] If `mainFile` is omitted, look for `main.sem`.
  - [ ] If `mainOperation` is omitted, look for `operation main`.
  - [ ] Require explicit build rows when more than one plausible entry exists.
  - [ ] Reject accidental entry operations in library-only targets.
- [ ] Define root module behavior for `main.sem`.
  - [ ] Declare the root module in `build.sem`.
  - [ ] Decide whether `main.sem` may repeat the root module row for local
        context.
  - [ ] If repetition is allowed, require exact match with `build.sem`.
  - [ ] If repetition is not allowed, lint against source-level module rows in
        project mode.
  - [ ] Document the chosen rule with examples.
- [ ] Define webserver entry behavior.
  - [ ] Allow `main.sem` to declare the primary `webServer`.
  - [ ] Allow `build.sem` to select a webserver target.
  - [ ] Require exactly one routed webserver when target is `webServer` and no
        explicit server is selected.
  - [ ] Reject multiple webservers without an explicit selection row.
  - [ ] Validate route handlers after imports and module resolution.
- [ ] Add entry tests.
  - [ ] Default `main.sem` plus `operation main`.
  - [ ] Explicit `mainFile`.
  - [ ] Explicit `mainOperation`.
  - [ ] Missing main file.
  - [ ] Missing main operation.
  - [ ] Multiple candidate entries.
  - [ ] Webserver target with one server.
  - [ ] Webserver target with ambiguous servers.

### Folder-Owned Modules

- [ ] Make folders hard module boundaries.
  - [ ] Every folder containing production `.sem` files must be declared in
        `build.sem`.
  - [ ] Every production `.sem` file in a folder belongs to that folder's
        module.
  - [ ] Reject multiple module declarations for the same folder in `build.sem`.
  - [ ] Reject source files whose `module` row conflicts with the folder module
        declared in `build.sem`.
  - [ ] Decide whether source files may repeat the folder `module` row for
        local context.
  - [ ] If repetition is allowed, require exact match.
  - [ ] If repetition is not allowed, lint against duplicate module rows in
        source files.
- [ ] Define module path mapping.
  - [ ] Root `modulePath` from `build.sem` defines the project module path.
  - [ ] Folder module path must equal root module path plus folder path unless
        an explicit override row exists.
  - [ ] Reject `..` path escapes in `moduleFolder`.
  - [ ] Normalize slash direction across Windows and POSIX.
  - [ ] Preserve case-sensitivity rules in docs.
  - [ ] Decide whether folder names with hyphens map to module path segments.
- [ ] Add build-owned folder module metadata rows.
  - [ ] Add `moduleFolder MODULE_PATH PATH_TEXT`.
  - [ ] Add `modulePurpose MODULE_PATH TEXT`.
  - [ ] Add `moduleOwns MODULE_PATH TEXT`.
  - [ ] Add `moduleDoesNotOwn MODULE_PATH TEXT`.
  - [ ] Add `moduleDependency MODULE_PATH DEPENDENCY_ALIAS`.
  - [ ] Add `moduleWarning MODULE_PATH TEXT`.
  - [ ] Add `moduleInvariant MODULE_PATH TEXT`.
  - [ ] Add `moduleSecurity MODULE_PATH TEXT`.
  - [ ] Add `moduleObservability MODULE_PATH TEXT`.
- [ ] Enforce minimum module context.
  - [ ] Require `modulePurpose` for every folder module.
  - [ ] Require at least one `moduleOwns` or an explicit no-ownership rationale.
  - [ ] Warn when `moduleDoesNotOwn` is missing for public modules.
  - [ ] Warn when a module imports dependencies not listed by
        `moduleDependency`.
  - [ ] Warn when `moduleDependency` lists unused dependencies.
- [ ] Add module boundary tests.
  - [ ] Folder with missing module rows in `build.sem`.
  - [ ] Folder with conflicting module paths.
  - [ ] Root path plus folder path happy case.
  - [ ] Path normalization on Windows-style paths.
  - [ ] Duplicate module declarations.
  - [ ] Module metadata diagnostics.

### Exports As Public Semantic Contracts

- [x] Define export rows in module source files.
  - [x] Add `exportType MODULE_PATH TYPE_NAME`.
  - [x] Add `exportError MODULE_PATH ERROR_TYPE`.
  - [x] Add `exportOperation MODULE_PATH OPERATION_NAME`.
  - [x] Add `exportCapability MODULE_PATH CAPABILITY_NAME`.
  - [x] Add `exportConstant MODULE_PATH CONSTANT_NAME`.
  - [x] Decide `exportRecord` is redundant with `exportType`.
  - [x] Decide `exportEnum` is redundant with `exportType`.
- [ ] Define export visibility rules.
  - [ ] Symbols are private unless exported.
  - [x] Export rows may only appear in module source files.
  - [x] Exported symbols must be declared in the same registered module.
  - [ ] Exported operations must have complete `input` and `output` contracts.
  - [ ] Exported operations must declare all effects.
  - [ ] Exported operations with effects must prove capability or authority
        coverage.
  - [ ] Exported operations should have `purpose`.
  - [ ] Exported operations should have `warning` when they expose nullable,
        unsafe, or external runtime behavior.
  - [ ] Exported types should have invariants where useful.
  - [ ] Exported constants must be immutable module storage.
  - [ ] Reject export of mutable module storage.
  - [ ] Reject export of local storage.
  - [ ] Reject export of shared state values directly.
  - [ ] Require mutation to cross modules through exported operations.
- [ ] Build a module contract tape.
  - [ ] Extract exported operation inputs.
  - [ ] Extract exported operation outputs.
  - [ ] Extract exported operation effects.
  - [ ] Extract exported operation capability requirements.
  - [ ] Extract exported operation failure types.
  - [ ] Extract exported operation async/timing metadata.
  - [ ] Extract exported operation memory metadata.
  - [ ] Extract exported type/record fields.
  - [ ] Extract exported enum and error cases.
  - [ ] Extract exported constants and literal trust metadata.
  - [ ] Preserve source locations for every exported contract edge.
- [ ] Validate exports.
  - [x] Reject unknown exported symbols.
  - [ ] Reject duplicate exports.
  - [ ] Reject export cycles if a public facade imports and re-exports itself.
  - [ ] Warn when exported operation names are too generic.
  - [ ] Warn when exported symbols have no module ownership context.
  - [ ] Warn when exported operations hide dependencies through wrapper names
        without purpose explaining the abstraction.
- [ ] Add export tests.
  - [x] Exported operation happy path.
  - [x] Unknown exported operation.
  - [ ] Exported private mutable state rejected.
  - [x] Exported immutable constant accepted.
  - [ ] Exported error cases available to consumers.
  - [ ] Exported capability available to consumers.
  - [ ] Contract tape includes effects and failures.

### Module Imports And Qualified Calls

- [ ] Define canonical module import syntax.
  - [x] Keep current `importModule DOTTED.PATH [as ALIAS]` for 1.x
        compatibility.
  - [ ] Prefer `importModule ALIAS MODULE_PATH` for new project modules if the
        grammar can migrate without ambiguity.
  - [x] Document aliases as local source names, not package identities.
  - [ ] Require aliases for external dependencies.
  - [ ] Reject alias collisions with local declarations.
  - [x] Reject imports of modules not reachable from `build.sem`.
- [ ] Define qualified name usage.
  - [ ] Allow `moduleAlias.operationName` call targets.
  - [ ] Allow `moduleAlias.TypeName` type references.
  - [ ] Allow `moduleAlias.ErrorType` error references.
  - [ ] Allow `moduleAlias.CapabilityName` capability references only where
        capability imports are legal.
  - [ ] Reject qualified access to non-exported symbols.
  - [ ] Reject qualified access to mutable storage.
  - [ ] Preserve qualified names in diagnostics.
- [ ] Implement module import resolution.
  - [x] Resolve same-project registered modules.
  - [ ] Resolve dependency modules from `.semcache/`.
  - [x] Resolve standard-library modules.
  - [ ] Reject imports that bypass `build.sem` dependency declarations.
  - [ ] Reject ambiguous module paths.
  - [ ] Cache resolved contract tapes.
  - [ ] Preserve source location of import rows for diagnostics.
- [ ] Add import diagnostics.
  - [ ] Unknown module path.
  - [ ] Unknown alias.
  - [ ] Duplicate alias.
  - [ ] Import cycle.
  - [ ] Imported module lacks module contract rows in `build.sem`.
  - [ ] Imported module has no exports.
  - [ ] Imported symbol exists but is private.
  - [ ] Imported operation contract has undeclared effects.
- [ ] Add import tests.
  - [ ] Qualified call to exported operation.
  - [ ] Qualified type reference.
  - [ ] Qualified error reference.
  - [ ] Private symbol rejected.
  - [ ] Alias collision rejected.
  - [ ] Import cycle rejected.
  - [ ] Standard-library import.
  - [ ] Dependency import from cache.

### Singular Imports

- [ ] Define singular import rows.
  - [ ] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [ ] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [ ] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [ ] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [ ] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [ ] Explicitly reject wildcard imports.
  - [ ] Explicitly reject implicit singular imports by capitalization or naming.
- [ ] Define singular import semantics.
  - [ ] Singular imports create local aliases only.
  - [ ] Singular imports do not change the provider module's contract.
  - [ ] Singular operation imports bring the full operation contract.
  - [ ] Singular type imports bring related record/enum layout metadata.
  - [ ] Singular error imports bring exported error cases.
  - [ ] Singular capability imports bring effect path and access metadata.
  - [ ] Singular constant imports bring immutable value/type metadata.
  - [ ] Singular imports must not shadow local declarations.
  - [ ] Singular imports must not shadow other imports.
  - [ ] Singular imports should be linted when they make the source less clear
        than qualified names.
- [ ] Add singular import lint guidance.
  - [ ] Prefer qualified calls for most module usage.
  - [ ] Allow singular imports for central domain operations used repeatedly.
  - [ ] Allow singular imports for facade modules that intentionally re-export
        public API.
  - [ ] Warn when a file imports many singular operations from the same module.
  - [ ] Warn when singular local alias hides the provider domain.
  - [ ] Require rationale for aliasing two different modules into similar local
        names.
- [ ] Add singular import tests.
  - [ ] Singular operation import happy path.
  - [ ] Singular type import happy path.
  - [ ] Singular error import happy path.
  - [ ] Singular capability import happy path.
  - [ ] Singular constant import happy path.
  - [ ] Unknown exported symbol rejected.
  - [ ] Shadowing local symbol rejected.
  - [ ] Wildcard import rejected.

### Cross-Module Effects And Capabilities

- [ ] Preserve effect contracts across module calls.
  - [ ] Caller diagnostics should cite imported operation effects.
  - [ ] Caller must declare matching effects when imported operation effects
        escape through the call boundary.
  - [ ] Caller must use a capability or authority covering its declared effect.
  - [ ] Callee capability requirements should not be silently satisfied by the
        provider module once called from another module unless the contract says
        so.
  - [ ] Decide whether imported operations require caller capability proof,
        callee capability proof, or both.
- [ ] Define capability exports.
  - [ ] Exported capabilities are authority names, not runtime tokens by
        default.
  - [ ] Imported capability aliases must preserve effect path and access mode.
  - [ ] Hierarchical capability coverage works across modules.
  - [ ] Narrow imported capabilities should remain narrow.
  - [ ] Reject broad capability re-export without a rationale.
- [ ] Define dependency effect propagation.
  - [ ] External dependency effects in a provider module must appear in exported
        operation contracts if the exported operation can trigger them.
  - [ ] Wrapper/facade modules may narrow or rename effects only with explicit
        metadata explaining the boundary.
  - [ ] Observability effects must cross module boundaries like other effects.
  - [ ] Network/file/database effects must never disappear through import.
- [ ] Add cross-module effect tests.
  - [ ] Imported operation with console effect.
  - [ ] Imported operation with filesystem effect.
  - [ ] Imported operation with HTTP response effect.
  - [ ] Imported operation with broad provider capability and narrow caller
        effect.
  - [ ] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
  - [ ] Re-exported broad capability warning.

### Dependency Fetching And Cache

- [ ] Define Go-style module fetching.
  - [ ] Add `sem get MODULE_PATH@VERSION_OR_REF`.
  - [ ] Support GitHub module paths.
  - [ ] Support generic Git URLs later without making GitHub special in the
        language grammar.
  - [ ] Support local path dependencies for development.
  - [ ] Support pinned tags.
  - [ ] Support pinned commits.
  - [ ] Reject floating branches in release builds unless explicitly allowed.
- [ ] Define `.semcache/`.
  - [ ] Store cloned dependencies outside source roots.
  - [x] Keep `.semcache/` ignored by git.
  - [ ] Support user-global cache later if useful.
  - [ ] Support project-local cache for reproducible experiments.
  - [ ] Do not modify cached dependency sources during normal builds.
- [ ] Define lockfile behavior without TOML.
  - [ ] Decide whether lock data lives in `sem.lock`, `build.lock.sem`, or
        another SemanticScript tape file.
  - [ ] Record module path.
  - [ ] Record requested version/ref.
  - [ ] Record resolved commit.
  - [ ] Record checksum.
  - [ ] Record dependency module root.
  - [ ] Record transitive dependencies.
  - [ ] Make normal builds use locked versions without hitting the network.
- [ ] Implement dependency update flows.
  - [ ] `sem get` adds or updates dependency rows in `build.sem`.
  - [ ] `sem mod tidy` removes unused dependency rows.
  - [ ] `sem update ALIAS` updates one dependency.
  - [ ] `sem update` updates all dependencies within allowed constraints.
  - [ ] `sem vendor` copies dependencies into a vendored tree if that workflow
        is later accepted.
- [ ] Add dependency fetch tests.
  - [ ] Local path dependency.
  - [ ] GitHub tag dependency.
  - [ ] GitHub commit dependency.
  - [ ] Missing repository diagnostic.
  - [ ] Missing `build.sem` diagnostic.
  - [ ] Missing module contract rows in `build.sem` diagnostic.
  - [ ] Lockfile prevents network access during build.
  - [ ] Cache corruption diagnostic.

### Tests And `*.test.sem`

- [ ] Define colocated test file behavior.
  - [x] `*.test.sem` belongs to the same folder module as sibling source.
  - [ ] Test files may access public exports by default.
  - [ ] Decide whether tests may access private symbols in their same folder
        module.
  - [ ] Reject test files that declare a different module path.
  - [x] Exclude `*.test.sem` from normal module-source selection.
  - [ ] Include `*.test.sem` in `sem test`.
- [ ] Define test import behavior.
  - [ ] Tests can import sibling folder modules through normal imports.
  - [ ] Tests can import dependency modules declared in `build.sem`.
  - [ ] Tests can define test-only helper operations.
  - [ ] Test-only helpers are not exported into production contract tape.
- [ ] Add test discovery diagnostics.
  - [ ] Test file without sibling module.
  - [ ] Test file outside `sourceRoot`.
  - [ ] Test file with wrong module declaration.
  - [ ] Test file accidentally included in production build.
- [ ] Add test layout tests.
  - [ ] Sibling `foo.test.sem` happy path.
  - [ ] Nested module test happy path.
  - [ ] Private symbol access decision enforced.
  - [ ] Test-only helper excluded from exports.

### Migration From Current Import/Module Behavior

- [ ] Audit existing `module` rows.
  - [ ] List files with source-level `module` rows that should move to
        `build.sem`.
  - [ ] Identify modules that can become build-owned folder modules unchanged.
  - [ ] Identify samples needing a root `build.sem`.
  - [ ] Identify stdlib modules needing module contracts in `build.sem`.
- [ ] Audit existing `importModule` usage.
  - [ ] List current import paths.
  - [ ] Decide compatibility period for `importModule DOTTED.PATH [as ALIAS]`.
  - [ ] Add migration diagnostics that suggest the new form.
  - [ ] Avoid breaking current `.sscript` / `.sem` tests before migration is
        staged.
- [ ] Add compatibility rules.
  - [x] Single-file scripts can keep old import behavior temporarily.
  - [x] Project builds through `build.sem` use registered module resolution.
  - [ ] Linter can warn on old form before compiler rejects it.
  - [x] Docs clearly mark filesystem/std-lib fallback as compatibility behavior.
- [ ] Add migration tests.
  - [ ] Legacy single-file import still works during compatibility window.
  - [ ] New project import works.
  - [ ] Mixed old/new imports produce clear diagnostics.
  - [ ] Migration suggestions include exact replacement rows.

## P1 - Developer Tooling Roadmap For A Real Language

This section tracks the toolchain needed for SemanticScript to feel like a
complete language instead of a set of implementation scripts. These are not all
required for the scoped 1.0 release, but they should guide the post-1.0 tooling
order.

### `semfmt` Formatter

- [ ] Create a formatter entrypoint named `semfmt`.
  - [ ] Decide whether `semfmt` lives under `SemanticScript/tools/`,
        `SemanticScript/formatter/`, or as a `sem fmt` subcommand wrapper.
  - [ ] Add command help with examples for `.sscript` and `.sem` files.
  - [ ] Support formatting one file.
  - [ ] Support formatting multiple explicit files.
  - [ ] Support recursive project formatting with include/exclude globs.
  - [ ] Add `--check` mode for CI that exits non-zero on formatting drift.
  - [ ] Add `--diff` mode that prints a unified diff without writing files.
  - [ ] Add `--stdin-file-name` support for editor integrations.
- [ ] Make formatting parser-aware instead of regex-only.
  - [ ] Reuse the compiler/linter tokenizer or extract a shared tokenizer.
  - [ ] Preserve comments exactly unless indentation is intentionally adjusted.
  - [ ] Preserve blank lines where they separate logical sections.
  - [ ] Preserve quoted strings and escape sequences byte-for-byte.
  - [ ] Preserve unknown/proposed verbs instead of deleting or rewriting them.
- [ ] Define canonical row layout rules.
  - [ ] Canonicalize one space between tokens.
  - [ ] Trim trailing whitespace.
  - [ ] Keep comments after code separated by at least two spaces if inline
        comments are allowed.
  - [ ] Keep top-level declaration rows unindented.
  - [ ] Decide whether operation body rows remain unindented or gain logical
        indentation in formatted output.
  - [ ] Define maximum line length and whether long strings are never wrapped.
  - [ ] Define how long metadata strings should be wrapped, if at all.
- [ ] Define canonical ordering rules where safe.
  - [ ] Decide whether formatter may reorder metadata rows.
  - [ ] If reordering is allowed, order operation metadata as
        `purpose`, `input`, `output`, `effect`, `useCapability`, warnings, then
        invariants.
  - [ ] Never reorder executable body rows unless a proof exists that behavior
        is unchanged.
  - [ ] Never reorder route rows unless route precedence rules make ordering
        irrelevant.
- [ ] Add formatter configuration.
  - [ ] Define formatter settings in `build.sem` or a future SemanticScript
        settings tape, not TOML.
  - [ ] Support line width.
  - [ ] Support newline mode.
  - [ ] Support quote-preservation only, not quote-style rewrites.
  - [ ] Document defaults as the canonical project style.
- [ ] Add formatter tests.
  - [ ] Golden-format tests for small syntax examples.
  - [ ] Golden-format tests for webserver apps.
  - [ ] Golden-format tests for comments and blank lines.
  - [ ] Golden-format tests for quoted strings with escaped characters.
  - [ ] Idempotence tests: formatting twice produces byte-identical output.
  - [ ] Safety tests: formatted source parses to the same high-level semantic
        tape as the original.
  - [ ] Fuzz tests for tokenizer/formatter round-tripping.
- [ ] Integrate formatter into editors and CI.
  - [ ] Add VS Code `DocumentFormattingEditProvider`.
  - [ ] Add format-on-save documentation.
  - [ ] Add CI `semfmt --check` once formatting is stable.
  - [ ] Add release checklist item requiring formatter clean output.

### `sem` Project Command Driver

- [ ] Create a single daily-use command named `sem`.
  - [ ] Decide implementation language for the first driver.
  - [ ] Make the driver work from PowerShell on Windows.
  - [ ] Make the driver work from POSIX shells.
  - [ ] Add `sem --version`.
  - [ ] Add `sem --help`.
  - [ ] Add useful non-zero exit codes for scripting.
- [ ] Wrap compiler commands.
- [x] Add `sem build`.
  - [ ] Add `sem run`.
  - [ ] Add `sem check` for parse, lint, and type/codegen validation.
  - [ ] Add `sem emit-ir`.
  - [ ] Add `sem clean` for ignored local build artifacts.
  - [ ] Pass through `--build-profile dev|prod`.
  - [ ] Pass through `--runtime-checks off|traps|panic`.
  - [ ] Pass through `--persist-llvm-ir auto|yes|no`.
  - [ ] Pass through `--opt-level`.
- [ ] Wrap quality tools.
  - [ ] Add `sem lint`.
  - [ ] Add `sem lint --engine semlint`.
  - [ ] Add `sem lint --engine semlint`.
  - [ ] Add `sem fmt`.
  - [ ] Add `sem fmt --check`.
  - [ ] Add `sem test`.
  - [ ] Add `sem doc`.
  - [ ] Add `sem explain`.
  - [ ] Add `sem bench`.
  - [ ] Add `sem doctor`.
- [ ] Add project discovery.
  - [ ] Discover the nearest `build.sem`.
  - [ ] Fall back to single-file mode when no build tape exists.
  - [ ] Resolve source roots from `build.sem`.
  - [ ] Resolve build output directories from `build.sem`.
  - [ ] Resolve default entrypoints from `build.sem`.
  - [ ] Resolve target runtime settings from `build.sem`.
- [ ] Add project templates.
  - [ ] Add `sem new console`.
  - [ ] Add `sem new web`.
  - [ ] Add `sem new library`.
  - [ ] Add `sem new package`.
  - [ ] Add template tests proving generated projects build.
- [ ] Add toolchain environment checks.
  - [ ] `sem doctor` checks Python version.
  - [ ] `sem doctor` checks `llvmlite`.
  - [ ] `sem doctor` checks clang or `SEMSC_CLANG`.
  - [ ] `sem doctor` checks Node.js when VS Code extension tooling is needed.
  - [ ] `sem doctor` checks native HTTP runtime build prerequisites.
  - [ ] `sem doctor` prints concrete fix commands where possible.
- [ ] Add driver tests.
  - [ ] Unit-test argument parsing.
  - [ ] Test single-file build.
  - [ ] Test build-tape-based build.
  - [ ] Test `sem check` failure reporting.
  - [ ] Test PowerShell examples.
  - [ ] Test POSIX examples in CI if a POSIX runner is available.

### `build.sem` Project Build Tape

- [ ] Define the project build tape schema.
  - [ ] Project name.
  - [ ] Project version.
  - [ ] License field.
  - [ ] Source roots.
  - [ ] Default entry operation.
  - [ ] Build profiles.
  - [ ] Runtime target.
  - [ ] Native HTTP settings.
  - [ ] Test roots.
  - [ ] Formatter settings.
  - [ ] Linter settings.
  - [ ] Documentation output settings.
- [ ] Implement build-tape parsing.
  - [ ] Add strict diagnostics for malformed project build rows.
  - [ ] Add strict diagnostics for unknown top-level keys.
  - [ ] Add strict diagnostics for missing required fields.
  - [ ] Add path normalization on Windows and POSIX.
  - [ ] Add tests for relative and absolute paths.
- [ ] Integrate project build tapes with existing tools.
- [x] `semsc.py` can accept a `build.sem`-driven build through `sem build`.
  - [ ] `semlint.py` can lint a `build.sem` project.
  - [ ] VS Code extension can discover project settings from `build.sem`.
  - [ ] Future language server can use `build.sem` as the workspace root.
- [ ] Document the project build tape.
  - [x] Add a minimal console app `build.sem` example.
  - [ ] Add a native webserver `build.sem` example.
  - [ ] Add a library/package `build.sem` example.
  - [ ] Add a schema reference table.

### `semls` Language Server

- [ ] Create a language server entrypoint named `semls`.
  - [ ] Decide whether to implement JSON-RPC directly or use an LSP library.
  - [ ] Define startup options.
  - [ ] Define workspace-root discovery through `build.sem`.
  - [ ] Support single-file mode.
  - [ ] Add structured logging for LSP failures.
- [ ] Move VS Code-only intelligence into reusable language services.
  - [ ] Extract tokenizer and symbol index into shared code.
  - [ ] Extract hover generation into shared code.
  - [ ] Extract completion data into shared code.
  - [ ] Extract diagnostics conversion into shared code.
  - [ ] Keep the VS Code extension as a thin client once `semls` is stable.
- [ ] Implement core LSP features.
  - [ ] `textDocument/didOpen`.
  - [ ] `textDocument/didChange`.
  - [ ] `textDocument/didSave`.
  - [ ] `textDocument/hover`.
  - [ ] `textDocument/definition`.
  - [ ] `textDocument/references`.
  - [ ] `textDocument/documentSymbol`.
  - [ ] `workspace/symbol`.
  - [ ] `textDocument/completion`.
  - [ ] `textDocument/semanticTokens/full`.
  - [ ] `textDocument/formatting` backed by `semfmt`.
  - [ ] `textDocument/codeAction`.
  - [ ] `textDocument/rename` after symbol resolution is reliable.
- [ ] Implement diagnostics.
  - [ ] Run parser diagnostics incrementally.
  - [ ] Run `semlint.py` or equivalent stable diagnostics.
  - [ ] Run `semlint.py` structured diagnostics.
  - [ ] Debounce diagnostics on type.
  - [ ] Cancel stale diagnostics for older document versions.
  - [ ] Map diagnostic codes to `sem explain` documentation.
  - [ ] Add quick fixes where the edit is obvious and low-risk.
- [ ] Implement project awareness.
  - [ ] Resolve imports.
  - [ ] Build a cross-file symbol index.
  - [ ] Detect duplicate exported names.
  - [ ] Detect ambiguous unqualified references.
  - [ ] Support go-to-definition across imported files.
  - [ ] Support find-references across imported files.
- [ ] Add language-server tests.
  - [ ] Protocol-level tests for initialize/shutdown.
  - [ ] Hover snapshot tests.
  - [ ] Completion snapshot tests.
  - [ ] Definition/reference tests.
  - [ ] Diagnostic debounce/cancellation tests.
  - [ ] Workspace import-resolution tests.

### `sem test` Test Runner

- [ ] Define first-class SemanticScript test conventions.
  - [ ] Decide test file naming rules.
  - [ ] Decide whether test operations use metadata or naming conventions.
  - [ ] Decide how fixtures are referenced.
  - [ ] Decide how expected failures are declared.
- [ ] Implement test discovery.
  - [ ] Discover tests from `build.sem` / `testPattern`.
  - [ ] Discover tests from default `tests/` roots.
  - [ ] Support explicit file selection.
  - [ ] Support explicit test name filtering.
  - [ ] Support tags.
- [ ] Support test kinds.
  - [ ] Parse-only tests.
  - [ ] Lint-clean tests.
  - [ ] Compile-success tests.
  - [ ] Compile-fail tests with expected diagnostic codes.
  - [ ] Runtime-success tests.
  - [ ] Runtime-fail tests with expected crash/error output.
  - [ ] Golden stdout tests.
  - [ ] Golden stderr tests.
  - [ ] HTTP route tests.
  - [ ] Multipart upload tests.
  - [ ] SSE response tests.
  - [ ] Timeout/metadata tests.
- [ ] Add test output formats.
  - [ ] Human-readable console output.
  - [ ] JSON output for agents and CI.
  - [ ] JUnit XML for CI systems.
  - [ ] Snapshot update mode for golden tests.
- [ ] Add test isolation.
  - [ ] Use temporary build directories.
  - [ ] Allocate non-conflicting local ports for web tests.
  - [ ] Kill child processes on timeout.
  - [ ] Clean generated executables and IR after each test unless debugging.
- [ ] Add test runner tests.
  - [ ] Test discovery.
  - [ ] Test success/failure exit codes.
  - [ ] Test compile-fail matching.
  - [ ] Test golden-output diff rendering.
  - [ ] Test webserver lifecycle cleanup.

### `semdoc` Documentation Generator

- [ ] Create a documentation generator entrypoint named `semdoc`.
  - [ ] Support `sem doc` as the primary user-facing wrapper.
  - [ ] Support Markdown output.
  - [ ] Support HTML output later if needed.
  - [ ] Support JSON output for agents.
- [ ] Extract source-level documentation.
  - [ ] Operations.
  - [ ] Inputs and outputs.
  - [ ] Effects.
  - [ ] Capabilities and authorities.
  - [ ] Records and fields.
  - [ ] Enums and error variants.
  - [ ] Web servers and route tables.
  - [ ] Route middleware and timeout metadata.
  - [ ] Warnings, invariants, security notes, and observability notes.
- [ ] Add cross-linking.
  - [ ] Link operation references to operation sections.
  - [ ] Link route handlers to operation sections.
  - [ ] Link capability uses to capability declarations.
  - [ ] Link diagnostic codes to `sem explain`.
- [ ] Add docs quality checks.
  - [ ] Warn when public operations lack `purpose`.
  - [ ] Warn when route handlers lack response behavior notes.
  - [ ] Warn when warnings/invariants reference missing operations or calls.
  - [ ] Warn when documented effects do not match declared effects.
- [ ] Add docs generator tests.
  - [ ] Snapshot generated docs for a console app.
  - [ ] Snapshot generated docs for a web app.
  - [ ] Snapshot generated docs for HTTP gauntlet.
  - [ ] Test broken references become diagnostics.

### `sem explain` Error Explainer

- [ ] Create an error explainer entrypoint.
  - [ ] Support `sem explain CODE`.
  - [ ] Support explaining compiler diagnostic codes.
  - [ ] Support explaining `semlint.py` rules.
  - [ ] Support explaining `semlint.py` diagnostic codes.
  - [ ] Support explaining runtime panic codes such as `SSRUN001`.
- [ ] Create a diagnostic knowledge base.
  - [ ] Store code title.
  - [ ] Store short explanation.
  - [ ] Store why agents usually trigger it.
  - [ ] Store common fixes.
  - [ ] Store bad/fixed source examples.
  - [ ] Store related spec/doc links.
  - [ ] Store severity and category.
- [ ] Integrate explain output into tools.
  - [ ] Compiler diagnostics include `Run: sem explain CODE`.
  - [ ] Linter diagnostics include explain links in JSON output.
  - [ ] VS Code hovers/code actions can open explain docs.
  - [ ] Language server diagnostics include `codeDescription` links.
- [ ] Add tests.
  - [ ] Every compiler diagnostic code has an explanation.
  - [ ] Every semlint diagnostic code has an explanation.
  - [ ] Examples in explanations parse or intentionally fail as documented.

### Trace, Crash, And Debug Tooling

- [ ] Define source-to-runtime trace metadata.
  - [ ] Map semantic tape rows to source file/line/column.
  - [ ] Map generated LLVM blocks back to operation and call names.
  - [ ] Map native runtime failures back to SemanticScript route/handler names.
- [ ] Add trace execution mode.
  - [ ] Add `sem run --trace`.
  - [ ] Add trace output for operation entry/exit.
  - [ ] Add trace output for call execution.
  - [ ] Add trace output for branch decisions.
  - [ ] Add trace output for returned values where safe.
  - [ ] Redact values from paths marked sensitive by future metadata.
- [ ] Add crash explanation mode.
  - [ ] Add `sem run --explain-crash`.
  - [ ] Capture runtime panic code.
  - [ ] Capture SemanticScript stack/operation context.
  - [ ] Capture direction message that hints at the likely fix.
  - [ ] Capture build profile and runtime-check mode.
  - [ ] Keep prod profile output minimal by default.
- [ ] Add IR inspection helpers.
  - [ ] Add `sem inspect-ir`.
  - [ ] Show the source operation that produced an IR function.
  - [ ] Show native ABI signatures for HTTP handlers.
  - [ ] Show linked runtime objects.
- [ ] Add minimal debugger plan.
  - [ ] Decide whether to integrate with LLDB/GDB or keep source-level traces
        only for the first release.
  - [ ] Define breakpoint syntax if source-level breakpoints are added.
  - [ ] Define watch/expression support only after value representation is
        stable.

### REPL And Scratch Runner

- [ ] Decide whether a REPL fits SemanticScript's file/operation model.
  - [ ] If yes, define how scratch operations are wrapped.
  - [ ] If no, document `sem scratch` as the supported interactive workflow.
- [ ] Add `sem scratch`.
  - [ ] Create a temporary source file.
  - [ ] Insert a minimal operation scaffold.
  - [ ] Compile/run the scratch file.
  - [ ] Preserve scratch files on failure for debugging.
- [ ] Add `sem run-snippet`.
  - [ ] Accept source from stdin.
  - [ ] Accept a named entry operation.
  - [ ] Print compiler/linter diagnostics with source snippets.
- [ ] Add tests for scratch/snippet workflows.

### `sem bench` Benchmark Tool

- [ ] Create a benchmark entrypoint.
  - [ ] Support `sem bench`.
  - [ ] Support `build.sem`-discovered benchmarks.
  - [ ] Support explicit benchmark files.
  - [ ] Support warmup iterations.
  - [ ] Support measured iterations.
  - [ ] Support JSON output.
- [ ] Track benchmark dimensions.
  - [ ] Compile time.
  - [ ] Native executable size.
  - [ ] Runtime duration.
  - [ ] Peak memory if practical.
  - [ ] HTTP requests per second for webserver benchmarks.
  - [ ] Startup latency for native webserver binaries.
- [ ] Add baseline benchmarks.
  - [ ] Console hello world.
  - [ ] Numeric loop.
  - [ ] String scanning.
  - [ ] JSON encode/decode once implemented.
  - [ ] Todo web hello route.
  - [ ] HTTP API gauntlet route matrix.
- [ ] Add benchmark guardrails.
  - [ ] Store baselines outside normal source unless intentionally committed.
  - [ ] Add tolerance thresholds.
  - [ ] Avoid flaky wall-clock assertions in normal CI.
  - [ ] Provide local comparison reports.

### Fuzzing And Property Testing

- [ ] Add parser fuzzing.
  - [ ] Fuzz token streams.
  - [ ] Fuzz quoted strings and escape sequences.
  - [ ] Fuzz comments and blank lines.
  - [ ] Assert parser never crashes.
  - [ ] Assert diagnostics stay source-located.
- [ ] Add formatter fuzzing.
  - [ ] Fuzz format round-trips.
  - [ ] Assert formatter is idempotent.
  - [ ] Assert formatted source still parses.
- [ ] Add linter fuzzing.
  - [ ] Fuzz operation/call graphs.
  - [ ] Fuzz route metadata.
  - [ ] Fuzz capability/effect paths.
  - [ ] Assert linter emits bounded diagnostics without exceptions.
- [ ] Add compiler fuzzing.
  - [ ] Generate small well-typed programs.
  - [ ] Generate expected-invalid programs.
  - [ ] Assert compiler never throws uncaught Python exceptions.
  - [ ] Assert invalid programs produce structured diagnostics.
- [ ] Add HTTP runtime fuzzing.
  - [ ] Fuzz request lines.
  - [ ] Fuzz headers.
  - [ ] Fuzz query strings.
  - [ ] Fuzz multipart boundaries.
  - [ ] Fuzz large bodies within configured limits.
  - [ ] Assert runtime returns controlled 4xx/5xx responses instead of
        crashing.
- [ ] Integrate fuzzing carefully.
  - [ ] Add short deterministic fuzz smoke tests to CI.
  - [ ] Add long fuzz jobs for manual/nightly runs.
  - [ ] Persist failure seeds.
  - [ ] Add minimization instructions.

### Package, Module, And Registry Tooling

- [ ] Define package layout conventions.
  - [ ] Source root.
  - [ ] Test root.
  - [ ] Generated output root.
  - [ ] Documentation output root.
  - [ ] Native runtime configuration root.
- [ ] Define dependency syntax in `build.sem` or a SemanticScript lock/build
      tape.
  - [ ] Local path dependencies.
  - [ ] Git dependencies.
  - [ ] Versioned registry dependencies later.
  - [ ] Dependency feature flags later if needed.
- [ ] Add dependency resolution.
  - [ ] Lockfile design.
  - [ ] Reproducible dependency graph.
  - [ ] Clear diagnostics for missing dependencies.
  - [ ] Clear diagnostics for conflicting versions.
- [ ] Add package validation.
  - [ ] License present.
  - [ ] README present.
  - [ ] Public operations documented.
  - [ ] Tests pass.
  - [ ] No generated artifacts included.
- [ ] Defer registry implementation until local/package workflow is stable.
  - [ ] Document registry requirements.
  - [ ] Define package signing or checksum expectations.
  - [ ] Define ownership/namespace rules.

### Installer And Version Manager

- [ ] Decide install strategy.
  - [ ] Single archive download.
  - [ ] Python package wrapper.
  - [ ] Native launcher.
  - [ ] Platform package managers later.
- [ ] Create `semup` or equivalent version manager plan.
  - [ ] Install a named SemanticScript version.
  - [ ] Update to latest stable.
  - [ ] Select active version per user.
  - [ ] Select active version per project.
  - [ ] Print installed versions.
- [ ] Add Windows support.
  - [ ] PowerShell installer script.
  - [ ] PATH setup instructions.
  - [ ] Toolchain detection.
  - [ ] Uninstall instructions.
- [ ] Add POSIX support.
  - [ ] Shell installer script.
  - [ ] PATH setup instructions.
  - [ ] Toolchain detection.
  - [ ] Uninstall instructions.
- [ ] Add release artifact checks.
  - [ ] Checksums.
  - [ ] Signature plan if needed.
  - [ ] Smoke test installed `sem`.
  - [ ] Smoke test installed VS Code extension package separately.

### Agent-Focused Tooling

- [ ] Add machine-readable project context output.
  - [ ] `sem context --json` summarizes project roots, entrypoints, tools, and
        supported syntax.
  - [ ] Include compiler version.
  - [ ] Include linter version.
  - [ ] Include runtime feature flags.
  - [ ] Include known xfail/deferred features.
- [ ] Add machine-readable symbol graph output.
  - [ ] `sem symbols --json`.
  - [ ] Include operations, calls, inputs, outputs, effects, and routes.
  - [ ] Include source locations.
  - [ ] Include unresolved references.
- [ ] Add agent-safe fix suggestions.
  - [ ] Diagnostics should include minimal fix direction.
  - [ ] Diagnostics should distinguish safe automatic edits from human review
        edits.
  - [ ] Avoid suggestions that require broad refactors unless explicitly marked.
- [ ] Add docs for agent workflows.
  - [ ] How to run the fast validation set.
  - [ ] How to inspect route/effect/capability graphs.
  - [ ] How to safely update generated docs.
  - [ ] How to avoid touching ignored build artifacts.

### Release, Packaging, And Repository Policy

- [x] Add MIT root `LICENSE`.
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
  - [x] CI workflow or script for semlint tests.
  - [x] CI workflow or script for extension syntax check.
  - [x] CI workflow or script for parity/feature coverage once green.
- [x] Add release process documentation.
  - [x] Required local commands.
  - [x] Artifact cleanup rules.
  - [x] Version bump rules.
  - [x] VSIX packaging rule.
- [x] Decide license before publishing.
  - [x] Use MIT for first-party source, docs, samples, and tooling.
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
