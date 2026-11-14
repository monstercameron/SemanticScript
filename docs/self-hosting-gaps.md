# Self-hosting gap analysis (2026-11-14)

Scope: the refined language and its compiler (`semanticscript/compiler/refined`) at commit `21cf659`, measured against a 70-item checklist with one goal: a compiler for the language, written in the language, that produces a runnable artifact. The explicit-syntax rule (D-47: one `<subject> <predicate> <payload>` pattern, no shorthand, no inferred defaults, no expression syntax) is treated as fixed. Where an item is absent only because it would need concise syntax, the item is marked "Not applicable by design" and the explicit-row equivalent is named.

## Executive summary

Of the 70 items, **29 are Supported, 31 Partial, 3 Missing, and 7 Not applicable by design**. The language core (records, enums with payloads, exhaustive `match`, ownership, regions, loops, recursion, typed list positions) is sound enough to write a compiler in, and the `lexer` and `symbols` examples prove the front-end half under `refined run`. Self-hosting is blocked by one structural fact, not by the language design: everything a compiler needs from the operating system and every keyed or growable-text container is a **host target implemented in Python (`host.py`) and refused in standalone executables with R901**. Verified: `refined build --kind executable` refuses the `lexer` example (11 host targets, including `fs.readAll`, `process.argument`, `buffer.*`, `string.fromBytes`) and the `symbols` example (`map.Map.*`). A compiler written in the language today can run only inside the Python JIT, and nothing it emits could be a compiler that reads a file. After that, the largest risks are the AST model (no mutation of an element in place, a `NodeId` that cannot index a second list or become a number, a verified stale-position defect after `clear`), the volume the explicit rule produces (about 12 rows per call; an estimated 100,000 to 180,000 rows for the compiler), and a checker whose time grows quadratically with module size (measured). The recommended emission target is **C source**, written to a file and built by the C compiler that `refined build --kind executable` already requires.

## Status since this report

The report below describes commit `21cf659` and is kept as written. Since then, the roadmap at the end has
moved as follows (decisions in `docs/language-refinement.md`):

| Roadmap item | State | Where |
| --- | --- | --- |
| 1, 3: native `fs`, process arguments, `environment`, `console.readLine`, `process.run`, `buffer`, `string.fromBytes`, `time.Deadline` | Done: an executable reads files and arguments with no Python | D-80 to D-85 |
| 2: native `map.Map` and `set.Set` | Done | D-80 to D-85 |
| 4: position soundness | Done: positions carry the list's identity; indexed lists only grow | D-100 |
| 5: tree ergonomics | Done: `<Alias>.toInt64`, `replace`, `removeLast`, `truncate` | D-100, D-102, D-105 |
| 6: trapping twins | Done: `getOrTrap`, `byteAtOrTrap` | D-101 |
| 7: text and bytes targets | Done without the host | D-91 |
| 8: `constant`, `<table>.rowAt`, `<table>.length` | Done | D-103, D-104 |
| 9: checker performance | Done: 4,000 operations check in about 2 seconds | D-106 |
| 10: integer types | Done: every integer type computes | D-90 |
| 11: layered generics, sets of `String` | Done | D-92 to D-94 |
| 15: chunked native arena | Done | D-80 to D-85 |
| 12 to 14: the compiler in the language, its C emitter, the bootstrap | In progress: a stage-0 compiler is being written in the language | — |

An adversarial review of the new collection and tooling rules then found nine holes. All are closed and each has
a regression check (D-107 to D-109; `tests/suite/conformance.py`, `tests/test_review.py`).

## Method

Statuses come from reading `shapes.py`, `library.py`, `host.py`, `codegen.py`, `native.py`, `native_runtime.c`, `semantics.py`, `flow.py`, and the design record, and from probes run on scratch copies outside the repository. "Verified" below means a probe was run; "by reading" means the claim rests on the cited code only. Three levels are kept apart for every item:

- **Checker**: `refined check` accepts it.
- **JIT**: `refined run` compiles and runs it (LLVM through llvmlite, host targets through the Python callback `refined_host`, D-28).
- **Executable**: `refined build --kind executable` links it with `native_runtime.c` and it runs with no Python.

What an executable contains today (by reading `codegen.py` and `native_runtime.c`, and verified with a probe that built and ran a program using a region, a `list.List String`, `string.concat`, `string.fromInt64`, `string.toInt64`, a wide enum, and `match`): `console.write*` and `writeError`, `math`, `compare`, `logic`, `bits`, `convert`, `byte`, the inline `string` targets (`byteLength`, `byteAt`, `equals`, `startsWith`, `find`, `slice`, `concat`, `fromInt64`, `toInt64`, `toBytes`, `advancePosition`), `list.List`, records, enums, `option.Option`, tables, operation references, regions and `arena`, `test`, and tasks run sequentially at `start` (D-37). Everything registered with `@target` in `host.py` is refused: `fs`, `process`, `environment`, `console.readLine`, `time`, `clock`, `net`, `http`, `buffer`, `string.fromBytes`, `map.Map`, `set.Set`, `channel.Channel`, `json`, `crypto`, `random`, `secret`, `signal`, `ffi`.

## Checklist

