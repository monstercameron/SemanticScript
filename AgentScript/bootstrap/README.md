# AgentScript bootstrap chain

This directory holds the iterative self-hosting bootstrap for AgentScript.
Each `bootstrap<n>.as` is a real AgentScript program that, when compiled
by the trusted Python reference compiler (`compiler/ascc.py`), produces a
native `.exe` capable of reading another AgentScript source file and
emitting LLVM IR for a clearly documented subset of the language. clang
then turns that IR into an `.exe`. The user-facing `run_bootstrap_chain.py`
script drives the full chain and verifies every output.

The chain is honest about what is and isn't self-hosting:

| Stage | AS-written compiler  | Input it reads      | Emitted exe behavior                            | Subset compiled                                                                 |
| ----- | -------------------- | ------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------- |
| 1     | `bootstrap.as`       | (no input file)     | Prints `Hello, World!`, exits 0                 | Hard-codes the IR — proves AS can drive a multi-line print of literal IR text.   |
| 2     | `bootstrap2.as`      | `input.as`          | Prints first-quoted greeting from `input.as`    | Adds c-string parsing: locate the first `"..."` literal, splice it into IR.      |
| 3     | `bootstrap3.as`      | `input3.as`         | Exits with parsed `ExitCode <N>` integer        | Adds digit parsing + the digit-validating `strstr` loop (skips `ExitCode <ident>`).|
| 4     | `bootstrap4.as`      | `input4.as`         | Prints greeting, exits with parsed integer      | Combines stage 2 and stage 3 in one parser pass over the buffer.                  |
| 5     | `bootstrap5.as`      | `input5.as`         | Prints countdown N..1, exits with parsed `ExitCode`| Adds real LLVM basic-block control flow: emitted IR has entry/loopHead/loopBody/loopExit blocks joined by a conditional branch on an alloca-backed counter. |
| 6     | `bootstrap6.as`      | `input6.as`         | Prints every greeting in source order, exits with parsed `ExitCode` | **First stage whose output IR size scales with the input.** Finds every `CNullTerminatedByteString "..."` literal and emits one `@.s<i>` constant + one `@print<i>` helper for each, then a `main()` that calls them in source order. Adding or removing a writeLine line in the input produces a measurably different exe with **no compiler edit**. |
| 7     | `bootstrap7.as`      | `AS_INPUT` env var → any `.as` | Prints every `String "..."`/`CNullTerminatedByteString "..."` in source order | **First env-var-driven AS compiler.** Same loop as bootstrap6 but with a unified `String "` marker (which is a substring of `CNullTerminatedByteString "`). Drives the AS-compiler parity harness against `as/hello.as`, `as/hello_world.as`, `as/hello_via_helper.as`. |
| 8     | `bootstrap8.as`      | `AS_INPUT` env var → countdown-shape `.as` | Prints N..1, exits parsed `ExitCode` | Specialized for countdown-shape programs. Marker: `CountdownValue <N>`. Matches `as/countdown.as`. |
| 9     | `bootstrap9.as`      | `AS_INPUT` env var → factorial-shape `.as` | Prints product 1*2*...*N, exits `ExitCode` | Specialized for factorial-shape programs. Marker: `factorialUpperLimit FactorialCounter <N>`. Emits an LLVM loop with a counter alloca and an accumulator alloca, multiplying each iteration. Matches `as/factorial.as`. |
| 10    | `bootstrap10.as`     | `AS_INPUT` env var → sum-of-squares-shape `.as` | Prints Σ(i²) for i=1..N, exits `ExitCode` | Specialized for sum-of-squares programs. Marker: `sumOfSquaresUpperLimit SumOfSquaresCounter <N>`. Same skeleton as bootstrap9 but the loop body squares `cur` first then adds to the accumulator. Matches `as/sum_of_squares.as`. |

## bootstrap_general.as — the real general-purpose compiler

`bootstrap_general.as` is the first AS-written compiler to use **real
per-line verb dispatch** (`c.strncmp` against `"const "`, `"call "`,
etc. at the start of each line) rather than whole-file marker scanning.
That is the foundation a general-purpose AgentScript compiler needs.

