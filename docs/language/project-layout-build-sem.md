# Project Layout and build.sem

This page defines the current SemanticScript project-layout rule set. It is
based on the `app/todo` lab project and the current `semsc.py` / `semlint.py`
behavior.

The short version:

```text
build.sem registers modules and build outputs.
main.sem is the executable module entry by convention.
*.sem files own module source.
*.test.sem files own local tests.
build/ owns generated artifacts and is ignored by git.
exports are explicit and must name symbols declared by that module source.
```

## Canonical Layout

Use one folder per project or app:

```text
app/todo/
  build.sem
  main.sem
  domain/
    main.sem
  persistence/
    main.sem
  ui/
    main.sem
  main.test.sem
  build/
    todo.exe
    todo.ll
    resources/
  .semcache/
    github.com/example/dependency/
```

Rules:

- `build.sem` is the single build entry point.
- `main.sem` is the default executable source file for the root module.
- Module folders are organization boundaries; each folder should contain one
  module source, normally `main.sem`.
- Tests live beside the source they test as `*.test.sem`.
- Generated `.exe`, `.ll`, `.obj`, `.res`, `.ico`, and runtime fixture outputs
  belong under the compiler-managed `build/` folder.
- Future fetched dependencies belong under `.semcache/`; that cache is a build
  input cache, not checked-in source.
- Application project folders do not need `module.sem`; module identity,
  imports, and exports belong in the module source file. The standard library
  is the exception: `SemanticScript/std/module.sem` is a top-level relay for
  child `standard.*` modules.

## build.sem Responsibilities

`build.sem` describes project identity, module registration, executable entry,
artifact policy, and future comptime hooks.

Example:

```semanticscript
buildProject todoTui
project TodoTuiApp
modulePath todoTui github.com/monstercameron/SemanticScript/app/todo
languageVersion todoTui "1.0"
projectVersion todoTui "1.0.0"
projectLicense todoTui MIT

sourceRoot todoTui "."
registerModule todoTui app.todo "."
registerModule todoTui app.todo.domain "domain"
registerModule todoTui app.todo.persistence "persistence"
mainFile todoTui "main.sem"
mainOperation todoTui main
testPattern todoTui "*.test.sem"

target console
runtime native 1
entry console main

targetRuntime todoTui nativeExe
buildProfile todoTui dev
optLevel todoTui 2
runtimeChecks todoTui panic
persistLlvmIr todoTui yes
cpuBaseline todoTui generic
cpuTune todoTui generic
cpuFeatureCheck todoTui auto
nativeOutput todoTui "todo.exe"
keepResources todoTui no

comptimeOperation todoTui configureTodoTuiBuild

importModule app.todo
```

### build.sem Schema Reference

Current responsibilities:

- `buildProject PROJECT` names the build tape's project identity.
- `project NAME`, `target NAME`, and `runtime NAME VERSION` remain compiler
  bridge rows used by the current reference compiler. `entry console OP` is
  only for console/native executable builds; `windowsGui` builds omit `entry`
  and use a `standard.gui` application descriptor.
- `modulePath PROJECT PATH` records the Go-style canonical project path.
- `languageVersion PROJECT "VERSION"` records the expected language version.
- `projectVersion PROJECT "VERSION"` records the package/application version.
- `projectLicense PROJECT LICENSE` records the SPDX-style license token.
- `sourceRoot PROJECT "PATH"` records the source root relative to `build.sem`.
- `registerModule PROJECT MODULE_PATH "PATH"` registers a module path to a
  source file or folder.
- `mainFile PROJECT "main.sem"` records the default executable source.
- `mainOperation PROJECT OPERATION` records the default executable operation.
- `testPattern PROJECT "*.test.sem"` records local test discovery rules.
- `testRoot PROJECT "PATH"` records the root used by test discovery.
- `targetRuntime`, `buildProfile`, `optLevel`, `runtimeChecks`, `persistLlvmIr`,
  `emitLlvmIr`, `llvmIrOutput`, `emitOptimizedLlvmIr`,
  `optimizedLlvmIrOutput`, `buildDir`, `buildRoot`, `buildFolderName`,
  `nativeOutput`, and `keepResources` record build-output policy.
