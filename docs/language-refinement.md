# Language refinement notes

Status: design accepted by the project owner on 2026-11-13 (P-1, P-2, and
LR-01 through LR-23, with LR-19 superseded by LR-20). Part 2 (LR-24 to LR-41)
and Part 3 (LR-42, amendments after an adversarial review) were added
afterwards by delegation and have not been reviewed by the owner. Part 3
overrides earlier text where they conflict. Parts 4 to 6 record the
implementation, which started the same day: Part 5 removed the bridge to the
earlier compiler and dropped backwards compatibility at the owner's request, and
Part 6 removed the earlier compiler.

**This file is the language's normative design.** With the earlier compiler and
its spec removed (Part 6), the decisions here, the shape table
(`semanticscript/compiler/refined/shapes.py`, rendered as
`docs/refined-grammar.md`), and the checker together define the language.
Started: 2026-11-13. Baseline: `main` at `b6aa5c7`. Section references written
as `§n` point to `docs/LANGUAGE.md` as it was at that commit (removed in Part 6;
still in git history).

## Purpose

A place to collect and settle changes to the language itself: syntax, scoping,
typing rules, and the effect model. Compiler and tooling defects go in GitHub
issues; they appear here only when the fix is a language rule.

## How to use this file

Each item has an id (`LR-nn`), a status, and four parts:

- **Problem**: what hurts, in one or two sentences.
- **Evidence**: a program, measurement, or spec section that shows it.
- **Options**: the candidate changes, with their costs.
- **Decision**: empty until we agree. When decided, add the date and move a
  one-line summary to the decision log at the bottom.

Statuses: `open` (not discussed), `discussing`, `decided`, `dropped`. A decided
rule is implemented when the checker enforces it; Part 5 lists what is
enforced.

"Leaning" marks a preference from the review, not a decision.

Worked examples anywhere in this file follow the full skeleton from LR-18,
LR-20, LR-30, and LR-31, as amended by Part 3. The complete examples are the
projects in `docs/refined-examples/`, checked by the refined front end (Part 4).

"By delegation" marks a decision made on behalf of the project owner from P-1
and P-2, after the owner asked for design questions to be decided that way.
Any of them can be overturned; record the reversal in the decision log.

## Principles (decided)

- **P-1 Explicit over terse** (2026-11-13). Source is verbose and 100% explicit.
  Agents write the code, so the human preference for implicit forms is ignored.
  Row count is not a cost we optimize.
- **P-2 Explicit construction is enforced** (2026-11-13). Nothing is implied and
  every stated fact is checked. Concretely:
  1. No defaults. A fact that affects meaning must be written; a missing row is
     an error, not a default.
  2. Fixed shape. Every predicate has an exact token count and a token class or
     closed value set per position. Extra, missing, or out-of-set tokens are
     errors.
  3. No silent duplicates. A single-valued fact appears exactly once.
  4. No unchecked statements. If a row states a type, effect, owner, or name, the
     compiler verifies it against the rest of the program.

## Constraints we keep

- One row shape: `<subject> <predicate> <payload>`. No nesting, no expressions.
- The split (`do` → call, `start` → task, `defer` → cleanup) stays (§34.4).
- Effects, failures, cleanup, memory, and authority stay source data.
- §34 (minimal core) is the direction. A refinement should shrink or hold the
  keyword set, not grow it, unless it removes more than it adds.
- Every change moves spec, grammar, compiler, tests, and editor together
  (the change protocol in CONTRIBUTING.md).

## Items

### LR-01 Call declarations sit far from the steps that use them

Status: decided

- **Problem**: An operation's step list says `do recCall`, but the call's target,
  arguments, and outputs are declared in a separate entity elsewhere in the file.
  Reading one operation means jumping between its steps and every call it uses.
  Flat is not the same as local.
- **Evidence**: `examples/factorial.sem`: `factorial` has 5 steps and 4 call
  entities declared after it. `branch if isBase` uses a name that only appears as
  an `out` row on `baseCheck`.
- **Options**:
  1. Keep the model; make canonical ordering (§22) place each call entity
     directly after its first use, and have `fmt` enforce it.
  2. Allow an inline step form for single-use calls, as non-canonical sugar that
     `fmt` expands (same mechanism as `ifOut`, §13).
  3. Leave source as is and rely on tooling (`slice`) for the local view.
- **Decision** (2026-11-13, by delegation): option 1. No inline form, because P-1 allows one
  spelling per fact. Canonical order (§22) places each call, task, and cleanup
  entity directly after its owning operation, in order of first use.
  `fmt --check` is part of the strict gate, so non-canonical order is an error.

### LR-02 Call and task names are global

Status: decided

- **Problem**: A call is tied to its operation by an `in` row, but its name lives
  in one program-wide namespace. Every call in a program needs a unique name.
- **Evidence**: Names like `setMeDisplayNameCall` in
  `apps/taskforge-web/src/main.sem`. Two modules with a private `helper` fail to
  compose when the second owns calls. The SSRF and path-traversal validators can
  be bypassed by declaring the same binding name in another operation.
- **Options**:
  1. Scope call, task, cleanup, and binding names to their owning operation.
     Rows keep the same shape; resolution becomes `(operation, name)`.
  2. Keep global names but require an operation prefix by convention and lint it.
- **Decision** (2026-11-13, by delegation): option 1. Call, task, cleanup, label, and binding
  names resolve as `(owning operation, name)`. The owner is already explicit in
  the required `in` row, so nothing becomes implicit. Two operations may reuse
  a name; within one operation a name is unique across all of those classes.

### LR-03 Row count for ordinary programs

Status: dropped (P-1: verbosity is intended; none of the options below apply)

- **Problem**: Simple programs take many rows, which costs reading time for
  people and tokens for agents.
- **Evidence**: hello world is 31 lines; recursive factorial with three
  assertions is 127; `taskforge-web`'s main file is 4,674 lines for 18
  operations. §21 already defines a row-count adoption gate.
- **Options**:
  1. Make more metadata optional on private entities (`memory`, `async`,
     `purpose`, `invariant`) with documented defaults.
  2. Drop restated facts (see LR-05).
  3. Promote the compact profile (§23) to the authoring default and treat the
     canonical form as what `fmt` and tools produce.
- **Decision**:

### LR-04 Scope at a label depends on which jumps reach it

Status: decided

- **Problem**: Control flow is `goto` only. Whether a binding exists at a label
  depends on the paths that reach it, and the language has no stated rule for it.
- **Evidence**: A value bound on one branch and used after a label that the other
  branch also reaches passes `check --strict` and then fails in LLVM. §25 (formal
  scope model) does not define definite assignment.
- **Options**:
  1. Add a definite-assignment rule to §25: a binding is in scope at a step only
     if every path from the operation's entry to that step binds it. Violations
     are a check error.
  2. Add the planned `repeat`/`each` sugar (§27) so most programs need fewer
     hand-written labels. This reduces the problem but does not replace option 1.
- **Decision** (2026-11-13, by delegation): option 1. §25 gains a definite-assignment rule: a
  binding is in scope at a step only if every path from the operation's entry
  to that step binds it; anything else is a check error. The same pass
  requires every path to end in a `return` whose value matches the `out` type.
  Option 2 is rejected as sugar (see LR-15). If iteration gets a construct, it
  is a real one designed under LR-10, with one spelling.

### LR-05 `arg` rows restate the type

Status: decided

- **Problem**: `arg left Int64 n` repeats a type the binding and the target's
  signature already fix. A restated fact can drift, and today the restatement is
  not compared with the binding's real type.
- **Evidence**: Passing an `Int64` binding in an `arg text String n` row is only
  rejected in code generation, with an LLVM-level message.
- **Options**:
  1. Keep the type token and make it a checked assertion: it must equal both the
     binding's type and the parameter's type.
  2. Make the type token optional; `fmt` fills it in for the canonical form.
  3. Remove it from `arg` rows.
- **Decision**: option 1, by P-1 and P-2.4 (2026-11-13). The type stays and is
  checked against both the binding and the parameter.

### LR-06 Prose contracts that are half-checked

Status: decided

- **Problem**: `purpose` and `invariant` are required English strings. One rule
  (SS1880) pattern-matches the English against the code, which makes ordinary
  wording a compile error.
- **Evidence**: "Always returns ExitCode 0" rejected the getting-started example
  and currently fails `apps/taskforge-tui`. §34.3 already plans to demote these
  rows to typed comments.
- **Options**:
  1. Follow §34.3: prose becomes typed comments, never checked.
  2. Split the two uses: free prose in comments, plus a small closed set of
     machine-checked contract rows (for example a `returns` fact with a literal).
- **Decision** (2026-11-13): neither option as written. `purpose` and
  `invariant` stay as rows, because they carry product context that code cannot
  express and rows travel with `slice` output where comments may not. This
  departs from §34.3, which demoted them to typed comments. The rules:
  1. **Where required.** `purpose` is required on entities that carry product
     meaning: operations, modules, capabilities, records, errors, and anything
     exported. `invariant` is required on operations only, because an invariant
     must be backed by a test (rule 3) and only behavior can be tested; it is
     allowed but optional elsewhere. Neither is required on calls, tasks,
     cleanups, or aliases of primitive types. (Narrowed 2026-11-13 while writing
     the worked example: a module or error invariant restates structure and
     would be filler under rule 5.)
  2. **`purpose` is declared intent.** The compiler treats it as narrative and
     never as fact. No rule reads its English.
  3. **`invariant` is a claim and must be checked** (P-2.4). Each invariant
     carries an id, and at least one test must reference that id. The compiler
     enforces that every invariant has a referencing test; it does not read the
     English.
  4. **Staleness.** When an entity's structural rows change and its `purpose` or
     `invariant` rows do not, tooling flags the entity for the author to
     re-confirm or rewrite the prose.
  5. **No filler.** Text that restates the entity name or is trivially short is
     an error.
  6. **SS1880 is removed.** No rule pattern-matches English against code.
- **Still to design**: the row shape for an invariant id and for a test's
  reference to it; how "re-confirmed" is recorded for rule 4; the threshold for
  rule 5.

### LR-07 Where a call target's effects are declared

Status: decided

- **Problem**: The language says no operation performs an effect it did not
  declare, but it does not say where the effects of a library target such as
  `console.writeLine` are stated for the static check.
- **Evidence**: An operation that calls `console.writeLine` with no `effect` and
  no `uses` row passes `check --strict`. The project's own negative example
  `capability_ungranted_use` is not blocked. Any `imports` row plus an unresolved
  `uses` name skips coverage checking.
- **Options**:
  1. Every callable target carries its effects in its signature (`.semsig`, §26).
     An operation's effective effects are its own plus those of everything it
     activates, and all must be covered by `uses`.
  2. Additionally require that every `uses` row resolves to a declared or
     imported capability; an unresolved name is an error, never a skip.
- **Decision** (2026-11-13, by delegation): both options. Every callable target states its
  effects in its signature. An operation's effective effects are its own plus
  those of everything it activates, transitively. Each must appear as an
  `effect` row on the operation and be covered by a `uses` row naming a
  capability that grants it. A `uses` name that does not resolve is an error in
  every mode, with or without imports.

### LR-08 Mutability vocabulary

Status: decided

- **Problem**: The spec says only `mutability mutable` storage may be reassigned,
  but the value set for the row is not closed.
- **Evidence**: `mutability constant`, `mutability Immutable`, or no mutability
  row all allow `set`.
- **Options**:
  1. Closed set `mutable | immutable`, default `immutable`, anything else is a
     parse error.
- **Decision**: closed set `mutable | immutable`, and the row is required with no
  default, by P-2.1 and P-2.2 (2026-11-13).

### LR-09 Per-predicate arity and value sets

Status: decided

- **Problem**: Rows are accepted with extra tokens, missing tokens, or values
  outside the intended set. A flat grammar is only uniform if every predicate has
  a fixed shape.
- **Evidence**: `main is operation extra junk`, `main async banana`, a one-token
  `effect` row, a call with no `in` row or two of them.
- **Options**:
  1. Give every predicate in §5 a schema: token count (or range) and an enum or
     token class per position. The parser enforces it from one table, which also
     drives the editor grammar and `GRAMMAR.md`.
- **Decision**: option 1, by P-2.2 (2026-11-13). The audit below measures how far
  the current compiler is from it.

### LR-10 Collections, loops, and generics

Status: decided (2026-11-13, by delegation; see LR-24 and LR-25 in Part 2)

- **Problem**: v0.3 has no collections, structured iteration, or type
  parameters (§27). Real programs reach for raw `c.malloc` and `c.fopen`, which
  sidestep the safety model the language is built around.
- **Evidence**: `check --strict` on `apps/taskforge-web` reports 14 raw-heap
  findings; `apps/taskforge-tui` uses `c.fopen` and `c.malloc`.
- **Options**: to be written. Starting points are the planned shapes in §27 and
  `design-bounds-carrying-buffers.md`.
- **Decision**:

### LR-11 Lexical edge cases

Status: decided

- **Problem**: A few lexical rules are unstated or inconsistent.
- **Evidence**: Tokens split on space and tab only, while blank-line detection
  uses Unicode whitespace, so a trailing non-breaking space becomes part of a
  name. `"x"y` splits silently into two tokens. Raw control bytes are allowed
  inside strings although the `\0` escape is rejected.
- **Options**:
  1. State in §2: source is UTF-8; the only whitespace is space and tab; any
     other whitespace or control character outside a string is an error; a string
     must be followed by whitespace or end of line.
- **Decision** (2026-11-13, by delegation): option 1 as written, plus: raw control bytes
  inside a string are an error (use `\xNN`), and a quote character anywhere
  but the first and last position of a token is an error.

### LR-12 Integer conversion and shift semantics

Status: decided

- **Problem**: The spec says conversions are checked and a trap beats undefined
  behavior (§33), but two cases are not pinned down.
- **Evidence**: `convert.toUInt32` of a negative `Int64` returns 4294967295
  instead of trapping. A shift by a computed amount of 64 or more yields an
  undefined value.
- **Options**:
  1. State in §33: signed to unsigned traps on a negative value at every width;
     a shift amount at or above the bit width traps (or is defined to yield 0 /
     sign fill; pick one).
- **Decision** (2026-11-13, by delegation): both trap. Signed to unsigned traps on a negative
  value at every width, including equal widths. A shift amount below zero or at
  or above the bit width traps. A trap is the only result consistent with §33;
  a defined-but-surprising value would be an implicit behavior.

### LR-13 Order of the §34 migration

Status: decided

- **Problem**: §34.5 lists a migration order, but several items above interact
  with it (LR-06 metadata, LR-07 capability surface, LR-09 predicate table).
- **Options**: to be written once the items above are decided.
- **Decision** (2026-11-13, by delegation): the enforcement plan below runs first. §34's
  keyword demotions then proceed in the §34.5 order, with two changes: the
  metadata step is cancelled (LR-06 keeps `purpose` and `invariant` as rows),
  and each demoted domain must arrive with a shape-table entry and a
  strict-clean example, so the audit gate covers it from day one.

### LR-14 The compact authoring profile

Status: decided

- **Problem**: §23 lets authors omit a row's subject and has `fmt` restore it.
  That is an implicit form, and it means every tool must accept two spellings
  of one program.
- **Decision** (2026-11-13, by delegation): removed. The canonical form is the only accepted
  source. §23 and the compact round-trip gate in §21 are deleted from the
  spec; the compiler rejects subject-less rows.

### LR-15 Non-canonical sugar forms

Status: decided

- **Problem**: Several forms are accepted as input and rewritten by `fmt`:
  the `ifOut`, `ifValue`, and `else` branch guards, the compound `defer`, and
  `async` on a `call`. Each is a second spelling of something the canonical
  form already says.
- **Decision** (2026-11-13, by delegation): all become errors. One spelling per fact (P-1). A
  one-time migration command rewrites existing sources to the canonical form
  before the compiler starts rejecting them; after that the rewrite code is
  deleted.

### LR-16 Branching: implicit fallthrough

Status: decided (2026-11-13, by delegation; amended by LR-18)

- **Problem**: Control flow has two implicit edges. A `branch` names only the
  taken target; the not-taken path is "the next row". A label can be entered by
  falling into it from the row above. Inserting or moving one row can change
  where control goes without any row saying so.
- **Evidence**: `main branch if flag goto skip` followed by unrelated rows; the
  else-path is positional. `main at base return one` in `examples/factorial.sem`
  is reachable only by jump, but nothing in the grammar says a label cannot be
  fallen into.
- **Proposal**: make an operation's steps an explicit control-flow graph.
  1. A block starts at the operation's first step or at a label and ends in
     exactly one terminator: `return`, `goto`, or `branch`.
  2. `branch` names both targets: `OP branch <guard> goto <label> else goto
     <label>`. No fallthrough out of a branch.
  3. Falling into a label is an error. The row before a label must be a
     terminator.
  4. Every fallible `do` is followed immediately by its `branch ifError`.
  5. A chain of `ifVariant` tests on an enum must cover every variant, or end in
     a branch whose `else` target is declared as the default.
  6. Every backward `goto` (a loop) belongs to an operation that states
     `maxIterations <n>` or `maxIterations unbounded` with a `because` reason.
  7. No structured loop constructs. Structured loops are a human reading aid;
     an explicit graph is the more exact form for agents and for the checker.
     This narrows LR-10 to collections and generics.
- **Why**: the source becomes the same graph the compiler lowers to, so
  definite assignment and return-on-every-path (LR-04) are exact, and a one-row
  patch cannot silently re-route control.
- **Decision**:

### LR-17 Concurrency: tasks that do not run concurrently

Status: decided (2026-11-13, by delegation)

- **Problem**: The source can state concurrency that does not happen.
- **Evidence** (compiler at `b6aa5c7`): `start` runs the task's call to
  completion on the spot and sets a state flag; `join` and `poll` only change
  the flag; `cancel` sets a flag after the work has already finished;
  `ifPending` is never true. `readShared`/`setShared ... protectedBy <token>`
  ignore the guard token. Real asynchrony exists separately as the
  `standard.async` library on a single-threaded libuv loop, unconnected to the
  `start`/`join` keywords. Under P-2 these are unchecked statements.
- **Proposal**: one honest model, in three layers.
  1. **Ownership of tasks.** A task is owned by the operation that starts it.
     On every path to a `return`, each started task has been joined or
     cancelled. The check uses the same control-flow graph as LR-16. `detach`
     is removed; long-lived work is started by an operation that itself lives
     that long.
  2. **Cooperative tasks on one thread.** `start` schedules the task on the
     event loop and returns. Other tasks run only at explicit suspension rows
     (`join`, `poll`, and awaiting library calls). Every point where other code
     can run is a row in the source. There are no data races in this layer, so
     `mutex`, guard tokens, and `protectedBy` are removed from the language
     rather than kept as no-ops.
  3. **Parallel workers without shared memory.** Real threads are isolated
     workers. A worker receives its inputs by value or by ownership transfer
     (`takesOwnership`), returns a value, and talks to others only through
     channels. A worker's `uses` rows list its capabilities at spawn, so a
     forked worker can do only what it was granted. No shared mutable state
     crosses a worker boundary; `sharedState` is per-thread.
  4. **Processes.** No `fork`. Starting another process is a library call under
     a `process.spawn` capability.
  5. **Until layer 2 exists**, the compiler rejects `task` entities and the
     lifecycle steps with a "not implemented" error instead of running them
     synchronously.
- **Why**: P-2 forbids statements the backend ignores, and code proven on a
  backend where races cannot happen would break silently when a concurrent
  backend arrives.
- **Decision**:

### LR-18 Uniformity: one shape, one word, one spelling

Status: decided (2026-11-13, by delegation)

- **Problem**: Reviewing the first refined example for how predictable it is to
  write and read (for a small or large model) found forms where meaning is
  carried by absence, by position, or by a word that means two things. Each one
  is a place where a model has to guess.
- **Evidence**: the sum-to-five example written for LR-16.
  - Empty sets are written by leaving rows out (no inputs, no result, cannot
    fail), while `memory heap no` and `async no` state their negatives.
  - Only the first row of a block names the block; the rest belong to it by
    position. The entry block has no name at all.
  - `in` means "owned by" on a call and "input parameter" on an operation.
    `out` means "return type" on an operation and "bind a result" on a call,
    with different token counts.
  - Yes/no facts are spelled `yes`/`no`; Bool literals are `true`/`false`.
  - With two-target branches, `ifFalse` is a second spelling of `if`.
  - `RESERVED_WORDS` has 218 entries, including `limit`, `value`, `type`,
    `error`, `output`, `owner`, `timeout`, `target`, and `scope`. A model will
    reach for those as variable names. Writing the example hit this with
    `limit`.
  - `maxIterations` sat on the operation, so with two loops it would not say
    which one it bounds.
- **Rules**:
  1. **Fixed skeleton.** Every entity of a kind carries the same header
     predicates in the same order. An empty set is written `none`:
     `main input none`, `printTotal out none`, `pastLimitCheck catch none`,
     `factorial effect none`, `factorial uses none`. The checker verifies each
     `none` (for example `catch none` against a target that cannot fail).
  2. **Every step row names its block.** All step rows have the shape
     `<operation> at <label> <step> <payload>`. The unlabelled step-row class
     is removed. The entry block is labelled `entry`. A block's rows are
     contiguous. This amends LR-16.1.
  3. **One word, one meaning.** On operations, parameters are `input <name>
     <type>` and the result is `output <type>`. `in` means only "owned by" and
     `out` means only "bind a result".
  4. **One boolean spelling.** Yes/no facts take `true` or `false`:
     `main async false`, `main memory heap false`. The spec allows only
     `yes|no` for `memory heap`, so it is a boolean like the others (settled
     2026-11-13).
  5. **`ifFalse` is removed.** Swap the two targets of `if`.
  6. **Only literals are reserved** (`true`, `false`, `nil`, `none`). Every
     position in a row has a fixed class from the shape table, so a name cannot
     be mistaken for a predicate.
  7. **Loop bounds attach to the block.** `<operation> label <label>
     maxIterations <n>` bounds how many times control may enter that block in
     one run of the operation; `unbounded` requires a `because` row. This
     amends LR-16.6.
  8. **No member-style dots in references.** A test names an invariant as two
     tokens: `verifies main sumIsFifteen`.
- **Measuring it**: these rules come from inspection, not from a measured
  perplexity. The plan gains an evaluation step: have a small and a large model
  write a fixed set of programs from the spec alone, and track the first-try
  `check --strict` pass rate and which rules they break.

### LR-19 Who frees ordinary values

Status: superseded by LR-20 (2026-11-13). The rule "an operation frees what it
made unless it returned it" survives; LR-20 makes the region a named, declared
owner instead of an unnamed per-call one.