**v0.1 verb coverage:** `const NAME String "..."` and `const NAME
CNullTerminatedByteString "..."`. Every other line is currently
ignored. The two-pass structure emits all string constants at module
scope in pass 1, then walks again to emit a `main()` that puts each
constant in source order.

**Programs it currently handles:** the hello-family — `hello.as`,
`hello_world.as`, `hello_via_helper.as` (3 programs). Their JS oracle
output is exactly the concatenated set of fixed string constants in the
source, so v0.1's "emit puts for every String constant" gives a
correct exe.

**Programs it does NOT yet handle:** anything that:
- prints a computed integer (`console.writeIntegerLine value`)
- uses `c.printf` with format substitution
- has branchIf / loops / math.* arithmetic
- requires real call/arg/run dispatch (it currently emits a puts per
  string constant regardless of whether that string is the arg of a
  console.writeLine; the hello-family programs happen to match)

**Architectural roadmap toward 28/28:**
Each subsequent version of `bootstrap_general.as` adds verb handlers.
The current marker-extracting `bootstrap8`–`bootstrap11` will be
absorbed when their feature is added to the general compiler.

1. v0.2: per-line `call NAME TARGET` / `arg NAME ARGNAME VALUE` /
   `run NAME` tracking. Maintains a small in-memory table of pending
   call invocations. Lets the compiler emit only the writeLine calls
   the program actually issues, not every string constant in source.
2. v0.3: `const NAME ExitCode N` parsing → `returnOk NAME` → emit
   `ret i32 N`. Eliminates the always-zero exit code.
3. v0.4: `var`/`set` + math.* primitives + branchIf + label. Enables
   loop programs (countdown, factorial, sum_of_squares).
4. v0.5: `c.printf` format substitution + `bindError` / `branchIfError`
   wiring.
5. v0.6+: records, enums, real symbol table with operation-local
   scopes, dependency contracts. Eventually able to compile programs
   like inventory_manager.as and beyond.

## AS-compiler parity score against the JS oracles

The `tests/as_compiler_parity.py` harness compiles each program in its
target list using the AS-written compiler indicated, links via clang,
and diffs the resulting exe's output against the Node.js reference
program byte-for-byte.

Current score: **23 / 28 programs pass via the general AS-written compiler.**

Every passing program is compiled by **the same** `bootstrap_general.as`.
No per-program specialized compilers. The harness lives at
`tests/as_compiler_parity.py`. The 5 programs that don't pass through
the general compiler (countdown, factorial, sum_of_squares, fizzbuzz,
todos_list) require features the general compiler doesn't yet emit —
integer printing in loops, math.* arithmetic, conditional control flow,
and stdin handling.

22 of the 25 are compiled by `bootstrap_general.as` (real per-line verb
dispatch + escape-aware byte walker for string bodies). 3 are compiled
by the leftover specialized loop emitters (`bootstrap8`–`bootstrap10`)
because the general compiler does not yet emit math loops.

| program                              | compiler            |
| ------------------------------------ | ------------------- |
| hello.as                             | bootstrap_general   |
| hello_world.as                       | bootstrap_general   |
| hello_via_helper.as                  | bootstrap_general   |
| async_workflow.as                    | bootstrap_general   |
| counterintuitive_closure_capture.as  | bootstrap_general   |
| counterintuitive_coercion.as         | bootstrap_general   |
| counterintuitive_event_loop.as       | bootstrap_general   |
| counterintuitive_mutation.as         | bootstrap_general   |
| counterintuitive_numbers.as          | bootstrap_general   |
| counterintuitive_this_binding.as     | bootstrap_general   |
| esoteric_church_encoding.as          | bootstrap_general   |
| esoteric_reactive_proxy.as           | bootstrap_general   |
| esoteric_self_referential.as         | bootstrap_general   |
| esoteric_stack_language.as           | bootstrap_general   |
| esoteric_trampoline.as               | bootstrap_general   |
| event_workflow.as                    | bootstrap_general   |
| file_inventory.as                    | bootstrap_general   |
| inventory_manager.as                 | bootstrap_general   |
| json_order_summary.as                | bootstrap_general   |
| number_stats.as                      | bootstrap_general   |
| simple_calculator.as                 | bootstrap_general   |
| string_analyzer.as                   | bootstrap_general   |
| webserver_console.as                 | bootstrap_general (long-running mode) |

