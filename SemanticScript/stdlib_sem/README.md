# SemanticScript standard library (`stdlib_sem/`)

This directory contains executable SemanticScript modules that exercise
standard-library-shaped operations. Each file is standalone today because the
compiler does not yet support cross-file SemanticScript imports or linking.

Most helper logic is written in SemanticScript: byte loops, classifiers,
integer math, float helpers, memory walks, table lookups, and small container
algorithms. A few operations intentionally bottom out in host C calls where
there is no useful pure-SemanticScript substitute yet, such as `c.putchar`, `c.malloc`,
`c.free`, `c.clock`, `c.time`, `c.getenv`, `c.exit`, `c.abort`, and
`c.raise`.

## Coverage

The current tree has 318 `operation` blocks across 28 runnable `.sscript` files,
including each file's self-test `main`.

| file | category | operation blocks |
| --- | --- | ---: |
| `array.sscript` | array helpers | 7 |
| `assert.sscript` | assertion helpers | 9 |
| `bit.sscript` | bit operations | 7 |
| `bool.sscript` | boolean helpers | 8 |
| `char.sscript` | character helpers | 19 |
| `compare.sscript` | comparison helpers | 9 |
| `constants.sscript` | constants | 18 |
| `convert.sscript` | conversion helpers | 8 |
| `ctype.sscript` | byte classifiers | 15 |
| `errno.sscript` | errno names/messages | 15 |
| `errno_more.sscript` | additional errno values | 23 |
| `inttypes.sscript` | inttypes-style helpers | 6 |
| `iso646.sscript` | alternate token helpers | 7 |
| `limits.sscript` | integer limits | 12 |
| `math.sscript` | integer math | 17 |
| `math_float.sscript` | float math helpers | 33 |
| `memory.sscript` | byte memory routines | 8 |
| `numeric.sscript` | numeric helpers | 12 |
| `process.sscript` | process wrappers | 3 |
| `random.sscript` | deterministic pseudo-random helpers | 6 |
| `signal.sscript` | signal wrappers | 8 |
| `signal_more.sscript` | additional signal values | 16 |
| `sort.sscript` | sorting/search helpers | 4 |
| `stddef.sscript` | stddef-style helpers | 6 |
| `stdio.sscript` | stdout formatting helpers | 7 |
| `stdlib.sscript` | integer parsing/numeric helpers | 9 |
| `string.sscript` | string routines | 17 |
| `time.sscript` | time wrappers/helpers | 9 |

## Running the self-tests

From `SemanticScript/`:

```powershell
python tests/test_stdlib.py
```

The harness compiles every file through the trusted Python reference compiler
(`compiler/semsc.py`) and runs it. Most files must print exactly `OK`; `stdio.sscript`
prints a fixed multiline smoke-test transcript.

Each file can also be run directly:

```powershell
python compiler/semsc.py stdlib_sem/string.sscript --run --quiet
python compiler/semsc.py stdlib_sem/math_float.sscript --run --quiet
python compiler/semsc.py stdlib_sem/stdio.sscript --run --quiet
```

## Compiler support this depends on

The stdlib files use a few compiler capabilities beyond the original 1.0.0
surface:

- lazy `puts` / `printf` extern declarations, so SemanticScript code can define user
  operations with those names without colliding with libc glue;
- typed user-operation returns derived from `output` lines, including pointer,
  integer, and float success values;
- typed `returnOk`, `returnError`, and `returnValue` coercion;
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
