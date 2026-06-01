# SSDX-001 · Safe Integer Division — agent DX trial

| Field | Value |
|---|---|
| **Type** | Task (spike) |
| **Priority** | High |
| **Estimate** | 2h (hard timebox) |
| **Components** | language-onboarding, toolchain, codegen |
| **Labels** | `agent-dx` `blackbox` `eval` `tool-only` |
| **Assignee** | the AI agent under test |
| **Reporter** | DX team |
| **Status** | Ready |

---

## ⛔ BOOTSTRAP — read this first, it governs everything below

You are being dropped into an unfamiliar programming language called
**SemanticScript**. This is a controlled experiment measuring whether its
**built-in toolchain alone** is enough for an AI agent to become productive. The
experiment is only valid if you obey the constraints below to the letter. If you
break a rule, the run is void — so don't.

### The single source of knowledge: the toolchain

The repo ships a `semanticscript` command-line tool **and** a
`semanticscript mcp` stdio JSON-RPC server. **Everything you need to learn the
language, inspect programs, validate your work, and repair errors must come from
that toolchain.** It is self-describing: it has commands for its own help, for
agent onboarding rules, for skills, for searching its docs, for explaining
diagnostics, for inspecting any program, and for checking/running/formatting
code. Your first job is to *discover those commands by asking the tool itself.*

### Hard constraints (violating any one voids the run)

1. **Tool-only.** The ONLY way you may obtain information about SemanticScript is
   by invoking the `semanticscript` CLI or its MCP tools. Nothing else.
2. **No web.** Do **not** search the internet, fetch URLs, or use any web/search
   tool. Assume you are offline.
3. **No reading the implementation or docs files.** Do **not** open, read, cat,
   or grep the compiler source (e.g. `semanticscript/compiler/*.py`), the
   markdown docs (`docs/*.md`, `README.md`, `CHANGELOG.md`), or any other repo
   file to learn the language. You may not `Read`/`Grep`/`find` your way around
   the repo for knowledge.
4. **Inspect programs only through the tool.** If you want to study an existing
   program (e.g. something under `examples/`), you must do it through the
   toolchain's own inspection commands (the ones that take a file path and emit
   docs / a symbol graph / a description / a trace), **never** by opening the
   file directly.
5. **No prior knowledge.** If you already recall SemanticScript syntax, you may
   not rely on it. Re-derive every fact from the tools, and note in the DEVLOG
   any place where your memory and the tool disagreed.

### What you ARE allowed to do

- Run any `semanticscript` CLI subcommand and any MCP tool, as many times as you
  like.
- **Write** your two deliverable files (`safe_divide.sem`, `DEVLOG.md`) and read
  back **your own** `safe_divide.sem` while iterating on it.
- Use the toolchain's scaffold/new/template, search, explain, docs, describe,
  trace, check, fix, patch, run, query, graph, and fmt capabilities — whatever
  you can find via the tool's own help and onboarding.

> If you are ever tempted to "just check the docs" or "look at how an example is
> written" — stop. Route that question through a toolchain command instead, and
> write down in the DEVLOG how well the tool answered it. That friction *is* the
> measurement.

---

## Summary

Author one correct SemanticScript program, `safe_divide.sem`, that divides two
integers, prints the quotient, and models division-by-zero as an **explicit,
named failure path** in the source. Learn the language and workflow entirely from
the toolchain, prove every acceptance criterion with a tool command, and keep an
engineering DEVLOG of the experience. The DEVLOG is a graded deliverable.

## Background / context

SemanticScript is a row-based language: every line is
`<subject> <predicate> <payload>` — no expressions, braces, or hidden control
flow. Its thesis is that an operation's whole contract — its inputs, outputs,
side effects, the authority (capability) it holds, and how it can fail — is
written as explicit, checkable rows, so a program is legible to an agent without
running it. This ticket measures whether an agent can actually exploit that from
the tools alone.

## User story

