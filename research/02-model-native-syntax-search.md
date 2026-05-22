# Experiment 2: Model-Native Syntax Search

Preservation note: this document is the durable extraction from the original
model-native syntax search. The raw score files, monitors, manifests, and
reports are not required to understand or reuse the finding.

## Research Intent

This experiment widened the aperture. Instead of asking whether one proposed
syntax was good, it rendered the same canonical program IR through many syntax
families and measured how models scored the load-bearing tokens.

That distinction is important. The experiment was not tied to LLVM, compiler
internals, or a favorite surface style. It treated syntax as a model-facing
serialization layer and asked:

```text
Which surface makes semantic reconstruction easiest for a model?
```

Families included path assignment, block objects, relation facts, keyed
S-expressions, verb slots, JSONL, key/value rows, Prolog-like facts, table rows,
and other renderings. Keyword styles included semantic words, symbols, hash
prefixes, path tokens, sentinels, opcodes, numeric forms, and marker styles.

## Decision-Grade Finding

The unconstrained lowest-PPL result was not SemanticScript-shaped.

In the replicated binsearch screen:

- `path_assign__hash_prefixed`: lb PPL 1.239.
- `path_assign__symbol_prefixed`: lb PPL 1.244.
- `fact_relation__semantic_lower`: lb PPL 1.254.
- `block_object` was the best family average at lb PPL 1.414.
- `verb_slot` was much lower in the unconstrained family ranking at lb PPL
  2.001.

In the smaller expanded family/keyword screen, the top individual rows again
favored non-SemanticScript shapes:

- `block_object__path_tokens`: lb PPL 1.016.
- `fact_relation__semantic_upper`: lb PPL 1.027.
- `fact_relation__symbol_prefixed`: lb PPL 1.028.
- `path_assign__semantic_lower`: lb PPL 1.029.

## Core Answer

Raw model preference is valuable, but it is not the same as language design.

The experiment made the tradeoff visible:

```text
Models often like marker-rich, path-like, object-like, or fact-like surfaces.
SemanticScript needs a surface that models can use and maintain safely.
```

That is a stronger position than simply accepting or rejecting the raw winner.
It means we can mine low-PPL designs for useful local patterns while preserving
the language properties that matter for a real toolchain.

## Transferable Lessons

The axis soft-concepts run produced the most portable guidance:

- Explicit or no-run call lifecycle beat fused call lifecycle.
- Branch edges scored better than split or single branch alternatives on
  average.
- Type locality helped enough to keep it in the design discussion.
- Lean and parent-echo redundancy were close, so redundancy should be used only
  when it buys clarity.
- Value-first ordering sometimes helped, but not enough to justify turning the
  whole language around.
- Symbol and hash markers often helped PPL, but conflicted with the accepted
  no-symbol direction.

## Changes Supported By This Experiment

This experiment supports:

- keeping call construction, argument binding, execution, result binding, and
  error handling as separate explicit facts
- making branch targets visible as semantic edges
- keeping type or role context near important values
- using regular row families instead of collapsed one-off verbs
- rejecting fused rows when they hide lifecycle or control-flow facts

## What We Rejected

We did not adopt:

```text
path_assign__hash_prefixed
path_assign__symbol_prefixed
anonymous fact subjects
marker-heavy labels
one-field-per-line object facts
equals-sign assignment surfaces
object blocks as the canonical program shape
```

Those forms are useful evidence, but not acceptable endpoints for the language.
They score well locally while making the language less flat, less patchable, and
less aligned with SemanticScript's row model.

## Ranked Reference Results

Evidence snapshot: the values below were copied from the original replicated
binsearch screen before cleanup of the raw experiment data.

How to read the scores:

```text
lb PPL    Lower is better. Local score on tokens the model must get right.
whole PPL Lower is better. Whole rendered program score.
tokens    Approximate rendered token count.
n         Independent replicated observations.
```

Top 10 unconstrained variants in human terms:

1. Path-assignment syntax with hash-prefixed role markers.
   Score: lb PPL 1.239, whole PPL 1.188, 2762.8 tokens, n=5.
   Meaning: the raw model liked path-like assignment plus strong marker tokens.
   Rejected as canonical because it relies on symbols and assignment shape.

2. Path-assignment syntax with symbol-prefixed role markers.
   Score: lb PPL 1.244, whole PPL 1.187, 2765.8 tokens, n=5.
   Meaning: nearly identical to rank 1. The model liked explicit markers, but
   the language direction rejected sigils.

3. Fact-relation syntax with lowercase semantic words.
   Score: lb PPL 1.254, whole PPL 1.313, 1931.4 tokens, n=5.
   Meaning: this was the strongest non-symbolic raw contender. It inspired more
   explicit role words, but not dotted fact rows or anonymous relation subjects.

4. Path-assignment syntax with uppercase semantic role words.
   Score: lb PPL 1.257, whole PPL 1.223, 2506.8 tokens, n=5.
   Meaning: semantic labels can compete with symbols, but path assignment still
   conflicts with the final no-`=` row model.

5. Block-object syntax with hash-prefixed role markers.
   Score: lb PPL 1.268, whole PPL 1.225, 2275.4 tokens, n=5.
   Meaning: grouped object-like facts scored well, but object blocks hurt flat
   row patchability.

6. Path-assignment syntax with sentinel labels.
   Score: lb PPL 1.279, whole PPL 1.200, 2846.8 tokens, n=5.
   Meaning: sentinels were model-friendly, but still marker-driven.

7. Block-object syntax with token marker labels.
   Score: lb PPL 1.282, whole PPL 1.183, 2783.4 tokens, n=5.
   Meaning: another strong object/marker result. Useful as evidence that
   explicit boundaries matter, not as a surface to adopt.

8. Path-assignment syntax with path-token labels.
   Score: lb PPL 1.285, whole PPL 1.228, 2538.8 tokens, n=5.
   Meaning: path-like labels helped the model, but would move SemanticScript
   toward a configuration-file shape.

9. Path-assignment syntax with lowercase semantic words.
   Score: lb PPL 1.287, whole PPL 1.250, 2303.8 tokens, n=5.
   Meaning: the best path-assignment result without symbols was still strong,
   but the assignment form itself was rejected.

10. Fact-relation syntax with symbol-prefixed role markers.
    Score: lb PPL 1.289, whole PPL 1.222, 2393.4 tokens, n=5.
    Meaning: relation facts plus symbols worked well locally, but violates the
    accepted no-symbol canonical syntax.

What this ranking proves:

- The raw model winner was not the same as the language-design winner.
- Six of the top 10 were path-assignment forms.
- Four of the top 10 depended on hash, symbol, or token markers.
- The useful transferable lesson was explicit local roles and boundaries, not
  the specific marker-heavy surface.

## Why It Made Us Smarter

This run gave us the discipline to separate measurement from adoption. It showed
that the model can prefer things we should still reject. That is exactly the
kind of result a serious language-design process needs: a way to learn from the
model without letting the model's local token preferences overwrite the system's
long-term architecture.
