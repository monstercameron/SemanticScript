# EAV-Steps — governance, versioning, glossary

Contract version: **eav-0.3.1** (must equal `semanticscript.CONTRACT_VERSION`; the
`test_contract_version_lockstep` check fails if they drift — X-020).

> **eav-0.3.1** adds the §1J memory-safety model (WS1-110…122): the `region` and
> `sharedState` entity kinds; the `borrows`/`lifetime`/`mayEscape`,
> `consumes`/`takesOwnership`, `allocateIn`/`releaseRegion`,
> `readShared`/`setShared`, and `unsafe`/`wrapsAs`/`allocator` rows; and the
> SS1560–SS1571 + SS3083/SS3084 checks. Additive over eav-0.3 (no removals).

## Change protocol / docs lockstep (X-020)

A grammar change moves these together: `README.md` (§1–§34 spec), `GRAMMAR.md`
(EBNF), `semanticscript.py` (lexer/parser/validation/codegen), `test_semanticscript.py` (tests +
invalid corpus), and this file's contract version. The token-sync drift guard
(X-005, `token_sync_drift`) enforces §2↔§5↔§22 consistency automatically.

## Versioning & rollout (X-022)

- **Versioning:** `CONTRACT_VERSION` is bumped on any grammar/contract change.
- **Compatibility mode:** the current/compact verb-led surface remains
  acceptable at the source level; EAV is the canonical normalized form (§ adoption
  framing). The compact↔EAV round-trip is the gate-0 guarantee.
- **Deprecation policy:** deprecated constructs (e.g. `async` on a `call`) parse
  but warn, and `sem fmt` promotes them to the canonical form.
- **Milestones:** L1 core → L2 lint → L3 stdlib/build → L4 tooling → L5 migration
  (§31). v0.4 narrows the keyword surface to a minimal core (§34).

## Spec coherence (X-021)

- **Normative vs informative:** §1–§17 are normative grammar/semantics; §29
  (gaps), §31 (layering), §34 (direction) are informative/roadmap.
- **Single source of truth:** each topic has one home — grammar in §1–§5,
  diagnostics in the `DIAGNOSTICS` registry, ordering in §22, the roadmap in
  `ROADMAP.md`.

### Glossary

- **entity / fact / step / labeled-step** — the four row classes (§1).
- **predicate** — column-2 token; dispatched per entity kind (§5).
- **island** — an indented foreign body after `body <kind>` (§2).
- **the split** — `do`→call, `start/…`→task, `defer`→cleanup; cross-use is a
  hard error (§34.4, preserved verbatim).
- **effective effects** — an operation's own effects ∪ those of the calls/
  tasks/cleanups it (transitively) activates; must be covered by `uses` (§8).
- **gate-0** — the compact↔EAV (and EAV↔canonical-EAV) round-trip preserves
  semantics and the entity/row set (§21).

## §31 freeze vs §33/§34 reconciliation (X-024)

§31 freezes §§1–17 as the stable core. §33 (core gap resolutions) and §34
(minimal-core direction) are **post-freeze exceptions**: they refine semantics
and narrow the keyword surface *without* changing the §§1–17 row model, the
call/task/cleanup split, or the effect/capability boundary (§34.4/§34.1b, X-017).
So the freeze holds for the tape/control/type core; §33/§34 are additive
clarifications and a forward keyword-shrink, not breaking changes to the frozen
core.