> **As** an AI coding agent new to SemanticScript,
> **I want** to write a small, fully-validated program using only the language's
> own toolchain,
> **so that** the team can judge whether the toolchain's onboarding, search,
> diagnostics, and fix-loop are strong enough to make an agent productive without
> external help.

---

## Reference behavior (the program's contract)

| Aspect | Required behavior |
|---|---|
| Target | console program, single entry operation |
| Dividend | a named, immutable value binding equal to `84` |
| Divisor | a named value binding equal to `2` |
| Computation | quotient produced by a **real integer-divide call** over those two bindings |
| Success output | prints exactly `42` and a trailing newline to stdout, nothing else |
| Success exit code | `0` |
| Failure mode | if the divisor is zero, take a distinct labeled failure path that does **not** divide and returns a **non-zero** exit code |
| Authority | the stdout write is a declared effect, granted by a capability the operation `uses`; the grant is exactly that effect, nothing broader |
| Error vocabulary | a named `error` entity for the divide-by-zero condition, referenced by the failure path |

For this input (`84 / 2`) the **success path is the one taken**; the failure path
must still be present, well-formed, and reachable in principle (the guard is real,
not dead syntax).

---

## Functional requirements

- **FR-1 — Project shape.** A console-target program with exactly one entry
  operation. No `build.sem`, no multi-file project.
- **FR-2 — Named operands.** `84` (dividend) and `2` (divisor) are declared as
  named value bindings inside the operation. The quotient must be computed from
  them — a hardcoded `42` anywhere is an automatic fail.
- **FR-3 — Real division.** The quotient comes from the language's integer-divide
  primitive, invoked as a first-class call with the two bindings as its
  arguments and its result bound to a name that is then printed.
- **FR-4 — Single clean line of output.** On success, print the integer quotient
  and only that, followed by a newline. No banners, labels, or extra lines.
- **FR-5 — Declared, granted effect.** The operation declares the stdout-write
  effect and `uses` a capability that `grants` exactly `write console.stdout`.
  Removing either the declaration or the grant must make the program fail to
  check (you will prove this in T-8).
- **FR-6 — Explicit zero-divisor guard.** Before the division, the program tests
  whether the divisor is zero and branches to a separate, labeled block. The
  divide must be unreachable when the divisor is zero. (Find out from the
  toolchain how integer divide-by-zero behaves at runtime, and follow the repair
  guidance it gives for that diagnostic.)
- **FR-7 — Named error entity.** A dedicated `error` entity represents the
  divide-by-zero condition and is referenced on the failure path.
- **FR-8 — Exit codes.** Success path returns `0`; the divide-by-zero failure
  path returns a non-zero code.

## Design constraints

- One flat tape of `subject predicate payload` rows; no hidden control flow.
- No external libraries, no network, no runtime seams (sqlite/http/json/...).
- The only files that may exist or change as a result of this ticket are
  `experiments/agent-dx-blackbox/safe_divide.sem` and `.../DEVLOG.md`.

## Edge cases to handle / consider (note your reasoning in the DEVLOG)

- **EC-1** The compiler may constant-fold a literal divisor and complain that the
  guard branch is dead, or it may demand a mutable/opaque binding. Decide how to
  keep the guard genuine and record what the tool told you.
- **EC-2** The integer-divide primitive's exact name, argument slot names, and
  output binding form are things you must confirm via the tool, not guess.
- **EC-3** `INT_MIN / -1` and divide-by-zero may share one runtime trap. Note
  whether the toolchain distinguishes them.
- **EC-4** Printing an integer vs. a string: confirm which primitive prints a
  bare integer line so output is exactly `42`.

---

## Acceptance criteria

Each is `Given/When/Then` and must be **proven by a tool command** whose output
you paste into the DEVLOG. Self-attestation does not count.

- [ ] **AC-1 — Builds clean.** *Given* `safe_divide.sem`, *when* you run the
      toolchain's parse+lint check, *then* it reports **zero errors and zero
      warnings**. Paste the check output.