- `cpuBaseline`, `cpuTune`, `cpuFeature`, and `cpuFeatureCheck` record CPU
  lowering policy and the build-time host feature check.
- `nativeHttpHost` and `nativeHttpPort` record the native webserver defaults.
- `formatterSetting`, `linterSetting`, and `docsOutput` expose project tool
  settings without adding a TOML/YAML sidecar.
- `comptimeOperation` is reserved for future compile-time configuration work.
- The final `importModule app.todo` is the current compiler bridge that inlines
  the registered executable module.

`build.sem` must not own public API export rows. Those belong in the module
source so a module folder can be understood without editing the build entry
point.

## build.sem Schema Reference

The current build tape is deliberately row-oriented. Every project-scoped row
starts with the same `PROJECT` token declared by `buildProject PROJECT`.

| Row | Required | Meaning |
|---|---:|---|
| `buildProject PROJECT` | yes | Names the single project described by this tape. |
| `project NAME` | bridge | Current compiler project name row. |
| `modulePath PROJECT MODULE_PATH` | yes | Canonical Go-style module/package path. |
| `languageVersion PROJECT "VERSION"` | yes | SemanticScript language contract. |
| `projectVersion PROJECT "VERSION"` | yes | Package or application version. |
| `projectLicense PROJECT LICENSE` | yes | SPDX-style license token, for example `MIT`. |
| `sourceRoot PROJECT "PATH"` | yes | Root for project source paths, relative to `build.sem` unless absolute. |
| `registerModule PROJECT MODULE_PATH "PATH"` | usually | Registers a module folder or source file. |
| `mainFile PROJECT "PATH"` | executable | Default source file for `nativeExe`, `webServer`, and `windowsGui`. |
| `mainOperation PROJECT OPERATION` | nativeExe | Default operation for console/native executable entry. |
| `testRoot PROJECT "PATH"` | no | Root folder for test discovery. |
| `testPattern PROJECT "GLOB"` | no | Local test filename pattern, normally `*.test.sem`. |
| `targetRuntime PROJECT nativeExe\|webServer\|windowsGui\|library` | yes | Project build target class. |
| `buildProfile PROJECT dev\|prod` | yes | Default compiler profile. |
| `runtimeChecks PROJECT off\|traps\|panic` | yes | Runtime check lowering policy. |
| `optLevel PROJECT 0\|1\|2\|3` | yes | LLVM optimization level for JIT/AOT paths. |
| `persistLlvmIr PROJECT auto\|yes\|no` | yes | Whether generated LLVM IR is kept. |
| `emitLlvmIr PROJECT auto\|yes\|no` | no | Project default for pre-optimization `.ll` output. |
| `llvmIrOutput PROJECT "PATH"` | no | Explicit pre-optimization `.ll` path. Basenames use the build folder. |
| `emitOptimizedLlvmIr PROJECT yes\|no` | no | Project default for optimized IR during `--run`. |
| `optimizedLlvmIrOutput PROJECT "PATH"` | no | Explicit optimized `.ll` path. Basenames use the build folder. |
| `buildDir PROJECT "PATH"` | no | Exact artifact directory. Mutually exclusive with build root/folder CLI shape. |
| `buildRoot PROJECT "PATH"` | no | Parent directory where the managed build folder is created. |
| `buildFolderName PROJECT NAME` | no | Managed build folder name. Must be one folder name, not a path. |
| `cpuBaseline PROJECT generic\|native\|x86_64_v1\|x86_64_v2\|x86_64_v3\|x86_64_v4\|arm64_generic\|arm64_v8_2` | no | CPU instruction baseline. Defaults to portable `generic`. |
| `cpuTune PROJECT generic\|native\|CPU_NAME` | no | AOT scheduling tune token. Defaults to `generic`. |
| `cpuFeature PROJECT FEATURE on\|off` | no | Per-feature override. Repeatable. |
| `cpuFeatureCheck PROJECT auto\|off\|warn\|require` | no | Host CPU feature check policy. Defaults to `auto`. |
| `nativeOutput PROJECT "PATH"` | no | Native executable output. Basenames use the build folder. |
| `keepResources PROJECT yes\|no` | no | Keep transient Windows resource files for debugging. |
| `resourcesDir PROJECT "PATH"` | no | Explicit resource scratch directory. Implies kept resources. |
| `nativeHttpHost PROJECT "HOST"` | webServer | Default webserver host metadata. |
| `nativeHttpPort PROJECT PORT` | webServer | Default webserver port metadata. |
| `formatterSetting PROJECT KEY VALUE` | no | Project formatter setting row. |
| `linterSetting PROJECT KEY VALUE` | no | Project linter setting row. |
| `docsOutput PROJECT "PATH"` | no | Documentation output directory. |
| `comptimeOperation PROJECT OPERATION` | reserved | Future 2.0 compile-time build hook. |
| `importModule MODULE_PATH` | bridge | Current compiler bridge that inlines registered module source. |