Each entry gives status, evidence, gaps, impact on self-hosting, and a recommendation.

### Types

**1 Primitive types. Partial.** Evidence: `BUILTINS` in `library.py` declares `Int8` to `Int64`, `UInt8` to `UInt64`, `Float32`, `Float64`, `Bool`, `Byte`, `ExitCode`; literals are range-checked (`INTEGER_RANGES`). Gaps: operations exist only for `Int64`, `Int32`, `Float64` (`math`), plus `Byte` in `compare`; `bits` is `Int64` only; `convert` has eight targets. `Int8`, `Int16`, every `UInt*`, and `Float32` can be declared and stored but have no arithmetic, comparison, or conversion target, so they are inert. Impact: **Minor**; a compiler can work in `Int64` and `Byte`, but it cannot range-check a `UInt64` literal above `Int64` maximum. Recommendation: add the missing `math`, `compare`, and `convert` targets per type as named targets, or remove the inert types until they have them.

**2 Strings and characters. Partial.** Evidence: `String` is `{bytes, length}` UTF-8 (LR-27); `Byte` stands in for characters; `byte.isLetter` and four more classifiers; D-70 to D-72. Gaps: no character or code-point type; no ordering comparison of strings; no `endsWith`, no search from an offset, no string from one byte in an executable (only `buffer.appendByte`, a host target). Impact: **Minor**; the language's own source is ASCII-structured and the lexer example works with bytes. Recommendation: add `string.compare`, `string.findFrom`, `string.fromByte` as inline targets.

**3 User-defined structs and records. Supported.** Evidence: `record` kind; derived targets `T.new`, `T.<field>`, `T.with`, `T.equals` (`codegen.py` `derived`); JIT and executable. Gaps: one field changes per `with` call; a record that holds non-plain fields takes a region in `new` (verified: R405 without it). Impact: **None**. Recommendation: none.

**4 Enums and tagged unions. Supported.** Evidence: `enum` with `variant <name> none|<Type>`; compact and wide layouts (D-30); exhaustive `match` (R509). Verified in an executable with a `String` payload. Gaps: one payload per variant, so a multi-field variant needs a record declared beside it. Impact: **None**. Recommendation: none.

**5 Recursive data types. Partial.** Evidence: D-60 rejects a type that holds itself by value or inside a collection (R403) and gives trees as a list of nodes read by a typed position (`NodeId aliasOf Int64`, `NodeId indexes Nodes`, `Nodes.appendIndexed`); `symbols` example; `tests/suite/programs/08-strings-collections/trees.sem`. Gaps: `indexes` is exactly one row and the list type must be in the same module (R403), so one alias positions one list; see items 68 and 69 for what follows. Impact: **Major**; every AST, type table, and control-flow graph in the compiler takes this form. Recommendation: see 68 and 69.

**6 Type aliases. Partial.** Evidence: `alias` kind with `aliasOf` and `indexes`; `typeParameter` is exactly `none`. Verified: an index alias is nominal, `math.addInt64` refuses a `NodeId` (R403). Gaps: no generic alias; no conversion between an alias and its base type in either direction. Impact: **Minor** on its own, **Major** through item 69. Recommendation: a derived target `<Alias>.toInt64` (one way; a position still has no literal).

**7 Generic types and functions. Partial.** Evidence: `typeParameter <T> any|plain` on `record`, `enum`, `operation`; `typeInstance` and `operationInstance` name every instantiation (LR-24); compiled once per instance (Part 8); `tests/suite/programs/14-types-generics/generics.sem`. Gaps: (a) the only constraints are `any` and `plain`, so a generic body cannot compare, hash, order, or print a `T`; (b) `operationType` is `typeParameter none`, so a comparator over `T` cannot be passed in; (c) verified: a generic operation cannot call another generic operation at its own `T` (R402 "call it through an `operationInstance`", and an instance is a module-level entity that names concrete types). Generic code therefore cannot be layered: no generic sort, no generic hash map written in the language. Impact: **Major**; it is the reason maps and sets must stay runtime built-ins. Recommendation: allow `operationInstance` rows inside a generic operation's module to name that operation's type parameter (`sortSwap instantiates swap T` with an `in <operation>` row), and allow `typeParameter` on `operationType`. Both are explicit rows.

**8 Optional and nullable types. Supported.** Evidence: `option.Option` (`present`, `absent`), read by `match`; no null. Each `Option T` needs its own `typeInstance`. Impact: **None**.

**9 Result and error types. Supported.** Evidence: `raises <Enum>`, `catch <name> <Type>`, `branch ifError`, `return error` (LR-30); calling convention `{failed, output, error}` in both backends. Gaps: one error enum per operation and no conversion between error enums except by constructing the outer variant in a call. Impact: **None** for capability; see 49 for volume.

**10 Typed references and pointers. Not applicable by design.** Evidence: D-60 ("no pointer types"). The substitutes are loans (`lend`, `lendMutable`) and typed positions. Impact: **Minor** by itself; the consequences are under 45, 68, 69.

### Variables and functions

**11 Mutable and immutable variables. Supported.** Evidence: `let <name> <Type> <value|unset> immutable|mutable`, `set <name> <name>`; R507 (set on every path), R505 (loop counters). Impact: **None**.

