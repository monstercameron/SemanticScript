# Reference Compiler

The reference compiler is `SemanticScript/compiler/semsc.py`. It parses
line-oriented SemanticScript, resolves imports and external literals, builds an
AST, emits LLVM IR with `llvmlite`, can JIT-run, and can call `clang` for
native executables.

`SemanticScript/tools/sem.py` is the thin project driver. It discovers
`build.sem` from the requested path and delegates to `semsc.py`; it does not
implement a second build engine.

## Commands

Run from the repository's `SemanticScript/` directory unless paths are explicit:

```powershell
python compiler/semsc.py --version
python compiler/semsc.py sem/fizzbuzz.sscript --parse-only
python compiler/semsc.py sem/fizzbuzz.sscript --lint
python compiler/semsc.py sem/fizzbuzz.sscript --run
python compiler/semsc.py sem/fizzbuzz.sscript --emit-ir
python compiler/semsc.py sem/fizzbuzz.sscript --emit-optimized-ir fizzbuzz.opt.ll --run
python compiler/semsc.py sem/fizzbuzz.sscript --emit-exe
python tools/sem.py build ../apps/taskforge-tui --parse-only --quiet
python tools/sem.py check ../apps/taskforge-tui --quiet
python tools/sem.py emit-ir ../apps/taskforge-tui --quiet
python tools/sem.py clean
python tools/sem.py lint ../apps/taskforge-tui -- --summary
python tools/sem.py fmt --check ../apps/taskforge-tui
python tools/sem.py doctor
python tools/sem.py context --json ../apps/taskforge-tui
python tools/sem.py symbols --json ../apps/taskforge-tui
```

The `sem` driver also exposes `run`, `inspect-ir`, `compare-profiles`, and
`bench`. `context --json` reports project roots, entrypoints, tool versions,
runtime feature flags, syntax support counts, and known deferred feature counts.
`symbols --json` reports source files, modules, imports, operations, calls,
inputs, outputs, effects, routes, source locations, and unresolved references.
`clean` previews ignored generated artifacts by default and only deletes them
with `--force`. `lint` currently supports the canonical `--engine semlint`
backend; `fmt` delegates to `SemanticScript/formatter/semfmt.py`; `doctor`
checks Python, llvmlite, clang, Node.js, and native HTTP runtime build
prerequisites.

CLI flags:

| Flag | Behavior |
|---|---|
| `--version` | Print compiler version. |
| `--build-dir PATH` | Set the exact compiler-managed artifact directory. Relative paths resolve beside the source file. Cannot be combined with `--build-root` or `--build-folder-name`. Defaults to `SOURCE_DIR/build`. |
| `--build-root PATH` | Set the parent directory where the managed build folder should be created. Relative paths resolve beside the source file. For example, `--build-root ..` writes to `../build/` by default. |
| `--build-folder-name NAME` | Rename the managed build folder created beside the source or under `--build-root`. Defaults to `build`; must be a single folder name, not a path. |
| `--emit-ir [PATH]` | Write pre-optimization LLVM IR. With no path, writes to the managed build directory. |
| `--persist-llvm-ir auto\|yes\|no` | Control LLVM IR persistence. `auto` is the default and persists only with `--emit-ir`; `yes` writes a `.ll` sidecar in the managed build directory when no explicit path is provided; `no` disables IR persistence. |
| `--emit-optimized-ir PATH` | Write post-optimization LLVM IR during `--run`. |
| `--cpu-baseline generic\|native\|x86_64_v1\|x86_64_v2\|x86_64_v3\|x86_64_v4\|arm64_generic\|arm64_v8_2` | Select CPU instruction baseline for LLVM/clang lowering. Defaults to `generic` unless `build.sem` provides `cpuBaseline`. |
| `--cpu-tune CPU_NAME` | Pass an AOT clang tune token such as `generic`, `native`, or `alderlake`. |
| `--cpu-feature FEATURE=on\|off` | Add one CPU feature override. May be repeated; `+FEATURE` and `-FEATURE` are also accepted. |
| `--cpu-feature-check auto\|off\|warn\|require` | Control host CPU feature checks before codegen. `auto` fails local builds that request unavailable features. |
| `--run` | JIT-execute `main` and return its exit code. |
| `--emit-exe [PATH]` | AOT compile with clang. With no path, writes to the managed build directory. |
| `--lint` | Run built-in compiler lint pass. |
| `--strict` | Run the compiler's built-in lint pass, enable the current strict fallible-call disposition checks, and treat diagnostics as fatal. This is a CI strictness flag; it is separate from source-level `languageMode strictExecutable`. |
| `--parse-only` | Parse, optionally lint, and stop before codegen. |
| `--opt-level N` | LLVM optimization level `0..3`, default `2` unless `build.sem` provides `optLevel PROJECT N`. |
| `--build-profile dev\|prod` | Runtime safety profile for compiled output. `dev` is the default and embeds `SSRUN001` panic context; `prod` keeps trap checks but hides source context. |
| `--runtime-checks off\|traps\|panic` | Override the profile default. `off` emits no runtime checks, `traps` emits silent `llvm.trap` checks, and `panic` embeds the SemanticScript panic message before trapping. |
| `--build-file PATH` | Merge build-time declarations (project metadata, icon registry, build switches) from this `.sem` / `.sscript` file into the main Program before codegen. Conflicting redeclarations are rejected. Unused by `build.sem` entry points that use `importModule` directly. |
| `--std-path PATH` | Add an explicit standard-library root. May be repeated. Accepts a `std` root containing `module.sem`, a `SemanticScript` root containing `std/`, or a repo root containing `SemanticScript/std`. |
| `--keep-resources` | Retain the intermediate Windows resource files (`.rc` / `.res` / `.ico`) next to the executable for debugging. Default behavior writes them to a tempdir and deletes after linking — the bytes survive only inside the `.exe`'s PE resource section. Overrides `keepResources PROJECT no` in the build tape. |
| `--resource-dir PATH` | Explicit directory for intermediate resource files. Implies `--keep-resources`. Path resolves relative to the source file's directory unless absolute. Overrides `resourcesDir PROJECT "path"` in the build tape. |
| `--quiet` | Suppress success messages. |

