# Agent DX Black-Box Trial

A reusable, self-contained evaluation that measures **how well an AI agent can
become productive in SemanticScript using only the toolchain's own onboarding**
(`agent-docs` / `skills`) and tools — no human spoon-feeding of syntax.

It is a *black box* in two senses:

1. The agent is opaque — it is scored **only on observable artifacts** (the
   `.sem` file it produces, the tool transcript, and the DEVLOG it writes),
   never on its hidden reasoning.
2. The toolchain interface is **left unspecified to the agent** on purpose. The
   ticket tells it *what* to build and *how it will be graded*, but not *which
   commands exist*. If the bootstrap surface is strong enough, the agent finds
   the workflow itself. Where it can't, the DEVLOG records exactly where it got
   stuck — which is the data we actually want.

The ticket enforces a **hard tool-only constraint**: the agent may learn the
language *only* through the SemanticScript toolchain — **no web search, no
reading the compiler source or the markdown docs, no grepping the repo, no
prior-knowledge shortcuts.** Existing programs may be inspected only through the
toolchain's own commands, never by opening the file. This is what makes it a true
test of the built-in onboarding/skills/search surface: if those aren't
self-sufficient, the agent has nowhere else to go, and the DEVLOG's "constraint
pressure" section captures every place that hurt.

## Why this design

- **The compiler is the grader.** Every acceptance criterion is a deterministic
  tool/grep check (see `GRADER.md`). No LLM judge — reproducible across model
  versions, so you can re-run the same ticket on each new model and diff the
  DEVLOGs.
- **It targets the value prop.** Declared effect + granting capability + a named
  typed error + an explicit failure branch is exactly what SemanticScript claims
  makes a program legible to an agent without running it. If the agent can't
  express that from the tools alone, that's the finding.
- **Timeboxed to 2h.** One small single-file program. Long enough to exercise
  onboarding + the `check → fix → patch → fmt` loop; short enough to run often.

## How to run the trial

1. Start a **fresh** agent session rooted in the SemanticScript repo (no prior
   context about the language — that is the point).
2. Paste the entire body of [`TICKET.md`](TICKET.md) as the task.
3. Let it work (timebox: 2 hours). It must produce `safe_divide.sem` and
   `DEVLOG.md`.
4. **Grade independently** with [`GRADER.md`](GRADER.md) — do not trust the
   agent's self-attestation; run the checks yourself.

## Files

| File | Purpose | Audience |
|---|---|---|
| `TICKET.md` | The Jira-style ticket + ground rules. Paste this to the agent. | the agent under test |
| `GRADER.md` | The objective pass/fail checks an evaluator runs afterward. | the human/evaluator |

## What to look at after a run

The pass/fail in `GRADER.md` is binary; the **DEVLOG is the real signal** —
calls-to-green, where the agent guessed wrong, which diagnostic actually
unblocked it, and the onboarding gaps. Keep each run's `DEVLOG.md` to compare
toolchain DX across models and over time.
