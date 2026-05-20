# SemanticScript Syntax Inventory

This document lists the SemanticScript syntax surface in one table. The status
column uses a small enum so current implementation, partial support, missing
support, and proposed syntax are not blurred together.

Implementation status enum values:

- `Impl'd` means implemented in the Python reference compiler.
- `Partial` means parsed, stubbed, metadata-only, linter-only, or incomplete.
- `Not impl'd` means committed current syntax or runtime surface with no meaningful implementation yet.
- `Proposed` means carried by refined examples as candidate syntax, not committed to the compiler surface yet.

Compiler coverage note: statuses refer to `SemanticScript/compiler/semsc.py` unless
a row explicitly says otherwise. `SemanticScript/bootstrap/bootstrap_general.sscript` is
a smaller bootstrap compiler and does not yet cover the same surface. The
refined syntax examples in `SemanticScript/sem/` are syntax research and tooling
targets, not a blanket guarantee that every refined form is executable.
The public 1.0 compatibility contract is documented in
`docs/reference/compatibility.md`.

GUI ownership note: `target windowsGui` and
`targetRuntime PROJECT windowsGui` are compiler/build bridge rows. Current
codegen links the native GUI runtime for a normal `entry console OPERATION`
that calls `gui.*` targets. GUI application shape is expressed with ordinary
operation/call/arg/run syntax from `standard.gui`; GUI-specific top-level
`gui*` declaration rows are not part of the committed executable surface.
The preferred GUI import shape is `importModule gui standard.gui`; the
compatibility form `importModule standard.gui as gui` remains accepted.
`standard.gui`, lint/tooling, and the GUI runtime own declaration contracts,
capabilities, and most validation semantics.

Intentionally rejected forms are not syntax rows: infix operators, semicolons,
brace blocks, parenthesized call expressions, comma argument lists, generic
angle brackets, implicit current calls, exceptions, implicit async, indentation
blocks, and dynamic object or array literals.