- **Problem**: The spec splits memory into three tiers but only defines two.
  Stack locals are automatic. External resources and raw heap are author-tracked
  through `owns`, `cleanedBy`, `cleanup`, and `defer`, and the compiler checks
  them. Ordinary heap values (`String`, records, enums built at run time) are
  "compiler-managed" with the mechanism "deferred" (§10.6, §29 #14).
- **Evidence**: The runtime gives these values a "process-lifetime allocation
  model" (`ss_sqlite.c`, `ss_string.c`): strings from `string.concat`,
  `convert.toString`, and `sqlite.columnText` are allocated and never freed. A
  long-running server leaks on every request. `memory stack` and `memory max`
  rows may be omitted, in which case "the runtime default applies" (an implicit
  default under P-2).
- **Proposal**:
  1. Every operation has an implicit-free but explicitly declared region for the
     ordinary values it creates. The region is released when the operation
     returns. A returned value is moved into the caller's region.
  2. The declaration is a required row, for example `OP memory region
     perCall`, with `perCall` the only value until others are designed. An
     operation that creates no heap values states `OP memory heap false` and
     the compiler verifies it.
  3. `memory stack` and `memory max` are required rows or are removed; they do
     not default.
  4. Raw `c.malloc`/`c.free` stay available only to standard-library modules.
     Application code uses regions and owned resources.
- **Why**: deterministic, no garbage collector, no reference counts, and the
  rule fits in one sentence: an operation frees what it made when it returns,
  unless it returned it.
- **Decision**:

### LR-20 Explicit memory and ownership

Status: decided (2026-11-13, accepted by owner)

#### How it works at `b6aa5c7`

Three tiers. Stack locals are automatic. Resources (handles) are tracked with
`owns` + `cleanedBy` on the acquiring call, a `cleanup` entity, and a `defer`
step. Ordinary heap values (`String` and friends built at run time) are
"compiler-managed" and in practice never freed.

Probes against `check --strict`, mutating `examples/defer_ownership_release.sem`
(audit scripts since removed with the earlier compiler, Part 6):

| Probe | Result |
| --- | --- |
| `owns` + `cleanedBy` but no `defer` | rejected (SS1503) |
| `owns` with no `cleanedBy` | rejected (SS3900) |
| `cleans` a name no call `owns` | rejected |
| Return an owned handle | rejected (SS3044C: ownership cannot be returned at all) |
| Same cleanup deferred twice | rejected (SS3044B) |
| Use after `takesOwnership` | rejected (SS1564) |
| Store an owned handle in module storage | **accepted** (escapes its cleanup) |
| `defer` registered before the resource is acquired | **accepted** |
| A path returns before the `defer` is registered | **accepted** (leak on that path) |
| `takesOwnership`, old owner's cleanup still deferred | **accepted** (double release) |
| Cleanup worker call takes no argument | **accepted** (it cannot touch what it "cleans") |
| Owned handle passed to a call with no borrow or transfer row | **accepted** (lending is implicit) |

Other findings:

- `memory heap no` is checked against five target names only (`c.malloc`,
  `c.calloc`, `c.realloc`, `memory.allocateMemoryBytes`, `buffer.create`).
  `string.concat`, `convert.toString`, and every other allocating call pass.
  The row is also optional.
- Strings made at run time use a "process-lifetime allocation model" in the
  runtime: allocated, never freed.
- `borrows`, `mayEscape`, `takesOwnership`, `consumes yes`, `region`,
  `allocateIn`, and `releaseRegion` appear in no example, no app, and no
  standard-library module. Only three `.semsig` files mention `borrows`.
- The 29 `examples/defer_*.sem` files are one program under 29 names
  (`defer_memory_free`, `defer_region_release`, `defer_borrow_return`, ...). The
  "resource" in each is an `Int64` constant and the cleanup sets a module
  variable.
- The spec says raw `c.malloc`/`c.free` is never app source. `taskforge-web` has
  14 `c.malloc` calls and `taskforge-tui` has 4 plus 2 `c.fopen`; they are
  warnings.
- Transfer has two spellings (`arg ... consumes yes` and `takesOwnership`), and
  `borrows X` and `lifetime X` state the same fact twice.

#### The refined model

One rule: **every value that needs release has exactly one named owner at every
step, and every acquisition, loan, transfer, and release is a row.** The checker
follows each owned value along every path of the control-flow graph (LR-16).

1. **Three value classes, stated per value.**
   - *Plain*: numbers, `Bool`, and fixed-size records and enums. Copied. No
     owner.
   - *Region-owned*: every heap value (`String` built at run time, buffers,
     collections). Its owner is a named region.
   - *Operation-owned*: resources (files, databases, sockets). The owner is the
     operation, which must release it.
2. **Every call states the owner of its result.** One skeleton row replaces
   `owns`: `<call> ownedBy none | <region> | <operation>`. The checker verifies
   it against the target's signature. `ownedBy <operation>` requires a
   `cleanedBy` row (LR-31 allows `cleanedBy none` when every path gives or
   returns the value).
3. **Regions are declared entities with a stated lifetime.**
   ```
   scratch is region
   scratch in greet                # owned by this operation
   scratch strategy arena
   scratch capacity 4096           # bytes, or `unbounded` with a `because` row
   scratch released atReturn       # atReturn | atProcessExit
   ```
   `atReturn` means the compiler releases the region at every `return` of the
   owning operation. `atProcessExit` is the stated form of today's silent
   behavior and is only allowed on regions owned by the entry operation.
4. **Allocation is visible as an argument.** A target that allocates takes a
   `Region` parameter. There is no hidden allocator. To return a heap value, an
   operation receives the caller's region as an input and states
   `<operation> outputOwner <thatInput>`.
5. **Every parameter and argument states how the value is passed.**
   - Operation: `<op> input <name> <type> value | borrowed | owned`.
   - Call: `<call> arg <slot> <type> <value> copy | lend | give`.
   - The checker matches them (`copy`/`value`, `lend`/`borrowed`,
     `give`/`owned`). LR-31 adds a fourth pair for exclusive loans,
     `lendMutable`/`borrowedMutable`. This is the single spelling for transfer; `consumes yes`
     and `takesOwnership` are removed.
6. **Linear rule for operation-owned values.** On every path from acquisition
   to a `return`, the value is released exactly once, given exactly once, or
   returned as an owned output. Concretely:
   - A deferred cleanup must be registered on the success target of the
     acquiring call's `branch ifError`, before any other use, and on no path
     where the value was not acquired.
   - A value with a deferred cleanup cannot be given or returned. A value that
     is given or returned on some paths is released on the others by an
     explicit `do` of its release call.
   - The cleanup's worker call must take the cleaned value as an `arg ... give`.
7. **Ownership can be returned.** `<op> output <type>` plus
   `<op> outputOwner caller` hands a resource to the caller, whose call row must
   then state `ownedBy <callerOperation>` and a `cleanedBy`. This removes the
   reason apps reach for raw handles.
8. **Borrowed values stay put.** A `borrowed` input or a view cannot be stored,
   returned, or given. A view names its source with one row, `borrows <value>`;
   `lifetime` and `mayEscape` are removed because a view may never outlive its
   source.
9. **No owned value in module storage.** Module storage and shared state hold
   plain values only. Long-lived resources are owned by the entry operation and
   lent downward.
10. **`memory heap` is checked exactly.** `true` if and only if the operation
    owns a region or receives one. `memory stack` and `memory max` are required
    rows.
11. **Raw allocation is an error in application source.** `c.malloc`, `c.free`,
    `c.fopen` and the pointer primitives are usable only inside standard-library
    modules, which wrap them as region-taking or resource-returning operations.

#### Worked example

```
greet is operation
greet purpose "Build a greeting for one name"
greet invariant startsWithHello "The result starts with Hello"
greet input name String borrowed
greet input resultRegion Region borrowed
greet output String
greet outputOwner resultRegion
greet raises none
greet effect none
greet uses none
greet memory heap true
greet memory stack 256
greet memory max 4096
greet async false
greet let prefix immutable String "Hello, "
greet at entry do joinText
greet at entry return ok greeting

joinText is call
joinText in greet
joinText invokes string.concat
joinText arg left String prefix lend
joinText arg right String name lend
joinText arg region Region resultRegion lend
joinText out greeting String
joinText ownedBy resultRegion
joinText borrows none
joinText catch none
```

`greet` allocates nothing of its own: the result lives in the region its caller
passed in, and the caller's region declaration says when that memory is freed.

#### Corpus work this implies

- Replace the 29 identical `defer_*` examples with examples that each exercise
  one rule above against a real resource or region.
- Add an accepted example and a rejected example for every row in the probe
  table.
- Port the standard library's string, JSON, and SQLite text results to take a
  region, and remove the process-lifetime allocation model.

### LR-21 Comments and extra context

Status: decided (2026-11-13; item 4 overturned by the owner the same day:
comments stay)

#### How it works at `b6aa5c7`

Context can be written four ways:

1. **Plain comments.** `#` at column 1, or trailing after a row. Free text,
   ignored by the checker, kept by `fmt`, included in `slice` output.
2. **Typed comments.** `# <tag>: text` with 17 fixed tags (`rationale`,
   `warning`, `agent`, `memory`, `concurrency`, `timing`, `failure`, `security`,
   `dependency`, `observability`, `test`, `todo`, `purpose`, `invariant`,
   `note`, `risk`, `example`). `check --json` returns them with line numbers.
3. **Metadata rows** on any entity: `purpose`, `invariant`, `note`,
   `rationale`, `risk`, `example`, `tag`, `deprecated`, `owner`. Labels take
   them through `<op> label <label> <predicate> "<text>"`.
4. **Reason strings inside rows**: `discards "<reason>"`, `because "<reason>"`.

Probe (`comments.sem`, a hello world with one comment of each kind):

- A plain comment written between two rows of `main` is moved by `fmt` to above
  `main is operation`. It no longer sits next to the row it explained.
- A comment after an entity's last row is attached to the next entity.
- `# madeUpTag: ...` is accepted silently as a plain comment, so a misspelled
  tag is lost without a diagnostic.
- `slice` carries all comments and metadata rows for the entity. (An earlier
  note in this discussion said comments might not travel with slices; that was
  wrong.)

Corpus:

- Typed comments: 0 uses in `examples/` and in `apps/taskforge-web`.
- Metadata rows other than `purpose`/`invariant`: `rationale` 19 and `risk` 10
  across the apps; `note`, `example`, `tag`, `deprecated`, and `owner` 0.
- 233 examples open with `# Expected output: ...`. The example runner does not
  read it, so the stated output is never compared with the real output.

Problems under P-1 and P-2:

- Five tags exist both as rows and as typed comments: two spellings of one fact.
- A comment's subject is inferred from where it sits, and `fmt` changes where it
  sits.
- Comments get none of the LR-06 protections (staleness flag, filler check).
- The `agent` tag is a channel for instructions to whichever model reads the
  file next. Text in source should describe the code, not direct the reader.

#### Decision

Two mechanisms with different jobs:

- **Comments are free space.** Authors, which here means agents, fill them as
  they see fit. They carry no machine meaning and are never checked.
- **Context rows are structured.** They have a subject, a closed vocabulary, and
  the LR-06 protections. Anything a tool must act on is a row.

1. **`#` comments stay**, both full-line and trailing, with no restriction on
   content. (The first version of this decision removed them. The owner
   overturned that: comments exist for agents to use freely.)
2. **A comment has no tags.** The typed-comment grammar is removed, so there is
   one spelling for structured context (a row) and a misspelled tag can no
   longer be silently lost. `# todo: ...` is still a perfectly good comment; it
   is just not parsed.
3. **A comment stays where it was written.** A full-line comment belongs to the
   next row; a trailing comment belongs to its own row; comments after the last
   row belong to the file. `fmt` never moves a comment relative to its row, and
   when canonical ordering moves a row, its comments move with it. This fixes
   the hoisting found in the probe.
4. **Comments travel.** `slice` and other views that show a row show its
   comments.
5. **Comments are never evidence.** No check passes or fails because of a
   comment, and tools present them as author notes, not as facts about the
   code.
6. **Closed set of context rows:**

   | Row | Meaning |
   | --- | --- |
   | `<e> purpose "<text>"` | Why it exists. Unchecked intent (LR-06). |
   | `<e> invariant <id> "<text>"` | A claim backed by a test (LR-06). |
   | `<e> rationale "<text>"` | Why it is built this way, so a later author does not "fix" a deliberate choice. |
   | `<e> risk <category> "<text>"` | A known hazard. Category is one of `security`, `failure`, `timing`, `concurrency`, `memory`, `data`. |
   | `<e> note "<text>"` | Context that should survive and be staleness-checked but fits none of the above. |
   | `<e> todo "<text>"` | Work still owed. Listed by tooling; a release gate may reject any. |
   | `<e> deprecated "<text>"` | What to use instead. |

   `example`, `tag`, and `owner` are removed (unused, and `owner` collides with
   ownership vocabulary).
7. **Subjects.** A context row attaches to an entity, or to a block through
   `<op> label <label> <predicate> ...`.
8. **LR-06 rules apply to context rows, not to comments**: the staleness flag
   when the entity's structural rows change, and the filler check.
9. **Reasons stay where a row waives a check.** `discards "<reason>"` and
   `because "<reason>"` keep their inline strings and remain required.

Rule of thumb for authors: if the next reader must not miss it, or a tool should
track it, write a row. Otherwise write a comment.

#### Worked example

```
main is operation
main purpose "Print a greeting and exit cleanly"
main invariant exitsZero "Exits with code zero"
main rationale "The greeting is a fixed literal so the demo has no input"
main risk security "Must never print user-supplied text without escaping"
main todo "Replace the fixed greeting with a configured one"
main label failed purpose "Shared exit for any write failure"
# Tried building the greeting with string.concat first; a literal is simpler.
main at entry do greetCall   # the only step that touches stdout
```

### LR-22 Loops, retries, and recursion

Status: decided (2026-11-13, accepted by owner)

#### How it works at `b6aa5c7`

- **A loop is a label and a backward `goto`.** There is no loop construct.
  60 of the examples contain one.
- **`maxIterations <n>`** is an operation-level row. Its only effect is to
  silence SS0951, which fires when a loop's exit test reads untrusted input.
  Probes on the sum-to-five example:
  - `main maxIterations 2` on a loop that runs five times passes `check --strict`
    and the program prints 15. The bound is not enforced at compile time or at
    run time.
  - `main maxIterations banana` passes.
  - No example or app has a `maxIterations` row.
- **Stuck loops.** SS0950 catches a loop with no exit path at all. A loop whose
  counter never advances (the increment deleted) is not reported.
- **Retries are a hidden loop.** `useRetry <n>` on a call re-invokes it up to
  `n` times, with `retryBackoffMs` between attempts. The repetition appears in
  no step row.
- **Recursion** traps at a compiler constant (`EAV_RECURSION_LIMIT`). The limit
  is not stated in source.

#### Decision

Builds on LR-16 (explicit control-flow graph) and LR-18 rule 7 (bounds attach to
the block).

1. **A loop is a block that some `goto` or `branch` jumps back to.** No loop
   keyword. Leaving early and skipping ahead are ordinary jumps to named blocks.
2. **Every loop block states its bound**, and only loop blocks may:
   `<op> label <label> maxIterations <bound>`. `<bound>` is an integer literal
   or the name of an immutable `Int64` value, so a loop over run-time data can
   be bounded by a stated cap. A missing row on a loop block is an error; the
   row on a block nothing jumps back to is an error.
3. **The bound is enforced.** The compiler counts entries to the block per run
   of the operation and traps with a structured panic naming the operation and
   label when the count passes the bound. When the trip count is a compile-time
   constant, a bound smaller than it is a check error.
4. **Unbounded loops are stated.** `<op> label <label> maxIterations unbounded`
   requires `<op> label <label> because "<reason>"`. This is for accept loops
   and event loops.
5. **No hidden repetition.** `useRetry` and `retryBackoffMs` are removed. A
   retry is written as a loop block with a bound, an attempt counter, and an
   explicit delay call.
6. **Recursion states its depth.** An operation that can reach itself through
   calls states `<op> maxRecursion <n>`. The compiler enforces it with the
   existing depth guard, using the stated number in place of the global
   constant. The row is an error on an operation that cannot recurse.
7. **Progress is not proven.** The compiler does not try to prove a loop
   advances; the enforced bound is the safety net. SS0950 stays for the case it
   can decide (no exit path).
8. **Iterating a collection** uses the same loop block, driven by calls that
   fetch the next item. Its design belongs to LR-10.

#### Worked example

A retry, written out (in the form amended by Part 3):

```
fetch label begin loopKind none
fetch label begin within none
fetch label attempt loopKind doWhile
fetch label attempt within none
fetch label attempt maxIterations 2
fetch label countAttempt loopKind none
fetch label countAttempt within attempt
fetch label backoff loopKind none
fetch label backoff within attempt
fetch label succeeded loopKind none
fetch label succeeded within none
fetch label gaveUp loopKind none
fetch label gaveUp within none
fetch let maxAttempts immutable Int64 3
fetch let one immutable Int64 1
fetch let attemptsMade mutable Int64 0
fetch at begin goto attempt
fetch at attempt do requestPage
fetch at attempt branch ifError requestPage goto countAttempt else goto succeeded
fetch at countAttempt do addAttempt
fetch at countAttempt set attemptsMade nextAttempts
fetch at countAttempt do attemptsLeftCheck
fetch at countAttempt branch if attemptsLeft goto backoff else goto gaveUp
fetch at backoff do waitBeforeRetry
fetch at backoff goto attempt
fetch at succeeded return ok pageText
fetch at gaveUp return ok emptyText
```

Three attempts means returning to `attempt` at most twice, so the bound is 2.

### LR-23 Loop kinds as declared, checked shapes

Status: decided (2026-11-13, accepted by owner). Extends LR-22.

- **Problem**: Under LR-22 a loop is "a block something jumps back to". The
  bound is stated, but the loop itself is still inferred from the shape of the
  graph: which blocks belong to it, where it may be entered, and what kind of
  loop the author meant. P-2 says nothing is implied. An inferred loop also
  gives the checker nothing to hold the code to, which is why a counter that
  never advances goes unreported.
- **Decision**: a loop is declared on its header block with a kind from a
  closed set, every block in it states its membership, and the compiler checks
  the blocks against the shape that kind requires.

#### Rows

```
<op> label <header> loop <kind>            # counted | while | doWhile | forEach | forever
<op> label <header> maxIterations <bound>  # LR-22; `unbounded` only with kind forever
<op> label <header> counter <name>         # kind counted only
<op> label <block> within <header>         # every other block of the loop
```

A nested loop's header states `within <outerHeader>`.

#### Rules for every kind

1. **Single entry.** A block outside a loop may jump only to the loop's header.
   Jumping into the middle of a loop is an error.
2. **Stated membership.** A block that states `within H` may jump to another
   block within `H`, to `H` itself (next iteration), or to a block outside `H`
   (leaving the loop). The compiler rejects any jump the declarations do not
   allow, and any block on a cycle that declares no loop.
3. **Leaving early and skipping ahead are jumps.** Leaving several nested loops
   at once is a jump to a block outside all of them. No `break` or `continue`
   keywords.
4. **Bound enforced at run time** (LR-22), counted per entry to the header.

#### Kinds

| Kind | What it is | Shape the compiler checks | Termination |
| --- | --- | --- | --- |
| `counted` | Runs a number of times fixed before it starts | Header tests the counter against an immutable limit and branches in or out. Exactly one `set` of the counter in the loop, from the counter plus or minus an immutable non-zero step, in the direction of the limit. | Proven at check time. A counter that does not advance is an error. |
| `while` | Tests a condition first; body may run zero times | Header ends in a two-target branch: one target within the loop, one outside. | Run-time bound. |
| `doWhile` | Runs the body, then tests; body runs at least once | Header is the first body block. The branch that returns to the header or leaves is in a later block. | Run-time bound. |
| `forEach` | Visits each item of a collection once | Defined with collections (LR-10). The collection may not be changed inside the loop. | Bounded by the collection's length. |
| `forever` | A service loop that is meant not to end | `maxIterations unbounded` and a `because` row. | None, by declaration. |

#### How familiar loops are written

| Loop | Written as |
| --- | --- |
| `for i in 1..n` | `counted` |
| `while condition` | `while` |
| `do ... while condition` | `doWhile` |
| `for item in list` | `forEach` (after LR-10) |
| `while true` server or event loop | `forever` |
| Retry up to n times | `counted`, leaving early on success |
| Poll until ready, with a delay | `while`, with a bound |
| Search with early exit | any kind, with a jump out to a "found" block |
| Loop with the test in the middle | `while` or `doWhile`, with the exit branch in a middle block |
| Nested loops | inner header `within` the outer header |
| State machine | `while` whose header branches on a state enum with `ifVariant` |
| Recursion | not a loop; `maxRecursion` (LR-22) |

#### Not representable, on purpose

- A loop with no stated bound that is not declared `forever`.
- Jumping into the middle of a loop, or a cycle with two entry points.
- A jump to a computed target.
- Loops inside expressions (comprehensions): there are no expressions.
- Generators or coroutines that pause mid-loop: use tasks (LR-17).
- Parallel loops: use workers (LR-17).

#### Worked example

The sum-to-five loop (in the form amended by Part 3):

```
main label begin loopKind none
main label begin within none
main label sumLoop loopKind counted
main label sumLoop within none
main label sumLoop maxIterations 5
main label sumLoop counter nextNumber
main label addStep loopKind none
main label addStep within sumLoop
main at begin goto sumLoop
main at sumLoop do pastLimitCheck
main at sumLoop branch if pastLimit goto finish else goto addStep
main at addStep do addToTotal
main at addStep set total nextTotal
main at addStep do addOne
main at addStep set nextNumber afterNextNumber
main at addStep goto sumLoop
```

Deleting `main at addStep set nextNumber afterNextNumber` is now a check error: a
`counted` loop must advance its counter.

## Part 2: completing the language (LR-24 to LR-41)

Status of every item in this part: decided 2026-11-13 by delegation. The owner
asked for further refinement notes in line with the earlier decisions, with one
target: enough language to write an HTTP server and SemanticScript's own
compiler. Each item is open to reversal like any other.

Two worked examples exercise this part end to end:

- `docs/refined-examples/server/`: listen, accept forever, one task per
  connection, a static route table, per-request region.
- `docs/refined-examples/selfhost/`: read a word token from source text and
  classify it against a keyword table, then tokenize into a list.

Both pass the refined checker (Part 4). Neither runs yet.

### What the two targets need

| Need | HTTP server | Compiler | Item |
| --- | --- | --- | --- |
| Lists and maps of any type | headers, routes | tokens, rows, symbol tables | LR-24, LR-25 |
| Iterating a collection | match a route | every pass | LR-25 |
| Static lookup data | route table | keywords, predicate shapes, diagnostics | LR-26 |
| Byte and text access | parse a request | lex source | LR-27 |
| Records, variants, optional values | request, response | tokens, entities, AST | LR-28 |
| A value set on several paths | the response | most results | LR-29 |
| Errors with data | parse failures | diagnostics | LR-30 |
| Mutating through a loan | append to a list | append to a list | LR-31 |
| Several files | handlers per file | one module per pass | LR-32 |
| Waiting on I/O, many tasks | accept, read, write | none | LR-33 |
| Arguments, streams, exit code | port from arguments | file names, exit status | LR-34 |
| Files and sockets | sockets | read source, write output | LR-35 |
| HTTP itself | parse and serialize | none | LR-36 |
| Passing an operation as a value | handlers | visitors, comparators | LR-37 |
| Exact integer behavior | lengths, status codes | offsets, widths, hashing | LR-38 |
| Tests tied to invariants | handlers | every rule and diagnostic | LR-39 |
| A standard library to stand on | net, http, time | string, byte, fs, process | LR-40 |

### LR-10 Collections, loops, and generics (resolved)

Loops were settled in LR-16, LR-22, and LR-23. Generics are LR-24 and
collections are LR-25. This item is closed.

### LR-24 Generics by named instantiation

- **Now**: `typeParam T` on a record, enum, or operation, and
  `<Name> instantiates <Generic> <Type>` to create a concrete type (three
  examples use it). The standard list is not generic: `list.*` works on a
  `ListHandle` of `Int64` only.
- **Decision**:
  1. Keep `typeParam` and `instantiates`. There is no inference and no type
     application inside a row: a generic is used only through a named
     instantiation.
     ```
     HeaderList is record
     HeaderList instantiates List Header
     ```
  2. An instantiation is an ordinary named type with derived call targets, the
     same way `<Record>.new` is derived today: `HeaderList.new`,
     `HeaderList.append`, `HeaderList.get`. One instantiation per distinct type
     argument list per module; a second with the same arguments is an error.
  3. A generic operation is likewise called only through a named instantiation:
     `sortTokens is operation` / `sortTokens instantiates sort Token`.
  4. A type parameter may be constrained by one row,
     `<Generic> typeParam T plain | any`. `plain` admits only values with no
     owner (LR-20), which is what lets a container copy its elements.

### LR-25 Collections and iteration

- **Now**: `list.*` (5 targets, `Int64` only) and `map.*` (5 targets), both
  with a manual `release`. No iteration support; examples index by hand.
- **Decision**:
  1. The standard library defines generic `List T`, `Map K V`, and `Set T`.
     They are region-owned (LR-20): `new` takes a region, and there is no
     `release` target.
  2. Reads that can miss are fallible: `<List>.get` raises `IndexOutOfRange`,
     `<Map>.get` raises `KeyMissing`. There is no unchecked access.
  3. Mutating targets (`append`, `put`, `remove`, `clear`) take the collection
     as `lendMutable` (LR-31).
  4. **`forEach`** (LR-23) is driven by one guard:
     ```
     <op> label <header> loop forEach
     <op> label <header> over <collection>
     <op> label <header> maxIterations <bound>
     <op> at <header> branch ifNext <collection> bind <item> goto <body> else goto <done>
     ```
     The compiler keeps the position. `<item>` is a copy when the element type
     is plain and a borrowed view otherwise. Inside the loop the collection may
     not be passed as `lendMutable` or `give`. The `ifNext` row must be the only
     row of the header block.
  5. **Typed positions.** An index into a particular list is its own type:
     ```
     NodeId is alias
     NodeId for Int64
     NodeId indexes NodeList
     ```
     `<List>.get` on `NodeList` accepts only a `NodeId`. This is how trees and
     graphs are built: nodes live in a list and refer to each other by id. There
     are no pointer types in application source.

### LR-26 Static data tables

- **Now**: no way to write constant compound data. Lookup tables are built by
  calls at start-up, and the compiler's own tables live in Python.
- **Decision**: a `table` entity holds constant records, one fact per row.
  ```
  keywords is table
  keywords of Keyword
  keywords cell isWord text "is"
  keywords cell isWord kind keywordIs
  keywords cell atWord text "at"
  keywords cell atWord kind keywordAt
  ```
  1. `of` names a record type whose fields are plain values, static strings, or
     operation references.
  2. `cell <rowId> <field> <value>`: every row id must state every field
     exactly once. Row order is the order row ids first appear.
  3. A table is owned by the built-in region `static` and is read-only. It
     supports `forEach`, `<table>.length`, and `<table>.get` by row id.
  4. This is also the form for the predicate shape table and the diagnostic
     registry once the compiler is self-hosted.

### LR-27 Text and bytes

- **Now**: `string.*` has 9 targets: concat, compare, find, byte length. There
  is no way to read one byte, take a slice, or parse a number, so a lexer or a
  request parser cannot be written.
- **Decision**:
  1. Three types. `String` is immutable, valid UTF-8 text. `Bytes` is immutable
     raw bytes. `ByteBuffer` is a growable, mutable buffer. All are region-owned,
     except string literals and table cells, which belong to `static`.
  2. No implicit conversion. `string.fromBytes` validates and is fallible;
     `string.toBytes` is a view.
  3. Positions are byte offsets (`Int64`). Required targets:
     `string.byteLength`, `string.byteAt` (fallible), `string.slice` (fallible,
     returns a view that `borrows` the source), `string.equals`,
     `string.startsWith`, `string.find` (returns an optional offset),
     `string.concat` (takes a region), `string.toInt64` (fallible),
     `string.fromInt64` (takes a region).
  4. Byte classification lives in `standard.byte`: `byte.isLetter`,
     `byte.isDigit`, `byte.isLetterOrDigit`, `byte.isSpace`, `byte.equals`.
  5. Text is assembled with a `ByteBuffer`: `buffer.new` (region),
     `buffer.appendString`, `buffer.appendByte`, `buffer.appendInt64` (all
     `lendMutable`), then `buffer.toString` (fallible) or `buffer.toBytes`.
  6. Unicode scalar values are `Rune` (`UInt32`) with `string.decodeRuneAt`
     (fallible). Nothing in the core depends on it.

### LR-28 Records, variants, and optional values

- **Now**: `<Record>.new`, `<Record>.<field>`, `<Enum>.<variant>`, and
  `branch ifVariant ... bind` exist. A record cannot be changed after it is
  built, and there is no standard optional type.
- **Decision**:
  1. Keep the derived targets. Add `<Record>.with<Field>` (record and new value
     in, new record out) and `<Record>.equals` / `<Enum>.equals`.
  2. Records and enums are immutable values. A value that changes is a mutable
     `let` that is `set` to a new record.
  3. **Class follows contents** (LR-20). A record or variant is plain if every
     field is plain. If any field is region-owned, the whole value is owned by
     that same region, and `<Record>.new` takes the region as an argument. A
     record may not hold an operation-owned resource.
  4. A field read of a region-owned field returns a view: `borrows <record>`.
  5. The standard library defines `Option T` with variants `some` (payload `T`)
     and `none`. "Maybe a value" is always an instantiated `Option`, never `nil`.
     The `nil` literal is removed.
  6. `ifVariant` chains must cover every variant (LR-16.5).

### LR-29 Values set on more than one path

- **Now**: a name bound by one call cannot be bound by another, so a value that
  comes from different calls on different paths has no spelling. Authors
  duplicate everything downstream.
- **Decision**: declare the merge explicitly.
  ```
  handleConnection let response mutable HttpResponse unset
  handleConnection at dispatch set response handlerResponse
  handleConnection at badRequest set response badRequestResponse
  ```
  `unset` is a declared absence of an initial value, legal only on a mutable
  `let`. Definite assignment (LR-04) rejects any read that some path reaches
  without a `set`. If the type is region-owned, every assigned value must be
  owned by the same region.

### LR-30 Errors and returns

- **Now**: `error` and `errorCase` entities, `raises` rows, `out Result`,
  and positional returns such as `return nil writeError`.
- **Decision**:
  1. Errors are enums (as §34 already plans). A variant may carry a payload,
     including the lower-level error that caused it.
  2. Every operation states `<op> raises <ErrorEnum> | none`. Exactly one row.
  3. Every return says which it is:
     `<op> at <label> return ok <value> | none` or
     `<op> at <label> return error <value>`. `return error` is legal only when
     `raises` names that enum.
  4. A call to an operation that `raises` must state `catch <name> <ErrorEnum>`
     and is followed at once by `branch ifError` (LR-16.4).
  5. There is no propagation shorthand. To pass a failure up, the failure block
     builds this operation's own error variant and returns it. If the types are
     the same it returns the caught value.
  6. Deliberately ignoring a failure is written as a branch whose two targets
     are the same block. The row stays visible; a comment or `rationale` row
     says why.
  7. Traps (overflow, bound exceeded, out of memory) are not errors. They end
     the task with a structured panic and cannot be caught.

### LR-31 Passing modes and call skeleton, completed

Amends LR-20 after writing the worked examples.

1. **Four modes.** A loan is read-only or exclusive:

   | Operation `input` | Call `arg` | Meaning |
   | --- | --- | --- |
   | `value` | `copy` | plain value, copied |
   | `borrowed` | `lend` | read-only loan |
   | `borrowedMutable` | `lendMutable` | exclusive loan; the callee may change it |
   | `owned` | `give` | ownership moves to the callee |

   While a value is lent with `lendMutable` it may not appear in another
   argument of the same call. Lending a `Region` so the callee can allocate in
   it is `lend`.
2. **Call and task skeleton**, in order: `in`, `invokes`, `arg` rows, `out`,
   `ownedBy`, `borrows`, `catch`. `out none` when there is no result;
   `borrows none` when the result is not a view.
3. **`cleanedBy`** is required exactly when `ownedBy` names the operation. Its
   value is a cleanup entity, or `none` when every path gives or returns the
   value (the accepted connection in the server example).
4. **Operation skeleton**, in order: context rows, `input` rows (or
   `input none`), `output`, `outputOwner`, `raises`, `effect` rows (or
   `effect none`), `uses` rows (or `uses none`), `memory heap`, `memory stack`,
   `memory max`, `async`, then labels, `let` rows, and steps.
5. **`outputOwner`** is `none` (plain result), the name of a `Region` input, or
   `caller` (an operation-owned resource handed to the caller).
6. **`static`** is a built-in region that lives for the whole run. String
   literals and tables are owned by it. Nothing can be allocated in it at run
   time.

### LR-32 Modules and imports

- **Now**: `imports`, plus five selective predicates (`importOperation`,
  `importType`, `importError`, `importCapability`, `importConstant`). Standard
  targets such as `string.concat` need no import at all.
- **Decision**:
  1. One file is one module. `<module> path <dotted.path>` must match the file's
     location.
  2. One way to import: `<module> imports <dotted.path>`, one row per module
     used, standard library included. The five selective predicates are removed.
  3. An imported name is always written with its module's last path segment:
     `string.concat`, `lexer.scanWord`. Two imports with the same last segment
     are an error; there are no aliases. A name with no prefix is local to the
     module.
  4. `exports` lists every name visible outside, one row each. Everything else
     is private.
  5. Import cycles are an error.
  6. The `project` entity lives only in `build.sem`.

### LR-33 Waiting, deadlines, and many tasks

Builds on LR-17.

1. **A call that can wait is a task.** Any target that may suspend (socket and
   file I/O, timers, channel receive) is `async true` and can only be invoked
   through a `task` entity with `start` and `join`. `join` is the visible
   suspension point. `do` never suspends.
2. **Every waiting target takes a `Deadline`.** `Deadline.after` (milliseconds)
   or `Deadline.never`. There are no default timeouts. A missed deadline is an
   ordinary error variant.
3. **Cancellation is an error path.** `cancel <task>` makes the task's pending
   wait fail with a `cancelled` variant, which the task handles like any other
   failure and then releases what it owns.
4. **Task groups** own a changing number of tasks:
   ```
   connections is taskGroup
   connections in main
   connections limit 256
   connections atReturn joinAll        # joinAll | cancelAll

   main at startHandler start handleTask into connections
   main at stopped join connections
   ```
   `start ... into` at the limit waits for a slot. A group is owned by one
   operation and is joined or cancelled on every path to its `return`.
5. **Operations that `join` anything are `async true`.** The entry operation
   may be.
6. **Channels** (`Channel T`, an instantiated generic) carry values between
   tasks and between workers. `send` uses `give` for owned values.

### LR-34 The edges of a program

1. **Entry.** `main input none`, `main output ExitCode`. Everything else comes
   through capability-gated calls.
2. **Arguments and environment.** `process.argumentCount`, `process.argument`
   (fallible, by index), `environment.get` (fallible).
3. **Standard streams.** `console.readLine` (fallible, takes a region and a
   maximum length), `console.write`, `console.writeLine`, `console.writeError`.
4. **Other programs.** `process.run` (program, argument list, deadline) under a
   `process.spawn` capability. A self-hosted compiler writes LLVM IR as text and
   runs the system linker this way; no foreign-function binding is needed.
5. **Capabilities carry a scope.** Every capability has exactly one `scope`
   row: a quoted prefix (a directory, an address and port, a program name) or
   `none` when the resource kind has no scope. A call outside the stated scope
   fails with a permission error at run time, and a literal argument outside
   the scope is a check error.
6. **Time.** `clock.now` (wall time) and `clock.monotonic` under a clock
   capability. There is no ambient time.

### LR-35 Files and network resources

- **Now**: `fs.*` can only read (6 targets). `net.*` is client-only (6
  targets); serving is done by the `webServer` entity and a C runtime.
- **Decision**: both are operation-owned resources (LR-20).
  1. Files: `fs.openRead`, `fs.openWrite`, `fs.create`, `fs.read` (region,
     maximum bytes, deadline), `fs.write`, `fs.close`, `fs.exists`, `fs.remove`,
     `fs.list`, and the convenience pair `fs.readAll` / `fs.writeAll` with a
     stated maximum size.
  2. Sockets: `net.listen`, `net.accept`, `net.connect`, `net.read`,
     `net.write`, `net.close`, `net.closeListener`. Every read states a maximum
     byte count.
  3. Handles are `owned` by exactly one operation, lent to tasks that read and
     write, and given to the task that will close them.

### LR-36 HTTP is a library

- **Now**: `webServer` is an entity kind with `route`, `host`, `port`, and
  other keywords; `htmlTemplate` and SQL/JSON/HTML "islands" make indentation
  meaningful inside a `body` row.
- **Decision** (carries out §34.3):
  1. Remove the `webServer` entity, the `webServer` target, and its keywords. A
     server is a console program that listens (see the worked example).
  2. `standard.http` is written in SemanticScript: `HttpRequest`,
     `HttpResponse`, `HttpMethod`, `http.parseRequest`, `http.response`,
     `http.serializeResponse`, `http.header`. Parsing limits (header count,
     line length, body size) are arguments, not hidden constants.
  3. Routing is a `table` of method, path, and handler (LR-26, LR-37).
  4. Remove islands and `htmlTemplate`. Indentation is never meaningful. Long
     text is a string literal or an embedded file (`literalSource` with its
     digest); HTML and SQL are built by library calls that escape by
     construction.

### LR-37 Operations as values

- **Now**: `operationType` declares a signature; a named operation can be
  passed and invoked indirectly. No closures.
- **Decision**: keep it, with the full skeleton.
  1. An `operationType` states `input` rows with modes, `output`,
     `outputOwner`, and `raises`. An operation matches only if every one of
     those rows is identical.
  2. Operation references are plain values. They may be stored in a `let`, a
     record field, or a table cell.
  3. The effects of an indirect call are those the `operationType` declares
     with `effect` rows (or `effect none`). An operation with more effects than
     the type allows cannot be used as a value of that type.
  4. Still no closures. State is passed as an argument.

### LR-38 Numbers

1. Fixed-width integers and floats only. No implicit conversion or promotion,
   including between signed and unsigned (LR-12).
2. Arithmetic targets name their type and behavior:
   `math.addInt64` traps on overflow; `math.wrappingAddInt64` and
   `math.saturatingAddInt64` are separate targets. Division and remainder trap
   on zero.
3. Comparison is by call: `compare.equalInt64`, `compare.lessThanInt64`,
   `compare.greaterOrEqualInt64`, and so on for each type. The comparator
   keywords inside `branch` are already removed (LR-15).
4. Bit operations are calls in `standard.bits`.
5. `Byte` is `UInt8`. A literal takes the type its position states and is
   range-checked at compile time.

### LR-39 Tests

Finishes LR-06.

1. A `test` is an entity kind with the operation skeleton, no inputs, and no
   output. It lives in a `<name>.test.sem` file beside the module it tests.
   ```
   healthIsOkTest is test
   healthIsOkTest verifies handleHealth healthIsOk
   healthIsOkTest purpose "A health request gets status 200"
   ```
2. `verifies <operation> <invariantId>` may repeat. Every `invariant` must be
   named by at least one test, and every `verifies` must name a real invariant.
3. Assertions are calls in `standard.test`; a failed assertion fails the test
   and reports the operation, the invariant id, and the row.
4. A test declares its effects and capabilities like any operation.
5. Compiler tests for rejected programs are fixtures with one stated
   expectation: `<fixture> expectsDiagnostic <code>`.

### LR-40 The standard library contract

1. Every standard target has a signature stating its inputs with modes, output
   and owner, errors, effects, whether it can wait, and whether it allocates
   (it takes a `Region` if so).
2. The library is written in SemanticScript wherever possible. Raw bindings to
   the C runtime are confined to a small core (`memory`, `byte`, `fs`, `net`,
   `process`, `clock`) and are the only place `runtimeBinding` is legal.
3. Modules the two targets need: `string`, `byte`, `bits`, `math`, `compare`,
   `list`, `map`, `set`, `option`, `buffer`, `fs`, `net`, `http`, `time`,
   `clock`, `process`, `environment`, `console`, `test`.
4. Each module ships with an accepted example and a test for every target.

### LR-41 What is still missing

Known gaps after this part, in the order they would block real work:

1. **Floating-point formatting and parsing** beyond `convert`. Needed for JSON.
2. **JSON** as a library on top of LR-27 and LR-28.
3. **TLS.** The server example is plain HTTP.
4. **Sorting and hashing** as generic operations (LR-24 covers the mechanism).
5. **Worker pools** for CPU-bound work (LR-17 layer 3 names them; no row shapes
   yet).
6. **Incremental and separate compilation** rules for modules.
7. **A formal grammar** generated from the shape table (plan step 1).

## Part 3: amendments after adversarial review (LR-42)

Status: decided 2026-11-13 by delegation. Not reviewed by the owner.

An independent reviewer was given the notes, the worked examples, and the
checker, with instructions to break the design against its own goal: a very low
perplexity, fully explicit, agent-first language. It reported 17 findings. Each
was checked against the files before being acted on; all held.

**Where this part conflicts with Part 1 or Part 2, this part wins.** The worked
examples follow it, and the refined checker (Part 4) enforces it.

### The cold-write test

The reviewer wrote a new program (count the words on each input line) using
only this file, then ran the checker.

- **First attempt: 4 checker errors, one cause.** It wrote `arg none` on calls
  with no arguments, as LR-18.1 says. The examples and the checker omitted the
  row. The rule was right and the examples were wrong (A1).
- **Twelve guesses the checker could not see**, each now answered below: effect
  vocabulary (A8), whether console reads wait (A25), error and slot names
  (A26), whether `ExitCode` is built in (A26), memory numbers (A18), literals in
  arguments (A23), how end of input is signalled (A6, A25), which loop kind
  reads until end of input (A25), row order outside operations (A22), tests
  (A17), and allocating in a loop (A24).

This is the first measurement behind plan step 12. The target is zero errors
and zero guesses on a first attempt.

### Amendments

| # | Finding | Rule now |
| --- | --- | --- |
| A1 | Calls with no arguments omitted their `arg` rows: an empty set by absence | Every call and task has at least one `arg` row; with no arguments it is `arg none`. |
| A2 | `maxIterations` counted entries to the header, so five passes needed `6`, and the lexer example trapped on a word that ran to the end of the source | `maxIterations` counts returns to the header from inside the loop. Five passes is `5`. |
| A3 | Imported types and enum variants were written bare, against LR-32.3; a module had two names | An imported type is `module.Type` (`net.NetError`, `http.HttpRequest`). A variant is always `Enum.variant`, in every position. A module entity is named after the last segment of its `path`. Built-in, unprefixed types: the fixed-width numbers, `Bool`, `Byte`, `String`, `Bytes`, `Region`, `ExitCode`. |
| A4 | `ifNext ... bind candidate` gave no type; which names an `ifError` branch puts in scope was unstated | `branch ifNext <collection> bind <name> <Type> ...`. After `branch ifError <call>`, the call's `catch` name is in scope only on the error arm and its `out` name only on the `else` arm. A task's `out` and `catch` names are bound at `join`. A `forEach` starts from the first element each time its header is entered from outside the loop. |
| A5 | Value keywords shared positions with user names; `nil` was reserved and removed; `none` was a literal and an `Option` variant | Reserved: `true`, `false`, `none`, `caller`, `unset`, `unbounded`, `static`, `begin`. `nil` is not a word. `Option` has variants `present` and `absent`. |
| A6 | `ifVariant` had no stated shape and its "declared default" was undefined | Variant inspection is one construct that is exhaustive by construction. A block ends in `<op> at <L> match <value> <EnumType>` followed by one `<op> at <L> case <Enum.variant> bind <name\|none> <Type\|none> goto <label>` row per variant. Every variant appears exactly once. `ifVariant` is removed. |
| A7 | Payloadless variants omitted the payload | `<Enum> variant <name> <PayloadType\|none>`. |
| A8 | Effect and `grants` words were never defined | `effect <verb> <module>.<resource>` with verbs `read`, `write`, `readWrite`, `listen`, `connect`, `spawn`. The resources are published by each library module's signature; there is no other source of them. |
| A9 | The cleanup skeleton was undefined; `logAndSuppress` logged with no effect; the cleanup's fallible call had no error path | Cleanup rows, in order: `in`, `call`, `cleans`, `onFailure suppress\|trap`, `because`. The worker call is run by the cleanup, not by `do`, so the `ifError` rule does not apply to it; `onFailure` is its error path. Nothing is logged implicitly. |
| A10 | Slot names of derived targets were unstated | `<Record>.new`: one slot per field, named by the field. `<Record>.<field>`: slot `record`. `<Record>.with`: slot `record` plus one slot named by the field to change. `<Enum>.<variant>`: slot `payload`, or `arg none`. `equals`: `left`, `right`. |
| A11 | `HttpHandler` stated no effects or `async`; an indirect call looked like a direct one | An `operationType` states `effect` rows (or `effect none`) and `async`. A call through a reference uses `invokesReference <binding>`, never `invokes`. A reference whose type is `async true` is invoked through a task. |
| A12 | `start ... into` could wait; `atReturn joinAll` duplicated an explicit `join` and one path skipped it | A task group has no `atReturn` row. Every path to a `return` states `join <group>` or `cancel <group>`. Waiting for room is its own step, `awaitSlot <group>`; `start ... into` a full group traps. |
| A13 | Several skeleton rows existed only conditionally, so "not a loop" and "not recursive" were stated by absence | `cleanedBy` is on every call (`none` when it does not apply), after `ownedBy`. Every operation states `maxRecursion <n>\|none`. Every block states `label <L> loopKind <kind\|none>` and `label <L> within <header\|none>`. The predicate is `loopKind`, which also ends `label loop loop counted`. The first block is `begin`, since `entry` is a project predicate. |
| A14 | "Exactly one `set`" did not prove a `counted` loop advances; the bound was only checked one way | Exactly one `set` of the counter on every path from the header back to the header. When the trip count is a compile-time constant, `maxIterations` must equal it. |
| A15 | The LR-22 retry example declared no loop; a retry cannot have the `counted` header shape | A retry is a `doWhile` with a bound. The example is corrected. |
| A16 | Ignoring a failure had two rules, one of which relied on a comment | A same-target `branch ifError` requires a `rationale` row on the call. `discards "<reason>"` is only for an unused result. |
| A17 | Tests needed their own invariants (a regress); private operations were untestable; mandatory invariants on helpers invite untrue prose; the filler check read English | A test file is part of the module beside it. A test states `verifies` and no `invariant`. A non-exported operation may state `invariant none`. The filler check is mechanical: empty, under ten characters, or equal to the entity's name ignoring case and spaces. |
| A18 | `memory stack` and `memory max` were required numbers with no meaning, so authors invent them | Both rows are removed. Memory is stated by `memory heap true\|false` and by each region's `capacity`. **This reverses part of LR-20 rule 10, which the owner accepted.** |
| A19 | The checker called a jump "backward" by text order; the notes never ordered blocks | Blocks may appear in any order after `begin`. A loop is what the declarations say. A jump to a block `within H` is legal only from `H` or from a block inside `H`. Every cycle must pass through a declared header. |
| A20 | `in` was glossed "owned by" beside `ownedBy`; an instantiated list was `is record`; `with<Field>` changed case; "no dots" sat beside `Token.new` | `in` means "belongs to". An instantiation is `<Name> is instance`. Field update is `<Record>.with` (A10). Dots appear only in paths: `module.name`, `Type.target`, `Enum.variant`. |
| A21 | Table row order was semantic but positional | `<table> row <rowId> <position>` declares each row and its order. Cells name a declared row. |
| A22 | Context rows came first on operations and last on everything else | On every entity kind, context rows come directly after the `is` row. |
| A23 | Whether `arg`, `set`, and `return` accept literals was unstated, which gives two spellings | Literals appear only in `let` rows and table `cell` rows. Everything else takes a name. |
| A24 | A region only empties at `return`, so a loop that allocates grows without limit; what a trap does to cleanups was unstated | A loop body that allocates is its own operation with its own region. A trap runs the deferred cleanups of every operation on that task's stack, then ends the task; its owner sees a `trapped` failure. |
| A25 | Whether console calls wait, and which loop kind reads to end of input, were guesses | `console.readLine` waits, so it is a task. Console writes are `do`. End of input is an error variant, inspected with `match`. A loop over input of unknown size is `forever`; a `forever` loop may have exits. |
| A26 | Slot and error names had to be guessed | Library conventions: slots `left`/`right` for two operands, `value` for one, `text`, `index`, `list`/`item`, `record`, `payload`, `region`. Error enums are `<module>.<Thing>Error`. Every module publishes its targets, slots, errors, and effects in its signature, and tooling lists them. |

### Not adopted

- **A per-iteration region reset step.** It would need the checker to prove no
  value from the region is still in use. The separate-operation idiom (A24) is
  explicit and already works.

### What the examples now cover

`tokens.sem` and `tokens.test.sem` were added because the reviewer showed the
first two examples avoided most of what a compiler needs. Together the four
files now use: an instantiated list, `lendMutable`, an operation that `raises`,
`return error`, an error payload, `match` / `case`, `Option`, a fallible list
read, a `while` loop bounded by a run-time value, `forEach`, `forever`, a task
group, an operation reference, and a test with `verifies`.

Still not exercised by any example: `Map`, `Set`, `counted` and `doWhile`
loops, `give` of a region-owned value, `cancel`, channels, and file I/O.

## Part 4: implementation (2026-11-13)

Superseded in part by Part 5: the bridge described here was removed, and every
item in "Not enforced yet" is now enforced.

Work on the compiler started from this file on 2026-11-13. This part records
how it is built, what it enforces today, and the decisions made while building
it. Decisions marked D-n were made by delegation, the same way as Parts 2 and 3.

### Approach

The refined syntax changes almost every row, so it is implemented as a new
front end beside the legacy compiler rather than inside it:

- `semanticscript/compiler/refined/` holds the lexer, the shape table
  (`shapes.py`), the parser, the checks (`semantics.py`, `flow.py`), the
  standard-library signatures (`library.py`), and a lowering bridge.
- The bridge (`lower_legacy.py`) turns a checked program in a small runnable
  subset into legacy rows and runs it on the existing LLVM backend. Anything
  outside the subset is refused with `R901`; nothing is silently dropped.
- The legacy compiler (`semanticscript.py`) is unchanged. It retires once the
  corpus is migrated (plan step 10) and the refined front end has its own
  backend.

Commands:

```
python semanticscript/compiler/refined check <module.sem | build.sem | project dir> [--json]
python semanticscript/compiler/refined run   <build.sem | project dir> [--json]
python semanticscript/compiler/refined lower <build.sem | project dir>
python semanticscript/compiler/refined grammar
```

`docs/refined-grammar.md` is generated by `grammar` from the shape table.

### Worked examples, now checked by the real checker

| Project | What it shows | Status |
| --- | --- | --- |
| `docs/refined-examples/hello` | Hello world | checks clean, runs: `Hello, world!` |
| `docs/refined-examples/sum` | A `counted` loop | checks clean, runs: `15` |
| `docs/refined-examples/factorial` | Recursion with `maxRecursion` | checks clean, runs: `120` |
| `docs/refined-examples/server` | HTTP server: tasks, a task group, a cleanup, regions, a route table, an operation reference | checks clean; not runnable yet (R901) |
| `docs/refined-examples/selfhost` | Lexer and tokenizer in two modules, a generic list, `match`/`case`, `Option`, a test file | checks clean; library project |

The sketch checker `tests/audit/refined_sketch_lint.py` is retired; the real
checker replaces it.

Writing the checker found mistakes the sketch checker had passed: the lexer
example never exported the `Token` and `TokenKind` types that the tokenizer
imports, and two calls passed plain records by loan.

### Tests

`tests/test_refined.py` (74 tests):

- every worked example checks clean, and the three runnable ones print the
  expected output;
- the server is refused by `run` with `R901`, not half-run;
- one test per rule: copy a clean example, introduce exactly one mistake,
  assert the rule's code is reported;
- a guard that fails if any diagnostic code has no such test.

### What is enforced today

| Rule | Source | Code |
| --- | --- | --- |
| Lexical rules: whitespace, control characters, strings, quotes, `#` | LR-11, A23 | R101-R106 |
| An entity's rows follow its `is` row without interruption | D-14 | R201 |
| Known kinds, unique names, case by kind, reserved words | A5, D-3 | R202, R203, R206, R207 |
| Every predicate allowed on its kind, with its exact shape | LR-09, LR-18 | R204, R205 |
| Skeleton order, exactly-one and one-or-more rows, `none` alone | LR-18, A1, A13, A22 | R301-R303 |
| `purpose` where required, invariants on operations only, filler text | LR-06, A17, D-4, D-5 | R304 |
| Every block declares `loopKind` and `within`, in block order | A13, D-6 | R305 |
| Tables: declared rows, every cell exactly once, typed values | LR-26, A21 | R306 |
| Every name resolves, to the right kind | LR-02, LR-32 | R401, R402 |
| Imports: prefixed names, no unused or missing imports, exports | LR-32, A3 | R404 |
| Types agree everywhere a row states one | LR-05 | R403 |
| Arguments match the target's parameters, in order, with paired modes | LR-31, D-7, D-8 | R405, R406 |
| `out`, `catch`, `ownedBy`, `borrows`, `cleanedBy` agree with the target | LR-20, LR-31 | R403, R409 |
| A cleanup's call takes the cleaned value with `give` | LR-20 rule 6 | R409 |
| Declared effects equal performed effects, transitively | LR-07, D-11 | R407 |
| Every effect granted by a used capability; no idle capabilities | LR-07 | R408 |
| `async`, `memory heap`, `maxRecursion` state exactly what the code does | D-11 | R410 |
| A waiting target is a task | LR-33 | R410 |
| One namespace per operation | LR-02, D-15 | R411 |
| Blocks: contiguous, `begin` first, one terminator, `match`/`case` | LR-16, A6, A13 | R501 |
| Jumps go to existing blocks; every block reachable | LR-16 | R502, R511 |
| Loop facts belong to loop headers; bounds stated; `forEach` shape | LR-22, LR-23 | R503 |
| Single entry into loops; every cycle passes a declared header | LR-23, A19 | R504 |
| A counted loop sets its counter exactly once on every pass | A14 | R505 |
| A fallible `do`/`join` is followed at once by `branch ifError` | LR-16, LR-30 | R506 |
| Each call, task, and cleanup activated the right number of times | D-10 | R510 |
| Every value set on every path that reads it, with types checked at each use | LR-04, LR-29, A4 | R507 |
| `return ok` / `return error` agree with `output` and `raises` | LR-30 | R508 |
| `match` covers every variant once; bindings mirror payloads | A6, D-9 | R509 |
| Tasks and task groups settled on every path to a return | LR-33, A12 | R512 |
| build.sem, module file locations, import cycles, `verifies` targets | LR-32, D-13 | R601-R604 |

### Not enforced yet

Each line is a rule from this file that the checker does not yet check. Until it
does, the rule is a stated fact that is not verified, so closing these is the
next work.

1. **Per-path ownership.** An owned value is released, given, or returned
   exactly once on every path (LR-20 rule 6). Today: only "given or returned
   somewhere" when `cleanedBy none`.
2. **Use after `give`**, and borrowed values that are stored or returned
   (LR-20 rules 6 and 8).
3. **Every invariant is verified by a test** (LR-06 rule 3). Today only that
   each `verifies` names a real operation and invariant.
4. **`maxIterations` equals a constant trip count**, and the `counted` header
   tests its counter against an immutable limit (A14).
5. **Run-time enforcement** of `maxIterations` and `maxRecursion`. The bridge
   runs programs without these traps.
6. **Staleness flag** for context rows (LR-06 rule 4).
7. **Capability `scope`** against literal arguments (LR-34 rule 5).
8. **`<Record>.with`**, generic operations, and `typeParam` constraints
   (LR-24, LR-28).
9. **Library signatures** for `map`, `set`, `buffer`, `fs`, `process`, `clock`,
   `environment`, and channels (LR-40). Today `library.py` covers what the
   worked examples use.
10. **A backend** for regions, tasks, records, enums, tables, and errors. The
    bridge runs only the plain subset.

### Decisions made while implementing

- **D-1** The refined front end is a separate package; the legacy compiler
  retires after the corpus migrates.
- **D-2** Every record and enum states `typeParam none` when it is not generic,
  and every alias states `indexes none` when it indexes nothing. Same reason as
  A1 and A13: no fact by absence.
- **D-3** Type names (records, enums, aliases, instances, operation types) start
  upper-case; every other name starts lower-case.
- **D-4** `invariant` rows live only on operations. A test's `verifies` names
  an operation, so an invariant anywhere else could never be verified; this
  resolves a conflict between LR-06 rule 1 and A17.
- **D-5** Context rows come in a fixed order: `purpose`, `invariant`,
  `verifies`, `rationale`, `risk`, `note`, `todo`, `deprecated`.
- **D-6** Label rows are grouped per label, in the same order as the blocks,
  each label's facts in the order `loopKind`, `within`, `maxIterations`,
  `counter`, `over`, `because`, then its context rows.
- **D-7** Arguments appear in the target's parameter order.
- **D-8** The passing mode follows the type. Plain values are `value` / `copy`
  (including reading a field of a plain record); a `Region` is always
  `borrowed` / `lend`; non-plain values are `borrowed`, `borrowedMutable`, or
  `owned`.
- **D-9** A `case` binding mirrors its variant: `bind none none` exactly when
  the variant has no payload. A payload is always bound, even if unused.
- **D-10** A task started into a task group is settled by the group: it is not
  joined itself, and it states `out none` and `catch none` because its result
  cannot be read.
- **D-11** Declared facts are exact in both directions: an `effect` row with
  nothing behind it is as wrong as a missing one, and likewise `async true`,
  `memory heap true`, and `maxRecursion <n>`.
- **D-12** Tests live in `<module>.test.sem` beside the module and are part of
  it; the module imports what its tests use (for example `standard.test`).
- **D-13** `build.sem` holds one `project` entity: `target console|library`,
  one `module <path>` row per module, and `entry <module>.<operation>` or
  `entry none`. A module with path `a.b` lives in `a/b.sem` beside build.sem.
- **D-14** An entity's rows follow its `is` row without interruption.
- **D-15** Within one operation, labels, values, and owned entities share one
  namespace, and none may reuse a module-level name.

## Part 5: everything enforced, own backend (2026-11-13)

The owner asked to enforce every rule Part 4 listed as not enforced, to keep
going, and then: **no bridge, no backwards compatibility.** This part records
what changed. Where it conflicts with Part 4, this part wins.

### Direction

- **No bridge.** The lowering to the earlier compiler is deleted. The refined
  compiler generates LLVM IR from its own checked model
  (`semanticscript/compiler/refined/codegen.py`) and runs it with its own JIT
  runtime (`runtime.py`). It imports nothing from `semanticscript.py`.
- **No backwards compatibility.** Nothing is kept or built to stay compatible
  with the earlier syntax. Plan step 10 (migrate the corpus) is replaced by:
  *remove the earlier compiler, its 245 examples, its tests, and its CI lanes,
  and point CI, packaging, and the editor extension at the refined compiler.*
  That removal has not been done yet.
- The library table no longer carries names from the earlier backend.

### Commands

```
python semanticscript/compiler/refined check   <module.sem | build.sem | dir> [--json]
python semanticscript/compiler/refined run     <build.sem | dir> [--json]
python semanticscript/compiler/refined test    <build.sem | dir> [--json]
python semanticscript/compiler/refined emit-ir <build.sem | dir> [--test MODULE.TEST]
python semanticscript/compiler/refined stale   <path> --base <git revision> [--json]
python semanticscript/compiler/refined grammar
```

`test` runs each test in its own process, so a trap ends only that test, and
reports PASS, FAIL (with the failed assertions), TRAPPED (with the trap
message), or UNSUPPORTED (with the backend's R901 diagnostic).

### Part 4's open list, closed

| # | Rule | Now |
| --- | --- | --- |
| 1 | Owned value released, given, or returned exactly once on every path | Enforced: a per-path analysis tracks each owned value as not acquired, owned, under a deferred cleanup, or given. Leaks at a return, a second acquisition over a live value, giving a value under a cleanup, and returning it are R513. |
| 2 | Use after `give`; borrowed values stored or returned | Enforced: R513 for use after give; R514 for giving or returning a borrowed input or a view; R515 for exclusive loans of shared or read-only values. |
| 3 | Every invariant verified by a test | Enforced (R604). |
| 4 | Counted-loop header shape and exact constant trip count | Enforced (R505); see D-23. |
| 5 | Run-time `maxIterations` and `maxRecursion` | Enforced by the backend; both trap with a message naming the source. |
| 6 | Staleness flag | `refined stale` (R605); see D-17. |
| 7 | Capability scope | Enforced (R408); see D-22. |
| 8 | `Record.with`, generic operations, type-parameter constraints | Enforced; see D-18 to D-20. |
| 9 | Library signatures | Added for console, math, compare, bits, convert, string, byte, buffer, time, clock, environment, process, fs, net, http, list, map, set, option, channel, test. |
| 10 | A backend | The refined compiler's own LLVM backend; coverage below. |

### Backend coverage

Runs today: integers with overflow and division traps, `Byte`, `Bool`,
`ExitCode`, `Float64`, `String` literals, records, enums (payloads that are
integers, `Bool`, `Byte`, or payload-less enums), tables walked by `forEach`,
`match`/`case`, operations that raise and `return error`, `branch ifError`,
operation references, recursion with `maxRecursion`, loops with
`maxIterations`, regions (arena with enforced capacity, freed at return),
`list.List`, `option.Option`, cross-module calls, and these library targets:
`math`, `compare`, `bits`, `convert`, `console` writes, `string.byteLength`,
`byteAt`, `equals`, `startsWith`, `byte`, and `test`.

Refused with R901 for now: tasks, task groups, and every target that waits
(`net`, `fs` reads and writes, `console.readLine`, `time.sleep`, `channel`);
cleanups and `defer`; generic operations and `operationInstance`; strings
allocated at run time (`string.concat`, `fromInt64`, `fromBytes`, `buffer`);
`map`, `set`; `process`, `clock`, `environment`; `http`.

Worked examples:

| Project | Check | Run / test |
| --- | --- | --- |
| hello | clean | runs: `Hello, world!`; 1 of 1 tests pass |
| sum | clean | runs: `15` |
| factorial | clean | runs: `120`; 1 of 1 tests pass |
| selfhost (lexer, tokenizer) | clean | 5 of 5 tests pass |
| server | clean | refused: tasks are not supported yet |

### Tests

`tests/test_refined.py` has 96 tests, all passing: every worked example checks
clean; every rule code has a test that breaks a clean example and gets that
code; generic operations and `Record.with` check clean and fail on misuse;
`stale` flags a structural change without a prose change; the example tests
pass on the backend; the backend reports a wrong expectation as FAIL with the
values and a low loop bound as TRAPPED with the loop named; `run --json`
captures output.

### Decisions in this pass

- **D-16** A project's entry operation may state `invariant none`. Its
  behavior is the whole program's, checked end to end, not by a unit test.
  Every other exported operation still makes a tested claim.
- **D-17** The staleness flag is a command, not a compile error: `stale`
  compares with a git revision and exits 1 when it flags anything. An author
  re-confirms unchanged prose by adding a `note` row that says why it still
  holds.
- **D-18** Every operation states `typeParam` (`none` when not generic), for
  the same reason as D-2. A generic operation is called only through an
  `operationInstance` entity (`<name> instantiates <operation> <Type>...`),
  never directly. A test is never generic.
- **D-19** A type parameter's constraint is part of its type: `plain`
  parameters are copied (`value`), `any` parameters are borrowed. An
  instantiation whose argument breaks a `plain` constraint is an error.
- **D-20** `<Record>.with` takes `record`, then exactly one slot named by the
  field it replaces.
- **D-21** The backend's runtime surface is a fixed set of callbacks (output,
  byte comparison, traps, test assertions, regions). A trap writes
  `trap: <file>:<line>: <message>` to standard error and exits with code 70.
- **D-22** Scoped resources are `net.tcp` (scope `"<address>:<port>"`, checked
  against the port), `net.outbound` and `fs.files` (scope is a prefix), and
  `process.programs` (scope is the exact program). A capability's grants are
  all scoped the same way; everything else is `scope none`.
- **D-23** A counted loop's header is `do <check>` then `branch if <result>`,
  where the check is `compare.lessThanInt64`, `lessOrEqualInt64`,
  `greaterThanInt64`, or `greaterOrEqualInt64` of the counter against an
  immutable limit. The single `set` of the counter takes the result of
  `math.addInt64` or `math.subtractInt64` with the counter as `left` and an
  immutable non-zero step as `right`. The counter must move toward the exit,
  and when the start, limit, and step are all literals, `maxIterations` must
  equal the number of passes.

### Next

1. Remove the earlier compiler and switch CI, packaging, and the editor
   extension to the refined compiler (the replacement for plan step 10).
2. Backend: cleanups and `defer`, run-time strings in regions, `map` and
   `set`, then tasks and task groups on a cooperative scheduler, then `net`
   and `http` so the server runs.
3. A formatter (`fmt --check` is part of the strict gate, LR-01) and the editor
   grammar generated from the shape table.
4. Plan step 12: the agent-writability evaluation, now that a model's program
   can be checked, run, and tested end to end.

## Part 6: the earlier compiler removed (2026-11-13)

At the owner's request ("remove it"), everything that belonged to the earlier
toolchain was deleted. There is no compatibility layer and no migration; the
code remains in git history before this change.

Removed:

- the earlier compiler (`semanticscript/compiler/semanticscript.py`), its
  standard library (`semanticscript/std`), signatures (`semanticscript/sigs`),
  C runtime (`semanticscript/runtime`), and packaging;
- `examples/` (245 programs), `apps/`, `experiments/`, and `legacy/`;
- vendored third-party C sources (`third_party/`: sqlite, libuv, bcrypt, and
  the h2o and emsdk submodules), which only the C runtime used;
- the earlier test suite (every file in `tests/` except `conftest.py`), the
  audit scripts in `tests/audit/` (they measured the earlier compiler; the
  explicitness-audit numbers below are kept as history), and the coverage
  config;
- the earlier docs: `LANGUAGE.md`, `GRAMMAR.md`, `ROADMAP.md`,
  `GOVERNANCE.md`, `getting-started.md`, `todos.md`, `defect-ledger.md`,
  `security-matrix.md`, `design-bounds-carrying-buffers.md`, and
  `human-authoring-validation.md`;
- CI workflows for the earlier toolchain: compiler executable, native safety,
  runtime platform, release, and the project website.

Changed:

- **CI** (`.github/workflows/ci.yml`) runs the refined test suite on Windows
  (Python 3.11 and 3.12) and Linux, checks every worked example, and fails if
  `docs/refined-grammar.md` or the editor grammar is out of date. The Windows
  job names are unchanged, so the branch-protection checks still match. A
  separate job checks the editor extension. CodeQL analyzes Python and
  JavaScript only.
- **Editor extension** rewritten (about 150 lines, from 5,800): its grammar is
  generated from the shape table (`refined grammar --textmate`), diagnostics
  come from `refined check --json` on save, and it has Check, Run, and Test
  commands and skeleton snippets.
- **README, CONTRIBUTING, CHANGELOG, THIRD_PARTY_LICENSES** describe the refined
  compiler only. Dependabot watches pip, GitHub Actions, and the extension.
- Plan step 10 (migrate the corpus) is done by removal; plan step 1's promise
  that one table drives the parser, the grammar reference, and the editor
  grammar is now true.

Not done: a release workflow and packaged binary for the refined compiler, and
a Marketplace publisher for the extension.

## Part 7: the test suite (2026-11-14)

The owner asked for a clear and powerful test suite, aligned with the language,
covering positive, negative, and edge cases, to find and fill gaps. It lives in
`tests/suite` and runs as `tests/test_suite.py`; `docs/test-suite.md` is now a
generated coverage map of the owner's checklist (456 items), each with a status
and the cases that prove it.

What it holds:

- **Program cases** (`tests/suite/programs`, one directory per checklist
  section): complete programs whose header comments state what they cover and
  what must happen: check clean, run with exact stdout, stderr and exit code,
  trap with a message, pass or fail their tests, or be refused by the backend
  with R901 (`unsupported`, so the case fails the day the backend learns the
  feature).
- **Mutations** (`tests/suite/mutations.py`): one deliberate mistake in a
  passing case and the exact set of rule codes it must produce. Every rule code
  except R605 (needs git history) and R901 has at least one.
- **Generated tests**: stress (2,000 values in one operation, a chain of 1,000
  operations, 300 nested decisions, a 200,000-byte string, recursion 200,000
  deep, a 500,000-item list, 40 modules in a chain), fuzz (random damage to
  every single-file case must give diagnostics with known codes and real lines,
  never an exception), differential (random `math` and `bits` arithmetic
  against a Python model, traps included), determinism, source locations, and
  the CLI.

What it found, and what changed:

| Found | Kind | Fix |
| --- | --- | --- |
| A row that broke its shape (`main let ten immutable 10`) crashed the checker with an `IndexError` | checker crash | Rows are reported, then dropped before later passes; a malformed row only ever produces diagnostics |
| A nested counted loop could not restart its counter: only the loop may set it, so the inner loop of `for i, for j` was inexpressible; entering an inner loop from its outer loop was also reported as a jump back (R504) | language gap | D-24 below; the R504 back-edge test stops at the headers of enclosing loops |
| `string.slice` with a huge length overflowed `start + length` and passed the bounds check, giving a view far past the end of the string | memory safety | The check compares without forming the sum |
| Recursion within a large stated `maxRecursion` overflowed the native stack and killed the process with no message | safety | D-25 below |
| `math.powerInt64` multiplied once per unit of exponent, so `1` to the power `10^18` effectively never finished | denial of service | Square-and-multiply: at most 63 rounds; same overflow traps |
| `math.saturating*Int64` passed the checker but the backend refused them | backend gap | Implemented |
| A project module named like a standard module (`clock`) produced a self-import cycle and misleading errors | language gap | D-26 below |
| A call into a project module that failed to load said "the standard module `area` has no target" | diagnostic | Says the module is not part of the project |
| A reserved word or an upper-case name in a `let` gave only a generic shape error | diagnostic | R206 and R207 name the slot when it is the only thing wrong |
| `run` on a lone module file reported that module's other errors instead of "needs a project" | CLI | `run`, `test`, and `emit-ir` report the missing project first |

Decisions (by delegation):

- **D-24** A counted loop's counter may also be set by a block outside the loop
  when that block enters the loop directly (its last step is `goto <header>`)
  and sets the counter from an immutable `Int64` let. The constant trip count
  is computed for every such start value, and `maxIterations` states the
  largest, counted per entry. This is how a nested counted loop restarts.
- **D-25** Compiled code runs on its own thread with a 128 MiB stack. Every
  operation with a `maxRecursion` bound checks, on entry, that more than 8 MiB
  of that stack remains, and traps with "ran out of stack before reaching
  maxRecursion N" when it does not. `maxRecursion` is still the declared bound;
  the stack check makes an unrealistic bound a clean trap instead of a crash.
- **D-26** A project module may not take the name of a standard module (R602),
  since `<name>.<target>` would be ambiguous.

Open work is listed at the end of `docs/test-suite.md` (every `gap` and
`static` item). The largest: tasks, cleanups, `map` and `set`, generic
operations, and the host-I/O modules do not run in the backend yet; there is no
foreign function interface, formatter, language server, debugger support, or
package versioning.

## Part 8: everything compiles and runs (2026-11-14)

The owner asked to compile and run every program. Before this part, twelve
suite cases and the server example were refused by the backend (R901). Now
every positive and edge program in the suite runs (a test enforces it), every
worked example runs or passes its tests, and the server answers real HTTP
requests.

What the backend gained:

- **Generic operations**, compiled once per set of type arguments an
  `operationInstance` names (direct calls and operation references).
- **Cleanups and `defer`**: an armed cleanup runs at every later `return`,
  newest first, at most once; `onFailure trap` traps if its call fails.
- **Tasks, task groups, channels, async operations** (D-27, since replaced by D-31).
- **Host targets** through one callback (D-28): `console.readLine`,
  `time.sleep` and deadlines, `clock`, `environment`, `process` (arguments and
  running programs), `fs`, `net`, `http`, `buffer`, `string.fromBytes`, and
  `map`, `set`, and `channel` values.
- `string.toBytes` (a view, no copy); `Bytes` values; handles for resources
  and host-kept values; `refined run PATH -- <arguments>`.

Decisions (by delegation):

- **D-27** (replaced by D-31 below) Tasks run eagerly: `start` runs the task to completion, in program
  order, on the program's thread; `join`, `cancel`, and `awaitSlot` then have
  nothing to wait for. Programs written for real concurrency stay correct
  (the checker's structure rules are unchanged), and runs are deterministic.
  The cost: nothing overlaps, and a channel wait that only another task could
  satisfy cannot be satisfied. Such a wait traps as a deadlock when it has no
  deadline, and waits the deadline out (then fails with `timedOut`) when it
  has one. A real scheduler can replace this without changing the language.
- **D-28** Library targets that need the operating system are lowered to one
  runtime callback, `refined_host`. Arguments are flattened into 64-bit slots
  by machine type (an integer is one slot, a string or byte string is pointer
  and length, an enum is tag and payload, a record is its fields), and the
  runtime dispatches by target name (`semanticscript/compiler/refined/host.py`).
  Values the host keeps (files, sockets, maps, sets, channels, buffers,
  argument lists, responses) are integer handles. A handle made in a region is
  dropped when the region is released; using a dropped or closed handle traps.
- **D-29** `net.listen` binds the host named in the scope of the capability
  that grants `listen net.tcp`. The server example's scope is now
  `"127.0.0.1:8080"`, so running it never opens a port to the network;
  widening the scope is the explicit way to serve beyond loopback.

- **D-30** An enum whose payloads are all integers, `Bool`, or payload-free
  enums keeps the compact layout `{tag, 64-bit payload}`. Any other enum (an
  `option.Option String`, a variant carrying a record, a list, or another such
  enum, an error carrying a message) has a wide layout: the tag, then one field
  per variant that carries a payload. `equals` is structural for every type:
  records field by field, enums by tag and the active payload, lists element by
  element, text and bytes by content, host values by identity.

- **D-31** (replaces D-27) Tasks run in parallel. `start` fills a frame with
  the task's arguments and hands the runtime a generated thunk that runs the
  task on its own thread; `join` waits and reads the results back from the
  frame. A task group runs at most `limit` tasks at once; `awaitSlot` waits for
  room, and starting into a full group traps (A12). Cancellation is
  cooperative and reaches every task a cancelled task started: waits on
  channels, sleeps, accepts, and socket reads end with `cancelled`; pure
  computation runs to its end, and `cancel` waits for the task to stop. When
  every task waits on another with no deadline, the program traps and names
  each wait. Recursion depth and the stack floor are kept per thread.
- **D-32** `fs` gains `openAppend` (write at the end, creating the file if
  missing), `createDirectory`, `removeDirectory`, and `listDirectory` with
  `entryCount` and `entryName` (names in sorted order, region-owned).

Nothing a clean program can contain is refused any more. R901 stays as a guard:
a library target the backend does not implement is refused by name, never
miscompiled (`test_unknown_library_target_is_refused_not_dropped`). The suite
proves the rest: every operation and test of every program and worked example
compiles (`test_every_operation_compiles`), every program case runs
(`test_every_program_case_runs`), and a tour calls every standard-library target
no other case uses (`tests/suite/programs/19-stdlib/library-tour.sem`).

## Part 9: the checklist closed (2026-11-14)

After Part 8 the coverage map still listed 44 gaps. All but one are now
implemented and tested; `docs/test-suite.md` has the evidence for each.

- **Library:** `random`, `crypto`, `log`, `json` (parse, typed access, build,
  `stringify`), `secret`, `signal`, `fs.lock`/`unlock`, `fs.openAppend` and
  directory operations, `process.runCaptured` (pipes).
- **Runtime:** parallel tasks (D-31); a trap prints the chain of callers.
- **Tooling:** `refined fmt`, `repl`, `lsp`, `bench`, a build cache, and
  `run --trace`, `--coverage`, `--profile`, `--debug --break`.
- **Native:** `refined build` emits objects or assembly for any LLVM target,
  or WebAssembly that `tests/suite/wasm_host.mjs` runs in Node.
- **Interop:** the `ffi` module.
- **Packages:** versions and local packages in build.sem.

Decisions (by delegation):

- **D-33** A new effect verb, `load`, for bringing native code into the
  process. `ffi.open` needs `load ffi.libraries`, scoped by library name.
  A foreign function's type is an `operationType` over numbers and `Bool`
  that raises nothing, waits for nothing, and has no effects; only values the
  C ABI passes as they are cross, so no memory is shared across the boundary.
- **D-34** build.sem states `version "<MAJOR.MINOR.PATCH>"`, `language
  refined-1`, `standardLibrary 1`, and `requires <name> "<path>"
  "<constraint>"` (or `requires none`). A required project is a library whose
  version satisfies the constraint; its modules are imported as
  `<name>.<module path>`. Requirement cycles are R603.
- **D-35** A `secret.Secret` has no route back to text but `reveal`, which
  needs `read secret.values`; a program that must not leak a value keeps it a
  Secret.
- **D-36** The formatter changes layout only: token spacing, blank lines
  between entities, the space before a trailing comment. Comment text is
  kept exactly.

- **D-37** `refined build --kind executable` links the program's object, a C
  runtime (`native_runtime.c`: output, regions, traps with stack traces, the
  call stack, recursion and stack guards, tasks run when started), and a
  generated `main` with the system C compiler, statically where the platform
  allows. Library targets that need the operating system host stay in the JIT
  runtime; in an executable they trap with the target's name.

Every checklist item now has evidence or a stated reason.

## Part 10: adversarial refinement (2026-11-14)

An adversarial critic was asked to break the language: to write programs the
checker accepts but that are wrong, and to find rules that are vague,
inconsistent, or unenforced. Each round's findings were fixed, then the critic
ran again. Findings fixed in the first round:

- Loans to tasks: a task holds every loan it was given from `start` to `join`
  (D-39). Giving, setting, or lending mutably a value a running task holds is
  R515; so is changing a collection inside a `forEach` over it.
- Task lifetime: starting a task that may still be running (for example in a
  loop with the join after it), joining twice, and joining or cancelling a
  task that is not running are R510.
- Scope checks: a network scope is a prefix only up to a `:` or `/` boundary,
  so `"api.test"` no longer admits `"api.test.evil.example"`. A literal path
  with a `..` component is R408.
- Tests: a test that `verifies` an operation it never calls, or that calls no
  `test.` assertion, is R604.
- A cleanup whose call is not the `cleanedBy` of the value it releases is R409.
- A malformed row no longer also reports its predicate as missing (R302).

Decisions (by delegation):

- **D-38** Capability scopes are enforced again at run time: a scoped argument
  that is computed, not a literal, is checked before the call against the
  scopes of the capabilities the operation uses, after `..` and links are
  resolved. Outside every scope is a trap naming the argument and the scopes.
- **D-39** A task's loans last from `start` to `join` (or `cancel` then
  `join`); the collection of a `forEach` is lent for the whole loop.
- **D-40** A `let` initialized from a name copies only plain values (R514); a
  second name for a String, list, or record would carry a borrow past its
  loan. A resource (a file, a socket, a library) cannot be stored in a
  collection (R403), because a region releases a collection without closing
  what is in it. `ExitCode` is 0 to 255, what every platform delivers.
  `secret.matches` and `secret.length` need `read secret.values`, since both
  reveal something about the secret. `fs.close` needs no authority beyond
  owning the handle. A standalone executable is refused (R901) when the
  program calls a host-library target, instead of trapping when it runs
  (amends D-37).
- **D-41** build.sem states the program's whole authority in `allows` rows,
  the same `<verb> <resource> <scope>` triples capabilities grant
  (`allows none` when it needs none). Every capability in every module grants
  only what an `allows` row covers, with a scope inside the allowed one
  (R408). A required package states what it needs in its own build.sem, and
  the program requiring it must allow that too, so the project file is the
  one place to audit what a program may do. A foreign function is authorized
  by name: binding needs `load ffi.symbols` scoped to that symbol. An
  `fs.files` scope says which kind it is: a directory ends in `/`
  (`"data/"`: anything inside it), a name pattern ends in `*` (`"suite-*"`:
  entries of the current directory whose names start with `suite-`). Any
  other scope is R408. Tools that write a build.sem for code they did not
  write (the REPL, the test harness) derive the `allows` rows from the
  capabilities in it.
- **D-42** Every error a waiting target raises has a `cancelled` variant
  (`console.ReadError`, `process.RunError`, `fs.FileError`), and every wait
  honours its deadline: `readLine` and child processes stop waiting at the
  deadline or on cancellation, and a file read or write made after its
  deadline, or by a cancelled task, does not start. A negative duration given
  to `time.Deadline.after` or `time.sleep` traps instead of counting as zero.
  `process.runCaptured` output larger than `maxBytes` is
  `process.RunError.tooLarge`, not a numbered `failed`.

- **D-43** A target that changes the state of the handle it is given (a
  file's position or lock, a connection's stream, a listener's queue) takes
  it `borrowedMutable`: `fs.read`, `fs.write`, `fs.lock`, `fs.unlock`,
  `net.accept`, `net.read`, `net.write`. Two activations can never use one
  handle at once. A channel stays a shared loan: it is a synchronized queue
  that exists to be used by several tasks.
- **D-44** `cancel` asks a task (and every task it started) to stop and
  returns at once; `join` waits for it and delivers its outcome. Every
  started task is joined on every path, cancelled or not, and its loans last
  until that `join`. There is no detached task. (Replaces the part of D-31
  where `cancel` waited.)
- **D-45** A `forEach` over a table states a `maxIterations` at least the
  table's row count, checked when the program is checked; over a list,
  passing the bound traps at run time.
- **D-46** Capabilities are never exported (R402).

- **D-47** One pattern for the whole syntax (the owner: "don't simplify
  syntax, make sure it has a consistent pattern"). Nothing becomes implicit;
  rows that said the same thing two ways now say it one way:
  - one word for "why": `rationale` (the cleanup row and the `forever` label
    fact `because` are gone; every cleanup states a `rationale` context row);
  - context rows lead everywhere: a label's `purpose`/`rationale`/`risk`/
    `note`/`todo` come before its `loopKind`, as an entity's do after `is`;
  - `let <name> <Type> <value> <mutability>`, slot for slot like
    `argument <slot> <Type> <value> <mode>`, and `let none` when there are
    none (every `some` predicate states `none` rather than being absent);
  - `grants <verb> <resource> <scope|none>`: each grant carries its scope,
    the same triple as `allows` (the capability `scope` row is gone);
  - parameter modes `copied`/`borrowed`/`borrowedMutable`/`owned` pair with
    argument modes `copy`/`lend`/`lendMutable`/`give`;
  - single-word predicates: `memoryHeap`, `outputOwnedBy` (beside `ownedBy`),
    `onError` (errors are never called failures), `runs` for a cleanup's call;
  - bounds are `max<Thing>`: `maxIterations`, `maxRecursion`, `maxBytes`
    (region), `maxTasks` (task group);
  - full words: `argument`, `result`, `typeParameter`;
  - `start <task> into <group|none>` always states its group;
  - type kinds alike: `typeInstance` (beside `operationInstance`),
    `aliasOf`, `rowType`, and `typeParameter` on every type kind; `alias`
    states a `purpose`;
  - build.sem: `includesModule <path>` (a kind name is no longer a
    predicate) and `language refined 1` (a name and a number, like
    `standardLibrary 1`).
  Not changed, on purpose: `raises`/`uses` keep their verbs, and loop-only
  label facts stay on loop headers. Rows in Parts 1 to 10 show the syntax of
  their time; `docs/refined-grammar.md`, generated from the shape table, is
  the current reference.

- **D-48** Failure propagates through task groups. A group states the one
  error type its tasks raise (`<group> catch <name> <Type>`, or `catch
  none`); a fallible task may be started into it only if it raises that type
  (R403). The first task to fail records its error in the group and cancels
  the group's other tasks; `join <group>` waits for every task and delivers
  that error, and is followed directly by `branch ifError <group>` (R506).
  Later failures are dropped, since every task already stopped for the first.
  (Replaces D-10's rule that grouped tasks state `catch none`.)
- **D-49** Running out of a region is a safe trap, not a typed error. The
  trap happens before any memory is written and names the region and its
  capacity. A typed error would make every allocating target fallible,
  so every string, list, and read would need an error branch for a limit the
  program states itself; the program sizes its regions instead. (The goal's
  item 6 allows typed errors or safe traps; this is the second.)
- The authoring-syntax items of the same goal (inferred defaults, a concise
  syntax over the rows) were replaced by the owner's instruction "dont
  simplify syntax, make sure it has a consistent pattern"; D-47 is that
  consistency pass.

- **D-50** Task state is checked on every path, not on some: a `join` or
  `cancel` needs its task started and not yet joined on each path that
  reaches it (R510). A block reached both after a join and without one is
  rejected, so no path joins a task twice or joins one it never started.
- **D-51** After a trap no program code runs, so deferred cleanups are
  skipped: the state that trapped may be the state they would act on. The
  runtime then releases what the program holds outside it (files flushed and
  closed, connections and listeners closed, child processes stopped) and
  says how many in the trap message, before exiting with 70.
- **D-52** Independently opened handles can name one file, so the runtime
  guards it: a file, under any name (links and `..` resolved), is open for
  writing by at most one handle and never while another reads it; readers
  share it. A conflicting `open*`, `readAll`, `writeAll`, or `remove` fails
  with the new `fs.FileError.busy`.
- **D-53** Declaring authority does not grant it. `refined run`, `test`,
  `bench`, and executable builds start only when every `allows` row of
  build.sem is listed in the project's `authority.approved`, written by
  `refined approve` after review; otherwise they stop with exit 3 naming the
  rows. The REPL approves its own session (its user typed the capabilities)
  and prints what it grants; the test harness approves the programs it
  generates.
- **D-54** A dropped failure states exactly what it drops. Every call, task,
  and task group has `suppresses` rows: `none` when its failure is handled,
  and every variant of its error type when it is discarded (both `ifError`
  arms to one block, or a cleanup under `onError suppress`), next to the
  `rationale`. A variant added to an error type later breaks every discard
  that does not name it.
- **D-55** Allocation a program can recover from: `arena.remaining(region)`
  and `arena.ensure(region, bytes)` (failing with
  `arena.ArenaError.exhausted`, carrying the bytes left) let a program ask
  before a step that allocates. Passing a region's capacity unasked still
  traps (D-49).
- **D-56** A loop's bound may be computed at run time, such as a list's
  length: any immutable `Int64` value set on every path into the loop before
  its first pass, back edges included (R507). A value first set inside the
  loop cannot bound it.

- **D-100** Positions are sound. Every list gets an identity when it is
  made; a position from an indexed list carries that identity in its high
  bits, and `get`, `set`, `getOrTrap`, and `replace` refuse a position from
  any other list (`list.IndexOutOfRange`). An indexed list only grows: it
  has no `clear`, `removeLast`, or `truncate`, so a position never names a
  slot that was emptied and reused. `<Alias>.toInt64` gives a position's
  number for printing and as a key; there is no way back. (Corrects D-60,
  whose promise did not hold after `clear`.)
- **D-101** Trapping twins: `<List>.getOrTrap` and `string.byteAtOrTrap`
  trap on a bad index instead of raising, for indexes the program has
  already proved in range. They are separate, explicitly named targets, on
  the reasoning D-49 uses for region limits; the fallible targets stay.
- **D-102** A list of plain items is a stack too: `removeLast` (an empty
  list raises `list.IndexOutOfRange`) and `truncate`.
- **D-103** Module constants: `<name> is constant` with `type` and `value`
  rows. Every operation of the module reads it as an immutable value set on
  entry; the value is a literal of its type (R403), it cannot be set, and no
  operation may reuse its name (R411).
- **D-104** A table is a fixed array: `<table>.length`, and `<table>.rowAt`
  reading a row by the number its `row` row gives it (1 to n, as R306
  numbers rows); any other number raises `list.IndexOutOfRange`.
- **D-105** Changing what a list holds: `<List>.replace` puts a new item in
  and hands the old one back owned (for items that are not plain values, as
  a value of the list's region, which the call names and the runtime
  checks). A list or record held in a list is changed by replacing it with
  a fresh one, changing it, and putting it back; no new loan kind.
- **D-106** The checker indexes an entity's rows by predicate and a module's
  owned entities by owner, caches a module's names, and lexes plain words
  without per-character checks. A module of 4,000 operations (172,000
  rows) checks in about 2 seconds instead of growing quadratically.

- **D-107** A collection outlives what it stores only if what it stores lives
  in its region. Found while reviewing D-105: an operation could make a list
  in its own region, store it in its caller's list, and return, leaving the
  caller's list holding released memory; text stored the same way had the
  same flaw. Now text, and text inside records and enum payloads, is copied
  into the collection's region when it is stored (lists inline; maps, sets,
  and channels through the region the runtime records for each of them). A
  value that holds a list, map, set, or channel cannot be copied that way,
  so it must come from a call whose `ownedBy` names the collection's own
  region, in the same operation (R514); an operation that builds such a
  value for its caller returns it, allocated in a region the caller passes.

- **D-108** A value is safe only in the region it is said to live in. An
  adversarial review of D-107 found five ways around it, closed together:
  a result is returned in the region its `outputOwnedBy` names, so text in
  it is copied there at the return, and a list, map, set, or channel in it
  must have been made there (R514); an error carries only plain values,
  because nothing names a region for it (R403); a type parameter that is not
  `plain` may stand for a container, so a generic operation stores its values
  under the same proof as a concrete one; a `set` takes no value that is not
  plain from a view or a borrowed input (R514), which had let a view be
  laundered into a value that outlived its list; and a resource is never a
  record field or an enum payload (R403), so a file cannot escape the
  cleanup and release rules inside a value.
- **D-109** Tools read the program the way the compiler does. `allows` and
  `grants` rows are compared token by token through the lexer, so spacing,
  tabs, or a trailing comment cannot widen authority past `refined approve`
  (exit 3). `run-one-test` needs approved authority like `test` and reports
  an unknown module or test as an error (exit 2). The build cache hashes
  every package a project `requires`, wherever it is. One writer per file
  (D-52) is checked by the file's identity (device and file number) once it
  is open, as well as by its path, so a hard link names the same file; a
  file opened for writing is emptied only after that check. Under the JIT,
  where started tasks run on their own threads, only the first of two
  simultaneous traps is reported, as in an executable.

Writing `stage0`, a compiler for a subset of the language in the language
(`docs/refined-examples/stage0`), ranked what cost the most. D-110 to D-113
answer it within the explicit rule:

- **D-110** `string.contains` tells whether text holds a part, as a `Bool`.
  `string.find` reports a missing part as an error, which made a membership
  test a control-flow branch.
- **D-111** `<table>.find` returns the first row whose first field equals a
  key (`Int64`, `String`, `Byte`, or `Bool`), or raises `list.NotFound`. A
  table's first field is its key; stage0 had written seven near-identical
  scans to look words up.
- **D-112** A module's test file may declare operations its tests share. A
  helper states `invariant none` (the tests that call it are what check it,
  R604), is never exported, and only tests and other helpers call it
  (R402). Before, test-only code had to be exported from the module with
  invariants and tests of its own.
- **D-113** Error propagation stays explicit. Each fallible call keeps its
  `catch` row, its `branch ifError` row, and a label that returns or
  converts the error. A row that merged the branch and the return would be
  the shorthand D-47 rules out, and the explicit form is what lets a reader
  see every path an error takes. The volume is accepted; the remedies are
  shared labels per operation and targets that do not fail (D-110). A
  record's single field is already changed with `<Record>.with` (A10), so
  no new form is needed for that either.

The guarantees these rules add up to are stated, with the executable checks
that prove each one, in `docs/safety-guarantees.md`, generated from
`tests/suite/conformance.py`.

The `warehouse` example (`docs/refined-examples/warehouse`) uses these rules
together: build.sem `allows`, a scoped file capability, a table loaded into
a list, operation references, two tasks borrowing one list, cancellation on
the failure path, a cleanup that traps, exhaustive matches, and a test per
invariant. It has since taken up the later rules: each order line's price
is looked up in a `catalog` table by SKU (`catalog.find`, D-111, with an
unknown SKU handled as exit 7), the report's path and labels are module
constants (D-103), the report read back is checked with `string.contains`
(D-110), and its order tests share a helper in the test file (D-112).
Later still it expands bundles through a bill of materials (a tree of
bundles walked by a bounded recursive operation; a cycle is a handled
error), keeps subtotals per category in a map printed in first-seen order
(D-62), rejects a repeated SKU with a set, and does that through `markNew`,
a generic operation instantiated at `Int64`. All of it in explicit rows.

## stage0 compiles itself (2026-11-14)

stage0 (`docs/refined-examples/stage0`) now compiles its own six modules, and
the compiler it builds compiles them again to the same C (the fixed point,
`tests/test_bootstrap.py`). What that took, decided by delegation; none of
it changes the language, only how the self-hosted compiler reads and writes
a program:

- **D-114** stage0 compiles a project, not a file. It reads build.sem's
  `includesModule` rows and `entry <module>.main`, reads each module's file,
  and checks and writes the modules one after another as one program and
  one C file. Each module is checked with its own names plus the names of
  the modules included above it, spelled `<module>.<name>`; a module may
  not refer to one included below it (it is refused at the name). Every
  name a module declares is written in C as `<module>_<name>`, so modules
  may share names. A diagnostic names the module's file and the line in
  that file. A project that requires another project, or includes a module
  with a dotted path, is refused at build.sem's row.
- **D-115** `string.Position` is a record of the standard library. stage0
  declares it in a module of its own, `string`, which it puts before every
  program's modules, so it is the first declared type (12) and its members
  (`new`, `offset`, `line`, `column`) are ordinary record members;
  `string.advancePosition` is written in C over its fields (D-71's rules).
- **D-116** A map is the host's map in C as under the JIT: each map type
  gets helpers that call `refined_host` with keys `map.Map.<member>|...`,
  its String keys passed as a pointer and a length and its values flattened
  to 64-bit slots exactly as the LLVM backend flattens them (`fl_<Type>` and
  `uf_<Type>` for records and enums). A stored record or enum that holds
  text is copied into the map's region first (D-107). `forEach` over a map
  reads its keys in the order they were first put (D-62).
- **D-117** An operation may raise an error enum of the standard library
  (`raises string.StringIndexError`). Since a program can only branch on
  such an error or pass it on, never match it, stage0 treats every standard
  error as one opaque type and passes its value through the error out
  pointer unchanged.
- **D-118** A value of an `operationType` is a C function pointer of the
  operation signature stage0 writes; a `let` of that type names an
  operation, and `invokesReference` calls through the value. A call of a
  scoped host target (`fs.readAll`, `fs.writeAll`, `fs.createDirectory`,
  `process.run`) passes the scope text the LLVM backend passes (D-38):
  `<verb> <resource>`, then the scope of each grant of it in the
  capabilities the calling operation uses.
- **D-119** 1.0. The bar in `docs/self-hosting-plan.md` holds: stage0, a
  compiler written in the language, compiles its own six modules; the
  compiler it builds compiles them again to byte-identical C (the fixed
  point); everything it builds behaves as under `refined run`, and
  everything outside its subset is refused with a located message. An
  independent audit reproduced each claim by hand. The bar measures
  correctness, not reach, so 1.0 does not wait for stage0 to accept the
  whole suite (14 of 52 programs today); widening it is the next stage.
  The name `stage0` stays: it is the first stage of the bootstrap, and a
  rename would touch every generated file for no change in meaning. The
  safety analyses stay in `refined check`, which every program passes
  first; porting the checker into the language comes after 1.0.

## The runtime in SemanticScript, stage 1 (2026-11-14)

`docs/runtime-in-semanticscript.md` moves the runtime of standalone
executables out of C and links them with no C library. Stage 1 put the
primitive layer in the compiler and wrote the first slice of the runtime
(`semanticscript/runtime`), enough for `hello` and programs of integers,
text, regions, recursion, and traps. Decided by delegation:

- **D-120** The machine and the operating system are reached through two
  standard modules, `machine` and `system`, whose every target performs an
  effect with a new verb, `use`: `use machine.memory` and
  `use system.calls`. Nothing else about authority changes: an operation
  declares the effect and names a capability that grants it, the module
  declares the capability, build.sem allows it, and someone approves it
  (D-53), so a program without them is refused by `refined check` (R407,
  R408) and one whose authority was not approved does not run or build. The
  language still has no raw memory and no system calls; these are for the
  runtime, and every project that reaches them says so in two places a
  reviewer reads.
- **D-121** `machine` has one type, `machine.Address` (a 64-bit address, a
  plain value, `i8*` in the backend), and targets that are each a few
  instructions: `zero`; `offset` by a number of bytes, `difference`,
  `equal`, `lessThan` (unsigned), `toInt64`, `fromInt64`; `load<T>` and
  `store<T>` for `Byte`, `Int32`, `Int64`, `UInt64`, `Float64`, and
  `Address`, at any alignment; `copy` (with memmove's meaning: the ranges
  may overlap), `fill`, and `compare` (-1, 0, or 1, by the first differing
  byte as unsigned) of a range; `addressOfString` and `addressOfBytes`, and
  `stringAt` and `bytesAt`, a view of a range as text or bytes (nothing is
  copied and nothing checks the range stays valid); `stackAddress`, an
  address in the calling operation's own frame, for the stack floor;
  `state`, the first byte of one zeroed static block of 64 KiB
  (`STATE_BYTES`), the runtime's process-wide state, laid out by the
  modules that use it (each module's header says which bytes are its own);
  `callWithAddress`, a call of `void f(void *)` through an address, for the
  thunks the compiler hands the runtime when a task starts; and `runEntry`,
  the exit code of the program linked with the runtime (D-124). A byte's
  length is already `string.byteLength` and `bytes.length`, so `machine`
  does not repeat them. Under `refined run` the targets work as compiled,
  in the JIT's own memory, so the runtime's tests run there too.
- **D-122** `system` has one typed target per operating-system function the
  runtime calls, named after it with a lower-case first letter
  (`system.writeFile` is `WriteFile`), with its C signature: a `DWORD` or
  `BOOL` is `Int32`, a `HANDLE` or pointer `machine.Address`, a `SIZE_T`
  `Int64`. The table is `SYSTEM_CALLS` in library.py: `GetStdHandle`,
  `WriteFile`, `ReadFile`, `ExitProcess`, `VirtualAlloc`, `VirtualFree`,
  `GetCommandLineW`, and `GetLastError` so far; each later stage adds the
  functions it needs (the plan lists them). A call is a direct call of the
  function, imported from kernel32.dll (`dllimport`) in an executable and
  bound to the function already in the process under `refined run`.
  Windows comes first; Linux will reach the kernel through raw system calls
  behind the same kind of table.
- **D-123** `<operation> abi c "<symbol>"` exports an operation to C under
  that exact symbol, with the C calling convention. It is the only
  optional structural row (at most one, after `maxRecursion`): only the
  runtime's operations have it, and an `abi none` row on every other
  operation would state nothing a reader needs; context rows are already
  optional in the same way. The checker holds it to what crosses the
  boundary as it is: the symbol is a C identifier and names one operation
  in the program, inputs and output are `Int64`, `Int32`, `Byte`, `Bool`,
  `Float64`, or `machine.Address`, and the operation raises nothing (C has
  no error values), is not generic, and does not wait (R402, R403). Tests
  have no `abi` row.
- **D-124** `refined build --kind executable --runtime semanticscript`
  compiles the runtime project to its own object, with every `abi c`
  operation as a root, and links it with the program's object by
  `-nostdlib -nostartfiles -Wl,-e,refined_entry -lkernel32 -lgcc`: no CRT
  start files and no C library; `libgcc` is the compiler's support library
  (stack probes, `___chkstk_ms`), not libc. The executable's import table
  names KERNEL32.dll alone (a test reads it). The runtime's
  `refined_entry` sets the stack floor (248 MiB below its frame, the main
  thread's stack being 256 MiB, as the C runtime does), runs the program's
  entry through `machine.runEntry` (a call of `refined_program_main`, which
  native.py defines next to the program as a call of its entry operation),
  and ends the process with the exit code. A program that needs a runtime
  function this runtime does not define yet (every callback the program's
  IR declares is checked) is refused before linking, with R901 naming the
  functions; the C runtime stays the default until stage 5. A program that
  defines runtime functions (an `abi c` operation named like one of
  codegen's callbacks) is the runtime, and is compiled as such: its
  operations push no frames on the shadow call stack and count their own
  recursion in place, since those calls would reach the runtime itself, and
  each runtime function it calls is its own operation. Its object leaves
  `refined_stack_here` to the program's. The runtime is written as DSL files
  (`semanticscript/runtime/tools`) that stage0's generator expands into the
  `.sem` modules, which are what `refined check` and `refined test` read.

## The runtime in SemanticScript, stage 2 (2026-11-14)

Stage 2 of `docs/runtime-in-semanticscript.md` moved floating-point text and
the host library's buffers, maps, sets, `string.fromBytes`, and log lines into
`semanticscript/runtime`, as six new modules (`heap`, `tables`, `handles`,
`bignum`, `floats`, `host`). Decided by delegation:

- **D-126** `refined_host` dispatches by branching on a target's number, the
  row of the runtime's `hostTargets` table that names it, not through a table
  of function addresses. So the language gains no call through an address
  with several arguments and no address of an `abi c` operation. Each target
  is an ordinary operation that the checker sees whole (signature, effects,
  capabilities), where an indirect call through an address is the one
  primitive that could jump anywhere. A key's shape is worked out once and
  kept by the key's address, as the C runtime does, so a call costs one
  lookup and at most one comparison per target (25 today). The same table
  is what native.py reads to refuse a program that calls any other target
  (R901). Task thunks, whose addresses come from the compiler, keep
  `machine.callWithAddress` (stage 4); if a later stage needs more indirect
  calls, they come with it.
- **D-127** `convert.float64BitsToUInt64` and `convert.uint64BitsToFloat64`
  read a Float64's IEEE 754 bits as a UInt64 and back, unchanged (a NaN
  keeps its payload); they never trap. They are conversions of a value, not
  memory, so they need no capability, and they replace stage 1's round trip
  through `machine.state`.
- **D-128** The runtime's memory that grows and is given back piece by piece
  (buffers, the rows and indexes of maps and sets, the handle table, call
  shapes, trap messages) comes from the process heap: `system` rows for
  `GetProcessHeap`, `HeapAlloc`, `HeapReAlloc`, and `HeapFree`, always with
  `HEAP_ZERO_MEMORY`, behind the `heap` module's `take`, `resize`, and
  `give`. Regions keep their VirtualAlloc chunks. These are kernel32's own
  functions, so the executable still imports KERNEL32.dll alone.
- **D-129** Floating-point text is exactly what `refined run` writes and
  reads, which is Python's: a Float64 is written as `repr` writes it, the
  fewest significant digits that read back as it, the nearest of those to it,
  an exact tie to the even digit, with an exponent (`1e+16`, `1.5e-07`) when
  the decimal point is 4 or more places left of the first digit or more than
  16 right of it and otherwise with a point and a digit after it (`100.0`),
  and `nan`, `inf`, `-inf`; text is read correctly rounded, ties to even.
  This refines D-125, whose `%g`-style layout was the C runtime's, and the C
  runtime was wrong: it wrote `100.0` as `1e+02`, `1e15` as `1e+15`, NaN as
  `-nan(ind)`, and 17 digits where repr writes 16 next to some powers of
  two (220 of the 15,722 lines of the test's table). native_runtime.c now
  writes repr too. In SemanticScript the digits come from Steele and White's
  free-format method as Burger and Dybvig give it, and reading divides the
  significand (800 digits kept exactly, and a final 1 standing for any
  dropped that are not zero) by a power of ten to 54 bits and a remainder,
  all with the `bignum` module's exact arithmetic (6,400-bit numbers in
  `machine.state`). `tests/floattable.py` checks thousands of values of every
  kind against Python in both runtimes.
- **D-130** The host's objects are kept as the C runtime keeps them: a handle
  is a number from 1, never reused, naming a kind and an object, so one used
  after it was closed or after its region was released traps naming its
  kind; a region's header lists the handles it owns, and releasing it drops
  them; maps and sets are tables of rows in first-put order found through an
  open-addressing index (`tables`), with a text key copied into the region
  once, a text value at every `put`, and text inside a stored record moved by
  the compiler through `refined_handle_region` (D-107). native.py refuses
  (R901) a program that calls a host target outside `hostTargets`, naming it,
  and now reads target names with digits in them (`buffer.appendInt64` was
  invisible to both runtimes' checks). Channels are not in the C runtime's
  table either; the programs that use them also need tasks (stage 4).

## The runtime in SemanticScript, stages 3 and 4 (2026-11-14)

Stages 3 and 4 of `docs/runtime-in-semanticscript.md` moved the rest of the C
runtime into `semanticscript/runtime`: files, directories, claims, scopes,
the environment, arguments, standard input, child processes and pipes, time,
tasks, groups, cancellation, channels, and the test callbacks, as five new
modules (`slots`, `wide`, `tasks`, `files`, `processes`) and additions to
`frames` and `handles`. Decided by delegation:

- **D-131** `machine.taskEntry()` is the address of the runtime's operation
  exported as `refined_task_entry`, and nothing else: the one place the
  language hands out the address of an operation. A task's fiber needs a
  start routine that never returns (when a fiber's routine returns, its
  thread ends), and the compiler's task thunk returns, so the runtime starts
  every fiber in its own entry, which calls the thunk through
  `machine.callWithAddress` and then runs the next task. D-126's reason for
  keeping operation addresses out stands: the target is fixed by name, the
  checker sees the operation whole, and a program that does not define it
  cannot compile the target. Only the runtime has it.
- **D-132** The `system` rows for files, paths, the environment, child
  processes and pipes, time, and fibers are kernel32's own (`CreateFileW`,
  `GetFinalPathNameByHandleW`, `FindFirstFileW`, `LockFile`,
  `GetEnvironmentVariableW`, `CreateProcessW`, `CreatePipe`, `PeekNamedPipe`,
  `WaitForMultipleObjects`, `GetTickCount64`, `CreateFiberEx`,
  `SwitchToFiber`, and the like), so an executable still imports
  KERNEL32.dll alone. What lives outside kernel32 is written in
  SemanticScript: the command line is split into words as
  `CommandLineToArgvW` (shell32) splits it, and child command lines are
  quoted as `subprocess.list2cmdline` quotes them. Text crosses to the
  system through `MultiByteToWideChar` and `WideCharToMultiByte`, and a path
  is lower-cased by `LCMapStringEx` with the invariant locale, which is what
  Python's `os.path.normcase` itself calls on Windows (the C runtime used
  user32's `CharLowerBuffW`). Windows errors become errnos as Python's
  `winerror_to_errno` makes them, then the library's error variants as
  host.py classifies them.
- **D-133** Tasks in an executable linked with the runtime in SemanticScript
  run on fibers, one thread, one task at a time. `start` makes the task's
  fiber (64 MiB of stack reserved, as a task's thread has under the JIT) and
  switches to it at once, so a task that never waits runs to its end before
  `start` returns, exactly as the C runtime runs it (D-37, D-83). A task that
  waits (a `join`, an `awaitSlot`, a channel, a sleep, a child process, a
  lock, standard input with a deadline) notes what it waits for and the
  generation it saw, and the next task in start order that can go on runs:
  one that is ready, or a waiting one when the generation moved (every send,
  receive, close, cancel, start, and end counts one), its deadline passed, it
  was cancelled in a cancellable wait, or the system handle it waits on is
  signalled. When none can, the program sleeps until the nearest deadline or
  handle; with neither, it traps with the JIT's message, `deadlock: every task
  is waiting on another:` and every wait once, in order. Cancellation is the
  JIT's (D-44): a cancelled task's next cancellable wait ends with
  `cancelled`, so the conformance check `group-first-failure`, which D-83 left
  to the JIT, holds in these executables too. Each task has its own call stack
  for traps, depth counters, and stack floor (56 MiB below its fiber's first
  frame), which the switch saves and restores in `machine.state`; the C
  runtime's semantics are kept for standard input with no deadline, which a
  blocking read serves (every task waits on it).
- **D-134** The runtime defines the test callbacks (`refined_assert_int`,
  `refined_assert_true`, `refined_assert_str`, `refined_fail`) as the C
  runtime does, trapping with `an assertion failed (tests run with `refined
  test`)` or the failure's message, and `refined_block`, which does nothing
  (an executable keeps no trace). Under `refined test` the runtime project's
  own tests keep reporting through the test runner's callbacks: those
  operations take their C names only in the object built for an executable.
- **D-135** An executable is one LLVM module: the runtime, kept as bitcode in
  the temporary directory once per runtime and compiler source, and the
  program linked into it; every function but `refined_entry` and `memcpy`,
  `memmove`, `memset`, and `memcmp` (which LLVM's code may call) is made
  internal, and global dead-code elimination drops whatever the entry never
  reaches. The runtime's own functions are internal before the program is
  linked in, so a program operation named like one of them is a different
  function. Linking adds `--gc-sections` and `-s`. `hello` is 23 KB (145 KB
  when the whole runtime object was linked); the warehouse example 272 KB.
  Separate function sections were tried first and dropped nothing: the
  linker keeps every function its unwind data names.
- **D-136** Channels are host targets of the runtime in SemanticScript
  (`channel.Channel.new`, `send`, `receive`, `close`), as host.py has them: a
  capacity of at least 1 (else a trap naming it), text items copied into the
  channel's region (D-107), a send that waits for room and a receive that
  waits for an item, with `closed`, `timedOut`, and `cancelled`. The C
  runtime still refuses them (R901). Child processes join the resources a
  trap releases (D-51), stopped and closed with the open files; a captured
  child's three pipes are pumped a piece at a time between other tasks (each
  pipe holds 64 KiB; the room left in the child's input is read from a copy
  of its end), so no helper thread is needed.
- **D-137** The runtime in SemanticScript also implements `secret` (a copy of
  the bytes, `matches` comparing in time that depends on the lengths only, as
  `hmac.compare_digest` does), `crypto` (SHA-256 as FIPS 180-4 gives it,
  HMAC-SHA-256 with a 64-byte block, lower-case hex, constant-time equality,
  each what hashlib and hmac give), and `ffi` (`ffi.open` loads a library with
  `LoadLibraryW`, `c` naming ucrtbase and then msvcrt as ctypes does;
  `ffi.Function.bind` is `GetProcAddress`; the library stays loaded at `close`,
  as under the C runtime), all of which D-81 left to the JIT; a library loaded
  this way is not in the import table, which still names KERNEL32.dll alone.
  What stays refused (R901): `net` (Winsock is ws2_32.dll, not kernel32), `http`
  and `json` (not written yet; `json` must reproduce Python's error offsets and
  `dumps` layout), `random` (`int64Between` needs the system's secure generator,
  which is outside kernel32 and takes two arguments, more than
  `machine.callWithAddress` passes; seeded generators promise Python's
  Mersenne Twister), and `signal` (an interrupt arrives on a thread of its own
  through a handler whose address the language does not give out).

## The runtime in SemanticScript, stage 5 (2026-11-14)

Stage 5 of `docs/runtime-in-semanticscript.md` made the runtime in SemanticScript the only runtime of standalone
executables, on Windows and on x86_64 Linux, deleted `native_runtime.c`, and linked stage0's C with the runtime
built from SemanticScript. Decided by delegation:

- **D-138** Linux is reached through raw system calls. `system` gains one row per system call the runtime uses,
  named after it (`system.read`, `system.openat`, `system.mmap`, `system.wait4`, `system.pidfdOpen`, ...; the table
  is `LINUX_CALLS` in library.py), every input an `Int64` or a `machine.Address` and every output the kernel's
  `Int64` result, a negative errno when the call fails; each is one `syscall` instruction (LLVM inline assembly,
  x86_64 numbers and registers). `system.linux()` is a constant of the target triple. A runtime module asks it
  and takes the Windows path (kernel32) or the Linux path, the same module and the same messages either way; the
  backend lowers a target of the other system to a trap that refers to nothing, and native.py folds the constant
  (SROA, SCCP, CFG simplification) before dropping what nothing reaches, so an executable holds one system's code
  (`hello` went from 23 KB to 14 KB on Windows). A new first module, `kernel`, holds what many modules share:
  memory from the system (VirtualAlloc or an anonymous mmap), the errno of a result, Linux's clocks and sleep,
  and what a Linux process starts with (argc, argv, envp). Each module that ends the process has its own
  `endProcess` (ExitProcess or exit_group), since an exported operation must have a tested invariant and ending
  the process cannot be tested. On Linux the file calls keep the errno of the last failure where Windows asks
  GetLastError, so the claims, scopes, and error classification are the same code on both; paths are resolved as
  `posixpath.realpath` resolves them (one component at a time, links followed, at most 40), names are compared as
  they are, a directory opened for reading is EISDIR as Python's `open` makes it, and a lock is `flock`.
- **D-139** Stacks on Linux are the runtime's own. Three `machine` targets switch them, each a few instructions
  of module assembly for the architecture (x86_64 System V, and AArch64): `switchStack` keeps the running stack
  at a save slot and resumes another, `startStack` keeps it and runs `function(argument)` on a fresh stack,
  `runEntryOnStack` runs the program's entry on a fresh stack and gives its exit code. The process entry is a
  `_start` of module assembly that hands `refined_entry` the stack the kernel started it with; `refined_entry`
  keeps argc, argv, and envp, ignores SIGPIPE (as Python does, so a write to a closed pipe is EPIPE), maps a
  stack of 256 MiB (MAP_NORESERVE, pages given as they are touched) and runs the program on it with the same
  floor as on Windows. A task's fiber is a 64 MiB stack of its own started with `startStack`; what a task waits
  on outside the program is a descriptor (stored as the descriptor plus one, 0 being none) that `poll` watches:
  a child's pidfd, standard input. Linking is `-nostdlib -nostartfiles -static`, the entry `_start`, and libgcc;
  the executable has no dynamic section and no interpreter.
- **D-140** Linux has no process heap, so the runtime keeps its own (the `heap` module's Linux path): a block of
  up to 4 KiB with its header is one of nine sizes cut from 64 KiB chunks of an anonymous mmap and goes back to
  that size's free list; a larger one is a mapping of its own. Every block is zeroed when it is handed out, as
  HEAP_ZERO_MEMORY makes it on Windows. `ffi` is refused on Linux (R901): loading a C library needs the C
  library's dynamic loader, which an executable with no C library does not have. Child processes start as
  `_posixsubprocess` starts them: the program, or each PATH directory joined with it (`/bin:/usr/bin` when PATH
  is not set), made ready before `fork`; in the child SIGPIPE goes back to its default, the pipes become its
  standard streams, and `execve` is tried with each name; the first error that is not ENOENT or ENOTDIR (or the
  last) comes back on a close-on-exec pipe. A child ended by a signal exits with minus the signal, as
  `Popen.returncode` has it; this program's ends of a captured child's pipes are non-blocking.
- **D-141** The runtime in SemanticScript is the only runtime: `refined build --kind executable` links it on
  Windows and on x86_64 Linux; `--runtime semanticscript` is still accepted and changes nothing; `--runtime c`
  is gone with `native_runtime.c`. macOS is refused with a diagnostic (R901): there is no CI to validate a
  system layer for it, so none is written; run the program with `refined run` there. Linux on another
  architecture is refused the same way (the system call numbers and registers are x86_64's).
- **D-142** stage0's C links the runtime built from SemanticScript. `refined build semanticscript/runtime --kind
  runtime --output runtime.o` writes the runtime as a standalone object for the C compiler's platform, every
  `abi c` operation an external symbol and `refined_program_main` left undefined; stage0's emitted C defines
  `int32_t refined_program_main(void)` (the runtime's `refined_entry` reads the command line itself) where it
  wrote `main` and `refined_start`, and calls no C library function (its prelude declares `memcpy` and `memset`,
  which the runtime defines, and measures C strings itself). stage0 links with `runtime.o -nostdlib -nostartfiles
  -Wl,-e,refined_entry -Wl,--stack,268435456 -lkernel32 -lgcc` on Windows and `runtime.o -nostdlib -nostartfiles
  -static -fno-stack-protector -lgcc` on Linux (the stack protector reads a canary through the thread pointer,
  which only the C library sets up).
- **D-143** With `native_runtime.c` gone, what tests read from it they read from the runtime: the host targets
  from its `hostTargets` table, the error variants' numbers from the constants named `<module>.<Enum>.<variant>,
  numbered from 1`. D-80 to D-85 are superseded where they describe the C runtime: a task now runs on a fiber
  until it waits (D-133), a captured child's pipes are pumped between tasks with no helper thread (D-136), and
  channels, secrets, crypto, and (on Windows) foreign libraries work in executables.

## The runtime in SemanticScript, the rest of the library (2026-11-15)

The five modules stage 4 left to `refined run` (D-137) moved into `semanticscript/runtime`: `random`, `http`,
`json`, `signal`, and `net`, and the Linux system layer gained AArch64. Decided by delegation:

- **D-144** "No C library" means no C library or C runtime of any kind: no msvcrt, ucrt, vcruntime, glibc, or musl,
  no CRT start files, and on Linux no dynamic loader. What an executable may link besides the program and the runtime
  in SemanticScript is the operating system's own interface, and only where the system gives no other: on Windows
  `KERNEL32.dll`, `WS2_32.dll` (Winsock, the only interface Windows gives to its TCP/IP stack), and `bcrypt.dll`
  (the system's random number generator, `BCryptGenRandom`, which Python's `os.urandom` also calls); on Linux the
  system calls themselves. Their rows are `SYSTEM_CALLS`, each named in `SYSTEM_DLLS` with its DLL when it is not
  kernel32's, and executables and stage0 link `-lkernel32 -lws2_32 -lbcrypt`; a DLL is in the import table when the program's code
  can reach it: `hello`, which calls no host target, imports KERNEL32.dll alone, and a program that calls any host
  target reaches `refined_host`'s dispatch over all of them (D-126), so it imports WS2_32.dll and bcrypt.dll too
  (Winsock is started only at the first socket). `assert_no_libc` holds
  every executable the tests build to it: on Windows the import table names KERNEL32.dll and a subset of
  {WS2_32.dll, bcrypt.dll}, never a CRT DLL; on Linux the file is static, with no PT_DYNAMIC or PT_INTERP and no
  trace of the C library.
- **D-145** Two platform limits follow from the bar, and stay. `ffi` on Linux is refused (R901): `ffi.open("c")`
  asks for the C library itself, and every library `ffi.open` could load is linked against it; a static process
  with no C library cannot host glibc, whose own start-up (thread-local storage, the dynamic loader's link map,
  `__libc_start_main`'s initialisation) only `ld.so` performs, so loading it would mean shipping the dynamic loader
  and the C library, which is what the bar rules out. macOS is refused (R901): Apple's kernel interface is private
  and changes between releases, and every macOS executable must link libSystem, which is the C library; there is
  no macOS executable without a C library to build. Both are stated in the R901 messages and in
  docs/runtime-in-semanticscript.md. The limit on `ffi` is lifted by D-153 and D-154: the runtime's own C library
  and loader.
- **D-146** `random` is the module `generators`. `random.int64Between` reads the operating system's secure source as
  `secrets.randbelow` does, a fresh draw of the range's bit length until one falls inside it: `BCryptGenRandom` with
  `BCRYPT_USE_SYSTEM_PREFERRED_RNG` on Windows (bcrypt.dll, D-144), the `getrandom` system call on Linux; a source
  that fails traps. A seeded generator is CPython's Mersenne Twister exactly: `init_genrand(19650218)` and
  `init_by_array` of the seed's magnitude in 32-bit words, least significant first (one word for 0), as
  `random.Random(seed)` seeds from an `int`; `random.nextInt64(low, high)` is `randint(low, high)`, which takes
  `getrandbits(k)` of the width's bit length (one 32-bit word shifted down for 32 bits or fewer, words least
  significant first above that, the last shifted down) until it falls below the width, so a generator gives the
  same numbers as under `refined run` for every seed and range, the full range of Int64 included. A generator is a
  heap block of its 624 words and the next word's place, a `Generator` handle owned by its region.
- **D-147** `signal` is the module `interrupts`, as `refined run` handles SIGINT for a program that reads `signal`:
  the first interrupt sets the flag `signal.interrupted` reads and ends a `signal.waitForInterrupt`; the second ends
  the process with exit code 130. The handler is installed before the program's entry runs, as the JIT installs its
  own before it runs the program: native.py's `refined_program_main` calls the runtime's `refined_signals_start`
  first when the program calls a signal target. The handler is an `abi c` operation, `refined_interrupt_handler`,
  whose address `machine.interruptHandler()` gives, the second place the language hands out an operation's address
  (after D-131's `taskEntry`) and on the same terms: fixed by name, only in the runtime. On Windows it is a console
  control handler (`SetConsoleCtrlHandler`) for CTRL_C_EVENT only, as Python maps CTRL+C alone to SIGINT, other
  events left to the system; it runs on a thread the system makes, so it sets the flag, counts a change in the
  scheduler's generation, and sets an auto-reset event that the scheduler's sleep also waits on (without counting it
  against a deadlock, so a wait for an interrupt with no deadline and nothing else to wait for is a deadlock, as
  under `refined run`). On Linux it is an `rt_sigaction` handler for SIGINT with SA_RESTART, so reads and writes go
  on, and SA_RESTORER, the runtime's `rt_sigreturn` trampoline of module assembly (`machine.signalRestorer()`); the
  signal ends the scheduler's `poll` by itself. A wait honours its deadline and cancellation as other waits do.
  `ctrlc.py` sends CTRL+C on Windows to a console of the test's own, since CTRL+C cannot be sent to one process.
- **D-148** `net` is the module `sockets`, IPv4 TCP as host.py has it. A socket never blocks the program: it is
  non-blocking (WSAEventSelect on Windows, SOCK_NONBLOCK on Linux), and a call that would block waits through the
  scheduler on the socket's event (Windows) or its descriptor (Linux, as POLLIN, or POLLOUT for connect and write:
  the descriptor plus one, with 2^32 added for POLLOUT), so other tasks run meanwhile and deadlines hold; accept and
  read stop for a cancelled task and a passed deadline before they try, as host.py's `_until_ready` does, and connect
  and write are not cancelled, as host.py's are not; a deadline already passed tries once without waiting, as a
  Python timeout of 0 does. Errors are what `_net_error` makes of Python's: a timeout (ETIMEDOUT too) timedOut,
  ECONNREFUSED refused, a reset, an abort, a broken pipe, or a shut-down socket closed, anything else failed with
  Python's errno (the Winsock code on Windows, as winerror_to_errno leaves all but six); a port that is not a whole
  number as int() reads text is failed 22, and `net.listen` of a port outside 0 to 65535 traps with Python's
  OverflowError. `listen` binds the capability scope's host (127.0.0.1 when it names none) with SO_REUSEADDR on
  Linux, as Python's socket does there, and a backlog of 128. Connections and listeners are handles with no region
  (the caller owns them); a trap needs no release, since the system closes a process's sockets as it ends. The
  scope check of D-38 now covers `net.tcp` (the port's decimal text against the text after the scope's last colon)
  and `net.outbound` (address_within). Winsock's rows are named `winsock<Name>` beside Linux's system calls of the
  same names. tests/nettour.py prints exactly what `refined run` prints. Writing it found a false deadlock in
  `refined run` itself (tasks.py): a joiner woken as a task ended could see every thread idle for an instant, and six
  such wake-ups in a row (a task that runs many short waits, each its own thread) read as a deadlock on a slow
  machine; a poll now counts as quiet only when nothing changed since the last one.
- **D-149** Names are resolved as Python's create_connection resolves them, IPv4 only (where getaddrinfo would also
  give IPv6 addresses, the executable tries the IPv4 ones, which is what reaches an IPv4 listener): on Windows by
  ws2_32's getaddrinfo with AF_INET hints; on Linux, with no C library to call, by a resolver written in the runtime:
  a numeric address in any form glibc's inet_aton reads, else the first IPv4 line of /etc/hosts that names the host
  in any case, else an A query over UDP to the first nameserver of /etc/resolv.conf (127.0.0.1 when it names none),
  five seconds a try and two tries as glibc's defaults are, through the scheduler. A name that does not exist is
  EAI_NONAME (-2), one with no address EAI_NODATA (-5), and no answer or a server's failure EAI_AGAIN (-3), the
  errnos Python's gaierror carries; search domains and IPv6 are not used.
- **D-150** Linux on AArch64 has the runtime's system layer too. A Linux `system` row is one `svc #0` there, the
  number in x8 from `AARCH64_NUMBERS` (the kernel's generic table), the arguments in x0 to x5, the result in x0. The
  three calls AArch64 lacks become what glibc makes of them: `poll` is `ppoll` (its milliseconds a timespec on the
  stack, NULL for none), `fork` is `clone(SIGCHLD)`, `dup2` is `dup3(fd, target, 0)`. Where the kernel's structures
  and flags differ the runtime asks `system.aarch64()`, a constant of the target like `system.linux()`: st_mode is at
  16 in the generic struct stat (24 on x86_64), and O_DIRECTORY is 0x4000 (0x10000 on x86_64); everything else the
  runtime uses (errnos, signals, sigaction, pollfd, dirent64, timespec, mmap and socket flags) is the same. The
  process entry `_start` and the rt_sigreturn trampoline are AArch64 module assembly beside D-139's stack switches.
  native.py builds `aarch64-unknown-linux-gnu` executables when the C compiler is an AArch64 Linux one, and CI runs
  the whole suite on `ubuntu-24.04-arm` (Python 3.12).
- **D-151** `json` is two modules: `values`, below `handles`, which keeps JSON values as `refined run` keeps Python
  objects (an array or object is shared, so what `field` and `item` give and what `setValue` stores is the same
  value, and a change shows through every handle and container that holds it; each value is counted, and the last
  handle or container to let go gives it back with what only it held, as a handle is closed or its region released),
  and `documents`, the targets. `json.parse` reads the text as `json.loads(text.decode("utf-8", "surrogateescape"))`
  reads it, CPython's C scanner step by step: the bytes that are not UTF-8 become U+DC80 to U+DCFF, positions count
  code points, NaN, Infinity, and -Infinity are numbers, a leading U+FEFF is invalidAt 0, a lone surrogate escape is
  kept (Python's `str` may hold one; the runtime keeps text in UTF-8 that may hold surrogates, so equal keys are
  equal strings), duplicate keys keep their first place and their last value, and every error is invalidAt at the
  position the scanner reports. Nesting deeper than 2,994 arrays and objects is tooDeep: the C recursion limit of
  CPython 3.12, where `refined run`'s scanner reaches it (CPython 3.11 counts Python frames instead and stops
  earlier; the executable keeps one number). `json.stringify` is `json.dumps(value, separators=(",", ":"),
  ensure_ascii=False)` encoded with surrogateescape: keys in order, text escaped as the C encoder escapes it, floats
  as repr writes them with `NaN`, `Infinity`, and `-Infinity`. Where `refined run` raises a Python exception inside a
  target it traps with ``` `<target>` failed inside the runtime: <repr of the exception>```, and the executable traps
  with the same message: an integer of more than 4,300 digits (`ValueError`, int()'s limit), a surrogate
  surrogateescape cannot write (`UnicodeEncodeError` with the text's repr and the run's positions), a value that holds
  itself (`ValueError('Circular reference detected')`), and nesting past the limit while writing (`RecursionError`).
  Names and text given to `field`, `setText`, `appendText`, and the setters are read with `decode("utf-8",
  "replace")`, one U+FFFD for each maximal part that is not UTF-8, as host.py reads them. tests/jsontour.py runs
  every target on 1,300 texts (tests/jsoncases.py) and the executable prints exactly what `refined run` prints.
- **D-152** `http` is the module `requests`, pure text as host.py handles it: the head ends at the first `\r\n\r\n`
  (else `\n\n`, else the whole text); its lines split at `\n`, a `\r` before one dropped; the request line is exactly
  three parts split at single spaces, a method of HttpMethod's names in any case of ASCII, a path that starts with
  `/`, a version that starts with `HTTP/`; every other line is `name: value`, the name trimmed of ASCII white space
  and lower-cased with each byte that is not ASCII standing for U+FFFD (as `decode("ascii", "replace")` reads it), the
  value trimmed and copied into the region, path first and then the values in order (so `arena.remaining` agrees
  even when a later line is malformed). The headers are kept by the address of the request's path, as host.py keeps
  them in a dict by that pointer, so `http.header` finds them for the record the parse gave and its copies; a name is
  looked up lower-cased as `str.lower` lower-cases it (ASCII letters, and the Kelvin sign, which becomes `k`), the
  last header of a name winning. `http.response` keeps a status and a copy of the body as a `Response` handle of its
  region; `serializeResponse` writes `HTTP/1.1 <status> <reason>` (OK, Created, No Content, Bad Request, Not Found,
  Method Not Allowed, Internal Server Error, else `Status`), then `Content-Type: text/plain; charset=utf-8`,
  `Content-Length`, `Connection: close`, a blank line, and the body.

## The runtime in SemanticScript, the whole C library: the parallel modules (2026-11-15)

The rest of ISO C's library is written as modules of their own (cmathbits, cmathexp, cmathtrig, cmathspecial,
ctime, cwide, cextra), each by its own agent working at the same time in this checkout, each with a tour that calls
its functions through `ffi` in an executable with no C library and compares them with exact values, and on Linux
with glibc. Decided by delegation:

- **D-180** math.h's hyperbolic, error, and gamma functions (`cmathspecial`): sinh, cosh, tanh, asinh, acosh, atanh,
  erf, erfc, tgamma, lgamma, their `f` forms, and lgamma_r and lgammaf_r. They compute in double-double (Dekker
  products; a private exp with ln 2 in three parts and a log by one Newton step on it; gamma by Stirling's series
  after shifting the argument to 24 or more, Taylor series about 1 and 2, and reflection with sin(pi x) below 0; erf
  by its series below 3; erfc by Laplace's continued fraction from 3), so each is within 1 ulp of the exact value
  (lgamma near its zeros below -2 within 2^-72 absolutely); in the tour's 980 calls every finite result is the
  correctly rounded one. The `f` forms compute in double and round once. Annex F's special values are exact; errno is
  ERANGE on overflow and poles, EDOM on domain errors. `signgam` is not exported (it is POSIX's, not ISO C's): the
  sign is kept at machine.state 24592 and given by lgamma_r and lgammaf_r. The module's state is machine.state 24576
  to 24831 (each parallel module has a range of its own, 24576 to 27903).
- **D-181** math.h's trigonometric functions (`cmathtrig`): sin, cos, tan, asin, acos, atan, atan2, and their `f`
  forms, each within 1 ulp of the exact value (the tour's worst over about 3,900 arguments from 2^-60 to 1.8e308 is
  0.64 ulp, tan's). Arguments are reduced not at all up to pi/4, by Cody-Waite up to 1.6e6 (pi/2 in four pieces,
  every rounding caught by two-sum), and by Payne-Hanek above (2/pi to 41 limbs, a 288-bit product held in 32-bit
  limbs in machine.state 25344 to 25599), so a huge argument such as 6381956970095103 * 2^797 reduces exactly. The
  inverse functions start from a table of atan(k/8) as double-double pairs and a short series. Every constant is
  computed from Python integers by tools/cmathtriggen.py (pi from Machin's formula, 2/pi by one exact division, the
  series from exact fractions), which writes the generated blocks of cmathtrig.dsl. Annex F's special values are
  exact, with errno EDOM for the infinities of sin, cos, and tan and arguments of asin and acos beyond 1. The `f`
  forms compute in double and round once (within 1 ulp, not glibc's sinf bit for bit). In the runtime's DSL a NaN
  test is `!(x == x)`: `!=` on floats is an ordered comparison.

- **D-182** math.h's exponential, logarithmic, and power functions (`cmathexp`): exp, exp2, expm1, log, log2, log10,
  log1p, pow, cbrt, hypot, and their `f` forms, each within 1 ulp of the correctly rounded value (the tour: 2523 of
  2524 values correctly rounded against a 110-digit Decimal reference, the one miss pow(DBL_MAX, 0.5) by 1 ulp).
  They are table-free double-double algorithms (Dekker and Knuth), not glibc's table-driven ones from ARM's
  optimized-routines, whose tables cannot be reproduced bit for bit from what is published in words; so they are not
  claimed identical to glibc's, and on Linux the test holds them within 2 ulp of glibc's (cbrt within 4), with NaN,
  the infinities, and the sign of zero equal. exp and its kin reduce by ln 2 in parts, take expm1 of r/8 by a Taylor
  series and double it back three times, and scale in two exact steps; the logarithms are 2 atanh((m-1)/(m+1)); pow is
  exp(y log|x|) in double-double; cbrt is Newton's method with one double-double correction; hypot corrects a square
  root of double-double squares. Every constant is computed with Decimal and Fraction by tools/cmathexpgen.py. errno
  is ERANGE on overflow, on underflow to 0 and at poles, EDOM on invalid arguments (glibc's ERANGE for an inexact
  subnormal result of exp is not set). An invalid result is the default NaN with its sign bit set, as on x86_64.

- **D-183** The rest of string.h and stdlib.h, and locale.h, assert.h, and inttypes.h (`cextra`): strtok (its save
  pointer at machine.state, left at the string's end as glibc leaves it), strtok_r, strsep, strcoll and strxfrm (the C
  locale's byte order), memccpy, mempcpy, stpcpy, stpncpy, strchrnul, memrchr; strtof, correctly rounded (the double
  from clibrary's reader, rounded to float on integer bits, and a text that lands on a float midpoint compared with it
  exactly in bignum, so it never rounds twice), with hex floats, inf, nan, subnormals, and ERANGE; rand and srand as
  glibc's TYPE_3 generator (rand before srand as srand(1), srand(0) as srand(1)), rand_r as glibc's three-step LCG;
  aligned_alloc (a non-power-of-two alignment is NULL with EINVAL, as glibc 2.38 has it) and posix_memalign; setlocale
  ("C", "POSIX", "" and NULL give "C", any other name NULL) and localeconv (glibc's C values in its x86_64 struct
  lconv layout); `__assert_fail` with glibc's message, then abort; imaxabs, strtoimax, strtoumax, wcstoimax,
  wcstoumax. Aligned blocks above 16 bytes of alignment are a known weakness: on Linux they are carved from a larger
  block or mapped pages that free does not give back whole, and on Windows, where HeapAlloc cannot align, they are
  found by taking blocks until one is aligned, so a large aligned request there can fail. errno is set through
  clibrary's setErrno (per thread, D-166). machine.state 26880 to 27903.

- **D-184** wchar.h, wctype.h, uchar.h, and stdlib.h's multibyte functions (`cwide`), as glibc has them in the C
  locale, with wchar_t 32 bits on every system (Windows too, so the library's ABI is glibc's): the wide classifiers
  and case mappings (ASCII only, as glibc's C locale), wctype, iswctype, wctrans, towctrans; the wcs and wmem string
  functions, wcstok, wcsdup; wcstol and its kin and wcstod through clibrary's readers on the narrowed text; wcstof
  correctly rounded, as strtof is (D-183); wcscoll and wcsxfrm in the C locale's order; btowc, wctob, mbsinit,
  mbrlen, mbrtowc, wcrtomb, mbsrtowcs, wcsrtombs, mblen, mbtowc, wctomb, mbstowcs, wcstombs, mbrtoc16, c16rtomb,
  mbrtoc32, c32rtomb. The C locale's multibyte encoding is one byte per character, every byte 0 to 255 its own wide
  character, and a wide character above 255 is EILSEQ; MB_CUR_MAX is 1 and the conversion state is ignored. The
  Linux comparison with glibc decides each of these: the tour prints whether a classifier's result is nonzero, not
  its value, and every high byte's conversion both ways.

- **D-185** math.h's exact operations and fenv.h (`cmathbits`): frexp, ldexp, scalbn, scalbln, ilogb, logb, modf,
  rint, nearbyint, lrint, llrint, lround, llround, remainder, remquo, fdim, fmax, fmin, fma, nextafter, nan, their
  `f` forms, and feclearexcept, fetestexcept, feraiseexcept, fegetround, fesetround, fegetenv, fesetenv,
  feholdexcept, feupdateenv, fegetexceptflag, fesetexceptflag. Each is exact in IEEE arithmetic, so each is bit for
  bit, signed zeros and NaN payloads included (the tour's 5996 lines match). fenv.h acts on the processor's own state
  through machine.loadFloatControl and storeFloatControl (D-167), with each architecture's FE_* values: fenv_t is
  glibc's 32 bytes on x86_64 (a fresh x87 environment, MXCSR at offset 28; only the SSE state is mirrored) and FPCR
  and FPSR as two words on AArch64. rint, nearbyint, lrint, and llrint round in the current mode; rint raises inexact
  when it changes a value, nearbyint never; an out-of-range lrint or lround is LONG_MIN on x86_64 and saturates on
  AArch64, as the instructions do. fma is machine.fusedMultiplyAdd, correctly rounded. nexttoward and nexttowardf
  are not provided here: their second argument is a long double, which the compiler's long double support brings.

- **D-186** time.h (`ctime`): time, clock (CPU time at CLOCKS_PER_SEC 1000000: CLOCK_PROCESS_CPUTIME_ID on Linux,
  GetProcessTimes on Windows), difftime, timespec_get (TIME_UTC only), gmtime, gmtime_r, localtime, localtime_r,
  mktime, asctime, asctime_r, ctime, ctime_r, and strftime with every C11 conversion and glibc's extensions, flags,
  widths, and E and O modifiers. struct tm is glibc's 56 bytes, and gmtime and localtime share one static struct as
  glibc's do. The local zone is the runtime's own reading: TZ (a TZif file under /usr/share/zoneinfo or an absolute
  path, else a POSIX rule string with Mm.w.d, Jn, and n rules), and with TZ unset /etc/localtime on Linux and
  GetDynamicTimeZoneInformation on Windows (its zone names abbreviated to their initials, which cannot be glibc's);
  TZif version 1 and the 64-bit block of later versions, with the footer's rule past the last transition; UTC when
  nothing is found. TZ is read again only when its text changes, and a zone's data is never freed, so a struct tm's
  tm_zone stays valid. mktime searches as glibc's (gnulib's) does, tm_isdst -1 included. machine.state 25600 to
  26623. tzset and the tzname, timezone, and daylight globals are POSIX's, not ISO C's, and are left out.

- **D-187** complex.h (`cmathcomplex`): cabs, carg, cimag, creal, conj, cproj, cexp, clog, cpow, csqrt, csin, ccos,
  ctan, casin, cacos, catan, csinh, ccosh, ctanh, casinh, cacosh, catanh, and their `f` forms, each an `abi library`
  operation on a record of two Float64 or two Float32 that the compiler passes as glibc's ABI passes a complex value
  (D-175). Bounds per part: cabs and carg 1 ulp, clog and csqrt 2, cexp 3, csin, ccos, csinh, ccosh, casin, cacos,
  casinh, cacosh, and catanh 4, ctan, ctanh, and catan 6 (measured at most 3); cpow, which is cexp(y clog x) with
  C99's complex multiplication and Annex G's recovery of infinities, within (6 + 2|y log x|) 2^-53 of the result's
  magnitude. csin, ccos, ctan, casin, and catan come from Annex G's identities through the hyperbolic forms; casinh,
  cacosh, and cacos use Hull, Fairgrieve, and Tang's kernel; clog near |z| = 1 takes log1p of x^2 + y^2 - 1 summed in
  double-double. Annex G's special values are exact, with the open signs chosen as glibc chooses them. errno is left
  as the caller had it (C99's complex functions raise only floating-point exceptions). The `f` forms compute in
  double and round each part once.

- **D-188** math.h's transcendental long double functions and fmal (`cmathlong`): sinl, cosl, tanl, asinl, acosl,
  atanl, atan2l, expl, exp2l, expm1l, logl, log2l, log10l, log1pl, powl, cbrtl, hypotl, sinhl, coshl, tanhl, asinhl,
  acoshl, atanhl, erfl, erfcl, tgammal, lgammal, lgammal_r, and fmal. Each computes on a 320-bit floating value of its
  own (sign, kind, power of two, ten 32-bit limbs) in a heap workspace per call, so each is reentrant and needs no
  long double arithmetic, and rounds once with clong's settling into the target's long double (D-174): the same code
  serves x87 on x86_64, binary128 on AArch64, and double on Windows, and all three are tested on any host. Each is
  within 1 ulp of the exact value (the method's error is near 2^-300, so results are correctly rounded but within that
  of a rounding boundary; the 1,596 table cases across the three formats are bit for bit); fmal is exactly rounded;
  lgammal near its zeros below -2 is within 2^-250 absolutely; the argument reduction's 2/pi reaches 17,200 bits, for
  the largest x87 and binary128 arguments. An invalid result is the default NaN (sign set on x86_64, clear on
  AArch64); errno is EDOM or ERANGE as glibc sets them (not for a subnormal result). The cost is size and time: each
  call takes a 17.6 KB workspace.

- **D-190** strerror on Windows says what the Windows C runtime says. D-172's table is filled from glibc only on a
  glibc machine, so every executable built on Windows said `Unknown error N` for every number. Built on Windows for
  Windows, the compiler now fills it from Python's os.strerror, which is the Microsoft C runtime's (ucrt's) strerror
  there, so a Windows program gets its platform's C library's messages. The runtime's numbers are glibc's (D-171) and
  ucrt numbers some errors differently, so each number is matched by its symbolic name (`GLIBC_ERRNO_NAMES` in
  codegen.py, 1 to 133): ENOENT 2 is ucrt's 2, EDEADLK 35 is ucrt's 36, ECONNREFUSED 111 is ucrt's 107. Python's
  errno module gives ucrt's numbers for most names but Winsock's WSAE numbers for the socket ones (errno.ECONNREFUSED
  is 10061 there, and ucrt's strerror of it is "Unknown error"), so the 24 names ucrt's errno.h numbers from 100 to
  138 are taken from that header (`_UCRT_SOCKET_ERRNOS`). 0 is ucrt's "No error". A number whose name ucrt does not
  have (ENOTBLK, the STREAMS and keyring errors, EHWPOISON), and 41 and 58, which glibc leaves unnamed, stay `Unknown
  error N`: ucrt's own text for them would be a bare "Unknown error". The messages are ucrt's words and case ("Not
  enough space", "connection refused"), not glibc's. tests/cstdio.py expects the compiler's table on Windows and
  checks 13 numbers against messages written out (`UCRT_SAMPLES`); a Linux target built on Windows keeps the empty
  table.

- **D-191** threads.h on Windows waits in the system instead of sleeping a millisecond and looking again (D-168). A
  mutex (glibc's 40 bytes, opaque to C) is an SRW lock at 0 that guards it, its owner at 8, its count at 16, its kind
  at 24, its state at 28 (0 free, 1 held, 2 held with waiters), and a condition variable at 32: a take sleeps on that
  condition variable under the guard while the mutex is held (SleepConditionVariableSRW), and a give marks it free and
  wakes one waiter when the state says one waits. The guard is held only for those few instructions, so every kind
  (plain, recursive, timed) has the same shape and mtx_timedlock works on any, sleeping for the milliseconds left
  before its TIME_UTC deadline (rounded up, read from GetSystemTimeAsFileTime) and giving thrd_timedout once it has
  passed; a waiter that gives up leaves the state at 2, so no other waiter's wake is lost. A condition variable
  (glibc's 48 bytes) is a Windows condition variable at 0: cnd_wait, under the mutex's guard, marks the mutex free
  (waking one of its waiters), sleeps on the condition variable, which lets the guard go only once it is asleep, so a
  signal sent by a thread that took the mutex afterwards is never missed, and takes the mutex again; cnd_signal and
  cnd_broadcast are WakeConditionVariable and WakeAllConditionVariable. A recursive mutex waited on is given back whole
  and its count restored. call_once's flag is glibc's 4-byte int, too small for a lock, so every flag shares one SRW
  lock and one condition variable in machine.state (28512 and 28520): the first caller marks the flag running and
  calls the function without the lock, later callers sleep until it is done. The streams' lock (D-166) is an SRW lock
  at its machine.state word, its holder and count as before. The heap's lock is Linux's only: on Windows the heap is
  HeapAlloc's, which Windows locks itself. thrd_join already waited on the thread's handle. New kernel32 rows:
  InitializeSRWLock, AcquireSRWLockExclusive, ReleaseSRWLockExclusive, InitializeConditionVariable,
  SleepConditionVariableSRW, WakeConditionVariable, WakeAllConditionVariable (no event or WaitOnAddress is needed, so
  executables import KERNEL32.dll alone among the C-free DLLs, D-144). For the runtime's own tests the compiler gains
  `machine.testThreadEntry`, the address of a test's operation exported as `refined_c_test_thread`, so cthreads'
  contentionTest starts threads that run SemanticScript under `refined test`: four threads add 2,000 each to a counter
  under a plain, a recursive, and a timed mutex, a read and its write a yield apart, and the counter is 8,000 each
  time; a condition variable hands a flag over and an answer back; a timed lock and a timed wait time out once their
  deadline has passed; four threads' call_once calls rand once; four threads flush every stream 500 times.
  tests/threadtour.py proves the executable's (x86_64) build of them through `ffi`, which cannot start a thread of
  its own: mtx_timedlock and cnd_timedwait give thrd_timedout only once a deadline a second ahead has passed.

- **D-192** setjmp's and longjmp's Windows x64 routines (D-170) are written as their machine code, so an x86_64
  executable built on an ARM64 machine has them: LLVM assembles inline assembly with the target's own assembler,
  llvmlite on ARM64 registers none for x86 (not even for `.byte` directives, which the same parser reads), and the
  routine trapped there. Each is now a constant array of its bytes (`_X86_64_WINDOWS_CODE` in codegen.py, one
  instruction a line with its assembly beside it, the bytes GNU as gives for D-170's text) in the section
  `.text$refined`, which the linker merges into .text, and the operation's function is an internal alias of that
  array (`_MachineCodeFunction`), so the C library's table and any caller reach it by its own name. Same entry
  semantics: setjmp keeps rbx, rbp, r12 to r15, rdi, rsi, xmm6 to xmm15, the caller's stack pointer, and the return
  address in glibc's jmp_buf layout of D-170 and gives 0; longjmp restores them and returns from that setjmp again
  with its value, 1 for 0. Every object built for x86_64 Windows uses the bytes, on any machine (an executable, the
  runtime object stage0 links), so CI's x86_64 runner builds what this machine builds; only the JIT on an x86_64 host
  keeps the inline assembly, since its bytes would be data in memory that does not execute. tests/jumptour.py builds
  an executable that calls setjmp and longjmp through `ffi` and keeps its count in memory: setjmp gives 0, then 7
  from longjmp(7), then 1 from longjmp(0). No other x86 assembly reaches a Windows executable: the system call
  instruction, the thread pointer (`%fs`), and the start, stack, thread, and signal routines are Linux's.

- **D-193** complex.h's long double forms on Windows: cabsl, cargl, cimagl, creall, conjl, cprojl, cexpl, clogl,
  cpowl, csqrtl, and the trigonometric and hyperbolic l forms, each the double function itself, since Windows' long
  double is double (D-174) and so its long double complex is double complex, with the same ABI (D-175); their
  results are bit for bit the double forms'. An `abi library "<name>" windows` row puts a function in the C library
  of Windows targets only (shapes.py accepts the word, semantics.library_windows_only reads it, and the code
  generator leaves such rows out of other targets' table), so on Linux, where long double is x87 or binary128, these
  names are symbolMissing until complex values of those formats have an ABI of their own.
- **D-194** aligned_alloc and posix_memalign cooperate with free and realloc (replacing D-183's search on Windows and
  its leak on Linux). An alignment below 4096 cuts the block from size + 2 alignment + 16 bytes, at least 16 bytes
  into its page, with a header just below the aligned address (the original block, the size, log2 of the alignment,
  and a 16-bit tag); free reads a header only for an address at least 16 bytes into its page, where it can be read,
  and the tag, the alignment bits, and the distance guard against a false match. An alignment of 4096 or more starts
  a page, where nothing below may be readable, so those blocks are kept in a registry (1024 chains by page number
  under a spin lock, machine.state 27328 to 27359). free and realloc give back the original block; realloc of an
  aligned block gives a plain one, as C allows. An ordinary free pays one page-offset test and one load. The aligned
  size limit is 2^39.

## The runtime in SemanticScript, the whole C library: stdio (2026-11-15)

The runtime's C library (D-153) grows toward the whole ISO C library, written in SemanticScript and behaving as glibc
does in the C locale. Step one is stdio, which needs variadic functions. Decided by delegation:

- **D-156** The runtime's DSL (docs/refined-examples/stage0/tools/semgen.py), which writes the runtime's `.sem` files,
  gains `calc <name> = <expression>`, `calc <name> := <expression>` (a `set` of a mutable let), and
  `when <expression> <yes> <no>`, and a call statement's arguments may be expressions. Each operator is written out
  as the explicit call it stands for, one call entity each (`a * b + c` of Float64 values is `math.multiplyFloat64`
  then `math.addFloat64`), with lets for literals of the operand's type (a Float64 written in hexadecimal, `0x1.8p52`,
  is a let of exactly that value; one outside 1e-15 to 1e17 is its bits and `convert.uint64BitsToFloat64`). On
  addresses `+` and `-` with an Int64 are `machine.offset`, and `==`, `!=`, `<` are `machine.equal` and
  `machine.lessThan`. Every operand is evaluated, left to right (`&&` and `||` are `logic.and` and `logic.or`). `set`
  and `return` take a literal, and a call whose result the statement does not name gets a name. Why: the C library
  is tens of thousands of steps, and a DSL line per step made arithmetic unreadable; nothing of this is
  SemanticScript syntax, and the generated modules hold only explicit calls, lets, and branches, as before (every
  existing module regenerates byte for byte).
- **D-157** An `abi library` row may end in `variadic` (`abi library "printf" variadic`): the function takes `...`
  after its own arguments, and `machine.variadicStart()`, only in such an operation, is the address of its `va_list`
  (32 bytes, `llvm.va_start`). The runtime reads the list as each system lays it out (cformat's cursor): x86_64 Linux
  (`gp_offset`, `fp_offset`, `overflow_arg_area`, `reg_save_area`), AArch64 Linux (`__stack`, `__gr_top`, `__vr_top`,
  `__gr_offs`, `__vr_offs`), and Windows (a pointer, eight bytes an argument, a double in its integer slot); a
  v-function's `va_list` argument is the list's address on Linux (an array) and the list itself on Windows (a
  pointer). Also for the C library: `Float32` crosses the C boundary (C's float), `machine.loadFloat32` and
  `storeFloat32`, and an `abi library` operation may give a record of two `Int64` (`ldiv_t`): returned in two
  registers on x86_64 Linux and AArch64, and on Windows through memory the caller passes first (the compiler wraps the
  operation; Windows x64 returns a 16-byte struct so).
- **D-158** On x86_64 a call through a reference (an operation reference or a bound foreign function) is made as a
  call of a C function of `...`: every argument goes where a fixed one would, and the call also says in %al how many
  vector registers it used (Linux) or copies a double to its integer register as well (Windows). That is what a
  variadic C function such as printf reads its arguments by, and any other function ignores it; without it, printf
  called through `ffi` with a double read garbage. AArch64 is left as it is: Linux passes variadic arguments as fixed
  ones, and on Windows on ARM they differ, so the change would break fixed ones. An executable's program is now
  compiled for the triple it is linked for (it was the host's, retargeted), so this holds in executables built on
  another machine than the target.
- **D-159** printf's engine is the module `cformat`: every conversion of glibc's printf in the C locale (`d i o u x X
  c s p n m % f F e E g G a A`, `C` and `S`, the flags `- + space # 0` and `'` and `I`, which change nothing in the C
  locale, `*` and `*n$` widths and precisions, `%n$` argument numbers, the lengths `hh h l ll q L j z Z t`), as glibc
  writes them: `(nil)` for a null `%p`, `(null)` for a null `%s` unless the precision is below 6, `%p` and `%+p`
  signed like a number, `-nan`, infinities and NaN padded with spaces, a conversion glibc does not know written as it
  stands. Every argument is read first, in the order the format names them, so `*` and `%n$` read what they name.
  A floating value is written from its exact digits: m * 2^e is m * 5^-e / 10^-e for a negative e, a whole number
  kept in base 10^9, rounded at the digit the conversion keeps as the current rounding mode rounds (to nearest, ties
  to even, as glibc's printf_fp does; reading the mode is step 3's). %a writes the hexadecimal digits of the
  significand, without trailing zeros unless a precision asks, rounding there; a subnormal is `0x0.<digits>p-1022`
  and x87's long double `0x8p-3` for 1, as glibc writes them. `L` reads a long double where the system has one (x87's
  80 bits on x86_64 Linux, binary128 on AArch64 Linux) and writes its exact digits too; on Windows `long double` is
  `double`. The text goes to a builder that the stdio functions copy to a stream or a string, and more than INT_MAX
  bytes is -1 with EOVERFLOW.
- **D-160** stdio is the module `cstreams`. A FILE is a block of the library's own (opaque to C, as glibc's is to a
  program that does not look inside it); stdin, stdout, and stderr are blocks in machine.state that the data symbols
  `stdin`, `stdout`, and `stderr` point at. Buffering is glibc's: a terminal is line buffered, other files fully
  buffered with a buffer of the file's `st_blksize` (4096 on Windows), stderr unbuffered, setvbuf and setbuf choose
  otherwise; reading a line-buffered or unbuffered stream first flushes a line-buffered stdout; end of file is sticky
  (glibc 2.28 and later); ungetc keeps 8 bytes. fopen takes `r w a`, `+`, `b` (which changes nothing: no stream
  translates line ends, on Windows either), `x` (O_EXCL, CREATE_NEW), and `e` (O_CLOEXEC); tmpfile is an O_TMPFILE
  file in /tmp (else a named one removed at once) on Linux and a file deleted on close on Windows; tmpnam gives
  `/tmp/file` and six letters or digits no file has on Linux, as glibc, and `file` and six in the current directory
  on Windows, where /tmp is not; rename replaces a file that has the new name (renameat2, MoveFileExW with
  MOVEFILE_REPLACE_EXISTING); remove deletes a file or an empty directory. scanf's engine follows glibc's C99 forms
  (`__isoc99_scanf` and its kin are the same functions under the names glibc's headers give): a conversion gathers
  the bytes that can still become its number and reads them with strtol's or strtod's own code, a byte that ends it
  going back with ungetc, so a conversion consumes what it looked at but that byte; `%[` scansets with ranges and
  `^`; `%l` with c, s, and [ stores wchar_t; `%Lf` stores the double's value as a long double, so it is read to a
  double's precision only; EOF when the input ends before the first conversion is stored. exit and fflush(NULL) flush
  every stream, and a program of SemanticScript that used a C stream through `ffi` has them flushed when it ends (the
  stdio module keeps fflush's address at machine.state byte 2336 and the start module calls it), as glibc's exit
  does under `refined run`. strerror (and so perror and `%m`) gives `Unknown error N` for every number for now: glibc's
  messages are a known gap, left out of every glibc-equality test until they are written.

- **D-161** `refined build semanticscript/runtime --kind clibrary` writes the runtime's C library as one object a C
  program links instead of glibc on Linux, x86_64 and AArch64 (`cc -nostdlib -static program.o <object> -lgcc`): every
  `abi library` function under its C name (the runtime's own `memcpy` and its kin give way to the library's), the data
  symbols `stdin`, `stdout`, `stderr`, and `__stack_chk_guard` as globals filled before main, and a `_start` that keeps
  the kernel's stack, readies the library (the module `cstart`: argv and envp kept, on x86_64 the thread pointer set to
  a block of the library's own with a random canary at 0x28, which gcc's stack protector reads; on AArch64 a random
  `__stack_chk_guard`), runs the program's preinit and init arrays, calls `main(argc, argv, envp)`, and exits with
  what it gives; everything else is internal and what no exported name reaches is dropped. The runtime's own `_start`
  (for programs of SemanticScript) is left out. An object rather than an archive, because there is nothing to choose
  members from: the linker keeps what the program reaches with `--gc-sections` or not, and one file is simplest to
  hand to `cc`. A program with thread-local variables of its own is not supported (the thread block has no TLS
  area). Windows is refused (R901): MinGW's headers assume the Microsoft C runtime's ABI, so there programs reach the
  library through `ffi`. tests/test_cprograms.py compiles each program in tests/cprograms with the system's gcc and
  glibc's headers, links it both ways, and requires the same output, error output, and exit code, byte for byte.

- **D-162** exit calls the functions atexit and `__cxa_atexit` registered, the last first (one registered while they
  run runs too), then flushes every stream, then ends the process; quick_exit calls at_quick_exit's and ends the
  process without flushing; `_Exit` ends it at once. A C program's fini array is registered with atexit before its
  init arrays run, so it runs after every handler the program registers, as glibc's. ldiv, lldiv, and imaxdiv give
  D-157's pair (two registers on Linux). The lists are kept at machine.state 27904 and 27928.
- **D-163** setjmp, `_setjmp`, `__sigsetjmp`, longjmp, `_longjmp`, siglongjmp, and `__longjmp_chk` are `abi library`
  operations whose one call is `machine.saveContext` or `machine.resumeContext`: the compiler emits each as the
  routine itself, a naked function of a few instructions, since only the routine sees its caller's frame. The buffer
  (glibc's `jmp_buf`, opaque to programs) holds the callee-saved registers, the stack pointer, and the return address
  (x86_64: rbx, rbp, r12 to r15; AArch64: x19 to x30, sp, d8 to d15); longjmp with 0 returns 1. The signal mask is
  neither kept nor restored, so sigsetjmp's `savemask` changes nothing. On Windows the routines trap: a program
  reaches the library through `ffi` there, and a foreign call cannot return twice.
- **D-164** signal installs a handler with rt_sigaction as glibc's signal does (SA_RESTART, the handler stays, the
  runtime's restorer), giving the handler before it, and SIG_ERR with EINVAL for a number that has none (SIGKILL and
  SIGSTOP included); raise is kill(getpid(), sig), so a handler runs before raise returns. On Windows there are no
  such signals: the library keeps a table of handlers (glibc's numbers), raise calls the handler, ignores SIG_IGN, and
  for SIG_DFL ends the process with exit code 3 as the Microsoft runtime does; nothing else delivers a signal there.
  abort raises SIGABRT, so a handler runs, then takes the default action (the end of the process by SIGABRT on Linux,
  exit code 3 on Windows). system runs `/bin/sh -c` on Linux (fork, execve, wait4: the wait status, as glibc gives
  it) and `cmd.exe /c` on Windows (its exit code shifted into the same form); system(NULL) is 1 when /bin/sh exists
  (on Windows, always). Signal handlers' table is at machine.state 27952.

- **D-165** The names glibc's headers call under `_FORTIFY_SOURCE` (on by default with optimization on Ubuntu):
  `__printf_chk`, `__fprintf_chk`, `__sprintf_chk`, `__snprintf_chk`, `__vprintf_chk`, `__vfprintf_chk`,
  `__vsprintf_chk`, `__vsnprintf_chk`, `__memcpy_chk`, `__memmove_chk`, `__memset_chk`, `__strcpy_chk`,
  `__strncpy_chk`, `__strcat_chk`, `__strncat_chk`, `__fgets_chk`, `__fread_chk`, and `__chk_fail`. Each checks that
  what it writes fits the size the compiler knows (sprintf's whole text and its 0; snprintf's and fgets's bound; the
  bytes for the others), and otherwise writes glibc's `*** buffer overflow detected ***: terminated` to standard error
  and aborts, as `__chk_fail` does; then it does what the unchecked function does. The printf ones' flag (which asks
  glibc to refuse `%n` in writable memory) asks nothing more here. The wide-character ones belong with wchar.h's
  functions. tests/test_cprograms.py builds every C program at -O0 and at -O2, so the second calls these names.

- **D-166** threads.h is the module `cthreads`: C11 threads on Linux's own threads. thrd_create clones a thread
  (CLONE_VM, FS, FILES, SIGHAND, THREAD, SYSVSEM, SETTLS, PARENT_SETTID, CHILD_CLEARTID) onto an 8 MiB stack with a
  thread block of its own (the thread pointer: it points at itself, holds the stack protector's canary at 0x28 copied
  from the first thread's, errno at 0x40, the thread's record at 0x38, and thread-specific values from 0x80; the first
  thread of a C program gets one too, and on AArch64 tpidr_el0 is set to it). The new thread runs
  `refined_c_thread_main`, which calls the function, keeps what it gives, and runs the storage destructors; the kernel
  clears and wakes the thread id when the thread ends, which thrd_join waits on with a futex before freeing the
  stack. Mutexes (plain, recursive, timed), condition variables, and call_once are futex words; thread-specific
  storage keeps 64 keys. thrd_detach's thread is never freed. (D-169 gives timed waits their deadlines; D-168 gives
  Windows real threads.) Shared state is locked once a thread is started: the runtime's heap
  (its own lock word, so malloc and every block the library takes is safe) and the streams (one recursive lock around
  writing, reading, pushing back, and flushing, so one printf's text is never split). errno is per thread: the first
  thread's stays machine.state's cell, so code that writes that cell keeps working, and a started thread's is in its
  block (`__errno_location` gives the running thread's). New compiler primitives, for the runtime only:
  `machine.compareExchange32` (cmpxchg, sequentially consistent), `machine.threadPointer` and `setThreadPointer`,
  `machine.startThread` (a few instructions of assembly for x86_64 and AArch64 Linux), and the system calls futex,
  gettid, and sched_yield. Windows has no C threads here: a program reaches the library through `ffi` there, with no
  C function to start, so thrd_create gives thrd_error; mutexes, once, and storage work in its one thread. (The DSL
  now writes a decimal Float64 argument as a let of its value, as it does a hexadecimal one.)
- **D-167** fenv.h and fma get three primitives: `machine.loadFloatControl` (MXCSR on x86_64 through
  llvm.x86.sse.stmxcsr; FPCR | FPSR << 32 on AArch64, read with mrs), `machine.storeFloatControl` (ldmxcsr; msr), and
  `machine.fusedMultiplyAdd` and `fusedMultiplyAdd32` (llvm.fma, one rounding: fmadd on AArch64, and on x86_64 an
  operation that uses it is compiled with FMA3, `"target-features"="+fma"`, rather than calling a libm fma that does
  not exist here; every x86_64 processor since 2015 has FMA3). They act on the running thread's own state, the JIT
  process's under `refined run`. They use LLVM's intrinsics, not inline assembly, so an x86_64 executable can still be
  built on an ARM64 machine.

- **D-168** threads.h on Windows starts real threads: thrd_create calls CreateThread at `refined_c_thread_main`
  (`machine.threadEntry`, its address), which first puts the thread's block in a thread-local slot (TlsAlloc once,
  TlsSetValue) where thrd_current and storage find it; thrd_join waits on the thread's handle; thrd_exit is ExitThread
  after the storage destructors; thrd_yield is SwitchToThread. Waits on Windows (a contended mutex, a condition
  variable, the streams' lock) sleep a millisecond and look again, which a futex's caller already does after a wake
  for nothing: WaitOnAddress is in an API-set DLL, not kernel32, and an executable imports kernel32 alone (D-144).
  The heap is HeapAlloc's, which Windows locks itself; the streams' lock takes GetCurrentThreadId. errno stays one cell
  for every thread on Windows, so setting it reaches no system call. New kernel32 rows: CreateThread, ExitThread,
  SwitchToThread, GetCurrentThreadId, TlsAlloc, TlsGetValue, TlsSetValue. The runtime's DSL now refuses a reserved
  word (`none`, `unbounded`, ...) as the name of a value or a block, which the checker would refuse later.
- **D-169** mtx_timedlock and cnd_timedwait honour their deadline (a TIME_UTC timespec): on Linux the wait is
  FUTEX_WAIT_BITSET with FUTEX_CLOCK_REALTIME, which takes the absolute deadline itself, and ETIMEDOUT is
  thrd_timedout; on Windows each millisecond's wait first compares GetSystemTimeAsFileTime with the deadline.
- **D-170** setjmp and longjmp work on Windows too. Windows on ARM keeps the same registers as AAPCS64, so the AArch64
  routine serves both; Windows x64's routine keeps rbx, rbp, rdi, rsi, r12 to r15, xmm6 to xmm15, the stack pointer,
  and the return address. LLVM assembles a routine with the target's own assembler, and llvmlite registers only the
  host's, so an x86_64 object built on an ARM64 machine gets a routine that traps; on x86_64 hosts (CI's Windows
  runner) it is the real one, and cprocess's jumpTest runs it under `refined test` (and the AArch64 one here).

- **D-171** errno is glibc's numbers everywhere. On Linux the library passes on the kernel's own (they are glibc's),
  and it sets EINVAL, ERANGE, ENOMEM, EBADF, EILSEQ, and EOVERFLOW where glibc's functions set them (setvbuf with an
  unknown mode leaves errno alone, as glibc's does; raise(0) is the kernel's check and gives 0). On Windows one table
  (clibrary's windowsErrors) maps each Windows error code a file, pipe, process, socket, or memory call can give to
  glibc's number for the same failure: ENOENT for a file or path not found, EACCES for access denied and sharing
  violations, EEXIST, EBADF, ENOMEM, ENOSPC, EPIPE for a broken pipe, ENOTEMPTY, ENAMETOOLONG, EXDEV, EROFS, Winsock's
  WSAE codes to their errno, and so on (109 codes); any other is EINVAL. tests/cprograms/errno_values.c compares
  errno after 21 failing calls with glibc's.

- **D-172** strerror's messages are glibc's own, taken from glibc rather than written into the runtime: the compiler
  builds the table (`machine.errorMessages`: how many numbers, then each one's message as a C string, or none) by
  asking the machine it runs on, when that machine's C library is glibc (Python's os.strerror is glibc's strerror
  there), for every number from 0 to 4095 that has a message. An executable or C library object built on a glibc
  system (CI's Linux runners, and any Linux machine that builds for Linux) therefore says exactly what that glibc says,
  in every message, and a number without one is `Unknown error N`, as glibc writes it. Built anywhere else (on
  Windows, where Python's strerror is the Microsoft runtime's and differs), the table is empty and every number is
  `Unknown error N`: recorded as the remaining gap, since nothing on such a machine holds glibc's messages and the
  runtime writes none of its own. perror and printf's `%m` use strerror. tests/ctour.py prints strerror for -1 to 135
  through `ffi` and expects os.strerror's text where Python's C library is glibc (and `Unknown error N` elsewhere);
  tests/cprograms/strerror_text.c compares every message, perror, and `%m` with glibc's.

- **D-173** glibc 2.38 and later give C23's names to programs compiled as C23 (and, on newer systems, by default):
  `__isoc23_strtol`, `__isoc23_strtoll`, `__isoc23_strtoul`, `__isoc23_strtoull`, `__isoc23_strtoimax`,
  `__isoc23_strtoumax`, `__isoc23_wcstol`, `__isoc23_wcstoll`, `__isoc23_wcstoul`, `__isoc23_wcstoull`,
  `__isoc23_wcstoimax`, `__isoc23_wcstoumax`, and the scanf family's `__isoc23_scanf`, `__isoc23_fscanf`,
  `__isoc23_sscanf`, `__isoc23_vscanf`, `__isoc23_vfscanf`, `__isoc23_vsscanf`. They read as the C17 names do, and
  also C23's binary numbers: `0b` (or `0B`) in base 2 and base 0, and scanf's `%b` and `0b` under `%i`; a `0b` with no
  binary digit after it reads as 0 ending at the `b`, as `0x` does. The C17 names never take `0b`. Two fixes found by
  CI on Linux against glibc: printf's `%5%` writes a bare `%` (the width is ignored), and scanf's `%f` reads `nan`
  but not the `(chars)` strtod takes after it, stopping before the `(` as glibc's scanf does.

- **D-174** C's long double is the platform's: x87's 80-bit extended format on x86_64 Linux (64 significand bits with
  the leading one written out, 16 bytes in memory), IEEE binary128 on AArch64 Linux (113 bits), and a double on
  Windows (the Microsoft ABI's long double). The compiler has the type `machine.LongDouble` (LLVM's `x86_fp80`,
  `fp128`, or `double`), which an `abi library` operation takes and gives as the C ABI passes it (x87's on the stack
  and in `st(0)`, binary128 in a vector register), `machine.loadLongDouble` and `machine.storeLongDouble`, and
  arithmetic, comparisons, and conversions on it (`addLongDouble`, `lessLongDouble`, `longDoubleFromFloat64`, ...:
  x87 instructions, libgcc's soft float on AArch64). The runtime's long double functions (`clong`) use none of that
  arithmetic: a value is unpacked into parts (sign, kind, power of two, a 128-bit significand), worked on exactly as
  whole numbers, and `settle` rounds the result to the format as the rounding mode rounds (read from MXCSR or FPCR,
  `roundingMode`; printf's rounding of digits reads the same), so each function is exact on all three formats and is
  tested on all three from any machine (every operation takes the layout: 0 double, 1 x87, 2 binary128, 3 float).
  clong has fabsl, copysignl, frexpl, ldexpl (ERANGE), scalbnl, scalblnl, ilogbl, logbl, nanl, truncl, floorl, ceill,
  roundl, rintl, nearbyintl, lrintl, llrintl, lroundl, llroundl, modfl, fmaxl, fminl, fdiml, nextafterl,
  nexttowardl, nexttoward, nexttowardf, fmodl, remainderl, remquol, and sqrtl (bit by bit, correctly rounded). Past
  the largest finite value a rounding toward zero (or downward for a positive value, upward for a negative one) gives
  the largest finite value rather than an infinity, as IEEE 754 says. strtold (in `cformat`) reads what strtod reads
  (strtod finds the end, the infinities and the NaNs) and rounds once: a decimal number's significant digits are
  compared exactly with the decimal expansion of candidates m * 2^e (`decimalDigits`), first to find the power of two
  at or below the value, then for each significand bit from the top to two below the format's last, then for whether
  anything is left; a hexadecimal number's digits are its bits. ERANGE comes with an overflow and with a subnormal or
  zero result that is not exactly the text's value. wcstold reads the ASCII characters of a wide string the same way,
  and scanf's `%Lf` (`%Le`, `%Lg`, `%La`) stores what strtold reads rather than a double widened. The transcendental
  `l` functions (expl, logl, sinl, powl, ...) and fmal are not in this piece: they come with `cmathlong`.
  tests/cprograms/long_double.c compares strtold, wcstold, the exact functions, printf's `%La` and `%.30Lg`, and
  sscanf's `%Lf` and `%La` with glibc's on Linux, and `cformat.longTextTest` checks strtold for the double layout
  against strtod (bits, ends, errno) and for x87, binary128, and float against values computed exactly.

- **D-175** A record of two numbers crosses the C boundary as the C ABI passes a struct of them: two Int64 (ldiv_t,
  D-157), two Float64 (`double complex`), or two Float32 (`float complex`), as an input or output of an `abi library`
  operation and of a foreign function bound with `ffi.Function`. Windows x64 passes a 16-byte struct by reference and
  returns it through memory the caller gives, and a struct of two floats as one integer register; x86_64 Linux packs
  two floats into one vector register and splits two doubles or two longs into two registers; AArch64 (Linux and
  Windows) passes two doubles or two floats as a homogeneous aggregate in two vector registers and two longs in two
  integer registers. The compiler wraps the operation (`library_function`) or the call (`foreign_pair_call`) so the
  record's own value is what SemanticScript sees on each side.

- **D-176** Wide stdio, as glibc has it in the C locale, whose multibyte encoding is ASCII (D-177). A stream has an
  orientation (FILE offset 96: 0 none yet, 1 wide, -1 bytes), which its first use gives it and only freopen takes
  away: fwide sets or tells it; fputwc, fputws, the wide printf family, and the wide scanf family make a stream wide
  and refuse a byte stream (WEOF, -1, EOF), and printf, scanf, fputs, puts, and fwrite make it bytes and refuse a
  wide one, as glibc's do; fgetwc, fgetws, ungetwc, getc, fgets, fread, and putc only orient a stream that has none.
  A wide stream reads and writes each wide character from 0 to 127 as its byte; writing one past 127 fails with
  EILSEQ and sets the stream's error, what came before it written (glibc buffers wide characters and fails when it
  converts them, at a flush: a recorded difference of timing), and reading a byte past 127 gives WEOF with EILSEQ
  and the error. The wide printf family (wprintf, fwprintf, swprintf, their v forms, and `_FORTIFY_SOURCE`'s
  `__wprintf_chk`, `__fwprintf_chk`, `__swprintf_chk`, and their v forms) runs printf's engine in a wide mode: the
  wide format is made bytes, a character past 254 as 255 and six bytes holding six of its bits each
  (`cformat.addUnit`: no byte of it is `%` or 0), `%c`, `%s`, `%lc`, and `%ls` write wide characters padded and cut
  by characters, `%n` and the result count characters, and the text is turned back into wide characters, so
  swprintf keeps every character; `%s` of a byte past 127 fails the whole call with EILSEQ, nothing written, as
  glibc's does; swprintf gives -1 when the text and its 0 do not fit, the first n - 1 characters written and no 0.
  The wide scanf family (wscanf, fwscanf, swscanf, their v forms, and their `__isoc99_` and `__isoc23_` names) runs
  scanf's engine over the wide format's bytes up to its first character past 127, which no input could match, and
  swscanf reads its wide text's characters up to its first past 127 (a recorded limit: a wide string scanned for
  `%ls` stops there). fgetws has `__fgetws_chk`. wcsftime (module `cwidetime`, after ctime) is strftime's text as
  wide characters, its format made bytes the same way and passed to `ctime.formatTime`, which ctime now exports.

- **D-177** glibc's C locale converts ASCII only: CI's comparison in glibc's real C locale shows btowc(128 to 255)
  giving WEOF, mbrtowc of a byte past 127 giving -1 with EILSEQ, and wcrtomb of a wide character past 127 the same,
  where D-184 had taken the bytes 128 to 255 as the wide characters of the same values. The runtime now does as
  glibc does throughout: cwide's mbrtowc, mbrlen, mbtowc, mblen, mbrtoc16, mbrtoc32, mbstowcs, and mbsrtowcs refuse
  a byte past 127 (EILSEQ; mbsrtowcs leaves the source at it), its wcrtomb, wctomb, c16rtomb, c32rtomb, wcstombs,
  and wcsrtombs a wide character past 127, btowc and wctob give WEOF and EOF past 127; printf's `%lc` and `%ls` of
  a character past 127 fail the whole call with EILSEQ, nothing written, and so does wprintf's `%s` of a byte past
  127; wide streams read and write ASCII (D-176). tests/cwidetour.py's model and its section "high bytes" expect
  exactly that.

- **D-178** glibc sends a program compiled as C23 (a newer compiler's default) to `__isoc23_sscanf` and its kin and
  any other to `__isoc99_sscanf`, and the two read `nan(chars)` differently: on CI's Ubuntu 26.04 a C23 program's
  sscanf of `nan(123) 1e400 1e-400` with `%lf %lf %f` reads all three, while on Ubuntu 24.04 a C17 program's stops
  at the `(` (D-173). The runtime's scanf engine takes the `(chars)` after `nan` (letters, digits, `_`, then `)`)
  for the `__isoc23_` forms only; tests/cprograms/stdio_scanf.c prints which of glibc's names its headers chose.
  Two fixes found by CI with it: thrd_join's private futex wait that the kernel's clear-tid wake never reached
  (4d580f2), and the unlock of a contended lock (threads.h's mutexes, the heap's and the streams' locks), whose
  plain store of 0 let a critical section's writes drift past it on AArch64; each is now a seq_cst
  compare-exchange, as is call_once's done flag and its read. nexttoward and nexttowardf compared their double or
  float with the long double target by normalizing both to long double's precision in place, so they then stepped
  at the wrong precision on x87 and binary128; they compare copies now. The JIT on AArch64 Linux loads libgcc_s, which
  holds the soft float routines (__addtf3 and its kin) that binary128 arithmetic calls, as an executable links
  libgcc.

## The runtime in SemanticScript, the C library and a loader (2026-11-15)

`ffi` was the one module an executable on Linux refused (D-145): `ffi.open("c")` asked for glibc, which a static
process with no C library cannot host. The runtime now has a C library of its own, written in SemanticScript, which
`ffi.open("c")` binds on Windows and on Linux alike, and a loader of ELF shared libraries for every other name on
Linux. Decided by delegation:

- **D-153** The runtime's C library is the module `clibrary`: each function an `abi library "<name>"` operation (D-155)
  under its C name, behaving as glibc does in the C locale, on Windows too, so a program's foreign calls give the
  same results on both. It has ctype.h (`isalnum` to `isxdigit`, `isascii`, `toascii`, `toupper`, `tolower`, each
  classifier giving glibc's class bit, 1024 for `isalpha('A')`, and `__ctype_b_loc`, `__ctype_toupper_loc`,
  `__ctype_tolower_loc`, the tables glibc's macros read, for -128 to 255); string.h (`strlen`, `strnlen`, `strcmp`,
  `strncmp`, `strcasecmp`, `strncasecmp`, `strcpy`, `strncpy`, `strcat`, `strncat`, `strchr`, `strrchr`, `strstr`,
  `strspn`, `strcspn`, `strpbrk`, `strdup`, `strndup`, `memchr`, `memcmp`, `memcpy`, `memmove`, `memset`; a
  comparison gives the difference of the first differing bytes as unsigned chars); stdlib.h (`abs`, `labs`, `llabs`
  wrapping at the most negative value; `div`, whose `div_t` every 64-bit C ABI returns in one register, so it is an
  `Int64` with the quotient in its low half; `ldiv` and `lldiv` return two registers or memory and are not there;
  `atoi`, `atol`, `atoll`, `strtol`, `strtoll`, `strtoul`, `strtoull` as glibc reads them: white space, a sign, `0x`
  in base 16 and base 0, `0` for octal in base 0, `0x` with no hexadecimal digit after it read as `0` ending at the
  `x`, the limits with ERANGE, EINVAL for a base that is neither 0 nor 2 to 36 with the end not stored; `strtod` and
  `atof`: `inf`, `infinity`, `nan`, `nan(chars)` in any case, hexadecimal numbers rounded to nearest even with
  subnormals, decimal ones normalized and read correctly rounded by the `floats` module, HUGE_VAL with ERANGE past
  the largest double, ERANGE for a decimal result that is subnormal or 0 from nonzero digits and a hexadecimal one
  that is so inexactly; `malloc`, `calloc`, `realloc`, `free` on the runtime's heap (blocks aligned to 16 and
  zeroed, NULL with ENOMEM past PTRDIFF_MAX or for a `calloc` that overflows, `realloc` to 0 bytes freeing, as
  glibc's; a heap the system cannot grow traps as the runtime's heap does); `qsort`, a stable merge sort as glibc's
  is, and `bsearch`, glibc's halving, both calling the caller's comparison (`machine.callComparison`); `getenv`, the
  environment the Linux process started with, and on Windows a UTF-8 copy the next `getenv` replaces, as C allows;
  `exit` and `_exit`, which end the process at once (the runtime writes as it goes, so nothing is buffered; nothing
  registered with `__cxa_atexit` runs); `abort`, SIGABRT with its default action on Linux, exit code 3 on Windows
  as the C runtime's abort; `__errno_location`, one errno cell); math.h's basics (`fabs`, `copysign`, `trunc`,
  `floor`, `ceil`, `round`, `fmod` exactly by musl's integer algorithm, `sqrt` by `machine.squareRoot`, one
  instruction; `floor` and the like are not LLVM intrinsics here because on x86_64 without SSE4.1 they lower to calls
  of libm); stdio.h's writes (`puts`, `putchar`, `fputs`, `fputc`, `putc`, `fwrite`, `fflush`): a stream is the number
  1 (stdout) or 2 (stderr), which the data symbols `stdout` and `stderr` hold, and nothing is buffered, so C's lines
  and the program's come out in the order they were written; and what glibc's start files and stack protector make
  compiled code call: `__stack_chk_fail` (glibc's message, then abort), `__stack_chk_guard` (a data symbol, random),
  `__cxa_finalize` and `__cxa_atexit` (nothing is run at exit, as at `_exit`). `long` and `size_t` are 64 bits
  everywhere (LP64), Windows included, where the C runtime's `long` is 32. `ffi.open` binds this library for `c` on
  every system and on Linux also for the files the C library and its parts are, `libc.so.6`, `libm.so.6`,
  `libpthread.so.0`, `libdl.so.2`, `librt.so.1`, and `m` (`find_library("m")`'s); `ffi.Function.bind` finds a name in
  the table and then among the data symbols, and a name it does not have is `symbolMissing` exactly as under `refined
  run`. On Windows `c` no longer loads ucrtbase: a program that binds a function the runtime's library lacks gets
  `symbolMissing` where `refined run` finds it, and ctype's classifiers give glibc's bits where ucrtbase's differ;
  other names still load with LoadLibraryW. The executable stays free of the C library (D-144): `libc.so.6` and
  `ld-linux-*` appear in an executable that reaches `ffi` only as names the runtime recognizes, so `assert_no_libc`
  now looks for what linking glibc would leave (`GLIBC_` versions, `__libc_start_main`, an interpreter path) besides
  a dynamic section. `c` is the C library with math.h on every system: glibc keeps math.h's functions in libm.so.6,
  so `refined run` on Linux binds `c`'s names from libc.so.6 and then libm.so.6 (host.py), as the executable finds
  them in its one library. tests/ctour.py binds the scalar functions and builds strings in memory the library gave;
  the executable prints what glibc gives (`expected()`), and on Linux exactly what `refined run` prints.
- **D-154** `ffi.open` of any other name on Linux maps an ELF shared library with the runtime's loader, the module
  `loader`, as `dlopen(name, RTLD_NOW)` would: a name with `/` is a path, any other is looked for in
  LD_LIBRARY_PATH, then the asking library's RUNPATH (or RPATH) with `$ORIGIN`, then the system's library
  directories (`/lib/<arch>-linux-gnu`, `/usr/lib/<arch>-linux-gnu`, `/lib64`, `/usr/lib64`, `/lib`, `/usr/lib`; the
  ld.so cache is not read). A file that is not a 64-bit little-endian ET_DYN object for this machine, like a name no
  file has, is notFound, as dlopen's failure is; a library is loaded once, known by its file's device and inode, and
  stays loaded (`ffi.close` gives the handle back, as before). Its PT_LOAD segments are mapped from the file
  (MAP_FIXED, private) inside a span reserved at a base the kernel picks, each with its protection, the rest of a
  last file page zeroed and pages past the file anonymous; its DT_NEEDED libraries load first (the C library and its
  parts, and the dynamic loader's own name, stand for the runtime's C library), and a library it needs that is not
  found makes it notFound; then its relocations are applied and bound at once: DT_RELR, DT_RELA, and DT_JMPREL, the
  types RELATIVE (base plus addend), 64 and ABS64, GLOB_DAT, and JUMP_SLOT (symbol plus addend) on x86_64 and
  AArch64. A symbol is the library's own definition when it defines it, else the first definition found through
  DT_GNU_HASH (or DT_HASH) in its libraries breadth first, then the runtime's C library; a weak symbol nothing
  defines is 0. Then DT_INIT and DT_INIT_ARRAY run, in order, after its libraries'. `ffi.Function.bind` looks a name
  up as `dlsym` does in the library's scope: the library, its libraries breadth first, and the runtime's C library
  only when one of them needs the C library. What the loader cannot do right it never does wrongly: a library with
  thread-local storage (PT_TLS, a TLS relocation, an STT_TLS symbol, DF_STATIC_TLS), an ifunc (IRELATIVE,
  STT_GNU_IFUNC), text relocations (DT_TEXTREL, DF_TEXTREL), DT_REL, a relocation of any other type, or a symbol
  neither its libraries nor the runtime's C library define traps, with ``trap: `ffi.open` cannot load `<path>` in an
  executable with no C library: <why> (D-154); run the program with `refined run` ``. A trap and not an error value,
  because `ffi.LoadError` has two variants and a third would make every exhaustive `match` of it incomplete, and
  `notFound` would be false: the library is there, and `refined run` loads it. Code a loaded library runs reads the
  stack protector's canary through the thread pointer on x86_64 (`%fs:0x28`), so before the first initializer runs
  an executable sets the thread pointer (`arch_prctl(ARCH_SET_FS)`, D-155) to a block of its own that points at
  itself with a random canary at 0x28 (under `refined run` and `refined test` the thread pointer is the C library's and
  is left alone); on AArch64 the canary is the data symbol `__stack_chk_guard`, filled from getrandom. An
  initializer is called with one argument, 0 (glibc passes argc, argv, and envp; the start files' do not read them).
  tests/loadtour.py compiles a probe library on the Linux runner (linked with libc.so.6, a constructor, a pointer to
  strlen in its data, a library it needs through `$ORIGIN`, functions with stack protectors) whose thousands of
  probes give exactly what the same library gives calling glibc through ctypes, one linked with no C library that
  calls strlen, and libraries with thread-local storage, an ifunc, and a missing function, which trap.
- **D-155** The compiler gains what the C library and the loader need, for the runtime only, as D-121's primitives
  are. An operation's `abi` row may be `abi library "<name>"`: the C calling convention and D-123's rules (inputs and
  output the C ABI passes as they are, nothing raised, not generic, not async), one operation per name, but no linker
  symbol: its LLVM function is `refined.c.<name>`, so LLVM never takes it for the library function it is named after
  (a `strlen` loop recognized as a call of `strlen` would call itself), and an executable that does not reach `ffi`
  drops it. `machine.cLibrary()` is the address of a table the compiler builds of every such operation, sorted by
  name: the count, then for each the name's address, its length, and the function's address (constant, internal).
  `machine.callComparison(function, left, right)` calls `int function(const void *, const void *)`, the comparison a
  C caller hands qsort and bsearch, the third place the language calls an address (after D-131's `callWithAddress`
  and the program's own operation references). `machine.squareRoot` is `llvm.sqrt`, which is one instruction on
  x86_64 (SSE2) and AArch64 and needs no libm. `system.archPrctl` is x86_64's arch_prctl; AArch64 has no such call,
  so it has no number there and the backend lowers it to a trap, never reached since the runtime asks
  `system.aarch64()` first.

## Data structures for self-hosting (2026-11-14)

A compiler written in the language needs tokens and AST nodes (records and
enums with payloads already suffice), trees, growable lists (`list.List`),
symbol tables keyed by text, and loops over collections whose size is known
only at run time (`maxIterations <name>`, where the name is an immutable
`Int64` such as a `length` result, already works: the bound is read when the
loop is entered and passing it traps, D-45). The audit found that a record
holding a list of itself was accepted and then crashed the backend, that a
`Map` could not have `String` keys, and that a map could not be read in full.

- **D-60** Trees are lists of nodes with a typed position (LR-25 rule 5,
  now enforced). `<Alias> aliasOf Int64` with `<Alias> indexes <List>` makes
  the alias the position type of that `list.List` type of the same module:
  its `get` and `set` take the alias, not `Int64`, and it gains
  `appendIndexed` (item in, the new item's position out). A position has no
  literal (R403); it comes only from `appendIndexed`, and a position the
  list does not have is `list.IndexOutOfRange`, so a stale or foreign
  position is an error, never a stray read. A list type has one index alias,
  the alias is `aliasOf Int64`, and `indexes` names a list type (R403). A
  type may no longer hold itself inside a collection either (R403, beside
  the by-value rule): one way to build trees, no pointer types, and nothing
  the region model cannot see. Why not an indirection type living in a
  region: it would be a second, pointer-like way to reach a value, with a
  lifetime the checker would have to track per node; a position is a plain
  number checked at every read.
- **D-61** A map's key is a plain value or a `String` (the library-only
  constraint `@key`; R403 otherwise). A `String` key is passed by loan
  (`lend`, R406 for `copy`), compared by content, and copied into the map's
  own region the first time it is put, so a key read back lives as long as
  the map, whatever region the caller's text was in. Why: symbol tables are
  keyed by names, and copying on first put keeps the map's contents in the
  map's region, the same rule `string.concat` follows.
- **D-62** A `forEach` may read a map: `branch ifNext <map> bind <key>
  <KeyType>` visits each key once, in the order keys were first put
  (putting an existing key again keeps its place). The loop rules are those
  of a list: inside it the map cannot be changed, lent exclusively, or given
  away (R515), and passing `maxIterations` traps. Why: a compiler lists a
  symbol table (to report unused names, to emit declarations) in a stable
  order; insertion order is deterministic where hash order is not.

Not done in this pass: a `growing` region strategy. Both runtimes already
take a region's memory on demand, block by block, with `maxBytes` as the
ceiling at which allocation traps (D-49), so nothing is reserved up front;
a separate strategy becomes useful only if `arena` starts reserving its
whole capacity.

The `symbols` example (`docs/refined-examples/symbols`) uses these rules: it
builds `(1 + 2) * x` in a node list, defines names in a `String`-keyed
symbol table, evaluates the tree by recursion under `maxRecursion 64`, and
lists the table in definition order, with a test per invariant.

### Text, source positions, and tooling for a compiler (D-70 to D-73)

Toward a compiler written in SemanticScript: what a lexer needs from text,
positions for diagnostics, and the tools to look inside one. The `lexer`
example (`docs/refined-examples/lexer`) is the proof: it reads the file its
command-line argument names, tokenizes it with a line and column per token,
reports an invalid byte as `path:line:column: why`, and writes the token list
to `<path>.tokens`.

- **D-70** `string.slice` keeps characters whole. A slice whose start or end
  falls inside a UTF-8 sequence (on a continuation byte, `10xxxxxx`) is
  `outOfRange` carrying the start, like any other bad range. Before, a slice
  could cut a character in two and hand back text that is not UTF-8; byte
  offsets a lexer computes from whole characters never hit the new error.
- **D-71** `string.Position` is a library record (`offset`, `line`,
  `column`, all `Int64`; line and column count from 1), built with
  `string.Position.new` and read by field like any record.
  `string.advancePosition text position` returns the position after the
  character at `position`'s offset: a character is the UTF-8 sequence its lead
  byte announces when that many continuation bytes follow, and any other byte
  is a character of its own, so invalid text still advances. A newline byte
  moves to column 1 of the next line; anything else moves one column. An
  offset outside the text is `outOfRange` carrying the offset; a line or
  column past `Int64` traps. Why a target: every lexer and every diagnostic
  needs it, getting UTF-8 widths right takes some thirty rows, and it is
  lowered inline, so it runs the same in `run`, standalone executables, and
  WebAssembly.
- **D-72** `byte.isPunctuation`: the 32 printable ASCII bytes that are not
  letters, digits, or space (`!` to `/`, `:` to `@`, `[` to `` ` ``, `{` to
  `~`). It includes `"` and `_`, so a lexer that gives them their own meaning
  tests for them first, as the example does. Nothing else was missing: the
  lexer's arithmetic and comparisons (`compare.*Byte`, `compare.*Int64`,
  `math.subtractInt64`, `logic.or`, `convert.byteToInt64`) were already named
  targets, so no expression syntax was needed (the owner's instruction).
- **D-73** The debugger's `vars` shows a record whose fields are integers or
  `Bool` by field (`{offset 12, line 1, column 13}`) and an enum in the narrow
  layout by variant (`integer(42)`, `newline`), where it showed `<value>`.
  Other records and enums still show `<value>`.

Also confirmed on the example: `match`/`case` binds token-kind payloads
(`Int64`, `Byte`) and a record payload (`LexError` carries a
`string.Position`); a path taken from `process.argument` is checked against
the capability's scope when the file is opened (D-38), and a path outside it
traps before the file is touched; `buffer.ByteBuffer` builds the output and
`fs.writeAll` writes it; `--trace`, `--coverage`, `--profile`, and `--debug`
all work on it. The conformance suite gains a "Text and source positions"
guarantee whose run checks pass command-line arguments (`Check.args`).

### Library and generics for self-hosting (D-90 to D-94)

From `docs/self-hosting-gaps.md` (roadmap items 7, 10, and 11): the numbers,
text, and bytes a compiler written in the language computes with, and generic
code that can be layered. Every new target is lowered inline, so it runs the
same under `refined run`, in standalone executables, and in WebAssembly; only
the two float conversions call the core runtime, as `string.fromInt64`
already did.

- **D-90** Every integer type the language declares computes. `Int8`,
  `Int16`, `Int32`, `Int64`, `UInt8`, `UInt16`, `UInt32`, `UInt64`, and
  `Byte` each have `math.{add,subtract,multiply,divide,remainder}<Type>`
  (trapping on overflow, on an unsigned result below zero, and on division
  by zero), `math.{wrapping,saturating}{Add,Subtract,Multiply}<Type>`,
  `compare.<six comparisons><Type>`, and `bits.{and,or,xor,not,shiftLeft,
  shiftRight}<Type>`; the signed types also have `math.negate<Type>` and
  `math.absolute<Type>`. A shift amount is an `Int64` from 0 to the width
  less one (any other amount traps); `shiftRight` keeps the sign of a signed
  type and fills with zeros for an unsigned one. `Float32` gains the four
  arithmetic targets and the comparisons. Conversions go through two hubs:
  every integer type to and from `Int64`, every narrower unsigned type to and
  from `UInt64`, `ExitCode` to and from `Int64`, `Float32` to and from
  `Float64`; a conversion traps exactly when the value does not fit (so
  `int64ToExitCode` now traps outside 0 to 255, the range `ExitCode`
  declares, where it used to check the `Int32` range).
  `convert.int64BitsToUInt64` and `uint64BitsToInt64` reinterpret the 64
  bits and never trap, for hashing. A conversion is named
  `<source>To<Target>` with the source's leading capitals in lower case
  (`uint64ToInt64`, `int8ToInt64`). Why every type, not removal: the types
  were already declared and range-checked as literals, `UInt64` is what a
  compiler needs to read a literal above `Int64` maximum and to hash, and a
  name per type keeps the one pattern (no overloading, D-47). `ExitCode` stays
  a status: it converts and nothing more.
- **D-91** Text and bytes without the host. `string.compare` returns
  `string.Ordering` (`less`, `equal`, `greater`), comparing bytes as unsigned
  numbers (code point order for UTF-8), a prefix ordering first.
  `string.endsWith`. `string.findFrom text needle start` searches from a byte
  offset and returns the offset in the whole text; it fails with
  `string.FindError` (`absent`, or `outOfRange` carrying a start outside 0 to
  the length). `string.fromByte` makes a one-byte text and fails with
  `string.Utf8Error.invalidAt 0` for a byte of 128 or more, since that byte
  alone is not UTF-8. `string.fromUInt64` and `string.toUInt64` (decimal;
  `notANumber` outranks `outOfRange`: every byte is read before deciding),
  `string.fromUInt64Hex` (lower-case, no prefix, no padding) and
  `string.fromByteHex` (exactly two digits) are the hex formatting an emitter
  needs; they stand in for `buffer.appendHex`, since `buffer` is a host
  target and composing `fromByteHex` with `buffer.appendString` gives the
  same text. `string.fromFloat64` writes the shortest text that reads back as
  the same value (as `console.writeFloatLine` prints it), and
  `string.toFloat64` reads `-`? digits (`.` digits)? (`e` sign? digits)?,
  nothing else, failing with `notANumber` or `outOfRange` (too large for a
  `Float64`). The `bytes` module reads a `Bytes`: `length`, `byteAt`,
  `slice` (a view, like `string.slice`, but with no character rule), and
  `equals`; positions outside it are `bytes.BytesIndexError.outOfRange`.
- **D-92** Generic code layers. A `typeInstance` or `operationInstance`
  states `<name> in none` (it belongs to the module, and names concrete
  types) or `<name> in <operation>`: it belongs to that generic operation of
  the same module, its type arguments may name that operation's type
  parameters, and only that operation uses it (R402 elsewhere, and it is
  never exported). So a generic operation calls another generic operation at
  its own type parameter (`pickAt in bestOf`, `pickAt instantiates pick T`)
  and holds lists, options, and operation types of it (`ItemsT in bestOf`,
  `ItemsT instantiates list.List T`). An instance's signature is seen in the
  caller's types: where the generic operation's signature uses one of its own
  instances, the caller must have declared the instance of the same generic
  at the same arguments in its own scope (R403 at the `instantiates` row,
  naming what is missing), so every value passed has a type the caller names.
  Instances stay named entities with no inference (LR-24); the backend
  compiles one copy of the generic operation per set of concrete arguments,
  as before. Why an `in` row and not a different kind: it is the row calls,
  tasks, and regions already use to say which operation owns them, and `in
  none` keeps every instance's rows the same.
- **D-93** Sets of text, read in order. A set's item is a plain value or a
  `String`, like a map's key (D-61): a `String` item is lent (R406 for
  `copy`), compared by content, and copied into the set's region when first
  added. A `forEach` reads a set with `branch ifNext <set> bind <item>
  <Type>`, item by item in the order first added (adding an item again keeps
  its place), under the loop rules of a list or map (R515). Sets remain host
  targets until the native runtime has them; the host keeps the order (the
  compiler asks `set.Set.itemAt` for each position below the length).
- **D-94** An operation type may be generic: `typeParameter <T> plain|any`
  rows, as on records and enums (the row was `none` only). Like every
  generic, it is used through a `typeInstance` (`BetterNumber instantiates
  Better Int64`), whose type is an operation type with the arguments put in;
  inside a generic operation, an instance stated `in` it names the
  operation's own parameter (`BetterT instantiates Better T`), so a
  comparison over `T` is passed in. Naming any generic type directly where a
  type is expected, outside an `instantiates` row, is R402.

The `layered-generics` case (`tests/suite/programs/14-types-generics`) uses
D-92 and D-94 together: `bestOf<T>` reads a `list.List T` by `forEach`, judges
items with a `Better T` passed in, and keeps the winner through `pick` at its
own `T`; it runs at `Int64` and at `Byte`, under the JIT and as an executable.

### Standalone executables with the host library (D-80 to D-85)

Superseded where they describe `native_runtime.c`, which stage 5 deleted (D-141, D-143): executables now link
the runtime in SemanticScript, whose tasks wait on fibers (D-133, so `group-first-failure` holds in an executable
too), whose captured children are pumped between tasks with no helper thread (D-136), and which implements
channels, secrets, crypto, and on Windows foreign libraries (D-137). What D-80 to D-85 promise about behaviour
(the same variants, payloads, scopes, claims, traps, and region accounting as `refined run`) still holds.

Roadmap items 1, 2, 3, and 15 of `docs/self-hosting-gaps.md`: a program that
reads its arguments and files, builds text, keeps maps, and runs a child
process now builds with `refined build --kind executable` and runs with no
Python. The `lexer`, `symbols`, and `warehouse` examples do, with the same
output, errors, exit codes, and written files as `refined run`
(`tests/test_native.py`).

- **D-80** The host library is implemented twice, in `host.py` for the JIT
  and in `native_runtime.c` for executables, behind the same callback:
  compiled code calls `refined_host` with `<target>|<slots>|<results>` in
  both, so code generation does not change and one IR serves both. The C side
  parses each name once and caches it by the constant's address. Its
  `TARGETS` table is the one list of what is native, with each target's
  scoped parameter; `native.py` reads it, and a test checks it and every
  error-variant number against `library.py` and `host.py`. Each target
  matches `host.py` exactly: the same variants and payloads (errno as Python
  classifies it, including Windows error codes mapped as Python maps them),
  D-38 scope checks with links and `..` resolved as `os.path.realpath` does,
  D-52 one writer per file, handles that trap by kind when used after
  `close` or after their region is released, maps keyed by content for
  `String` keys copied once into the map's region (D-61) and iterated in
  first-put order (D-62), and the same accounting of region bytes, so
  `arena.remaining` agrees. Why a second implementation rather than one
  shared C library: the JIT's tasks are threads and its waits are
  cancellable through the scheduler in Python; the executable's are not.
- **D-81** What stays host-only, refused at build time with R901 naming the
  targets: `net` and `http` (sockets and the scheduler-driven waits), `channel`
  (a send or receive must wait for another task, which cannot happen when
  tasks run when started), `json`, `crypto`, `secret` (large, and no compiler
  needs them), `random` (`newGenerator` promises the JIT's exact sequence,
  Python's Mersenne Twister), `signal` (needs asynchronous delivery), and
  `ffi` (dynamic loading). Everything else in the library is native,
  including `log`.
- **D-82** The generated entry is `main(int argc, char **argv)`; it hands the
  command line to `refined_start`, so `process.argument 0` is the first word
  after the program's name, as after `--` under `refined run`. On Windows the
  words come from the wide command line as UTF-8, and the standard streams
  are binary, as Python makes them: a line ends with one `\n` byte. On POSIX
  `SIGPIPE` is ignored, as in Python, and restored for child processes.
- **D-83** Waiting in an executable. Tasks still run to their end when started
  (D-37), so `cancelled` never happens and a sibling's failure cannot cut a
  waiting task short (the conformance check `group-first-failure` therefore
  runs under the JIT only). Deadlines hold as under the JIT: a file read or
  write checks its deadline before it starts; standard input, child
  processes, and locks wait at most until the deadline (`poll` and `waitpid`
  on POSIX, wait functions and pipe threads on Windows) and then fail with
  `timedOut`, stopping the child. Standard output is flushed before a child
  starts and before anything is written to standard error, so the streams
  interleave as the JIT's unbuffered writes do. A child is always waited for
  before the program continues, so at a trap (D-51) only open files remain
  to be released.
- **D-84** A region in an executable allocates by bumping a pointer through
  chunks (4 KiB doubling to 1 MiB; a block over 256 KiB gets its own chunk),
  instead of one `calloc` and list node per allocation; memory still starts
  zeroed and the capacity still counts the bytes asked for. The recursion
  counter is a table indexed by each recursive operation's id that grows as
  needed, where it was `depth[op & 4095]`, which aliased past 4,095 recursive
  operations. A task starts with its own counters, as it does on its own
  thread under the JIT.
- **D-85** A trap prints the JIT's trace: the running task's operations only,
  repeats collapsed with their depth however deep (the frame table grows; it
  was capped at 65,536 entries), at most 12 lines then `... and N more`, then
  a line naming the task inside a task, then the D-51 release
  line. The C runtime is compiled once per compiler and source text and kept
  in the temporary directory, so linking a program compiles only its `main`.

## Explicitness audit (2026-11-13)

Measures the current compiler against P-2.

### Method

For each row in the examples, apply one mutation and run `check --strict`:

- **DEL**: delete the row (not applied to `is` rows).
- **DROP**: remove the row's last token.
- **ADD**: append a junk token (`zzExtraToken`).
- **DUP**: repeat the row on the next line.

A mutation is "accepted" if the check still reports `ok: true`. Up to 12 rows
were tested per (kind, predicate, mutation). The audit scripts were removed in Part 6 along with the compiler they measured;
they are in git history before that change.

### Coverage

- 224 of 243 examples pass `check --strict` unmodified and were used.
- 2,682 checks over 73 (kind, predicate) pairs.
- The compiler's `ALLOWED_PREDICATES` table has 259 structural pairs across 23
  kinds; the usable examples exercise 59 of them. Ten kinds have no coverage:
  `errorCase`, `function`, `htmlTemplate`, `intrinsic`, `platform`, `region`,
  `semsig`, `sharedState`, `typestate`, `webServer`.
- So these results are a floor. Most of the vocabulary has no strict-clean
  example to test against, which is itself a gap.

### Results

| Mutation | Predicates accepting it | What it means |
| --- | --- | --- |
| ADD (junk token) | 54 of 73 | Token count is not enforced (P-2.2) |
| DROP (last token) | 43 of 72 | A payload token is optional (P-2.1, P-2.2) |
| DEL (row) | 34 of 73 | The row is optional or defaulted (P-2.1) |
| DUP (row) | 37 of 73 | Duplicates pass silently (P-2.3) |

**Junk token accepted.** Every structural predicate tested except `let`, `set`,
`return`, `instantiates`, and `literalDigest`. That includes `invokes`, `arg`,
`in`, `out`, `catch`, `effect`, `uses`, `grants`, `do`, `branch`, `goto`,
`start`, `join`, `defer`, `entry`, `target`, `field`, and all `storage` facts.
The prose predicates (`purpose`, `invariant`) are the ones that enforce arity.
There is no per-predicate shape table: `ALLOWED_PREDICATES` holds names only.

**Rows that can be deleted** (single-valued facts, so deletion means an implicit
default or a missing check):

| Row | Accepted | Note |
| --- | --- | --- |
| `operation effect` | 12/12 | The effect declaration is not required (LR-07) |
| `operation memory` | 12/12 | Implicit default |
| `operation async` | 11/12 | Implicit default |
| `alias for` | 12/12 | An alias with no target type |
| `project entry`, `target`, `module`, `mode` | all | Implicit defaults |
| `module path` | 12/12 | Implicit default |
| `call in` | 6/12 | Owner inferred from use |
| `cleanup in` | 12/12 | Owner inferred from use |
| `storage mutability`, `storage value` | 12/12 | Implicit defaults (LR-08) |
| `operationType out` | 2/2 | Implicit `Void` |
| `call discards` | 1/12 | An unused result with no stated discard |

Repeatable rows (`enum variant`, `record field`) can also be deleted when the
member is unused. That is a valid program, not an implicit default. Metadata
rows (`purpose`, `invariant`, `risk`) are optional on most kinds; whether prose
is required at all is LR-06.

**Last token can be dropped** (the row keeps its meaning with less stated):

- Typed bindings without the type: `call out NAME`, `task out NAME`,
  `call catch NAME`, `operation in NAME`, `operation let NAME MUT TYPE` with no
  value.
- Bare predicates with no payload at all: `alias for`, `call in`, `cleanup in`,
  `cleanup cleans`, `call cleanedBy`, `call discards`, `module path`,
  `project entry`, `project target`, `project module`, `operation async`,
  `operation cancel`, `operation poll`, `storage mutability`, `storage value`,
  `operationType out`.
- Shortened facts: `operation effect write` (no resource), `operation memory
  heap` (no yes/no), `record field NAME` (no type), `enum variant` (no name).

**Duplicate rows accepted** (declarations only; repeating a step row is a
different program, not a duplicate):

- Single-valued: `call invokes`, `call in`, `task invokes`, `task in`,
  `cleanup in`, `operation body`, `call catch`, `project target`,
  `project mode`, `storage literalSource`.
- Same member twice: `call arg` and `task arg` (same parameter bound twice),
  `operation in`, `operation typeParam`, `operation effect`, `operation uses`,
  `capability grants`, `module exports`, `project module`, `call owns`.

### What already holds

- These rows are required today: `call invokes`, `call arg`, `call out`,
  `call catch`, `capability grants`, `module exports`, `operation in`,
  `operation out`, `operation uses`, `storage scope`, `storage type`,
  `task in`, `task invokes`, and the `purpose`/`invariant` pair on modules.
- Duplicates are already rejected for `let`, `out`, `async`, `memory`,
  `entry`, `alias for`, `storage scope/type/mutability/value`, and
  `record field`.

## Enforcement plan (draft)

Ordered so each step is small, testable, and does not depend on a later one.

1. **Predicate shape table.** Includes the LR-18 skeletons: required header
   predicates per kind, `none` for empty sets, `input`/`output` on operations,
   and a reserved-word list of literals only. One table keyed by (kind, predicate) giving the
   exact token count or range, a token class or closed value set per position,
   and cardinality (`one`, `optional`, `many`). The parser enforces it. This
   closes ADD and DROP in one place and replaces `ALLOWED_PREDICATES`. The same
   table generates `GRAMMAR.md` and the editor grammar.
2. **Cardinality and duplicates.** From the same table: single-valued facts
   appear exactly once; repeatable facts reject identical repeats and repeated
   keys (same `arg` parameter, same `in` name). Closes DUP.
3. **Required rows, no defaults.** Mark as required every row the DEL table
   lists: `effect` (when any activated target has effects, LR-07), `memory`,
   `async`, `alias for`, `project entry/target/module`, `module path`,
   `call in`, `cleanup in`, `storage mutability/value`, `operationType out`,
   and a `catch` or `discards` row on every fallible call. Closes DEL.
4. **Checked statements.** The lexical rules from LR-11 and the conversion and
   shift traps from LR-12 land here too. Restated facts are verified: `arg` type against the
   binding and the parameter (LR-05), `out`/`catch` types against the target's
   signature, `in` owner against the activating operation, `uses` against a
   declared capability (LR-07).
5. **Flow checks (LR-04, LR-16, LR-18, LR-22, LR-23).** Loops are declared
   with a kind and stated membership; each kind's shape is checked. Loop bounds and recursion
   depth are stated and enforced at run time; `useRetry` is removed. Every step row carries its block
   label; branches name both targets; loop bounds attach to blocks. Build a control-flow graph per operation and
   enforce definite assignment, a `return` on every path, and the return type
   against `out`. Run LLVM's verifier inside `check` as a backstop.
6. **Scoped names (LR-02).** Resolve call, task, cleanup, label, and binding
   names per operation.
7. **One spelling (LR-14, LR-15).** Ship the one-time migration command, then
   reject the compact profile and every sugar form.
8. **Memory and ownership (LR-20).** Region entities with stated lifetimes;
   `ownedBy` on every call; passing modes on every `input` and `arg`; the
   per-path linear check for operation-owned values; exact `memory heap`
   check; raw allocation rejected in application source. Port the standard
   library to region-taking operations.
9. **Context rows and comments (LR-06, LR-21).** Closed set of context
   predicates; typed-comment grammar removed; `fmt` keeps every comment
   attached to its row. Remove SS1880. Require `purpose` and `invariant` on
   product-meaning entities only. Add invariant ids and the rule that each is
   referenced by a test. Add the filler check and the staleness flag.
10. **Migrate the corpus.** Run the formatter or a one-time fixer to add the rows
    steps 3, 8, and 9 make mandatory, across `examples/`, `apps/`, and `std/`.
11. **Make the audit a gate.** Run `tests/audit/row_mutation_audit.py` in CI and
   fail on any accepted ADD, DROP, or DUP, and on any accepted DEL of a required
   row. Add strict-clean examples for the ten uncovered kinds so the gate sees
   them.

12. **Agent-writability evaluation (LR-18).** A small and a large model write a
    fixed set of programs from the spec alone. Track the first-try
    `check --strict` pass rate and which rules are broken, and feed the results
    back into this file.

No open question blocks step 1. Part 2 adds two steps, which come after the
enforcement steps because they build on the checked core:

13. **Language completion (LR-24 to LR-39).** Generics by instantiation,
    collections and `forEach`, tables, text and bytes, `unset` merge
    variables, `raises` and `return ok|error`, the four passing modes, the
    single import form, task groups and deadlines, tests.
14. **Standard library (LR-40).** Rewrite the library to the contract, then
    make `docs/refined-examples/` compile and run. Those two files are the
    acceptance test for this plan.

## Decision log

| Date | Item | Decision |
| --- | --- | --- |
| 2026-11-13 | P-1 | Source is verbose and 100% explicit; agents are the authors |
| 2026-11-13 | P-2 | Explicit construction is enforced: no defaults, fixed shapes, no silent duplicates, no unchecked statements |
| 2026-11-13 | LR-03 | Dropped; row count is not a problem under P-1 |
| 2026-11-13 | LR-05 | Keep the type on `arg` rows and check it |
| 2026-11-13 | LR-08 | `mutability` is required, closed set `mutable \| immutable`, no default |
| 2026-11-13 | LR-09 | Every predicate gets a fixed shape, enforced from one table |
| 2026-11-13 | LR-06 | `purpose` and `invariant` stay as rows on product-meaning entities; `purpose` is unchecked intent; each `invariant` has an id referenced by a test; staleness flag; no filler; SS1880 removed |
| 2026-11-13 | LR-01 | No inline call form; canonical order puts each call after its operation; `fmt --check` is in the strict gate (by delegation) |
| 2026-11-13 | LR-02 | Call, task, cleanup, label, and binding names are scoped to the owning operation (by delegation) |
| 2026-11-13 | LR-04 | Definite assignment and return-on-every-path are check errors; no loop sugar (by delegation) |
| 2026-11-13 | LR-07 | Targets state effects in signatures; effects are transitive and must be declared and covered; unresolved `uses` is always an error (by delegation) |
| 2026-11-13 | LR-11 | Whitespace is space and tab only; control bytes and misplaced quotes are errors (by delegation) |
| 2026-11-13 | LR-12 | Signed-to-unsigned of a negative value traps; out-of-range shift amounts trap (by delegation) |
| 2026-11-13 | LR-13 | Enforcement plan first, then §34 demotions minus the metadata step (by delegation) |
| 2026-11-13 | LR-14 | Compact profile removed (by delegation) |
| 2026-11-13 | LR-15 | All sugar forms become errors after a one-time migration (by delegation) |
| 2026-11-13 | LR-16 | Steps form an explicit control-flow graph: two-target branches, no fallthrough, bounded loops (by delegation) |
| 2026-11-13 | LR-17 | Owned tasks, cooperative single-thread scheduling, isolated workers for parallelism; task rows rejected until implemented (by delegation) |
| 2026-11-13 | LR-18 | Fixed skeletons with explicit `none`; every step row names its block; `input`/`output`; one boolean spelling; `ifFalse` removed; only literals reserved (by delegation) |
| 2026-11-13 | LR-19 | Each operation frees the ordinary values it made when it returns, unless it returned them; the region is a required row; raw malloc is standard-library only (accepted by owner) |
| 2026-11-13 | All | Owner accepted the refinement as a whole. Decisions marked "by delegation" stand as confirmed. LR-10 remains open |
| 2026-11-13 | LR-20 | Every releasable value has one named owner; regions are declared with a stated lifetime; allocation takes a region argument; every `input` and `arg` states its passing mode; operation-owned values are linear per path; supersedes LR-19 (accepted by owner) |
| 2026-11-13 | LR-21 | Comments stay as free space for authors, untagged, never checked, never moved by `fmt`. Structured context is rows: `purpose`, `invariant`, `rationale`, `risk <category>`, `note`, `todo`, `deprecated`. (Owner overturned the first version, which removed comments) |
| 2026-11-13 | LR-22 | Every loop block states a bound that is enforced at run time; `unbounded` needs a reason; `useRetry` removed in favor of written-out retry loops; recursive operations state `maxRecursion` (accepted by owner) |
| 2026-11-13 | LR-23 | A loop is declared on its header with a kind (`counted`, `while`, `doWhile`, `forEach`, `forever`); member blocks state `within`; single entry; the compiler checks each kind's shape and proves `counted` loops terminate (accepted by owner) |
| 2026-11-13 | LR-10 | Closed: loops are LR-16/22/23, generics LR-24, collections LR-25 (by delegation) |
| 2026-11-13 | LR-24 | Generics only through named instantiations with derived call targets; no inference (by delegation) |
| 2026-11-13 | LR-25 | Generic `List`, `Map`, `Set`, region-owned; fallible reads; `forEach` driven by `branch ifNext ... bind`; typed index aliases with `indexes` (by delegation) |
| 2026-11-13 | LR-26 | `table` entity for constant records, one `cell` fact per row (by delegation) |
| 2026-11-13 | LR-27 | `String`, `Bytes`, `ByteBuffer`; byte offsets; fallible `byteAt` and `slice`; no implicit conversion (by delegation) |
| 2026-11-13 | LR-28 | Immutable records and enums; class follows contents; `Option T` replaces `nil` (by delegation) |
| 2026-11-13 | LR-29 | `let <name> mutable <type> unset` for values set on several paths (by delegation) |
| 2026-11-13 | LR-30 | Errors are enums; every operation states `raises`; `return ok` / `return error`; no propagation shorthand (by delegation) |
| 2026-11-13 | LR-31 | Four passing modes; call skeleton gains `borrows`; `cleanedBy none`; `outputOwner`; built-in `static` region (by delegation) |
| 2026-11-13 | LR-32 | One file one module; one `imports` form; names always carry their module prefix; selective import predicates removed (by delegation) |
| 2026-11-13 | LR-33 | Waiting calls are tasks; every wait takes a `Deadline`; `taskGroup` for many tasks (by delegation) |
| 2026-11-13 | LR-34 | Arguments, streams, `process.run`; every capability states a `scope` (by delegation) |
| 2026-11-13 | LR-35 | Files and sockets as operation-owned resources; file writing and listening sockets added (by delegation) |
| 2026-11-13 | LR-36 | HTTP is a library; `webServer`, `htmlTemplate`, and indentation-based islands removed (by delegation) |
| 2026-11-13 | LR-37 | Operation references keep the full skeleton and declared effects; no closures (by delegation) |
| 2026-11-13 | LR-38 | No implicit numeric conversion; trapping arithmetic by default with named wrapping and saturating targets (by delegation) |
| 2026-11-13 | LR-39 | `test` entity with `verifies <operation> <invariantId>` (by delegation) |
| 2026-11-13 | LR-40 | Standard library contract and the module list the two targets need (by delegation) |
| 2026-11-13 | LR-41 | Known gaps recorded: float formatting, JSON, TLS, sorting and hashing, worker pools (by delegation) |
| 2026-11-13 | LR-42 | 26 amendments after an adversarial review, including: `arg none`; `maxIterations` counts returns to the header; imported types and variants are prefixed; `match`/`case` replaces `ifVariant`; every block declares `loopKind` and `within`; `memory stack`/`memory max` removed (reverses part of owner-accepted LR-20); literals only in `let` and `cell` rows (by delegation) |
| 2026-11-13 | Part 4 | Implementation started as a new front end beside the legacy compiler; decisions D-1 to D-15 recorded there (by delegation) |
| 2026-11-13 | Part 5 | No bridge and no backwards compatibility (owner); the refined compiler has its own LLVM backend; every Part 4 open item enforced; decisions D-16 to D-23 (by delegation) |
| 2026-11-13 | Part 6 | Earlier compiler, examples, runtime, vendored C, tests, docs, and CI lanes removed (owner); CI, editor, and docs point at the refined compiler |
| 2026-11-14 | Part 9 | Library, tooling, native output, FFI, and packages; decisions D-33 to D-36 (by delegation) |
| 2026-11-14 | Part 8 | Backend completed so every program compiles and runs; decisions D-27 to D-32 (by delegation; D-31 replaces D-27) |
| 2026-11-14 | Part 7 | Test suite and generated coverage map (owner); fixes for what it found; decisions D-24 to D-26 (by delegation) |
| 2026-11-14 | Part 10 | Adversarial refinement: loan, task, scope, and test holes closed; decisions D-38 to D-41 (by delegation) |
| 2026-11-14 | D-43 to D-47 | Exclusive handle loans, cancel-then-join, table loop bounds, no exported capabilities, a conformance suite; one consistent syntax pattern (owner) |
| 2026-11-14 | D-48 to D-56 | Group failure propagation, region trap rationale, task state on every path, release on trap, one writer per file, approved authority, exact suppression, recoverable allocation, run-time loop bounds |
| 2026-11-14 | D-100 to D-106 | Sound positions, trapping twins, stacks, module constants, table access, replace for nested values, linear checking |
| 2026-11-14 | D-107 to D-109 | Collections keep what they store alive; adversarial review: results, errors, generics, `set`, and resource fields stay in their regions; approval, test runner, cache, and file identity read the program as the compiler does |
| 2026-11-14 | D-110 to D-113 | From writing stage0: `string.contains`, `<table>.find`, helpers in test files; error propagation stays explicit |
| 2026-11-14 | D-119 | 1.0: the language compiles its own compiler to a fixed point |
| 2026-11-14 | D-114 to D-118 | stage0 compiles itself: projects of several modules, `string.Position` as a declared record, maps through the host, standard errors passed on, operation references and scoped host targets in C (by delegation) |
| 2026-11-14 | D-120 to D-124 | The runtime in SemanticScript, stage 1: the `use` effect for `machine.memory` and `system.calls`, the `machine` and `system` modules, `abi c` exports, executables linked with no C library (by delegation) |
| 2026-11-14 | D-126 to D-130 | The runtime in SemanticScript, stage 2: host dispatch by target number, Float64 bit conversions, the process heap, floating-point text as `refined run` writes it (C runtime fixed), host objects and R901 for host targets (by delegation) |
| 2026-11-14 | D-131 to D-137 | The runtime in SemanticScript, stages 3 and 4: `machine.taskEntry`, kernel32 rows for files, processes, time, and fibers, tasks on fibers with deadlock detection and cancellation, test callbacks, one-module executables, channels, secrets, crypto, foreign libraries (by delegation) |
| 2026-11-14 | D-138 to D-143 | The runtime in SemanticScript, stage 5: Linux through raw system calls (`LINUX_CALLS`, `system.linux`), the runtime's own stacks and heap on Linux, `ffi` refused there, the only runtime (macOS refused), stage0's C linking the runtime object, `native_runtime.c` deleted (by delegation) |
| 2026-11-15 | D-144 to D-152 | The runtime in SemanticScript, the rest of the library: "no C library" worded (OS interfaces ws2_32 and bcrypt allowed, never a CRT), the platform limits (ffi on Linux, macOS), `random` (CPython's Mersenne Twister, the system's secure source), `signal` (console control handler, rt_sigaction), `net` (non-blocking sockets through the scheduler, a resolver for Linux), `json` (CPython's scanner and encoder, shared counted values), `http`, AArch64 Linux (by delegation) |
| 2026-11-15 | D-153 to D-155 | The runtime in SemanticScript, `ffi` everywhere: a C library written in SemanticScript (ctype, string, stdlib, math basics, stdio writes, as glibc in the C locale) that `ffi.open("c")` binds on Windows and Linux, an ELF shared-library loader for Linux (eager binding, refusals that trap), `abi library` rows and `machine.cLibrary` (by delegation) |
| 2026-11-15 | D-156 to D-161 | The runtime in SemanticScript, the whole C library, stdio: expressions in the runtime's DSL, variadic `abi library` rows and `machine.variadicStart`, x86_64 calls through references made as variadic ones, printf's engine with exact digits, FILE streams buffered as glibc's, scanf (strerror's messages a known gap), the C library as a C program's libc on Linux (`--kind clibrary`) (by delegation) |
| 2026-11-15 | D-162 to D-164 | The runtime in SemanticScript, the whole C library: exit handlers and the div family, setjmp and longjmp as routines the compiler emits, signal, raise, abort, and system (by delegation) |
| 2026-11-15 | D-165 | The runtime in SemanticScript, the whole C library: the `__*_chk` names `_FORTIFY_SOURCE` makes compiled code call (by delegation) |
| 2026-11-15 | D-166 to D-167 | The runtime in SemanticScript, the whole C library: C11 threads on Linux's threads with futexes, a locked heap and locked streams, errno per thread; the floating-point control and fused multiply-add primitives (by delegation) |
| 2026-11-15 | D-168 to D-170 | The runtime in SemanticScript, the whole C library: threads.h on Windows (CreateThread, a thread-local slot), deadlines for timed waits, setjmp and longjmp on Windows (by delegation) |
| 2026-11-15 | D-171 | The runtime in SemanticScript, the whole C library: errno as glibc's numbers, Windows errors mapped by one table (by delegation) |
| 2026-11-15 | D-172 | The runtime in SemanticScript, the whole C library: strerror's messages taken from glibc by the compiler on a glibc machine (by delegation) |
| 2026-11-15 | D-173 | The runtime in SemanticScript, the whole C library: glibc's `__isoc23_` names with C23's binary numbers; `%5%` and scanf's `nan` as glibc (by delegation) |
| 2026-11-15 | D-174 | The runtime in SemanticScript, the whole C library: long double as each platform's C has it, its exact functions on parts, strtold and wcstold correctly rounded, scanf's `%Lf` (by delegation) |
| 2026-11-15 | D-175 | The runtime in SemanticScript, the whole C library: records of two numbers (complex numbers, ldiv_t) passed as the C ABI passes structs (by delegation) |
| 2026-11-15 | D-176 | The runtime in SemanticScript, the whole C library: wide stdio with streams' orientation, the wide printf and scanf families, wcsftime (by delegation) |
| 2026-11-15 | D-177 | The runtime in SemanticScript, the whole C library: the C locale converts ASCII only, as glibc's does (by delegation) |
| 2026-11-15 | D-178 | The runtime in SemanticScript, the whole C library: C23 scanf reads `nan(chars)`; release ordering for unlocks; nexttoward across formats; libgcc_s in the AArch64 JIT (by delegation) |
| 2026-11-15 | D-180 | The runtime in SemanticScript, the whole C library: math.h's hyperbolic, error, and gamma functions within 1 ulp, in double-double (by delegation) |
| 2026-11-15 | D-181 | The runtime in SemanticScript, the whole C library: math.h's trigonometric functions within 1 ulp, with Payne-Hanek reduction (by delegation) |
| 2026-11-15 | D-182 | The runtime in SemanticScript, the whole C library: math.h's exponential, logarithmic, and power functions within 1 ulp, table-free in double-double (by delegation) |
| 2026-11-15 | D-183 | The runtime in SemanticScript, the whole C library: the rest of string.h and stdlib.h (strtok, strtof correctly rounded, glibc's rand), locale.h, assert.h, inttypes.h (by delegation) |
| 2026-11-15 | D-184 | The runtime in SemanticScript, the whole C library: wchar.h, wctype.h, uchar.h, and the multibyte functions in the C locale, wchar_t 32 bits everywhere (by delegation) |
| 2026-11-15 | D-185 | The runtime in SemanticScript, the whole C library: math.h's exact operations bit for bit, and fenv.h on the processor's own state (by delegation) |
| 2026-11-15 | D-186 | The runtime in SemanticScript, the whole C library: time.h with the runtime's own reading of TZ, TZif files, and the Windows zone (by delegation) |
| 2026-11-15 | D-187 | The runtime in SemanticScript, the whole C library: complex.h with Annex G's special values, through the complex ABI (by delegation) |
| 2026-11-15 | D-188 | The runtime in SemanticScript, the whole C library: math.h's transcendental long double functions and fmal in 320-bit arithmetic, one code for x87, binary128, and double (by delegation) |
| 2026-11-15 | D-190 | The runtime in SemanticScript, the whole C library: strerror built on Windows gives ucrt's message for each error, matched by its symbolic name (by delegation) |
| 2026-11-15 | D-191 | The runtime in SemanticScript, the whole C library: threads.h on Windows blocks in kernel32's SRW locks and condition variables; `machine.testThreadEntry` for the runtime's thread tests (by delegation) |
| 2026-11-15 | D-192 | The runtime in SemanticScript, the whole C library: setjmp's and longjmp's Windows x64 routines written as machine code, so x86_64 executables built on ARM64 have them (by delegation) |
| 2026-11-15 | D-193, D-194 | The runtime in SemanticScript, Windows: complex.h's long double forms (Windows-only C library rows), aligned blocks that free and realloc give back (by delegation) |

| 2026-11-14 | D-70 to D-73 | Whole-character slices, `string.Position` and `advancePosition`, `byte.isPunctuation`, debugger shows records and enums; the lexer example (by delegation) |
| 2026-11-14 | D-90 to D-94 | Targets for every integer type, text and bytes without the host, instances `in` a generic operation, sets of text read in order, generic operation types (by delegation) |

| 2026-11-14 | D-80 to D-85 | Native host library in standalone executables (files, arguments, environment, standard input, processes, deadlines, buffers, maps, sets, log), `main(argc, argv)`, chunked native regions, JIT-identical traps (by delegation) |

## Parking lot

Ideas raised but not yet written up as items.

-
