# AgentScript — reference implementation

A minimal but real implementation of the AgentScript language from the spec at
`../AgentScript.md`. The compiler emits LLVM IR via `llvmlite` and JIT-executes
through MCJIT. Programs in `as/` match the behavior of their `js/` peers
byte-for-byte (validated by `tests/compare.py`).

```
<project root>/
├── javascript/             canonical Node.js benchmark oracles (root level)
│   ├── hello.js
│   ├── countdown.js
│   ├── fizzbuzz.js
│   ├── factorial.js
│   ├── sum_of_squares.js
│   └── … (many more)
├── AgentScript.md          the language spec
└── AgentScript/
    ├── AST.md              full syntax-tree design
    ├── README.md           this file
    ├── compiler/
    │   └── ascc.py         tokenizer + parser + LLVM codegen + JIT runner + linter
    ├── as/                 AgentScript programs
    │   ├── hello.as
    │   ├── countdown.as
    │   ├── fizzbuzz.as
    │   ├── factorial.as
    │   ├── sum_of_squares.as
    │   └── syntax_sample_web_server.as  (parse-only: records, route, taskGroup, codec, ...)
    └── tests/
        └── compare.py      runs both sides and diffs stdout + exit code
```

Parity tests use `<project root>/javascript/<name>.js` as the oracle for
each `AgentScript/as/<name>.as`.

## Run one program

```
python compiler/ascc.py as/fizzbuzz.as --run
```

To inspect the emitted LLVM IR:

```
python compiler/ascc.py as/fizzbuzz.as --emit-ir fizzbuzz.ll
```

## Run the parity suite

```
python tests/compare.py
```

For each program it shells out to `node <project-root>/javascript/<name>.js`
and to `python compiler/ascc.py as/<name>.as --run`, then byte-compares the
two stdouts and exit codes.

## Run the standalone linter

```
python linter/aslint.py as/fizzbuzz.as --summary
python linter/aslint.py as --strict
python linter/aslint.py as/fizzbuzz.as --format json
```

The standalone linter lives at `linter/aslint.py` and does not invoke LLVM
codegen. It checks source-level AgentScript laws such as explicit failure
flow, call lifecycle consistency, branch target validity, effect declarations,
role suffixes, duplicate domain literals, group balance, and abstraction
purpose.

## What's implemented vs. the full spec

The spec is large. This implementation covers the subset listed in `AST.md`
§3–§6 — enough to compile and run console programs that exercise:

- top-level project / target / runtime / entry headers
- full operation headers (input, output, effect, memory, async, purpose,
  invariant, warning)
- constants and mutable variables (`const`, `var`, `set`)
- named call objects with `arg` / `run` / `bindOk` / `bindError` / `bind`
- branching via `branchIf`, `branchIfError`, `branch`
- labels as first-class basic blocks
- explicit failure-flow `returnError` / `returnOk` / `returnValue`
- a `math.*` namespace for arithmetic and comparison
- a `console.*` namespace for stdout writes (`writeLine`, `writeInteger`)

Out of scope here (but designed for in `AST.md`): async (`start`/`await` are
parsed but lowered to synchronous `run`), task groups, web servers, channels,
mutexes, defer, dependency contracts, retry policies, time types. Each of
those slots into the existing AST without restructuring it.