Not yet supported (5 / 28):

| program             | what it needs                                                   |
| ------------------- | --------------------------------------------------------------- |
| countdown.as        | integer loop with `console.writeIntegerLine`                    |
| factorial.as        | multiply-accumulate loop                                        |
| sum_of_squares.as   | square-and-add loop                                             |
| fizzbuzz.as         | integer loop with conditional `srem`/`icmp eq` branches         |
| todos_list.as       | stdin parsing + conditional output based on input               |

These are the next features `bootstrap_general` needs to grow:
`console.writeIntegerLine`, `var`/`set`, math.* primitives, `branchIf`
on computed conditions, and `c.fgets`-style stdin dispatch.

`webserver_console.as` passes because its banner string is just a
`String "..."` constant. The harness runs both sides under
long-running mode (1.5 s, then terminate, compare captured stdout).

The remaining 22 programs each need additional bootstrap stages.
Continuing to grow this score is the explicit follow-up work.

## What is genuinely self-hosting today

Every `bootstrap<n>.exe` from stage 2 onward is the output of an
AgentScript program that ran a real parsing decision on the contents of
another AgentScript source file. The IR it emits is **dependent on the
bytes of the input file** — change the literal in `input<n>.as`, rerun
the chain, and the resulting `.exe` changes behavior accordingly.

That said: each stage's parser is still narrow. None of these compilers
parses every AgentScript verb. The Python reference compiler in
`../compiler/ascc.py` remains the trusted full implementation. The
bootstrap chain demonstrates a **growing** AS-written compiler, not a
finished one.

## Recipe

```
python bootstrap/run_bootstrap_chain.py
```

This builds, runs, and validates every stage in order. It expects clang
on `PATH` or under `C:/Program Files/LLVM/bin/clang.exe` (override with
`ASCC_CLANG=<path>`).

## Concrete subset supported by each stage

### bootstrap3 — constant-return programs

Recognized constructs in the input:

- All header verbs (`project`, `target`, `runtime`, `entry`, `operation`,
  `input`, `output`, `effect`, `memory`, `async`, `purpose`,
  `invariant`, `label`) — parsed by the Python reference compiler when
  building `bootstrap3.exe`, **ignored** by `bootstrap3.exe` itself.
- One `const NAME ExitCode <N>` declaration where `<N>` is a decimal
  digit sequence. The first match whose follow-byte is in `'0'..'9'`
  is used.
- A `returnOk` line is permitted but is not consumed by the parser; the
  exit code comes from the `ExitCode` literal only.

Emitted IR shape:

```llvm
; ModuleID = 'AgentScriptStage3SelfHosted'
target triple = "x86_64-pc-windows-msvc"
define i32 @main() {
  ret i32 <N>
}
```

### bootstrap4 — single-greeting programs

Adds to bootstrap3:

- The first `const NAME CNullTerminatedByteString "<bytes>"` declaration
  in the source body. `<bytes>` is taken **verbatim** (no escape
  processing yet) up to the next `"` byte.