**12 Constants. Partial.** Evidence: immutable `let` rows inside one operation; `table` for static record data. Gaps: no module-level constant. The lexer example declares `newlineByte Byte 10` in two operations and `colon Byte 58` in three. A table is read only by `forEach` (R402 "tables are read with `forEach`, not passed"), so it cannot serve as a named constant either. Impact: **Minor**, but it multiplies rows across hundreds of operations. Recommendation: a `constant` entity kind (`<name> is constant`, `<name> purpose "..."`, `<name> type <Type>`, `<name> value <literal>`), usable wherever a `let` name is.

**13 Variable scoping and shadowing. Supported (shadowing rejected by design).** Evidence: R411: one flat scope per operation covering inputs, lets, results, labels, and owned entities, and no clash with a module-level name. Gaps: none in the rule. At scale it is a naming burden: call entities are module-level (R203), so every call site in a module needs a module-unique name, and every result a name unique in its operation. Impact: **Minor**. Recommendation: none; a naming convention (`<operation><Step>`) is enough.

**14 Type inference. Not applicable by design.** Every `let`, `argument`, `result`, and `bind` row states its type (suite case `var-no-inference`). Impact: **None** on capability.

**15 Explicit type conversions. Partial.** Evidence: `convert.int32ToInt64`, `int64ToInt32`, `byteToInt64`, `int64ToByte`, `int64ToFloat64`, `float64ToInt64`, `exitCodeToInt64`, `int64ToExitCode`; narrowing traps. Gaps: nothing for `Int8`, `Int16`, `UInt*`, `Float32`, `Bool`, an alias and its base, or an enum's tag. Impact: **Minor**. Recommendation: complete the table with item 1.

**16 Functions and return values. Supported.** Evidence: `operation` with one `output`; several results go in a record. Both backends. Impact: **None**.

**17 Function overloading. Not applicable by design.** R203: one name, one operation.

**18 Recursive functions. Supported.** Evidence: `maxRecursion <integer>` required exactly when the call graph (including operation references and cross-module calls) has a cycle (R410, `check_recursion`). Verified: a probe recursed 1,000,000 deep under the JIT and trapped cleanly at about 1,570,000 ("ran out of stack before reaching maxRecursion"); the executable reached 1,900,000 (256 MB stack on Windows, `native.py` `STACK_BYTES`). Gaps: the bound is an integer literal, so a recursive-descent parser must pick a maximum nesting depth; import cycles are R603, so mutually recursive operations must share a module or go through an operation reference; `native_runtime.c` keeps depth in `depth[op & 4095]`, which would alias past 4,095 recursive operations (by reading). Impact: **None**.

**19 First-class functions and callbacks. Partial.** Evidence: `operationType`, a `let` initialized from an operation name, `invokesReference`; references in record fields and table cells (`server` example routes); lowered to function pointers, so they work in executables. Gaps: not generic; no bound arguments. Impact: **Minor**; a compiler can dispatch with `match`.

**20 Closures and lambdas. Not applicable by design.** `docs/test-suite.md`: no captured environment. The explicit equivalent is a context record passed as an input. Impact: **Minor**.

### Control flow and operators

**21 Conditional expressions. Supported** as control flow: `branch if <Bool name> goto <label> else goto <label>`. There is no conditional value; the equivalent is a mutable `let` set on both arms (LR-29). Impact: **None**.

**22 Pattern matching and destructuring. Partial.** Evidence: `match <name> <Type>` with one `case` row per variant, binding the one payload (R509). Gaps: one level only; no record destructuring; no match on integers, bytes, or text; no default case, so a match on a 40-variant node enum is at least 41 rows plus two label rows per target block. Dispatch on a byte is a chain of `compare.equalByte` calls at 11 rows each plus a branch. Impact: **Major** for volume, not a blocker. Recommendation: keep exhaustive rows (they are the explicit form). For byte and integer dispatch add indexed table access (item 30) so a 256-row table can classify a byte in one call.

**23 For and while loops. Supported.** Evidence: `loopKind counted|doWhile|forEach|forever|while`, mandatory `maxIterations` (integer, immutable `Int64` name per D-56, or `unbounded` with `forever`), R503 to R505. Both backends. Impact: **None**.

**24 Break, continue, and early return. Supported** through `goto` out of or back to the header (R504) and `return` in any block.

**25 Arithmetic and logical operators. Supported** as named targets (`math.*`, `compare.*`, `logic.*`), inline in both backends. Limited to the types in item 1.

**26 Bitwise operators. Partial.** Evidence: `bits.andInt64`, `orInt64`, `xorInt64`, `notInt64`, `shiftLeftInt64`, `shiftRightInt64`; out-of-range shifts trap. Gaps: `Int64` only; no rotate, no unsigned shift. Impact: **Minor**; enough for a hash with `math.wrappingMultiplyInt64`.

**27 Operator precedence and associativity. Not applicable by design.** No expression syntax; order is the order of `do` steps.

**28 Short-circuit evaluation. Not applicable by design.** `logic.and` takes two values already computed. The explicit equivalent is two branches. Impact: **None**.

### Collections