Strict checks now reject multiple `buildProject` rows, project-name drift,
malformed project rows, invalid enum values, missing required rows, and
`buildFolderName` values that are paths.

## CPU Feature Checks

CPU flags are a build-tape concern, not a module-source concern. The safe
default is portable:

```semanticscript
cpuBaseline todoTui generic
cpuTune todoTui generic
cpuFeatureCheck todoTui auto
```

For a local-only performance build, a project may request host-native lowering:

```semanticscript
cpuBaseline todoTui native
cpuTune todoTui native
cpuFeatureCheck todoTui require
```

Specific features can be required or disabled:

```semanticscript
cpuBaseline todoTui x86_64_v2
cpuFeature todoTui avx2 off
cpuFeatureCheck todoTui auto
```

`cpuFeatureCheck auto` inspects the build machine with LLVM before codegen and
fails if the requested required feature set is missing. That is useful for
local JIT/AOT builds because it prevents producing or running binaries with
instructions this CPU cannot execute. It is not a cross-compilation proof:
use `cpuFeatureCheck off` only when the target machine is known separately.

## Native Webserver Example

```semanticscript
buildProject helloWeb
project HelloWeb
modulePath helloWeb github.com/example/hello-web
languageVersion helloWeb "1.0"
projectVersion helloWeb "1.0.0"
projectLicense helloWeb MIT

sourceRoot helloWeb "."
registerModule helloWeb app.hello_web "."
mainFile helloWeb "main.sem"
testRoot helloWeb "."
testPattern helloWeb "*.test.sem"

target webServer
runtime native 1

targetRuntime helloWeb webServer
buildProfile helloWeb dev
runtimeChecks helloWeb panic
optLevel helloWeb 2
persistLlvmIr helloWeb yes
emitLlvmIr helloWeb auto
emitOptimizedLlvmIr helloWeb no
buildFolderName helloWeb build
cpuBaseline helloWeb generic
cpuTune helloWeb generic
cpuFeatureCheck helloWeb auto
nativeOutput helloWeb "hello_web.exe"
nativeHttpHost helloWeb "127.0.0.1"
nativeHttpPort helloWeb 18080

importModule app.hello_web
```

## Native Windows GUI Example

The build tape owns only the target/link bridge. GUI vocabulary belongs to the
imported `standard.gui` module, which should provide the metadata contracts,
capabilities, and validation rules for application/window/control declarations.

`build.sem`:

```semanticscript
buildProject helloGui
project HelloGui
modulePath helloGui github.com/example/hello-gui
languageVersion helloGui "1.0"
projectVersion helloGui "1.0.0"
projectLicense helloGui MIT

sourceRoot helloGui "."
registerModule helloGui app.hello_gui "."
mainFile helloGui "main.sem"
testRoot helloGui "."
testPattern helloGui "*.test.sem"

target windowsGui
runtime native 1

targetRuntime helloGui windowsGui
buildProfile helloGui dev
runtimeChecks helloGui panic
optLevel helloGui 2
persistLlvmIr helloGui yes
buildFolderName helloGui build
cpuBaseline helloGui generic
cpuTune helloGui generic
cpuFeatureCheck helloGui auto
nativeOutput helloGui "hello_gui.exe"

importModule app.hello_gui
```