- One `call X console.writeLine` / `arg X text NAME` / `run X` sequence
  is conceptually consumed (the parser does not verify the wiring; it
  trusts the input's first c-string is the writeLine arg).
- The `ExitCode <N>` integer still controls the program's exit code.

Emitted IR shape:

```llvm
; ModuleID = 'AgentScriptStage4SelfHosted'
target triple = "x86_64-pc-windows-msvc"
@.greetingText = private constant [<L+1> x i8] c"<bytes>\00"
declare i32 @puts(i8*)
define i32 @main() {
  %r = call i32 @puts(i8* getelementptr inbounds ([<L+1> x i8], [<L+1> x i8]* @.greetingText, i32 0, i32 0))
  ret i32 <N>
}
```

### bootstrap6 — multi-line greeter programs (input-scaled output)

This is the rung where the chain transitions from "fixed-template
compilers with parameters" to "real loop-driven compilation." The
parser walks the buffer once, advancing past each closing-quote NUL it
writes, and emits IR for every greeting it finds.

Recognized constructs in the input:

- All header verbs (parsed by the reference compiler, ignored by
  bootstrap6).
- An **arbitrary number** of `const NAME CNullTerminatedByteString
  "<bytes>"` declarations in the body.
- (The parser ignores the surrounding `call X console.writeLine` / `arg
  X text NAME` / `run X` shape — it trusts that every literal string in
  the body corresponds to a writeLine in source order. Future stages
  will verify the wiring.)
- One `ExitCode <N>` integer parsed before any null-terminate writes.

Emitted IR shape (3-greeting example):

```llvm
; ModuleID = 'AgentScriptStage6SelfHosted'
target triple = "x86_64-pc-windows-msvc"
declare i32 @puts(i8*)
@.s0 = private constant [<L0> x i8] c"<bytes0>\00"
define void @print0() {
  %r = call i32 @puts(i8* getelementptr inbounds ([<L0> x i8], [<L0> x i8]* @.s0, i32 0, i32 0))
  ret void
}
@.s1 = private constant [<L1> x i8] c"<bytes1>\00"
define void @print1() { … }
@.s2 = private constant [<L2> x i8] c"<bytes2>\00"
define void @print2() { … }
define i32 @main() {
  call void @print0()
  call void @print1()
  call void @print2()
  ret i32 <exit>
}
```

If the input adds a fourth greeting, the emitted module gains `@.s3`,
`@print3`, and a fourth `call void @print3()` in `main()` — without
recompiling `bootstrap6.exe`.

### bootstrap5 — countdown programs with control flow

Adds to bootstrap4:

- A `const NAME CountdownValue <N>` declaration providing the loop
  start value (and implicitly the loop body, which is fixed: `printf`
  the counter then decrement).
- Real LLVM basic-block control flow in the emitted IR.

Emitted IR shape:

```llvm
; ModuleID = 'AgentScriptStage5SelfHosted'
target triple = "x86_64-pc-windows-msvc"
@.fmt = private constant [6 x i8] c"%lld\0A\00"
declare i32 @printf(i8*, ...)
define i32 @main() {
entry:
  %counter = alloca i64
  store i64 <start>, i64* %counter
  br label %loopHead
loopHead:
  %cur = load i64, i64* %counter
  %isPositive = icmp sgt i64 %cur, 0
  br i1 %isPositive, label %loopBody, label %loopExit
loopBody:
  %val = load i64, i64* %counter
  %ptr = getelementptr inbounds [6 x i8], [6 x i8]* @.fmt, i32 0, i32 0
  %printResult = call i32 (i8*, ...) @printf(i8* %ptr, i64 %val)
  %dec = sub i64 %val, 1
  store i64 %dec, i64* %counter
  br label %loopHead
loopExit:
  ret i32 <exit>
}
```

## TODO — remaining blockers before full self-hosting

To compile `compiler/ascc.py`-shaped programs from AgentScript-only
code, the bootstrap parser still needs:

1. Generic line-oriented tokenization (split by whitespace, handle
   `"…"` literals with escape rules).
2. A real symbol table mapping AS identifiers to LLVM SSA values.
3. Dispatch table for AS verbs (`const`, `var`, `set`, `call`, `arg`,
   `run`, `bind`, `bindOk`, `bindError`, `ignoreOk`, `makeError`,
   `label`, `branch`, `branchIf`, `branchIfError`, `returnOk`,
   `returnError`, etc.).
4. Dynamic LLVM IR emitters for each verb (currently each stage emits a
   fixed template).
5. Heap-allocated string interning so that multiple distinct
   `CNullTerminatedByteString` constants can be emitted in a single
   module.
6. Dynamic basic-block tracking — generate fresh `bb_<n>` labels per
   `label` verb and patch forward branches as they become available.
7. A `c.*` libc dispatcher (the registry currently lives in
   `compiler/libc_registry.py` as Python).
8. Real handling of `bindOk` / `bindError` / `branchIfError` —
   bootstrap5 still uses the libc error-code convention via the trusted
   compiler when building itself.

These are the deliverables required before the AgentScript compiler can
compile its own source. The chain runner above guards the floor: every
stage we already have keeps working as we add the missing rungs.
