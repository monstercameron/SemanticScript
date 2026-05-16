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