Set `SEMSC_CLANG` to override the clang executable used by `--emit-exe`.
Set `SEMANTICSCRIPT_STD_PATH` or `SEMSC_STD_PATH` to one or more std roots
separated by the platform path separator when the standard library is installed
outside the compiler bundle. Set `SEMSC_TRACEBACK=1` to print Python
tracebacks for parse/codegen failures.

## Strictness and Safe Defaults

The current compiler has three strictness layers:

- Always-on compiler checks. These are part of parsing or codegen and do not
  require `--lint`: build-tape schema validation, unsupported hard runtime
  verbs refusing codegen, exact math operand widths, `return void` only on
  Void/Void outputs, and routed webserver handler ABI validation.
- Source-level `languageMode strictExecutable`. This opt-in row closes the
  executable grammar from that point in the resolved source stream: unknown
  lowercase top-level and operation-body verbs become parse errors without
  requiring `--lint`. Use `languageMode refinedSyntax` for research/metadata
  files that intentionally rely on permissive lowercase rows. The two modes are
  mutually exclusive.
- The `--strict` flag. This runs the compiler's built-in lint pass and promotes
  its diagnostics to fatal exit code `2`. It also activates the current
  strict fallible-call disposition checks. Result-shaped targets such as
  `sqlite.prepareStatement` must use the checked pattern (`run`,
  `bind ok` or `ignore ok`, `bind error`, and `branch error`) until
  a compact checked-run syntax exists. Explicit-disposition targets such as heap
  allocation and native HTTP response writers are still tracked as hardening
  work unless the local compiler tests prove otherwise.

The source-level strict row is:

```semanticscript
languageMode strictExecutable
```

Strictness is source-stream scoped, not package-version scoped. Imported modules
should declare their own `languageMode` when they need a stable strict or refined
parse contract; `languageVersion PROJECT "1.0"` does not imply strict mode.

Compact checked-run rows, owned binding rows, and `requireNonNull` remain
research syntax only. Do not document them as current syntax until
parser/compiler tests exist for them.

Use these commands when checking whether a rule is compiler-enforced or still a
linter migration rule:

```powershell
python SemanticScript\compiler\semsc.py PATH\to\file.sem --parse-only --quiet
python SemanticScript\compiler\semsc.py PATH\to\file.sem --parse-only --strict --quiet
python SemanticScript\linter\semlint.py PATH\to\file.sem --summary
```

