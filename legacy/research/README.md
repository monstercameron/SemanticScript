# SemanticScript Syntax Research

This folder is the research brief behind the current SemanticScript syntax
cutover. It is designed to stand on its own after the original experiment data
is deleted. The important measurements, rankings, conclusions, and caveats have
been extracted here as durable notes.

The work was not a cosmetic syntax pass. It was a focused attempt to answer a
harder question:

```text
What should a programming language look like when the primary reader, writer,
debugger, and maintainer is an AI agent?
```

The answer we arrived at is deliberately pragmatic. We did not simply chase the
lowest perplexity number, and we did not blindly preserve the original language.
We used the experiments to separate signal from novelty, then folded the useful
signal back into a language that remains flat, explicit, searchable, patchable,
and compiler-friendly.

## Strategic Conclusion

The strongest result is that agent-native syntax needs two layers of judgment:

1. Measure what models actually prefer.
2. Filter those preferences through the language constitution.

Unconstrained model-native syntax often drifts toward path/object/fact notations
with markers, anonymous facts, and compact structural tricks. Those shapes can
score well locally, but they are poor fits for a long-lived programming language
that must be greppable, patchable, auditable, and predictable under migration.

The winning direction is therefore not:

```text
lowest PPL at any cost
```

It is:

```text
best measured agent behavior inside a disciplined SemanticScript surface
```

That is the core insight. SemanticScript becomes stronger by absorbing the
measured wins, while rejecting the shapes that would make the language harder to
own.

## Accepted Language Direction

The accepted syntax keeps SemanticScript's verb-led row tape and adopts the
research-backed improvements that make the rows more explicit and easier for
agents to edit safely.

Accepted changes:

- Use `type NAME result ok OK_TYPE error ERROR_TYPE`.
- Replace `importModule` with `import`.
- Use subject-qualified metadata: `purpose module ...`,
  `purpose operation ...`, `invariant module ...`, `invariant operation ...`.
- Use subject-qualified signatures: `input operation ...`,
  `output operation ...`.
- Remove `var`, `let`, and `const` from the surface language.
- Use `storage` for module/shared state and constants.
- Use `memory` for operation-local state and heap policy.
- Align authority with effects: `authority OPERATION ACTION PATH`.
- Use `set memory ...` and `set storage ...`.
- Use `bind value ...`, `bind ok ...`, and `bind error ...`.
- Replace `arg` with `argument`.
- Keep call-site argument rows explicit enough for type and role recovery.
- Use `branch if`, `branch error`, and `branch else` for branch chains.
- Use `jump` only for unconditional control transfer.
- Use one `return` verb with variants: `return value`, `return ok`,
  `return error`, `return void`.
- Use one `ignore` verb with matching variants.
- Reject `=`, sigils, dotted fact names, anonymous fact IDs, and object-like
  fact blocks in the canonical surface.

This gives us a language that is still recognizably SemanticScript, but with a
cleaner control model, cleaner result model, cleaner state model, and a more
consistent row grammar.

## Four Research Threads

1. [Syntax LLM Eval](01-syntax-llm-eval.md)
   - Tested feature-level comprehension and load-bearing perplexity.
   - Core answer: explicit local context, descriptive names, and variant words
     help agents recover the facts that matter.

2. [Model-Native Syntax Search](02-model-native-syntax-search.md)
   - Ran broad local-GPU screens across syntax families and keyword styles.
   - Core answer: raw PPL finds useful local patterns, but the raw winners are
     not automatically acceptable language designs.

3. [Syntax Sample Explorer](03-syntax-sample-explorer.md)
   - Generated hundreds of concrete syntax samples and judged them pairwise.
   - Core answer: verb-led rows remained highly competitive, and the best
     samples exposed cleaner branch, argument, bind, and return shapes.

4. [Competitive Syntax Arena](04-competitive-syntax-arena.md)
   - Put candidates through compliance, locality, patch, search, and modality
     metrics.
   - Core answer: within the SemanticScript constitution,
     `verb_slot__semantic_lower` is the right base. The language should steal
     ideas from other forms, not become them.

## Preservation Note

The original experiment workspace included generated samples, logs, pairwise
judgment data, score CSVs, checkpoint JSON, and proposal drafts. Those raw files
are intentionally not required by this research folder. The four experiment
notes preserve the decision-grade results in human-readable form:

- the question each experiment answered
- the ranked findings that mattered
- what we accepted into the language
- what we rejected and why
- the caveats needed to keep the claims honest

The synthesis work that translated these findings into parser/compiler/linter
changes is summarized here rather than linked to a disposable folder.

## Why This Matters

Most programming languages were designed around human notation and later adapted
to tooling. This research takes the opposite path: start from the operations AI
agents actually perform, measure where models lose semantic certainty, and then
design the surface so the language is easier to read, write, patch, search, and
compile under that workload.

The result is not novelty for its own sake. It is a more serious foundation for
agent-maintained software:

- stable rows instead of decorative syntax
- explicit semantic variants instead of overloaded verbs
- branch chains that expose intent
- state declarations that map directly to memory and storage
- migration rules that remove old ambiguity instead of preserving it forever

Future syntax experiments should use this folder as the decision filter. A new
idea is valuable when it improves agent behavior and fits the disciplined
SemanticScript row model. If it only wins by adding markers, anonymous facts,
hidden reconstruction, or one-off parser magic, it is evidence, not a proposal.
