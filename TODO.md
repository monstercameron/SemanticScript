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

## P1 - Strict Syntax Hardening

This section turns the strict-syntax research in
`docs/language/strict-syntax-research.md` into implementation-sized tasks. The
goal is to make recurring bug classes fail in the compiler itself, without
requiring a separate linter invocation.

### Strict Executable Mode

- [ ] Decide the source row for strict mode.
  - [x] Prefer `languageMode strictExecutable` unless a better existing
        versioning row should own the setting.
  - [x] Decide whether strict mode belongs in source files, `build.sem`, or
        both.
  - [ ] Decide whether strict mode is inherited by imported modules.
  - [ ] Decide whether `languageVersion PROJECT "1.0"` implies strict mode in
        the future.
  - [x] Document the initial rollout as opt-in, not default.
- [x] Add parser support for `languageMode NAME`.
  - [x] Store language modes on `Program`.
  - [x] Reject duplicate incompatible language modes.
  - [x] Accept `strictExecutable`.
  - [x] Accept `refinedSyntax` for research files that intentionally use
        metadata-only rows.
  - [x] Reject unknown language-mode values with a parse diagnostic.
  - [x] Add syntax inventory rows for `languageMode strictExecutable`.
  - [x] Add syntax inventory rows for `languageMode refinedSyntax`.
- [ ] Close the executable grammar when strict mode is active.
  - [x] Reject unknown lowercase top-level verbs in strict mode.
  - [x] Reject unknown lowercase operation-body verbs in strict mode.
  - [ ] Keep typed comments and group anchors parseable in strict mode.
  - [ ] Keep explicitly documented metadata-only rows parseable in strict
        mode only when they are in the allowed strict metadata set.
  - [x] Keep permissive parsing for non-strict refined examples.
  - [x] Add a clear diagnostic that tells users to add
        `languageMode refinedSyntax` only for research/metadata files.
- [x] Add strict-mode compiler tests.
  - [x] Negative test: misspelled lowercase top-level verb fails without
        `--lint`.
  - [x] Negative test: misspelled lowercase operation-body verb fails without
        `--lint`.
  - [x] Positive test: documented strict metadata row parses.
  - [x] Positive test: `languageMode refinedSyntax` preserves permissive
        metadata parsing.

### Shared Contract Tables

- [ ] Extract built-in call target signatures into a shared module.
  - [ ] Include math targets.
  - [ ] Include pointer targets.
  - [ ] Include C/libc targets or references to `libc_registry.py`.
  - [ ] Include native HTTP targets.
  - [ ] Include native GUI targets.
  - [ ] Include SQLite targets.
  - [ ] Include JSON runtime targets.
  - [ ] Make both `semsc.py` and `semlint.py` consume the same source of
        truth where practical.
- [ ] Add a shared fallibility table.
  - [ ] Mark heap allocation calls as fallible.
  - [ ] Mark file-open calls as fallible.
  - [ ] Mark native HTTP response writers as fallible.
  - [ ] Mark SQLite open/exec/prepare/bind/step/reset/finalize/close calls as
        fallible.
  - [ ] Mark checked arithmetic calls as fallible.
  - [ ] Mark infallible math calls as infallible.
  - [ ] Mark explicit status-return calls whose failures are status values,
        not `Result`, so they can require `bind` or `ignoreValue`.
- [ ] Add a shared ownership table.
  - [ ] Mark `c.malloc`, `c.calloc`, and successful `c.realloc` outputs as
        owned heap buffers.
  - [ ] Mark `sqlite.openDatabase` success output as an owned SQLite database.
  - [ ] Mark `sqlite.prepareStatement` success output as an owned SQLite
        statement.
  - [ ] Mark cleanup targets for each owned resource.
  - [ ] Record whether cleanup is allowed by explicit call, `defer`, or both.
- [ ] Add drift tests for shared tables.
  - [ ] Verify linter and compiler agree on built-in signatures.
  - [ ] Verify linter and compiler agree on fallible targets.
  - [ ] Verify linter and compiler agree on owned-resource producers.

### Checked Fallible Calls

- [ ] Design the checked call syntax.
  - [ ] Confirm `runChecked CALL ok VALUE TYPE error ERROR TYPE else LABEL`
        is the preferred shape.
  - [ ] Decide whether `runChecked` should create the ok/error binds itself.
  - [ ] Decide whether `runChecked` replaces or coexists with `run`,
        `bindOk`, `bindError`, and `branchIfError`.
  - [ ] Decide whether `runChecked` may target calls with no success value.
  - [ ] Decide whether `runChecked` may target status-return calls.
  - [ ] Decide whether `ignoreOk` is still legal for checked calls.
- [x] Add parser support for `runChecked`.
  - [x] Add `runChecked` to body verb tables.
  - [x] Validate minimum arity.
  - [x] Validate keyword positions such as `ok`, `error`, and `else`.
  - [x] Preserve source line information for generated diagnostics.
- [ ] Add compiler validation for fallible targets in strict mode.
  - [ ] Reject plain `run` for known fallible targets in strict mode.
  - [x] Reject plain `run` for Result-shaped SQLite prepare in strict mode.
  - [ ] Require `runChecked` or an explicitly accepted legacy checked pattern
        for every known fallible target.
  - [x] Accept the legacy checked pattern for Result-shaped fallible calls.
  - [ ] Reject unchecked explicit-disposition targets such as heap allocation
        and native HTTP response writers.
  - [ ] Reject `bindError` without a corresponding branch in strict mode.
  - [ ] Reject `branchIfError` on targets that the shared table marks
        infallible.
  - [ ] Reject fallible calls whose success value is used before the error
        branch is established.
  - [ ] Ensure diagnostics point at the `run` line and the original `call`
        line.
- [x] Lower `runChecked`.
  - [x] Emit the same call lowering as `run`.
  - [x] Bind the success value on the fallthrough path.
  - [x] Bind the error value on the error path.
  - [x] Emit the branch to the declared failure label.
  - [x] Preserve existing `defer` behavior on both paths.
- [ ] Migrate app examples after the syntax exists.
  - [ ] Convert `app/todo-web-pro` heap allocations to `runChecked`.
  - [ ] Convert `app/todo-web-pro` SQLite bootstrap calls to `runChecked`.
  - [ ] Convert native HTTP response writes in sample apps to `runChecked`
        where appropriate.
  - [ ] Keep legacy examples only where they deliberately document old syntax.
- [ ] Add compiler tests for checked calls.
  - [x] Negative test: `c.malloc` with plain `run` fails in strict mode.
  - [x] Negative test: SQLite prepare with plain `run` fails in strict mode.
  - [ ] Negative test: HTTP response write with ignored status fails in strict
        mode.
  - [x] Positive test: `runChecked` heap allocation compiles.
  - [ ] Positive test: `runChecked` SQLite prepare compiles.
  - [ ] Positive test: `runChecked` HTTP response write compiles.

### Owned Resources And Cleanup

- [ ] Design owned binding syntax.
  - [ ] Confirm `bindOwned VALUE TYPE CALL cleanup TARGET` for infallible
        owned producers.
  - [ ] Confirm `bindOkOwned VALUE TYPE CALL cleanup TARGET` for fallible
        owned producers.
  - [ ] Decide whether cleanup args are implicit from the owned value or
        explicitly listed.
  - [ ] Decide how ownership transfer is represented.
  - [ ] Decide whether `returnOwned` or `transferOwned` is needed.
  - [ ] Decide how owned values interact with `defer`.
- [ ] Add parser support for owned binding rows.
  - [ ] Add `bindOwned`.
  - [ ] Add `bindOkOwned`.
  - [ ] Validate `cleanup TARGET` arity.
  - [ ] Validate that the call target is in the ownership table.
  - [ ] Validate that the cleanup target matches the owned resource kind.
- [x] Add conservative compiler ownership validation.
  - [x] Reject returning from an operation while an owned value is live.
  - [x] Reject branching to a label that can return while an owned value is
        live and unreleased.
  - [x] Treat a matching explicit cleanup call as release.
  - [x] Treat a matching lowered `defer` as release where the backend actually
        emits it on that path.
  - [ ] Reject cleanup calls that consume a value after ownership transfer.
  - [x] Reject double cleanup of the same owned value in strict mode.
- [ ] Add SQLite ownership coverage.
  - [x] Model `sqlite.openDatabase` as producing owned `SqliteDatabase`.
  - [x] Model `sqlite.closeDatabase` as releasing `SqliteDatabase`.
  - [x] Model `sqlite.prepareStatement` as producing owned `SqliteStatement`.
  - [x] Model `sqlite.finalizeStatement` as releasing `SqliteStatement`.
  - [x] Check schema/bootstrap failure paths after database acquisition.
  - [x] Check statement failure paths after prepare succeeds.
- [ ] Add C heap ownership coverage.
  - [x] Model `c.malloc` as producing owned heap memory.
  - [x] Model `c.calloc` as producing owned heap memory.
  - [x] Model successful `c.realloc` as producing owned heap memory.
  - [x] Model `c.free` as releasing heap memory.
  - [x] Check return paths after heap acquisition.
  - [x] Check failure paths between heap acquisition and cleanup.
- [ ] Add ownership tests.
  - [x] Negative test: `sqlite.openDatabase` followed by schema failure
        without close fails in strict mode.
  - [x] Negative test: `sqlite.prepareStatement` without finalize fails in
        strict mode.
  - [x] Negative test: `c.malloc` without `c.free` fails in strict mode.
  - [x] Negative test: double `c.free` fails in strict mode.
  - [x] Positive test: explicit cleanup label compiles.
  - [x] Positive test: lowered `defer` cleanup compiles when supported.

### Nullable And Non-Null Values

- [ ] Add nullable ABI aliases.
  - [ ] Add `NullableCNullTerminatedByteString`.
  - [ ] Add `NullableCOpaqueMemoryAddress`.
  - [ ] Decide whether nullable aliases are first-class type constructors or
        named aliases only.
  - [ ] Document which built-in call targets can return nullable values.
- [ ] Update native HTTP request-reader contracts.
  - [ ] Mark `http.requestHeader` as returning nullable text.
  - [ ] Mark `http.requestQueryParam` as returning nullable text.
  - [ ] Mark `http.requestBodyText` as nullable if absent body remains a
        possible runtime result.
  - [ ] Mark multipart part text readers as nullable.
  - [ ] Mark multipart part bytes readers as nullable.
  - [ ] Keep `http.requestMethod` and `http.requestPath` non-null.
- [ ] Add non-null refinement syntax.
  - [ ] Add `requireNonNull OUT TYPE INPUT else LABEL`.
  - [ ] Decide whether the syntax should include an error binding.
  - [ ] Decide whether `requireNonNull` is allowed for all nullable pointer
        types or only text/body types.
  - [ ] Lower `requireNonNull` to `pointer.isNull` plus branch.
  - [ ] Bind the non-null value only on the success path.
- [ ] Enforce non-null response writer inputs.
  - [ ] Require `http.responseText` body to be non-null text.
  - [ ] Require `http.responseSseEvent` event and data to be non-null text.
  - [ ] Require `http.responseBytes` body to be non-null bytes when length is
        non-zero.
  - [ ] Reject direct nullable request-reader outputs passed to response
        writers.
  - [ ] Reject wrappers that erase nullable input without refinement.
- [ ] Add nullable tests.
  - [ ] Negative test: nullable request body passed directly to
        `http.responseText` fails.
  - [ ] Negative test: nullable header passed directly to `http.responseText`
        fails.
  - [ ] Positive test: `requireNonNull` then response write compiles.
  - [ ] Positive test: missing nullable value branches to explicit 400/404
        response path.

### Response Forwarding Contracts

- [ ] Decide final forwarding syntax.
  - [ ] Consider extending `input OP NAME TYPE forwardTo TARGET.ARG`.
  - [ ] Consider adding `forwardInput OP NAME to TARGET.ARG`.
  - [ ] Decide whether existing `responseBodyForwarder OP NAME` remains as a
        compatibility alias.
  - [ ] Decide whether forwarding contracts are required only in strict mode
        or always for response wrappers.
- [ ] Add parser support for the final forwarding contract.
  - [ ] Validate that the owning operation exists.
  - [ ] Validate that the input exists.
  - [ ] Validate that the target call arg is a known response-body slot.
  - [ ] Store forwarding facts on the operation contract.
- [ ] Add compiler validation for response wrappers.
  - [ ] Detect operations that pass an input directly to `http.responseText`
        body.
  - [ ] Detect operations that pass an input directly to `http.responseBytes`
        body.
  - [ ] Detect operations that pass an input directly to
        `http.responseSseEvent` event or data.
  - [ ] Reject missing forwarding contracts in strict mode.
  - [ ] Propagate nullable-body checks through forwarding contracts.
  - [ ] Propagate trust-boundary checks through forwarding contracts where
        available.
- [ ] Add forwarding tests.
  - [ ] Negative test: wrapper forwards response body without contract.
  - [ ] Negative test: wrapper declares wrong forwarded input.
  - [ ] Positive test: wrapper declares forwarding contract and compiles.
  - [ ] Positive test: transitive nullable body still requires
        `requireNonNull`.

### Capacity-Bounded Mutations

- [ ] Replace ambiguous row-count mutation contracts.
  - [ ] Identify all fixed-capacity row/list mutators in apps and stdlib.
  - [ ] Decide whether they return `Result RowCount RowCapacityError`.
  - [ ] Decide whether they return a closed `RowMutationStatus` enum plus
        output row count.
  - [ ] Decide whether unchanged row count is ever a valid success result.
  - [ ] Update syntax docs for capacity-bounded mutation contracts.
- [ ] Add compiler checks for strict capacity mutators.
  - [ ] Reject raw row-count outputs from operations marked as
        capacity-bounded mutators in strict mode.
  - [ ] Require call sites to branch on `Result` error or status enum before
        cursor movement.
  - [ ] Require dirty-state mutation only on the applied branch.
  - [ ] Require cursor movement only on the applied branch.
- [ ] Migrate `app/Kilo_port`.
  - [ ] Convert `insertEmptyRowAt` to the selected strict result shape.
  - [ ] Convert `splitRowAt` to the selected strict result shape.
  - [ ] Update caller branches to use the new result/status.
  - [ ] Keep the existing linter rule as a migration warning for non-strict
        code.
- [ ] Add capacity-mutation tests.
  - [ ] Negative test: unchecked raw row count fails in strict mode.
  - [ ] Negative test: cursor moves before capacity branch fails.
  - [ ] Negative test: dirty flag set before capacity branch fails.
  - [ ] Positive test: full-buffer branch returns without cursor movement.
  - [ ] Positive test: applied branch updates cursor and dirty state.

### GUI Event Mutation Boundaries

- [ ] Define strict GUI effect-conflict rules.
  - [ ] Treat `read gui.control.listBox.selection` plus
        `write gui.control.listBox.items` as conflicting in one event handler.
  - [ ] Decide whether the conflict applies to all list boxes or only the same
        list box when handle identity can be tracked.
  - [ ] Decide whether setup/build operations are exempt.
  - [ ] Decide whether a specific opt-in mode such as
        `operationMode reconcileListItems` is allowed.
- [ ] Add compiler validation for GUI handlers.
  - [ ] Identify operations registered via `gui.controlOnEvent`.
  - [ ] Read declared effects on those handler operations.
  - [ ] Reject conflicting selection-read/list-item-write effects in strict
        mode.
  - [ ] Reject direct `gui.listBoxSelectedIndex` and
        `gui.listBoxAppendItem` calls in one handler when effects are missing
        or insufficient.
  - [ ] Preserve the linter rule for non-strict code.
- [ ] Add GUI boundary tests.
  - [ ] Negative test: complete-selected handler also appends list item.
  - [ ] Negative test: handler omits effects but calls both targets.
  - [ ] Positive test: setup handler appends items without selection read.
  - [ ] Positive test: selection handler updates status text only.
  - [ ] Positive test: explicit reconciliation mode compiles if the mode is
        accepted.

### Explicit ABI Conversions

- [ ] Define strict conversion policy.
  - [ ] Require explicit numeric conversions before width changes in strict
        mode.
  - [ ] Require explicit pointer conversions before pointer/int crossings in
        strict mode.
  - [ ] Decide which existing ABI coercions remain allowed for opaque runtime
        handles.
  - [ ] Decide whether return-position coercions are rejected or only warned
        during migration.
- [ ] Remove implicit conversions in strict mode.
  - [ ] Reject `CSignedInt32` passed to `math.addI64`.
  - [ ] Reject `CSignedInt32` passed to C varargs expecting a 64-bit format
        unless explicitly widened.
  - [ ] Reject GUI i64 values passed to i32 GUI args unless explicitly
        narrowed.
  - [ ] Reject pointer values passed through integer slots without explicit
        conversion.
  - [ ] Reject integer values passed to pointer args except documented null
        constants.
- [ ] Add conversion helper targets where missing.
  - [ ] Ensure signed i32 to signed i64 conversion is available.
  - [ ] Ensure signed i64 to signed i32 conversion is available.
  - [ ] Decide whether unsigned conversions need separate targets.
  - [ ] Decide whether pointer-to-int and int-to-pointer conversions should be
        named language operations or forbidden outside runtime code.
- [ ] Add explicit conversion tests.
  - [ ] Negative test: `snprintf` byte count added to i64 cursor without
        widening fails.
  - [ ] Positive test: widened `snprintf` byte count compiles.
  - [ ] Negative test: GUI i64 dimension passed to i32 arg fails in strict
        mode.
  - [ ] Positive test: explicit narrowing compiles when allowed.
  - [ ] Negative test: pointer/int crossing fails without explicit conversion.

### Web Route And Middleware Schemas

