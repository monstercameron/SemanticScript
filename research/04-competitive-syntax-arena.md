# Experiment 4: Competitive Syntax Arena

Preservation note: this document is the durable extraction from the original
competitive syntax arena. The raw tournament files, gate outputs, manifests, and
agent leaderboard data are not required to understand or reuse the finding.

## Research Intent

This experiment treated syntax design as a competitive system rather than a
single proposal. The loop was:

```text
proposal -> adversarial critique -> refinement -> validation -> scoring
```

The goal was agent-native syntax, not human-aesthetic syntax. Candidates were
evaluated across the jobs agents actually perform:

- read code
- write code
- patch code
- search code
- preserve semantic round-trip behavior
- keep business and code context aligned
- avoid parser ambiguity
- avoid edit blast radius

The arena also introduced a hard compliance gate for the SemanticScript
constitution. That gate matters because a syntax can be low-PPL and still be a
bad language surface.

## Decision-Grade Finding

The arena established the most important distinction in the whole research set:

```text
The unconstrained PPL optimum is not the accepted language optimum.
The accepted language optimum is the best candidate inside the SemanticScript
constitution.
```

The compliance result was decisive:

- The eight measured-prior seeds from the earlier broad search round-tripped,
  but were 0/8 goal-compliant.
- They used non-English markers, anonymous `factN` subjects, indented blocks,
  or one-field-per-line structures.
- Among goal-compliant candidates, `verb_slot__semantic_lower` led the read,
  write, locality, and efficiency Pareto fronts.
- Inside the compliant set, `verb_slot__semantic_lower` had the lowest gold
  load-bearing PPL among compliant variants: 1.887.
- The patch metric quantified the cost of anonymous fact subjects: inserting
  one fact can renumber every downstream `factN`, producing roughly 200 lines of
  churn versus roughly 1 line under a verb-led tape.

## Core Answer

SemanticScript should optimize inside its own constitution:

```text
flat rows
one semantic record per line
lowercase English verbs
name-addressable subjects
no anonymous fact IDs
no marker-heavy canonical syntax
no hidden reconstruction step
```

This does not make the research conservative. It makes it credible. The arena
gave us a way to accept empirical signal without surrendering the structural
properties that make the language maintainable.

## Changes Supported By This Experiment

This experiment locked in these rules:

- keep verb-led row syntax as the base
- reject anonymous fact IDs
- reject sigils and marker-heavy canonical syntax
- reject indented object blocks as the program surface
- keep every row patchable as an independent semantic record
- make old replaced syntax invalid after migration
- make parser dispatch depend on full canonical row shape
- make the linter reject stale collapsed rows
- require branch targets to resolve to declared labels

It also raised patchability and greppability to first-class language goals,
which is exactly right for agent-maintained code.

## What We Did Not Take

Some arena candidates scored well on context or proxy PPL while carrying
rejected traits such as anonymous fact subjects, path-token relation syntax, or
object-like records. Those candidates were not failures. They were useful
negative controls: they showed what to mine for ideas and what to keep out of
the canonical surface.

The language outcome was therefore selective:

```text
Steal the semantic clarity. Reject the structural debt.
```

## Ranked Reference Results

Evidence snapshot: the values below were copied from the original arena analysis
and cross-modal ranking before cleanup of the raw experiment data.

The arena's strict compliant analysis has only six compliant variants, so this
section uses the broader cross-modal reference ranking for a 10-result view.

How to read the scores:

```text
read PPL       Lower is better. Model reading score.
patch radius   Lower is better. Estimated edit blast radius.
locality       Lower is better. How close references stay to definitions.
write tokens   Lower is better. Approximate cost to write the syntax.
greppability   Higher is better. How searchable the syntax is.
front          Whether the candidate is on a Pareto front.
```

Top 10 cross-modal candidates in human terms:

1. Verb rows with explicit token marker labels.
   Score: read PPL 1.8165, patch radius 1.0, locality 8.426, write tokens
   424.6, greppability 0.9709, Pareto front yes.
   Meaning: excellent model-facing score, but rejected as canonical because
   token markers are not the desired language surface.

2. Verb rows with symbol-prefixed labels.
   Score: read PPL 1.8390, patch radius 1.0, locality 8.426, write tokens
   264.4, greppability 0.9417, Pareto front yes.
   Meaning: strong and compact, but rejected because sigils are not allowed.

3. Verb rows with hash-prefixed labels.
   Score: read PPL 1.8473, patch radius 1.0, locality 8.426, write tokens
   264.4, greppability 0.9417, Pareto front no.
   Meaning: similar to rank 2, but not Pareto-front and still marker-based.

4. Plain lowercase SemanticScript-style verb rows.
   Score: read PPL 1.8869, patch radius 1.0, locality 8.426, write tokens
   211.0, greppability 0.9245, Pareto front yes.
   Meaning: this is the clean accepted candidate: no markers, lowest write cost
   in the top group, perfect patch radius, strong locality.

5. Key/value rows with symbol-prefixed labels.
   Score: read PPL 2.1645, patch radius 1.0, locality 8.532, write tokens
   676.0, greppability 0.9732, Pareto front yes.
   Meaning: searchable and patchable, but too verbose and symbol-dependent.

6. Key/value rows with hash-prefixed labels.
   Score: read PPL 2.2329, patch radius 1.0, locality 8.532, write tokens
   676.0, greppability 0.9732, Pareto front no.
   Meaning: did not beat the symbol-prefixed key/value form and still violates
   the no-marker direction.

7. Key/value rows with lowercase semantic labels.
   Score: read PPL 2.3258, patch radius 1.0, locality 8.532, write tokens
   485.4, greppability 0.9528, Pareto front no.
   Meaning: compliant-looking labels, but worse read PPL and higher write cost
   than plain verb rows.

8. Key/value rows with explicit token markers.
   Score: read PPL 2.4253, patch radius 1.0, locality 8.532, write tokens
   1247.8, greppability 0.9788, Pareto front yes.
   Meaning: very searchable, but far too expensive and marker-heavy.

9. YAML-like record blocks with lowercase semantic labels.
   Score: read PPL 1.5042, patch radius 6.0, locality 31.817, write tokens
   592.2, greppability 0.9528, Pareto front yes.
   Meaning: strong read PPL, but much worse locality and patch radius. Good
   evidence that read PPL alone is not enough.

10. YAML-like record blocks with symbol-prefixed labels.
    Score: read PPL 1.4859, patch radius 6.0, locality 31.817, write tokens
    782.8, greppability 0.9732, Pareto front yes.
    Meaning: the best read PPL in this list, but it is structurally wrong for
    SemanticScript: block-shaped, marker-based, and harder to patch.

What this ranking proves:

- Plain lowercase verb rows were the best accepted candidate, not the raw lowest
  read-PPL candidate.
- Marker variants can win narrow metrics, but violate the canonical surface.
- YAML-like blocks show why the arena needed multiple metrics: low read PPL can
  hide poor locality and patchability.
- The strict arena analysis narrowed the acceptable set to six compliant
  variants; inside that set, `verb_slot__semantic_lower` led the key lanes.

## Honest Caveat

The arena does not prove that `verb_slot__semantic_lower` is the universal
lowest-PPL syntax. It proves something more actionable for this language:

```text
Inside the SemanticScript constraints, it is the strongest measured base.
```

That is the right bar for implementation work. We are building SemanticScript,
not a disconnected notation benchmark.

## Why It Made Us Smarter

This experiment turned the project from syntax preference into language
governance. It gave us a constitution, tests, gates, and scoring lanes. It made
it possible to say no to impressive-looking results for principled reasons, and
yes to smaller changes that improve the actual language.

That is the mature posture: measure aggressively, but adopt selectively.