`main.sem`:

```semanticscript
module app.hello_gui
importModule gui standard.gui

guiApplication helloGuiApp
guiApplicationTitle helloGuiApp "Hello GUI"
guiApplicationMainWindow helloGuiApp mainWindow

guiWindow mainWindow
guiWindowApplication mainWindow helloGuiApp
guiWindowTitle mainWindow "Hello GUI"
guiWindowWidth mainWindow 800
guiWindowHeight mainWindow 480
guiWindowLayout mainWindow verticalStack
guiWindowResizable mainWindow yes
```

Rules:

- Do not declare `entry console` or `entry windowsGui` in a `windowsGui` build
  tape.
- The compiler bridge should consume only the normalized application/main-window
  descriptor needed to start the runtime.
- Shape checks such as duplicate controls, allowed events, accessibility names,
  and GUI capability coverage belong in `standard.gui` and lint/tooling where
  possible.

## Library/Package Example

```semanticscript
buildProject todoDomain
project TodoDomain
modulePath todoDomain github.com/example/todo/domain
languageVersion todoDomain "1.0"
projectVersion todoDomain "1.0.0"
projectLicense todoDomain MIT

sourceRoot todoDomain "."
registerModule todoDomain app.todo.domain "."
testRoot todoDomain "."
testPattern todoDomain "*.test.sem"

target library
runtime native 1

targetRuntime todoDomain library
buildProfile todoDomain dev
runtimeChecks todoDomain panic
optLevel todoDomain 2
persistLlvmIr todoDomain auto
emitLlvmIr todoDomain no
emitOptimizedLlvmIr todoDomain no
buildFolderName todoDomain build
cpuBaseline todoDomain generic
cpuTune todoDomain generic
cpuFeatureCheck todoDomain auto
formatterSetting todoDomain lineWidth 100
linterSetting todoDomain maxTier T4
docsOutput todoDomain "docs"
```

## Module Source Responsibilities

A module source declares the module it is, the registered modules it imports,
and the explicit symbols it exports.

Example:

```semanticscript
module app.todo
modulePurpose app.todo "Keyboard-driven console todo app."
moduleOwns app.todo "TUI lifecycle, keyboard handling, todo state, and save/load."
moduleDoesNotOwn app.todo "Reusable standard library abstractions."
moduleInvariant app.todo "main.sem is the executable entry selected by build.sem."

importModule domain app.todo.domain
importModule persistence app.todo.persistence

exportType app.todo TodoItem
exportError app.todo MainError
exportOperation app.todo main
exportOperation app.todo renderScreen
exportConstant app.todo maxTodoCount

type TodoItem TodoItemRecord
error MainError
storage module immutable maxTodoCount CSignedInt64 128

operation main
...
```

Rules:

- `module MODULE_PATH` must name a module registered by `build.sem`.
- `importModule ALIAS MODULE_PATH` is the preferred project import form.
  `importModule MODULE_PATH [as ALIAS]` remains supported for legacy source
  and standard-library samples.
- `exportType`, `exportError`, `exportOperation`, `exportCapability`, and
  `exportConstant` are explicit public contract rows.
- `exportType` covers aliases, records, and enums; there are no separate
  `exportRecord` or `exportEnum` rows in the current contract shape.
- Exports are never inferred from reachability, entry points, call sites, or
  tests.
- An `export*` row must target the current module and must name a symbol
  declared by that same module source.
- Public names are private by default. Importers may only rely on symbols that
  appear in the provider's export rows, even while the current compiler bridge
  still inlines registered module sources.
- `exportConstant` is for stable value contracts: `const`, `literal`,
  `domainLiteral`, or `storage module immutable`. Mutable module storage,
  local storage, and `sharedState` must cross module boundaries through
  exported operations with declared effects.
- The export row does not need to appear after the declaration. The current
  parser has operation bodies without an `endOperation` marker, so operation
  exports are usually safest near the top of the file.

## Export Contract Tape

The linter exposes a reusable export contract tape through
`build_export_contract_tape(gather_extended(parse_file(path)))`. The tape is a
flat list of source-located edges so tools can stream, diff, and render public
API without guessing from reachability.

