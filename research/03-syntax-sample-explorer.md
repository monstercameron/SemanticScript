# Experiment 3: Syntax Sample Explorer

Preservation note: this document is the durable extraction from the original
sample-generation and pairwise-judgment run. The generated samples, checkpoints,
rank CSVs, and proposal drafts are not required to understand or reuse the
finding.

## Research Intent

This experiment moved from abstract syntax families to concrete programs. It
generated hundreds of binsearch syntax samples and judged them pairwise across
dimensions that matter when agents read and modify code.

The completed budget run covered:

```text
programs:            binsearch
combo_count:         576
sample_total_target: 576
sample_total_done:   576
pair_total_done:     465
api_calls:           1331
generation_calls:    894
judge_calls:         437
error_count:         0
```

Judged dimensions:

- readability
- patchability
- context
- conciseness
- overall

This was the experiment that turned the research from tables into actual syntax
we could argue with.

## Decision-Grade Finding

The top-ranked judged sample was a plain verb-row language: declarations,
calls, control rows, and labels all used simple verb-slot rows, with no extra
context blocks.

Score: 36.5 wins; readability 9.0, patchability 5.5, context 4.0,
conciseness 9.0, overall 9.0.

Why it mattered: the strongest concrete sample looked like a cleaned-up
SemanticScript tape, not a totally new notation.

Rank 2 kept verb declarations and calls, but changed control into keyed rows and
added operation/branch context. It used symbol labels.

Score: 34.0 wins; readability 8.0, patchability 6.0, context 6.0,
conciseness 7.0, overall 7.0.

Why it mattered: keyed control improved context, but the symbol-label part was
not acceptable for the final language direction.

The most interesting agent-oriented sample was rank 5: verb declarations,
verb calls, keyed control rows, plain labels, and operation/branch context.

Score: 32.0 wins; readability 6.0, patchability 7.5, context 7.5,
conciseness 4.0, overall 7.0.

Why it mattered: rank 5 made the core tradeoff explicit. For agents, the best
sample may spend more syntax on branch and context clarity if that makes patches
safer.

Rank 5 mattered because it made the tradeoff explicit: spend more syntax on
branch and context clarity when that helps agents patch the program safely.

## Core Answer

The strongest concrete samples did not ask us to abandon SemanticScript. They
showed that SemanticScript's row tape was already close to a useful agent-native
surface, but needed cleaner semantic variants and cleaner control rows.

The important shift was:

```text
Keep the verb-led language. Replace collapsed or ambiguous rows with regular
variant rows.
```

## Changes Supported By This Experiment

The sample review directly influenced:

- `argument` instead of `arg`
- explicit call argument roles
- `bind value`, `bind ok`, and `bind error`
- `return value`, `return ok`, `return error`, and `return void`
- `branch if` and `branch error` as branch variants
- `branch else` as the explicit alternate branch target
- `jump` for unconditional transfer
- plain labels instead of sigil labels

Representative accepted shape:

```semanticscript
branch if condition isMatch target found
branch else target checkBelow
jump target searchLoop

return value mid
return ok okResponse
return error parseError
return void
```

## What We Rejected

Rejected sample traits:

```text
@label found
#label found
call.fn elementCall array.get
branch condition isMatch targetTrue found targetFalse checkBelow
argument call=elementCall name=index type=Int64 value=mid
set target high source newHigh
```

Reasons:

- Sigils and hash labels violate the no-symbol direction.
- Dotted fact names are not the canonical SemanticScript surface.
- `targetTrue` and `targetFalse` packed into one row make longer branch chains
  less pleasant than `branch if` followed by `branch else`.
- Equals-sign key/value rows were explicitly rejected.
- Some generated samples were useful as inspiration but contained model
  generation mistakes, such as generic `.fn` suffixes.

## Ranked Reference Results

Evidence snapshot: the values below were copied from the original full-space
budget summary before cleanup of the raw experiment data.

How to read the scores:

```text
wins          Pairwise judge wins across dimensions.
readability   Human/agent readability score contribution.
patchability  How easy the syntax looked to modify safely.
context       How much useful semantic context stayed near the code.
conciseness   How little syntax was needed.
overall       Aggregate subjective preference.
```

Top 10 judged samples in human terms:

1. Plain all-verb rows: verb declarations, verb calls, verb control, plain
   labels, no extra context blocks.
   Score: 36.5 wins; readability 9.0, patchability 5.5, context 4.0,
   conciseness 9.0, overall 9.0.
   Meaning: the clean SemanticScript-like row tape won the subjective round.

2. Verb declarations and calls, keyed control rows, symbol labels, operation and
   branch context.
   Score: 34.0 wins; readability 8.0, patchability 6.0, context 6.0,
   conciseness 7.0, overall 7.0.
   Meaning: keyed control improved context without destroying readability, but
   symbols were later rejected.

3. Verb declarations, calls, and control, symbol labels, operation and branch
   context.
   Score: 33.0 wins; readability 7.0, patchability 5.5, context 5.5,
   conciseness 8.0, overall 7.0.
   Meaning: verb-led control stayed strong even with extra context.

4. Fact-style declarations, verb calls, fact-style control, plain labels, no
   extra context blocks.
   Score: 32.0 wins; readability 8.0, patchability 6.0, context 4.0,
   conciseness 8.0, overall 6.0.
   Meaning: fact relations were readable, but did not beat the verb-led base.

5. Verb declarations and calls, keyed control rows, plain labels, operation and
   branch context.
   Score: 32.0 wins; readability 6.0, patchability 7.5, context 7.5,
   conciseness 4.0, overall 7.0.
   Meaning: this was the best agent-oriented sample: less concise, but much
   better for context and patching.

6. Verb declarations, fact-style calls, verb control, hash labels, operation
   context.
   Score: 31.5 wins; readability 9.0, patchability 4.5, context 3.0,
   conciseness 8.0, overall 7.0.
   Meaning: readable, but too weak on context and too dependent on hash labels.

7. Keyed declarations, verb calls, fact-style control, symbol labels, operation
   context.
   Score: 31.0 wins; readability 6.0, patchability 8.5, context 5.5,
   conciseness 5.0, overall 6.0.
   Meaning: strong patchability, but too far from the accepted row style.

8. Fact-style declarations and calls, verb control, plain labels, operation and
   branch context.
   Score: 30.0 wins; readability 7.5, patchability 5.5, context 2.5,
   conciseness 7.5, overall 7.0.
   Meaning: concise and readable, but context was too weak.

9. Fact-style declarations, verb calls, verb control, hash labels, operation and
   branch context.
   Score: 30.0 wins; readability 6.0, patchability 7.0, context 5.0,
   conciseness 6.0, overall 6.0.
   Meaning: mixed result; useful context, rejected marker style.

10. Fact-style declarations, verb calls, verb control, plain labels, operation
    and branch context.
    Score: 30.0 wins; readability 8.0, patchability 3.5, context 4.5,
    conciseness 7.0, overall 7.0.
    Meaning: readable, but patchability fell too far behind.

What this ranking proves:

- Verb-led rows were not just legacy preference; they won the concrete sample
  review.
- Keyed control was useful when it improved branch context.
- Plain labels were viable and cleaner than symbol/hash labels.
- The best agent-facing sample was not the shortest sample; context and
  patchability mattered more.

## Why It Made Us Smarter

This experiment forced the proposal to stay grounded in real programs. It gave
us examples that were good enough to steal from and flawed enough to sharpen the
rules. The result was not an invented replacement language. It was a disciplined
upgrade path for the language we already had.
