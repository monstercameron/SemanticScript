# AgentScript — reference implementation

> AgentScript 1.0.0 — a minimal but real implementation of the AgentScript
> language from the spec at `../AgentScript.md`. The compiler emits LLVM IR
> via `llvmlite` and either JIT-executes through MCJIT or links to a native
> executable through `clang`. Programs in `as/` match the behavior of their
> `js/` peers byte-for-byte (validated by `tests/compare.py`).

```
<project root>/
├── javascript/             canonical Node.js benchmark oracles
│   ├── hello.js
│   ├── countdown.js
│   ├── fizzbuzz.js
│   ├── factorial.js
│   ├── sum_of_squares.js
│   └── … (28 programs)
├── AgentScript.md          the language spec
└── AgentScript/
    ├── AST.md              full syntax-tree design
    ├── README.md           this file
    ├── CHANGELOG.md        release notes
    ├── compiler/
    │   ├── ascc.py         tokenizer + parser + LLVM codegen + JIT runner
    │   └── libc_registry.py  C-stdlib function signatures
    ├── linter/
    │   └── aslint.py       standalone source-level linter
    ├── bootstrap/
    │   ├── bootstrap.as    stage 1 — emits fixed hello-world IR
    │   ├── bootstrap2.as   stage 2 — extracts first quoted string
    │   ├── bootstrap3.as   stage 3 — parses ExitCode literal
    │   ├── bootstrap4.as   stage 4 — greeting + ExitCode
    │   ├── bootstrap5.as   stage 5 — countdown loop with branches
    │   ├── input*.as       inputs each stage parses
    │   ├── run_bootstrap_chain.py  full end-to-end chain check
    │   └── README.md       bootstrap-chain documentation
    ├── as/                 AgentScript programs
    │   ├── hello.as
    │   ├── countdown.as
    │   ├── fizzbuzz.as
    │   ├── factorial.as
    │   └── …
    └── tests/
        ├── compare.py      parity oracle (Node vs. AS, byte-for-byte)
        └── test_compiler.py  compiler unit tests
```

Parity tests use `<project root>/javascript/<name>.js` as the oracle for
each `AgentScript/as/<name>.as`.

## Quick start

```
# print the version
python compiler/ascc.py --version

# compile and JIT-run a program
python compiler/ascc.py as/fizzbuzz.as --run

# write LLVM IR to disk
python compiler/ascc.py as/fizzbuzz.as --emit-ir fizzbuzz.ll

# ahead-of-time compile to a native exe (requires clang)
python compiler/ascc.py as/fizzbuzz.as --emit-exe fizzbuzz.exe

# lint a single file or a whole directory
python linter/aslint.py as/fizzbuzz.as --summary
python linter/aslint.py as --strict
```

## Run the test suites

```
# parity: every as/<name>.as must match javascript/<name>.js byte-for-byte
python tests/compare.py

# compiler-internal unit tests (tokenizer, parser, codegen, bootstrap IR)
python tests/test_compiler.py

# full self-hosting bootstrap chain (5 stages, 20 sub-stages)
python bootstrap/run_bootstrap_chain.py
```

## CLI

```
ascc 1.0.0

usage: ascc [-h] [--version] [--emit-ir EMIT_IR] [--run] [--lint] [--strict]
            [--parse-only] [--opt-level OPT_LEVEL]
            [--emit-optimized-ir EMIT_OPTIMIZED_IR] [--emit-exe EMIT_EXE]
            [--quiet]
            [source]
```

Exit codes:

| Code | Meaning                                                     |
| ---- | ----------------------------------------------------------- |
| 0    | success (or, with `--run`, the program's own return code)   |
| 2    | parse error or source not readable                          |
| 3    | codegen error (including reserved-hard verbs not yet lowered) |
| 4    | linker error (clang failure when using `--emit-exe`)        |

## What's implemented vs. the full spec

The spec is large. The reference compiler covers the subset listed in
`AST.md` §3–§6 — enough to compile and run console programs that exercise:

- top-level `project` / `target` / `runtime` / `entry` headers
- operation headers (`input`, `output`, `effect`, `memory`, `async`,
  `purpose`, `invariant`, `warning`)
- constants and mutable variables (`const`, `var`, `set`)
- named call objects with `arg` / `run` / `bindOk` / `bindError` / `bind`
- branching via `branchIf`, `branchIfError`, `branch`
- labels as first-class basic blocks
- explicit failure-flow `returnError` / `returnOk` / `returnValue`
- a `math.*` namespace for arithmetic and comparison
- a `console.*` namespace for stdout writes (`writeLine`, `writeIntegerLine`)
- a full C-stdlib bridge (`c.<funcName>`, plus camelCase aliases for
  underscored C symbols)
- pointer primitives (`pointer.loadByte`, `pointer.storeByte`,
  `pointer.offset`, `pointer.difference`, `pointer.isNull`)

See [`CHANGELOG.md`](CHANGELOG.md) for the full feature matrix and the
list of spec verbs that are reserved-hard (parsed but not yet lowered).

## Self-hosting bootstrap chain

`bootstrap/` contains an iterative bootstrap demonstrating that AgentScript
can compile AgentScript. Each stage's compiler is a real `.as` source file;
running them produces LLVM IR for another `.as` source file, which clang
then turns into a native executable.

```
python bootstrap/run_bootstrap_chain.py
```

See [`bootstrap/README.md`](bootstrap/README.md) for the precise AgentScript
subset each stage compiles and the list of features still needed before
the AgentScript compiler can compile its own Python source.
