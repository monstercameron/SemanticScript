# Program Structure

A SemanticScript file is a sequence of top-level declarations followed by one or
more `operation` bodies. The parser keeps a current operation pointer; after
`operation NAME`, operation-scope lines are appended to that operation until a
new `operation` starts.

## Project Header

Common executable console header:

```semanticscript
project FizzBuzzProgram
target console
runtime native 1
module examples.fizzbuzz
entry console main
```

Line schemas:

```text
project NAME
target NAME
runtime NAME VERSION
module DOTTED.PATH
mode NAME
entry console OPERATION
```

`mode` is a closed set. The current recognized mode is:

```semanticscript
mode capturedOutputReplay
```

That mode marks a source file whose output is a captured transcript rather than
a full algorithmic reimplementation. Linters use it to relax specific replay
diagnostics.

## Import Resolution

```semanticscript
importModule standard.string as string
```

For project builds, `build.sem` registers modules and the module source files
own their own imports/exports:

```semanticscript
buildProject taskForgeTui
sourceRoot taskForgeTui "."
registerModule taskForgeTui app.taskforge_tui "."
mainFile taskForgeTui "main.sem"
mainOperation taskForgeTui main

importModule app.todo
```

```semanticscript
module app.todo
importModule app.persistence
exportOperation app.todo main
```

Exports are explicit only. The compiler and linter must not infer a public API
from reachable operations, entry points, or call sites; each `export*` row has
to name a symbol declared by that same module source.

`semsc.py` resolves `importModule ALIAS DOTTED.PATH` and the compatibility
form `importModule DOTTED.PATH [as ALIAS]` before parsing:

1. If the root source has `registerModule` rows, resolve matching module paths
   from that registry first.
2. A registered module path may point directly at a source file or at a folder
   containing `main.sem`, `index.sem`, the leaf module file, or exactly one
   non-test `.sem`/`.sscript`.
3. Resolve canonical standard-library modules through the std search path:
   explicit `--std-path`, `SEMANTICSCRIPT_STD_PATH` / `SEMSC_STD_PATH`,
   vendored `std/` ancestors, current-working-directory std roots, then the
   compiler-bundled `../std`. `standard` maps to `std/module.sem`, and
   `standard.<module>` maps to `std/<module>/main.sem`.
4. Convert unregistered dotted paths to filesystem paths:
   `app.persistence` -> `app/persistence.sem`.
5. Search relative to the source file's directory.
6. Search each discovered std root.
7. Search the project root.
8. Inline imported content with cycle detection while preserving the import row
   for alias and singular-import resolution.

Aliased project imports are namespace edges. A call like
`persistence.loadTodos` resolves only if the provider module exports
`loadTodos`. For local facade names, use `importOperation`, `importType`,
`importError`, `importCapability`, or `importConstant`; those singular imports
also select only from the provider export tape. New project modules should
import registered module paths with aliases; the filesystem/std-lib fallback is
kept for single-file sources and older samples.

## Project Layout Rules

`build.sem` owns the project-wide layout contract. It selects source roots,
registered modules, the executable source file, the executable operation, test
patterns, target runtime, and build artifact locations. `main.sem` is the
default executable source by convention when the build tape selects an
executable target.

`*.test.sem` files are colocated with the module they validate. Project test
discovery reads `testPattern PROJECT "*.test.sem"` from `build.sem` when the
project is using build-tape mode; standard-library smoke tests use the sibling
`main.test.sem` convention described below.

Generated files stay outside source control. Native executables, LLVM IR,
object files, packaged VSIX files, app-local data, and compiler caches belong in
ignored output folders such as `build/` or `.semcache/`, or in explicit release
artifact storage outside the source tree.

## Library, Web Server, and Windows GUI Mode

If a source has no `entry` line, the compiler usually emits every operation as a
callable LLVM function and emits a stub `int main() { return 0; }`. This is how
library-like and declarative files can still compile and link.

Routed `target webServer` programs are the exception. When `webServer` and
`route` metadata are present, `semsc.py` emits a native HTTP/1.1 entrypoint and
exact method/path dispatcher. Route handlers must use the native HTTP ABI:
`HttpRequest`, `HttpResponse`, and `Int32`.

`target windowsGui` uses the normal entry shape: `entry console OPERATION`.
The compiler role should stay narrow: select the Windows GUI bridge, link the
native GUI runtime, and lower explicit `gui.*` calls from `standard.gui`.
Application shape, controls, events, accessibility, effects, and capabilities
belong in `standard.gui`, the GUI runtime, and lint/tooling where possible.
Do not use top-level GUI declaration rows such as `guiApplication`,
`guiWindow`, or `guiButton` in executable source; the committed shape is
ordinary operation/call/argument/run syntax.

A renderable Windows GUI source imports `standard.gui`, creates an application,
creates a window and controls, attaches controls to the window, marks the main
window, and then calls `gui.applicationRun`. The first runtime behavior is:
enter the native Windows message loop and exit that loop when the main window
closes.