**29 Dynamic arrays and vectors. Partial.** Evidence: `list.List` members `new`, `append`, `get`, `set`, `length`, `clear`, and `appendIndexed` on an indexed list (`generic_members`); inline in both backends (header plus a data block that doubles). Verified in an executable. Gaps: no `removeLast`, `truncate`, `insert`, `remove`, slice, sort, or search. There is no way to pop, so a stack (parser state, work lists in the flow analyses) needs a separate top counter over a list that never shrinks. `get` of a non-plain item returns a read-only view; see 45. Impact: **Major**. Recommendation: add `removeLast` (returns the item, raises on empty), `truncate`, and `replace` (give a new item, receive the old one as owned).

**30 Fixed-size arrays. Missing.** A `table` is static data but has no indexed read, only `forEach`. Impact: **Minor**. Recommendation: derived targets `<table>.rowAt` (position in, record out, raises on range) and `<table>.length`.

**31 Hash maps and dictionaries. Partial.** Evidence: `map.Map K V` with `new`, `put`, `get`, `contains`, `remove`, `length`; keys plain or `String` (D-61); `forEach` over keys in insertion order (D-62). JIT only: the map is a Python dictionary behind a handle. Verified: the `symbols` example is refused as an executable (R901 naming `map.Map.get`, `keyAt`, `length`, `new`, `put`). Gaps: `get` of a non-plain value is a read-only view, so a map of lists cannot be updated in place; no `forEach` over values. Impact: **Blocker**; symbol tables, module tables, and interning all need it in the compiled compiler. Recommendation: implement `map.Map` and `set.Set` in `native_runtime.c` behind the same `refined_host` names (item 7 explains why they cannot yet be written in the language).

**32 Sets and tuples. Partial.** Evidence: `set.Set T` with `add`, `contains`, `remove`, `length`. Verified gaps: `T` must be plain, a `set.Set String` is R403; a set cannot be iterated, `ifNext` on a set is R402; host only. Tuples do not exist by design (records). Impact: **Minor** once maps exist (a `map.Map String Bool` substitutes). Recommendation: admit `@key` for sets as for map keys, and `forEach` over a set.

**33 Array indexing and slicing. Partial.** Evidence: `list.get`/`set` and `string.byteAt`/`slice` are range-checked. Gaps: no list slice; `Bytes` has no index at all (item 39). Impact: **Minor**.

**34 Collection iteration. Supported.** Evidence: `forEach` with `branch ifNext <collection> bind <name> <Type>` over a table, list, or map; the collection is lent for the whole loop (R515). Gaps: no position during iteration (keep a counter); not over sets. Impact: **None**.

**35 Iterators and iterable interfaces. Missing.** No user-defined iteration and no interface mechanism. Impact: **Minor**; counted loops over `length` cover it.

### Text and bytes

**36 String slicing and searching. Partial.** Evidence: `string.slice` (a view, whole characters, D-70), `find` (first occurrence from the start), `startsWith`, `equals`, `byteAt`. Gaps: as item 2. A slice is a loan: verified, appending a slice to a list with `give` is R514, so tokens cannot hold views of the source; they hold offsets (as the lexer example does) or a copy made with `string.concat`. Impact: **Minor**.

**37 String builders and formatting. Partial.** Evidence: `buffer.ByteBuffer` (`appendString`, `appendByte`, `appendInt64`, `length`, `toString`, `toBytes`), used by the lexer example to write its listing. Host only. In an executable the only way to build text is `string.concat`, which allocates a full copy per call in an arena that never frees, so building an N-byte output piece by piece costs on the order of N squared bytes of region. No formatting, padding, or hexadecimal. Impact: **Blocker** for the emitter in an executable; adequate under the JIT. Recommendation: move `buffer` into the native runtime (it is a growable block, like a list of bytes), and add `appendHex`.

**38 UTF-8 and Unicode handling. Partial.** Evidence: validation in `string.fromBytes`, whole-character slices, `string.advancePosition` (D-71) for line and column. Gaps: no decoding to a code point, no encoding, no classification above ASCII. Impact: **None** for this language's syntax.

**39 Byte buffers and binary operations. Partial.** Evidence: `Bytes` values, `buffer.toBytes`, `string.toBytes`. Gaps: `library.py` has no target that reads a `Bytes`: no length, no index, no slice, no equality outside `crypto.constantTimeEquals`. The only consumers are `fs.write*`, `net.write`, `crypto`, and `string.fromBytes`. Impact: **Minor** if the compiler emits text, **Blocker** for any binary format it would have to read. Recommendation: a `bytes` module (`length`, `byteAt`, `slice`, `equals`), inline.

**40 String-to-number parsing. Partial.** `string.toInt64` only (decimal). No float, hexadecimal, or unsigned parse. Impact: **Minor**; float literals can be carried as their source text into C. Recommendation: `string.toFloat64`.

**41 Numeric-to-string conversion. Partial.** `string.fromInt64`, `buffer.appendInt64`. A float can only be printed (`console.writeFloatLine`), not turned into text. Impact: **Minor**. Recommendation: `string.fromFloat64`.

### Memory

**42 Dynamic memory allocation. Supported** through regions only (`region` entity, `memoryHeap true`); there is no individual free. Impact: **None**.

