# EAV-Steps — roadmap register (§29 gaps #14–#25)

Each gap is **spec → stub → defer**: the direction is recorded here and a stub
exists where one is cheap, but the full build is deferred past L1–L4. The test
`test_roadmap_registers_all_gaps` asserts every gap below has an entry.

## #14 — Runtime value semantics (X-030)
Status: deferred. Direction: ordinary values are compiler-managed (no user
free/GC) — backend mechanism is region/arena/refcount, TBD. Stub: the source
contract is fixed (§10.6, WS1-096); `memory heap no` already satisfiable.

## #15 — Agent edit loop + diagnostic source-mapping (X-031)
Status: deferred. Direction: lint on canonical EAV maps back to the author's
compact/current span. Stub: diagnostics carry a line + code (`Diagnostic`),
which is the anchor a source-map would extend (WS2-004).

## #16 — Human-authoring validation session (X-032)
Status: deferred. Direction: measure learnability/reviewability/compact
ergonomics with real authors. Stub: scaffold/fmt/describe lower authoring cost.

## #17 — Existing-corpus migration (X-033)
Status: deferred. Direction: codemod the stdlib + apps; prove coexistence.
Stub: `rename`/`add`/`fmt` are the codemod primitives; `normalize --preview`
measures row delta.

## #18 — Runtime observability/debugging (X-034)
Status: deferred. Direction: traces/panics under `goto`, logging, source maps.
Stub: `trace` simulates a path; the div-by-zero trap is a real fault path.

## #19 — Security threat model (X-035)
Status: deferred. Direction: assets/adversaries (authority, trust, supply chain)
distinct from #10 enforcement. Stub: supply-chain allowlist + sha256 integrity
already enforce part of the model (WS3-034/036).

## #20 — Strategic success criteria (X-036)
Status: deferred. Direction: vs current syntax, vs competitors, multi-surface
cost. Stub: the conformance matrix + adoption-gate row-count are the metrics.

## #21 — Performance/profiling (X-037)
Status: deferred. Direction: codegen quality + profiling hooks.

## #22 — Text/i18n (X-037)
Status: deferred. Direction: `\u{…}` escapes + Unicode-aware string ops (today
strings are bytewise UTF-8; `\u{}` is reserved-rejected).

## #23 — Publishing/distribution workflow (X-037)
Status: deferred. Direction: `sem mod` publish/vendor + registry.

## #24 — Macros/reflection (X-037)
Status: deferred. Direction: compile-time metaprogramming surface, if any.

## #25 — Deployment/runtime config (X-037)
Status: deferred. Direction: runtime configuration + deployment targets.