- [ ] **AC-2 — Correct output & exit.** *Given* the program, *when* you run it,
      *then* stdout is exactly `42\n` and the process exit code is `0`. Paste the
      run output.
- [ ] **AC-3 — Effect declared.** *Given* the program, *when* you query its
      effects with the toolchain, *then* the result includes `write
      console.stdout`. Paste the query result.
- [ ] **AC-4 — Authority granted & minimal.** *Given* the program, *when* you
      inspect its capabilities/authority via the toolchain, *then* a capability
      grants exactly `write console.stdout` and the operation `uses` it; the
      grant is not broader than the declared effect. Paste the evidence.
- [ ] **AC-5 — Real computation.** *Given* the source, the quotient is produced
      by a real integer-divide call over the `84`/`2` bindings. Demonstrate via
      the toolchain's call graph (or a before/after experiment) that the printed
      value comes from that call and not a constant. Paste the graph slice.
- [ ] **AC-6 — Explicit, named failure path.** *Given* the source, there is a
      declared `error` entity for divide-by-zero, an explicit zero-divisor guard,
      and a distinct labeled block that returns non-zero without dividing. Show
      the rows and cite the toolchain's runtime divide-by-zero diagnostic
      (its code + repair text) to justify the guard.
- [ ] **AC-7 — Canonical format.** *Given* the file, *when* you run the
      toolchain's format check, *then* it passes with no diff. Paste the result.

## Test plan

Use whatever invocation the toolchain documents. Run every row; record command +
relevant output in the DEVLOG.

| # | Action (via the toolchain) | Expected result | AC |
|---|---|---|---|
| T-1 | Parse+lint check on the file | Clean: 0 errors, 0 warnings | AC-1 |
| T-2 | Run the program | stdout `42\n`; exit code `0` | AC-2 |
| T-3 | Query the program's **effects** | Includes `write console.stdout` | AC-3 |
| T-4 | Inspect **capabilities / authority** | A capability grants exactly `write console.stdout`; operation `uses` it | AC-4 |
| T-5 | Inspect the **call graph** | A real integer-divide call node feeds the printed value | AC-5 |
| T-6 | Explain the **runtime divide-by-zero diagnostic** | You can name the code + repair, and your guard matches it | AC-6 |
| T-7 | **Format** check | No reformatting needed | AC-7 |
| T-8 | **Negative check:** copy the file, delete the `uses` row *or* the `grants` row, check the copy | The check now **FAILS** with an effect/capability diagnostic — authority is enforced, not cosmetic. Delete the copy, keep the original. | AC-3/AC-4 |

---

## Deliverable: `DEVLOG.md` — THE primary artifact (graded hardest)

**The working program is table stakes; the DEVLOG is the actual deliverable.**
We are studying the toolchain's developer experience through your eyes, so we
need an aggressive, unfiltered, blow-by-blow record of what it was *actually*
like to use these tools. A green checkmark with a thin DEVLOG is a **failed**
trial. A rich DEVLOG with an honest partial result is a **successful** one.

### How to write it — non-negotiable rules

- **Document in real time, not at the end.** Open `DEVLOG.md` as your very first
  action and append to it continuously as you work. Do not reconstruct it from
  memory afterward — that loses exactly the friction we want.
- **Keep a running, timestamped command log.** For *every* tool invocation,
  record: the exact command, what you *expected*, what you *got* (paste the real
  output — verbatim, including errors and stack traces), and your one-line
  reaction. Yes, every single one. The log will be long; that is correct.
- **Quote, never paraphrase.** Diagnostics, error text, fix plans, search hits,
  help output — paste them verbatim. If you summarize, you have destroyed the
  evidence.
- **Be brutally honest and specific.** No diplomacy, no marketing, no "it was a
  bit tricky." Say *what* was confusing, *why*, what you assumed, how you were
  wrong, and how many tries it took. Name names: which command, which message,
  which missing piece.