**43 Arena and region allocation. Supported.** Evidence: `strategy arena`, `maxBytes <integer>`, `released atReturn|atProcessExit`; memory is taken on demand, so the ceiling costs nothing (verified: `maxBytes 1099511627776` checks, runs, and builds). Gaps: the ceiling is a literal chosen when the compiler is written, not from input size; the native arena calls `calloc` once per allocation and keeps a list node for each (`refined_region_alloc`), which is slow and wasteful for millions of small nodes; a list's outgrown blocks stay in the region. Impact: **Minor**. Recommendation: bump allocation in large chunks in `native_runtime.c`.

**44 Ownership and ownership transfer. Supported.** `owned`/`give`, `ownedBy`, `outputOwnedBy`, R513. `docs/safety-guarantees.md` lists the tests.

**45 Immutable and mutable borrowing. Partial.** Evidence: `borrowed`/`borrowedMutable`, `lend`/`lendMutable`, R514, R515. Gap, verified: an item read from a collection is a view and "cannot be lent exclusively" (R515), so a list inside a list, a list inside a map, or a list field of a stored node can never be appended to after it is stored. Every nested structure must be finished before it is inserted, or flattened into parallel top-level lists. Impact: **Major**; scopes holding symbol lists, nodes holding child lists, and per-block instruction lists all hit it. Recommendation: `List.replace` and `Map.replace` (give the new value, receive the old one owned): take the inner list out, change it, put it back. No new loan kind is needed.

**46 Lifetime annotations and inference. Not applicable by design.** There are no annotations; the fixed rules are one `borrows <input>` per result, `outputOwnedBy`, and no stored views (R514). Impact: **Minor** (see 36).

**47 Deterministic resource cleanup. Supported.** `cleanup` entities with `defer`, run newest first at every `return`; regions released at return; D-51 on traps.

**48 Allocation failure handling. Supported.** Passing a region's ceiling is a safe trap naming the region (D-49); `arena.remaining` and `arena.ensure` let a program ask first (D-55), both inline. Impact: **None**; a compiler can trap.

### Errors

**49 Error propagation and recovery. Partial.** Evidence: every fallible activation is followed directly by `branch ifError` (R506); a dropped failure names every variant it drops (D-54). Gaps: propagation is always written out, and an inner error must be rebuilt as the outer operation's enum by a constructor call. Every `list.get`, `string.byteAt`, `string.slice`, and `map.get` is fallible, so each index read costs the call (about 11 rows), a branch row, and an error block (two label rows, usually a constructor call of 10 rows, and a `return error` row): roughly 25 rows per read whose index the program has already proved in range. Impact: **Major** for volume. Recommendation: add trapping twins as separate named targets (`List.at`, `string.byteAtChecked`) that trap on a bad index, on the reasoning D-49 already uses for region limits. That is a second explicit target, not a shorthand.

**50 Exhaustive error matching. Supported.** R509 on `match`; D-54 `suppresses` rows.

### Modules and abstraction

**51 Modules, imports, and exports. Supported.** `module` with `path`, `imports`, `exports`; `includesModule` in build.sem; packages with `requires` (D-34). Rules that shape a large program: import cycles are R603; an unused import is R404; two modules may not share a last path segment; a module may not take a standard module's name (R602). Impact: **None**, but the compiler's passes must form a strict layering.

**52 Namespaces and visibility. Supported.** Names are private unless exported; imported names are written `<module>.<name>`.

**53 Interfaces or traits. Missing.** `docs/test-suite.md` marks "Trait / Interface implementation" and "Trait bounds" as tested by `generics.sem`; that file shows only the `plain` constraint, so the coverage map overstates this. Impact: **Minor**; a compiler dispatches with enums. Recommendation: correct the coverage map; item 7's recommendation covers the practical need.

**54 Methods and associated functions. Partial.** Derived members only (`T.new`, `T.<field>`, `T.with`, `T.equals`, variant constructors, collection members). User code is free operations. Impact: **None**.

**55 Capability declarations and enforcement. Supported.** `capability` with `grants`, `uses`, `allows` in build.sem (D-41), `authority.approved` (D-53), run-time scope checks for computed arguments (D-38). Gaps for a compiler: an `fs.files` scope is a directory or a name pattern relative to the working directory, and `process.programs` is an exact program name, so a general-purpose compiler must be run from the project root with a scope such as `"./"` and a fixed C compiler name. Impact: **Minor**. Recommendation: decide how a tool that takes paths from its arguments states its authority (for example a scope taken from an argument position, approved at run time).

**56 Effect declarations and inference. Supported.** `effect` rows are compared with what the operation performs (R407); nothing is inferred into the source by design.

### Concurrency

**57 Async functions and tasks. Supported** under the JIT (threads, D-31). In an executable a task runs to completion at `start` (D-37). A compiler needs tasks only because every waiting target (`fs.readAll`, `fs.writeAll`, `process.run`) must be a `task` (verified: R410 "can wait, so it is a task"). Impact: **None**.

**58 Structured concurrency. Supported.** R510, R512, D-44, D-48.

**59 Task cancellation and joining. Supported** under the JIT; the native runtime's `refined_task_cancel` and `refined_task_join` are empty because tasks already finished. Impact: **None**.