- [ ] Move route method validation into the compiler.
  - [x] Reject unsupported route methods without requiring `semlint`.
  - [x] Keep the allowed method set in one shared table.
  - [x] Include `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, and
        `OPTIONS`.
  - [ ] Decide whether lowercase source methods normalize or fail.
  - [x] Add diagnostics that point to the `route` row.
- [ ] Move middleware ABI validation into the compiler.
  - [x] Require middleware output `MiddlewareControl`.
  - [x] Reject bare `CSignedInt32` middleware output in strict mode.
  - [x] Require middleware handler input names and types to match the native
        ABI.
  - [ ] Validate short-circuit response expectations where possible.
- [ ] Move route handler naming/type validation earlier.
  - [x] Require route handler input names `request` and `response` in strict
        mode.
  - [x] Require route handler input types `HttpRequest` and `HttpResponse`.
  - [ ] Require route handler output `CSignedInt32` or the future strict HTTP
        result type if introduced.
  - [ ] Point diagnostics to both the `route` row and handler operation
        header.
- [ ] Enforce route coverage contracts.
  - [ ] Require timeout coverage for each route unless an opt-out row exists.
  - [ ] Require middleware coverage for each route unless an opt-out row
        exists.
  - [ ] Reject malformed opt-out rows in strict mode.
  - [ ] Decide whether coverage checks are target-specific to webserver builds
        or always active when `webServer` rows exist.
- [ ] Add web schema tests.
  - [x] Negative test: invalid method fails without `--lint`.
  - [x] Negative test: middleware returns bare `CSignedInt32`.
  - [x] Negative test: route handler has wrong input names.
  - [ ] Negative test: route missing timeout without opt-out.
  - [x] Positive test: valid middleware and handler shape compiles.
  - [ ] Positive test: explicit timeout/middleware opt-outs compile.

### Documentation And Tooling Follow-through

- [ ] Update language docs after each strict syntax change.
  - [x] Update `SYNTAX.md`.
  - [ ] Update `docs/language/lexical-model.md`.
  - [x] Update `docs/language/operations-dataflow.md`.
  - [ ] Update `docs/language/errors-effects-capabilities.md`.
  - [ ] Update `docs/language/memory-state.md`.
  - [x] Update `docs/language/native-http-api.md`.
  - [x] Update `docs/optimization-guide.md`.
- [x] Update toolchain docs.
  - [x] Document strict mode in `docs/toolchain/compiler.md`.
  - [x] Document which linter rules graduated to compiler errors.
  - [x] Document migration commands and expected diagnostics.
  - [x] Update agent workflow docs so agents run compiler negative tests, not
        only semlint.
- [ ] Update linter behavior after compiler hardening.
  - [ ] Keep linter rules for non-strict source.
  - [ ] Avoid duplicate diagnostics when the compiler already blocks the same
        strict-mode source.
  - [ ] Add fix candidates that migrate legacy patterns to strict syntax.
  - [ ] Keep aggressive targeted rules for app review and editor feedback.
- [ ] Update VS Code tooling.
  - [x] Add highlighting for `languageMode`.
  - [ ] Add highlighting for `runChecked`.
  - [ ] Add highlighting for `bindOwned` and `bindOkOwned`.
  - [ ] Add highlighting for `requireNonNull`.
  - [ ] Add highlighting for the final response-forwarding syntax.
  - [ ] Add hover docs for each new strict syntax row.
- [ ] Add migration coverage.
  - [ ] Add strict-mode parse/build coverage for at least one console app.
  - [ ] Add strict-mode parse/build coverage for one webserver app.
  - [ ] Add strict-mode parse/build coverage for one GUI app if GUI remains in
        scope.
  - [ ] Add strict-mode parse/build coverage for one SQLite-using app.
  - [ ] Add a non-strict compatibility test so existing refined examples still
        parse.

## P1 - Declarative Windows GUI Target

This section tracks the declarative Windows desktop GUI surface. The design
goal is an English-aligned application graph in source, with Win32 handles,
message loops, `HWND`, `WPARAM`, and `LPARAM` hidden behind a native runtime
adapter the same way `HttpRequest` / `HttpResponse` hide HTTP runtime state.

Boundary decision after implementation review: keep `semsc.py` as a thin
bridge. `standard.gui` owns public GUI vocabulary, aliases, capabilities,
closed token sets, and semantic contracts; semlint owns rich misuse
diagnostics; the native GUI runtime owns platform behavior. The compiler may
accept `targetRuntime windowsGui`, lower explicit `gui.*` calls from ordinary
operation bodies, and link the native adapter. It must not build GUI
application graphs from custom top-level GUI keywords.

Design pivot: the row-centric `guiApplication` / `guiWindow` / `guiButton`
checklists below are retained as historical design notes only. The committed
surface is now `entry console main` plus `standard.gui` function calls.

### Completed MVP

- [x] Added `targetRuntime PROJECT windowsGui` to compiler build-tape
      validation.
- [x] Added `targetRuntime PROJECT windowsGui` to semlint build-tape
      validation.
- [x] Kept `entry windowsGui` out of the first committed executable surface.
- [x] Converted `app/hello-gui` to `entry console main` plus standard
      `operation` / `call` / `arg` / `run` syntax.
- [x] Added `standard.gui` as the canonical contract module.
- [x] Added GUI type aliases, enums, capabilities, token constants, and runtime
      target constants to `std/gui/main.sem`.
- [x] Added lightweight GUI awareness to semlint and VS Code syntax tooling.
- [x] Added a native Win32 GUI runtime adapter with a backend-neutral
      `ss_gui_*` ABI.
- [x] Added the compiler link hook for the native GUI adapter.
- [x] Added a minimal `app/hello-gui` sample.
- [x] Built `app/hello-gui/build/hello_gui.exe`.
- [x] Verified the executable renders a Windows top-level window titled
      `Hello GUI` and exits `0` after the window is closed.

### GUI Target And Entry Model

- [x] Add `target windowsGui` to the syntax inventory.
- [x] Add `targetRuntime PROJECT windowsGui` to the build-tape enum.
- [x] Keep `entry windowsGui OPERATION` out of the committed surface for the
      first version.
- [x] Document that `target windowsGui` selects the GUI link/runtime bridge
      while source still declares a normal entry operation.
- [x] Reject no-entry `target windowsGui` codegen with guidance to use
      `entry console main` and `gui.*` calls.
- [ ] Reject `entry windowsGui ...` with a diagnostic that points users to
      `entry console main` and `gui.applicationRun`.
- [x] Allow `targetRuntime windowsGui` build tapes that declare
      `entry console`.
- [ ] Decide whether `target windowsGui` may coexist with `target console` in
      one source, or reject mixed executable targets.
- [x] Define that closing the `guiApplicationMainWindow` ends the GUI message
      loop by default.
- [ ] Define how `guiApplicationOnExit` runs after the message loop exits.
- [ ] Define whether `guiApplicationOnExit` may cancel process exit or is
      cleanup-only.
- [x] Define default exit status when the main window closes cleanly.
- [ ] Define exit status behavior when a GUI event handler returns non-zero.
- [x] Add `windowsGui` support to compiler build-tape validation.
- [x] Add `windowsGui` support to standalone linter build-tape validation.

### Committed Function Surface Follow-ups

- [x] Move executable GUI construction to `standard.gui` function targets.
- [x] Lower `gui.applicationCreate`, `gui.windowCreate`,
      `gui.textLabelCreate`, `gui.textBoxCreate`, `gui.buttonCreate`,
      `gui.listBoxCreate`, `gui.windowAddControl`,
      `gui.applicationSetMainWindow`, and `gui.applicationRun`.
- [x] Keep GUI source on normal `operation` / `call` / `arg` / `run` syntax.
- [x] Remove compiler code that discovers and lowers `guiApplication` /
      `guiWindow` metadata graphs.
- [x] Treat GUI keyword rows as non-standard in semlint.
- [ ] Add standard-library wrappers for platform-neutral layout policies before
      adding Linux/macOS backends.
- [ ] Add event registration functions in `standard.gui` before adding handler
      dispatch.
- [ ] Add accessibility and sizing helper functions in `standard.gui` instead
      of adding new parser verbs.

### Syntax Naming And Shape

Resolution: the committed executable GUI surface is `entry console main` plus
`standard.gui` function targets. The row-centric names below are reserved
historical design notes only; if top-level GUI declaration rows are revived,
they must keep this naming shape. `importModule standard.gui as gui` remains
accepted during the compatibility window, but `importModule gui standard.gui`
is the preferred source shape.

- [x] Use `guiApplication APP`, not bare `application APP`, to avoid future
      collisions with web, mobile, package, or process concepts.
- [x] Use `guiWindow WINDOW`, not bare `window WINDOW`, so grep results are
      scoped to the GUI surface.
- [x] Use per-kind control declarators such as `guiButton CONTROL` and
      `guiTextBox CONTROL`, not `guiControl CONTROL KIND`.
- [x] Do not use `label CONTROL`; `label NAME` already owns control-flow
      labels. Use `guiTextLabel CONTROL`.
- [x] Keep every GUI verb lower camelCase.
- [x] Keep every GUI symbol value lower camelCase.
- [x] Keep every GUI opaque type PascalCase with a `Gui` prefix.
- [x] Keep all runtime call targets under the `gui.*` namespace.
- [x] Add `standard.gui` as the canonical import module for GUI contracts.
- [x] Reserve `importModule gui standard.gui` as the preferred GUI import
      shape.
- [x] Decide whether legacy `importModule standard.gui as gui` remains accepted
      during the compatibility window.
- [x] Add all committed GUI rows to `SYNTAX.md` with `Partial` status until
      parser, validation, codegen, and runtime are complete.
- [x] Add GUI verbs to `docs/reference/verb-index.md`.
- [x] Add GUI target notes to `docs/language/program-structure.md`.
- [x] Add GUI build-tape notes to `docs/language/project-layout-build-sem.md`.

### Application Rows

- [ ] Add parser support for `guiApplication APP`.
- [ ] Add parser support for `guiApplicationTitle APP "text"`.
- [ ] Add parser support for `guiApplicationIcon APP ICON_GROUP`.
- [ ] Add parser support for `guiApplicationMainWindow APP WINDOW`.
- [ ] Add parser support for `guiApplicationOnExit APP OPERATION`.
- [ ] Store GUI application rows in a dedicated `Program.gui_applications`
      index.
- [ ] Reject duplicate `guiApplication APP` rows.
- [ ] Reject duplicate singleton rows for one application title.
- [ ] Reject duplicate singleton rows for one application icon.
- [ ] Reject duplicate singleton rows for one application main window.
- [ ] Reject duplicate singleton rows for one application exit handler.
- [ ] Validate that `guiApplicationMainWindow` names a declared `guiWindow`.
- [ ] Validate that the main window belongs to the same application.
- [ ] Validate that `guiApplicationOnExit` names a declared operation.
- [ ] Validate the `guiApplicationOnExit` operation output contract.
- [ ] Decide whether `guiApplicationIcon` accepts only icon groups with
      `iconRole applicationPrimary` or any declared icon group.
- [ ] Reuse existing icon registry validation for GUI application icons.

### Window Rows

- [ ] Add parser support for `guiWindow WINDOW`.
- [ ] Add parser support for `guiWindowApplication WINDOW APP`.
- [ ] Add parser support for `guiWindowTitle WINDOW "text"`.
- [ ] Add parser support for `guiWindowWidth WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowHeight WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowMinimumWidth WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowMinimumHeight WINDOW PIXELS`.
- [ ] Add parser support for
      `guiWindowLayout WINDOW verticalStack|horizontalStack|grid|absolute`.
- [ ] Add parser support for `guiWindowResizable WINDOW yes|no`.
- [ ] Add parser support for `guiWindowEvent WINDOW EVENT OPERATION`.
- [ ] Store GUI window rows in a dedicated `Program.gui_windows` index.
- [ ] Reject duplicate `guiWindow WINDOW` rows.
- [ ] Reject a `guiWindowApplication` that names an unknown application.
- [ ] Reject a `guiWindowTitle` row that names an unknown window.
- [ ] Reject width, height, and minimum-size rows with non-integer values.
- [ ] Reject width, height, and minimum-size rows with zero or negative values.
- [ ] Reject a minimum width larger than the initial window width.
- [ ] Reject a minimum height larger than the initial window height.
- [ ] Reject unknown `guiWindowLayout` values.
- [ ] Auto-register a `GuiWindowLayout` enum for
      `verticalStack`, `horizontalStack`, `grid`, and `absolute`.
- [ ] Reject unknown `guiWindowResizable` boolean tokens.
- [ ] Define default `guiWindowResizable` behavior when the row is omitted.
- [ ] Define default layout behavior when `guiWindowLayout` is omitted.
- [ ] Decide whether multiple windows per application are supported in the
      first implementation or parsed as future metadata.

### Control Declarators

- [ ] Add parser support for `guiButton CONTROL`.
- [ ] Add parser support for `guiTextBox CONTROL`.
- [ ] Add parser support for `guiListBox CONTROL`.
- [ ] Add parser support for `guiCheckBox CONTROL`.
- [ ] Add parser support for `guiMenuItem CONTROL`.
- [ ] Add parser support for `guiStatusBar CONTROL`.
- [ ] Add parser support for `guiTextLabel CONTROL`.
- [ ] Store controls in a dedicated `Program.gui_controls` index keyed by
      control symbol.
- [ ] Record each control's declared kind.
- [ ] Reject duplicate control symbols across all GUI control declarator kinds.
- [ ] Reject control symbols that collide with declared windows,
      applications, operations, constants, or storage bindings.
- [ ] Define each declarator as a typed compile-time handle constant:
      `guiButton addTodoButton` creates `addTodoButton : GuiButton`.
- [ ] Define `guiTextBox newTaskTitleTextBox` as
      `newTaskTitleTextBox : GuiTextBox`.
- [ ] Define `guiListBox visibleTodosListBox` as
      `visibleTodosListBox : GuiListBox`.
- [ ] Define `guiWindow todoAppMainWindow` as
      `todoAppMainWindow : GuiWindow`.
- [ ] Decide whether all control handles also subtype or alias a common
      `GuiControl` type.
- [ ] Ensure generated compile-time GUI handles can be passed as values to
      `gui.*` runtime calls.

### Generic Control Rows

- [ ] Add parser support for `guiControlWindow CONTROL WINDOW`.
- [ ] Add parser support for `guiControlEnabled CONTROL yes|no`.
- [ ] Add parser support for `guiControlVisible CONTROL yes|no`.
- [ ] Add parser support for `guiControlTabIndex CONTROL N`.
- [ ] Add parser support for `guiControlAccessibleName CONTROL "text"`.
- [ ] Add parser support for `guiControlEvent CONTROL EVENT OPERATION`.
- [ ] Reject generic control rows that name an unknown control.
- [ ] Reject `guiControlWindow` rows that name an unknown window.
- [ ] Reject controls without a `guiControlWindow` row.
- [ ] Reject duplicate `guiControlWindow` rows for one control.
- [ ] Reject duplicate `guiControlTabIndex` rows for one control.
- [ ] Reject duplicate `guiControlAccessibleName` rows for one control.
- [ ] Reject invalid yes/no values for enabled and visible rows.
- [ ] Define default enabled behavior when `guiControlEnabled` is omitted.
- [ ] Define default visible behavior when `guiControlVisible` is omitted.
- [ ] Reject negative tab-index values.
- [ ] Warn on duplicate tab-index values within one window.
- [ ] Warn when interactive controls omit `guiControlAccessibleName`.
- [ ] Decide whether `guiControlAccessibleName` defaults from visible text for
      buttons, check boxes, and labels.

### Kind-Specific Control Rows

- [ ] Add parser support for `guiButtonText BUTTON "text"`.
- [ ] Add parser support for `guiButtonIsDefault BUTTON yes|no`.
- [ ] Add parser support for `guiTextBoxPlaceholder TEXTBOX "text"`.
- [ ] Add parser support for `guiTextBoxMaxLength TEXTBOX N`.
- [ ] Add parser support for
      `guiListBoxSelectionMode LISTBOX single|multiple`.
- [ ] Add parser support for `guiCheckBoxChecked CHECKBOX yes|no`.
- [ ] Add parser support for `guiTextLabelText LABEL "text"`.
- [ ] Reject `guiButtonText` for non-button controls.
- [ ] Reject `guiButtonIsDefault` for non-button controls.
- [ ] Reject `guiTextBoxPlaceholder` for non-text-box controls.
- [ ] Reject `guiTextBoxMaxLength` for non-text-box controls.
- [ ] Reject `guiListBoxSelectionMode` for non-list-box controls.
- [ ] Reject `guiCheckBoxChecked` for non-check-box controls.
- [ ] Reject `guiTextLabelText` for non-text-label controls.
- [ ] Reject text-box max length values less than one.
- [ ] Define max length default behavior when the row is omitted.
- [ ] Auto-register a `GuiListBoxSelectionMode` enum for `single` and
      `multiple`.
- [ ] Reject unknown list-box selection mode values.
- [ ] Decide whether buttons may omit `guiButtonText`.
- [ ] Decide whether text labels may omit `guiTextLabelText`.
- [ ] Add diagnostics for controls that are declared but visually empty.

### Event Model

- [ ] Add a built-in `GuiEventKind` enum, or equivalent closed token set, for
      GUI event rows.
- [ ] Include `click` in the committed event set.
- [ ] Include `valueChanged` in the committed event set.
- [ ] Include `selectionChanged` in the committed event set.
- [ ] Include `enterPressed` in the committed event set.
- [ ] Include `keyPressed` in the committed event set.
- [ ] Include `focusGained` in the committed event set.
- [ ] Include `focusLost` in the committed event set.
- [ ] Include `closeRequested` in the committed event set.
- [ ] Include `resized` in the committed event set.
- [ ] Include `shown` in the committed event set.
- [ ] Include `hidden` in the committed event set.
- [ ] Validate allowed control events by control kind.
- [ ] Validate allowed window events by window kind.
- [ ] Allow `guiButton` to handle `click`.
- [ ] Allow `guiButton` to handle `focusGained` and `focusLost`.
- [ ] Allow `guiTextBox` to handle `valueChanged`, `enterPressed`,
      `keyPressed`, `focusGained`, and `focusLost`.
- [ ] Allow `guiListBox` to handle `selectionChanged`, `focusGained`, and
      `focusLost`.
- [ ] Allow `guiCheckBox` to handle `valueChanged`, `click`, `focusGained`,
      and `focusLost`.
- [ ] Allow `guiWindow` to handle `closeRequested`, `resized`, `shown`, and
      `hidden`.
- [ ] Reject `selectionChanged` on buttons.
- [ ] Reject `click` on list boxes unless a future design explicitly supports
      item activation.
- [ ] Reject `closeRequested` on controls.
- [ ] Reject unknown event tokens.
- [ ] Reject event rows whose handler operation is missing.
- [ ] Reject duplicate event handlers for the same target/event pair unless
      ordered event pipelines are designed.
- [ ] Decide whether event handler order is source-order or intentionally
      unsupported for the first version.

### Handler ABI

- [ ] Auto-register `GuiSession` as an opaque handler input type.
- [ ] Auto-register `GuiEvent` as an opaque handler input type.
- [ ] Auto-register `GuiWindow` as an opaque declarative handle type.
- [ ] Auto-register `GuiControl` as an opaque common control handle type if a
      common supertype is adopted.
- [ ] Auto-register `GuiButton`.
- [ ] Auto-register `GuiTextBox`.
- [ ] Auto-register `GuiListBox`.
- [ ] Auto-register `GuiCheckBox`.
- [ ] Auto-register `GuiMenuItem`.
- [ ] Auto-register `GuiStatusBar`.
- [ ] Auto-register `GuiTextLabel`.
- [ ] Define GUI handler operations as
      `input HANDLER session GuiSession`,
      `input HANDLER event GuiEvent`,
      and `output HANDLER CSignedInt32`.
- [ ] Reject GUI event handlers with missing `GuiSession` input.
- [ ] Reject GUI event handlers with missing `GuiEvent` input.
- [ ] Reject GUI event handlers with extra native ABI inputs.
- [ ] Reject GUI event handlers whose output is not `CSignedInt32`.
- [ ] Define that handler return `0` means handled successfully.
- [ ] Define non-zero handler returns as runtime-level event failure.
- [ ] Decide whether non-zero handler returns close the window, log and
      continue, or trap in dev builds.
- [ ] Preserve `GuiSession` and `GuiEvent` as ABI parameters for GUI handlers,
      like `HttpRequest` and `HttpResponse` are preserved for route handlers.
- [ ] Continue dropping ordinary opaque dependency inputs outside the GUI and
      HTTP ABIs.

### Runtime Call Surface

- [ ] Add `gui.textBoxText`.
- [ ] Add `gui.textBoxSetText`.
- [ ] Add `gui.listBoxSelectedIndex`.
- [ ] Add `gui.listBoxAppendItem`.
- [ ] Add `gui.listBoxClear`.
- [ ] Add `gui.windowClose`.
- [ ] Add `gui.eventKeyCode`.
- [ ] Add `gui.eventSelectedIndex`.
- [ ] Add `gui.eventWindowWidth`.
- [ ] Add `gui.eventWindowHeight`.
- [ ] Add `gui.eventCancelClose` or explicitly defer cancellable close events.
- [ ] Define required args for every `gui.*` runtime call.
- [ ] Require `session GuiSession` on every GUI runtime call that touches
      live GUI state.
- [ ] Define whether declarative handles are passed as `control`, `button`,
      `textBox`, `listBox`, or kind-specific arg names.
- [ ] Reject passing a `GuiButton` handle to `gui.textBoxText`.
- [ ] Reject passing a `GuiTextBox` handle to `gui.listBoxAppendItem`.
- [ ] Lower declarative GUI handle symbols to runtime control IDs or handles.
- [ ] Define the lifetime of strings returned by `gui.textBoxText`.
- [ ] Define whether returned GUI strings are copied, borrowed, or valid only
      until the next GUI runtime call.
- [ ] Define list-box item encoding as null-terminated UTF-8 or a future
      UTF-16 aware string type.
- [ ] Decide whether the MVP runtime stores UTF-8 internally and converts to
      UTF-16 at the Win32 boundary.
- [ ] Add source-of-truth comments so `semsc.py`, `semlint.py`, `SYNTAX.md`,
      and `standard.gui` stay aligned on `gui.*` target names.

### Effects And Capabilities

- [ ] Define `gui.control.textBox.text read`.
- [ ] Define `gui.control.textBox.text write`.
- [ ] Define `gui.control.listBox.items read`.
- [ ] Define `gui.control.listBox.items write`.
- [ ] Define `gui.control.listBox.selection read`.
- [ ] Define `gui.control.checkBox.checked read`.
- [ ] Define `gui.control.checkBox.checked write`.
- [ ] Define `gui.window write`.
- [ ] Define `gui.event read`.
- [ ] Define `gui.event.close write` if close cancellation is supported.
- [ ] Add reusable `standard.gui` capability declarations such as
      `guiTextBoxReader`, `guiTextBoxWriter`, and `guiListBoxWriter`.
- [ ] Ensure existing effect/capability coverage checks work unchanged for
      hierarchical GUI paths.
- [ ] Add lint tests proving `gui.control.textBox.text read` is covered by
      `capability guiTextBoxReader gui.control.textBox.text read`.
- [ ] Add lint tests proving a coarse capability such as
      `gui.control read` covers narrower read paths only if hierarchical
      coverage semantics intentionally allow it.
- [ ] Warn on overbroad GUI capabilities in exported module APIs.
- [ ] Decide whether GUI event registration rows require capabilities or only
      handler bodies require capabilities.

### Compiler Parser And Program Model

- [ ] Add GUI model classes or dictionaries to `Program`.
- [ ] Add parse handlers for all committed `guiApplication*` rows.
- [ ] Add parse handlers for all committed `guiWindow*` rows.
- [ ] Add parse handlers for all committed GUI control declarator rows.
- [ ] Add parse handlers for all committed `guiControl*` rows.
- [ ] Add parse handlers for all committed kind-specific control rows.
- [ ] Preserve source line numbers for every GUI declaration.
- [ ] Preserve raw text for diagnostics and future docs generation.
- [ ] Add conflict checks for duplicate declarations during parse.
- [ ] Add post-parse validation for cross-reference checks that require the
      whole Program.
- [ ] Add GUI declarations to compiler parse-only success coverage.
- [ ] Add GUI declarations to compiler JSON diagnostics if diagnostics are
      expanded to include source spans for validation errors.

### Compiler Codegen

- [ ] Detect `target windowsGui` with a validated `guiApplication` during
      no-entry codegen.
- [ ] Collect GUI event handler operation names before declaring user op
      functions.
- [ ] Preserve `GuiSession` and `GuiEvent` handler inputs in the ABI.
- [ ] Declare all GUI event handler functions before emitting the GUI entry.
- [ ] Compile non-handler helper operations as normal user ops.
- [ ] Emit a native GUI application config table.
- [ ] Emit one config record for the application title and icon.
- [ ] Emit one config record for each window.
- [ ] Emit one config record for each control.
- [ ] Emit one config record for each event edge.
- [ ] Encode control kind in a stable runtime enum.
- [ ] Encode event kind in a stable runtime enum.
- [ ] Emit handler function pointers in the event-edge table.
- [ ] Declare `ss_gui_application_run` in generated LLVM.
- [ ] Emit `main` or `WinMain` bridge code that calls
      `ss_gui_application_run`.
- [ ] Decide whether the LLVM entry symbol remains `main` with `-mwindows`, or
      whether codegen emits a dedicated `WinMain` wrapper.
- [ ] Add Windows subsystem linker support for GUI executables.
- [ ] Pass `-mwindows` through clang for Windows GUI builds when using the GNU
      driver mode.
- [ ] Pass the MSVC-linker equivalent `/SUBSYSTEM:WINDOWS` when clang is in
      MSVC driver mode if `-mwindows` is not sufficient.
- [ ] Ensure console executables do not accidentally inherit GUI subsystem
      flags.
- [ ] Link the GUI runtime source automatically for `target windowsGui`.
- [ ] Link `user32` automatically on Windows GUI builds.
- [ ] Link `gdi32` automatically on Windows GUI builds.
- [ ] Link `comctl32` automatically if common controls are used.
- [ ] Link `shell32` only if shell icon or file-dialog helpers are added.
- [ ] Keep Linux/macOS builds parse-only or fail with a clear unsupported
      target diagnostic until non-Windows GUI backends exist.

### Native Win32 Runtime Adapter

- [ ] Add `SemanticScript/runtime/native_win32_gui/`.
- [ ] Add `sem_win32_gui_runtime.h`.
- [ ] Add `sem_win32_gui_runtime.c`.
- [ ] Add `CMakeLists.txt` for the native GUI runtime.
- [ ] Define stable C ABI structs for application config.
- [ ] Define stable C ABI structs for window config.
- [ ] Define stable C ABI structs for control config.
- [ ] Define stable C ABI structs for event-edge config.
- [ ] Define a stable handler function pointer type:
      `int32_t (*)(SSGuiSession *, SSGuiEvent *)`.
- [ ] Implement `ss_gui_application_run`.
- [ ] Register a Win32 window class.
- [ ] Create the main window from generated config.
- [ ] Create child controls from generated config.
- [ ] Implement `verticalStack` layout.
- [ ] Implement `horizontalStack` layout.
- [ ] Stub or explicitly reject `grid` layout until implemented.
- [ ] Stub or explicitly reject `absolute` layout until implemented.
- [ ] Handle `WM_COMMAND` for button clicks.
- [ ] Handle text-box enter key dispatch.
- [ ] Handle list-box selection changes.
- [ ] Handle `WM_CLOSE` as `closeRequested`.
- [ ] Handle `WM_SIZE` as `resized`.
- [ ] Dispatch events to generated SemanticScript handler function pointers.
- [ ] Create and pass a runtime-owned `SSGuiSession` token.
- [ ] Create and pass a runtime-owned `SSGuiEvent` token.
- [ ] Map declarative control IDs to `HWND` values in the session.
- [ ] Implement `ss_gui_text_box_text`.
- [ ] Implement `ss_gui_text_box_set_text`.
- [ ] Implement `ss_gui_list_box_selected_index`.
- [ ] Implement `ss_gui_list_box_append_item`.
- [ ] Implement `ss_gui_list_box_clear`.
- [ ] Implement `ss_gui_window_close`.
- [ ] Implement `ss_gui_event_key_code`.
- [ ] Implement `ss_gui_event_selected_index`.
- [ ] Implement `ss_gui_event_window_width`.
- [ ] Implement `ss_gui_event_window_height`.
- [ ] Implement or defer `ss_gui_event_cancel_close`.
- [ ] Define thread affinity: all GUI runtime calls must happen on the GUI
      thread unless future dispatch helpers are added.
- [ ] Define memory ownership for strings returned from the runtime.
- [ ] Define error codes for missing controls, wrong control kinds, allocation
      failures, and Win32 API failures.
- [ ] Add runtime health demo that opens a window and exits cleanly.

### Standard Library Module

- [ ] Add `SemanticScript/std/gui/main.sem`.
- [ ] Relay `standard.gui` from `SemanticScript/std/module.sem`.
- [ ] Add module metadata for `standard.gui`.
- [ ] Add type aliases for `GuiSession`.
- [ ] Add type aliases for `GuiEvent`.
- [ ] Add type aliases for `GuiWindow`.
- [ ] Add type aliases for `GuiControl` if adopted.
- [ ] Add type aliases for every committed control handle type.
- [ ] Add capability declarations for the committed GUI effect paths.
- [ ] Add constants for GUI module version metadata.
- [ ] Add documentation comments explaining that `gui.*` targets are
      compiler/runtime-owned intrinsics.
- [ ] Add import example using `importModule gui standard.gui`.

### Linter And Editor Tooling

- [ ] Add GUI verbs to standalone linter arity tables.
- [ ] Add GUI closed enum values to linter validation.
- [ ] Add diagnostics for missing `guiApplicationMainWindow`.
- [ ] Add diagnostics for controls missing `guiControlWindow`.
- [ ] Add diagnostics for invalid control-kind-specific rows.
- [ ] Add diagnostics for invalid event-kind/control-kind combinations.
- [ ] Add diagnostics for missing or malformed GUI handler ABI inputs.
- [ ] Add diagnostics for missing GUI handler output contract.
- [ ] Add diagnostics for GUI runtime calls missing required `session` args.
- [ ] Add `gui.*` runtime call signatures to semlint's built-in call table.
- [ ] Add `gui.*` effect requirements to semlint's effect table.
- [ ] Add VS Code grammar highlighting for GUI declaration verbs.
- [ ] Add VS Code hover descriptions for GUI declaration verbs.
- [ ] Add VS Code document symbol grouping for GUI applications, windows,
      controls, and event edges.
- [ ] Add snippets only after the surface stabilizes.

### Tests And Samples

- [ ] Add parser tests for the minimum GUI application shape.
- [ ] Add parser tests for every application row.
- [ ] Add parser tests for every window row.
- [ ] Add parser tests for every control declarator row.
- [ ] Add parser tests for every generic control row.
- [ ] Add parser tests for every kind-specific control row.
- [ ] Add parse-failure tests for duplicate GUI applications.
- [ ] Add parse-failure tests for duplicate controls.
- [ ] Add validation tests for missing main window.
- [ ] Add validation tests for missing control window.
- [ ] Add validation tests for invalid event/control combinations.
- [ ] Add validation tests for malformed GUI handler ABI.
- [ ] Add compiler IR tests proving GUI handler params are preserved.
- [ ] Add compiler IR tests proving `ss_gui_application_run` is declared.
- [ ] Add compiler IR tests proving GUI config tables are emitted.
- [ ] Add linker tests proving Windows GUI builds include subsystem flags.
- [ ] Add linker tests proving `user32` and `gdi32` link args are added.
- [ ] Add a smoke sample under `app/hello-gui`.
- [ ] Add a Todo GUI sample under `app/todo-gui` only after the hello sample
      proves the base runtime.
- [ ] Add a runtime health test that opens and closes a window on Windows CI
      if the runner supports desktop interaction.
- [ ] Add a headless compile-only fallback test for CI environments that
      cannot open desktop windows.
- [ ] Add docs explaining how to run GUI smoke tests locally on Windows.

### Documentation And Release Scope

- [ ] Add a GUI language doc under `docs/language/`.
- [ ] Add a native GUI runtime doc under `docs/toolchain/` or
      `SemanticScript/runtime/native_win32_gui/README.md`.
- [ ] Update `README.md` support matrix once the surface is implemented or
      explicitly preview.
- [ ] Update `docs/README.md` with links to GUI language/runtime docs.
- [ ] Update `docs/agents.md` with compact GUI syntax guidance.
- [ ] Update `docs/optimization-guide.md` with GUI effect/capability examples.
- [ ] Decide whether declarative Windows GUI support is in 1.0 scope,
      post-1.0 preview scope, or experimental-only scope.
- [ ] Mark every GUI row in `SYNTAX.md` with honest implementation status.
- [ ] Add migration guidance if early names change before the committed
      syntax freezes.

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
  - [x] Detect ambiguous unqualified references when imports expose the same
        symbol.
  - [x] Define whether `importModule X as Y` creates a real namespace boundary.
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
- [ ] Add first-class HTML/SSX server template syntax.
  - [x] Add `htmlTemplate NAME` declarations for named server-rendered HTML
        values.
  - [x] Add `htmlArg TEMPLATE ARG_NAME TYPE` declarations for explicit,
        typed template input edges.
  - [x] Add `htmlBody TEMPLATE` syntax islands that parse following indented
        HTML/SSX lines until the next column-0 SemanticScript line.
  - [x] Keep `htmlBody` as the only indentation-sensitive syntax exception;
        normal SemanticScript remains flat and line-oriented.
  - [x] Allow JSX-like tags, attributes, fragments, and dynamic holes inside
        `htmlBody` only.
  - [x] Restrict dynamic holes to declared `htmlArg` values, using
        `htmlArg.name` references instead of a generic `props` object.
  - [x] Reject arbitrary calls, mutation, request reads, and hidden state reads
        inside HTML dynamic holes.
  - [x] Type-check dynamic holes by core HTML sink context: text nodes, quoted
        attributes, class values, URL attributes, fragments, and full documents.
  - [x] Escape `HtmlText` during hydration for text and attribute sinks.
  - [ ] Extend HTML sink-context checks to boolean attributes and a complete
        HTML parser instead of the current narrow server-template scan.
  - [x] Define first-class HTML trust types such as `HtmlText`, `HtmlClass`,
        `SafeUrl`, `HtmlFragment`, `HtmlTrustedFragment`, and `HtmlDocument`.
  - [x] Lower template hydration through generated targets such as
        `html.hydrate.TodoPageTemplate`.
  - [x] Add `standard.html` as the official standard-library import module for
        first-class HTML templates.
  - [x] Resolve `standard.html` through `SemanticScript/std/html/main.sem`.
  - [x] Use the canonical `importModule html standard.html` form in the demo app.
  - [x] Add `standard.http` and `standard.json` metadata modules for the
        compiler-owned `http.*` and `json.*` intrinsic namespaces.
  - [x] Resolve `standard.http` and `standard.json` through
        `SemanticScript/std/http/main.sem` and `SemanticScript/std/json/main.sem`.
  - [x] Add `<module>/main.sem` canonical entries for every C-derived stdlib module.
  - [x] Add `SemanticScript/std/module.sem` as the top-level `standard` relay.
  - [ ] Add `http.responseHtml` as the explicit HTML response writer with
        `text/html; charset=utf-8` content type behavior.
  - [x] Add compiler diagnostics for malformed HTML islands, unknown
        `htmlArg` references, and mismatched component/template arguments.
  - [x] Add compiler diagnostics for unsafe dynamic HTML sinks covered by the
        core context checker.
  - [ ] Add compiler diagnostics for remaining unsafe dynamic HTML sinks once
        the complete HTML parser exists.
  - [ ] Add semlint checks proving untrusted request/query/header/body data
        cannot flow into HTML without an explicit escape or trust conversion.
  - [ ] Add formatter and VS Code grammar support for `htmlTemplate`,
        `htmlArg`, `htmlBody`, and embedded SSX syntax.
  - [ ] Add docs explaining why HTML symbols are a narrow grammar-island
        exception to the normal no-brace/no-angle/no-indentation rules.
  - [ ] Add webserver tests proving hydrated HTML responses preserve escaping,
        content type, content length, and route-handler failure behavior.
- [ ] Add static-file serving helper.
  - [ ] Define root directory safety and path traversal behavior.
  - [ ] Add MIME/content-length tests.
- [ ] Add graceful shutdown hook.
  - [ ] Define signal/control API.
  - [ ] Add tests that server processes stop without forced termination.

### Data, Codec, And Collection Runtime

- [ ] (superseded) Implement real JSON codec runtime for records.
  - All JSON record-codec, encode/decode, and runtime work — including the
    `json.encode.RecordTypeName` / `json.decode.RecordTypeName` lowerings,
    required-field/unknown-field/limit enforcement, and the malformed/missing/
    escaping test matrix — is now owned end-to-end by the
    `### Native JSON CRUD API And jsonBody Literal` section below. Do not add
    new JSON-handling bullets here; extend that section instead.
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