- **Count everything.** Attempts-to-green per acceptance criterion, number of
  fix→check cycles, number of times you guessed a row's shape wrong, number of
  dead ends. Numbers make DX comparable across model runs.
- **Log the misses too.** Every command that returned something useless,
  misleading, empty, or wrong. Every tool you *expected* to exist and went
  looking for and couldn't find. Every moment you wanted to break a constraint.
- **Mark wins and pains inline as you go** with `✅ WIN:` and `❌ PAIN:` tags so
  they can be grepped out later. Don't save them all for the summary.

### Required structure

Start with a continuously-updated **§0 Running command log** (the timestamped
blow-by-blow above). Then, the synthesis sections — written *from* that log:

1. **Onboarding** — Your exact first command and why. Could you learn the
   language *and* the edit workflow from the toolchain alone? Where precisely was
   it ambiguous, missing, or wrong? Wall-clock time to your first compiling row.
2. **The good** — Tools/diagnostics that genuinely helped, each with the verbatim
   output that unblocked you and what it saved you.
3. **The bad / friction** — Every stuck point, wrong guess, and confusing or
   misleading message, quoted verbatim, with attempts-to-green per AC.
4. **The fix loop** — Did diagnose → repair-plan → apply → format actually get
   you to green? Did the fix plan apply cleanly or did you hand-edit? How many
   cycles?
5. **Tool routing** — A table: every distinct tool/command × what it was good for
   × would you reach for it again. Plus tools you expected but couldn't find, and
   tools that returned something useless.
6. **Constraint pressure** — Every moment the "tool-only / no web / no source
   reading" rule actually hurt, and whether the toolchain covered for it. **This
   is the core finding** — give it real depth.
7. **Verdict (3–5 sentences)** — Would an AI agent be productive here on tools
   alone? The single biggest DX **win** and the single biggest DX **gap**.

> Rule of thumb: if a reader of your DEVLOG cannot reconstruct your entire
> session — every command, every error, every decision — without watching you
> work, the DEVLOG is not detailed enough. Err on the side of *too much*.

## Suggested time budget (timebox 2h — fill the time with rigor, not filler)

- ~25 min: onboarding via the tool (help, agent rules, skills, search).
- ~35 min: first compiling version (operands + divide + print + capability).
- ~30 min: the guard, the named error, the failure path; reach a clean check.
- ~20 min: run all of T-1…T-8, including the negative check.
- ~10 min: finalize the DEVLOG sections and the proof block.

---

## Definition of Ready (already met)

- Goal, scope, reference behavior, ACs, and test plan are specified above.
- The environment has a working `semanticscript` toolchain.

## Definition of Done

- [ ] `safe_divide.sem` and `DEVLOG.md` exist in `experiments/agent-dx-blackbox/`,
      and nothing else in the repo was created or modified.
- [ ] AC-1 … AC-7 each proven with a pasted tool command + output in the DEVLOG.
- [ ] T-1 … T-8 executed and recorded, including the T-8 negative check (reverted).
- [ ] DEVLOG was written **in real time** and contains the §0 running command log
      (every invocation: command, expected, verbatim output, reaction) plus all
      seven synthesis sections, with verbatim quotes and `✅ WIN:` / `❌ PAIN:`
      tags throughout. A thin DEVLOG fails the trial even if the program is green.
- [ ] You confirm, in one line, that you used **only** the toolchain — no web, no
      reading the compiler source or docs files, no prior-knowledge shortcuts.
- [ ] End your turn by printing the per-AC proof block and pointing to
      `DEVLOG.md`. Do **not** restate the DEVLOG in chat — it lives in the file.

## Risks & assumptions

- **Assumption:** the toolchain's onboarding/skills/search are self-sufficient.
  If they are not, that is a finding, not a reason to break a constraint —
  document the gap and continue with best effort.
- **Risk:** masked success (a program that prints `42` but doesn't really divide,
  or whose authority isn't enforced). The negative check (T-8) and the call-graph
  check (AC-5) exist to catch exactly that — do not skip them.
