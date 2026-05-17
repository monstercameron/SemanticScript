# AgentScript standard library (`stdlib_as/`)

This directory contains executable AgentScript modules that exercise
standard-library-shaped operations. Each file is standalone today because the
compiler does not yet support cross-file AgentScript imports or linking.

Most helper logic is written in AgentScript: byte loops, classifiers,
integer math, float helpers, memory walks, table lookups, and small container
algorithms. A few operations intentionally bottom out in host C calls where
there is no useful pure-AS substitute yet, such as `c.putchar`, `c.malloc`,
`c.free`, `c.clock`, `c.time`, `c.getenv`, `c.exit`, `c.abort`, and
`c.raise`.

## Coverage

The current tree has 318 `operation` blocks across 28 runnable `.as` files,
including each file's self-test `main`.

| file | category | operation blocks |
| --- | --- | ---: |
| `array.as` | array helpers | 7 |
| `assert.as` | assertion helpers | 9 |
| `bit.as` | bit operations | 7 |
| `bool.as` | boolean helpers | 8 |
| `char.as` | character helpers | 19 |
| `compare.as` | comparison helpers | 9 |
| `constants.as` | constants | 18 |
| `convert.as` | conversion helpers | 8 |
| `ctype.as` | byte classifiers | 15 |
| `errno.as` | errno names/messages | 15 |
| `errno_more.as` | additional errno values | 23 |
| `inttypes.as` | inttypes-style helpers | 6 |
| `iso646.as` | alternate token helpers | 7 |
| `limits.as` | integer limits | 12 |
| `math.as` | integer math | 17 |
| `math_float.as` | float math helpers | 33 |
| `memory.as` | byte memory routines | 8 |
| `numeric.as` | numeric helpers | 12 |
| `process.as` | process wrappers | 3 |
| `random.as` | deterministic pseudo-random helpers | 6 |
| `signal.as` | signal wrappers | 8 |
| `signal_more.as` | additional signal values | 16 |
| `sort.as` | sorting/search helpers | 4 |
| `stddef.as` | stddef-style helpers | 6 |
| `stdio.as` | stdout formatting helpers | 7 |
| `stdlib.as` | integer parsing/numeric helpers | 9 |
| `string.as` | string routines | 17 |
| `time.as` | time wrappers/helpers | 9 |

## Running the self-tests

From `AgentScript/`:

```powershell
python tests/test_stdlib.py
```

The harness compiles every file through the trusted Python reference compiler
(`compiler/ascc.py`) and runs it. Most files must print exactly `OK`; `stdio.as`
prints a fixed multiline smoke-test transcript.

Each file can also be run directly:

```powershell
python compiler/ascc.py stdlib_as/string.as --run --quiet
python compiler/ascc.py stdlib_as/math_float.as --run --quiet
python compiler/ascc.py stdlib_as/stdio.as --run --quiet
```

## Compiler support this depends on

The stdlib files use a few compiler capabilities beyond the original 1.0.0
surface:

- lazy `puts` / `printf` extern declarations, so AS code can define user
  operations with those names without colliding with libc glue;
- typed user-operation returns derived from `output` lines, including pointer,
  integer, and float success values;
- typed `returnOk`, `returnError`, and `returnValue` coercion;
- user-operation error predicates that match the return shape (`0`, null, or
  `0.0` as the success sentinel);
- `math.intToFloat` and `math.floatToInt` lowering for pure-AS float helpers.

## Still missing

This is not a complete C standard library. The large remaining surfaces are
formatted input/output, full file streams, complete transcendental math with
IEEE edge cases, locale, wide characters, complex numbers, floating-point
environment controls, setjmp/longjmp, atomics, and true cross-file linking.

The current value of this directory is narrower and concrete: it gives the
compiler real AgentScript library code to compile, run, and regress-test.