### Native JSON CRUD API And jsonBody Literal

This section turns the JSON refinement design into implementation-sized tasks.
The goal is a native CRUD surface over a mutable parsed JSON tree, a column-0
`jsonBody NAME` indented-island literal that lowers to a compile-time-validated
constant, and typed `json.stringify.<TypeName>` / `json.parse.<TypeName>` entry
points that wrap the existing builder/finder runtime so handlers stop hand-rolling
JSON through `c.snprintf` format templates. Honor the `feedback_verify_impld_claims`
rule: nothing here promotes a SYNTAX.md row to `Impl'd` without a feature_test that
would fail under a no-op lowering.

#### standard.json Types, Error, And Enum

- [x] Add `type JsonDocument COpaqueMemoryAddress` to
      `SemanticScript/std/json/main.sem` with `exportType standard.json JsonDocument`.
  - [x] Add a `typeInvariant JsonDocument` stating the handle is created by
        `json.createDocument` / `json.createEmptyDocument` and freed via
        `defer json.destroyDocument`; backing buffer grows up to `capacityBytes`
        and surfaces `JsonAccessError.CapacityExceeded` past that bound.
- [x] Add `type JsonCursor CSignedInt64` with `exportType standard.json JsonCursor`.
  - [x] Add a `typeInvariant JsonCursor` documenting the stable-index contract
        and the structural-mutation invalidation list
        (`removeObjectField`, `removeArrayElementAt`, `clearObject`, `clearArray`,
        `setObjectFieldObject`, `setObjectFieldArray`,
        `insertArrayElement*`, `replaceArrayElement*` when the new value is a
        container) — cross-reference SYNTAX.md:446 sqlite column-pointer lifetime.
- [x] Add `type JsonPath CNullTerminatedByteString` with
      `exportType standard.json JsonPath`.
  - [x] Add a `typeInvariant JsonPath` pinning the grammar: `.fieldName` object
        steps, `[index]` array steps, anything else returns
        `JsonAccessError.MalformedPath`.
- [x] Add the `JsonValueKind` enum in `SemanticScript/std/json/main.sem`.
  - [x] Declare `enum JsonValueKind repr CSignedInt32`.
  - [x] Declare cases `objectJsonValueKind 0`, `arrayJsonValueKind 1`,
        `stringJsonValueKind 2`, `integerJsonValueKind 3`,
        `doubleJsonValueKind 4`, `booleanJsonValueKind 5`,
        `nullJsonValueKind 6` using the descriptive-suffix convention.
  - [x] Auto-register the enum in `SemanticScript/compiler/semsc.py`'s built-in
        enum table the same way `SqliteColumnType` is registered.
- [x] Add the `JsonAccessError` declaration in `SemanticScript/std/json/main.sem`.
  - [x] Declare `error JsonAccessError`.
  - [x] Declare `errorCase JsonAccessError PathNotFound CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError WrongType CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError IndexOutOfRange CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError FieldNameTooLong CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError DocumentNotMutable CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError CapacityExceeded CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError MalformedPath CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError ScratchTooSmall CSignedInt32`.
  - [x] Add `exportError standard.json JsonAccessError`.
- [x] Add `JsonEncodeError` and `JsonDecodeError` declarations in the same file.
  - [x] `JsonEncodeError` cases: `CapacityExceeded`, `WrongType`,
        `OutputBufferTooSmall`, each carrying `CSignedInt32`.
  - [x] `JsonDecodeError` cases: `UnexpectedToken`, `MissingRequired`,
        `WrongType`, `Oversize`, `Truncated`, `EscapeMalformed`,
        each carrying `CSignedInt32`.

#### Native JSON Document Runtime

- [x] Add the `SSJsonDocument` opaque struct to
      `SemanticScript/runtime/native_json/sem_json_runtime.h`.
  - [x] Hold a growable node table indexed by `int64_t` cursors so cursors
        survive non-structural mutations.
  - [x] Hold a capacity-bounded text arena for owned string values.
  - [x] Track `capacity_bytes` / `bytes_used` for `CapacityExceeded` checks.
- [x] Add `SSJsonNodeKind` matching `JsonValueKind` integer values exactly so
      the lowering can forward `cursor_kind` without a translation table.
- [x] Add `SS_JSON_OK = 0` and one `SS_JSON_ERR_*` constant per
      `JsonAccessError` case in `sem_json_runtime.h`; map 1:1 to the error
      case ordinals.
- [x] Implement `ss_json_document_create_from_text(const char *json_text,
      int64_t capacity_bytes, SSJsonDocument **out)` in
      `SemanticScript/runtime/native_json/sem_json_runtime.c`.
  - [ ] Reuse the RFC-8259-aware tokenizer that backs the existing finder API.
  - [x] Reject malformed input with the matching `SS_JSON_ERR_*` code; never
        leak a half-built document on failure.
- [x] Implement `ss_json_document_create_empty(int64_t capacity_bytes,
      int32_t root_kind, SSJsonDocument **out)` accepting only
      `objectJsonValueKind` / `arrayJsonValueKind` as roots.
- [x] Implement `ss_json_document_destroy(SSJsonDocument *document)` freeing
      the node table and arena; tolerate NULL.
- [x] Implement `ss_json_document_serialize(SSJsonDocument *document,
      char *scratch, int64_t scratch_capacity, const char **out)`.
  - [x] Reuse the builder's RFC 8259 `\uXXXX` escape path so output matches
        the SYNTAX.md:448 escape policy exactly.
  - [x] Return `SS_JSON_ERR_SCRATCH_TOO_SMALL` when output would overflow
        the scratch; never truncate silently.
- [x] Implement `ss_json_document_length(SSJsonDocument *document)` returning
      the byte count the next serialize will emit, mirroring
      `json.builderLength`.
- [x] Implement `ss_json_document_root(SSJsonDocument *document)` returning
      cursor 0 (always defined).