### Operating system

**60 File and directory operations. Partial.** Evidence: `fs.openRead`, `openWrite`, `create`, `openAppend`, `read`, `write`, `close`, `readAll`, `writeAll`, `exists`, `remove`, `createDirectory`, `removeDirectory`, `listDirectory`, `entryCount`, `entryName`, `lock`, `unlock`. All host targets; R901 in an executable (verified on the lexer example). Further gaps: no rename, no size or modification time, no way to tell a file from a directory, no working directory, no path joining. Impact: **Blocker**. Recommendation: port `fs` to `native_runtime.c` first; add `fs.kind` (file, directory, absent) and `fs.modifiedAt` for incremental builds.

**61 Standard input, output, and error. Partial.** Output and error are inline in both backends. `console.readLine` is a host target; there is no read of all of standard input. Impact: **Minor** for a batch compiler. Recommendation: port `readLine`; add `console.readAll`.

**62 Command-line arguments. Partial.** `process.argumentCount` and `process.argument` work under `refined run PATH -- args` (verified with the lexer example). In an executable they are refused, and the generated entry is `int main(void)` (`native.py`), so arguments are not even received. Impact: **Blocker**. Recommendation: generate `main(int argc, char **argv)` and store them for the runtime.

**63 Environment variables. Partial.** `environment.get`, host only. Impact: **Minor** (the C compiler override `REFINED_CC`).

**64 Process execution. Partial.** `process.run` and `process.runCaptured` with an argument list and a deadline; host only; no working directory or environment for the child. Impact: **Major**: without it the compiled compiler can write C but cannot produce the executable in one command. Recommendation: port with `fs`.

**65 Binary file reading and writing. Partial.** Verified under the JIT: `buffer.appendByte` with 255, `buffer.toBytes`, and `fs.writeAll` write the single byte `ff`. Reading returns a `Bytes` that nothing can inspect (item 39). Host only. Impact: **Minor** with a text target.

### Safety

**66 Integer overflow semantics. Supported.** Checked arithmetic traps; `math.wrapping*Int64` and `saturating*Int64` exist; `tests/suite/programs/03-operators/trap-*.sem`. No wrapping forms for `Int32`.

**67 Bounds-checked indexing. Supported.** Typed errors `list.IndexOutOfRange` and `string.StringIndexError`, in both backends. The cost is under 49.

### Compiler data structures

**68 Recursive AST-friendly data structures. Partial.** Evidence: the `symbols` example builds `(1 + 2) * x` in a node list and evaluates it by recursion; a probe ran the same shape in an executable. Gaps: (a) a node with a variable number of children needs a child list that is complete before the node is stored (item 45), or first-child and next-sibling positions; (b) a later pass cannot annotate a node in place: it reads the node, builds a changed copy with `with`, and `set`s the whole node; (c) per-node side tables are not available in an executable, see 69. Impact: **Major**. Recommendation: with 69.

**69 Stable references or node IDs. Partial.** Evidence: D-60 positions. Three verified or read defects and limits:

1. **Stale positions are not detected (verified, JIT and executable).** A probe appended a node holding 7, called `Nodes.clear`, appended a node holding 9, and read the first node's old `NodeId`: it printed 9. `get` checks only `0 <= index < length` (`list_member`). D-60's sentence "a stale or foreign position is an error, never a stray read" is false after `clear`.
2. **Foreign positions (by reading).** Two lists of one indexed type accept each other's positions when in range, for the same reason.
3. **A position cannot leave its list (verified).** `Sizes.get` with a `NodeId` as the index of a `list.List Int64` is R403, and so is passing it to `math.addInt64`. The only side table keyed by a position is `map.Map NodeId X`, which checks but is host only.

Impact: **Major**. Recommendation: reject `clear` on a list type that has an index alias (R403); allow more than one `indexes` row so one alias positions several lists of one module (types by node, spans by node); add `<Alias>.toInt64` for printing and hashing.

**70 Dynamic collection resizing. Supported.** Lists double inline; maps and sets grow in the host. No shrink and no reserve. Impact: **None**.

## Self-hosting critical path

What the self-hosted compiler must do, and what stands in the way of each stage. "JIT" means the compiler runs under `refined run`; "executable" means the compiler compiled by itself.

| Stage | Needs | JIT today | Executable today | Blocking items |
| --- | --- | --- | --- | --- |
| Read build.sem and every module file | arguments, directory listing, `readAll`, `fromBytes` | works (lexer example) | refused: R901 | 60, 62, 39 |
| Tokenize | `byteAt`, `byte.*`, `advancePosition`, lists | works | works | none (22 and 49 for volume) |
| Parse rows into entities | lists of records, a shape table, text comparison | works | works, but no indexed table read | 30, 29 |
| Build the model (entities by name, facts by predicate) | `map.Map String X`, nested lists | works with flattening | refused: maps | 31, 45 |
| Resolve names across modules | maps, module ordering, import graph | works | refused: maps | 31, 32 |
| Type and signature checks | a library signature table, generics instances | works | refused: maps | 31, 7, 12 |
| Flow analyses (R5xx) | per-block sets, work lists, fixed points | works; sets of text are R403 | refused | 29 (no pop), 32, 45 |
| Emit code | a growable text buffer, number formatting | works | refused: `buffer` | 37, 41 |
| Write the output and build it | `writeAll`, `process.run` | works | refused | 60, 64 |
| Report diagnostics | `writeError`, exit code | works | works | none |

