# SemanticScript

[![CI](https://github.com/monstercameron/SemanticScript/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/monstercameron/SemanticScript/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

SemanticScript is an explicit, agent-first programming language. Programs are
written and edited by AI agents, so the language optimizes for being exact and
checkable, not short:

- **Nothing is implied.** Every fact that changes what a program means is
  written as a row. A missing row is an error, not a default.
- **Every stated fact is checked.** If a row states a type, an effect, an owner,
  a loop bound, or a claim, the compiler verifies it.
- **One shape, one spelling.** Every line is `<subject> <predicate> <payload>`,
  each predicate has exactly one shape, and each idea has one spelling.

The design, every rule, and the reasons behind them are in
[docs/language-refinement.md](docs/language-refinement.md). The exact shape of
every row is in [docs/refined-grammar.md](docs/refined-grammar.md), generated
from the compiler.

The language is pre-release and changes without backwards compatibility.

## Hello, world

`hello/build.sem`:

```
hello is project
hello purpose "Print one greeting line and exit"
hello target console
hello module hello
hello entry hello.main
```

`hello/hello.sem` (abridged; the full file is
[docs/refined-examples/hello/hello.sem](docs/refined-examples/hello/hello.sem)):

```
main is operation
main purpose "Print a greeting and exit with code zero"
main invariant printsGreeting "Writes the greeting line and exits with code zero"
main typeParam none
main input none
main output ExitCode
main outputOwner none
main raises none
main effect write console.stdout
main uses stdoutWriter
main memory heap false
main async false
main maxRecursion none
main label begin loopKind none
main label begin within none
main label succeeded loopKind none
main label succeeded within none
main label failed loopKind none
main label failed within none
main let greeting immutable String "Hello, world!"
main let okCode immutable ExitCode 0
main let failCode immutable ExitCode 1
main at begin do printGreeting
main at begin branch ifError printGreeting goto failed else goto succeeded
main at succeeded return ok okCode
main at failed return ok failCode

printGreeting is call
printGreeting in main
printGreeting invokes console.writeLine
printGreeting arg text String greeting lend
printGreeting out none
printGreeting ownedBy none
printGreeting cleanedBy none
printGreeting borrows none
printGreeting catch printError console.WriteError
```

## Use it

Requires Python 3.11 or newer and `llvmlite`:

```bash
python -m pip install -r requirements.txt
```

```bash
python semanticscript/compiler/refined check docs/refined-examples/hello
```

```bash
python semanticscript/compiler/refined run docs/refined-examples/hello
```

```bash
python semanticscript/compiler/refined test docs/refined-examples/selfhost
```

| Command | What it does |
| --- | --- |
| `check PATH [--json]` | Check a module file or a project (`build.sem` or its directory) against every rule |
| `run PATH [--json]` | Compile a console project to LLVM and run it |
| `test PATH [--json]` | Run every test in a project, each in its own process |
| `emit-ir PATH [--test MODULE.TEST]` | Print the generated LLVM IR |
| `stale PATH --base REF` | Flag entities whose code changed but whose context rows did not |
| `grammar [--textmate] [--output FILE]` | Generate the row-shape reference or the editor grammar |

Diagnostics have stable codes (`R101`...`R901`); each code's summary is in
`semanticscript/compiler/refined/diagnostics.py`.

## What runs today

The checker enforces the whole language as designed, and the backend compiles
and runs all of it: integers, floats, strings, records, enums, tables, loops
and recursion with enforced bounds, errors, regions, lists, maps, sets,
generic operations, cleanups, parallel tasks, task groups and channels,
and files and directories, sockets, HTTP, processes, the environment, and the clock. Every
worked example runs, including an HTTP server, and every operation of every
program in the repository compiles; `R901` is now only a guard against a library
target the backend has not implemented.
Every item still open is listed at the end of
[docs/test-suite.md](docs/test-suite.md).

## Commands

`refined` is `python semanticscript/compiler/refined`.

| Command | What it does |
| --- | --- |
| `refined check PATH` | Check a project or a module file |
| `refined run PATH [-- ARGS]` | Compile and run the entry (`--trace`, `--coverage`, `--profile`, `--debug --break M.OP`) |
| `refined test PATH` | Run every test, each in its own process |
| `refined bench PATH --runs N` | Time repeated runs |
| `refined build PATH --output F` | Object, assembly, or WebAssembly (`--kind`), for any target (`--target`) |
| `refined fmt PATH [--check]` | Format sources |
| `refined repl` | Type rows, then check and run them |
| `refined lsp` | Language server on stdin and stdout |

## Repository map

```text
semanticscript/compiler/refined/   the compiler: lexer, shape table, checker, LLVM backend, runtime
docs/language-refinement.md        the language design, decisions, and plan
docs/refined-grammar.md            every row shape (generated)
docs/refined-examples/             worked example projects (hello, sum, factorial, selfhost, server)
tests/test_refined.py              rule tests on the worked examples
tests/suite/, tests/test_suite.py  the language test suite: program cases, negative mutations, stress, fuzz
docs/test-suite.md                 coverage map of the testing checklist (generated)
vscode-semanticscript/             VS Code extension (generated grammar, check-on-save diagnostics)
```

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