- [x] Implement `ss_json_navigate_object_field(SSJsonDocument *document,
      int64_t cursor, const char *field_name, int64_t *out)`.
  - [x] Return `SS_JSON_ERR_WRONG_TYPE` when the cursor's node is not an
        object.
  - [x] Return `SS_JSON_ERR_PATH_NOT_FOUND` when the field is absent.
- [x] Implement `ss_json_navigate_array_element(SSJsonDocument *document,
      int64_t cursor, int64_t index, int64_t *out)` with
      `SS_JSON_ERR_INDEX_OUT_OF_RANGE` outside `[0, array_length)` and
      `SS_JSON_ERR_WRONG_TYPE` for non-arrays.
- [x] Implement `ss_json_cursor_parent(SSJsonDocument *document,
      int64_t cursor, int64_t *out)` returning `SS_JSON_ERR_PATH_NOT_FOUND`
      for the root.
- [x] Implement `ss_json_cursor_at_path(SSJsonDocument *document,
      const char *path, int64_t *out)`.
  - [x] Parse segments left-to-right: `.fieldName` for object steps,
        `[index]` for array steps; reject anything else with
        `SS_JSON_ERR_MALFORMED_PATH`.
  - [x] Reuse the per-step navigators internally so error codes from a
        mid-path failure match what the user would see if they walked the
        cursor manually.
- [x] Implement `ss_json_cursor_kind` returning the `JsonValueKind` integer
      directly.
- [x] Implement `ss_json_cursor_is_null` returning 1 for `null` and 0 for any
      other kind (no error path).
- [x] Implement `ss_json_cursor_int64(document, cursor, missing_default,
      out)` matching the `findInt64` `missingDefault` contract from
      SYNTAX.md:449 — total function, no error code.
- [x] Implement `ss_json_cursor_double` and `ss_json_cursor_bool` with the
      same `missing_default` propagation.
- [x] Implement `ss_json_cursor_string(document, cursor, scratch,
      scratch_capacity, out)`.
  - [x] Un-escape standard JSON escapes plus `\uXXXX` for BMP code points
        into the scratch buffer (reuse the `findString` algorithm).
  - [x] Return `SS_JSON_ERR_WRONG_TYPE` for non-strings,
        `SS_JSON_ERR_SCRATCH_TOO_SMALL` when the unescaped value plus NUL
        does not fit.
- [x] Implement `ss_json_cursor_array_length` /
      `ss_json_cursor_object_field_count` with `SS_JSON_ERR_WRONG_TYPE` on
      kind mismatch.
- [x] Implement `ss_json_cursor_object_field_name_at(document, cursor, index,
      scratch, scratch_capacity, out)` copying the field name into scratch.
- [x] Implement `ss_json_cursor_object_field_value_at(document, cursor,
      index, out)` returning the child cursor.
- [x] Implement `ss_json_set_object_field_string`,
      `ss_json_set_object_field_int64`, `ss_json_set_object_field_double`,
      `ss_json_set_object_field_bool`, `ss_json_set_object_field_null`.
  - [x] Overwrite an existing field in place when the field name matches.
  - [x] Append a new field record when the name is absent.
  - [x] Return `SS_JSON_ERR_WRONG_TYPE` on a non-object cursor,
        `SS_JSON_ERR_FIELD_NAME_TOO_LONG` past the per-document field-name
        bound, `SS_JSON_ERR_CAPACITY_EXCEEDED` when the arena cannot fit
        the new bytes within `capacity_bytes`.
- [x] Implement `ss_json_set_object_field_object` /
      `ss_json_set_object_field_array` returning the new child cursor.
- [x] Implement `ss_json_set_object_field_json_text` parsing the supplied
      sub-document, type-validating it, and grafting it under the named
      field.
- [x] Implement `ss_json_append_array_element_*` for string, int64, double,
      bool, null, object, array, and json_text variants; append at
      `array_length`; return the new element cursor for containers.
- [x] Implement `ss_json_insert_array_element_*` for the same variants;
      shift later elements one slot; reject `index > array_length` with
      `SS_JSON_ERR_INDEX_OUT_OF_RANGE`.
- [x] Implement `ss_json_replace_array_element_*` overwriting one slot in
      place; invalidate descendant cursors of the replaced slot when the
      new value is a container.
- [x] Implement `ss_json_remove_object_field` returning `0` when removed and
      `1` when the field was absent (matches the design's documented
      semantics).
- [x] Implement `ss_json_remove_array_element_at` shifting later elements
      down one slot.
- [x] Implement `ss_json_clear_object` and `ss_json_clear_array` removing
      every field/element while preserving the cursor's kind.
- [x] Document the cursor invalidation contract in `sem_json_runtime.h`
      next to each mutator so the C-side comments match the SemanticScript
      `typeInvariant JsonCursor`.
- [x] Extend `_native_json_link_inputs` in
      `SemanticScript/compiler/semsc.py` to pull in `sem_json_runtime.c`
      whenever any `json.*` document call appears (the existing builder
      trigger already covers this, but document the additional symbols).

#### Compiler Lowering (semsc.py)

- [x] Register `json.createDocument` in the `json.*` dispatch table in
      `SemanticScript/compiler/semsc.py`.
  - [x] Allocate the out-pointer slot in the function's entry block,
        pre-initialized to NULL, exactly like `sqlite.openDatabase`.
  - [x] Stash the slot on `call["handle_slot"]` so the matching
        `defer json.destroyDocument` re-loads the handle at every exit.
  - [x] Populate `call["result"]` / `call["error_value"]` /
        `call["error_cond"]` so `bindOk` / `bindError` / `branchIfError`
        fall through unchanged.
- [x] Register `json.createEmptyDocument` with the same handle-slot
      machinery.
- [x] Add `json.destroyDocument` to `_NATIVE_DEFER_DISPATCH` alongside
      `json.destroyBuilder` so `defer json.destroyDocument userDocument`
      compiles to a real call at every cleanup site, including failure
      labels.
- [x] Register `json.serializeDocument` returning
      `Result JsonText JsonAccessError`.
- [x] Register `json.documentLength` returning a plain `CSignedInt64`.
- [x] Register `json.documentRoot` returning a plain `JsonCursor` (root is
      always defined, no error path).
- [x] Register `json.objectFieldAt`, `json.arrayElementAt`,
      `json.cursorParent`, `json.cursorAtPath` returning
      `Result JsonCursor JsonAccessError`.
- [x] Register the cursor readers (`cursorKind`, `cursorIsNull`,
      `cursorInt64`, `cursorDouble`, `cursorBool`, `cursorString`,
      `cursorArrayLength`, `cursorObjectFieldCount`,
      `cursorObjectFieldNameAt`, `cursorObjectFieldValueAt`) with the
      bind shape documented in the design table.
- [x] Register the mutator calls (`setObjectField*`, `appendArrayElement*`,
      `insertArrayElement*`, `replaceArrayElement*`, `removeObjectField`,
      `removeArrayElementAt`, `clearObject`, `clearArray`) returning
      `CSignedInt32` status with `ignoreOk` + `bindError CSignedInt32` +
      `branchIfError`, matching the existing `json.field*` shape.
- [x] Add `json.document.tree` to the effect-axis validator so
      `effect OP read json.document.tree` and
      `effect OP write json.document.tree` parse and route through semlint
      as a real axis, parallel to `gui.control.textBox.text`.
- [x] Resolve `useCapability OP <name>` for the two heap capabilities the
      design uses (`jsonDocumentAllocateCapability heap allocate`,
      `jsonDocumentFreeCapability heap free`) without introducing a new
      capability bucket — they remain user-named heap capabilities.

#### jsonBody Indented-Island Literal

- [x] Add parser support for `jsonBody NAME` at column 0 in
      `SemanticScript/compiler/semsc.py`.
  - [x] Recognize indented lines that follow as one raw-text island,
        terminated at the next non-empty column-0 SemanticScript line — the
        same termination rule used by `htmlBody` (SYNTAX.md:307).
  - [x] Capture the island bytes verbatim, preserving inner whitespace
        inside JSON string literals.
  - [x] Bind the island to the most recently declared
        `storage local|module immutable NAME TYPE` row that has no inline
        value; reject orphan `jsonBody NAME` rows with a parse diagnostic.
  - [x] Reject `jsonBody` rows whose target storage type is neither
        `JsonText` nor a declared `record` type with a parse diagnostic
        that names the offending type.
- [x] Validate the island as JSON at compile time.
  - [x] Parse with a strict RFC 8259 tokenizer that rejects trailing
        commas, comments, unquoted keys, and non-UTF-8 bytes.
  - [x] Emit a diagnostic citing the column-0 island name and the in-island
        line+column of the offending byte.
- [ ] Type-check the parsed literal against the declared storage type.
  - [x] `JsonText`: store the canonicalized JSON bytes as a
        `CNullTerminatedByteString` constant.
  - [ ] `record`: enforce every required field is present, every type
        matches, no unknown keys are present, and nested record literals
        recurse through the same rule.
  - [ ] Honor `recordFieldJsonName` overrides when mapping JSON keys to
        record fields.
  - [ ] Honor `recordFieldJsonOmitWhen empty|null|false|zero` so omitted
        fields default to the configured policy without runtime branching.
  - [ ] Emit one diagnostic per failure naming the offending field, the
        expected type, and the actual JSON kind.
- [ ] Lower the typed literal to a constant in the emitted module.
  - [x] `JsonText`: emit a static null-terminated byte array exactly like
        an inline `"..."` storage value.
  - [ ] Record-typed: emit a typed struct constant whose layout matches
        the record's emitted struct so no runtime parse runs.
- [x] Update `SemanticScript/linter/semlint.py` to walk `jsonBody` islands
      and surface the same parse/type diagnostics that `semsc.py` emits,
      so `ascc --lint --parse-only` reports them without a full compile.
- [x] Update `vscode-semanticscript/syntaxes/semanticscript.tmLanguage.json`
      to highlight the `jsonBody NAME` row and JSON-token the island lines.
- [x] Update `vscode-semanticscript/extension.js` symbol/hover support to
      treat `jsonBody NAME` as a value-producing declaration that resolves
      to the prior storage row.
- [x] Add a semfmt pass for `jsonBody` islands so formatting preserves
      indentation, mirroring the `htmlBody` exception flagged in
      `feedback_semfmt_strips_htmlbody`.
  - [x] Add a regression test that runs semfmt on a file containing
        `jsonBody` and asserts the JSON island still parses afterward.

#### json.stringify.<TypeName> And json.parse.<TypeName>

- [ ] Add `json.stringify.<TypeName>` dispatch in
      `SemanticScript/compiler/semsc.py`.
  - [x] For primitive `TypeName` (I64, Bool, F64, String,
        width-specific C ABI integers) reuse the existing
        `json.encode.<Primitive>` lowering at SYNTAX.md:428.
  - [ ] For record `TypeName` generate a field-by-field encoder that walks
        `recordField` + `recordFieldJsonName` + `recordFieldJsonOmitWhen`
        and calls the matching `json.field*` builder primitive; promotes
        the SYNTAX.md:430 Partial row toward `Impl'd`.
  - [ ] For `JsonText` perform an identity copy through scratch with a
        length check so pre-built bodies can flow through a typed
        pipeline without escaping twice.
  - [ ] Surface `bindOk JsonText` / `bindError JsonEncodeError` at the
        call site.
- [ ] Add `json.parse.<TypeName>` dispatch in `semsc.py`.
  - [x] Primitive: reuse `json.decode.<Primitive>` at SYNTAX.md:429.
  - [ ] Record: generate a field-by-field decoder that validates required
        fields, type-checks each field, applies `omit-when` defaults, and
        surfaces field-level failures through `JsonDecodeError`.
  - [ ] `JsonText`: validate JSON syntax and pass bytes through unchanged.
- [ ] Add `recordFieldJsonOmitWhen` parser support if not already present;
      accept `empty`, `null`, `false`, `zero` policies.
- [x] Update SYNTAX.md:428 / :429 / :430 rows to cross-reference
      `json.stringify.<TypeName>` and `json.parse.<TypeName>` as the
      recommended high-level entry points.

#### semlint Rules

- [x] Add `SS3620 unguardedJsonAccess` to `SemanticScript/linter/semlint.py`.
  - [x] Flag any operation that consumes a `bindOk JsonCursor` from a
        fallible navigator without a `branchIfError` between the `run`
        and the first use of the cursor.
  - [x] Treat `json.documentRoot` as exempt (cannot fail).
  - [x] Add unit coverage in
        `SemanticScript/linter/test_semlint.py`.
- [x] Add `SS3621 staleJsonCursor`.
  - [x] Track `JsonCursor` bindings across the operation body and warn
        when a cursor is read after a structural mutator on its document
        (full mutator list per the `typeInvariant JsonCursor` row).
  - [x] Surface a fix-it hint suggesting a fresh `objectFieldAt` /
        `arrayElementAt` / `cursorAtPath` call.
  - [x] Add unit coverage with each structural-mutator case.
- [x] Add `SS3622 malformedJsonPath`.
  - [x] Parse every `JsonPath` literal at lint time and flag unmatched
        `[`, empty `.` segments, unescaped dots inside field names, and
        non-numeric array indices.
  - [x] Block compilation when the literal is statically malformed so the
        diagnostic fires before the runtime sees the path.
- [x] Add `SS3623 unescapedJsonStringInterpolation`.
  - [x] Flag `c.snprintf` format strings that contain `%s` inside JSON
        string content (heuristic: surrounded by `"` and embedded in a
        literal that includes `{` / `:` / `,`).
  - [x] Recommend `json.stringify.<TypeName>` or
        `json.serializeDocument` as the safe replacement.
- [ ] Re-run `python SemanticScript/linter/test_semlint.py` after each new
      rule to confirm zero regressions.

#### SYNTAX.md Rows

- [x] Add a row for the new `standard.json` types
      (`JsonDocument`, `JsonCursor`, `JsonPath`) mirroring SYNTAX.md:447.
- [x] Add a row for `JsonValueKind` next to `SqliteColumnType`.
- [x] Add a row for `JsonAccessError`, `JsonEncodeError`, `JsonDecodeError`.
- [x] Add a row for the document lifecycle calls (`json.createDocument`,
      `json.createEmptyDocument`, `json.destroyDocument`,
      `json.serializeDocument`, `json.documentLength`,
      `json.documentRoot`).
- [x] Add a row for the navigation calls (`json.objectFieldAt`,
      `json.arrayElementAt`, `json.cursorParent`, `json.cursorAtPath`).
- [x] Add a row grouping the cursor readers.
- [x] Add a row grouping the object mutators.
- [x] Add a row grouping the array mutators.
- [x] Add a row grouping the delete calls.
- [x] Add a row for `jsonBody NAME` describing the indented-island contract,
      noting it as the second indentation-sensitive exception after
      `htmlBody`.
- [x] Add a row for `json.stringify.<TypeName>` and `json.parse.<TypeName>`
      as the high-level typed entry points.
- [ ] Promote SYNTAX.md:430 from `Partial` to `Impl'd` once the record
      codec generator is live; verify with a feature_test per
      `feedback_verify_impld_claims`.

#### Feature Tests

- [x] Add `SemanticScript/tests/feature/<NNN>_json_document_round_trip.sscript`
      exercising `createDocument` → cursor walk → mutator →
      `serializeDocument`; assert the recovered text equals an expected
      literal, deep-audit pattern from `json_runtime_smoke.sscript`.
- [x] Add a feature test for `createEmptyDocument` that builds a tree
      from scratch and serializes it; assert byte-for-byte equality with
      a known literal.
- [ ] Add one feature test per navigator covering both success and the
      typed-error paths (`PathNotFound`, `WrongType`, `IndexOutOfRange`).
- [ ] Add one feature test per cursor reader, including the
      `missingDefault` propagation path for numeric/bool readers and the
      `ScratchTooSmall` path for `cursorString`.
- [ ] Add one feature test per mutator asserting the post-mutation
      serialization equals an expected literal, then re-reading the
      mutated field to confirm round-trip.
- [ ] Add a feature test for `clearObject` / `clearArray` confirming kind
      preservation and zero length post-clear.
- [ ] Add a feature test for `JsonAccessError.CapacityExceeded` that
      intentionally undersizes the document and asserts the typed error
      reaches a `returnError`.
- [ ] Add an adversarial test parallel to
      `json_runtime_adversarial.sscript` covering deep nesting up to the
      documented bound, control bytes in strings, full RFC 8259 escape
      coverage, and pathological `JsonPath` inputs.
- [ ] Add a `jsonBody` feature test with four cases:
  - [ ] One literal bound to `JsonText`.
  - [ ] One literal bound to a record covering every primitive field type.
  - [ ] One literal that intentionally fails record type-check; assert
        the diagnostic names the offending field.
  - [ ] One literal that intentionally fails JSON syntax; assert the
        diagnostic cites the in-island offset.
- [ ] Add `json.stringify` / `json.parse` round-trip tests, one per
      primitive and one per record codec; each deep-audit asserts the
      lowered behavior cannot be a no-op.
- [x] Confirm zero XFAIL change in
      `python SemanticScript/tests/feature_coverage.py` after each batch.

#### Documentation

- [x] Update `docs/reference/verb-index.md` with every new `json.*` verb.
- [ ] Update `docs/language/operations-dataflow.md` with the end-to-end
      CRUD example matching the design's `renameFirstTodoHandler` flow.
- [x] Add `docs/language/json-crud.md` describing the document lifecycle,
      cursor invalidation contract, path grammar, and stringify/parse
      typed entry points; link from `docs/language/README.md`.
- [x] Update `CHANGELOG.md` with one entry per landed batch
      (types, runtime, lowering, jsonBody, stringify/parse, semlint).
- [x] Update `SemanticScript/std/README.md` JSON section to reference the
      new types/errors/enum and the high-level entry points.

#### App Migration (todo-web-pro)

- [x] Replace the static success bodies in `app/todo-web-pro/main.sem`
      (`healthBodyJson`, `versionBodyJson`, `logoutResponseBody`,
      `deleteOkBody`, `completeOkBody`, `uncompleteOkBody`) with
      `storage local immutable NAME JsonText` rows backed by
      `jsonBody NAME` islands.
- [ ] Replace `userResponseFormat`, `meResponseFormat`,
      `loginResponseFormat`, `createResponseFormat`, and `listRowFormat`
      with record-typed codecs invoked via `json.stringify.<TypeName>`.
- [x] Replace the streaming list serializer at
      `app/todo-web-pro/main.sem:2200-2380` with a single
      `json.createEmptyDocument` + `appendArrayElementObject` loop +
      `json.serializeDocument` pipeline so the unescaped `%s` title bug
      in `listRowFormat` goes away by construction.
- [ ] Replace the per-field `bodyMissing` / `usernameMissing` /
      `passwordMissing` error responses with one `JsonDecodeError` switch
      in front of `json.parse.LoginRequest` and
      `json.parse.RegisterRequest`.
- [x] Run `python app/todo-web-pro/scripts/test_todo_web_pro.py` after
      each migration step to confirm response shapes remain byte-stable.

#### Removal Of Pre-CRUD JSON Surfaces

Once the new surface lands the existing user-facing JSON calls become dead
weight and the project must end with exactly one way to handle JSON. The
underlying C runtime helpers can stay as internal primitives that the new
lowerings reuse — every removal below is at the **language surface**, not
in `sem_json_runtime.c`. Each removal must be paired with equivalent
coverage under the new surface so this is a strict refactor with zero
behavior regressions.

- [ ] Remove the user-facing builder calls from the `json.*` dispatch table
      in `SemanticScript/compiler/semsc.py`.
  - [ ] `json.createBuilder`, `json.destroyBuilder`, `json.finishBuilder`,
        `json.builderLength`.
  - [ ] `json.objectOpen`, `json.objectClose`, `json.arrayOpen`,
        `json.arrayClose`.
  - [ ] `json.fieldInt64`, `json.fieldDouble`, `json.fieldBool`,
        `json.fieldString`, `json.fieldNull`.
  - [ ] `json.elementInt64`, `json.elementDouble`, `json.elementBool`,
        `json.elementString`, `json.elementNull`.
  - [x] Add `SS3624 deprecatedJsonBuilderCall` in
        `SemanticScript/linter/semlint.py` so any lingering source emits a
        block-compile diagnostic with a fix-it pointing at
        `json.stringify.<TypeName>` or `json.createEmptyDocument` +
        `appendArrayElement*`.
  - [ ] Drop `json.destroyBuilder` from `_NATIVE_DEFER_DISPATCH` once no
        user source references it; keep the C symbol as an internal helper
        the new mutator family reuses.
