# AgentScript reference implementation

AgentScript 1.0.0 is a minimal but real implementation of the language spec
in `../AgentScript.md`. The compiler emits LLVM IR through `llvmlite`, can
JIT-run with MCJIT, and can link native executables through `clang`.

The 28 oracle-backed programs in `as/` match their JavaScript peers
byte-for-byte via `tests/compare.py`. The AS-written `bootstrap_general.as`
compiler currently passes 23 of those oracle programs via
`tests/as_compiler_parity.py`.

## Layout

```text
<project root>/
  javascript/                 Node.js oracle programs
  python/                     Python comparison programs
  AgentScript.md              language spec
  CHANGELOG.md                date-grouped repository changelog
  AgentScript/
    AST.md                    implemented syntax-tree/codegen surface
    README.md                 this file
    CHANGELOG.md              toolchain release notes
    compiler/
      ascc.py                 tokenizer, parser, LLVM codegen, runner
      libc_registry.py        C standard-library signature registry
    linter/
      aslint.py               standalone source linter
    bootstrap/
      bootstrap.as            stage 1 fixed hello-world IR emitter
      bootstrap2.as           stage 2 first quoted-string parser
      bootstrap3.as           stage 3 ExitCode parser
      bootstrap4.as           stage 4 greeting + ExitCode compiler
      bootstrap5.as           stage 5 countdown-loop IR emitter
      bootstrap6.as           stage 6 input-scaled multi-string compiler
      bootstrap_general.as    current AS-written compiler for parity tests
      run_bootstrap_chain.py  end-to-end bootstrap verification
    as/                       AgentScript programs and smoke files
    stdlib_as/                standalone AS stdlib-shaped modules
    as_python/                reserved for future Python parity mirrors
    tests/
      compare.py              Python ascc vs Node parity, 28 programs
      as_compiler_parity.py   bootstrap_general vs Node parity, 23 targets
      test_compiler.py        compiler/bootstrap smoke checks
      test_stdlib.py          stdlib_as self-test runner
```

## Quick Start

Run from `AgentScript/` unless noted otherwise.

```powershell
python compiler/ascc.py --version
python compiler/ascc.py as/fizzbuzz.as --run
python compiler/ascc.py as/fizzbuzz.as --emit-ir fizzbuzz.ll
python compiler/ascc.py as/fizzbuzz.as --emit-exe fizzbuzz.exe
python linter/aslint.py as/fizzbuzz.as --summary
python linter/aslint.py as --strict
```

## Tests

```powershell
# 28 oracle-backed as/<name>.as files match javascript/<name>.js
python tests/compare.py

# AS-written compiler parity: 23 current bootstrap_general targets
python tests/as_compiler_parity.py

# compiler-internal checks
python tests/test_compiler.py

# stdlib_as self-tests
python tests/test_stdlib.py

# full self-hosting bootstrap chain: 6 stages, 24 sub-stages
python bootstrap/run_bootstrap_chain.py
```

## Implemented Surface

The reference compiler covers the subset documented in `AST.md`: enough to
compile console programs, C-stdlib bridge calls, pointer-buffer programs,
stdlib-shaped helper modules, and the current bootstrap compilers.

Implemented runtime/codegen pieces include:

- top-level `project`, `target`, `runtime`, and `entry` headers;
- operation contracts: `input`, `output`, `effect`, `memory`, `async`,
  `purpose`, `invariant`, and related metadata;
- constants, variables, mutation, labels, branches, and returns;
- named call objects with `arg`, `run`, `bind`, `bindOk`, `bindError`,
  `ignoreOk`, and `branchIfError`;
- same-file user-defined operation calls with typed returns derived from each
  operation's `output` line;
- integer and floating-point math primitives, including `math.intToFloat` and
  `math.floatToInt`;
- stdout helpers through `console.writeLine` and `console.writeIntegerLine`;
- direct C calls through `c.<funcName>` using `compiler/libc_registry.py`;
- pointer primitives: `pointer.loadByte`, `pointer.storeByte`,
  `pointer.offset`, `pointer.difference`, and `pointer.isNull`.

Spec verbs with runtime meaning that are not lowered yet are parsed for
inspection but rejected in normal compile mode. See `AST.md` for the exact
reserved-hard list.

## Bootstrap Status

`bootstrap/` demonstrates AgentScript compiling narrower AgentScript subsets.
Every numbered stage is real `.as` source compiled by the trusted Python
reference compiler, then run to emit LLVM IR for another `.as` input.

`bootstrap_general.as` is separate from the numbered chain. It reads a target
program from `AS_INPUT`, emits LLVM IR, and currently handles the 23 oracle
programs whose stdout can be reproduced from source string constants. It is
not yet a full compiler for loops, mutation, computed integer output, stdin, or
real call dispatch.

See `bootstrap/README.md` for the detailed stage matrix and remaining
self-hosting blockers.
