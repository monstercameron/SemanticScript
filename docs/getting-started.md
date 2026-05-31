# Getting Started with SemanticScript

SemanticScript is a row-based language whose programs are flat triples
(`<subject> <predicate> <payload>`). The toolchain lexes, parses, lints, and
lowers programs to LLVM IR, then JIT-runs them or builds native executables.

> The root [`README.md`](../README.md) is the full language specification. This
> page is the practical "install it and run something" guide.

## Prerequisites

- **Python 3.12** (a native ARM64 build on ARM64 hosts — an x64-emulated Python
  cannot reach the JIT target).
- The Python dependencies in [`requirements.txt`](../requirements.txt) (chiefly
  `llvmlite`, which bundles LLVM for the JIT).
- A **C compiler — `clang` (LLVM) or `zig cc`** — on `PATH`. This is needed the
  first time a program references a native runtime (sqlite/http/json/bcrypt/…)
  and for `build` (native executables). Pure console/compute programs JIT-run
  without it. Override discovery with `SEMANTICSCRIPT_CC`.

## Install from source

```sh
git clone https://github.com/monstercameron/SemanticScript.git
cd SemanticScript
python -m pip install -r requirements.txt
```

The compiler entry point is `semanticscript/compiler/semanticscript.py`. For
brevity below, assume a shell alias:

```sh
# bash / zsh
alias semanticscript='python semanticscript/compiler/semanticscript.py'
# PowerShell
function semanticscript { python semanticscript/compiler/semanticscript.py @args }
```

A prebuilt single-file binary (`semanticscript` / `semanticscript.exe`) is
attached to GitHub releases, or build one yourself with
`python semanticscript/packaging/package.py` (requires `pyinstaller`).

## Your first program

Save this as `hello.sem`:

```
Hello is project
Hello module helloModule
Hello target console
Hello entry main

helloModule is module
helloModule path hello
helloModule exports main

ExitCode is alias
ExitCode for Int32

stdoutWriter is capability
stdoutWriter grants write console.stdout
stdoutWriter purpose "Authority to write one line to standard output"

main is operation
main purpose "Print a greeting and exit cleanly"
main invariant "Always returns ExitCode 0"
main out ExitCode
main effect write console.stdout
main uses stdoutWriter
main do greetCall

greetCall is call
greetCall in main
greetCall invokes console.writeLine
greetCall arg text String "Hello from SemanticScript!"
```

Run it:

```sh
semanticscript run hello.sem
# Hello from SemanticScript!
```

Every line is `<subject> <predicate> <payload>`. The `project` declares the
target and entry; `main` is an `operation` whose effect (`write console.stdout`)
must be covered by a `uses`-ed `capability`; the `call` invokes the
`console.writeLine` primitive.

## The toolchain

| Command | What it does |
|---|---|
| `semanticscript run <path>` | JIT-compile and execute (a file or a project dir). |
| `semanticscript check --json <path>` | Structured diagnostics (`sem.check.v1`). |
| `semanticscript lint <path>` | Human-readable lint diagnostics. |
| `semanticscript fmt <path>` | Format source (canonical row layout). |
| `semanticscript build <path> -o out` | Build a native executable. |
| `semanticscript version` | Print the source-compatibility contract version. |

Run `semanticscript --help` for the full subcommand list.

## Multi-file projects

A project is a directory with a `build.sem` (the project/module manifest) and
sources under `src/`. Point the toolchain at the directory:

```sh
semanticscript run path/to/project
semanticscript build path/to/project -o path/to/project/build/app
```

See `apps/` for worked examples (a TUI, an HTTP client, and a full
sqlite+bcrypt+json web API).

## Editor support

The [`vscode-semanticscript/`](../vscode-semanticscript) extension provides
syntax highlighting, snippets, an icon theme, and lint/compile commands wired to
this compiler. Package it with `npm install && npx vsce package` and install the
resulting `.vsix`, or open the folder in VS Code and press F5 to launch an
Extension Development Host.

## Where to go next

- [`README.md`](../README.md) — the language specification.
- [`CHANGELOG.md`](../CHANGELOG.md) — what's new and the known pre-release gaps.
- [`docs/todos.md`](todos.md) — the roadmap toward 1.0.