- [ ] Remove the user-facing finder calls from the `json.*` dispatch table.
  - [ ] `json.findString`, `json.findInt64`, `json.findDouble`,
        `json.findBool`, `json.hasField`.
  - [x] Add `SS3625 deprecatedJsonFinderCall` recommending
        `json.createDocument` + `json.cursorAtPath` + `json.cursor*` as
        the replacement.
- [ ] Remove the user-facing primitive encode/decode shortcuts from the
      `json.*` dispatch table.
  - [ ] Delete the `json.encode.<Primitive>` dispatch path
        (current SYNTAX.md:428).
  - [ ] Delete the `json.decode.<Primitive>` dispatch path
        (current SYNTAX.md:429).
  - [ ] Route internal callers through `json.stringify.<Primitive>` /
        `json.parse.<Primitive>` so there is one public spelling and the
        primitive-vs-record dispatch lives in exactly one switch.
- [ ] Remove the user-facing record encode/decode shortcuts.
  - [ ] Delete the `json.encode.RecordTypeName` dispatch path.
  - [ ] Delete the `json.decode.RecordTypeName` dispatch path.
  - [ ] Mark SYNTAX.md:430 as removed with a one-line pointer to the new
        `json.stringify.<TypeName>` / `json.parse.<TypeName>` rows.
- [ ] Remove the obsolete public exports from
      `SemanticScript/std/json/main.sem`.
  - [ ] Drop `exportType standard.json JsonBuilder`; keep `JsonBuilder` as
        an internal-only alias the runtime header uses.
  - [ ] Drop `exportConstant standard.json defaultJsonBuilderCapacityBytes`
        if no surviving public call references it.
  - [ ] Audit every other `JsonFieldName` / `JsonStringValue` /
        `JsonScratchBuffer` export and remove ones that no surviving
        public call still uses.
- [ ] Delete the corresponding SYNTAX.md rows.
  - [ ] Rewrite row 447 to list only the surviving aliases
        (`JsonText`, `JsonScratchBuffer`, `JsonCapacityBytes`,
        `JsonDocument`, `JsonCursor`, `JsonPath`).
  - [ ] Delete row 448 (builder call surface) — replaced by the new
        document-lifecycle + mutator rows.
  - [ ] Delete row 449 (finder call surface) — replaced by the new cursor
        reader rows.
  - [ ] Delete rows 428/429/430 — replaced by `json.stringify.<TypeName>`
        and `json.parse.<TypeName>` rows.
- [ ] Migrate or delete the legacy JSON runtime tests.
  - [ ] `SemanticScript/tests/json_runtime_smoke.sscript`: port every
        assertion to the new CRUD surface, then delete the legacy file.
  - [ ] `SemanticScript/tests/json_runtime_adversarial.sscript`: same
        treatment.
  - [ ] `SemanticScript/runtime/native_json/health_demo.c`: delete if its
        coverage is now redundant with the new `ss_json_document_*` unit
        tests, otherwise rewrite to exercise the document surface.
- [ ] Update VS Code extension surfaces.
  - [ ] Remove the deprecated `json.*` call names from
        `vscode-semanticscript/extension.js` symbol/hover tables.
  - [ ] Remove deprecated highlights from
        `vscode-semanticscript/syntaxes/semanticscript.tmLanguage.json`.
- [ ] Update `docs/reference/verb-index.md` to delete every removed
      `json.*` verb entry.
- [x] Rewrite `docs/optimization-guide.md` JSON sections around
      `json.stringify.<TypeName>` and `json.serializeDocument` so the
      stack-allocated-buffer guidance migrates to the new surface.
- [ ] Replace every legacy call site in the repository.
  - [ ] Grep for `json\.(createBuilder|destroyBuilder|finishBuilder|`
        `builderLength|objectOpen|objectClose|arrayOpen|arrayClose|`
        `field(Int64|Double|Bool|String|Null)|`
        `element(Int64|Double|Bool|String|Null)|`
        `findString|findInt64|findDouble|findBool|hasField|`
        `encode\.|decode\.)` and migrate every match to the new surface.
  - [ ] Confirm the grep returns zero hits in `app/`,
        `SemanticScript/tests/`, `SemanticScript/std/`, `docs/`, and
        `vscode-semanticscript/` before marking removal complete.
- [ ] Audit the rest of this file.
  - [ ] Re-run `grep -ni "json" TODO.md` and confirm every JSON-handling
        bullet lives under
        `### Native JSON CRUD API And jsonBody Literal`.
  - [ ] Delete any orphan JSON bullet found elsewhere and replace it with
        a one-line pointer to this section.

#### Aggressive Testing And Edge Case Coverage

Every test below must follow the deep-audit pattern
(`feedback_verify_impld_claims`): each case asserts a semantic outcome that
would fail under a no-op lowering, not just that the call returns OK. Place
the new tests under `SemanticScript/tests/feature/` so
`feature_coverage.py` picks them up automatically. Each batch finishes only
when `python SemanticScript/tests/feature_coverage.py` is green.

- [ ] Add `SemanticScript/tests/feature/<NNN>_json_document_tokenizer_edges.sscript`
      covering JSON tokenizer corner cases.
  - [ ] Empty object `{}` parses to a zero-field root and serializes
        identically.
  - [ ] Empty array `[]` parses to a zero-element root and serializes
        identically.
  - [ ] Mixed whitespace (spaces, tabs, LF, CR) between every token
        parses to the same tree as the no-whitespace input.
  - [ ] UTF-8 BOM (`EF BB BF`) at the start of input is rejected with
        `JsonAccessError.UnexpectedToken`.
  - [ ] Every standard escape (`\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`,
        `\t`) survives parse + serialize byte-for-byte.
  - [ ] `\uXXXX` for BMP code points round-trips.
  - [ ] Surrogate pair `😀` decodes to one non-BMP character
        and re-serializes to the same surrogate pair.
  - [ ] Lone high surrogate `\uD83D` (no low follow-up) is rejected with
        `EscapeMalformed`.
  - [ ] Lone low surrogate `\uDE00` is rejected with `EscapeMalformed`.
  - [ ] Raw control byte (0x00-0x1F) inside a string literal is rejected.
  - [ ] Trailing comma in an object is rejected.
  - [ ] Trailing comma in an array is rejected.
  - [ ] `//` line comment is rejected.
  - [ ] `/* block comment */` is rejected.
  - [ ] Single-quoted string is rejected.
  - [ ] Unquoted object key is rejected.
  - [ ] Leading zero `05` is rejected.
  - [ ] Plus-signed integer `+5` is rejected.
  - [ ] Hex integer `0x5` is rejected.
  - [ ] Trailing `.` on a float (`5.`) is rejected.
  - [ ] Leading `.` on a float (`.5`) is rejected.
  - [ ] Scientific notation `1e10`, `1E-5`, `1.5e+2` parses correctly.
  - [ ] `NaN`, `Infinity`, `-Infinity` are rejected (RFC 8259 forbids).
  - [ ] Duplicate object keys: confirm the documented last-wins policy
        and assert `SS3626 duplicateJsonObjectKey` fires in semlint.
- [ ] Add boundary/precision tests.
  - [ ] `i64` max (9223372036854775807) round-trips through stringify +
        parse.
  - [ ] `i64` min (-9223372036854775808) round-trips.
  - [ ] `i64` overflow (one past max in source) returns the documented
        atoll-fallback value; pin the choice in SYNTAX.md.
  - [ ] `f64` smallest positive subnormal round-trips within documented
        precision.
  - [ ] `f64` largest finite (`1.7976931348623157e+308`) round-trips.
  - [ ] `-0.0` is distinguishable from `0.0` after round-trip.
  - [ ] 1 MiB string value fits under a 2 MiB `capacity_bytes`.
  - [ ] 1 MiB string under a 512 KiB `capacity_bytes` returns
        `CapacityExceeded`.
  - [ ] Field name at exactly the `FieldNameTooLong` boundary succeeds.
  - [ ] Field name one byte past the boundary returns
        `FieldNameTooLong`.
- [ ] Add nesting-depth tests.
  - [ ] Object nested to the documented bound (currently 16) parses +
        serializes.
  - [ ] Object nested one past the bound is rejected with the
        `JsonAccessError.NestingTooDeep` case (add the case to the error
        enum and the C status table if not already present).
  - [ ] Array nested to the bound parses + serializes.
  - [ ] Array nested one past the bound is rejected.
  - [ ] Mixed object/array nesting to the bound parses + serializes.
- [ ] Add cursor stability tests.
  - [ ] Cursor to `todos[0]` survives `setObjectFieldInt64` on a
        sibling.
  - [ ] Cursor to `todos[0].title` survives a primitive-overwrite on
        the same string (in-place update).
  - [ ] Cursor to `todos[0]` is invalidated by `removeArrayElementAt
        todos 0`; using it triggers `SS3621 staleJsonCursor`.
  - [ ] Cursor to `todos[1]` is invalidated by `insertArrayElement* todos
        0 ...` (shifted-position case).
  - [ ] Cursor to any object field is invalidated by `clearObject` on
        the parent.
  - [ ] Cursor to any array element is invalidated by `clearArray` on
        the parent.
  - [ ] Cursor invalidation propagates through nested containers
        (clear grandparent → all descendants stale).
- [ ] Add mutator semantic tests.
  - [ ] `setObjectFieldString` on a present field overwrites in place
        and preserves key order.
  - [ ] `setObjectFieldString` on an absent field appends and preserves
        existing field order.
  - [ ] `setObjectField*` on a non-object cursor returns `WrongType`.
  - [ ] `appendArrayElement*` on a non-array cursor returns
        `WrongType`.
  - [ ] `insertArrayElement*` at `index == length` appends without
        error.
  - [ ] `insertArrayElement*` at `index > length` returns
        `IndexOutOfRange`.
  - [ ] `insertArrayElement*` at negative index returns
        `IndexOutOfRange`.
  - [ ] `replaceArrayElement*` at out-of-range index returns
        `IndexOutOfRange`.
  - [ ] `removeObjectField` of an absent field returns `1` (status,
        not error).
  - [ ] `removeArrayElementAt` of out-of-range index returns
        `IndexOutOfRange`.
  - [ ] `clearObject` on an already-empty object is a no-op success.
  - [ ] `clearArray` on an already-empty array is a no-op success.
  - [ ] `setObjectFieldJsonText` rejects a syntactically malformed
        sub-document with `UnexpectedToken` and does not partially
        graft.
- [ ] Add path edge case tests.
  - [ ] Empty path `""` returns the root cursor or `MalformedPath` —
        pin the choice in SYNTAX.md and assert it.
  - [ ] `.field` works on a root object.
  - [ ] `[0]` works on a root array.
  - [ ] `.field[0].sub` (three steps) resolves correctly.
  - [ ] `[10][20]` resolves a nested-array lookup.
  - [ ] Unmatched `[` returns `MalformedPath`.
  - [ ] Empty `.` segment returns `MalformedPath`.
  - [ ] Non-numeric index `[abc]` returns `MalformedPath`.
  - [ ] Negative index `[-1]` returns `MalformedPath`
        (negative indexing not supported — pin the contract).
  - [ ] Missing object field returns `PathNotFound` carrying the failing
        segment index in the error payload.
  - [ ] Out-of-range array index returns `IndexOutOfRange`.
- [ ] Add capacity / scratch / OOM tests.
  - [ ] `createDocument` with `capacityBytes` smaller than the input
        text returns `CapacityExceeded` and does not allocate a
        partial document.
  - [ ] `createEmptyDocument` with `capacityBytes == 0` returns
        `CapacityExceeded` on first mutation.
  - [ ] `setObjectFieldString` that would push the arena past
        `capacity_bytes` returns `CapacityExceeded` and leaves the
        document unchanged (transactional mutation).
  - [ ] `serializeDocument` with `scratch_capacity` one byte short of
        the serialized length returns `ScratchTooSmall`.
  - [ ] `cursorString` with `scratch_capacity` one byte short of the
        unescaped value plus NUL returns `ScratchTooSmall`.
  - [ ] `destroyDocument` on NULL does not crash.
  - [ ] Double-destroy is caught by a debug assert and does not
        corrupt heap.
  - [ ] Defer cleanup runs `destroyDocument` exactly once per exit
        path — verify under valgrind in CI.
- [ ] Add `jsonBody` literal edge case tests
      (`SemanticScript/tests/feature/<NNN>_json_body_*`).
  - [ ] Empty island after `jsonBody NAME` is rejected with
        `parseDiagnosticEmptyJsonBody`.
  - [ ] Two `jsonBody` rows targeting the same `storage` name are
        rejected with `duplicateJsonBodyBinding`.
  - [ ] `jsonBody` row whose target storage already has an inline value
        is rejected with `jsonBodyTargetAlreadyValued`.
  - [ ] `jsonBody` row with no matching storage row is rejected with
        `orphanJsonBody`.
  - [ ] `jsonBody` row whose storage type is neither `JsonText` nor a
        declared record is rejected with `jsonBodyUnsupportedType`.
  - [ ] Record-typed island with a missing required field surfaces a
        diagnostic naming the field.
  - [ ] Record-typed island with an extra unknown key is rejected.
  - [ ] Record-typed island with a wrong-typed field surfaces a
        diagnostic naming the expected vs actual JSON kind.
  - [ ] `recordFieldJsonName` override is honored when the JSON key
        differs from the record field identifier.
  - [ ] `recordFieldJsonOmitWhen empty` accepts an absent string field
        and defaults to `""`.
  - [ ] `recordFieldJsonOmitWhen null` accepts an explicit JSON `null`.
  - [ ] `recordFieldJsonOmitWhen false` accepts an absent bool field
        and defaults to `false`.
  - [ ] `recordFieldJsonOmitWhen zero` accepts an absent numeric field
        and defaults to `0`.
  - [ ] Nested record literal inside an outer record literal type-checks
        recursively.
  - [ ] Multi-line island with deeply nested objects parses identically
        after `semfmt`.
- [ ] Add `json.stringify` / `json.parse` round-trip tests.
  - [ ] Stringify and re-parse for every primitive type
        (I64, Bool, F64, String, width-specific C integers, F32).
  - [ ] Stringify and re-parse for a record with every primitive field
        type at once.
  - [ ] Stringify and re-parse for a record carrying an array-of-records
        field.
  - [ ] Stringify a record with `recordFieldJsonOmitWhen` fields and
        confirm omitted keys are absent from output.
  - [ ] Stringify a string containing every standard escape and a
        non-BMP character; re-parse equals the original byte-for-byte.
  - [ ] Stringify the empty string; re-parse equals the empty string.
  - [ ] Parse with an unknown key surfaces
        `JsonDecodeError.UnknownKey` when the codec's policy is strict,
        or is ignored when lenient — pin the per-codec policy in
        `jsonCodec` metadata.
  - [ ] Parse with a missing required key surfaces `MissingRequired`
        naming the field.
  - [ ] Parse with a wrong-typed value surfaces `WrongType` naming the
        field.
  - [ ] Parse a record whose JSON keys use `recordFieldJsonName`
        overrides decodes correctly.
- [ ] Add single-thread concurrency-shape tests.
  - [ ] Two `JsonDocument` handles open at once, each with its own
        cursor, do not alias trees.
  - [ ] Multi-document defer order runs cleanup in reverse declaration
        order and frees both arenas.
  - [ ] A cursor produced from `documentA` and passed against
        `documentB` is rejected with
        `JsonAccessError.CursorForeignToDocument` (add the error case
        if not already present).
- [ ] Add performance baseline tests.
  - [ ] Document with 10,000 fields opens, walks, and serializes inside
        a per-call wall-clock budget published in
        `docs/optimization-guide.md`.
  - [ ] Array with 10,000 elements appends inside budget.
  - [ ] Nesting at exactly the documented bound serializes inside
        budget.
  - [ ] Repeated `setObjectFieldString` on the same key 1,000 times
        does not leak the arena: heap bytes-used returns to baseline
        after a `clearObject`.
- [ ] Add cross-platform byte-equality tests.
  - [ ] Serialize the same document on Windows + Linux CI; assert
        byte-for-byte equality.
  - [ ] LF / CRLF inside a JSON string literal survives parse +
        serialize unchanged on both platforms.
  - [ ] File I/O round-trip (write serialized output to disk, read
        back, re-parse, structural equality) on both platforms.
- [x] Add semlint rule edge case tests in
      `SemanticScript/linter/test_semlint.py`.
  - [x] `SS3620 unguardedJsonAccess` fires when a cursor is used
        before `branchIfError`.
  - [x] `SS3620` is silent when the cursor comes from
        `json.documentRoot` (exempt path).
  - [x] `SS3621 staleJsonCursor` fires once per structural mutator
        when the cursor is used after.
  - [x] `SS3621` is silent when a fresh cursor is rebound after the
        mutator.
  - [x] `SS3622 malformedJsonPath` fires for the malformed-path corpus
        used above.
  - [x] `SS3622` is silent for a syntactically valid path even when the
        path would resolve to a missing field at runtime (lint is
        syntactic, not semantic).
  - [x] `SS3623 unescapedJsonStringInterpolation` fires for the
        `listRowFormat`-style heuristic.
  - [x] `SS3623` is silent for an `snprintf` outside any JSON context
        (false-positive guard).
  - [x] `SS3624 deprecatedJsonBuilderCall` and
        `SS3625 deprecatedJsonFinderCall` fire on the legacy call
        names from the removal section and block compilation.
- [ ] Add fuzz coverage.
  - [ ] Add `SemanticScript/tests/fuzz/json_document_fuzz.py` that
        drives random JSON inputs through `createDocument`; assert no
        crash, no leak, and round-trip equality where parse succeeds.
  - [ ] Add an output-side fuzzer that emits random typed values
        through `json.stringify` and re-parses through `json.parse`;
        assert round-trip equality.
  - [ ] Run each fuzzer for a fixed wall-clock budget in CI and fail
        on any non-zero exit from the driver.
  - [ ] Seed the corpus with the malformed-surrogate, deep-nesting,
        big-string, and full-escape cases above.
- [ ] Add memory-safety coverage.
  - [ ] Run the full feature_coverage suite under
        `valgrind --leak-check=full` on Linux CI and assert zero leaks.
  - [ ] Run the full suite under AddressSanitizer on supported
        platforms and assert no errors.
  - [ ] Add a leak regression test: create 1,000 documents in a tight
        loop, destroy each via `defer`, assert heap usage returns to
        baseline within a documented tolerance.
- [ ] Add migration regression coverage.
  - [ ] Diff every assertion in `json_runtime_smoke.sscript` against
        the equivalent assertion in the new feature tests; confirm
        zero coverage gaps before deleting the legacy test.
  - [ ] Same diff against `json_runtime_adversarial.sscript`.
  - [ ] `python app/todo-web-pro/scripts/test_todo_web_pro.py` passes
        identically before and after the app migration, with
        byte-stable response bodies; archive the pre/post diff in the
        CHANGELOG entry for the migration.

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

- [x] Define and implement the build-tape parser surface.
  - [x] Add parser support for `buildProject`.
  - [x] Add parser support for `modulePath`.
  - [x] Add parser support for `languageVersion`.
  - [x] Add parser support for `projectVersion`.
  - [x] Add parser support for `projectLicense`.
  - [x] Add parser support for `sourceRoot`.
  - [x] Add parser support for `mainFile`.
  - [x] Add parser support for `mainOperation`.
  - [x] Add parser support for `testPattern`.
  - [x] Add parser support for `dependency`.
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
  - [x] Search current directory and ancestors for `build.sem`.
  - [x] Support single-file mode when no `build.sem` exists.
  - [ ] Reject ambiguous nested project roots with a source-located diagnostic.
  - [x] Preserve source locations for every build-tape row.
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
  - [x] Add compiler project-mode entrypoint.
  - [x] Pass build profile from `build.sem` into existing compiler options.
  - [x] Pass runtime checks from `build.sem` into existing compiler options.
  - [x] Pass LLVM IR persistence from `build.sem` into existing compiler
        options.
  - [x] Resolve native output from `build.sem`.
  - [x] Add focused tests for valid and invalid build tapes.
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
- [x] Enforce export visibility rules.
  - [x] Treat symbols as private unless exported.
  - [x] Restrict export rows to module source files.
  - [x] Require exported symbols to belong to the same registered module.
  - [x] Reject unknown exports.
  - [x] Reject duplicate exports.
  - [x] Reject mutable module storage exports.
  - [x] Reject local/shared state exports.
  - [x] Allow immutable module storage through `exportConstant`.