Each `ExportContractEdge` carries:

- `moduleName`
- `exportVerb`
- `symbolName`
- `edgeKind`
- `values`
- `line`

Current edge kinds include:

- `export.row`
- `operation.input`
- `operation.output`
- `operation.effect`
- `operation.useCapability`
- `operation.authority`
- `operation.failureType`
- `operation.failureCase`
- `operation.async`
- `operation.timing`
- `operation.memory`
- `type.alias`
- `type.record`
- `type.field`
- `type.enum`
- `type.enumCase`
- `error.declaration`
- `error.case`
- `capability.authority`
- `constant.value`
- `constant.literalEncoding`
- `constant.literalSource`
- `constant.literalDigest`
- `constant.literalTrust`

This shape is the handoff contract for import resolution, dependency loading,
language-server indexing, and documentation generation. If a symbol is absent
from the tape, an importer should treat it as private.

## Import and Export Boundary

Imports are explicit contract edges. A module import names a provider module
registered by `build.sem` and may bind that provider to a local alias. Aliased
imports create qualified names backed by the provider's export contract tape.

Good:

```semanticscript
importModule persistence app.todo.persistence
call loadCall persistence.loadTodos
```

Compatibility:

```semanticscript
importModule app.todo.persistence as persistence
importModule app.todo.persistence
```

The alias-first form is preferred for project modules because it puts the local
namespace before the provider path and makes call sites mechanically
predictable. Unaliased `importModule MODULE_PATH` keeps the legacy import bridge
alive, but new multi-module code should use an alias.

## Import Contracts

Qualified names are resolved from provider export rows only:

```semanticscript
importModule persistence app.todo.persistence
call loadCall persistence.loadTodos
input saveHandler todo persistence.TodoItem
useCapability saveHandler persistence.todoStoreReader
arg limitCall max persistence.maxTodoCount
```

Rules:

- `moduleAlias.operationName` resolves only when the provider has
  `exportOperation MODULE operationName`.
- `moduleAlias.TypeName`, `moduleAlias.ErrorType`,
  `moduleAlias.CapabilityName`, and `moduleAlias.CONSTANT` resolve only through
  matching `exportType`, `exportError`, `exportCapability`, and
  `exportConstant` rows.
- Qualified access to private provider symbols is rejected. Current compiler
  import inlining is not authority to bypass the export tape.
- Qualified diagnostics preserve the source name, such as
  `persistence.loadTodos`, even though the current compiler lowers that to the
  inlined operation name internally.
- Module aliases must be unique and must not shadow a local operation, type,
  error, capability, or constant.

Singular imports are allowed when a module intentionally wants a local facade
name:

```semanticscript
importModule persistence app.todo.persistence
importOperation loadTodos persistence loadTodosFromDisk
importType TodoItem persistence TodoItem
importError TodoStoreError persistence TodoStoreError
importCapability TodoStoreReader persistence todoStoreReader
importConstant MaxTodoCount persistence maxTodoCount
```

Rules:

- Singular imports use `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_NAME`
  and equivalent `importType`, `importError`, `importCapability`, and
  `importConstant` rows.
- Singular imports select from the provider export tape; they never create,
  infer, or re-export a provider symbol.
- Wildcard imports are rejected.
- A singular import must not shadow a local declaration or another singular
  import.
- Bare unqualified calls into aliased modules are rejected unless there is a
  matching singular import row. Prefer qualified calls when the provider domain
  context helps the reader.
- Many singular imports from the same module produce a readability warning.

Imported operation contracts carry their exported input, output, effect,
capability, and failure edges into linter checks. Imported types carry
alias/record/enum metadata; imported errors carry cases; imported capabilities
carry effect path and access mode. This is the handoff API for dependency
cache work: `build_import_contract_index(facts)` returns qualified and singular
symbols keyed to provider export tape edges.

Imported operation effects are caller-visible. When a consumer calls an
exported operation whose contract tape includes an `operation.effect` edge, the
consumer operation must restate that effect, or a broader hierarchical effect
path, in its own source:

```semanticscript
importModule github app.net.github

operation syncIssues
output syncIssues Void
effect syncIssues read github.api
useCapability syncIssues githubApiReader

call fetchIssueCall github.fetchIssue
run fetchIssueCall
returnVoid
```

This keeps network, filesystem, database, and observability authority from
disappearing behind wrappers or module boundaries.

## Dependency Fetch, Cache, And Lock Rows

Dependency rows live in `build.sem` because fetching source is build-time
authority, not ordinary program behavior.

```semanticscript
dependency todoTui semstd github.com/example/semstd v1.0.0
dependencyFetch todoTui semstd github example/semstd v1.0.0
dependencyIntegrity todoTui semstd commit:abcdef1234567890

dependency todoTui semhttp github.com/example/semhttp v0.3.0
dependencyFetch todoTui semhttp http "https://example.com/semhttp-v0.3.0.tar.gz"
dependencyIntegrity todoTui semhttp sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

dependencyCache todoTui ".semcache"
dependencyLock todoTui "sem.lock"
```

Rules:

- `dependency PROJECT ALIAS MODULE_PATH VERSION_OR_REF` names the requested
  module contract.
- `dependencyFetch PROJECT ALIAS github OWNER/REPO REF` is the canonical GitHub
  fetch shape. The explicit `OWNER/REPO REF` split gives cache and lock tooling
  stable keys without parsing arbitrary URLs.
- `dependencyFetch PROJECT ALIAS http "https://..."` is the generic HTTPS
  archive/API fetch shape. Plain `http://` is rejected.
- `dependencySource PROJECT ALIAS SOURCE` remains as a compatibility row; new
  build tapes should prefer `dependencyFetch` when the source must be fetched.
- `dependencyIntegrity` must use `sha256:<64 hex>` for archive bytes or
  `commit:<7-40 hex>` for resolved GitHub commits.
- `dependencyCache` should normally be `.semcache`; it is ignored source cache,
  not checked-in project source.
- `dependencyLock` names the future lock tape. Locked builds should read
  resolved commits and checksums from the lock tape before touching the network.

The current compiler validates the row shapes but does not yet perform network
fetching. The linter emits `SS255x` diagnostics when remote dependency rows are
missing cache, lock, source, or integrity context.

## Registered Module Source Selection

When `build.sem` has `registerModule` rows, the compiler resolves registered
module imports before legacy filesystem fallback.

`registerModule PROJECT MODULE_PATH "PATH"` may point at:

- a direct `.sem` or `.sscript` source file;
- a folder containing `main.sem`;
- a folder containing `index.sem`;
- a folder containing a source file named after the module leaf;
- a folder containing exactly one non-test `.sem` or `.sscript` file.

Ambiguous folders should be fixed with `main.sem` or a direct file path. Test
files must not be selected as normal module source.

## Build Artifacts

The compiler-managed artifact directory defaults to `SOURCE_DIR/build`.

Examples:

```powershell
python SemanticScript\compiler\semsc.py app\todo\build.sem --emit-exe
python SemanticScript\compiler\semsc.py app\todo\build.sem --emit-exe --build-root ..\artifacts
python SemanticScript\compiler\semsc.py app\todo\build.sem --emit-exe --build-folder-name semantic-build
python SemanticScript\compiler\semsc.py app\todo\build.sem --emit-exe --build-dir C:\sem-artifacts\todo-dev
```

Rules:

- `--build-root PATH` changes the parent directory for the managed build folder.
- `--build-folder-name NAME` renames the managed folder; it must be one folder
  name, not a path.
- `--build-dir PATH` selects the exact artifact directory and cannot be
  combined with `--build-root` or `--build-folder-name`.
- Basename outputs such as `--emit-exe todo.exe` resolve into the managed build
  directory.
- Generated resources live under `build/resources/` only when resources are
  persisted for debugging; otherwise they are transient and embedded into the
  native executable.

## Linter Contract

The current linter enforces the project-module boundary with `SS250x` rules:

| Code | Rule |
|---|---|
| `SS2520` | A known-but-invalid top-level row must not appear in `build.sem`. |
| `SS2521` | A build tape must declare exactly one `buildProject`. |
| `SS2522` | Required build rows must be present for the active project. |
| `SS2523` | Project-scoped build rows must have the required shape. |
| `SS2524` | Singleton build rows must not be duplicated. |
| `SS2525` | Build enum values, LLVM opt levels, and HTTP ports must be valid. |
| `SS2526` | `buildFolderName` must be one folder name, not a path. |
| `SS2527` | Project-scoped rows must target the active `buildProject`. |
| `SS2501` | A registered module path must select a deterministic module source. |
| `SS2502` | `export*` rows must not live in `build.sem`. |
| `SS2503` | A module declaration in project code must be registered by `build.sem`. |
| `SS2504` | A project module import must target a registered module. |
| `SS2505` | A module export must target the module declared by that source. |
| `SS2506` | An exported symbol must be declared by that module source. |
| `SS2507` | A module must not export the same public symbol more than once. |
| `SS2508` | Mutable module storage must not be exported as a constant. |
| `SS2509` | Local storage and shared state must not be exported directly. |
| `SS2510` | Imported module operations are private unless exported by the provider. |
| `SS2511` | Exported operations should have `purpose`. |
| `SS2512` | Exported operation names should be domain-specific, not generic placeholders. |
| `SS2513` | Exported operations should declare every effect implied by known runtime calls. |
| `SS2514` | Exported dependency wrappers should carry module ownership context. |
| `SS2530` | `importModule` rows must use a supported module/alias shape. |
| `SS2531` | Module aliases must not collide or shadow local declarations. |
| `SS2532` | Wildcard singular imports are rejected. |
| `SS2533` | Singular imports must target a known module alias. |
| `SS2534` | Qualified or singular imports may only access exported provider symbols. |
| `SS2535` | Singular imports must not shadow local declarations or other imports. |
| `SS2536` | Ambiguous unqualified imported calls must be qualified or singularly imported. |
| `SS2537` | Bare calls to aliased provider operations are implicit singular imports and are rejected. |
| `SS2538` | Many singular imports from one provider reduce qualified-name clarity. |
| `SS2539` | Generic local singular import aliases hide provider domain context. |
| `SS2540` | Registered module imports must be acyclic. |
| `SS2541` | Qualified and singular constant imports must not expose mutable module storage. |
| `SS2542` | Imported operation effects must be redeclared by the caller. |
| `SS2550` | Dependency aliases must be unique and have a source/fetch row. |
| `SS2551` | Dependency source, fetch, and integrity rows must target declared aliases. |
| `SS2552` | Dependency source/fetch rows must use valid `github` or HTTPS `http` shapes. |
| `SS2553` | Remote dependencies should have strong `sha256:` or `commit:` integrity pins. |
| `SS2554` | Remote dependencies should declare `dependencyCache`. |
| `SS2555` | Remote dependencies should declare `dependencyLock`. |
| `SS3614` | A `mainFile PROJECT "PATH"` row must resolve to a file on disk. |

These diagnostics are deliberately conservative. They prevent agents and tools
from inventing public API from nearby code and make module boundaries auditable
from the source text alone.

## Current Support Boundary

This layout is the intended project model for SemanticScript, but the current
reference compiler still treats some rows as metadata while project-mode parsing
matures.

Implemented now:

- `.sem` and `.sscript` source files.
- `build.sem` as a compiler entry point through the final `importModule`.
- registered module resolution before filesystem fallback.
- compiler-managed build folders.
- `sem build PATH` discovery through the thin `SemanticScript/tools/sem.py`
  driver.
- strict build-tape schema validation in `semsc.py` and `semlint.py`.
- linter validation for registered modules, imports, explicit exports, and
  `mainFile` rename drift.
- linter validation for dependency fetch/source/cache/lock/integrity row shape.
- linter validation that imported operation effects remain visible at caller
  operations.

Partial or reserved:

- full network package fetching from `dependencyFetch`;
- semantic-version module selection;
- automatic test discovery from `testPattern`;
- execution of `comptimeOperation`;
- `windowsGui` native bridge support beyond the minimal target/link/codegen hook;
- `standard.gui` validation and capability coverage for GUI metadata rows;
- lock-tape generation and offline locked builds.
