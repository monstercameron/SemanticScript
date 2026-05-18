# Reference Compiler

The reference compiler is `SemanticScript/compiler/semsc.py`. It parses
line-oriented SemanticScript, resolves imports and external literals, builds an
AST, emits LLVM IR with `llvmlite`, can JIT-run, and can call `clang` for
native executables.

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
```

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
| `--run` | JIT-execute `main` and return its exit code. |
| `--emit-exe [PATH]` | AOT compile with clang. With no path, writes to the managed build directory. |
| `--lint` | Run built-in compiler lint pass. |
| `--strict` | Treat compiler lint diagnostics as fatal. |
| `--parse-only` | Parse, optionally lint, and stop before codegen. |
| `--opt-level N` | LLVM optimization level `0..3`, default `2`. |
| `--build-profile dev\|prod` | Runtime safety profile for compiled output. `dev` is the default and embeds `SSRUN001` panic context; `prod` keeps trap checks but hides source context. |
| `--runtime-checks off\|traps\|panic` | Override the profile default. `off` emits no runtime checks, `traps` emits silent `llvm.trap` checks, and `panic` embeds the SemanticScript panic message before trapping. |
| `--build-file PATH` | Merge build-time declarations (project metadata, icon registry, build switches) from this `.sem` / `.sscript` file into the main Program before codegen. Conflicting redeclarations are rejected. Unused by `build.sem` entry points that use `importModule` directly. |
| `--keep-resources` | Retain the intermediate Windows resource files (`.rc` / `.res` / `.ico`) next to the executable for debugging. Default behavior writes them to a tempdir and deletes after linking — the bytes survive only inside the `.exe`'s PE resource section. Overrides `keepResources PROJECT no` in the build tape. |
| `--resource-dir PATH` | Explicit directory for intermediate resource files. Implies `--keep-resources`. Path resolves relative to the source file's directory unless absolute. Overrides `resourcesDir PROJECT "path"` in the build tape. |
| `--quiet` | Suppress success messages. |

Set `SEMSC_CLANG` to override the clang executable used by `--emit-exe`.
Set `SEMSC_TRACEBACK=1` to print Python tracebacks for parse/codegen failures.

Generated `.exe`, `.ll`, linker resource files, and temporary link inputs live
under the managed build directory by default. A basename such as
`--emit-exe todo.exe` also resolves into that directory; pass a path with a
directory component to opt into a different output file location.

Use `--build-root` when the build folder should live somewhere else but still
be a managed folder:

```powershell
python compiler/semsc.py ..\app\todo\build.sem --emit-exe --build-root ..\artifacts
# writes into app/artifacts/build/

python compiler/semsc.py ..\app\todo\build.sem --emit-exe --build-root ..\artifacts --build-folder-name semantic-build
# writes into app/artifacts/semantic-build/
```

Use `--build-dir` only when you want to name the exact artifact directory:

```powershell
python compiler/semsc.py ..\app\todo\build.sem --emit-exe --build-dir C:\sem-artifacts\todo-dev
```

The repository ignores `build/` folders, so app-local artifacts such as
`app/todo/build/todo.exe` stay out of source control.

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
resource bytes survive only inside `todo.exe`. After a clean build the
output directory contains only the executable (and `.ll` if IR
persistence is on):

```text
build/
  todo.exe
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
| Python reference compiler | Supported | `SemanticScript/compiler/semsc.py` is the release compiler. It accepts `.sscript` and `.sem`, resolves `importModule`, emits LLVM IR, JIT-runs `entry console`, and can link native executables through clang. | It is not a general web server host and it is not replaced by the SemanticScript-written bootstrap compiler. |
| Bootstrap and self-hosting | Preview, release-tested | `bootstrap/run_bootstrap_chain.py` and `tests/sem_compiler_parity.py` are valid release verification commands. The staged SemanticScript-written compilers demonstrate input-dependent IR generation for documented subsets. | Self-hosting is not complete. `bootstrap_general.sscript` is not the 1.0 production compiler and does not compile the whole language. |
| VS Code extension | Supported editor tooling | `vscode-semanticscript/` registers `.sscript` and `.sem`, provides highlighting, hovers, semantic roles, and optional `semlint` / `semlint` diagnostics. | Highlighted or hovered syntax is not automatically executable compiler support. The compiler and `SYNTAX.md` decide runtime support. |
| Refined syntax | Partial, inspectable | The parser accepts many refined declarative lines for AST, linter, and editor inspection. Pure metadata is preserved or skipped safely. Some concurrency and dataflow forms lower to documented synchronous fallbacks. | Refined syntax is not uniformly runtime-complete. Use `--parse-only` for forms whose backend is intentionally absent. |
| Web / HTTP runtime | Preview, release-tested | Routed `target webServer` programs emit a native HTTP/1.1 listener with exact method/path dispatch. Handlers use `input request HttpRequest`, `input response HttpResponse`, and `output CSignedInt32`. The native adapter supports request method/path/header/query/body text/body bytes reads, bounded multipart part reads, response text/bytes/SSE-event/header writes, and one path-scoped middleware callback. | HTTP/2/H2O, path params, route timeout enforcement, static-file serving, graceful shutdown hooks, structured body decoders, long-lived streaming bodies, method-scoped middleware, and persistent state are not 1.0 guarantees. Unrouted webserver files still compile as library/stub programs. |
| Partial syntax rows | Explicitly partial | Rows marked partial in `SYNTAX.md` may parse, lint, lower synchronously, or emit structural stubs exactly as documented there. | A partial row must not be treated as full application-runtime support. Unsupported runtime semantics should fail rather than silently disappear. |
| Runtime and diagnostics flags | Supported compiler interface | `--build-profile dev\|prod`, `--runtime-checks off\|traps\|panic`, `--persist-llvm-ir auto\|yes\|no`, `--diagnostics-format agent\|json\|raw`, and `--opt-level 0..3` are the 1.0 flag surface. | These flags do not change language support. `prod` hides panic source context; `off` removes runtime checks and should be chosen deliberately. |

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

`importModule DOTTED.PATH [as ALIAS]` is resolved before parsing. If the root
source declares modules with `registerModule PROJECT MODULE_PATH "PATH"`, the
compiler resolves those registered module paths first. A registered path may
point at a source file or a folder with `main.sem`, `index.sem`, the leaf module
file, or exactly one non-test `.sem` / `.sscript`.

If no registered module matches, the legacy resolver searches source-relative
paths, `stdlib_sem/`, and the project root. Imports are inlined with cycle
detection.

The alias is recorded for tools; it is not currently a full namespace boundary.
New project code should keep `registerModule` rows in `build.sem`; module files
should keep their own `module`, `importModule`, and `export*` rows.

## Entry and Library Modes

`entry console OPERATION` emits `int main()` from that operation.

Without an `entry`, the compiler usually:

- declares every operation as a callable function;
- compiles every operation body;
- emits a stub `main` returning zero.

Routed `target webServer` programs are the exception: `webServer` / `route`
metadata selects the native HTTP entry generator instead of the stub.

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
python tests/sem_compiler_parity.py
python tests/test_compiler.py
python tests/test_stdlib.py
python bootstrap/run_bootstrap_chain.py
```

Feature programs live in:

```text
SemanticScript/sem/feature_tests/
```

When adding or changing lowering behavior, add the smallest feature test that
proves the exact line schema and runtime result.
