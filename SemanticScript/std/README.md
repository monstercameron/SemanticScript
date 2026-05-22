# SemanticScript standard library (`std/`)

This directory contains the SemanticScript standard library. It is a library
tree, not a buildable project, so it does not own a `build.sem` file.
`module.sem` is the top-level `standard` relay, and each child module owns a
linker/import entry at `std/<module>/main.sem`.

Most helper logic is written in SemanticScript: byte loops, classifiers,
integer math, float helpers, memory walks, table lookups, and small container
algorithms. A few operations intentionally bottom out in host C calls where
there is no useful pure-SemanticScript substitute yet, such as `c.putchar`, `c.malloc`,
`c.free`, `c.clock`, `c.time`, `c.getenv`, `c.exit`, `c.abort`, and
`c.raise`.

## Contents

Each module folder has the same shape: `main.sem` is the module entry and
`main.test.sem` is its companion smoke or unit-style test.

Namespaced standard modules live under matching folders. `html/main.sem` owns
the official `standard.html` import path for first-class HTML template syntax;
`gui/main.sem` owns the official metadata module for declarative Windows GUI
row vocabulary, handler types, handles, closed token sets, runtime target
names, status constants, and `gui.*` capability contracts; `http/main.sem`,
`json/main.sem`, and `sqlite/main.sem` own the official metadata modules for
compiler-owned `http.*`, `json.*`, and `sqlite.*` intrinsic namespaces.
App modules import them with rows such as `importModule html standard.html`,
`importModule gui standard.gui`, `importModule http standard.http`, and
`importModule json standard.json`.
The compiler resolves `standard.<module>` directly to `std/<module>/main.sem`.

`standard.json` currently exports the implemented builder/finder aliases
(`JsonBuilder`, `JsonText`, `JsonFieldName`, `JsonStringValue`,
`JsonScratchBuffer`, `JsonCapacityBytes`) plus the public document CRUD
contracts (`JsonDocument`, `JsonCursor`, `JsonPath`, `JsonValueKind`,
`JsonAccessError`, `JsonEncodeError`, and `JsonDecodeError`). The document
CRUD, `jsonBody`, and typed `json.stringify.<TypeName>` /
`json.parse.<TypeName>` entry points are documented in
`docs/language/json-crud.md`; check `SYNTAX.md` for the current lowering
status before using a surface in executable code.

This library tree intentionally has no `build.sem`. Add standard modules under
`std/<module>/main.sem` and relay them from `std/module.sem`.

For GUI specifically, `standard.gui` is intended to keep the compiler small:
parser, linter, and codegen may mirror the row names and numeric IDs for fast
validation and lowering, but the user-facing vocabulary and semantic contracts
belong in `std/gui/main.sem`.

## Current Status

Active stdlib implementation surface. Low-level `c.*` calls are still accepted
here as bootstrap/runtime implementation details; app-facing code should move
toward SemanticScript API operations as they become available.

## Coverage

The current tree has 35 standard modules plus the top-level `standard` relay.

| file | category | operation blocks |
| --- | --- | ---: |
| `module.sem` | top-level `standard` relay | 0 |
| `<module>/main.sem` | standard module entry and exported surface | varies |
| `<module>/main.test.sem` | companion self-test | 1 |

## Running the self-tests

From `SemanticScript/`:

```powershell
python tests/test_stdlib.py
```

The harness compiles every file through the trusted Python reference compiler
(`compiler/semsc.py`) and runs it. Most files must print exactly `OK`; `stdio`
prints a fixed multiline smoke-test transcript.

Each file can also be run directly:

```powershell
python compiler/semsc.py std/string/main.test.sem --run --quiet
python compiler/semsc.py std/math_float/main.test.sem --run --quiet
python compiler/semsc.py std/stdio/main.test.sem --run --quiet
```

## Compiler support this depends on

The stdlib files use a few compiler capabilities beyond the original 1.0.0
surface:

- lazy `puts` / `printf` extern declarations, so SemanticScript code can define user
  operations with those names without colliding with libc glue;
- typed user-operation returns derived from `output` lines, including pointer,
  integer, and float success values;
- typed `return ok`, `return error`, and `return value` coercion;
- user-operation error predicates that match the return shape (`0`, null, or
  `0.0` as the success sentinel);
- `math.intToFloat` and `math.floatToInt` lowering for pure-SemanticScript float helpers.

## Still missing

This is not a complete C standard library. The large remaining surfaces are
formatted input/output, full file streams, complete transcendental math with
IEEE edge cases, locale, wide characters, complex numbers, floating-point
environment controls, setjmp/longjmp, atomics, and true cross-file linking.

The current value of this directory is narrower and concrete: it gives the
compiler real SemanticScript library code to compile, run, and regress-test.
