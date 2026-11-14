# Self-hosting plan: what 1.0 means (2026-11-14)

The goal is a language that writes its own compiler. This file states the bar
for 1.0, the subset the self-hosted compiler must accept, the architecture,
and the stages. Progress is recorded in the table at the end.

## The 1.0 bar

1.0 is reached when all of these hold, each checked by a test in `tests/`:

1. **A compiler written in the language.** `docs/refined-examples/stage0`
   (renamed `selfhost` when it reaches the bar) is SemanticScript source that
   reads a project, checks that it is in the self-hosting subset, writes it
   as C, and builds it with the C compiler.
2. **It compiles itself.** Built once by the Python compiler (`refined build
   --kind executable`), it compiles its own source into a second executable.
3. **Fixed point.** The second executable compiles the same source to C that
   is byte-identical to what the first wrote. The bootstrap is closed: from
   then on the Python compiler is no longer needed to build the compiler.
4. **Same behaviour.** Every suite program inside the subset, built by the
   self-hosted compiler, prints what `refined run` prints and exits with the
   same code, traps included.
5. **Honest refusal.** A program outside the subset is refused with
   `path:line:column: message (word)` and exit 1; the compiler never writes C
   it cannot vouch for.

The safety analyses (ownership, loans, regions, task state, exhaustive
error handling, authority) stay in the reference checker, `refined check`,
which every program passes first, as stage0's header states today. Porting
the checker into the language is the work after 1.0; the compiler's own
source is checked by it like any other program.

## The self-hosting subset

Measured from the compiler's own source (stage0, 15,735 rows):

- Entities: `module`, `operation`, `record`, `enum` with payloads,
  `typeInstance` (`list.List`, `map.Map` with `String` keys), `table`,
  `constant`, `capability`, `region`, `task`, `operationType`.
- Steps: `do`, `set`, `goto`, `branch if`, `branch ifError`, `branch ifNext`,
  `match` and `case`, `return ok`, `return error`, `start`, `join`.
- Loops: plain labels, `forEach` over lists and tables, `while`.
- Library targets: about 120 from `string`, `buffer`, `byte`, `compare`,
  `math`, `logic`, `convert`, `console`, `fs`, `process`, `time`; derived
  targets `<Record>.new`, `<Record>.<field>`, `<Record>.with`,
  `<Enum>.<variant>`, `<List>.new/append/length/getOrTrap`,
  `<Map>.new/put/get/contains`, `<table>.rowAt`.

The subset grows only as the compiler's own source needs it.

## Architecture

- Emitted C links `native_runtime.c`, the runtime standalone executables
  already use. Host targets go through its single entry point,
  `refined_host(name, n, args, results, payload)`, with values flattened to
  64-bit slots exactly as `codegen.py` does; traps go through `refined_trap`
  so messages match the JIT; regions use the runtime's arena functions.
- The compiler is several modules (lexer, syntax, model, subset checker, C
  emitter, driver), each with module tests for every exported invariant.
- Its source is long because the syntax is explicit (about 17 rows per
  call, D-113). Generator scripts that write it are kept in `tools/` beside
  the source they produce, so a reader can regenerate and diff.

## Stages

| Stage | Accepts | State |
| --- | --- | --- |
| 0 | One module, `main` only; `Int64`, `String`, `Bool`, `ExitCode`; 22 targets; every step and loop kind but `forEach` | Done; builds natively and emits byte-identical C (tests/test_stage0.py); builds 3 of 52 suite programs (tests/test_selfhost_suite.py) |
| 1 | Several operations with inputs and outputs, calls between them, recursion; records; enums with payloads and `match`; `raises` | In progress |
| 2 | Lists in regions, `forEach`, tables; string targets; constants of every type | Planned |
| 3 | Host targets through `refined_host` (buffer, map, fs, process, console, time); several modules; tasks | Planned |
| 4 | Its own source: compile every compiler module; then the fixed point | Planned |