Reading the table: under the JIT nothing is refused, so the compiler can be written and tested today, slowly, against the Python compiler's output. The bootstrap cannot close until the native runtime has files, arguments, process execution, text buffers, `string.fromBytes`, and maps.

### What the self-hosted compiler should emit

**Recommendation: C source text**, one file per program, written with `fs.writeAll` and compiled together with `native_runtime.c` by the C compiler through `process.run`.

Reasons, from what the language can do today:

- **It needs only text.** The language can build text (`buffer`) and write it; it cannot usefully produce or read binary (items 39, 65), which rules out object files and makes WebAssembly binaries awkward.
- **The source form maps onto C almost one to one.** An operation is labelled blocks joined by `goto` and two-way branches; C has labels and `goto`, so no control-flow restructuring is needed. WebAssembly has only structured control flow and would need a relooper for the same blocks. Every value in an operation has a unique name (R411) and a stated type, so each `let` and each `result` becomes one C local with no temporaries to number and no SSA or phi construction, which LLVM IR text would require (or an alloca per value and trust in `mem2reg`).
- **No new dependency.** `refined build --kind executable` already requires a C compiler (`find_cc`: `cc`, `gcc`, `clang`, or `REFINED_CC`) and already ships a C runtime. LLVM IR text needs `clang` or `llc` specifically; on the analysis machine only `gcc` is installed, and it cannot read `.ll` files. The Python backend avoids that by linking LLVM in-process through llvmlite, which a self-hosted compiler cannot do.
- **The checked semantics are expressible.** Overflow traps map to `__builtin_add_overflow` and its siblings, records to structs passed by value, enums to a tag plus a union or the same wide struct the LLVM backend uses, the fallible convention to a returned struct `{failed, output, error}`, and `maxRecursion`, `maxIterations`, and stack checks to the runtime calls that exist.

Costs: the output cannot be compared textually with `refined emit-ir`, so correctness is checked by behaviour (every case in `tests/suite/programs` states its expected output and exit code); and C's undefined behaviour must be avoided in generated code (signed overflow, shifts, uninitialized locals). LLVM IR text remains a sound second backend once `clang` is an accepted dependency: it could be checked against `emit-ir` function by function.

The process-execution scope is then one line in the compiler's build.sem: `allows spawn process.programs "gcc"` (or the chosen compiler), which the present exact-name rule supports.

## Scale and ergonomics risks

**Size of the program.** Measured on a generated module: 2,000 calls in 100 operations take 26,842 rows, 13.4 rows per call including operation headers. One call with two arguments is 11 entity rows and one `do` step. `a + b * c` is 24 rows. A comparison and a branch to two new blocks is 17 rows. The existing examples total 8,069 lines; the lexer example alone is 3,428 (a 1,620-row tokenizer, a 1,000-row file driver with two operations and 58 calls, 781 rows of tests). The Python compiler's core that must be rewritten (`lexer`, `parser`, `model`, `shapes`, `semantics`, `flow`, `check`, `library`, `diagnostics`, `codegen`) is about 6,100 lines. Its 109-line lexer corresponds to a 1,620-row tokenizer, roughly 15 rows per line; at 15 to 30 rows per line the self-hosted compiler is an estimated **100,000 to 180,000 rows** before tests.

**Tests are mandatory volume.** An exported operation must state an invariant (R304) and every invariant must be verified by a test that calls the operation (R604). The examples' test files run from about 30% (`factorial`) to about 170% (`warehouse` pricing) of the module they test.

**Error handling volume.** About 25 rows per in-range index read (item 49); the lexer example has 31 labels in its two-operation driver, most of them error exits.

**No shared constants** (item 12) and **no layered generics** (item 7): each needed list, option, or map type is a named `typeInstance`, and each helper that would be generic is written once per type.

**Checker time is quadratic in module size (measured).** One module, `refined check --no-cache`:

| Rows | Calls | Check | Run (check, compile, execute) |
| --- | --- | --- | --- |
| 26,842 | 2,000 | 1.0 s | 2.0 s |
| 107,242 | 8,000 | 8.3 s | 11.9 s |
| 428,842 | 32,000 | 105 s | 111 s |

Four times the rows cost 8 and then 12.6 times the check. A profile of the middle case shows 36.9 million calls to `model.py` `predicate` under `facts`: each fact lookup scans an entity's rows, and lookups are repeated across a module's entities. Code generation is close to linear (a few seconds at 429,000 rows). A compiler split into 30 modules of 3,000 to 6,000 rows stays in the fast region (the 3,428-line lexer project checks in 0.3 s), but a few large modules will not. The self-hosted checker must not copy this structure: index facts by predicate once per entity.

**Recursion limits** are not a practical risk (item 18), provided a nesting bound is chosen. **Region sizing** is not a risk for capacity (the ceiling is free) but is for speed in executables (one `calloc` per allocation, item 43).

