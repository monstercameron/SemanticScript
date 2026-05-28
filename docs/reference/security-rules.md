# SemanticScript Security Rules

This is the single registry of the toolchain's security rules: what each catches,
which CWE it maps to, and on which enforcement layer it fires. Run
`sem explain <CODE>` for the per-rule summary + fixes; this page is the
rule × layer × CWE matrix.

## The three enforcement layers

1. **Always-on security floor** (`validate_security_floor` in `semsc.py`) — runs
   on **every** build regardless of `--strict`/`--quiet`/`languageMode`. Reserved
   for patterns with **no legitimate use in any context** (pure UB, or no
   legitimate *production* use with a narrow `*.test.sem` exemption). These are
   genuinely un-compilable.
2. **Strict wall** (`validate_strict_executable`) — fatal only under
   `languageMode strictExecutable` / `--strict`. The broader executable contract.
3. **Default-build advisory** (`collect_security_advisories`) — non-blocking
   `warning` printed on a default (non-strict) build unless `--quiet`. Carries an
   `agent_hint` + `fix`. Surfaces the dual-use security rules to agents who never
   opt into `--strict`.
4. **semlint floor** (`sem lint` / `sem check`) — structured `Diagnostic`s; the
   editor/CI lint surface. Mirrors the compiler rules (a parity test guards
   drift; single-file, so it conservatively under-reports cross-module cases the
   import-flattening compiler catches).

## Rule × layer × CWE matrix

| Code | Rule | CWE | Always-on floor | Strict wall | Default advisory | semlint floor |
|------|------|-----|:---------------:|:-----------:|:----------------:|:-------------:|
| SS4308 | divide / modulo by constant 0 | CWE-369 | ✅ block (every build) | ✅ | — | ✅ |
| SS4309 | shift count outside [0,63] | CWE-682 | ✅ block (every build) | ✅ | — | ✅ |
| SS4602 | weak / missing bcrypt cost | CWE-916 | ✅ block (non-`*.test.sem`) | ✅ | ✅ | ✅ |
| SS4601 | non-cryptographic PRNG | CWE-338 | — | ✅ | ✅ | ✅ |
| SS4603 | non-constant `c.system` command | CWE-78 | — | ✅ | ✅ | ✅ |
| SS4604 | hard-coded secret (`typeTrust secret`) | CWE-798 | — | ✅ | ✅ | ✅ |
| SS3911 | non-constant SQL text | CWE-89 | — | ✅ | ✅ | (adjacent SS3628) |
| SS3310 | non-constant format string | CWE-134 | — | ✅ | ✅ | ✅ |

Legend: ✅ = enforced on that layer; — = not on that layer (by design).

## Design principles

- **Always-on vs strict-only** is decided by *legitimacy*, not severity. A rule
  joins the always-on floor only when the pattern it catches has **no legitimate
  use**: pure UB (SS4308/4309), or no legitimate *production* use with a clean
  test exemption (SS4602). Dual-use patterns — a runtime command from trusted
  config (SS4603), a non-CSPRNG for non-security sampling (SS4601), a demo
  fallback secret (SS4604) — stay strict + advisory, because an always-on block
  has no escape hatch and would refuse to compile legitimate programs.
- **The default build surfaces, the strict build blocks.** An interactive
  `sem build` (no `--quiet`) prints the dual-use advisories with hint+fix; a
  project hardens to fatal with `languageMode strictExecutable`.
- **Provable-constant only, where it blocks.** The floor/strict checks fire only
  on operands they can *prove* bad (a literal, an immutable constant, a
  never-written mutable, a resolved const chain) — never on a runtime/guarded
  value. This is the zero-false-positive contract.
- **No weak primitive ⇒ no rule.** Several classic causes are N/A here because
  the language exposes no unsafe primitive to flag: weak hashes / `alg:none`
  (G1), TLS-verify-disable (G6), `eval` (D4), and any LLM/prompt surface
  (Group P). These are prevented by *language design*, not a checker.

See `research/06-vulnerability-root-causes.md` (the ~110-cause taxonomy) and
`research/07-cause-enforcement-map.md` (the full cause→enforcement map + the
iteration-by-iteration build log) for the complete picture.