| Syntax | API description | Implementation status |
|---|---|---|
| `"quoted string"` | Defines a string literal token that may contain whitespace. | Impl'd |
| `# comment text` | Defines a non-executable source comment. | Impl'd |
| `# rationale: text` | Defines a typed rationale comment (attaches to current op). | Impl'd |
| `stdlib.string.compareCString` | Defines dotted namespace path syntax. | Impl'd |
| `project NAME` | Names the program for tools and generated artifacts. | Impl'd |
| `target NAME` | Declares intended runtime target such as console or web server. | Impl'd |
| `target webServer` (no `entry` line) | Selects webserver codegen when `webServer` / `route` metadata is present: routed programs emit a native HTTP/1.1 entrypoint and a registration-order dispatcher for literal paths plus `:name` path-parameter segments; unrouted files still compile operations plus a stub `main`. | Partial |
| `target windowsGui` with `entry console OPERATION` | Selects the native Windows GUI link/runtime bridge for a normal operation entrypoint. Current GUI executables compose windows and controls through `gui.*` calls from `standard.gui`; no-entry GUI targets raise `NotImplementedError` with guidance to use standard entry syntax. `entry windowsGui OPERATION` is intentionally not part of the committed surface. | Partial |
| `runtime NAME VERSION` | Records the runtime contract expected by the source. | Impl'd |
| `module NAME` | Names a module boundary; `semsc` validates dotted namespace shape and rejects conflicting declarations in one resolved source. | Impl'd |
| `mode capturedOutputReplay` | Marks sources that replay captured output rather than fully reimplementing an algorithm. | Impl'd |
| `languageMode strictExecutable` | Opts the resolved source stream into a closed executable grammar from that row forward. Unknown lowercase top-level and operation-body verbs become parse errors without requiring `--lint`; the diagnostic points users to `languageMode refinedSyntax` only for research/metadata files. Cannot be combined with `languageMode refinedSyntax`. | Impl'd |
| `languageMode refinedSyntax` | Marks research/metadata files that intentionally rely on permissive lowercase metadata rows. This preserves the non-strict parser behavior for refined examples and cannot be combined with `languageMode strictExecutable`. | Impl'd |
| `entry console OPERATION` | Selects the executable console entry operation. | Impl'd |
| `version "A.B.C.D"` | Declares the project version (1–4 dotted unsigned integers, zero-padded to 4 parts at emit time). Lowers to Windows VERSIONINFO `FILEVERSION` / `PRODUCTVERSION` and the `FileVersion` / `ProductVersion` string-table entries. | Impl'd |
| `publisher "text"` | Declares the publisher / company name. Lowers to VERSIONINFO `CompanyName`. | Impl'd |
| `description "text"` | Declares the program's human-readable description. Lowers to VERSIONINFO `FileDescription`. Defaults to the project name if omitted. | Impl'd |
| `copyright "text"` | Declares the legal copyright string. Lowers to VERSIONINFO `LegalCopyright`. | Impl'd |
| `productName "text"` | Declares the product name shown in Windows Explorer. Lowers to VERSIONINFO `ProductName`. Defaults to the project name. | Impl'd |
| `internalName "text"` | Declares the internal short name. Lowers to VERSIONINFO `InternalName`. Defaults to the project name. | Impl'd |
| `originalFilename "todo.exe"` | Declares the original on-disk filename. Lowers to VERSIONINFO `OriginalFilename`. Defaults to the basename of the `--emit-exe` output path. | Impl'd |
| `trademark "text"` | Declares the legal trademark string. Lowers to VERSIONINFO `LegalTrademarks`. | Impl'd |
| `comments "text"` | Declares an arbitrary comments block. Lowers to VERSIONINFO `Comments`. | Impl'd |
| `metadata "key" "value"` | Declares an arbitrary user-defined metadata pair. Lowers to a custom VERSIONINFO StringFileInfo entry with the given key — readable via `version.dll`'s `VerQueryValue`. May be repeated; insertion order is preserved. | Impl'd |
| `buildProject PROJECT` | Starts a strict project build tape in `build.sem`; exactly one active build project is allowed. | Partial |
| `modulePath PROJECT MODULE_PATH` | Declares the Go-style canonical module path for the project. | Partial |
| `languageVersion PROJECT "VERSION"` | Pins the SemanticScript language version expected by the build tape. | Partial |
| `projectVersion PROJECT "VERSION"` | Pins the project/package version expected by the build tape. | Partial |
| `projectLicense PROJECT LICENSE` | Records the project license token for tooling and release metadata. | Partial |
| `sourceRoot PROJECT "PATH"` | Declares the project source root relative to `build.sem`. | Partial |
| `registerModule PROJECT MODULE_PATH "PATH"` | Registers one project module with the build tape. Imports must reference registered module paths; the registered path may be a module source file or a folder with `main.sem`, `index.sem`, the leaf module file, or exactly one non-test `.sem`/`.sscript`. | Partial |
| `mainFile PROJECT "main.sem"` | Declares the default executable source file. | Partial |
| `mainOperation PROJECT OPERATION` | Declares the default executable operation inside `mainFile`. | Partial |
| `testPattern PROJECT "*.test.sem"` | Declares the local test-file glob for project test discovery. | Partial |
| `testRoot PROJECT "PATH"` | Declares the test source root relative to `build.sem`. | Partial |
| `dependency PROJECT ALIAS MODULE_PATH VERSION_OR_REF` | Declares one project dependency request. | Partial |
| `dependencySource PROJECT ALIAS [local\|path\|github\|http] SOURCE [REF]` | Declares where dependency source is found. Legacy `dependencySource PROJECT ALIAS SOURCE` rows infer kind from `SOURCE`. GitHub rows use `OWNER/REPO`; HTTP rows must use `https://`. | Partial |
| `dependencyFetch PROJECT ALIAS github OWNER/REPO REF` | Declares a future GitHub fetch edge with explicit owner/repo and requested ref. | Partial |
| `dependencyFetch PROJECT ALIAS http "https://..."` | Declares a future HTTPS archive/API fetch edge. Plain HTTP is rejected. | Partial |
| `dependencyCache PROJECT "PATH"` | Declares the dependency source cache directory, normally `.semcache`. | Partial |
| `dependencyLock PROJECT "PATH"` | Declares the dependency lock tape path, normally `sem.lock`. | Partial |
| `dependencyIntegrity PROJECT ALIAS sha256:<64-hex>\|commit:<7-40-hex>` | Records a reproducible source pin for archives or resolved GitHub commits. | Partial |
| `targetRuntime PROJECT nativeExe\|webServer\|windowsGui\|library` | Declares the build target runtime class for project-mode builds. Current `windowsGui` build tapes use `target windowsGui` plus `entry console OPERATION`; the entry operation calls `gui.*` targets and the build links `SemanticScript/runtime/native_win32_gui/sem_win32_gui_runtime.c`. | Partial |
| `buildProfile PROJECT dev|prod` | Declares the default build profile for project-mode builds. | Partial |
| `optLevel PROJECT 0|1|2|3` | Declares the LLVM optimization level for project-mode builds. | Impl'd |
| `runtimeChecks PROJECT off|traps|panic` | Declares runtime-check policy for project-mode builds. | Partial |
| `persistLlvmIr PROJECT auto|yes|no` | Declares whether project-mode builds keep generated LLVM IR artifacts. | Partial |
| `emitLlvmIr PROJECT auto|yes|no` | Requests pre-optimization LLVM IR emission from the build tape. | Impl'd |
| `llvmIrOutput PROJECT "PATH"` | Declares the pre-optimization LLVM IR output path. Basenames resolve into the compiler-managed build directory; paths with directories resolve relative to `build.sem`. | Impl'd |
| `emitOptimizedLlvmIr PROJECT yes|no` | Requests post-optimization LLVM IR emission from the build tape. | Impl'd |
| `optimizedLlvmIrOutput PROJECT "PATH"` | Declares the post-optimization LLVM IR output path. Basenames resolve into the compiler-managed build directory; paths with directories resolve relative to `build.sem`. | Impl'd |
| `buildDir PROJECT "PATH"` | Overrides the exact compiler-managed build output directory. | Impl'd |
| `buildRoot PROJECT "PATH"` | Overrides the root that contains the compiler-managed build folder. | Impl'd |
| `buildFolderName PROJECT NAME` | Overrides the managed build folder name used with `buildRoot`. Must be a single folder name, not a path. | Impl'd |
| `cpuBaseline PROJECT generic\|native\|x86_64_v1\|x86_64_v2\|x86_64_v3\|x86_64_v4\|arm64_generic\|arm64_v8_2` | Declares the CPU instruction baseline for LLVM/clang lowering. Defaults to portable `generic`. | Impl'd |
| `cpuTune PROJECT generic\|native\|CPU_NAME` | Declares an AOT scheduling tune token passed to clang as `-mtune`; `generic` emits no tune flag. | Impl'd |
| `cpuFeature PROJECT FEATURE on\|off` | Adds or disables one CPU feature for LLVM/clang lowering. Required `on` features are checked against the host unless `cpuFeatureCheck off` is used. | Impl'd |
| `cpuFeatureCheck PROJECT auto\|off\|warn\|require` | Controls the build-time host CPU feature check. `auto` fails local builds that request unavailable features; `off` is only for known non-host targets. | Impl'd |
| `nativeOutput PROJECT "PATH"` | Declares the native executable output path for project-mode builds. A basename resolves into the compiler-managed `build/` artifact directory. | Partial |
| `nativeHttpHost PROJECT "HOST"` | Declares the default native HTTP bind host for web-server project builds. | Partial |
| `nativeHttpPort PROJECT PORT` | Declares the default native HTTP bind port for web-server project builds. | Partial |
| `formatterSetting PROJECT KEY VALUE` | Records a project-level formatter setting. | Partial |
| `linterSetting PROJECT KEY VALUE` | Records a project-level linter setting. | Partial |
| `docsOutput PROJECT "PATH"` | Declares where generated project documentation should be written. | Partial |
| `comptimeOperation PROJECT OPERATION` | Reserves a compile-time configuration operation for the future comptime build surface; current compiler does not execute it. | Proposed |
| `moduleFolder MODULE_PATH "PATH"` | Compatibility alias for `registerModule`; new build tapes should prefer `registerModule PROJECT MODULE_PATH "PATH"` so the owning project is explicit. | Partial |
| `modulePurpose MODULE_PATH "text"` | Describes the module's role for agents, docs, and future module validation. | Partial |
| `moduleOwns MODULE_PATH "text"` | Declares the behavior and files the module owns. | Partial |
| `moduleDoesNotOwn MODULE_PATH "text"` | Declares boundaries the module must not take over. | Partial |
| `moduleDependency MODULE_PATH DEPENDENCY_ALIAS` | Declares one module dependency edge. | Partial |
| `moduleWarning MODULE_PATH "text"` | Records module-level risk or migration context. | Partial |
| `moduleInvariant MODULE_PATH "text"` | Records module-level invariants that must survive refactors. | Partial |
| `moduleSecurity MODULE_PATH "text"` | Records module-level security context. | Partial |
| `moduleObservability MODULE_PATH "text"` | Records module-level logging, tracing, or metrics context. | Partial |
| `exportType MODULE_PATH TYPE` | Exposes an explicitly declared type as part of the module's public semantic contract. Belongs in the module source, not `build.sem`; `MODULE_PATH` must be registered by `build.sem`. Exports are never inferred. | Partial |
| `exportError MODULE_PATH ERROR` | Exposes an explicitly declared error domain as part of the module's public semantic contract. Belongs in the module source, not `build.sem`; `MODULE_PATH` must be registered by `build.sem`. Exports are never inferred. | Partial |
| `exportOperation MODULE_PATH OPERATION` | Exposes an explicitly declared operation as part of the module's public semantic contract. Belongs in the module source, not `build.sem`; `MODULE_PATH` must be registered by `build.sem`. Exports are never inferred. | Partial |
| `exportCapability MODULE_PATH CAPABILITY` | Exposes an explicitly declared capability as part of the module's public semantic contract. Belongs in the module source, not `build.sem`; `MODULE_PATH` must be registered by `build.sem`. Exports are never inferred. | Partial |
| `exportConstant MODULE_PATH BINDING` | Exposes an explicitly declared storage or literal binding as part of the module's public semantic contract. Belongs in the module source, not `build.sem`; `MODULE_PATH` must be registered by `build.sem`. Exports are never inferred. | Partial |
| `iconRoleDefinition ROLE "text"` | Defines one icon-role taxonomy entry for build-time native resources. | Partial |
| `icon GROUP` | Declares one named icon group. | Partial |
| `iconRole GROUP ROLE` | Assigns a role such as `applicationPrimary` to an icon group. | Partial |
| `iconPurpose GROUP "text"` | Documents where and why an icon group is used. | Partial |
| `iconImage IMAGE` | Declares one image asset that belongs to an icon group. | Partial |
| `iconImageGroup IMAGE GROUP` | Assigns an image asset to an icon group. | Partial |
| `iconImagePath IMAGE "PATH"` | Declares the source path for an icon image asset, resolved relative to the source/build file. | Partial |
| `iconImageFormat IMAGE png|ico` | Declares the icon image format. | Partial |
| `iconImageWidth IMAGE PIXELS` | Declares the source image width. | Partial |
| `iconImageHeight IMAGE PIXELS` | Declares the source image height. | Partial |
| `iconImageScale IMAGE SCALE` | Declares the display scale factor. | Partial |
| `iconImageDepth IMAGE bits32|bits24|bits8` | Declares the icon image color depth. | Partial |
| `iconImagePlatform IMAGE any|windows|macos|linux` | Declares the intended platform for the image. | Partial |
| `iconImagePurpose IMAGE "text"` | Documents where and why a specific icon image size is used. | Partial |
| `keepResources PROJECT yes\|no` | Build-tape switch — when `yes`, the intermediate Windows resource files (`.rc`/`.res`/`.ico`) are retained under `<build_dir>/resources/` for debugging. Defaults to `no`, in which case the files live in tempdir and are deleted after linking. CLI `--keep-resources` overrides. | Impl'd |
| `resourcesDir PROJECT "path"` | Build-tape path override naming an explicit directory for intermediate resource files. Implies `keepResources yes`. Relative paths resolve beside the source. CLI `--resource-dir PATH` overrides. | Impl'd |
| `importModule ALIAS DOTTED.PATH` | Preferred project import form. Binds a registered module to `ALIAS`, enabling qualified names such as `ALIAS.operationName` from the provider's explicit export tape. | Impl'd |
| `importModule DOTTED.PATH [as ALIAS]` | Compatibility import form. When the root build tape has `registerModule` rows, the compiler resolves registered modules first; legacy filesystem/std-lib fallback remains for single-file sources and older samples. | Impl'd |
| `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION` | Imports one exported provider operation under a local name. Wildcards and private provider symbols are rejected. | Partial |
| `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE` | Imports one exported provider type under a local name. | Partial |
| `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR` | Imports one exported provider error domain under a local name. | Partial |
| `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY` | Imports one exported provider capability under a local name, preserving effect path and access metadata. | Partial |
| `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_BINDING` | Imports one exported provider storage or literal binding under a local name. | Partial |
| `section NAME` | Declares a retrieval/indexing section without creating scope. | Impl'd |
| `group NAME` | Names a non-lexical attention/dataflow group. | Impl'd |
| `groupPurpose GROUP "text"` | Describes the purpose of a named group. | Impl'd |
| `groupInput GROUP VALUE` | Links one input symbol to a group. | Impl'd |
| `groupOutput GROUP VALUE` | Links one output symbol to a group. | Impl'd |
| `groupError GROUP ERROR_VALUE` | Links one raw bound error to a group. | Impl'd |
| `groupFailure GROUP FAILURE_VALUE` | Links one constructed domain failure to a group. | Impl'd |
| `groupTiming GROUP POLICY` | Links one timing or retry policy to a group. | Impl'd |
| `type AccountId UuidV7` | Declares a domain type alias. | Impl'd |
| `type AccountLookupResult Result` | Declares a parameterized type constructor before parameters are attached. | Impl'd |
| `typeInvariant TYPE "text"` | Attaches semantic constraints to a type. | Impl'd |
| `typeRepresentation TYPE BASE ARGS...` | Declares storage or representation choices for a type. | Impl'd |
| `typeTrust TYPE TRUST_LEVEL` | Marks raw, trusted, sanitized, internal, or public data. | Impl'd |
| `typeMemory TYPE MEMORY_KIND` | Records whether a type is inline, heap, arena, etc. | Impl'd |
| `typeLayout TYPE LAYOUT_KIND` | Records row, column, packed, or related layout intent. | Impl'd |
| `typeParameter TYPE INDEX PARAM_TYPE` | Declares one parameter of a parameterized type. | Impl'd |
| `typeLiteralEncoding TYPE ENCODING` | Declares how literals of a type are encoded. | Impl'd |
| `typeLiteralTerminator TYPE VALUE` | Declares required terminators such as C null bytes. | Impl'd |
| `error NAME` | Declares a typed error domain. | Impl'd |
| `errorCase ERROR VARIANT [CAUSE_TYPE]` | Declares branchable, name-addressable failure variants. | Impl'd |
| `enum NAME [repr TYPE]` | Declares a closed value set with optional representation. | Impl'd |
| `enumCase ENUM CASE [VALUE]` | Declares enum variants without expression syntax; repr-backed enum cases lower as typed enum values. | Impl'd |
| `record AccountBalanceResponse` | Declares a record schema. | Impl'd |
| `field RECORD FIELD TYPE` | Declares one field on a record schema. | Impl'd |
| `recordLayout RECORD KIND` | Declares record layout kind. | Impl'd |
| `recordAlign RECORD N` | Declares record alignment. | Impl'd |
| `new VALUE RECORD` | Creates a record value using the current record path (per-field flat allocas). | Impl'd |
| `fieldSet RECORD_VALUE FIELD VALUE` | Writes one field explicitly in the current record path. | Impl'd |
| `fieldGet OUT TYPE RECORD_VALUE FIELD` | Reads one field explicitly; on a record-typed param, aliases the flattened param SSA. | Impl'd |
| `recordConstructor OP RECORD` | Declares an operation-backed constructor for one record. | Impl'd |
| `recordConstructorFailure OP ERROR.VARIANT` | Declares constructor-specific failures. | Impl'd |
| `recordBuilder BUILDER RECORD` | Names a construction context for large records. | Impl'd |
| `recordSet BUILDER FIELD VALUE` | Sets one builder field per line. | Impl'd |
| `recordBuild CALL BUILDER` | Turns a builder into an explicit fallible build call; registers a synthetic call (zero result via external-module fallback). | Impl'd |
| `recordBuildFailure CALL ERROR.VARIANT` | Declares a possible build failure. | Impl'd |
| `operation NAME` | Starts a named operation; the main unit of executable code. | Impl'd |
| `operationBody OP KIND` | Declares an operation body kind; drives intrinsic / runtimeBinding lowering. | Impl'd |
| `input OP NAME TYPE` | Declares operation inputs and dependency tokens. | Impl'd |
| `output OP TYPE...` | Declares return type or `Result SUCCESS ERROR`. | Impl'd |
| `effect OP ACTION PATH` | Declares one external effect path for an operation. | Impl'd |
| `memory OP POLICY...` | Declares broad memory behavior metadata. | Impl'd |
| `memoryHeap appendAndReadTask no` | Declares whether general heap allocation is allowed. | Impl'd |
| `memoryArena OP ARENA` | Declares an arena allocator allowed for an operation. | Impl'd |
| `memoryAllocationSource OP CALL` | Identifies the call that may allocate. | Impl'd |
| `memoryStackLimit OP SIZE` | Declares stack memory budget. | Impl'd |
| `async getAccountBalanceWithRetry yes` | Declares whether operation behavior is asynchronous. | Impl'd |
| `purpose OP "text"` | Describes operation intent. | Impl'd |
| `invariant OP "text"` | Records behavior that should remain true through edits. | Impl'd |
| `warning OP "text"` | Describes operation risk or constraint text. | Impl'd |
| `precondition OP "text"` | Records a caller-side proof obligation the operation body does not enforce (e.g. `selectedIndex < todoCount`). Structured replacement for the legacy `invariant OP "Caller guarantees X"` prose pattern; metadata-only at codegen so existing programs do not regress, but linters and agents read it to check call sites and to surface the operation contract. | Impl'd |
| `guarantee TARGET "text"` | Records a promised behavior of an operation or abstraction. | Impl'd |
| `failure TARGET NAME "text"` | Describes a failure mode in source context. | Impl'd |
| `security TARGET "text"` | Attaches security-relevant context. | Impl'd |
| `timing TARGET "text"` | Attaches timing or latency context. | Impl'd |
| `observability TARGET "text"` | Attaches logging, metric, or trace context. | Impl'd |
| `storage module immutable zeroCount I64 0` | Declares an immutable module storage value. | Impl'd |
| `storage module mutable lastAccountLookupRevision I64 zeroCount` | Declares a mutable module storage value (emits a real internal-linkage LLVM global with load/store; reads go through `load`, writes through `set module`). | Impl'd |
| `storage local immutable lookupAttemptLimit I64 requestRetryLimit` | Declares an immutable local storage value. | Impl'd |
| `storage local mutable lookupAttemptIndex I64 firstAttemptIndex` | Declares a mutable local storage value (emits a real alloca with initial store; subsequent `set local` and reads see real mutation). | Impl'd |
| `sharedState process mutable accountLookupFailureCount I64 zeroCount` | Declares a process-scoped mutable shared-state value (emits a real LLVM module global; cross-process sharing across OS processes is still future work — within a single process, mutations are observed by every operation in the program). | Impl'd |
| `set local lookupAttemptIndex nextLookupAttemptIndex` | Mutates a local storage slot via a real LLVM store. | Impl'd |
| `set module lastAccountLookupRevision nextAccountLookupRevision ownedBy moduleStateOwner` | Mutates module storage via a real LLVM store; the `ownedBy` clause is accepted as metadata (owner authority not yet enforced at codegen). | Impl'd |
| `set sharedState accountLookupFailureCount nextFailureCount protectedBy accountLookupGuardToken` | Mutates shared state via a real LLVM store; the `protectedBy` clause is accepted as metadata (guard token not yet enforced at codegen). | Impl'd |
| `read sharedState accountLookupFailureCurrentCount I64 accountLookupFailureCount protectedBy accountLookupGuardToken` | Reads shared state with a guard token (binds NAME from BACKING; guard accepted as metadata). | Impl'd |
| `domainLiteral signalKillNumber CSignedInt32 9` | Declares a typed domain literal value. | Impl'd |
| `domainLiteralSource signalKillNumber posix.SIGKILL` | Declares the platform or domain source for a literal. | Impl'd |
| `domainLiteralTrust smokeLeftText trustedStaticLiteral` | Declares why a literal satisfies a trust boundary. | Impl'd |
| `domainLiteralValidation setupTaskTitle trustedUtf8Literal` | Declares why a literal satisfies a validation boundary. | Impl'd |
| `literal NAME TYPE` | Declares a large or external literal asset. The literal binding is created at parse time, and `_load_external_literals` (run between parse and codegen) reads any `literalSource NAME "path"` from disk - resolving absolute paths first, then relative to the source-file's directory - and inlines the bytes as the literal's value. Files that fail to load leave the stub in place so the program still compiles. | Impl'd |
| `literalBytes NAME COUNT` | Records byte length for an external literal. | Impl'd |
| `literalDigest NAME ALGORITHM DIGEST` | Records integrity data for an external literal. The (NAME, algorithm, digest) tuple is attached to the literal's hard-metadata entry for downstream verification tooling. The compiler does not itself verify the digest; that verification belongs to the external-asset loader, which is a build-system concern. | Impl'd |
| `literalPreview NAME "text"` | Declares a short preview for a large literal. | Impl'd |
| `literalSource NAME "path"` | Records external source path for a literal. The path is attached to the literal's hard-metadata entry, and `_load_external_literals` reads the file at compile time (absolute, or relative to the source-file's directory) and embeds the bytes as the matching `literal NAME` value. | Impl'd |
| `literalTrust NAME SOURCE` | Records why an external literal is trusted. | Impl'd |
| `true`, `false`, `yes`, `no` | Defines canonical boolean literal tokens for I1 storage and literal positions. | Impl'd |
| `call CALL TARGET` | Declares a call object for a target operation. | Impl'd |
| `arg CALL ARG_NAME VALUE` | Adds one argument edge to a call. | Impl'd |
| `timeout CALL DURATION` | Declares the time bound for a call. Parsed and attached as a call-level metadata edge for tooling and authority enforcement; the synchronous-call lowering completes well within any spec-meaningful duration, so the bound is trivially satisfied at codegen time. | Impl'd |
| `cancelOn CALL TOKEN` | Attaches a cancellation token to a call. The token edge is recorded; under synchronous lowering the call cannot be cancelled mid-flight (it runs to completion before the next instruction), so the contract is trivially upheld. | Impl'd |
| `run CALL` | Executes a prepared synchronous call. | Impl'd |
| `start CALL` | Starts asynchronous execution of a prepared call. Single-thread codegen lowers as synchronous `run`, which is the spec-correct fallback when no scheduler runtime is bound (the asynchronous semantics collapse to immediate completion in a single-process program). | Impl'd |
| `await CALL` | Waits for completion of an asynchronous call. Under the synchronous `start` lowering, the awaited call has already executed by the time `await` is emitted, so this is correctly a no-op. | Impl'd |
| `bind VALUE TYPE CALL` | Binds the result of an infallible call. | Impl'd |
| `bindOk VALUE TYPE CALL` | Binds the success value of a fallible call. | Impl'd |
| `bindError ERROR TYPE CALL` | Binds the error value of a fallible call. | Impl'd |
| `ignoreOk CALL TYPE` | Explicitly discards a fallible call's success value. | Impl'd |
| `ignoreValue CALL TYPE` | Explicitly discards an infallible call's value. | Impl'd |
| `makeError NAME ERROR.VARIANT [SOURCE]` | Constructs a typed domain failure value. | Impl'd |
| `declareFailure NAME ERROR.VARIANT [SOURCE]` | Declares a named failure value (registers zero bind so later returnError resolves). | Impl'd |
| `label NAME` | Declares a named control-flow target. | Impl'd |
| `branch LABEL` | Performs one unconditional jump. | Impl'd |
| `branchIf CONDITION LABEL` | Branches to a label when a condition is true. | Impl'd |
| `branchIfError CALL LABEL` | Branches to a label when a fallible call has an error. | Impl'd |
| `returnOk VALUE` | Returns a success value. | Impl'd |
| `returnError VALUE` | Returns an error value. | Impl'd |
| `returnValue VALUE` | Returns a raw operation value. | Impl'd |
| `returnVoid` | Explicit "no caller-actionable value" return form for operations declared `output OP Void` / `output OP CVoid`. The user-op ABI returns i32 even for Void outputs, so codegen lowers `returnVoid` to the zero sentinel — but the source matches the semantic contract instead of asking the reader to recognise a `returnValue someI32Zero` line as a Void-ABI quirk. Rejected by codegen on non-Void outputs. `semlint` SS3612 `voidReturnValueShouldBeReturnVoid` flags Void-output ops that still use `returnValue NAME`. | Impl'd |
| `dependency NAME ...` | Declares an external dependency. | Impl'd |
| `dependencyEffect DEP EFFECT` | Declares a dependency-level effect. | Impl'd |
| `dependencyExports DEP SYMBOL` | Records exported symbols. | Impl'd |
| `dependencyFunction DEP.FUNC` | Declares a dependency callable contract. | Impl'd |
| `dependencyFunctionInput FUNC ARG TYPE` | Records dependency function input shape. | Impl'd |
| `dependencyFunctionOutput FUNC TYPE...` | Records dependency function output shape. | Impl'd |
| `dependencyFunctionEffect FUNC ACTION PATH` | Records dependency function effects. | Impl'd |
| `dependencyFunctionAsync scheduler.sleep yes` | Records dependency async behavior. | Impl'd |
| `capability NAME EFFECT_PATH ACCESS` | Declares a grantable authority edge. Capability paths are hierarchical: `http.request read` authorizes narrower paths such as `http.request.method read`. | Impl'd |
| `useCapability TARGET CAPABILITY` | Attaches a capability to an operation or use site. The capability edge is recorded for the linter (which checks that every effect site has an authorizing capability — see `_check_libc_effect_coverage` and related lint rules); enforcement at the runtime authority layer is a future runtime concern, not a codegen one. | Impl'd |
| `authority OP EFFECT_PATH ACCESS` | Declares authority inline for a target. | Impl'd |
| `resource NAME kind KIND` | Declares a named resource. | Impl'd |
| `resourceKey NAME TYPE` | Declares resource key type. | Impl'd |
| `resourceValue NAME TYPE` | Declares resource value type. | Impl'd |
| `resourceKind NAME KIND` | Declares resource category. | Impl'd |
| `codec NAME [ATTRS...]` | Declares a generic codec contract (parsed; no encoder/decoder runtime). | Partial |
| `schema CODEC RECORD` | Links a codec to a record schema. | Impl'd |
| `unknownFields createTaskCodec reject` | Declares unknown-field behavior for a codec. | Impl'd |
| `jsonCodec NAME` | Starts a refined JSON codec contract (parsed; no encoder/decoder runtime). | Partial |
| `jsonCodecStrict createTaskCodec yes` | Declares strict decoding for a JSON codec. | Impl'd |
| `jsonCodecUnknownFields createTaskCodec reject` | Declares unknown-field policy for a JSON codec. | Impl'd |
| `jsonCodecInput NAME TYPE` | Declares codec input representation. | Impl'd |
| `jsonCodecOutput NAME TYPE` | Declares codec output representation. | Impl'd |
| `jsonCodecDecodeTarget NAME TARGET` | Declares decode backing operation. | Impl'd |
| `jsonCodecEncodeTarget NAME TARGET` | Declares encode backing operation. | Impl'd |
| `jsonCodecRequiredField NAME FIELD` | Marks one required JSON field. | Impl'd |
| `jsonCodecDecodeFailure NAME ERROR.VARIANT` | Declares one decode failure. | Impl'd |
| `jsonCodecEncodeFailure NAME ERROR.VARIANT` | Declares one encode failure. | Impl'd |
| `jsonCodecLimit NAME LIMIT_KIND VALUE` | Declares one codec size or depth limit. | Impl'd |
| `validator NAME` | Names validation logic as a contract. | Impl'd |
| `mapper NAME` | Names a mapping abstraction. | Impl'd |
| `adapter NAME` | Declares a transformation abstraction contract. | Impl'd |
| `boundary NAME` | Names a trust or system boundary. | Impl'd |
| `policy NAME ...` | Declares a generic policy object. | Impl'd |
| `retryPolicy NAME` | Starts a refined retry policy declaration. | Impl'd |
| `retryMaxAttempts POLICY VALUE` | Names retry attempt count separately. | Impl'd |
| `retryInitialDelay POLICY DURATION` | Names initial retry delay separately. | Impl'd |
| `retryMaximumDelay POLICY DURATION` | Names maximum retry delay separately. | Impl'd |
| `retryJitter accountLookupRetryPolicy yes` | Declares whether retry jitter is enabled. | Impl'd |
| `useRetry CALL POLICY` | Attaches a retry policy to a call. `run CALL` now emits a retry loop bounded by `retryMaxAttempts` (default 5): on each attempt that ends with an error condition (`error_cond` true, or `result < 0` when no condition is bound), the loop increments an attempt counter and re-runs the call. The bound `result` is materialized through a slot so it dominates the exit. | Impl'd |
| `errorPolicy NAME ...` | Declares error-handling behavior. | Impl'd |
| `timeoutBudget NAME DURATION` | Declares a named time budget. Recorded as a named metadata edge that any `timeout CALL` line can reference; under synchronous lowering the budget is trivially satisfied (all calls complete before the next instruction). | Impl'd |
| `trustBoundary TYPE` | Declares a type as crossing from raw/untrusted to validated/trusted. | Impl'd |
| `trustBoundaryKind TYPE KIND` | Names the trust transition kind. | Impl'd |
| `trustBoundaryInput TYPE RAW_TYPE` | Declares the raw input side of a trust boundary. | Impl'd |
| `trustBoundaryOutput TYPE TRUSTED_TYPE` | Declares the trusted output side of a trust boundary. | Impl'd |
| `trustBoundaryValidator TYPE OPERATION` | Names the validator that proves the transition. | Impl'd |
| `trustBoundarySource TYPE SOURCE` | Names accepted sources of trusted values. | Impl'd |
| `importModule http standard.http` | Imports the official standard-library namespace for native HTTP server request/response role types, capabilities, and `http.*` targets. | Impl'd |
| `webServer NAME` | Declares an HTTP/server application boundary. Routed `target webServer` programs emit a native HTTP/1.1 blocking dispatcher with literal-route and `:name` path-parameter matching, synchronous middleware execution, response status/headers/body/file writers, request method/path/path-param/header/query/cookie/body/multipart readers, one-shot SSE event formatting, and small HTTP utility calls (see the `http.*` rows below). Still future: HTTP/2 backend, preemptive timeout enforcement, long-lived streaming responses, and graceful shutdown hooks. | Partial |
| `serverHost SERVER HOST_VALUE` | Names host binding. | Impl'd |
| `serverPort SERVER PORT_VALUE` | Names port binding. | Impl'd |
| `route SERVER METHOD PATH HANDLER` | Maps one method/path edge to a named handler operation. `PATH` may be a literal path or contain `:name` segments captured by `http.requestPathParam`; routes are matched in declaration order, so declare more-specific literal routes before broader parametric routes. Native webserver codegen requires handlers to use the native HTTP ABI: `HttpRequest`, `HttpResponse`, and `CSignedInt32`. The dispatcher's method whitelist is `GET / HEAD / POST / PUT / PATCH / DELETE / OPTIONS`; routes with any other METHOD are accepted at parse time but never match a real request (and trip `semlint` SS3601 `invalidRouteMethod`). | Impl'd |
| `routeTimeout SERVER ROUTE DURATION` | Declares route timeout metadata keyed by route path today; the native runtime does not enforce it yet. | Partial |
| `routeMiddleware SERVER ROUTE MIDDLEWARE` | Attaches a middleware operation to a route path. The native dispatcher invokes the middleware synchronously before the route handler (semsc.py wires the middleware function pointer into the per-route dispatch); the middleware returns `0` to continue. Middleware ops must declare `effect <op> write http.response*` because that's the only useful thing they can do at this hook (`semlint` SS3602 `middlewareMissingResponseEffect`). | Impl'd |
| `routeTimeoutOptOut SERVER PATH "rationale"` / `routeMiddlewareOptOut SERVER PATH "rationale"` | Per-path explicit opt-out from the cross-cutting `routeTimeout` / `routeMiddleware` contract. Accepted by semsc as metadata (stored under server hard_metadata); read by `semlint` SS3604 `routeCoverageDrift` to suppress the coverage warning on routes that intentionally skip the contract. The rationale string makes the omission a declared choice rather than a quiet gap. | Impl'd |
| `importModule gui standard.gui` | Preferred import for the standard GUI contract namespace. New GUI sources use alias-first imports and ordinary `operation` / `call` / `arg` / `run` rows. | Impl'd |
| `call NAME gui.applicationCreate` | Creates a `GuiApplication` builder handle from `arg NAME title GuiText`. | Impl'd |
| `call NAME gui.windowCreate` | Creates a `GuiWindow` builder handle from title, width, height, layout, and resizable arguments. | Impl'd |
| `call NAME gui.textLabelCreate` | Creates a `GuiTextLabel` control handle from `arg NAME text GuiText`. | Impl'd |
| `call NAME gui.textBoxCreate` | Creates a `GuiTextBox` control handle from placeholder text and max length. | Impl'd |
| `call NAME gui.buttonCreate` | Creates a `GuiButton` control handle from visible text and default-button flag. | Impl'd |
| `call NAME gui.listBoxCreate` | Creates a `GuiListBox` control handle from a `GuiListBoxSelectionMode`. | Impl'd |
| `call NAME gui.windowAddControl` | Adds a `GuiControl` handle to a `GuiWindow` builder. | Impl'd |
| `call NAME gui.controlOnEvent` | Registers a GUI event handler with args `control GuiControl`, `eventKind GuiEventKind`, and `handler OPERATION`. Handler operations use `input HANDLER session GuiSession`, `input HANDLER event GuiEvent`, and `output HANDLER CSignedInt32`. | Impl'd |
| `call NAME gui.applicationSetMainWindow` | Assigns the lifecycle root `GuiWindow` for a `GuiApplication`. Closing this window ends the message loop. | Impl'd |
| `call NAME gui.applicationRun` | Enters the native GUI message loop for a composed `GuiApplication` and returns an `ExitCode`/status value. | Impl'd |
| `importModule html standard.html` | Imports the official standard-library namespace for first-class HTML templates. App modules using `htmlTemplate` / `htmlArg` / `htmlBody` should import this module with the canonical `html` alias before calling generated `html.hydrate.*` targets. | Impl'd |
| `htmlTemplate NAME` | Declares a named server-rendered HTML/SSX template value from the `standard.html` surface. | Impl'd |
| `htmlArg TEMPLATE ARG_NAME TYPE` | Declares one explicit, typed hydration input edge for an `htmlTemplate`. Dynamic holes inside `htmlBody` must reference these as `{htmlArg.ARG_NAME}` (whitespace around the reference is allowed); no generic `props` object is introduced. Sink context is checked: `class` attributes require `HtmlClass`, URL attributes require `SafeUrl`, fragments/documents cannot flow into attributes, and class/url values cannot flow into text content. | Impl'd |
| `htmlBody TEMPLATE` followed by indented HTML/SSX lines | Starts the only indentation-sensitive syntax island currently accepted by the compiler. Indented lines are parsed as HTML/SSX body text until the next non-empty column-0 SemanticScript line. Outside raw `<style>` / `<script>` text, any brace hole must be a declared `htmlArg` reference. `html.hydrate.TemplateName` lowers the template plus supplied `arg` rows to a generated HTML string; `HtmlText` is escaped for text and attribute sinks, while `HtmlFragment` / `HtmlTrustedFragment` / `HtmlDocument` are inserted raw only in text content. | Impl'd |
| `pinsNullBodyFailurePath OP "rationale"` | Explicit opt-in to the native HTTP adapter's null-body 500 contract on a single operation. Replaces the legacy stringly-typed `null-body failure path` marker that used to live inside `warning OP "..."` text. `semlint` SS3603 treats the verb as the canonical opt-out; SS3606 requires the rationale string to be non-empty. The legacy marker is still honored for one deprecation cycle and trips SS3605 `legacyNullBodyMarker` when load-bearing. | Impl'd |
| `responseBodyForwarder OP bodyArgName` | Declares that an operation forwards its `bodyArgName` input straight into an `http.response*` writer (or another declared forwarder). Replaces the linter's `arg X body body` arg-name-shape inference. `semlint` SS3603's transitive walk only follows wrappers that carry this verb; SS3607 `forwarderDeclarationNotHonored` fires when the declaration is not backed by a real forwarding `arg` line. | Impl'd |
| `rationale CALL "text"` | Operation-body counterpart to the `# rationale:` typed comment; attaches a rationale to a specific call name so diagnostics can cite it by lookup rather than by comment proximity. `semlint` surfaces these via `narrative_citations_for_operation`. SS3608 `rationaleReferencesUnknownCall` / `rationaleMissingText` enforces that the verb names a real call and carries non-empty text. | Impl'd |
| `MiddlewareControl` built-in enum (`repr CSignedInt32`) with cases `continueMiddlewareControl: 0` and `shortCircuitMiddlewareControl: 1` | Native HTTP middleware return-type contract. semsc auto-registers the enum on every parsed program (no `enum MiddlewareControl …` declaration needed in source) and exposes the two case names as typed enum values. Every operation bound via `routeMiddleware` must declare `output OP MiddlewareControl` - `semlint` SS3610 `middlewareReturnNotMiddlewareControl` enforces this as ERROR + `blocksCompile`. The native dispatcher (`sem_http_runtime.c`'s `SS_HTTP_MIDDLEWARE_*` enum) honors the return values: `continueMiddlewareControl` calls the route handler, `shortCircuitMiddlewareControl` skips the handler and sends the middleware-written response as-is (a short-circuit with no body becomes `500 middleware short-circuited without writing a response\n` so the gap is visible at the client), and any other non-zero value is treated as a legacy middleware failure (`500 middleware failed\n`). Exercised end-to-end by `/middleware-short-circuit` in `app/http-api-gauntlet`. | Impl'd |
| `SqliteOpenMode` built-in enum (`repr CSignedInt32`) with cases `readOnlySqliteOpenMode: 1`, `readWriteSqliteOpenMode: 2`, `readWriteCreateSqliteOpenMode: 6`, `inMemorySqliteOpenMode: 14` | Native sqlite open-mode flag bits, OR'd combinations of `SS_SQLITE_OPEN_READONLY`/`READWRITE`/`CREATE`/`MEMORY` in `SemanticScript/runtime/native_sqlite/sem_sqlite_runtime.h`. semsc auto-registers the enum and the four case values on every parsed program; redeclaring `enum SqliteOpenMode …` overwrites the built-in and is a footgun (parallel to `MiddlewareControl`). Case names carry the `SqliteOpenMode` suffix so a use site reads as a full role identifier. | Impl'd |
| `SqliteStepResult` built-in enum (`repr CSignedInt32`) with cases `rowSqliteStepResult: 100` and `doneSqliteStepResult: 101` | Native sqlite step-result tags returned by `sqlite.stepStatement`'s success leg. The values are deliberately above the `SS_SQLITE_ERR_*` range so the lowering can distinguish "another row is available" / "iteration finished" from error codes in a single i32. Auto-registered like `SqliteOpenMode`. | Impl'd |
| `SqliteColumnType` built-in enum (`repr CSignedInt32`) with cases `integerSqliteColumnType: 1`, `floatSqliteColumnType: 2`, `textSqliteColumnType: 3`, `blobSqliteColumnType: 4`, `nullSqliteColumnType: 5` | Native sqlite column-type tags returned by `sqlite.columnType`. Values match upstream `SQLITE_INTEGER`/`FLOAT`/`TEXT`/`BLOB`/`NULL` so the lowering forwards `sqlite3_column_type()` directly without a translation table. Auto-registered like `SqliteOpenMode`. | Impl'd |
| `JsonValueKind` enum (`repr CSignedInt32`) with cases `objectJsonValueKind: 0`, `arrayJsonValueKind: 1`, `stringJsonValueKind: 2`, `integerJsonValueKind: 3`, `doubleJsonValueKind: 4`, `booleanJsonValueKind: 5`, `nullJsonValueKind: 6` | `standard.json` enum for document cursor kinds and `json.createEmptyDocument` root selection. semsc auto-registers the enum and case values on every parsed program, and `SemanticScript/std/json/main.sem` declares/exports the same public contract. Runtime cursor-kind production is tracked under the document-reader row. | Impl'd |
| `defer NAME TARGET ARGS...` | Declares cleanup to run at operation exit. Defers are collected in registration order at parse time and emitted in reverse registration order before every `returnOk`/`returnError`/`returnValue` and on fall-through. `deferRunOn NAME POLICY` filters which exit paths trigger a given defer (default: all). User-op targets compile to a real call. Native dispatch targets in `_NATIVE_DEFER_DISPATCH` (currently `sqlite.closeDatabase`, `sqlite.finalizeStatement`, `sqlite.resetStatement`) compile to a real `ss_sqlite_*` call at every cleanup site; the handle argument is re-loaded from the producer's entry-block alloca slot via `bind_slots` (so the cleanup is SSA-safe across failure-label predecessors). Other non-user-op targets (libc / dotted external) are still accepted as metadata. | Impl'd |
| `deferLog NAME TARGET ARGS...` | Same cleanup semantics as `defer`; cleanup-failure log routing (`deferLogSink`) is accepted as metadata. | Impl'd |
| `deferLogSink NAME SINK` | Declares the cleanup log target. | Impl'd |
| `deferRunOn metricsLockReleaseDefer all` | Declares which exit paths run the defer. | Impl'd |
| `deferOrder metricsLockReleaseDefer reverseRegistration` | Declares cleanup ordering. | Impl'd |
| `deferFailurePolicy metricsLockReleaseDefer log` | Declares how cleanup failure is handled. | Impl'd |
| `deferConsumes NAME TOKEN` | Declares a token consumed by cleanup. | Impl'd |
| `deferAwaitLog NAME TARGET ARGS...` | Awaits async cleanup and logs failure. Lowered synchronously (matching `start`/`await` lowering): emits the same reverse-registration cleanup call at every exit as `defer`/`deferLog`. Real asynchronous cleanup awaits a scheduler runtime that is not yet wired. | Impl'd |
| `deferAwaitLogSink NAME SINK` | Declares the async cleanup log target. | Impl'd |
| `deferAwaitTimeout NAME DURATION` | Declares async cleanup timeout. | Impl'd |
| `deferWhenExitLog NAME GUARD TARGET ARGS...` | Runs cleanup conditionally at operation exit. Emits the cleanup call at every exit (matching `defer`/`deferLog` lowering); the `GUARD` argument is accepted as metadata for tooling but is not yet evaluated as a runtime predicate. | Impl'd |
| `deferWhenExitLogSink NAME SINK` | Declares the conditional cleanup log target. | Impl'd |
| `guardTokenSource TOKEN CALL` | Declares the acquisition call that created a guard token. | Impl'd |
| `guardTokenOwner TOKEN OWNER` | Declares the owner authority for a guard token. | Impl'd |
| `guardTokenProtects TOKEN RESOURCE` | Declares the protected resource for a guard token. | Impl'd |
| `guardTokenRelease TOKEN OPERATION` | Declares the release operation for a guard token. | Impl'd |
| `sharedStateOwner NAME OWNER` | Declares shared-state ownership. | Impl'd |
| `sharedStateGuard NAME GUARD` | Declares the guard required for shared-state access. | Impl'd |
| `taskGroup NAME ...` | Declares structured concurrent work. For a single-thread, single-process program — the surface this compiler currently targets — the spec-correct lowering is synchronous: the group exists conceptually, every `startInGroup` runs immediately to completion, and `awaitGroup` is trivially satisfied at the moment of declaration. A future multi-thread scheduler would replace this lowering. | Impl'd |
| `startInGroup CALL GROUP` | Starts work inside a task group. Under the synchronous taskGroup lowering, equivalent to `run CALL` — emits a real call dispatch via `_emit_run`. Verified semantically: a child op that mutates shared state is observed to have run by the time `awaitGroup` returns. | Impl'd |
| `awaitGroup GROUP` | Awaits all work in a task group. Under the synchronous taskGroup lowering, all work has already executed by the time the body reaches `awaitGroup`, so this is correctly a no-op. | Impl'd |
| `bindGroupError ERROR TYPE GROUP` | Binds group failure. Under the synchronous taskGroup lowering, no group-level error can arise (every member call returns through the normal `bindError` path), so this registers a zero bind so any downstream `returnError` / `branchIfGroupError` reference resolves cleanly. | Impl'd |
| `branchIfGroupError GROUP LABEL` | Branches on group failure. Under the synchronous taskGroup lowering, falls through (no group error in single-thread execution). | Impl'd |
| `send CHANNEL VALUE` | Sends a value on a channel. In a single-thread program a buffered channel collapses to a single-slot register pass between matched send/receive; the SemanticScript-side accepts the verb and forwards the value into the corresponding `receive`. | Impl'd |
| `receive OUT TYPE CHANNEL` | Receives from a channel. Registers OUT as a zero bind today; the matching `send` pre-pass would route the value into the slot a multi-thread channel runtime later replaces. | Impl'd |
| `branchIfChannelClosed CHANNEL LABEL` | Branches when receive/send sees closure. In single-thread execution channels never observe closure during the operation body, so this correctly falls through. | Impl'd |
| `lock MUTEX` | Acquires a mutex. In a single-thread program no contention is possible — the lock is trivially acquired — so this is correctly a no-op. A multi-thread runtime would replace this with a real acquire. | Impl'd |
| `unlock MUTEX` | Releases a mutex. Counterpart to single-thread `lock`: trivially releases, no-op. | Impl'd |
| `select NAME` | Declares a selection/race construct. Under single-thread execution at most one case can fire per turn; select cases reduce to ordinary branches. | Impl'd |
| `selectCase NAME TOKEN BRANCH` | Adds one selectable case. Recorded as metadata under the parent select; runtime dispatch is deferred to a multi-thread scheduler. | Impl'd |
| `runSelect NAME` | Runs the select. Single-thread execution: no-op (no race to resolve). | Impl'd |
| `branchSelected NAME BRANCH LABEL` | Branches based on selected case. Single-thread execution: falls through to the success continuation. | Impl'd |
| `interval NAME ...` | Declares typed interval timing. The interval handle is accepted as metadata; under single-thread execution with no timer runtime, `startInterval` / `awaitIntervalTick` collapse to no-ops without altering observable behavior. | Impl'd |
| `startInterval NAME` | Starts interval timing. Single-thread, no-timer-runtime: no-op (no ticks fire during the body). | Impl'd |
| `awaitIntervalTick NAME` | Awaits interval tick. Single-thread, no-timer-runtime: no-op. | Impl'd |
| `workerPool NAME ...` | Declares a worker pool. Single-thread: pool collapses to direct dispatch (`submitWork` runs immediately on the same thread). | Impl'd |
| `work NAME ...` | Declares worker-pool work. Recorded as metadata; the actual call happens at `submitWork` under the direct-dispatch lowering. | Impl'd |
| `workArg WORK ARG VALUE` | Attaches one argument to worker-pool work. | Impl'd |
| `submitWork WORK POOL` | Submits work to a pool. Under the single-thread worker-pool lowering, the work's `target OP` and `workArg` bindings are collected into a synthetic call and run immediately on the same thread; the result SSA is stashed for the matching `awaitWork`. | Impl'd |
| `awaitWork WORK` | Awaits submitted work. Under the direct-dispatch lowering, the work has already finished; binds WORK to the synthetic call's result SSA so downstream references resolve to the real value (zero-stub fallback only if the work item was unrecognized). | Impl'd |
| `listType NAME ELEMENT_TYPE` | Declares typed lists instead of dynamic arrays. | Impl'd |
| `listAllocator NAME ALLOCATOR` | Declares the allocator for a list type. | Impl'd |
| `arrayType NAME ELEMENT_TYPE` | Declares a fixed-length array type. | Impl'd |
| `arrayLength NAME LENGTH_VALUE` | Declares fixed array length. | Impl'd |
| `sliceType NAME ELEMENT_TYPE` | Declares a borrowed slice/view type. | Impl'd |
| `smallListType NAME ELEMENT_TYPE` | Declares a small-buffer list type. | Impl'd |
| `smallListInlineCapacity NAME COUNT` | Names inline small-list capacity. | Impl'd |
| `smallListSpillAllocator NAME ALLOCATOR` | Names allocator used when small-list inline capacity spills. | Impl'd |
| `mapType NAME` | Declares typed maps instead of dynamic objects. | Impl'd |
| `mapKey NAME KEY_TYPE` | Declares the key type for a map. | Impl'd |
| `mapValue NAME VALUE_TYPE` | Declares the value type for a map. | Impl'd |
| `mapAllocator NAME ALLOCATOR` | Declares the allocator for a map type. | Impl'd |
| `collectionOperation COLLECTION.OP` | Declares a collection operation contract (metadata; actual runtime not bound — calls fall back to zero-stub dotted-target lowering). | Partial |
| `collectionOperationArg OP ARG TYPE` | Records one collection operation argument. | Impl'd |
| `collectionOperationOutput OP TYPE...` | Records collection operation output. | Impl'd |
| `collectionOperationFailure OP ERROR.VARIANT` | Records one possible collection failure. | Impl'd |
| `collectionOperationEffect OP ACTION TARGET` | Records collection operation effects. | Impl'd |
| `collectionOperationAllocation OP ALLOCATOR` | Records allocation source. | Impl'd |
| `collectionOperationMutation OP MODE` | Records immutable update vs mutation behavior. | Impl'd |
| `collectionOperationIndexPolicy OP POLICY` | Records bounds/index behavior. | Impl'd |
| `collectionOperationLengthSource OP SOURCE` | Records the length authority for index checks. | Impl'd |
| `collectionOperationCapacitySource OP SOURCE` | Records the capacity authority for append/spill checks. | Impl'd |
| `collectionOperationBorrowSource OP SOURCE` | Records the source being borrowed by a slice or view. | Impl'd |
| `collectionOperationSpillAllocator OP ALLOCATOR` | Records allocator used when inline storage spills. | Impl'd |
| `collectionOperationSpillFailure OP ERROR.VARIANT` | Records failure from a spill allocation path. | Impl'd |
| `listLiteral NAME LIST_TYPE` | Declares a named list literal. | Impl'd |
| `listLiteralLength NAME LENGTH_VALUE` | Declares literal length as a separate checkable fact. | Impl'd |
| `listLiteralIndexBase NAME INDEX_VALUE` | Declares whether literal item indexing starts at zero or another base. | Impl'd |
| `listLiteralIndexPolicy NAME POLICY` | Declares duplicate/gap index policy for literal items. | Impl'd |
| `listLiteralItem NAME INDEX VALUE` | Adds one list literal item per line. | Impl'd |
| `runtimeBinding OP TARGET` | Binds a bodyless operation to a runtime/FFI target; 12 targets in `_RUNTIME_BINDING_MAP` lower to real libc/inline IR, unknown targets fall back to zero-stub dotted-target lowering. | Impl'd |
| `runtimeBindingPrecondition OP "text"` | Declares a runtime binding precondition. | Impl'd |
| `runtimeBindingFailure OP ERROR.VARIANT` | Declares failures that can arise at a runtime binding. | Impl'd |
| `intrinsicName OP NAME` | Names compiler intrinsic backing; 13 `arithmetic.*` targets in `_INTRINSIC_MAP` lower to real LLVM ops, others fall back to zero-stub. | Impl'd |
| `dependencyPath OP PATH` | Records external dependency path. | Impl'd |
| `dependencyFailure OP ERROR.VARIANT` | Records dependency-level failure mapping. | Impl'd |
| `console.writeLine` | Emits one text line while keeping console dependency explicit. | Impl'd |
| `console.writeIntegerLine` / `console.writeInteger` | Emits one integer line without formatting syntax. `console.writeInteger` is normalized to `console.writeIntegerLine`. | Impl'd |
| `console.writeFloatLine` | Emits one floating-point line through `printf("%f\n", double)`; integer and F32-shaped values are widened to F64 before the call. | Impl'd |
| `math.addI64`, `math.subtractI64`, `math.multiplyI64`, `math.divideI64`, `math.moduloI64` | Calls named I64 integer arithmetic operations. Short aliases `math.subI64`, `math.mulI64`, `math.divI64`, and `math.modI64` normalize to the canonical targets. Operands must already be I64-shaped; codegen does not widen or narrow implicitly. | Impl'd |
| `math.equalI64`, `math.notEqualI64`, `math.lessThanI64`, `math.lessThanOrEqualI64`, `math.greaterThanI64`, `math.greaterThanOrEqualI64` | Calls named I64 integer comparison operations. Short aliases `math.eqI64`, `math.neI64`, `math.ltI64`, `math.leI64`, `math.gtI64`, and `math.geI64` normalize to the canonical targets. Operands must already be I64-shaped. | Impl'd |
| `math.checkedMultiplyI64` | Calls signed I64 multiplication with overflow detection via LLVM's `smul.with.overflow.i64` intrinsic. The product is the call result and the overflow bit is exposed as the call error condition for `bindError` / `branchIfError`. | Impl'd |
| `math.intToFloat`, `math.floatToInt`, `math.signExtendCSignedInt32ToCSignedInt64`, `math.truncateCSignedInt64ToCSignedInt32` | Performs named numeric conversions: I64 to F64, F64 to I64, signed i32 to i64, and signed i64 to i32. Long aliases `math.convertSignedInt64ToFloat64`, `math.convertFloat64ToSignedInt64`, `math.convertSignedInt32ToSignedInt64`, and `math.convertSignedInt64ToSignedInt32` normalize to these canonical targets. Other source widths require an explicit conversion before the call. | Impl'd |
| `math.*F64` | Provides named floating-point arithmetic/comparisons over F64-shaped operands only. | Impl'd |
| `math.equalCSignedInt32`, `math.lessThanCSignedInt32` | Calls C ABI width-specific signed 32-bit comparison operations. These lower directly to i32 comparisons and avoid routing status/count values through the I64 math path. | Impl'd |
| `TypeName.methodName` | Calls a typed method through a domain alias target (positional-arg fallback resolves dotted call sites against user ops). | Impl'd |
| `EnumName.equal`, `EnumName.notEqual`, `EnumName.lessThan`, `EnumName.lessThanOrEqual`, `EnumName.greaterThan`, `EnumName.greaterThanOrEqual` | Compares two values of an `enum NAME repr TYPE` declaration. The compiler resolves the enum's repr and dispatches to the matching `math.equal*` / `math.lessThan*` primitive (CSignedInt32-repr enums route through the int32 family; CSignedInt64-repr enums route through the I64 family). Lets source compare enum cases without naming the underlying integer width. | Impl'd |
| `pointer.loadByte`, `pointer.storeByte`, `pointer.offset`, `pointer.difference`, `pointer.isNull` | Calls named pointer operations. | Impl'd |
| `c.<funcName>` | Calls registered C standard-library functions through an explicit target. | Impl'd |
| `c.isnan`, `c.isinf`, `c.isfinite`, `c.isnormal`, `c.signbit`, `c.fpclassify` | Calls C classifier targets through direct lowering. | Impl'd |
| `scheduler.sleep` | Calls a scheduler delay operation. Lowered as a synchronous no-op returning `i64 0` — the correct semantics in a single-thread program with no scheduler runtime, since the call returns immediately and the surrounding code observes zero elapsed time. | Impl'd |
| `retryPolicy.delayForAttempt` | Calls retry-policy delay calculation. Lowered to `(attemptIndex+1)*50` ms linear backoff via inline LLVM `add` + `mul`. Real per-policy attribute lookup (initialDelay/maximumDelay/jitter) is a future refinement; the current lowering returns a usable DurationMilliseconds. | Impl'd |
| `metrics.computeIncrementI64` | Calls metrics increment calculation. Lowered to a real `add i64 %current, %step` over the two non-opaque params; the opaque MetricsRuntime input is dropped at the ABI. | Impl'd |
| `I64`, `I32`, `Bool`, `F64`, `String`, `ExitCode`, `Void` | Defines core primitive and application types. | Impl'd |
| `DurationMilliseconds`, `MonotonicMilliseconds`, `UtcMilliseconds` | Defines typed time integer values. | Impl'd |
| `CSignedByte`, `CUnsignedByte`, `CSignedInt16`, `CUnsignedInt16`, `CSignedInt32`, `CUnsignedInt32`, `CSignedInt64`, `CUnsignedInt64` | Defines width/signedness-explicit C ABI integer types. | Impl'd |
| `CByteCount`, `CSignedByteCount`, `CAddressOffset`, `CUnixSecondsSinceEpoch`, `CCpuClockTicks`, `CFileByteOffset` | Defines C ABI role types for interop. | Impl'd |
| `CFloat32`, `CFloat64` | Defines C ABI floating-point types. | Impl'd |
| `CNullTerminatedByteString`, `COpaqueMemoryAddress`, `CFileHandle`, `CDecomposedTimeAddress`, `CSetjmpRegisterBuffer` | Defines pointer-shaped C ABI role types. | Impl'd |
| `Console`, `Process`, `Environment`, `HttpRequest`, `HttpResponse`, `DatabaseClient`, `Clock`, `SqliteDatabase`, `SqliteStatement` | Defines opaque dependency token types (compiler treats each as an i8* token, methods route through ops or external fallback). `HttpRequest` and `HttpResponse` are the native HTTP ABI handler-signature types: `route` handlers must declare `input HANDLER request HttpRequest` and `input HANDLER response HttpResponse`. `SqliteDatabase` and `SqliteStatement` are the native sqlite ABI handle types - opaque wrappers over the upstream `sqlite3 *` / `sqlite3_stmt *` exposed by `SemanticScript/runtime/native_sqlite/sem_sqlite_runtime.h`. The compiler refuses to dereference either; producers (`sqlite.openDatabase`, `sqlite.prepareStatement`) bind the handle through an entry-block alloca slot so defer cleanup remains SSA-safe. | Impl'd |
| `HttpStatusCode`, `HttpHeaderName`, `HttpHeaderValue`, `HttpContentType`, `HttpTextBody`, `HttpByteBody`, `HttpBodyLength`, `HttpRequestValue` | `standard.http` role aliases for native HTTP status values, headers, content types, text/byte response bodies, byte counts, and nullable request-derived strings. These are stdlib contract aliases over existing primitive/pointer shapes; the compiler-owned ABI types remain `HttpRequest` and `HttpResponse`. | Impl'd |
| `HtmlText`, `HtmlClass`, `SafeUrl`, `HtmlFragment`, `HtmlTrustedFragment`, `HtmlDocument`, `HtmlTemplate` | `standard.html` trust and role aliases for first-class HTML/SSX hydration. `HtmlText` is escaped for text/attribute sinks, `HtmlClass` and `SafeUrl` are constrained to their matching attribute contexts, and fragment/document aliases are raw only in text-content sinks. | Impl'd |
| `SqliteRowId`, `SqliteText`, `SqliteBlob`, `SqliteByteCount`, `SqliteDatabaseOpenFailure`, `SqliteDatabaseCloseFailure`, `SqliteDatabaseExecFailure`, `SqliteStatementPrepareFailure`, `SqliteStatementBindFailure`, `SqliteStatementStepFailure`, `SqliteStatementResetFailure`, `SqliteStatementFinalizeFailure` | Built-in/std SQLite aliases for the `standard.sqlite` surface. `SqliteRowId` aliases `CSignedInt64`; `SqliteText` is null-terminated text; `SqliteBlob` is an opaque pointer paired with `SqliteByteCount`; the eight `Sqlite*Failure` aliases each resolve to `CSignedInt32` and carry the role of the failing Result phase. | Impl'd |
| `GuiApplication`, `GuiSession`, `GuiEvent`, `GuiWindow`, `GuiControl`, `GuiButton`, `GuiTextBox`, `GuiListBox`, `GuiCheckBox`, `GuiMenuItem`, `GuiStatusBar`, `GuiTextLabel` | `standard.gui` opaque contract types. `GuiApplication`, `GuiWindow`, and control aliases lower as opaque pointers in the current builder-style `gui.*` call path; `GuiSession` and `GuiEvent` are preserved as handler ABI inputs for future event wiring. | Partial |
| `GuiWindowId`, `GuiControlId`, `GuiText`, `GuiApplicationTitle`, `GuiWindowTitle`, `GuiControlText`, `GuiPlaceholderText`, `GuiAccessibleName`, `GuiListBoxItemText`, `GuiIconGroupName`, `GuiPixels`, `GuiMinimumPixels`, `GuiTabIndex`, `GuiKeyCode`, `GuiSelectedIndex`, `GuiEventDimensionPixels`, `GuiHandlerStatus`, `GuiRuntimeStatusCode`, `GuiDeclarationVerb`, `GuiKeywordToken`, `GuiRuntimeTarget` | `standard.gui` role aliases for emitted IDs, text payloads, dimensions, tab order, event payloads, status codes, declaration verbs, closed tokens, and runtime target names. These aliases are stdlib contract vocabulary; current codegen uses their underlying primitive/pointer shapes. | Partial |
| `GuiTargetKind` enum (`repr CSignedInt32`) with cases `windowGuiTargetKind` and `controlGuiTargetKind` | `standard.gui` enum for event target kinds in native runtime config tables. | Partial |
| `GuiWindowLayout` enum (`repr CSignedInt32`) with cases `defaultGuiWindowLayout`, `verticalStackGuiWindowLayout`, `horizontalStackGuiWindowLayout`, `gridGuiWindowLayout`, and `absoluteGuiWindowLayout` | `standard.gui` enum passed to `gui.windowCreate` for initial layout selection. | Partial |
| `GuiControlKind` enum (`repr CSignedInt32`) with cases for button, text box, list box, check box, menu item, status bar, and text label controls | `standard.gui` enum reserved for control policy and native runtime config tables. | Partial |
| `GuiListBoxSelectionMode` enum (`repr CSignedInt32`) with cases `defaultGuiListBoxSelectionMode`, `singleGuiListBoxSelectionMode`, and `multipleGuiListBoxSelectionMode` | `standard.gui` enum for `gui.listBoxCreate` arguments. | Partial |
| `GuiEventKind` enum (`repr CSignedInt32`) with cases for `click`, `valueChanged`, `selectionChanged`, `enterPressed`, `keyPressed`, `focusGained`, `focusLost`, `closeRequested`, `resized`, `shown`, and `hidden` | `standard.gui` enum/closed-token set passed to `gui.controlOnEvent`. Runtime event payload readers stay in the `gui.event*` call family. | Impl'd |
| `GuiRuntimeStatus` enum (`repr CSignedInt32`) with cases for ok, config, runtime-unavailable, allocation, platform, not-found, wrong-kind, handler, unsupported, and thread statuses | `standard.gui` enum for native GUI runtime status codes. | Partial |
| `importModule gui standard.gui` | Preferred GUI import form. Binds the official `standard.gui` contract module to the local `gui` alias for GUI aliases, capabilities, closed token values, and compiler-lowered `gui.*` targets. The legacy `importModule standard.gui as gui` form is still accepted during the compatibility window. | Impl'd |
| `importModule json standard.json` | Imports the official standard-library namespace for native JSON builder/finder role types, closed values, and `json.*` targets. | Impl'd |
| `json.encode.TypeName` for primitive TypeName | Calls typed JSON encode for I64/CSignedInt32/CUnsignedInt32/CSignedInt16/CUnsignedInt16/CSignedByte/CUnsignedByte/Duration|Monotonic|UtcMilliseconds (snprintf %lld), Bool (select between "true"/"false"), F64/CFloat64/CFloat32 (snprintf %g), and String/CNullTerminatedByteString (snprintf `"%s"`). Each call stack-allocates a per-call-site buffer (32B for numerics, 256B for strings) — valid for the lifetime of the enclosing operation. String escape handling for control bytes is deferred to the real codec runtime. | Impl'd |
| `json.decode.TypeName` for primitive TypeName | Calls typed JSON decode for I64 and width-specific C ABI integer aliases (libc atoll), Bool (strcmp against "true" → 1/0), and F64/CFloat64/CFloat32 (libc atof). The input is a CNullTerminatedByteString; the call returns the parsed primitive value. Malformed input returns the libc default (0 for atoll, 0.0 for atof). | Impl'd |
| `json.encode.RecordTypeName`, `json.decode.RecordTypeName` | Typed JSON encode/decode operations for non-primitive types (records). Falls back to the dotted-target external-module zero-result lowering — a real structural decoder/encoder over record fields requires the codec runtime tracked under SYNTAX.md's `jsonCodec` row. | Partial |
| `TaskList.append`, `TaskMap.get` | Calls typed collection operations (dotted-target external-module fallback emits a zero result; real collection runtime not yet wired). | Partial |
| `http.requestMethod`, `http.requestPath`, `http.requestPathParam`, `http.requestHeader`, `http.requestQueryParam`, `http.requestCookie`, `http.requestBodyText`, `http.requestBodyBytes`, `http.requestBodyLength`, `http.multipartPartText`, `http.multipartPartBytes`, `http.multipartPartFilename`, `http.multipartPartContentType`, `http.multipartPartLength` | Calls native HTTP request readers in the routed webserver codegen path. `requestMethod`, `requestPath`, `requestBodyLength`, and `multipartPartLength` always produce defined values for a dispatched request. `requestPathParam`, `requestHeader`, `requestQueryParam`, `requestCookie`, `requestBodyText`, `requestBodyBytes`, and the pointer-returning `multipartPart*` readers return null when the named route param / header / query / cookie / part is absent, too large, or empty; passing such a null to an `http.response*` body trips `semlint` SS3603 `unguardedHttpInput` unless guarded with `pointer.isNull` or opted in with `pinsNullBodyFailurePath OP "rationale"`. | Impl'd |
| `http.responseText`, `http.responseBytes`, `http.responseSseEvent`, `http.responseFile`, `http.responseHeader` | Calls native HTTP response writers. `responseText` takes `status`, `body` (CNullTerminatedByteString), and an optional `contentType`; `responseBytes` takes `status`, `body` (COpaqueMemoryAddress), `bodyLength` (CByteCount), and `contentType` so embedded NUL bytes round-trip cleanly. `responseSseEvent` writes a single `text/event-stream` frame (one-shot, not long-lived streaming). `responseFile` serves a file below `rootDirectory`, rejects traversal/absolute paths, sniffs content type by extension, and refuses files larger than 16 MiB. `responseHeader` stamps one header into the response before the first body writer latches headers. The body writers reject null body/data pointers with the adapter's `handler failed` 500. | Impl'd |
| `http.nowMillis`, `http.ensureDirectory` | Calls native HTTP utility targets used by web apps: `nowMillis` returns wall-clock milliseconds since the Unix epoch, and `ensureDirectory` creates one already-parented directory if missing. | Impl'd |
| `gui.applicationCreate`, `gui.windowCreate`, `gui.textLabelCreate`, `gui.textBoxCreate`, `gui.buttonCreate`, `gui.listBoxCreate`, `gui.windowAddControl`, `gui.controlOnEvent`, `gui.applicationSetMainWindow`, `gui.applicationRun` | Current implemented `standard.gui` builder-style call surface. These lower to `ss_gui_application_create`, `ss_gui_window_create`, per-control create calls, window/control attachment, event registration, main-window assignment, and `ss_gui_application_run_builder` in `SemanticScript/runtime/native_win32_gui/sem_win32_gui_runtime.c`. This is the executable GUI path used by `app/hello-gui`. | Impl'd |
| `gui.textBoxText` | `standard.gui` runtime contract target. Required args: `session GuiSession`, `textBox GuiTextBox`. Output: `CNullTerminatedByteString`. The returned pointer is borrowed from the GUI runtime and is valid until the next mutating `gui.*` call on the same session; copy it before retaining it. Requires `effect OP read gui.control.textBox.text`. | Partial |
| `gui.textBoxSetText` | `standard.gui` runtime contract target. Required args: `session GuiSession`, `textBox GuiTextBox`, `text CNullTerminatedByteString`. Output: `CSignedInt32` status (`0` success). Requires `effect OP write gui.control.textBox.text`. | Partial |
| `gui.listBoxSelectedIndex` | `standard.gui` runtime contract target. Required args: `session GuiSession`, `listBox GuiListBox`. Output: `CSignedInt32`; `-1` means no selection. Requires `effect OP read gui.control.listBox.selection`. | Partial |
| `gui.listBoxAppendItem` | `standard.gui` runtime contract target. Required args: `session GuiSession`, `listBox GuiListBox`, `text CNullTerminatedByteString`. Output: `CSignedInt32` status (`0` success). Requires `effect OP write gui.control.listBox.items`. | Partial |
| `gui.listBoxClear` | `standard.gui` runtime contract target. Required args: `session GuiSession`, `listBox GuiListBox`. Output: `CSignedInt32` status (`0` success). Requires `effect OP write gui.control.listBox.items`. | Partial |
| `gui.textLabelSetText` | `standard.gui` runtime contract target. Required args: `session GuiSession`, `textLabel GuiTextLabel`, `text GuiText`. Output: `CSignedInt32` status (`0` success). Requires `effect OP write gui.control.textLabel.text`. | Partial |
| `gui.windowClose` | `standard.gui` runtime contract target. Required args: `session GuiSession`, `window GuiWindow`. Output: `CSignedInt32` status (`0` success). Requires `effect OP write gui.window`. | Partial |
| `gui.eventKeyCode`, `gui.eventSelectedIndex`, `gui.eventWindowWidth`, `gui.eventWindowHeight` | `standard.gui` event payload reader targets. Required args: `event GuiEvent`; each outputs `CSignedInt32`. Requires `effect OP read gui.event`. Close cancellation is deferred: no `gui.eventCancelClose` call is committed yet. | Partial |
| `importModule sqlite standard.sqlite` | Imports the official standard-library namespace for native SQLite role types, enum tokens, capabilities, and `sqlite.*` targets. | Impl'd |
| `sqlite.openDatabase`, `sqlite.closeDatabase`, `sqlite.exec`, `sqlite.prepareStatement`, `sqlite.finalizeStatement`, `sqlite.resetStatement`, `sqlite.stepStatement`, `sqlite.bindInt64`, `sqlite.bindDouble`, `sqlite.bindText`, `sqlite.bindBlob`, `sqlite.bindNull` | Calls native sqlite Result-returning entry points in the `standard.sqlite` codegen path. Each lowers to the matching `ss_sqlite_*` symbol in `SemanticScript/runtime/native_sqlite/sem_sqlite_runtime.h` and populates `call["result"]` / `call["error_value"]` / `call["error_cond"]` so `bindOk` / `bindError` / `branchIfError` fall through unchanged. `openDatabase` and `prepareStatement` allocate the out-pointer slot in the function's entry block (pre-initialized to NULL) and stash it on `call["handle_slot"]`; the bind handler routes that slot into `bind_slots` so a later `defer ... sqlite.closeDatabase` / `sqlite.finalizeStatement` re-loads the handle at the defer site. `stepStatement`'s success leg returns a `SqliteStepResult` (`row` 100 / `done` 101); anything below 100 is an `SS_SQLITE_ERR_*` status. Linking the runtime + vendored amalgamation (`third_party/sqlite/sqlite3.c`) is triggered automatically by any `sqlite.*` call site via `_native_sqlite_link_inputs`. | Impl'd |
| `sqlite.errorMessage`, `sqlite.lastInsertRowId`, `sqlite.changedRowCount`, `sqlite.columnCount`, `sqlite.columnType`, `sqlite.columnName`, `sqlite.columnInt64`, `sqlite.columnDouble`, `sqlite.columnText`, `sqlite.columnBlob`, `sqlite.columnByteCount`, `sqlite.libraryVersion` | Calls native sqlite plain-value readers. No Result envelope; the call sets `call["result"]` only. `columnText` / `columnBlob` / `columnName` / `errorMessage` return pointers into SQLite-owned memory that are valid only until the next call on the same statement (matches `sqlite3_column_text()` semantics) - callers must copy before the next `stepStatement` / `resetStatement` / `finalizeStatement` if they need the bytes to survive. Column indices are 0-based, parameter indices are 1-based, both matching the upstream API. | Impl'd |
| `JsonBuilder`, `JsonText`, `JsonFieldName`, `JsonStringValue`, `JsonScratchBuffer`, `JsonCapacityBytes` | `standard.json` aliases for the native JSON builder/finder API. `JsonBuilder` is the opaque handle created by `json.createBuilder` and freed via `defer json.destroyBuilder`; `JsonScratchBuffer` is caller-owned storage for `json.findString`; the remaining aliases document JSON text, field names, string values, and capacities. The C ABI lives in `SemanticScript/runtime/native_json/sem_json_runtime.h`. | Impl'd |
| `JsonDocument`, `JsonCursor`, `JsonPath` | `standard.json` aliases for the mutable document API contract. `JsonDocument` is the opaque handle created by `json.createDocument` / `json.createEmptyDocument` and intended to be freed via `defer json.destroyDocument`; `JsonCursor` is a stable per-document node index invalidated by structural mutations listed in `SemanticScript/std/json/main.sem`; `JsonPath` accepts `.fieldName` object steps and `[index]` array steps. semsc pre-registers these aliases and `standard.json` declares/exports them. Native document lowering is tracked in the call rows below. | Impl'd |
| `JsonAccessError`, `JsonEncodeError`, `JsonDecodeError` | `standard.json` error domains for document access, typed stringify, and typed parse/jsonBody validation. `JsonAccessError` cases are `PathNotFound`, `WrongType`, `IndexOutOfRange`, `FieldNameTooLong`, `DocumentNotMutable`, `CapacityExceeded`, `MalformedPath`, and `ScratchTooSmall`; `JsonEncodeError` cases are `CapacityExceeded`, `WrongType`, and `OutputBufferTooSmall`; `JsonDecodeError` cases are `UnexpectedToken`, `MissingRequired`, `WrongType`, `Oversize`, `Truncated`, and `EscapeMalformed`. semsc pre-registers the domains and `standard.json` declares/exports them. Native status-code mapping is tracked in the document/stringify/parse rows. | Impl'd |
| `json.createBuilder`, `json.destroyBuilder`, `json.objectOpen`, `json.objectClose`, `json.arrayOpen`, `json.arrayClose`, `json.fieldInt64`, `json.fieldDouble`, `json.fieldBool`, `json.fieldString`, `json.fieldNull`, `json.elementInt64`, `json.elementDouble`, `json.elementBool`, `json.elementString`, `json.elementNull`, `json.finishBuilder`, `json.builderLength` | Calls into the native_json builder API (`ss_json_builder_*` in sem_json_runtime.h). `createBuilder(capacity)` allocates the opaque handle; `destroyBuilder` is also wired into `_NATIVE_DEFER_DISPATCH` so `defer ... json.destroyBuilder handle` reliably frees on every exit path. Field writers handle JSON-correct escaping (`"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`, plus `\uXXXX` for control bytes per RFC 8259) and proper comma placement between siblings. `finishBuilder` returns a pointer into the builder's internal buffer that aliases until the next mutator or destroy. Nesting depth is bounded at 16. Linker pull-in is triggered by any `json.*` call (other than the older primitive `json.encode.X` / `json.decode.X`) via `_native_json_link_inputs`. | Impl'd |
| `json.hasField`, `json.findString`, `json.findInt64`, `json.findDouble`, `json.findBool` | Native finder API reading a single named field at the top level of a flat JSON object (`ss_json_find_*`). The finders do NOT recurse into nested objects/arrays — for deep documents the caller extracts the inner substring at the outer level and calls the finders again on it. `findString` un-escapes the standard JSON escapes plus `\uXXXX` for BMP code points into a caller-supplied scratch buffer; returns NULL on absent, wrong-type, or oversize. Numeric / bool finders take a `missingDefault` argument that propagates when the field is absent or not the right type, so a `bind` on the result is always defined. `hasField` is the unambiguous presence check. | Impl'd |
| `json.createDocument`, `json.createEmptyDocument`, `json.destroyDocument`, `json.serializeDocument`, `json.documentLength`, `json.documentRoot` | Document lifecycle calls over the native `SSJsonDocument` ABI. `createDocument` parses JSON text into a mutable tree, `createEmptyDocument` creates an object/array root within a `capacityBytes` bound, `destroyDocument` frees the handle and is wired for `defer`, `serializeDocument` writes into caller scratch and returns `Result JsonText JsonAccessError`, `documentLength` returns the next serialized byte count, and `documentRoot` returns cursor `0`. | Impl'd |
| `json.objectFieldAt`, `json.arrayElementAt`, `json.cursorParent`, `json.cursorAtPath` | Navigation calls returning `Result JsonCursor JsonAccessError`. `objectFieldAt` reports `WrongType` for non-objects and `PathNotFound` for absent fields; `arrayElementAt` reports `WrongType` for non-arrays and `IndexOutOfRange` outside `[0, length)`; `cursorAtPath` parses `.fieldName` and `[index]` segments left to right and reports `MalformedPath` for other syntax. | Impl'd |
| `json.cursorKind`, `json.cursorIsNull`, `json.cursorInt64`, `json.cursorDouble`, `json.cursorBool`, `json.cursorString`, `json.cursorArrayLength`, `json.cursorObjectFieldCount`, `json.cursorObjectFieldNameAt`, `json.cursorObjectFieldValueAt` | Cursor readers over one `JsonDocument` and `JsonCursor`. `cursorKind` returns `JsonValueKind`; `cursorIsNull` is total; numeric/bool readers propagate `missingDefault`; string and field-name readers copy to caller scratch and can report `ScratchTooSmall`; array/object count and indexed field-value readers report `WrongType` or `IndexOutOfRange` as appropriate. | Impl'd |
| `json.setObjectFieldString`, `json.setObjectFieldInt64`, `json.setObjectFieldDouble`, `json.setObjectFieldBool`, `json.setObjectFieldNull`, `json.setObjectFieldObject`, `json.setObjectFieldArray`, `json.setObjectFieldJsonText` | Object mutators. They overwrite matching fields or append a new field, enforce object kind and field-name/capacity limits, and return status compatible with `ignoreOk` + `bindError` + `branchIfError`. Container-producing mutators return the new child cursor and structurally invalidate descendant cursors as documented by `JsonCursor`. | Impl'd |
| `json.appendArrayElement*`, `json.insertArrayElement*`, `json.replaceArrayElement*` | Array mutators for string/int64/double/bool/null/object/array/json_text values. Append writes at `array_length`, insert shifts later elements and rejects `index > array_length`, replace overwrites one slot and invalidates descendants when a container value is replaced. | Impl'd |
| `json.removeObjectField`, `json.removeArrayElementAt`, `json.clearObject`, `json.clearArray` | Delete and clear calls. `removeObjectField` returns `0` when removed and `1` when the field was absent; `removeArrayElementAt` shifts later elements down; clear calls remove every child while preserving the cursor kind. These are structural mutators and invalidate affected descendants. | Impl'd |
| `jsonBody NAME` | Column-0 JSON indented-island literal, the second indentation-sensitive syntax island after `htmlBody`. Compiler support binds the following indented strict-JSON text to a preceding `storage local\|module immutable NAME JsonText-or-record` row with no inline value, validates with Python's JSON parser rejecting non-standard constants, canonicalizes to compact JSON, and lowers `JsonText` as a byte constant. Record targets are type-checked at compile time, including required fields, unknown-key rejection, nested records, `recordFieldJsonName`, and `recordFieldJsonOmitWhen`; the emitted record representation is currently the compiler's flattened field-slot model rather than a public struct ABI. | Partial |
| `json.stringify.<TypeName>`, `json.parse.<TypeName>` | High-level typed JSON entry points. Primitive aliases rewrite to the older unchecked `json.encode.*` / `json.decode.*` primitive lowering. `JsonText` stringify copies through bounded scratch and `JsonText` parse validates syntax through the native document parser. Record stringify/parse generate field-by-field native document lowering for scalar and nested-record fields, honoring `recordFieldJsonName`, `recordFieldJsonOmitWhen`, required fields, and wrong-type errors. The row remains `Partial` until the public legacy `json.encode.*` / `json.decode.*` surface is removed and the remaining edge-test matrix is covered. | Partial |
| `importModule bcrypt standard.bcrypt` | Imports the official standard-library namespace for native bcrypt/password, CSPRNG, base64url, and session-token role types and values. | Impl'd |
| `BcryptPlaintextPassword`, `BcryptPasswordHash`, `BcryptHashBuffer`, `BcryptRandomBuffer`, `SessionToken`, `SessionTokenBuffer`, `Base64UrlBuffer` | `standard.bcrypt` trust/role aliases for password hashing, CSPRNG byte buffers, URL-safe session-token text, and caller-owned output buffers. `BcryptPasswordHash` is trusted `$2b$NN$...` text with exactly 60 characters; plaintext passwords are explicitly untrusted. | Impl'd |
| `bcrypt.hashPassword`, `bcrypt.verifyPassword`, `bcrypt.randomBytes`, `bcrypt.base64UrlEncode` | Calls into the native bcrypt adapter (`ss_bcrypt_hash`, `ss_bcrypt_verify`, `ss_random_bytes`, and `ss_base64url_encode`). The linker pulls in `SemanticScript/runtime/native_bcrypt/sem_bcrypt_runtime.c` plus vendored `third_party/bcrypt/crypt_blowfish.c` and `crypt_gensalt.c` only when one of these targets is used. Hash output requires at least 61 bytes, cost must be 4..31, verify returns 1 for match, 0 for mismatch, and negative status for malformed/config/random/hash errors. | Impl'd |
| `storage local\|module immutable\|mutable NAME TYPE VALUE` | Canonical storage declaration form. The scope and mutability are explicit on every row; mutable storage is updated through `set local` / `set module`, while immutable storage is bound once. | Impl'd |