- [x] Build exported operation contracts.
  - [x] Extract inputs.
  - [x] Extract outputs.
  - [x] Extract effects.
  - [x] Extract capability or authority coverage.
  - [x] Extract failure types and error cases.
  - [x] Extract async/timing metadata.
  - [x] Extract memory metadata.
  - [x] Preserve source locations for every exported contract edge.
- [x] Build exported type/error/capability contracts.
  - [x] Extract record fields and invariants for exported record types.
  - [x] Extract enum cases for exported enum types.
  - [x] Extract error cases for exported error types.
  - [x] Extract capability effect path and access mode.
  - [x] Extract constant type and value/trust metadata.
- [x] Add export quality diagnostics.
  - [x] Warn when exported operations lack `purpose`.
  - [x] Warn when exported operations have hidden or undeclared effects.
  - [x] Warn when exported operations wrap dependency behavior without
        ownership/purpose context.
  - [x] Warn when exported names are overly generic.
- [x] Add export tests.
  - [x] Exported operation happy path.
  - [x] Private symbol rejected from external module.
  - [x] Exported immutable constant accepted.
  - [x] Mutable storage export rejected.
  - [x] Exported error cases visible to consumers.
  - [x] Exported capability visible to consumers.
- [x] Agent 3 handoff notes.
  - [x] Document contract tape shape for Agent 4 and Agent 5.
  - [x] Document export diagnostics for Agent 6 docs.

#### Agent 4 - Imports, Qualified Names, And Singular Imports

Owned scope: module imports, qualified access, singular import aliases, shadowing
rules, and imported contract lookup.

- [ ] Refine module import syntax.
  - [x] Decide compatibility path for current `importModule DOTTED.PATH [as
        ALIAS]`.
  - [x] Define preferred `importModule ALIAS MODULE_PATH` shape if adopted.
  - [ ] Require aliases for external dependency modules.
  - [x] Reject alias collisions.
  - [x] Reject imports not reachable from `build.sem`.
- [x] Implement qualified references.
  - [x] Resolve `moduleAlias.operationName` call targets.
  - [x] Resolve `moduleAlias.TypeName` type references.
  - [x] Resolve `moduleAlias.ErrorType` error references.
  - [x] Resolve `moduleAlias.CapabilityName` capability references.
  - [x] Reject qualified access to private symbols.
  - [x] Reject qualified access to mutable storage.
  - [x] Preserve qualified source names in diagnostics.
- [x] Implement singular import rows.
  - [x] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [x] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [x] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [x] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [x] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [x] Reject wildcard imports.
  - [x] Reject implicit singular imports.
- [x] Enforce alias and shadowing rules.
  - [x] Reject singular imports that shadow local declarations.
  - [x] Reject singular imports that shadow other imports.
  - [x] Reject ambiguous unqualified references.
  - [x] Warn when many singular imports from one module reduce clarity.
  - [x] Warn when local alias hides provider domain context.
- [x] Carry imported contracts through call checking.
  - [x] Imported operation calls use exported input contract.
  - [x] Imported operation calls use exported output contract.
  - [x] Imported operation calls expose exported effect contract.
  - [x] Imported types carry record/enum metadata.
  - [x] Imported errors carry error cases.
  - [x] Imported capabilities carry effect path/access metadata.
- [x] Add import tests.
  - [x] Qualified operation call happy path.
  - [x] Qualified type/error/capability references.
  - [x] Singular operation/type/error/capability/constant imports.
  - [x] Private symbol rejected.
  - [x] Alias collision rejected.
  - [x] Wildcard import rejected.
  - [x] Import cycle rejected.
- [x] Agent 4 handoff notes.
  - [x] Document import resolution API for Agent 5 dependency cache work.
  - [x] Document compatibility edge cases for Agent 6 migration docs.

#### Agent 5 - Dependency Fetching, Cache, Locking, And Cross-Module Authority

Owned scope: Go-style dependency fetching, `.semcache/`, lock behavior,
dependency contract loading, and cross-module effect/capability propagation.

- [ ] Define dependency fetch model.
  - [ ] Add `sem get MODULE_PATH@VERSION_OR_REF` design notes.
  - [ ] Define `sem get` as a tool-driver command, not a compiler backend
        phase.
  - [ ] Define `sem build` dependency preparation order: parse `build.sem`,
        resolve/fetch/cache dependencies, load dependency contracts, then call
        `semsc`.
  - [ ] Define whether direct `semsc build.sem` may fetch from the network or
        must remain validation/compile-only.
  - [ ] Define the source-level fetch API names: keep build-time dependency
        fetch as `dependencyFetch`; reserve runtime HTTP client calls for a
        separate `http.client*` or `net.fetch*` surface.
  - [x] Support GitHub module paths first.
  - [ ] Define GitHub archive URL construction from `OWNER/REPO REF`.
  - [ ] Define GitHub API calls needed to resolve a tag or branch to an exact
        commit.
  - [ ] Decide whether GitHub fetching uses anonymous HTTPS first and optional
        token auth later.
  - [ ] Keep grammar generic enough for non-GitHub Git paths.
  - [x] Support local path dependencies.
  - [x] Support pinned tags.
  - [x] Support pinned commits.
  - [ ] Distinguish immutable refs (`commit:<sha>`) from mutable refs
        (`main`, branch names, moving tags).
  - [ ] Reject floating branches in release builds unless explicitly allowed.
  - [ ] Define a dev-only override for intentionally floating dependency refs.
  - [ ] Define diagnostics when `dependencyFetch` exists without a matching
        `dependency` row.
- [ ] Implement dependency preparation before compile.
  - [ ] Add a dependency preparation module under the tooling layer, not inside
        LLVM/codegen.
  - [ ] Parse the active `buildProject` and collect `dependency`,
        `dependencyFetch`, `dependencyCache`, `dependencyLock`, and
        `dependencyIntegrity` rows.
  - [ ] Normalize dependency aliases and reject duplicate aliases before any
        network access.
  - [ ] Resolve local/path dependencies without network access.
  - [ ] Resolve GitHub dependencies through archive download or GitHub API.
  - [ ] Resolve generic HTTPS archive dependencies through direct download.
  - [ ] Materialize fetched sources into cache before compiler import
        resolution.
  - [ ] Return a structured dependency-resolution report for agent logs.
  - [ ] Ensure dependency preparation is idempotent for unchanged lock/cache
        state.
- [ ] Implement `.semcache/` behavior.
  - [ ] Store cloned dependencies outside source roots.
  - [ ] Define default project cache path as `.semcache/` beside `build.sem`.
  - [ ] Define exact cache directory layout for GitHub dependencies.
  - [ ] Store GitHub archive downloads under a content-addressed blob path.
  - [ ] Store extracted dependency source under a resolved-commit path.
  - [ ] Store local/path dependency entries as references, not copied source,
        unless vendoring is explicitly requested later.
  - [x] Keep `.semcache/` ignored by git.
  - [ ] Never mutate cached dependency source during normal builds.
  - [ ] Treat cached dependency source as read-only after extraction.
  - [ ] Write downloads to a temp file and atomically move them into cache.
  - [ ] Use per-dependency lock files to avoid two builds writing the same
        cache entry at once.
  - [ ] Detect cache corruption.
  - [ ] Recompute archive checksum before trusting a cached archive.
  - [ ] Recompute extracted tree checksum or manifest hash before trusting a
        cached source tree.
  - [ ] Delete or quarantine corrupt cache entries instead of compiling them.
  - [ ] Support cache refresh through explicit update commands.
  - [ ] Make normal builds reuse cache and lock data without refreshing.
  - [ ] Add a clear diagnostic when cache is missing and network is disabled.
- [ ] Define and implement lock data.
  - [x] Decide between `sem.lock`, `build.lock.sem`, or another SemanticScript
        lock tape.
  - [ ] Define `sem.lock` as a SemanticScript tape, not TOML/JSON/YAML.
  - [ ] Define top-level lock identity rows such as `lockProject`,
        `lockGeneratedBy`, and `lockFormatVersion`.
  - [ ] Define one locked dependency block per dependency alias.
  - [ ] Record module path.
  - [ ] Record requested version/ref.
  - [ ] Record resolved commit.
  - [ ] Record checksum.
  - [ ] Record dependency module root.
  - [ ] Record transitive dependencies.
  - [ ] Record fetch kind (`github`, `http`, or `local`).
  - [ ] Record source URL or GitHub `OWNER/REPO`.
  - [ ] Record archive URL used for the fetch.
  - [ ] Record archive SHA-256.
  - [ ] Record extracted source tree digest.
  - [ ] Record dependency `build.sem` path inside the cached source.
  - [ ] Record dependency language version and module path from its build tape.
  - [ ] Record lock timestamp only if it will not break reproducible diffs; if
        it is included, keep it in a clearly non-semantic metadata row.
  - [ ] Make locked builds avoid network access.
  - [ ] In prod/release profile, require lock rows before any remote fetch.
  - [ ] Fail if a locked dependency resolves to different bytes than the lock
        checksum.
  - [ ] Fail if a locked GitHub dependency resolves to a different commit.
  - [ ] Add a `--locked` or equivalent mode that forbids lock mutation.
  - [ ] Add an update mode that is explicitly allowed to mutate `sem.lock`.
- [ ] Load dependency contract tapes.
  - [ ] Read dependency `build.sem`.
  - [ ] Read dependency module registry rows from `build.sem`.
  - [ ] Read dependency module-source export rows and exported contract tape.
  - [ ] Support resolving registered dependency modules from the cached source
        root.
  - [ ] Merge dependency export contract indexes into import resolution without
        treating dependency private symbols as local project symbols.
  - [ ] Reject dependencies missing required module metadata.
  - [ ] Reject dependencies whose `modulePath` does not match the requested
        dependency module path.
  - [ ] Reject dependencies whose registered module source cannot be selected
        deterministically.
  - [ ] Surface dependency diagnostics with dependency source paths.
  - [ ] Include dependency alias, module path, requested ref, resolved commit,
        and cache path in diagnostics.
  - [ ] Ensure dependency diagnostics render cleanly in `--format agent`.
- [ ] Implement cross-module effect and authority propagation.
  - [x] Caller diagnostics cite imported operation effects.
  - [x] Caller declares effects triggered by imported calls.
  - [ ] Caller proves capability or authority coverage.
  - [ ] Imported capabilities preserve hierarchy.
  - [ ] Warn on broad capability re-export without rationale.
  - [x] Ensure file/network/database/observability effects do not disappear
        through wrappers.
- [ ] Add dependency/effect tests.
  - [ ] Local path dependency.
  - [ ] Local path dependency resolves without touching network.
  - [x] GitHub tag/commit dependency if network tests are allowed.
  - [ ] GitHub archive URL is constructed correctly.
  - [ ] GitHub tag resolves to exact commit.
  - [ ] GitHub commit ref skips mutable-ref resolution.
  - [ ] HTTPS archive dependency downloads and verifies checksum.
  - [ ] Locked build avoids network.
  - [ ] Locked prod build fails when lock is missing.
  - [ ] Locked build fails on checksum mismatch.
  - [ ] Cached archive corruption is detected.
  - [ ] Cached extracted tree corruption is detected.
  - [ ] Missing dependency `build.sem`.
  - [ ] Missing dependency module contract rows in `build.sem`.
  - [ ] Dependency `modulePath` mismatch diagnostic.
  - [ ] Dependency registered module source missing diagnostic.
  - [ ] Imported operation with filesystem effect.
  - [x] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
- [ ] Agent 5 handoff notes.
  - [x] Document lock format for Agent 6 docs.
  - [x] Document cache/authority APIs for final integration.

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
- [x] Update VS Code extension.
  - [x] Highlight build-tape verbs.
  - [x] Highlight module metadata verbs.
  - [x] Highlight export/import verbs.
  - [x] Add hover text for new verbs.
  - [x] Add completions for new verbs.
  - [x] Add document symbols for `buildProject`, `module`, exports, and
        imports.
  - [x] Add linter/diagnostic support when new diagnostics exist.
- [ ] Add migration checks.
  - [ ] Audit existing `module` rows.
  - [ ] Audit existing `importModule` rows.
  - [ ] Identify samples needing `build.sem`.
  - [ ] Identify stdlib modules needing relay entries in `std/module.sem`.
  - [ ] Add staged compatibility warnings before hard errors.
- [ ] Build integration harness.
  - [x] End-to-end console project build.
  - [ ] End-to-end web project build.
  - [x] End-to-end module import/export build.
  - [x] End-to-end singular import build.
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
        the application project model; `std/module.sem` is the library relay exception.
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
  - [x] Explain how root source files differ from folder modules.
  - [x] Explain how `main.sem` and `build.sem` interact.
  - [ ] Explain how tests are discovered from `*.test.sem`.
  - [ ] Explain how generated artifacts stay outside source control.
- [ ] Add examples under `samples/` or `app/`.
  - [x] Minimal `build.sem` plus `main.sem` console sample.
  - [ ] Multi-folder module sample with every module registered in `build.sem`.
  - [ ] Webserver sample using `build.sem`, `main.sem`, and folder modules.
  - [ ] Library sample with exports and import consumers.
  - [ ] Tests using `*.test.sem` next to the source folder they validate.

### `build.sem` Build Tape

- [x] Define the `build.sem` grammar as SemanticScript source, not a sidecar
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
  - [x] Add `dependency PROJECT_NAME ALIAS MODULE_PATH VERSION_OR_REF`.
  - [x] Add `dependencySource PROJECT_NAME ALIAS SOURCE_KIND SOURCE_TEXT`.
  - [x] Add `dependencyIntegrity PROJECT_NAME ALIAS INTEGRITY_TEXT`.
  - [x] Add `buildProfile PROJECT_NAME dev|prod`.
  - [x] Add `optLevel PROJECT_NAME 0|1|2|3`.
  - [x] Add `runtimeChecks PROJECT_NAME off|traps|panic`.
  - [x] Add `persistLlvmIr PROJECT_NAME auto|yes|no`.
  - [x] Add `nativeOutput PROJECT_NAME PATH_TEXT`.
  - [x] Add `targetRuntime PROJECT_NAME nativeExe|webServer|library`.
  - [x] Reserve `comptimeOperation PROJECT_NAME OPERATION_NAME` for 2.0.
- [x] Decide whether `build.sem` accepts only build verbs or the full language.
  - [x] If restricted, reject executable body rows in `build.sem`.
  - [ ] If full language, define which rows execute at compile time.
  - [x] Document that 1.x treats `build.sem` as declarative build tape.
  - [x] Document that 2.0 can widen this into comptime execution.
- [ ] Implement `build.sem` discovery.
  - [x] Search current directory and ancestors for `build.sem`.
  - [ ] Stop at repository root if detectable.
  - [ ] Emit a clear diagnostic when multiple candidate project roots compete.
  - [x] Support single-file mode when no `build.sem` exists.
  - [x] Never silently create `build.sem`.
- [ ] Implement `build.sem` parsing.
  - [x] Add parser rows for every current build-tape verb.
  - [x] Preserve source locations for build diagnostics.
  - [ ] Reject unknown build-tape verbs with a suggestion.
  - [x] Reject missing project names.
  - [x] Reject duplicate `buildProject` names in one build file.
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
  - [x] Add `semsc.py build.sem --project-build` or equivalent project mode.
  - [x] Make `sem build` call compiler project mode once the `sem` driver
        exists.
  - [x] Resolve all source roots before parsing application modules.
  - [x] Resolve build profile from `build.sem`.
  - [x] Resolve runtime checks from `build.sem`.
  - [x] Resolve LLVM IR persistence from `build.sem`.
  - [x] Resolve native output path from `build.sem`.
  - [x] Emit diagnostics in terms of `build.sem` rows when build config fails.
- [ ] Add build-tape tests.
  - [x] Minimal valid `build.sem`.
  - [x] Missing `modulePath`.
  - [ ] Duplicate `mainFile`.
  - [ ] Invalid dependency alias.
  - [ ] Invalid module path.
  - [x] Missing `main.sem`.
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
  - [x] Symbols are private unless exported.
  - [x] Export rows may only appear in module source files.
  - [x] Exported symbols must be declared in the same registered module.
  - [ ] Exported operations must have complete `input` and `output` contracts.
  - [x] Exported operations must declare all effects.
  - [x] Exported operations with effects must prove capability or authority
        coverage.
  - [x] Exported operations should have `purpose`.
  - [ ] Exported operations should have `warning` when they expose nullable,
        unsafe, or external runtime behavior.
  - [ ] Exported types should have invariants where useful.
  - [ ] Exported constants must be immutable module storage.
  - [x] Reject export of mutable module storage.
  - [x] Reject export of local storage.
  - [x] Reject export of shared state values directly.
  - [x] Require mutation to cross modules through exported operations.
- [x] Build a module contract tape.
  - [x] Extract exported operation inputs.
  - [x] Extract exported operation outputs.
  - [x] Extract exported operation effects.
  - [x] Extract exported operation capability requirements.
  - [x] Extract exported operation failure types.
  - [x] Extract exported operation async/timing metadata.
  - [x] Extract exported operation memory metadata.
  - [x] Extract exported type/record fields.
  - [x] Extract exported enum and error cases.
  - [x] Extract exported constants and literal trust metadata.
  - [x] Preserve source locations for every exported contract edge.
- [ ] Validate exports.
  - [x] Reject unknown exported symbols.
  - [x] Reject duplicate exports.
  - [ ] Reject export cycles if a public facade imports and re-exports itself.
  - [x] Warn when exported operation names are too generic.
  - [ ] Warn when exported symbols have no module ownership context.
  - [x] Warn when exported operations hide dependencies through wrapper names
        without purpose explaining the abstraction.
- [x] Add export tests.
  - [x] Exported operation happy path.
  - [x] Unknown exported operation.
  - [x] Exported private mutable state rejected.
  - [x] Exported immutable constant accepted.
  - [x] Exported error cases available to consumers.
  - [x] Exported capability available to consumers.
  - [x] Contract tape includes effects and failures.

### Module Imports And Qualified Calls

- [ ] Define canonical module import syntax.
  - [x] Keep current `importModule DOTTED.PATH [as ALIAS]` for 1.x
        compatibility.
  - [x] Prefer `importModule ALIAS MODULE_PATH` for new project modules if the
        grammar can migrate without ambiguity.
  - [x] Document aliases as local source names, not package identities.
  - [ ] Require aliases for external dependencies.
  - [x] Reject alias collisions with local declarations.
  - [x] Reject imports of modules not reachable from `build.sem`.
- [x] Define qualified name usage.
  - [x] Allow `moduleAlias.operationName` call targets.
  - [x] Allow `moduleAlias.TypeName` type references.
  - [x] Allow `moduleAlias.ErrorType` error references.
  - [x] Allow `moduleAlias.CapabilityName` capability references only where
        capability imports are legal.
  - [x] Reject qualified access to non-exported symbols.
  - [x] Reject qualified access to mutable storage.
  - [x] Preserve qualified names in diagnostics.
- [ ] Implement module import resolution.
  - [x] Resolve same-project registered modules.
  - [ ] Resolve dependency modules from `.semcache/`.
  - [x] Resolve standard-library modules.
  - [ ] Reject imports that bypass `build.sem` dependency declarations.
  - [ ] Reject ambiguous module paths.
  - [ ] Cache resolved contract tapes.
  - [x] Preserve source location of import rows for diagnostics.
- [ ] Add import diagnostics.
  - [x] Unknown module path.
  - [x] Unknown alias.
  - [x] Duplicate alias.
  - [x] Import cycle.
  - [ ] Imported module lacks module contract rows in `build.sem`.
  - [ ] Imported module has no exports.
  - [x] Imported symbol exists but is private.
  - [ ] Imported operation contract has undeclared effects.
- [ ] Add import tests.
  - [x] Qualified call to exported operation.
  - [x] Qualified type reference.
  - [x] Qualified error reference.
  - [x] Private symbol rejected.
  - [x] Alias collision rejected.
  - [x] Import cycle rejected.
  - [x] Standard-library import.
  - [ ] Dependency import from cache.