**The compiler's own speed under the JIT** is unmeasured at scale. Under the JIT every map and buffer operation crosses into Python through `refined_host`; a checker doing millions of map reads will be slow there, which is a second reason to move maps into the native runtime early.

**Naming.** Call entities are module-level and results are operation-level, all unique, with no shadowing. At about 60 calls per 1,000 rows (the lexer module has 92 in 1,620) this is manageable with a convention, but the convention has to be decided before writing begins.

## Prioritized roadmap

| # | Work | Closes | Size | Depends on |
| --- | --- | --- | --- | --- |
| 1 | Native host library, part 1: `fs` (open, read, write, close, `readAll`, `writeAll`, `exists`, `remove`, directories), `process.argumentCount`/`argument` with `main(int argc, char **argv)`, `time.Deadline`, `string.fromBytes`, `buffer.*` in `native_runtime.c`; narrow the R901 list in `native.py` accordingly; run the `lexer` example as an executable as the acceptance test | 37, 60, 62, 65 | L | none |
| 2 | Native `map.Map` (plain and `String` keys, insertion order) and `set.Set`; run the `symbols` example as an executable | 31, 32 | M | 1 (shared handle and region model) |
| 3 | Native `process.run`, `runCaptured`, `environment.get`, `console.readLine` | 61, 63, 64 | M | 1 |
| 4 | Position soundness: reject `clear` on an indexed list; amend D-60's wording; add a conformance check for stale and foreign positions | 69 (defects 1, 2) | S | none |
| 5 | Tree ergonomics: several `indexes` rows per alias, `<Alias>.toInt64`, `List.replace`, `Map.replace`, `List.removeLast`, `List.truncate` | 5, 6, 29, 45, 68, 69 | M | 4 |
| 6 | Trapping index targets (`List.at`, a trapping `byteAt`) as named twins of the fallible ones | 49 (volume), 67 | S | none |
| 7 | Text and bytes: `bytes.length`/`byteAt`/`slice`/`equals`, `string.compare`, `findFrom`, `fromByte`, `toFloat64`, `fromFloat64`, `buffer.appendHex` | 2, 33, 36, 39, 40, 41 | S | 1 |
| 8 | `constant` entity kind; `<table>.rowAt` and `<table>.length` | 12, 30, 22 (byte dispatch) | S | none |
| 9 | Checker performance: index facts per entity, remove the per-module quadratic scan | scale risk | S | none |
| 10 | Numeric completeness: `UInt64` and `Int32` arithmetic, bits, and conversions, or removal of inert types | 1, 15, 26 | S | none |
| 11 | Generics that layer: an operation instance at an enclosing type parameter, `typeParameter` on `operationType`; then sets of `String` and `forEach` over sets | 7, 19, 32, 35 | M | none |
| 12 | Write the compiler front end in the language (lexer, row parser, model, name resolution, type checks, flow analyses), one module per Python module, tested by comparing its diagnostics with `refined check --json` on every case in `tests/suite` | critical path | L | 5, 6, 8 (works under the JIT before 1 to 3) |
| 13 | C emitter and a driver that writes the file and runs the C compiler; tested by behaviour on every `expect: run` case | critical path | L | 12, 3 |
| 14 | Close the bootstrap: compile the compiler with the Python compiler into an executable, compile it again with itself, and require the two emitted C files to be identical | goal | M | 1, 2, 3, 13 |
| 15 | Native arena as chunked bump allocation; correct `docs/test-suite.md` on traits; fix `depth[op & 4095]` | 43, 53 | S | none |

Items 1 to 3 remove the blockers and can proceed while 12 is written under the JIT. Items 4 to 9 are small and each removes rows or risk from 12, so they are worth doing before it grows. Item 11 is not on the critical path: with native maps the compiler does not need layered generics.

## Probes run

All under a scratch directory outside the repository; none of the repository's files were changed.

| Probe | Result |
| --- | --- |
| `lexer` example: check, test, run with an argument | ok; 6 of 6 tests; 31 tokens written |
| `lexer` and `symbols` examples as executables | both refused, R901 (11 and 5 host targets) |
| `sum` example and a region, list, string, enum, `match` program as executables | linked and ran |
| List of lists: `get` the inner list, then `append` | R515, a view cannot be lent exclusively |
| `set.Set String`; `forEach` over a set | R403; R402 |
| Slice appended to a list with `give` | R514 |
| Generic record instance, `Option` of it, `map.Map String` of it | runs under the JIT; executable refused (map) |
| Generic operation calling a generic operation at `T` | R402 |
| `NodeId` passed as `Int64`; as the index of another list | R403 twice |
| `clear`, then read a position taken before it | reads the wrong node (9 for 7), JIT and executable |
| `maxBytes` of 1 TiB | accepted, runs |
| Recursion depth | 1,000,000 under the JIT, trap near 1,570,000; 1,900,000 in an executable |
| Byte 255 written through `buffer` and `fs.writeAll` | file holds `ff`; `fs.readAll` and `fs.writeAll` as calls are R410 (they wait, so they are tasks) |
| One module of 26,842, 107,242, and 428,842 rows | check 1.0 s, 8.3 s, 105 s |
| WebAssembly and object builds of the core probe | written (1,487 and 1,667 bytes) |
