# GRADER — SSDX-001 (run by the evaluator, not the agent)

Objective, deterministic pass/fail for a completed trial. Run these **yourself**
after the agent finishes; do not trust its self-attestation. All commands are run
from the **repo root**. The CLI entry point is:

```
python semanticscript/compiler/semanticscript.py <args>
```

(or your `semanticscript` alias). Let `F = experiments/agent-dx-blackbox/safe_divide.sem`.

## Automated checks

| Check | Command | Pass condition | Maps to |
|---|---|---|---|
| G-1 Builds clean | `... check $F --json` | JSON `surface == sem.check.v1` and no error-tier diagnostics | AC-1 |
| G-2 Correct output | `... run $F` | stdout is exactly `42` + newline; exit code `0` | AC-2 |
| G-3 Effect declared | `... query effects $F --json` | result contains `write console.stdout` | AC-3 |
| G-4 Real divide call | `... graph $F --json` | a `math.divideInt64` (or documented integer-divide) call node is present | AC-4 |
| G-5 Format clean | `... fmt --check $F` | exit code `0` (no diff) | AC-6 |
| G-6 DEVLOG depth | — | `DEVLOG.md` has a §0 running command log (verbatim commands + outputs) **and** all 7 synthesis sections, written in real time, with `✅ WIN:`/`❌ PAIN:` tags. A thin or after-the-fact DEVLOG fails the trial regardless of G-1…G-5. | primary deliverable |

## Source-structure checks (grep the file)

These defend against a "passes-but-cheats" solution. Each must be present in `F`:

| Check | Look for | Maps to |
|---|---|---|
| S-1 Named error entity | a line matching `is error` (an error declaration) | AC-5 / FR-6 |
| S-2 Explicit guard branch | a `branch if` / `branch ifFalse` / `branch ifError` row | AC-5 / FR-5 |
| S-3 Labeled failure block | an `at <label>` row reached only on the zero path | AC-5 / FR-5 |
| S-4 Capability grant | a `grants write console.stdout` row **and** a `uses` row on the operation | AC-3 / FR-4 |
| S-5 Real divide, named operands | a `math.divideInt64` call whose `arg`s reference the `let`-bound `84` and `2`, not literal `42` | AC-4 / FR-2 |
| S-6 Non-zero failure return | the failure block returns a non-zero exit code; success path returns `0` | AC-5 / FR-5/7 |

## Negative / enforcement check (the important one)

Proves authority is enforced, not cosmetic (AC-3 / T-8):

1. Copy `F` to a temp file.
2. Delete the operation's `uses <capability>` row (or the capability's `grants`
   row).
3. Run `check` on the temp file. **It must now FAIL** with an effect/capability
   diagnostic.
4. Discard the temp file.

If `check` still passes with the grant removed, the declared authority was not
actually wired to the effect — **fail the trial on AC-3** regardless of the
happy-path output.

## Scoring

- **Pass:** G-1…G-6 all pass, S-1…S-6 all present, and the negative check fails
  as required.
- **Partial:** happy path works (G-1,G-2) but a structural/enforcement check
  fails — record which, and treat the gap as a DX finding (did the toolchain let
  the agent ship a weaker program than the ticket asked for?).
- **Fail:** does not build, wrong output, **or a thin/after-the-fact DEVLOG** —
  the DEVLOG is the primary artifact; a green program with a shallow log is a
  failed trial.

## What to harvest regardless of pass/fail

The DEVLOG is the deliverable that matters. After scoring, pull out:

- attempts-to-green per AC,
- which single tool/diagnostic unblocked the agent the most,
- the worst piece of friction (verbatim quote),
- the agent's one-line verdict.

Keep the run's `DEVLOG.md` (rename per model/date) to compare DX across models
and over time.
