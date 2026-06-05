# Human-Authoring Validation Protocol

R-068 / gap #16 requires evidence from real authors, not only tool availability.
This protocol defines the session to run, the measurements to collect, and the
pass/fail threshold for compact versus canonical authoring.

## Status

Protocol ready; participant session pending.

No human-authoring session has been recorded in this repository yet. Do not mark
R-068 complete until at least one completed session report is appended under
`## Session Reports`.

## Participant Profile

Run at least one session with each profile before treating the result as a
release gate:

- Maintainer: has read or edited SemanticScript before.
- Application engineer: can read backend code but has not authored
  SemanticScript.
- Reviewer: reviews changes for correctness/security but does not implement the
  feature.

The minimum R-068 unblock is one non-maintainer session. The broader adoption
gate needs all three profiles.

## Materials

Use a real app or handler already in the corpus:

- Primary app: `apps/taskforge-web`.
- Fallback handler: `examples/http-runtime-gauntlet`.
- Tools allowed: `check --json`, `fmt`, `describe`, `search`, `slice`, `fix
  --plan`, VS Code extension features, and the README/spec.
- Tools disallowed for the timed score: direct compiler source edits, hidden
  maintainer hints, or generated patches not visible to the participant.

## Tasks

Each participant performs the same four tasks in order:

- Learnability: identify the entry operation, one route handler, and the
  capability that authorizes an outbound or storage effect.
- Reviewability: review a prepared one-route change and state whether effects,
  cleanup, and fallible operations are complete.
- Edit task: add or modify a small route/operation behavior, run `check`, and
  fix the first diagnostic without maintainer intervention.
- Compact ergonomics: compare the compact/current surface with canonical rows
  for the same handler and choose which surface they would author and which they
  would review.

## Metrics

Record all metrics in minutes/counts:

- Time to first correct mental model: participant can explain project entry,
  operation body, calls, and result binding.
- Time to successful edit: change parses and `check` reaches no error
  diagnostics.
- Diagnostic recovery count: number of diagnostics encountered before success.
- Tool hops: number of distinct commands or editor actions used.
- Maintainer interventions: count and reason.
- Review misses: count of intentionally seeded issues not noticed.
- Compact preference: authoring surface chosen, review surface chosen, and why.
- Confidence: participant self-rating from 1 to 5 for editing and review.

## Friction Taxonomy

Classify every observed issue under one primary category:

- Vocabulary: reserved words, predicate names, canonical ordering, or target
  naming were hard to discover.
- Shape: participant understood intent but not the row pattern or argument
  ordering.
- Tooling: `describe`, `search`, editor, `check`, `fix`, or `fmt` did not guide
  the next action.
- Diagnostics: message was missing, misleading, or not actionable.
- Review load: rows were too verbose, diff too noisy, or effect/failure/cleanup
  evidence too scattered.
- Runtime model: participant confused static check, run, test, authority, or
  cleanup behavior.
- Compact mismatch: compact and canonical surfaces disagreed or round-tripping
  obscured intent.

## Decision Thresholds

R-068 passes the minimum unblock only when one non-maintainer session satisfies
all of these:

- Time to first correct mental model is 20 minutes or less.
- Time to successful edit is 45 minutes or less.
- Maintainer interventions are 2 or fewer, and none are needed to explain a
  compiler crash or missing tool surface.
- Review misses are 1 or fewer for seeded effect/failure/cleanup issues.
- Participant confidence is at least 3 for editing and at least 3 for review.
- Every high-friction item is either fixed immediately or logged as a concrete
  follow-up todo with a testable acceptance criterion.

The broader adoption gate passes only when all three participant profiles pass
the same thresholds and at least two of three prefer compact/current for
authoring while still accepting canonical rows for review or generated diffs.

## Session Report Template

Append completed sessions here using this shape:

```text
### YYYY-MM-DD / participant profile

App/handler:
Facilitator:
Participant background:

Task results:
- Learnability:
- Reviewability:
- Edit task:
- Compact ergonomics:

Metrics:
- Time to first correct mental model:
- Time to successful edit:
- Diagnostic recovery count:
- Tool hops:
- Maintainer interventions:
- Review misses:
- Compact authoring preference:
- Compact review preference:
- Confidence editing:
- Confidence review:

Friction log:
- [category] observation -> follow-up/todo:

Decision:
- pass/fail:
- rationale:
```

## Session Reports

No completed human-authoring session recorded yet.