### Singular Imports

- [x] Define singular import rows.
  - [x] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [x] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [x] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [x] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [x] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [x] Explicitly reject wildcard imports.
  - [x] Explicitly reject implicit singular imports by capitalization or naming.
- [x] Define singular import semantics.
  - [x] Singular imports create local aliases only.
  - [x] Singular imports do not change the provider module's contract.
  - [x] Singular operation imports bring the full operation contract.
  - [x] Singular type imports bring related record/enum layout metadata.
  - [x] Singular error imports bring exported error cases.
  - [x] Singular capability imports bring effect path and access metadata.
  - [x] Singular constant imports bring immutable value/type metadata.
  - [x] Singular imports must not shadow local declarations.
  - [x] Singular imports must not shadow other imports.
  - [x] Singular imports should be linted when they make the source less clear
        than qualified names.
- [ ] Add singular import lint guidance.
  - [x] Prefer qualified calls for most module usage.
  - [ ] Allow singular imports for central domain operations used repeatedly.
  - [ ] Allow singular imports for facade modules that intentionally re-export
        public API.
  - [x] Warn when a file imports many singular operations from the same module.
  - [x] Warn when singular local alias hides the provider domain.
  - [ ] Require rationale for aliasing two different modules into similar local
        names.
- [x] Add singular import tests.
  - [x] Singular operation import happy path.
  - [x] Singular type import happy path.
  - [x] Singular error import happy path.
  - [x] Singular capability import happy path.
  - [x] Singular constant import happy path.
  - [x] Unknown exported symbol rejected.
  - [x] Shadowing local symbol rejected.
  - [x] Wildcard import rejected.

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
  - [x] Imported capability aliases must preserve effect path and access mode.
  - [ ] Hierarchical capability coverage works across modules.
  - [ ] Narrow imported capabilities should remain narrow.
  - [ ] Reject broad capability re-export without a rationale.
- [ ] Define dependency effect propagation.
  - [ ] External dependency effects in a provider module must appear in exported
        operation contracts if the exported operation can trigger them.
  - [ ] Wrapper/facade modules may narrow or rename effects only with explicit
        metadata explaining the boundary.
  - [x] Observability effects must cross module boundaries like other effects.
  - [x] Network/file/database effects must never disappear through import.
- [ ] Add cross-module effect tests.
  - [ ] Imported operation with console effect.
  - [ ] Imported operation with filesystem effect.
  - [ ] Imported operation with HTTP response effect.
  - [ ] Imported operation with broad provider capability and narrow caller
        effect.
  - [x] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
  - [ ] Re-exported broad capability warning.

### Dependency Fetching And Cache

- [ ] Define Go-style module fetching.
  - [ ] Add `sem get MODULE_PATH@VERSION_OR_REF`.
  - [ ] Keep `sem get` in the SemanticScript tool driver layer so real network
        IO does not couple directly to LLVM/codegen.
  - [ ] Define `sem build` dependency-prep order before invoking `semsc`.
  - [ ] Decide whether bare `semsc build.sem` is allowed to fetch or only
        validates dependency rows and compiles already-resolved sources.
  - [ ] Define agent-readable fetch logs with alias, module path, requested ref,
        resolved commit, cache path, lock path, and failure reason.
  - [x] Support GitHub module paths.
  - [ ] Resolve GitHub `OWNER/REPO REF` to a deterministic archive URL.
  - [ ] Resolve GitHub tags and branches through API metadata before download.
  - [ ] Support anonymous GitHub fetch first.
  - [ ] Add optional GitHub token support later without storing tokens in
        `build.sem` or `sem.lock`.
  - [ ] Support generic Git URLs later without making GitHub special in the
        language grammar.
  - [x] Support local path dependencies for development.
  - [x] Support pinned tags.
  - [x] Support pinned commits.
  - [ ] Classify refs as immutable commit pins, mutable tags, mutable branches,
        or local paths.
  - [ ] Reject floating branches in release builds unless explicitly allowed.
- [ ] Define build-time fetch API boundaries.
  - [ ] Treat `dependencyFetch` as the build-time dependency API.
  - [ ] Reserve runtime outbound HTTP calls for a separate future API such as
        `http.clientRequest`, `http.clientResponseText`, or `net.fetchText`.
  - [ ] Do not let runtime HTTP client naming collide with server-side
        `http.request*` and `http.response*` APIs.
  - [ ] Define capability paths for future runtime fetch calls, such as
        `network.http.client read/write`.
  - [ ] Require any future runtime fetch wrapper to export effects the same way
        dependency-imported operations do.
- [ ] Implement dependency resolution phase.
  - [ ] Add a resolver that reads `build.sem` dependency rows into structured
        dependency request records.
  - [ ] Validate alias uniqueness and source/fetch/integrity coverage before
        touching disk or network.
  - [ ] Resolve local path dependencies directly from disk.
  - [ ] Resolve GitHub dependencies through archive download as the first
        implementation strategy.
  - [ ] Decide whether to support `git clone` later for submodules and unusual
        refs.
  - [ ] Resolve HTTPS archive dependencies through direct download.
  - [ ] Verify downloaded bytes before extraction.
  - [ ] Extract into a temporary directory, verify extracted source, then
        atomically move into cache.
  - [ ] Return dependency roots to import resolution as read-only source roots.
- [ ] Define `.semcache/`.
  - [ ] Store cloned dependencies outside source roots.
  - [ ] Use `.semcache/` beside `build.sem` as the default project-local cache.
  - [ ] Define cache subfolders for source archives, extracted trees, temp
        downloads, and per-alias metadata.
  - [ ] Use content-addressed archive filenames to avoid ref-name collisions.
  - [ ] Use resolved commits in extracted tree paths for GitHub dependencies.
  - [ ] Keep local path dependencies as external references rather than cached
        copies during normal dev builds.
  - [x] Keep `.semcache/` ignored by git.
  - [ ] Support user-global cache later if useful.
  - [ ] Support project-local cache for reproducible experiments.
  - [ ] Do not modify cached dependency sources during normal builds.
  - [ ] Write cache entries atomically.
  - [ ] Add lock files or equivalent process coordination for concurrent builds.
  - [ ] Rehash cached archives before reuse.
  - [ ] Rehash extracted source trees before reuse.
  - [ ] Quarantine corrupt cache entries and emit a repair command suggestion.
- [ ] Define lockfile behavior without TOML.
  - [x] Decide whether lock data lives in `sem.lock`, `build.lock.sem`, or
        another SemanticScript tape file.
  - [ ] Define `sem.lock` as the canonical SemanticScript lock tape.
  - [ ] Define lock header rows: `lockProject`, `lockFormatVersion`,
        `lockGeneratedBy`, and optional non-semantic metadata.
  - [ ] Define locked dependency rows for alias, module path, requested ref,
        resolved commit, fetch kind, source URL, archive URL, archive checksum,
        extracted tree digest, and dependency root.
  - [ ] Record module path.
  - [ ] Record requested version/ref.
  - [ ] Record resolved commit.
  - [ ] Record checksum.
  - [ ] Record dependency module root.
  - [ ] Record transitive dependencies.
  - [ ] Make normal builds use locked versions without hitting the network.
  - [ ] Add locked mode that fails if `sem.lock` is missing or stale.
  - [ ] Add update mode that may rewrite `sem.lock`.
  - [ ] Fail if remote source bytes or resolved commits disagree with lock
        data.
  - [ ] Keep lock diffs stable and reviewable by sorting dependencies
        deterministically.
- [ ] Implement dependency update flows.
  - [ ] `sem get` adds or updates dependency rows in `build.sem`.
  - [ ] `sem get` fetches dependency source into `.semcache/`.
  - [ ] `sem get` writes or updates the matching `sem.lock` rows.
  - [ ] `sem get` validates the dependency's `build.sem` before accepting it.
  - [ ] `sem mod tidy` removes unused dependency rows.
  - [ ] `sem mod tidy` keeps lock rows only for reachable dependencies.
  - [ ] `sem update ALIAS` updates one dependency.
  - [ ] `sem update ALIAS` preserves version constraints when possible.
  - [ ] `sem update` updates all dependencies within allowed constraints.
  - [ ] `sem update` refuses floating release updates without an explicit flag.
  - [ ] `sem vendor` copies dependencies into a vendored tree if that workflow
        is later accepted.
- [ ] Integrate fetched dependencies with module imports.
  - [ ] Locate dependency `build.sem` under each cached dependency root.
  - [ ] Read dependency `registerModule` rows from cached `build.sem`.
  - [ ] Resolve dependency module source files from the cached root.
  - [ ] Build dependency export contract tapes from cached module sources.
  - [ ] Allow project modules to import dependency modules by registered module
        path and alias.
  - [ ] Prevent dependency private symbols from leaking into project imports.
  - [ ] Include dependency source paths in linter and compiler diagnostics.
- [ ] Add dependency fetch tests.
  - [ ] Local path dependency.
  - [ ] Local path dependency does not use network.
  - [x] GitHub tag dependency.
  - [x] GitHub commit dependency.
  - [ ] GitHub archive download happy path.
  - [ ] GitHub tag-to-commit resolution happy path.
  - [ ] GitHub branch rejected in prod/release locked mode.
  - [ ] HTTPS archive download happy path.
  - [ ] HTTPS archive rejects plain `http://`.
  - [ ] Missing repository diagnostic.
  - [ ] Missing `build.sem` diagnostic.
  - [ ] Missing module contract rows in `build.sem` diagnostic.
  - [ ] Lockfile prevents network access during build.
  - [ ] Missing lock fails in locked mode.
  - [ ] Stale lock fails in locked mode.
  - [ ] Checksum mismatch fails before extraction.
  - [ ] Cache corruption diagnostic.
  - [ ] Dependency import resolves from cache.
  - [ ] Dependency import diagnostics cite cached source file paths.

### Runtime HTTP Client And Fetch API

- [ ] Define the runtime fetcher scope separately from build-time dependency
      fetching.
  - [ ] Keep `dependencyFetch` as build-time source acquisition.
  - [ ] Define runtime fetch as compiled-program behavior that lowers to native
        runtime calls.
  - [ ] Require runtime fetch calls to work without Python tooling at program
        execution time.
  - [ ] Decide the public namespace: `http.client*`, `net.fetch*`, or another
        name that cannot be confused with server-side `http.request*` and
        `http.response*`.
  - [ ] Define MVP target as blocking HTTP/1.1 plus HTTPS, not HTTP/2.
  - [ ] Defer HTTP/2 client support until TLS/ALPN and backend-library choices
        are settled.
- [ ] Design runtime fetch call targets.
  - [ ] Add `http.clientRequest` or equivalent request-construction call.
  - [ ] Add `http.clientFetchText` for simple text responses.
  - [ ] Add `http.clientFetchBytes` for binary responses.
  - [ ] Add `http.clientSetHeader` or equivalent request-header API.
  - [ ] Add request method support for GET.
  - [ ] Add request method support for POST.
  - [ ] Add request method support for PUT/PATCH/DELETE later.
  - [ ] Add request body text support.
  - [ ] Add request body bytes support.
  - [ ] Add per-request timeout argument.
  - [ ] Add max response body size argument.
  - [ ] Add optional redirect policy argument.
  - [ ] Add response status reader.
  - [ ] Add response header reader.
  - [ ] Add response body text reader.
  - [ ] Add response body bytes reader.
  - [ ] Add response body length reader.
  - [ ] Add explicit response cleanup/free call if response memory is owned by
        the caller.
- [ ] Define source-level types for runtime fetch.
  - [ ] Add or document `HttpClientRequest`.
  - [ ] Add or document `HttpClientResponse`.
  - [ ] Add or document `HttpMethod`.
  - [ ] Add or document `HttpStatus`.
  - [ ] Add or document `HttpHeaderName`.
  - [ ] Add or document `HttpHeaderValue`.
  - [ ] Add or document `Url`.
  - [ ] Add or document `NetworkTimeout`.
  - [ ] Add or document `ResponseBodyLimit`.
  - [ ] Decide whether URLs are plain `CNullTerminatedByteString` in MVP or a
        trusted/sanitized domain type.
- [ ] Define runtime fetch effects and capabilities.
  - [ ] Add canonical capability path `network.http.client`.
  - [ ] Decide whether outbound request effects use `read`, `write`, or both.
  - [ ] Require operations that perform outbound fetch to declare
        `effect OP write network.http.client` or the chosen equivalent.
  - [ ] Require operations that read response data to declare the matching
        response read effect if fetch and response inspection are separated.
  - [ ] Add linter checks so runtime fetch wrappers cannot hide network
        effects.
  - [ ] Ensure exported runtime-fetch wrappers carry effect edges in their
        public contract tape.
  - [ ] Ensure imported runtime-fetch wrappers trigger `SS2542`-style caller
        effect propagation.
  - [ ] Add diagnostics that suggest reusable capabilities for
        `network.http.client`.
- [ ] Choose the native runtime backend.
  - [ ] Compare a small custom HTTP/1.1 client against libcurl.
  - [ ] Compare OS TLS APIs against OpenSSL/LibreSSL/BoringSSL.
  - [ ] Decide whether MVP uses libcurl for DNS, TLS, redirects, and HTTP
        parsing.
  - [ ] If libcurl is used, define minimum supported version.
  - [ ] If a custom client is used, define DNS, socket, TLS, parser, redirect,
        and proxy boundaries explicitly.
  - [ ] Keep the SemanticScript ABI small even if the backend library is large.
  - [ ] Avoid exposing backend-library structs in generated SemanticScript ABI.
- [ ] Implement native runtime client ABI.
  - [ ] Add `sem_http_client_*` declarations to the runtime header.
  - [ ] Add request allocation/init function.
  - [ ] Add request header setter.
  - [ ] Add request body setter for text.
  - [ ] Add request body setter for bytes.
  - [ ] Add blocking execute/fetch function.
  - [ ] Add response status getter.
  - [ ] Add response header getter.
  - [ ] Add response body text getter.
  - [ ] Add response body bytes getter.
  - [ ] Add response body length getter.
  - [ ] Add response cleanup/free function.
  - [ ] Return structured status codes from every runtime function.
  - [ ] Keep all runtime-owned pointers valid until explicit cleanup or until
        the documented operation lifetime ends.
- [ ] Add compiler lowering for runtime fetch calls.
  - [ ] Register runtime fetch call signatures in the compiler builtin surface.
  - [ ] Register runtime fetch call signatures in semlint builtin signature
        tables.
  - [ ] Lower request creation to the native runtime function.
  - [ ] Lower header setters to the native runtime function.
  - [ ] Lower body setters to the native runtime function.
  - [ ] Lower execute/fetch calls to the native runtime function.
  - [ ] Lower response readers to native runtime functions.
  - [ ] Lower response cleanup/free calls to native runtime functions.
  - [ ] Add agent-readable compiler diagnostics for unsupported runtime fetch
        call targets.
  - [ ] Keep runtime fetch target names synchronized across `semsc.py`,
        `semlint.py`, `SYNTAX.md`, and docs.
- [ ] Define TLS behavior.
  - [ ] Require HTTPS support for the runtime fetch MVP.
  - [ ] Decide platform TLS provider per OS.
  - [ ] Decide certificate trust-store behavior on Windows.
  - [ ] Decide certificate trust-store behavior on macOS.
  - [ ] Decide certificate trust-store behavior on Linux.
  - [ ] Add diagnostic for TLS backend not available at link/runtime.
  - [ ] Add option to reject insecure TLS by default.
  - [ ] Decide whether development builds can opt into insecure TLS for local
        test servers.
  - [ ] Ensure TLS errors map to typed SemanticScript errors.
- [ ] Define URL, redirect, and protocol rules.
  - [ ] Reject unsupported schemes before network access.
  - [ ] Support `https://` in MVP.
  - [ ] Decide whether `http://` is allowed for localhost/dev only or allowed
        generally with warning.
  - [ ] Define max redirect count.
  - [ ] Define whether POST redirects preserve method/body.
  - [ ] Reject redirects from HTTPS to HTTP by default.
  - [ ] Define header-size limit.
  - [ ] Define status-line parsing limit.
  - [ ] Define response body-size limit.
  - [ ] Define timeout behavior for DNS, connect, TLS handshake, write, and
        response read.
- [ ] Define runtime fetch error model.
  - [ ] Add `HttpClientError` error domain.
  - [ ] Add DNS failure case.
  - [ ] Add connect failure case.
  - [ ] Add timeout case.
  - [ ] Add TLS handshake failure case.
  - [ ] Add certificate validation failure case.
  - [ ] Add invalid URL case.
  - [ ] Add unsupported scheme case.
  - [ ] Add request body too large case.
  - [ ] Add response body too large case.
  - [ ] Add malformed response case.
  - [ ] Add redirect limit exceeded case.
  - [ ] Decide whether non-2xx HTTP status is a transport success or typed
        application-level failure.
- [ ] Define memory ownership for runtime fetch.
  - [ ] Decide whether simple `fetchText` copies body into runtime-owned memory
        or caller-owned heap memory.
  - [ ] Add explicit cleanup rule for response bodies.
  - [ ] Add linter diagnostic for missing cleanup if cleanup is explicit.
  - [ ] Ensure response header values have documented lifetime.
  - [ ] Ensure response body bytes have documented lifetime.
  - [ ] Prevent use-after-free of response-owned pointers where the linter can
        prove it.
  - [ ] Add max allocation guard before reading response body.
- [ ] Define blocking, async, and webserver interaction.
  - [ ] Allow blocking runtime fetch in console programs for MVP.
  - [ ] State explicitly that async plumbing is not required for the first
        runtime fetch MVP.
  - [ ] Define blocking fetch as a synchronous native runtime call that owns the
        socket/TLS operation until it returns a response or error.
  - [ ] Require every blocking fetch call to carry an explicit timeout value.
  - [ ] Reject or warn on blocking fetch calls that rely on an infinite/default
        timeout.
  - [ ] Define per-phase timeout defaults when the user supplies one aggregate
        timeout.
  - [ ] Define max response body size as mandatory for blocking fetch helpers.
  - [ ] Decide whether blocking fetch may be used in `main` and ordinary console
        operations with only an effect/capability proof.
  - [ ] Define warning when a native webserver handler performs blocking
        runtime fetch without timeout.
  - [ ] Require timeout/cancellation metadata for runtime fetch inside
        webserver handlers.
  - [ ] Add a linter rule that detects `http.client*` calls inside operations
        bound by `route` or `routeMiddleware`.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        must have a timeout row or a timeout argument on the fetch call.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        must declare the outbound network effect.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        should document backpressure/concurrency risk with `warning` or
        `invariant`.
  - [ ] Decide whether blocking fetch in webserver handlers is WARNING-only in
        dev and ERROR in prod/release build profiles.
  - [ ] Define runtime behavior when blocking fetch times out inside a handler:
        return typed error to handler, emit 500, or trap depending on the
        handler's error contract.
  - [ ] Define whether middleware is allowed to short-circuit after a failed
        outbound fetch.
  - [ ] Decide whether runtime fetch can be used inside middleware.
  - [ ] Add a gauntlet route that deliberately exercises blocking fetch through
        a local loopback server once runtime fetch exists.
  - [ ] Add a webserver test proving one blocking fetch pins the current
        single-threaded server loop until timeout/response.
  - [ ] Add docs warning that current native webserver adapter is blocking and
        single-threaded.
  - [ ] Defer async/event-loop integration until the native server adapter has
        an async story.
  - [ ] Define future async fetch shape with `start`, `await`, `timeout`, and
        `cancelOn`.
  - [ ] Define future async fetch as nonblocking runtime work, not just a
        blocking call hidden behind `start`.
  - [ ] Define whether async fetch uses a worker-thread pool, nonblocking
        sockets, or platform event loops.
  - [ ] Define the MVP async backend options: select/poll, epoll/kqueue, IOCP,
        or a portable library.
  - [ ] Define how DNS resolution works in async mode.
  - [ ] Define how TLS handshakes are driven in async mode.
  - [ ] Define how cancellation interrupts connect, TLS handshake, request
        write, and response read phases.
  - [ ] Define how response body streaming works without buffering the entire
        body.
  - [ ] Define async fetch result ownership after `await`.
  - [ ] Define event-loop ownership for console programs.
  - [ ] Define event-loop ownership for native webserver programs.
  - [ ] Define whether the native webserver must become event-loop based before
        async fetch is allowed inside handlers.
  - [ ] Define how async fetch interacts with existing `taskGroup`,
        `startInGroup`, `awaitGroup`, `timeout`, and `cancelOn` rows.
  - [ ] Add future tests for two concurrent async fetches completing out of
        order.
  - [ ] Add future tests for cancellation during DNS/connect/TLS/read.
