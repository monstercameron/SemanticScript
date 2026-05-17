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

`bootstrap_general.as` is separate from the numbered chain. It is the
current AS-written compiler used by `tests/as_compiler_parity.py`; it
reads the target program from `AS_INPUT`, emits LLVM IR to stdout, and
passes 23 oracle-backed programs today.

## bootstrap_general.as — the real general-purpose compiler

`bootstrap_general.as` is the first AS-written compiler to use **real
per-line verb dispatch** rather than whole-file marker scanning. It now
keeps repeated scanning work in same-file helper operations such as
`lineStartsWithKeyword` and `findLineEndOffset`; those helpers still bottom
out in the trusted compiler's `c.strncmp`, `c.strchr`, and pointer primitives.
That is the foundation a general-purpose AgentScript compiler needs.

**v0.1 verb coverage:** line-by-line detection of `const NAME String "..."`
and `const NAME CNullTerminatedByteString "..."`, with escape-aware string
body emission. Every other line is still ignored. The two-pass structure
emits all string constants at module scope in pass 1, then walks again to
emit a `main()` that puts each constant in source order.

**Programs it currently handles:** 23 oracle-backed programs whose expected
stdout is exactly the concatenation of string constants in source order.
That includes the hello-family, captured-output replay programs, and the
long-running `webserver_console.as` banner case.

**Programs it does NOT yet handle:** anything whose output depends on real
execution semantics instead of source string constants:
- computed integer output (`console.writeIntegerLine value`)
- `c.printf` format substitution
- `var` / `set` mutation and math.* arithmetic
- `branchIf` / loops / conditional control flow
- stdin-driven behavior
- real call/arg/run dispatch (it currently emits a puts per string const,
  regardless of whether the program actually runs that call)

**Architectural roadmap toward 28/28:**
Each subsequent version of `bootstrap_general.as` adds real verb handlers.

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

Current score: **23 / 28 oracle-backed programs pass via
`bootstrap_general.as`.**

Every passing program is compiled by the same AS-written compiler. There
are no per-program specialized compilers in the current tree. The harness
lives at `tests/as_compiler_parity.py`. The 5 programs that do not pass
through the general compiler yet require integer output, mutation, math,
conditional control flow, loops, or stdin handling.

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
on computed conditions, loop emission, real `returnOk ExitCode` handling,
and `c.fgets`-style stdin dispatch.

`webserver_console.as` passes because its banner string is just a
`String "..."` constant. The harness runs both sides under
long-running mode (1.5 s, then terminate, compare captured stdout).

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

1. Full line-oriented tokenization beyond the current `const` string
   scanner: split by whitespace, preserve quoted literals, and decode
   escape rules for every verb handler.
2. A real symbol table mapping AS identifiers to LLVM globals, allocas,
   SSA values, call objects, labels, and operation-local scopes.
3. Dispatch table for executable AS verbs (`const`, `var`, `set`, `call`, `arg`,
   `run`, `bind`, `bindOk`, `bindError`, `ignoreOk`, `makeError`,
   `label`, `branch`, `branchIf`, `branchIfError`, `returnOk`,
   `returnError`, etc.).
4. Dynamic LLVM IR emitters for each verb. `bootstrap_general` already
   emits an input-dependent set of string constants and puts calls, but
   the emitted `main()` is still a string-replay skeleton rather than a
   real lowering of the target program's call graph.
5. Heap-allocated string interning so that multiple distinct
   `CNullTerminatedByteString` constants can be emitted in a single
   module.
6. Dynamic basic-block tracking — generate fresh `bb_<n>` labels per
   `label` verb and patch forward branches as they become available.
7. A target-program `c.*` libc dispatcher in the AS-written compiler.
   The trusted Python compiler already has this registry in
   `compiler/libc_registry.py`; the self-host path still needs an
   AgentScript representation of the signatures it can emit.
8. Real handling of `bindOk` / `bindError` / `branchIfError` —
   bootstrap5 still uses the libc error-code convention via the trusted
   compiler when building itself.

These are the deliverables required before the AgentScript compiler can
compile its own source. The chain runner above guards the floor: every
stage we already have keeps working as we add the missing rungs.
