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
- Do not add `module.sem`; module identity, imports, and exports belong in the
  module source file.

## build.sem Responsibilities

`build.sem` describes project identity, module registration, executable entry,
artifact policy, and future comptime hooks.

Example:

```semanticscript
buildProject todoTui
project TodoTuiApp
modulePath todoTui github.com/monstercameron/SemanticScript/app/todo
languageVersion todoTui "1.0"

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
runtimeChecks todoTui panic
persistLlvmIr todoTui yes
nativeOutput todoTui "todo.exe"
keepResources todoTui no

comptimeOperation todoTui configureTodoTuiBuild

importModule app.todo
```

Current responsibilities:

- `buildProject PROJECT` names the build tape's project identity.
- `project NAME`, `target NAME`, `runtime NAME VERSION`, and `entry console OP`
  remain the compiler bridge rows used by the current reference compiler.
- `modulePath PROJECT PATH` records the Go-style canonical project path.
- `languageVersion PROJECT "VERSION"` records the expected language version.
- `sourceRoot PROJECT "PATH"` records the source root relative to `build.sem`.
- `registerModule PROJECT MODULE_PATH "PATH"` registers a module path to a
  source file or folder.
- `mainFile PROJECT "main.sem"` records the default executable source.
- `mainOperation PROJECT OPERATION` records the default executable operation.
- `testPattern PROJECT "*.test.sem"` records local test discovery rules.
- `targetRuntime`, `buildProfile`, `runtimeChecks`, `persistLlvmIr`,
  `nativeOutput`, and `keepResources` record build-output policy.
- `comptimeOperation` is reserved for future compile-time configuration work.
- The final `importModule app.todo` is the current compiler bridge that inlines
  the registered executable module.

`build.sem` must not own public API export rows. Those belong in the module
source so a module folder can be understood without editing the build entry
point.

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

importModule app.todo.domain
importModule app.todo.persistence

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
- `importModule MODULE_PATH [as ALIAS]` should target registered modules in
  project code.
- `exportType`, `exportError`, `exportOperation`, `exportCapability`, and
  `exportConstant` are explicit public contract rows.
- `exportType` covers aliases, records, and enums; there are no separate
  `exportRecord` or `exportEnum` rows in the current contract shape.
- Exports are never inferred from reachability, entry points, call sites, or
  tests.
- An `export*` row must target the current module and must name a symbol
  declared by that same module source.
- The export row does not need to appear after the declaration. The current
  parser has operation bodies without an `endOperation` marker, so operation
  exports are usually safest near the top of the file.

## Import and Export Boundary

Imports are module-level today. The current compiler records an optional alias,
but that alias is not a namespace system yet.

Good:

```semanticscript
importModule app.todo.persistence
```

Not a current project rule:

```semanticscript
importOperation app.todo.persistence loadTodos
```

If single-symbol imports are added later, they should select from explicit
exports only. A single-symbol import must not create or infer a new export in
the producer module.

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
| `SS2501` | A registered module path must select a deterministic module source. |
| `SS2502` | `export*` rows must not live in `build.sem`. |
| `SS2503` | A module declaration in project code must be registered by `build.sem`. |
| `SS2504` | A project module import must target a registered module. |
| `SS2505` | A module export must target the module declared by that source. |
| `SS2506` | An exported symbol must be declared by that module source. |
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
- linter validation for registered modules, imports, explicit exports, and
  `mainFile` rename drift.

Partial or reserved:

- full package fetching from `modulePath`;
- semantic-version module selection;
- automatic test discovery from `testPattern`;
- execution of `comptimeOperation`;
- single-symbol imports;
- true namespace aliasing.