- [ ] Define linker and distribution behavior.
  - [ ] Add platform-specific linker flags for the chosen HTTP/TLS backend.
  - [ ] Add Windows linker flags and DLL discovery rules.
  - [ ] Add macOS linker flags and framework/library rules.
  - [ ] Add Linux linker flags and package dependency notes.
  - [ ] Add `sem doctor` checks for runtime fetch prerequisites.
  - [ ] Add build-profile behavior for statically linked versus dynamically
        linked HTTP client runtime.
  - [ ] Document how generated executables discover runtime client libraries.
- [ ] Add runtime fetch documentation and examples.
  - [ ] Add `docs/language/native-http-client-api.md`.
  - [ ] Add `SYNTAX.md` rows for runtime fetch call targets.
  - [ ] Add `docs/toolchain/compiler.md` linker/runtime notes.
  - [ ] Add optimization-guide notes for agent-readable fetch errors.
  - [ ] Add a minimal console `GET https://example.com` sample.
  - [ ] Add a JSON API fetch sample.
  - [ ] Add a POST body sample.
  - [ ] Add a timeout failure sample.
  - [ ] Add a TLS failure documentation example.
- [ ] Add runtime fetch tests.
  - [ ] Unit-test compiler lowering for every fetch call target.
  - [ ] Unit-test semlint builtin signature coverage.
  - [ ] Unit-test missing network capability diagnostic.
  - [ ] Unit-test imported fetch-wrapper effect propagation.
  - [ ] Integration-test HTTP GET against a local test server.
  - [ ] Integration-test HTTPS GET against a controlled test server or fixture.
  - [ ] Integration-test request headers.
  - [ ] Integration-test response headers.
  - [ ] Integration-test POST text body.
  - [ ] Integration-test binary response body.
  - [ ] Integration-test timeout behavior.
  - [ ] Integration-test redirect policy.
  - [ ] Integration-test max body-size failure.
  - [ ] Integration-test response cleanup under sanitizer or leak-check mode
        when available.

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
  - [ ] Identify stdlib modules needing relay entries in `std/module.sem`.
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
  - [x] Legacy single-file import still works during compatibility window.
  - [x] New project import works.
  - [ ] Mixed old/new imports produce clear diagnostics.
  - [ ] Migration suggestions include exact replacement rows.

## P1 - Developer Tooling Roadmap For A Real Language

This section tracks the toolchain needed for SemanticScript to feel like a
complete language instead of a set of implementation scripts. These are not all
required for the scoped 1.0 release, but they should guide the post-1.0 tooling
order.

### `semfmt` Formatter

- [x] Create a formatter entrypoint named `semfmt`.
  - [x] Decide whether `semfmt` lives under `SemanticScript/tools/`,
        `SemanticScript/formatter/`, or as a `sem fmt` subcommand wrapper.
  - [ ] Add command help with examples for `.sscript` and `.sem` files.
  - [x] Support formatting one file.
  - [x] Support formatting multiple explicit files.
  - [x] Support recursive project formatting with include/exclude globs.
  - [x] Add `--check` mode for CI that exits non-zero on formatting drift.
  - [x] Add `--diff` mode that prints a unified diff without writing files.
  - [x] Add `--stdin-file-name` support for editor integrations.
- [ ] Make formatting parser-aware instead of regex-only.
  - [ ] Reuse the compiler/linter tokenizer or extract a shared tokenizer.
  - [ ] Preserve comments exactly unless indentation is intentionally adjusted.
  - [x] Preserve blank lines where they separate logical sections.
  - [x] Preserve quoted strings and escape sequences byte-for-byte.
  - [x] Preserve unknown/proposed verbs instead of deleting or rewriting them.
- [ ] Define canonical row layout rules.
  - [x] Canonicalize one space between tokens.
  - [x] Trim trailing whitespace.
  - [x] Keep comments after code separated by at least two spaces if inline
        comments are allowed.
  - [x] Keep top-level declaration rows unindented.
  - [x] Decide whether operation body rows remain unindented or gain logical
        indentation in formatted output.
  - [ ] Define maximum line length and whether long strings are never wrapped.
  - [ ] Define how long metadata strings should be wrapped, if at all.
- [ ] Define canonical ordering rules where safe.
  - [x] Decide whether formatter may reorder metadata rows.
  - [ ] If reordering is allowed, order operation metadata as
        `purpose`, `input`, `output`, `effect`, `useCapability`, warnings, then
        invariants.
  - [x] Never reorder executable body rows unless a proof exists that behavior
        is unchanged.
  - [x] Never reorder route rows unless route precedence rules make ordering
        irrelevant.
- [ ] Add formatter configuration.
  - [x] Define formatter settings in `build.sem` or a future SemanticScript
        settings tape, not TOML.
  - [ ] Support line width.
  - [ ] Support newline mode.
  - [x] Support quote-preservation only, not quote-style rewrites.
  - [ ] Document defaults as the canonical project style.
- [ ] Add formatter tests.
  - [x] Golden-format tests for small syntax examples.
  - [ ] Golden-format tests for webserver apps.
  - [x] Golden-format tests for comments and blank lines.
  - [x] Golden-format tests for quoted strings with escaped characters.
  - [x] Idempotence tests: formatting twice produces byte-identical output.
  - [x] Safety tests: formatted source parses to the same high-level semantic
        tape as the original.
  - [ ] Fuzz tests for tokenizer/formatter round-tripping.
- [ ] Integrate formatter into editors and CI.
  - [ ] Add VS Code `DocumentFormattingEditProvider`.
  - [ ] Add format-on-save documentation.
  - [ ] Add CI `semfmt --check` once formatting is stable.
  - [ ] Add release checklist item requiring formatter clean output.

### `sem` Project Command Driver

- [x] Create a single daily-use command named `sem`.
  - [x] Decide implementation language for the first driver.
  - [x] Make the driver work from PowerShell on Windows.
  - [x] Make the driver work from POSIX shells.
  - [x] Add `sem --version`.
  - [x] Add `sem --help`.
  - [x] Add useful non-zero exit codes for scripting.
- [ ] Wrap compiler commands.
- [x] Add `sem build`.
  - [x] Add `sem run`.
  - [x] Add `sem check` for parse, lint, and type/codegen validation.
  - [ ] Add `sem emit-ir`.
  - [ ] Add `sem clean` for ignored local build artifacts.
  - [x] Pass through `--build-profile dev|prod`.
  - [x] Pass through `--runtime-checks off|traps|panic`.
  - [x] Pass through `--persist-llvm-ir auto|yes|no`.
  - [x] Pass through `--opt-level`.
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
- [x] Add project discovery.
  - [x] Discover the nearest `build.sem`.
  - [x] Fall back to single-file mode when no build tape exists.
  - [x] Resolve source roots from `build.sem`.
  - [x] Resolve build output directories from `build.sem`.
  - [x] Resolve default entrypoints from `build.sem`.
  - [x] Resolve target runtime settings from `build.sem`.
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
  - [x] Test build-tape-based build.
  - [ ] Test `sem check` failure reporting.
  - [ ] Test PowerShell examples.
  - [ ] Test POSIX examples in CI if a POSIX runner is available.

### `build.sem` Project Build Tape

- [x] Define the project build tape schema.
  - [x] Project name.
  - [x] Project version.
  - [x] License field.
  - [x] Source roots.
  - [x] Default entry operation.
  - [x] Build profiles.
  - [x] Runtime target.
  - [x] Native HTTP settings.
  - [x] Test roots.
  - [x] Formatter settings.
  - [x] Linter settings.
  - [x] Documentation output settings.
  - [x] LLVM build flags.
  - [x] Compiler-managed build folder settings.
- [x] Implement build-tape parsing.
  - [x] Add strict diagnostics for malformed project build rows.
  - [x] Add strict diagnostics for unknown top-level keys.
  - [x] Add strict diagnostics for missing required fields.
  - [x] Add path normalization on Windows and POSIX.
  - [x] Add tests for relative and absolute paths.
- [x] Integrate project build tapes with existing tools.
  - [x] `semsc.py` can accept a `build.sem`-driven build through `sem build`.
  - [x] `semlint.py` can lint a `build.sem` project.
  - [x] VS Code extension can discover project settings from `build.sem`.
  - [x] Future language server can use `build.sem` as the workspace root.
- [x] Document the project build tape.
  - [x] Add a minimal console app `build.sem` example.
  - [x] Add a native webserver `build.sem` example.
  - [x] Add a library/package `build.sem` example.
  - [x] Add a schema reference table.

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

### Agent Observability, Trace, Crash, And Debug Tooling

- [x] Treat this surface as machine-readable agent tooling, not human debugger UI.
  - [x] Prefer deterministic JSON/JSONL artifacts over prose.
  - [x] Include `schemaVersion`, tool version, source fingerprint, build fingerprint,
        build profile, runtime-check mode, LLVM target triple, and artifact paths.
  - [x] Keep optional human text as a view over structured data, never as the
        only output.
  - [x] Keep LLVM IR, optimized LLVM IR, trace maps, crash reports, profiles,
        and benchmark reports cross-linkable by stable ids.

- [x] Define source-to-runtime trace metadata.
  - [x] Map semantic tape rows to source file/line/column.
  - [x] Map generated LLVM blocks back to operation and call names.
  - [x] Map native runtime failures back to SemanticScript route/handler names.
  - [x] Emit a trace-map sidecar with stable `siteId` values for operations,
        calls, branches, returns, routes, handlers, runtime symbols, and link inputs.
  - [x] Preserve imported-source origins instead of only reporting the flattened
        resolved stream.
  - [x] Include source row text and redaction metadata so agents can patch near
        the right source without leaking sensitive values.
- [x] Add agent-oriented IR inspection.
  - [x] Add `sem inspect-ir`.
  - [x] Support JSON output by default.
  - [x] Show the source operation that produced each LLVM function.
  - [x] Show generated LLVM basic blocks by function.
  - [x] Show native ABI signatures for HTTP handlers.
  - [x] Show linked runtime source files and link args.
  - [x] Include trace-map ids in the IR inspection output.
- [x] Add trace execution mode.
  - [x] Add `sem run --trace`.
  - [x] Support JSONL output for streaming traces.
  - [x] Add trace output for operation entry/exit.
  - [x] Add trace output for call execution.
  - [x] Add trace output for branch decisions.
  - [x] Add trace output for returned values where safe.
  - [x] Include monotonic sequence ids and monotonic timestamps.
  - [x] Include operation/call/site ids matching the trace-map sidecar.
  - [x] Redact values from paths marked sensitive by future metadata.
- [x] Add agent profiling mode.
  - [x] Add `sem run --profile --json`.
  - [x] Aggregate hot operations, hot calls, branch frequencies, runtime external
        calls, startup time, wall time, and HTTP request counts where applicable.
  - [x] Keep profile summaries separate from exhaustive traces so agents can
        optimize without measuring trace overhead as application cost.
- [x] Add crash explanation mode.
  - [x] Add `sem run --explain-crash`.
  - [x] Run crashing programs in a subprocess so LLVM traps do not kill the tool
        driver.
  - [x] Support JSON output for agent triage.
  - [x] Capture runtime panic code.
  - [x] Capture SemanticScript stack/operation context.
  - [x] Capture direction message that hints at the likely fix.
  - [x] Capture build profile and runtime-check mode.
  - [x] Attach the last N trace events when trace data is available.
  - [x] Emit suspected category and fix candidates for agent patch planning.
  - [x] Keep prod profile output minimal by default.
- [x] Add optimization-loop integration.
  - [x] Define the agent loop: inspect IR, capture baseline profile/bench,
        patch source, run check/tests, re-profile/re-bench, compare artifacts.
  - [x] Preserve artifact indexes so agents can compare before/after runs.
  - [x] Report benchmark/profile deltas in stable JSON fields.
- [x] Add minimal debugger plan.
  - [x] Keep source-level semantic traces as the first release debugger surface.
  - [x] Defer LLDB/GDB integration until source representation, trace ids, and
        value representation are stable.
  - [x] Define breakpoint syntax if source-level breakpoints are added.
  - [x] Define watch/expression support only after value representation is
        stable.
  - [x] Document where native debugger integration adds value for LLVM backend
        failures versus where semantic trace data is better for agents.

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

### Initial Release Hardening Gaps

These items were identified after comparing the current release checklist,
`TODO.md`, release docs, and repository state. They are release-polish and
release-trust tasks that were either absent from this file or too implicit to
assign cleanly.

- [ ] Define a single release version policy.
  - [ ] Decide whether all first-party tools should share the same release
        version for the initial public release.
  - [ ] Decide whether `semsc`, `semlint`, `semfmt`, `sem`, and the VS Code
        extension are independently versioned components or one product
        version.
  - [ ] Record the decision in `RELEASE.md`.
  - [ ] Record the decision in `docs/reference/release-hygiene.md`.
  - [ ] Add a release version matrix listing each public command/package and
        its version.
  - [ ] Include `SemanticScript/compiler/semsc.py`.
  - [ ] Include `SemanticScript/linter/semlint.py`.
  - [ ] Include `SemanticScript/formatter/semfmt.py`.
  - [ ] Include `SemanticScript/tools/sem.py`.
  - [ ] Include `vscode-semanticscript/package.json`.
  - [ ] Align stale docs that still mention old VSIX versions.
  - [ ] Update `README.md` if it references an older
        `semanticscript-vscode-*.vsix` artifact.
  - [ ] Update `docs/reference/release-hygiene.md` if it references an older
        extension version.
  - [ ] Add a simple release check that prints all tool versions.
  - [ ] Decide whether mismatched tool versions fail a release check or are
        allowed when documented in the matrix.

- [ ] Add a real security contact before public release.
  - [ ] Replace the `TODO` contact placeholder in `SECURITY.md`.
  - [ ] Decide the reporting channel: email address, GitHub security advisory,
        private issue tracker, or another maintained channel.
  - [ ] Document expected acknowledgement timing.
  - [ ] Document expected fix/disclosure timing.
  - [ ] Document which versions are supported for security fixes.
  - [ ] Confirm the contact can receive reports before tagging a public
        release.
  - [ ] Add a release checklist item that fails if `SECURITY.md` still contains
        a public-release contact placeholder.

- [ ] Add a third-party license and SBOM review.
  - [ ] Inventory every directory under `third_party/`.
  - [ ] Record upstream project name for each vendored dependency.
  - [ ] Record upstream URL for each vendored dependency.
  - [ ] Record pinned revision, release tag, or source acquisition date.
  - [ ] Record license for `third_party/h2o`.
  - [ ] Record license for `third_party/sqlite`.
  - [ ] Preserve upstream license files in packaged source archives.
  - [ ] Decide whether to add a root `NOTICE` file.
  - [ ] Decide whether to add a machine-readable SBOM file.
  - [ ] If adding an SBOM, choose a format such as SPDX or CycloneDX.
  - [ ] Document which release artifacts include third-party code.
  - [ ] Document whether source-only releases and binary releases have
        different notice requirements.
  - [ ] Run a basic vulnerability review for vendored dependencies.
  - [ ] Record known CVE exceptions or "none known at release time" in release
        notes.
  - [ ] Add a release checklist item that requires third-party license/SBOM
        review before tagging.

- [ ] Verify generated artifacts are removed from Git history.
  - [ ] Define which historical artifacts are disallowed in repository history.
  - [ ] Include generated `.exe` files.
  - [ ] Include generated `.ll` files.
  - [ ] Include generated `.bc`, `.obj`, `.o`, `.pdb`, `.res`, `.rc`, and
        native build folders.
  - [ ] Include packaged `.vsix` files if the release policy keeps VSIX
        artifacts outside Git.
  - [ ] Include local app data such as `todos.json`.
  - [ ] Add a non-destructive history scan command to `RELEASE.md`.
  - [ ] Run the history scan against all branches intended for release.
  - [ ] Decide whether history rewriting is required before the first public
        push/tag.
  - [ ] If rewriting history, document the exact tool and command used.
  - [ ] Prefer `git filter-repo` or another repeatable non-interactive tool for
        any required history rewrite.
  - [ ] Verify rewritten history still contains required source, docs, and test
        fixtures.
  - [ ] Verify current `.gitignore` catches the same artifact classes after the
        history scrub.
  - [ ] Record the final history-scan result in release notes.

- [ ] Make CI enforce the full release checklist.
  - [ ] Compare `.github/workflows/ci.yml` against `RELEASE.md`.
  - [ ] Add CI coverage for `SemanticScript/formatter/test_semfmt.py` if not
        already enforced.
  - [ ] Add CI coverage for `SemanticScript/tests/test_compiler.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/test_stdlib.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/compare.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/sem_alias_parity.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/sem_compiler_parity.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/feature_coverage.py`.
  - [ ] Add CI coverage for `SemanticScript/bootstrap/run_bootstrap_chain.py`.
  - [ ] Add CI coverage for `app/todo-web/test_todo_web.py`.
  - [ ] Add CI coverage for `app/todo-web-advanced/test_advanced_todo_web.py`.
  - [ ] Add CI coverage for `app/http-api-gauntlet/scripts/test_http_api_gauntlet.py`.
  - [ ] Add CI coverage for the native HTTP runtime CMake build where the
        runner toolchain supports it.
  - [ ] Add CI coverage for the native JSON runtime CMake build if it remains
        in the release scope.
  - [ ] Add CI coverage for the native SQLite runtime CMake build if it remains
        in the release scope.
  - [ ] Add CI coverage for `npm --prefix vscode-semanticscript run check`.
  - [ ] Add optional CI coverage for `npm --prefix vscode-semanticscript run
        package:vsix` without uploading the artifact by default.
  - [ ] Run native executable tests on Windows CI, not only Linux.
  - [ ] Run at least parse/lint/tooling checks on Linux CI.
  - [ ] Document any release validation commands that intentionally remain
        manual.
  - [ ] Add a release checklist item requiring CI green on the exact release
        commit.

- [ ] Define the public 1.0 compatibility contract.
  - [ ] Write down what `languageVersion PROJECT "1.0"` guarantees.
  - [ ] Define which syntax rows are stable for 1.0.
  - [ ] Define which syntax rows are preview, partial, metadata-only, or
        subject to change.
  - [ ] Define whether `.sscript` and `.sem` have equal long-term support.
  - [ ] Define whether `.sscript` remains canonical and `.sem` remains an alias.
  - [ ] Define compatibility guarantees for `build.sem`.
  - [ ] Define compatibility guarantees for module/import/export rows.
  - [ ] Define compatibility guarantees for native HTTP APIs.
  - [ ] Define compatibility guarantees for JSON runtime APIs currently in
        scope.
  - [ ] Define compatibility guarantees for VS Code syntax highlighting and
        extension configuration keys.
  - [ ] Define the deprecation process for syntax that changes after 1.0.
  - [ ] Define whether future compiler versions warn before rejecting old 1.0
        syntax.
  - [ ] Add the compatibility contract to `README.md` or a dedicated docs page.
  - [ ] Link the compatibility contract from `RELEASE.md`.
  - [ ] Link the compatibility contract from `SYNTAX.md`.

- [ ] Add a release artifact manifest.
  - [ ] Define a manifest filename and location for each release.
  - [ ] Record release tag.
  - [ ] Record release commit SHA.
  - [ ] Record release date.
  - [ ] Record tool versions.
  - [ ] Record Python version used for release validation.
  - [ ] Record Node.js version used for VS Code extension validation.
  - [ ] Record clang/LLVM version used for native executable validation.
  - [ ] Record operating systems used for validation.
  - [ ] Record exact validation commands run.
  - [ ] Record skipped validation commands and the reason.
  - [ ] Record generated release artifacts such as source archive and VSIX.
  - [ ] Record artifact checksums.
  - [ ] Record whether signatures were generated.
  - [ ] Record known deferred features from `TODO.md`.
  - [ ] Record known xfail/bootstrap limitations.
  - [ ] Add a release checklist item requiring the manifest before tagging.
  - [ ] Decide whether manifests are committed, attached to GitHub releases, or
        both.

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