If the first command fails, the behavior is compiler-enforced. If only
`--strict` fails, the behavior is compiler-owned strict lint. If only
`semlint.py` fails, the behavior is still standalone-linter guidance. Current
compiler strict-lint diagnostics include invalid route methods (`SS3601`),
route-bound input shape (`SS3609`), middleware output type (`SS3610`), response
forwarding declarations (`SS3615`/`SS3607`), nullable HTTP body flow (`SS3603`),
and unchecked Result-shaped fallible calls. Current standalone hardening
diagnostics include explicit Void returns (`SS3612`), heap allocation
disposition (`SS3305`), SQLite cleanup (`SS3905`/`SS3906`), row-count mutation
guards (`SS3207`), GUI selection/list mutation boundaries (`SS3206`), and
cursor-based string accumulation (`SS3203`/`SS3205`).

For example, both of these allow an app outside the repository to import
`standard.*` modules:

```powershell
python C:\tools\SemanticScript\compiler\semsc.py C:\apps\demo\main.sem --run
python C:\tools\SemanticScript\compiler\semsc.py C:\apps\demo\main.sem --std-path C:\tools\SemanticScript\std
```

Generated `.exe`, `.ll`, linker resource files, and temporary link inputs live
under the managed build directory by default. A basename such as
`--emit-exe taskforge_tui.exe` also resolves into that directory; pass a path with a
directory component to opt into a different output file location.

Use `--build-root` when the build folder should live somewhere else but still
be a managed folder:

```powershell
python compiler/semsc.py ..\apps\taskforge-tui\build.sem --emit-exe --build-root ..\artifacts
# writes into apps/artifacts/build/

python compiler/semsc.py ..\apps\taskforge-tui\build.sem --emit-exe --build-root ..\artifacts --build-folder-name semantic-build
# writes into apps/artifacts/semantic-build/
```

Use `--build-dir` only when you want to name the exact artifact directory:

```powershell
python compiler/semsc.py ..\apps\taskforge-tui\build.sem --emit-exe --build-dir C:\sem-artifacts\todo-dev
```

The repository ignores `build/` folders, so app-local artifacts such as
`apps/taskforge-tui/build/taskforge_tui.exe` stay out of source control.

`build.sem` can carry the same artifact and LLVM defaults so project builds are
repeatable without TOML/YAML sidecars:

| Build tape row | CLI equivalent |
|---|---|
| `buildDir PROJECT "PATH"` | `--build-dir PATH` |
| `buildRoot PROJECT "PATH"` | `--build-root PATH` |
| `buildFolderName PROJECT NAME` | `--build-folder-name NAME` |
| `optLevel PROJECT 0\|1\|2\|3` | `--opt-level N` |
| `persistLlvmIr PROJECT auto\|yes\|no` | `--persist-llvm-ir auto\|yes\|no` |
| `emitLlvmIr PROJECT yes` | `--emit-ir` |
| `llvmIrOutput PROJECT "PATH"` | `--emit-ir PATH` |
| `emitOptimizedLlvmIr PROJECT yes` | `--emit-optimized-ir <default>.opt.ll --run` |
| `optimizedLlvmIrOutput PROJECT "PATH"` | `--emit-optimized-ir PATH --run` |
| `cpuBaseline PROJECT VALUE` | `--cpu-baseline VALUE` |
| `cpuTune PROJECT VALUE` | `--cpu-tune VALUE` |
| `cpuFeature PROJECT FEATURE on\|off` | `--cpu-feature FEATURE=on\|off` |
| `cpuFeatureCheck PROJECT auto\|off\|warn\|require` | `--cpu-feature-check auto\|off\|warn\|require` |
| `guiBackend PROJECT win32\|winui3` | No CLI flag; native GUI backend selector. `win32` is active/default, `winui3` is recognized but currently rejected with a toolchain diagnostic. |

CLI flags win over build-tape defaults for one-off invocations.

## Build-Time Resources

On Windows, the compiler bakes project metadata and icon assets into the
executable's PE resource section via `llvm-rc`. Source-level verbs
(documented in `SYNTAX.md`) declare the resources:

- Project metadata: `version`, `publisher`, `description`, `copyright`,
  `productName`, `internalName`, `originalFilename`, `trademark`,
  `comments`, plus arbitrary `metadata "key" "value"` pairs.
- Icon registry: `iconRoleDefinition`, `icon`, `iconRole`, `iconPurpose`,
  and one `iconImage` plus its property rows (`iconImagePath`,
  `iconImageFormat`, `iconImageWidth`, `iconImageHeight`, `iconImageScale`,
  `iconImageDepth`, `iconImagePlatform`, `iconImagePurpose`,
  `iconImageGroup`) per registered image.