```semanticscript
project DesktopWindowSmoke
target windowsGui
runtime native 1
entry console main
module examples.desktopWindowSmoke

importModule gui standard.gui

storage module immutable title GuiText "Desktop Window Smoke"
storage module immutable width GuiPixels 800
storage module immutable height GuiPixels 480
storage module immutable resizable Int32 1

operation main
output main ExitCode
effect main allocate gui.application
effect main allocate gui.window
effect main write gui.window
authority main gui.application allocate
authority main gui.window allocate
authority main gui.window write
call createApp gui.applicationCreate
argument createApp title GuiText title
run createApp
bind value app GuiApplication createApp
call createWindow gui.windowCreate
argument createWindow title GuiText title
argument createWindow width GuiPixels width
argument createWindow height GuiPixels height
argument createWindow layout GuiWindowLayout verticalStackGuiWindowLayout
argument createWindow resizable Bool resizable
run createWindow
bind value window GuiWindow createWindow
call setMainWindow gui.applicationSetMainWindow
argument setMainWindow application GuiApplication app
argument setMainWindow window GuiWindow window
run setMainWindow
ignore value source setMainWindow type Int32
call runApp gui.applicationRun
argument runApp application GuiApplication app
run runApp
bind value status ExitCode runApp
return value status
```

`importModule standard.gui as gui` remains accepted for compatibility, but new
GUI source should use the alias-first `importModule gui standard.gui` form.

Do not write `entry windowsGui OPERATION`; that form is intentionally outside
the committed surface. GUI event handlers are ordinary operations whose
contract is owned by `standard.gui`; the compiler bridge preserves this native
GUI ABI when a handler is wired into the runtime:

```semanticscript
operation closeRequested
input closeRequested session GuiSession
input closeRequested event GuiEvent
output closeRequested Int32
```

Handler return `0` means success. Non-zero handler returns are reserved as
runtime-level event failures; the exact policy is a runtime concern.

## Operations

```semanticscript
operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
memory writeStandardOutputLine noHeapAllocation
async writeStandardOutputLine no
purpose writeStandardOutputLine "Emit one newline-terminated text line"
```

Operation header lines repeat the owner operation name as their first argument.
The parser enforces that ownership for:

```text
input output effect memory async purpose invariant warning
guarantee failure security timing observability
```

Bad:

```semanticscript
operation writeLine
purpose otherOperation "wrong owner"
```

Good:

```semanticscript
operation writeLine
purpose writeLine "owner matches operation"
```

The repetition is deliberate. A single retrieved line is independently
checkable.

## Test Companion Files

A standard-library module folder uses `main.sem` as the linker/import entry.
Its tests live in a sibling `main.test.sem` so the implementation file is not
crowded by smoke / unit-test prose.

```text
std/bit/main.sem       # module standard.bit, exports, implementation
std/bit/main.test.sem  # tests: importModule standard.bit + operation main
```

`main.sem` (module entry):

```semanticscript
module standard.bit
modulePurpose standard.bit "Canonical standard-library module for bit helpers."
exportOperation standard.bit shiftSignedInt64BitsLeft

operation shiftSignedInt64BitsLeft
...
```

`main.test.sem` (companion):

```semanticscript
project StdBitTest
target console
runtime AgentRuntime 0.1
entry console main

importModule standard.bit

error MainError
errorCase MainError BitSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

capability stdoutWriteCapability console.stdout write

operation main
input main console Console
output main Result ExitCode MainError
...
return ok exitOkCode
```

Rules:

- `main.test.sem` lives in the same directory as `main.sem`.
- It has its own `project` block (`StdFooTest` by convention), `entry console
  main`, and `importModule standard.foo` directive. The imported file's header
  lines are stripped by the import resolver, so the test owns the executable.
- Test files consume sibling modules through normal imports and public exports
  by default. Same-folder private symbols are not implicitly visible to tests;
  export a deliberate test helper or keep the helper inside the test file.
- Test files may also import dependency modules declared in the owning
  `build.sem`; the same alias and export-contract rules apply.
- A test file that repeats `module MODULE_PATH` must match the sibling folder
  module exactly. A different module path is a test-discovery diagnostic.
- Test files may declare local helper operations, local constants, and local
  error domains for the test executable. Those declarations belong only to the
  test project and are not exported into the production contract tape.
- Move every smoke-only declaration to the test: the `error MainError`
  domain, `errorCase` variants, and the `capability` declarations the smoke
  uses (`stdoutWriteCapability`, `heapAllocationCapability`, etc.).
- Capabilities used by implementation operations stay in `main.sem`.
- Module-level `error` domains referenced in operation signatures stay in
  `main.sem`.
- The `bind value X Ordering ...` form, or any type alias declared in `main.sem`, is
  not resolvable through the linter's per-file view of the test. Bind the
  underlying primitive instead, for example `bind value X Int32 ...`, when a
  test file consumes a typed alias from its imported module.

The harness `tests/test_stdlib.py` runs `std/<module>/main.test.sem` for every
canonical standard-library module.
## Sections and Groups

`section` and `group*` lines are retrieval/indexing aids. They do not create a
lexical scope.

```semanticscript
section validation
group requestValidation
groupPurpose requestValidation "Keep raw-to-trusted validation edges together"
groupInput requestValidation rawRequestBody
groupOutput requestValidation validatedTask
groupFailure requestValidation requestValidationFailure
```

Use sections for broad document structure. Use groups for named attention and
dataflow clusters that tooling can cite.

