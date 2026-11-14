# Experiment 1: Syntax LLM Eval

Preservation note: this document is the durable extraction from the original
feature-level syntax evaluation. The raw logs, CSVs, and reports are not required
to understand or reuse the finding.

## Research Intent

This experiment asked a precise question: which small syntax features help a
model recover the load-bearing facts of a program?

Instead of evaluating whether a syntax looked familiar, it tested whether the
model could predict or reconstruct the specific tokens that make the program
semantically correct: result types, branch targets, call arguments, bound values,
loop targets, and output types.

Axes included:

- type echo on or off
- inline state versus axis-style state
- baseline branch rows versus structured branch rows
- descriptive identifiers versus terse identifiers
- purpose and effect context lines
- comment lines
- `bind` versus `bindResult`

This gave us a feature-level map of where models benefit from explicit context
and where extra syntax is just noise.

## Decision-Grade Finding

The best attention/comprehension combination was:

```text
branch_form=baseline
effect_lines=False
ident_style=descriptive
purpose_lines=False
storage_form=inline
type_echo=True
```

Score:

```text
overall 0.979
full    0.958
snippet 1.000
```

The local 8B load-bearing PPL report refined the picture:

- Descriptive identifiers were strongly better in pooled results:
  `descriptive` lb PPL 1.218 versus `terse` 1.457.
- Baseline branch form beat the tested structured branch form:
  `baseline` 1.273 versus `structured` 1.394 pooled.
- Purpose lines helped in the full factorial:
  `purpose_lines=True` 1.320 versus `False` 1.344 pooled.
- `bind` versus `bindResult` was almost neutral, which suggested the real
  improvement should be variant clarity rather than a longer collapsed verb.
- Type echo was mixed in raw PPL, but helpful in the comprehension run.

## Core Answer

The model benefits when the syntax keeps type, role, and semantic variant
information near the fact that must be reconstructed.

The model is not helped by arbitrary terseness. Shorter rows can be worse if
they remove the very anchors the agent needs during generation or repair.

This matters because it gives SemanticScript a design principle:

```text
Spend tokens where they reduce semantic uncertainty.
Cut tokens where they only restate structure the parser already owns.
```

## Changes Supported By This Experiment

This experiment directly supports:

- explicit result variants in type rows
- `bind value`, `bind ok`, and `bind error`
- `return value`, `return ok`, `return error`, and `return void`
- descriptive identifiers over terse identifiers
- subject-qualified metadata rows
- keeping call-site argument rows explicit enough for local recovery
- avoiding compressed opcodes and clever fused rows

## Ranked Reference Results

Evidence snapshot: the values below were copied from the original local
load-bearing PPL report before cleanup of the raw experiment data.

How to read the scores:

```text
lb PPL    Lower is better. This is the load-bearing token score.
whole PPL Lower is better. This is the whole rendered program score.
n         Number of pooled program observations in this comparison.
```

Top 10 ranked findings in plain language:

1. Type-rich, descriptive, inline state, baseline branches, purpose context, no
   effect lines, no comments, `bindResult`.
   Score: lb PPL 1.062, whole PPL 1.723, n=2.
   Meaning: the best result kept the program readable and gave the model local
   type and purpose anchors without adding extra effect/comment noise.

2. Same as rank 1, but with effect lines and comments turned on.
   Score: lb PPL 1.063, whole PPL 1.778, n=2.
   Meaning: comments and effect lines did not destroy the score, but they added
   whole-program cost. This argues for structured semantic rows over prose.

3. Type-rich, descriptive, axis-style state, baseline branches, purpose context,
   effect lines, no comments, plain `bind`.
   Score: lb PPL 1.065, whole PPL 1.649, n=2.
   Meaning: the model could tolerate axis-style state, but this did not become
   the language direction because `memory` and `storage` are clearer.

4. Type-rich, descriptive, inline state, baseline branches, purpose context,
   effect lines, no comments, `bindResult`.
   Score: lb PPL 1.065, whole PPL 1.716, n=2.
   Meaning: effect context was useful when kept as structured rows near the code.

5. No type echo, descriptive, inline state, baseline branches, purpose context,
   no effect lines, no comments, `bindResult`.
   Score: lb PPL 1.071, whole PPL 1.897, n=2.
   Meaning: removing type echo still scored well, but whole-program prediction
   worsened. Type context remained worth keeping where it clarifies facts.

6. No type echo, descriptive, inline state, baseline branches, purpose context,
   effect lines, no comments, `bindResult`.
   Score: lb PPL 1.079, whole PPL 1.871, n=2.
   Meaning: effect rows helped recover some missing type context, but did not
   beat the type-rich top result.

7. No type echo, descriptive, inline state, baseline branches, purpose context,
   effect lines, no comments, plain `bind`.
   Score: lb PPL 1.080, whole PPL 1.887, n=2.
   Meaning: `bind` versus `bindResult` was not the real issue. The better fix
   was to make the result variant explicit: `bind value`, `bind ok`, `bind error`.

8. Type-rich, descriptive, axis-style state, baseline branches, purpose context,
   effect lines, no comments, `bindResult`.
   Score: lb PPL 1.084, whole PPL 1.640, n=2.
   Meaning: this had the best whole-program score in the top 10, reinforcing
   that global readability and local load-bearing recovery can disagree.

9. Type-rich, descriptive, inline state, baseline branches, purpose context,
   effect lines, comments, plain `bind`.
   Score: lb PPL 1.085, whole PPL 1.796, n=2.
   Meaning: comments were not necessary for a good score. The language should
   prefer typed semantic rows over prose explanation.

10. Type-rich, descriptive, inline state, baseline branches, purpose context,
    no effect lines, no comments, plain `bind`.
    Score: lb PPL 1.087, whole PPL 1.732, n=2.
    Meaning: the core winning pattern was stable across bind spelling: explicit
    types, descriptive names, simple branch rows, and local purpose context.

What this ranking proves:

- All top 10 results used descriptive identifiers.
- All top 10 results kept baseline-style branch locality.
- Nine of the top 10 used purpose context.
- Seven of the top 10 used type echo.
- The spelling of `bind` was much less important than making the bind variant
  semantically explicit.

## Nuance

The PPL run did not directly endorse every final syntax decision. For example,
the tested structured branch form underperformed the baseline branch form. The
final branch syntax came from combining this result with later sample review:
the language needed to separate conditional branch decisions from unconditional
loop jumps.

The final design keeps the experiment's lesson, but expresses it in a cleaner
SemanticScript row shape:

```text
branch if condition isMatch target found
branch else target checkBelow
jump target searchLoop
```

## Why It Made Us Smarter

This run prevented us from relying on taste. It showed that "clear to humans"
and "predictable to models" overlap, but are not the same thing. It also showed
that token reduction is not automatically better. The right goal is not minimum
syntax; it is maximum recoverable semantics per token.