At `--emit-exe` time, the compiler generates a transient `.rc` plus an
auto-packed multi-size `.ico`, hands them to `llvm-rc` (probed on PATH and
under `C:\Program Files\LLVM\bin\`; honors `SEMSC_WINRC`), and the
resulting `.res` is linked into the PE alongside the LLVM IR object.

**Default behavior is residue-free:** the intermediate `.rc`, `.res`, and
`.ico` live in a system tempdir and are deleted after linking. The
resource bytes survive only inside `taskforge_tui.exe`. After a clean build the
output directory contains only the executable (and `.ll` if IR
persistence is on):

```text
build/
  taskforge_tui.exe
  todo.ll
```

To inspect what got embedded, opt into keeping the intermediates:

| Source of truth | How to enable | Where files land |
|---|---|---|
| build tape | `keepResources PROJECT yes` in `build.sem` | `<build_dir>/resources/` |
| build tape | `resourcesDir PROJECT "path"` in `build.sem` | `path/` (relative to source dir, or absolute) |
| CLI flag | `--keep-resources` | `<build_dir>/resources/` |
| CLI flag | `--resource-dir PATH` | `PATH` |

Precedence: CLI flags win over `build.sem` declarations. Within each
source, an explicit path beats a boolean keep flag.

The icon group with `iconRole applicationPrimary` is the one that lowers
to the Windows VERSIONINFO ICON resource. Images with
`iconImagePlatform any` or `windows` are packed; macOS (`macos`) and
Linux images are parsed and indexed for future emitters but not yet
embedded.

## 1.0 Support Matrix

| Area | 1.0 status | Supported in 1.0 | Not a 1.0 guarantee |
|---|---|---|---|
| Python reference compiler | Supported | `SemanticScript/compiler/semsc.py` is the release compiler. It accepts `.sscript` and `.sem`, resolves `importModule`, emits LLVM IR, JIT-runs `entry console`, and can link native executables through clang. | It is not a general web server host, and the repository no longer includes a maintained SemanticScript-written compiler path. |
| VS Code extension | Supported editor tooling | `vscode-semanticscript/` registers `.sscript` and `.sem`, provides highlighting, hovers, semantic roles, and optional `semlint` / `semlint` diagnostics. | Highlighted or hovered syntax is not automatically executable compiler support. The compiler and `SYNTAX.md` decide runtime support. |
| Refined syntax | Partial, inspectable | The parser accepts many refined declarative lines for AST, linter, and editor inspection. Pure metadata is preserved or skipped safely. Some concurrency and dataflow forms lower to documented synchronous fallbacks. | Refined syntax is not uniformly runtime-complete. Use `--parse-only` for forms whose backend is intentionally absent. |
| Web / HTTP runtime | Preview, release-tested | Routed `target webServer` programs emit a native HTTP/1.1 listener with exact method/path dispatch and `:name` path-parameter matching. Handlers use `input request HttpRequest`, `input response HttpResponse`, and `output Int32`. The native adapter supports request method/path/path-param/header/query/cookie/body text/body bytes reads, bounded multipart part reads, response text/bytes/SSE-event/header/file writes, one path-scoped middleware callback, blocking SSE primitives including id-bearing event frames, and `standard.http.serverIsShuttingDown` for handler-visible drain state. | HTTP/2/H2O, route timeout enforcement, structured body decoders, async long-lived fanout, request cancellation tokens, method-scoped middleware, and persistent server state are not 1.0 guarantees. Unrouted webserver files still compile as library/stub programs. |
| Outbound `standard.net` client | Experimental prototype | `import net standard.net`, role types, `HttpGetRequest`, `HttpTextResponse`, `networkHttpClient`, and `net.fetchText` / `net.fetchBytes` call tapes are accepted. Canonical `net.fetchText` source passes a request record and receives a response record, while lowering still targets the native HTTP client ABI. The runtime link registry pulls in `native_http_client` plus `native_async` sources when these targets are used. Real network behavior requires building the optional libcurl/libuv runtime path. | The prototype is not a 1.0 guarantee. Continuation-frame `await` lowering, production async handler integration, and libcurl `multi_socket` support remain future work. |
| Windows GUI runtime | Preview / partial | The committed compiler-owned surface is `target windowsGui`, `targetRuntime PROJECT windowsGui`, optional `guiBackend PROJECT win32\|winui3`, normal `entry console main`, explicit `standard.gui` `gui.*` calls, native runtime linking, and handler ABI preservation for `GuiSession` / `GuiEvent`. The active/default executable backend is the classic Win32 adapter in `native_win32_gui`; `guiBackend winui3` is recognized but rejected until the Windows App SDK backend is buildable. | `standard.gui` owns the GUI vocabulary, declaration contracts, capabilities, and validation semantics. There is no `entry windowsGui` row, and WinUI must not be implemented as a C# / XAML app sidecar. WinUI 3 is not link-ready until Windows App SDK / C++/WinRT build integration lands. |
| Partial syntax rows | Explicitly partial | Rows marked partial in `SYNTAX.md` may parse, lint, lower synchronously, or emit structural stubs exactly as documented there. | A partial row must not be treated as full application-runtime support. Unsupported runtime semantics should fail rather than silently disappear. |
| Runtime and diagnostics flags | Supported compiler interface | `--build-profile dev\|prod`, `--runtime-checks off\|traps\|panic`, `--persist-llvm-ir auto\|yes\|no`, `--diagnostics-format agent\|json\|raw`, and `--opt-level 0..3` are the 1.0 flag surface. | These flags do not change language support. `prod` hides panic source context; `off` removes runtime checks and should be chosen deliberately. |

Native runtime ownership: `semsc.py` collects executable adapter sources through
`_NATIVE_RUNTIME_LINK_REGISTRY`. Each registry row must name the owning stdlib
module or compiler runtime surface. Reserved parse-only rows belong in docs and
tests, not in link inputs, until a branch also lands lowering and runtime ABI
coverage.

Compiler-owned call-target boundary:

| target family | owning layer | compiler responsibility |
| --- | --- | --- |
| `c.*` | temporary backend interop / libc registry | Validate signatures and lower ABI calls while stdlib replacements mature. No app policy belongs here. |
| `console.*` | compiler runtime surface | Lower process stdout/stderr helpers and keep effects explicit. |
| `math.*` / `pointer.*` | compiler primitive operations | Emit arithmetic, conversion, and pointer IR only. Domain rules should call these from `.sem` bodies. |
| `html.hydrate.*` / `jsonBody` | compiler syntax island plus `standard.html` / `standard.json` contracts | Generate structural glue and enforce source syntax; escaping/parsing belongs to the HTML/JSON helpers. |
| `http.*` | `standard.http` plus native HTTP runtime | Lower compiler-owned request/response ABI calls and route dispatch; stdlib-owned SSE and shutdown helpers lower through generic native `runtimeBinding`. App response wrappers must declare `responseBodyForwarder`. |
| `json.*` | `standard.json` plus native JSON runtime | Generate record field walking only; string escaping, primitive formatting, strict parsing, capacity, and status mapping live in `native_json`. |
| `sql body` / `sqlite.*` | `standard.sqlite` plus native SQLite runtime | Bind `SqlText` syntax islands to constants, enforce no interpolation, and lower adapter calls/resource lifetimes. Schemas, migrations, and query policy stay in `.sem` source. |
| `bcrypt.*` | `standard.bcrypt` plus native bcrypt runtime | Lower hashing/random/base64 adapter calls and link vendored sources only when used. |
| `gui.*` | `standard.gui` plus native GUI runtime | Preserve GUI handler ABI and link platform runtime; UI vocabulary and validation stay in the std module. |
| `net.fetch*` | `standard.net` plus `native_http_client` / `native_async` | Experimental prototype lowering and link selection. Request/response records, retry, caching, auth, and scheduling policy stay in `.sem` source and stdlib contracts; backend handles stay out of source. |

## Parse Pipeline

1. Read source as UTF-8.
2. Resolve `importModule` lines and inline imported files. For build tapes,
   registered modules are resolved before legacy filesystem fallbacks.
3. Tokenize line by line.
4. Build the `Program` object and current-operation body tapes.
5. Load external literals from `literalSource` metadata.
6. Optionally run compiler lint.
7. Stop for `--parse-only`, otherwise emit LLVM.

## Import Resolution

`importModule ALIAS DOTTED.PATH` and the compatibility form
`importModule DOTTED.PATH [as ALIAS]` are resolved before parsing. If the root
source declares modules with `registerModule PROJECT MODULE_PATH "PATH"`, the
compiler resolves those registered module paths first. A registered path may
point at a source file or a folder with `main.sem`, `index.sem`, the leaf module
file, or exactly one non-test `.sem` / `.sscript`.

If no project-registered module matches, canonical standard-library module
paths resolve through the std search path. `standard` maps to `std/module.sem`
and `standard.<module>` maps to `std/<module>/main.sem`. Search order is:
explicit `--std-path` roots, `SEMANTICSCRIPT_STD_PATH` / `SEMSC_STD_PATH`,
vendored `std/` folders found while walking up from the source file, `std/`
under the current working directory, then the compiler-bundled `../std`.
After that, the legacy resolver searches source-relative paths, std roots, and
the project root. Imports are inlined with cycle detection, and the import row
is preserved so alias and
singular-import metadata remain visible after inlining.

Project aliases are namespace boundaries for exported provider operations,
types, errors, capabilities, and constants. Qualified calls such as
`provider.publicOperation` lower to the inlined provider operation only when
the provider exports that operation. Singular import rows such as
`importOperation localName provider publicOperation` bind an exported provider
symbol to a local facade name. New project code should keep `registerModule`
rows in `build.sem`; module files should keep their own `module`,
`importModule`, singular import, and `export*` rows.

## Entry and Library Modes

`entry console OPERATION` emits `int main()` from that operation.

Without an `entry`, the compiler usually:

- declares every operation as a callable function;
- compiles every operation body;
- emits a stub `main` returning zero.

Routed `target webServer` programs are the exception: `webServer` / `route`
metadata selects the native HTTP entry generator instead of the stub.

`target windowsGui` is the reserved second no-entry exception. Its compiler
responsibility should stay small: select/link the native Windows GUI runtime,
preserve `GuiSession` and `GuiEvent` handler ABI parameters, and consume a
normalized application/main-window descriptor produced from `standard.gui`
metadata. The GUI row vocabulary and most validation belong in `standard.gui`
and lint/tooling, not in a large compiler-owned grammar. The form
`entry windowsGui OPERATION` is rejected; `targetRuntime PROJECT windowsGui`
build tapes should use `entry console main` and run the GUI through
`gui.applicationRun`.

### Windows GUI Smoke Test

Run the committed GUI smoke app from a Windows shell with LLVM/clang available:

```powershell
python SemanticScript\tools\sem.py check apps\desktop-window-smoke --quiet
python SemanticScript\tools\sem.py build apps\desktop-window-smoke --quiet
apps\desktop-window-smoke\build\desktop_window_smoke.exe
```

Expected behavior: a top-level window titled `Desktop Window Smoke` appears. Closing the
window exits the process with status `0`. The source should keep using ordinary
`operation` / `call` / `argument` / `run` rows with `importModule gui standard.gui`;
do not add `entry windowsGui`.

The stub mode supports stdlib files and refined syntax showcases that need
parse/codegen inspection without a runtime host.

## User Operation ABI

For each non-entry user operation:

- inputs become function parameters in source order;
- opaque inputs are dropped from the LLVM ABI;
- `output OP Result OK ERR` returns `OK`;
- `output OP TYPE` returns `TYPE`;
- missing, malformed, or unknown output contracts are compiler/lint errors;
- `Void` success currently uses an `i32` zero sentinel where LLVM needs a
  concrete return slot.

Opaque input names:

```text
console environment process httpRequest databaseClient clock
```

GUI handlers are a target-specific ABI exception. `GuiSession` and `GuiEvent`
are preserved for handlers wired by `standard.gui` metadata, while ordinary
opaque dependency inputs outside HTTP and GUI ABIs keep the usual dropped-token
behavior.

## Soft Metadata vs Runtime Features

The compiler accepts many refined verbs so tools can inspect current and future
syntax. The important distinction:

- Soft metadata lines can be safely ignored by codegen because they only
  annotate behavior.
- Runtime-feature lines must either lower correctly or use an explicit
  synchronous fallback.

Examples of synchronous fallbacks:

```text
start/await              start executes immediately; await is no-op
taskGroup                startInGroup executes immediately
channel                  single operation-local slot
lock/unlock              no-op in single-thread runtime
workerPool               direct dispatch on same thread
interval                 no timer runtime; no-op
```

## Codegen Errors

Parse errors exit with code `2`. Codegen errors and unsupported runtime backend
errors exit with code `3`. Native executable linking errors exit with code `4`.

Use `--parse-only` when authoring metadata-heavy syntax whose runtime backend is
not expected to exist yet.

## Tests

Primary compiler test commands:

```powershell
python tests/compare.py
python tests/test_compiler.py
python tests/test_stdlib.py
```

Feature programs live in:

```text
SemanticScript/sem/feature_tests/
```

When adding or changing lowering behavior, add the smallest feature test that
proves the exact line schema and runtime result.
