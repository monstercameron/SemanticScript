# EAV-Steps — Implementation TODO (every change + every test)

Granular implementation plan for the EAV-Steps SemanticScript spec (`README.md`,
§§1–34). Built in **3 coverage iterations** across **4 parallel workstreams** so the
whole surface area is accounted for. Workstreams are *tracks a team can run
simultaneously*, not subagents.

> Scope rule (project invariant): **no item is "done" without a test that would fail
> under a no-op lowering** (a test that still passes when the feature is stubbed is
> not a test). Every change row below names its test(s).

## Status — keystone landed

The keystone vertical slice (WS1-100/101) is built and tested. EAV-Steps source
is lowered by a **second front end** (`eavc.py`) that normalizes canonical EAV
into the existing v0.1 verb-led SemanticScript text, which
`SemanticScript/compiler/semsc.py` already compiles and runs — no backend AST
fork.

- **Front end:** `experiments/eav-syntax/eavc.py` — lexer (§2), parser (§1/§5),
  lowering (§18), CLI (`lex`/`parse`/`lower`/`run`).
- **Tests:** `experiments/eav-syntax/test_eavc.py` — incl. the
  no-op-lowering-fails guard. Run:
  `python -m pytest experiments/eav-syntax/test_eavc.py -q`.
- **Executable goldens:** `examples/hello_world.sem` (§18) and
  `examples/add_two.sem` run end to end
  (`python eavc.py run examples/hello_world.sem` → `hello world`, exit 0).
- **Scope of the slice:** the `console` target runs end to end; the parser
  accepts the full four-row-class grammar and every §5 entity kind (the
  66-entity webServer CRUD demo `main.sem` parses cleanly). webServer/wasm/
  sqlite/http lowering and the WS2/WS3/WS4 workstreams remain open.

Checked items below cite the proving test in `test_eavc.py`.

## How to read this

- IDs: `WSn-NNN`. Check `- [ ]` → `- [x]` as landed.
- `→test:` names the proving test(s); `§` cites the spec; `dep:` names blockers.
- **Tiers** map to §31 layers and §29 waves: **L1** core executable, **L2** safety/
  lint, **L3** stdlib/runtime/build, **L4** tooling/editor, **L5** migration/rollout.
- The keystone is **WS1 lowering** (§29 #3): until EAV → existing `semsc.py` AST is
  pinned, everything else is unanchored. Build the Hello-World vertical slice first.

## Workstream map & dependencies

| WS | Owns | Hard deps |
|----|------|-----------|
| **WS1 — Front end & semantics** | lexer, parser, AST, type/scope/effect model, value model, control flow, **lowering** | — (foundational) |
| **WS2 — Linter & diagnostics** | §17 invariants, MD rules, diagnostic-code registry, repair suggestions, fmt-determinism checks | WS1 parser+AST |
| **WS3 — Stdlib, runtime & build** | `standard.*` (.semsig + impl), capability/effect runtime, cleanup/async lowering, build.sem/lock + MVS, FFI | WS1 lowering, WS2 effect lints |
| **WS4 — Tooling, formatter & editor** | `sem fmt`, slice/explain/query/doctor/add/pack/verify-patch/…, conformance matrix, LSP, docs | WS1 AST, WS2 codes |
| **Cross-cutting** | conformance test matrix, minimal-core migration (§34), docs/change-protocol, drift guards | all |

**Critical path:** WS1-(lexer→parser→AST→types→lowering Hello World) → WS2 core lints
→ WS3 console/sqlite/http stdlib → WS4 fmt + slice/doctor → conformance matrix → §34 migration.

---

# WS1 — Front end & core semantics  (L1, then L2 semantics)

## 1A. Lexer (§2, §33.1–33.2)
- [x] WS1-001 Tokenizer: whitespace-split, trim, ignore blank lines. →test: row tokenization goldens. §2 _(eavc: `test_tokenize_basic_row`, `test_tokenize_string_keeps_spaces_and_quotes`)_
- [ ] WS1-002 Identifiers `[a-zA-Z][a-zA-Z0-9]*`; reject `_`/`-`/leading-digit in names. →test: invalid-name corpus rejects. §2
- [ ] WS1-003 Integer literals: decimal, `0x`, `0b`, `_` separator; reject octal/`0`-prefix; leading/trailing/doubled `_` error. →test: each base parses; bad-separator rejects. §2/§33.1
- [ ] WS1-004 Float `[0-9]+\.[0-9]+`; no leading/trailing dot. →test: `1.5` ok, `.5`/`5.` reject. §2
- [ ] WS1-005 Negative literals `-N`/`-N.N`, no space after `-`; only in let-init/arg. →test: `-42` ok, `- 42` reject. §2
- [x] WS1-006 String literals + escapes `\" \\ \n \t \xNN`; reject `\r \0`; `\u{}` reserved-deferred error. →test: escape table; banned escapes reject. §2/§33.1 _(eavc: `test_tokenize_supported_escapes`, `test_tokenize_hex_escape_ok`, `test_tokenize_banned_escapes_reject`, `test_tokenize_unicode_escape_deferred`)_
- [ ] WS1-007 Duration literals `<int>{ns,us,ms,s,m,h}` (reserved class; no v0.3 use). →test: lexes, flagged unused. §2/§30.1.2
- [ ] WS1-008 Repo-path / semver `v…` / `sha256 <64hex>` tokens — manifest positions only. →test: accepted in build.sem, rejected as names. §2/§28
- [x] WS1-009 Comments: `#` full-line + trailing; typed-comment tags (`# rationale:` …); `#` literal inside strings. →test: trailing-comment preserved; `#`-in-string not a comment. §2 _(eavc: `test_tokenize_full_line_comment_is_empty`, `test_tokenize_trailing_comment_stripped`, `test_tokenize_hash_inside_string_is_literal`; typed-comment classification treated as plain comments for now)_
- [ ] WS1-010 Punctuation gate: allow `"… # . / - _ +` (per position); **reject `=`** with "let is positional" hint; `->` unused. →test: `let x T = v` errors. §2/§12
- [ ] WS1-011 Source format: UTF-8 no BOM; CRLF→LF normalize. →test: CRLF file lexes identically. §33.2
- [x] WS1-012 Island indentation: spaces-only (tab = hard error), common-prefix strip, dedent at column-1 token row, mixed = error. →test: tab-indent island rejects; dedent boundary golden. §16/§33.2 _(eavc: `test_parse_island_body_strips_common_indent`, `test_parse_tab_indent_island_rejected`; mixed-indent error not yet tested)_

## 1B. Parser & row model (§1, §5)
- [ ] WS1-020 Four row classes: entity/fact/step/labeled-step; column-1 subject, column-2 predicate. →test: each class parses to correct node. §1
- [ ] WS1-021 Every entity's first row is `is <kind>`; missing/duplicate `is` errors. →test: §17 #1. §1
- [ ] WS1-022 Per-kind predicate dispatch from §5 table; unknown predicate for kind = hard parse error. →test: each kind's legal set; one illegal each. §5
- [ ] WS1-023 Reserved-word table (§2) enforced for entity/var/type names; **exempt** arg-slot/field/variant labels. →test: `arg path …` ok, `path is record` errors. §2
- [ ] WS1-024 `at LABEL <stepPred> …` labeled-step (one model, §1 row-class 4); label col 3, step col 4+. →test: labeled step parses; `at` not usable as bare predicate. §1/§13
- [ ] WS1-025 `async`-on-`call` tolerated-deprecated exception (promotes to task on fmt). →test: `call … async yes` parses with deprecation note. §5
- [ ] WS1-026 EBNF grammar doc + invalid-example corpus (§29 #1). →test: corpus all-reject. §29#1

## 1C. Types (§10, §33.6–33.7)
- [ ] WS1-030 Primitives Int8–64/UInt8–64/Float32/64/Bool/String/Void/Byte (Byte alias UInt8). →test: lowering widths. §10
- [ ] WS1-031 `alias … for T` newtype, no silent coercion. →test: pass base where alias required = type error. §10
- [ ] WS1-032 `record` + `field`; duplicate field = error; doc-order = field order. →test: dup-field reject. §10
- [ ] WS1-033 `enum` + `variant [payload]` + `repr`; all-or-none repr; repr only on payloadless; dup variant = error. →test: mixed-repr reject; data-variant repr reject. §10
- [ ] WS1-034 `error`/`errorCase`/`of`/`payload` (full profile; enum-equivalent). →test: case enumeration. §9
- [ ] WS1-035 `Result OK ERR` (only generic). →test: arity. §10
- [ ] WS1-036 `operationType` (`is in out`) function-pointer type. →test: §5 row; indirect-call type-check. §33.9
- [ ] WS1-037 Literal width: literal takes annotated-position type, compile-time range-check; un-annotated = Int64. →test: `let s HttpStatusCode 200` ok, `… 99999` (out of Int32) error. §33.6
- [ ] WS1-038 Type resolution for imported types by bare name; ambiguous-bare = error; alias `for importAlias.Type` disambiguates. →test: two imports same type → error → alias fixes. §7
- [ ] WS1-039 Record fieldwise equality; ordering on records invalid; layout compiler-chosen. →test: record `equals` deep; `greaterThan` reject. §33.7

## 1D. Operation / call / task / cleanup model (§11, §15, §15.5, §15.6, §34.4)
- [ ] WS1-040 Operation decl rows `in/out/effect/uses/memory/async/label/let/body`; order-independent except `in` order. →test: reorder-stable parse. §11
- [ ] WS1-041 `body steps|runtimeBinding <t>|intrinsic <n>`; non-step body has no steps. →test: runtimeBinding op has no step rows. §11
- [ ] WS1-042 Return arity from `out` (void/single/Result one-nil-slot). →test: §17 #10; both-nil + both-value reject. §13
- [ ] WS1-043 `call` structure (invokes/arg/out/catch/owns/cleanedBy/effect/discards). →test: infallible vs fallible parse. §15
- [ ] WS1-044 **Split**: `do`→call, `start/join/poll/cancel/detach`→task, `defer`→cleanup; cross-use = hard error (§34.4, non-negotiable). →test: `do <task>` reject; `start <call>` reject; `defer <call>` reject. §13/§34.4
- [ ] WS1-045 Task entity (async counterpart) + lifecycle state machine (RUNNING/COMPLETED/CONSUMED/CANCELED/…); illegal transitions reject. →test: lifecycle table goldens; `ifError` before `join` reject. §13/§15.5
- [ ] WS1-046 Cleanup entity (`call/cleans/onFailure/because`); `cleans`↔`owns` cross-check; exactly one `cleans`+`call`; `onFailure` iff worker `catch`; worker not also `do`-activated. →test: §17 #41–#44. §15.6
- [ ] WS1-047 `cleanedBy` on producer points to cleanup ENTITY; ownership triangle. →test: dangling cleanedBy reject. §15
- [ ] WS1-048 `discards "reason"` required for dropped non-void non-catch result. →test: §17 #25. §15

## 1E. Invocation & dataflow (§3, §15, §10.5)
- [ ] WS1-050 `invokes` resolution order: bare in-module op / alias.op / compiler-derived target / intrinsic. →test: each form resolves; unresolved bare = error. §15/§3
- [ ] WS1-051 Arg-slot↔`in`-name match + type; `out`/`catch` ← op `out`/Result. →test: arg-name mismatch reject; Result→out+catch binding. §15
- [ ] WS1-052 Namespace collision rules (alias≠type name; bare op≠reserved/built-in ns; field≠`new`). →test: §17 #51. §15
- [ ] WS1-053 Construction targets `<Record>.new` / `<Enum>.<variant>` / `<Error>.<case>`; arg/field/case match. →test: §17 #49; missing field reject. §10.5
- [ ] WS1-054 Access target `<Record>.<field>` read. →test: field read binds field type. §10.5
- [ ] WS1-055 Built-in derived targets need no import (like compare/console/math). →test: `Task.new` without import ok. §10.5
- [ ] WS1-056 Operation references: `operationType` binding invoked indirectly via `invokes <binding>`; binding-vs-op name rule. →test: indirect call type-checked; shadow warns. §33.9

## 1F. Control flow & guards (§13, §33.4)
- [ ] WS1-060 `do/branch/goto/return/at`. →test: CFG goldens. §13
- [ ] WS1-061 Guard `if`/`ifFalse` (Bool in scope). →test: §17 #8. §13
- [ ] WS1-062 `ifError CALL` (after `do`) / `ifError TASK` (after `join`); needs `catch`; `poll` not a predecessor. →test: §17 #6; ifError w/o catch reject. §13
- [ ] WS1-063 `ifVariant VALUE VARIANT [bind PAYLOAD] goto`; payload catch-style scope; exhaustiveness; canonical default `goto`. →test: §17 #52/#53; non-exhaustive warns; bind-off-path reject. §13/§10.5
- [ ] WS1-064 Payload definite-assignment across shared labels (every predecessor binds same name/type). →test: mixed-predecessor bind reject. §13
- [ ] WS1-065 Async guards `ifReady/ifPending/ifCanceled` (after poll/join+cancel). →test: §17 #22; ifCanceled w/o cancel+join reject. §13
- [ ] WS1-066 Non-canonical sugar lowering: `ifOut`/`ifValue` → comparison call + `branch if`; `branch else` → `goto`; deterministic generated names + reuse + collision suffix. →test: fmt(sugar) golden; fmt idempotent. §13
- [ ] WS1-067 Comparator-lowering table → `compare.<cmp><Type>`; Bool/enum equals/notEquals only. →test: §17 #45; `greaterThan Bool` reject. §13
- [ ] WS1-068 Compound conditions = sequential guards (no and/or). →test: A∧B / A∨B goldens. §33.4
- [ ] WS1-069 Label lint: every goto/branch target has one `at`; unique; referenced; dead-label warn. →test: §17 #11/#12/#13. §13
- [ ] WS1-070 Recursion permitted (direct/mutual); unbounded → trap; `memory stack` bound. →test: recursion lowers; deep-recursion traps. §33.3

## 1G. State, storage, locals (§12)
- [ ] WS1-080 `let NAME mutable|immutable TYPE [VALUE]` positional; forward-ref rule. →test: forward-ref reject; mutable/immutable. §12
- [ ] WS1-081 `out`-rebind of `let mutable`; rebind immutable = error; module-storage mutation via out + effect+capability. →test: §17 #28/#29; immutable rebind reject. §12
- [ ] WS1-082 Module `storage` entity (scope/type/mutability/value/body); module-global read scope. →test: cross-op read; §25 scope. §12/§25
- [ ] WS1-083 Module-storage initializers **effect-free** (literal/constant/prior-storage); effectful → reject. →test: effectful init reject. §30.2.1
- [ ] WS1-084 Storage `literalSource`/`literalDigest` compile-time asset embedding. →test: asset bytes embedded, digest checked. §30.3.2

## 1H. Value & runtime semantics (§10.6, §33.5)
- [ ] WS1-090 Integer overflow wraps two's-complement; checked `math.*` → Result. →test: wrap golden; checked overflow → err. §10.6
- [ ] WS1-091 Int/mod div-by-zero traps. →test: traps, no UB. §10.6
- [ ] WS1-092 IEEE-754 floats (NaN≠NaN, ±inf). →test: `NaN notEquals NaN` true. §10.6
- [ ] WS1-093 String equality bytewise UTF-8 (no normalization). →test: byte-equal vs canon-equal distinguished. §10.6
- [ ] WS1-094 Eval order: args in document order; effects at activation step. →test: ordered-effect golden. §10.6
- [ ] WS1-095 Numeric conversions explicit; float→int trunc/trap, narrowing trap, int→float round-even; Wrapping/Saturating variants. →test: each conversion + trap. §33.5
- [ ] WS1-096 Value lifetime: ordinary values compiler-managed (no free/GC pause); `memory heap no` satisfiable for pure-data ops. →test: record-building op compiles under `heap no`. §10.6

## 1I. **Lowering (KEYSTONE — §29 #3)**
- [x] WS1-100 Decide & document: EAV → existing `semsc.py` AST (shared AST vs pre-parser-normalizer vs second front-end). →test: design doc + ADR. §29#3 _(ADR: **second front end** lowering EAV→v0.1 text; documented in `eavc.py` module docstring.)_
- [x] WS1-101 Vertical slice: parse→lower→run **Hello World (§18)** end to end. →test: program prints + exit code; no-op lowering fails. §18 _(eavc: `test_e2e_hello_world_runs`, `test_noop_lowering_would_fail`)_
- [ ] WS1-102 Lower entity/fact/step rows → AST nodes. →test: AST snapshot per row class.
- [ ] WS1-103 Lower types/records/enums/Result/operationType → backend types. →test: width/discriminant goldens.
- [ ] WS1-104 Lower control flow (goto/branch/if/return/labels) → CFG. →test: irreducible-flow warn; CFG golden.
- [ ] WS1-105 Lower calls/args/out/catch → call sites + error slots. →test: fallible call lowering.
- [ ] WS1-106 Lower defer/cleanup (reverse-order, before each return; trap-during-cleanup fatal). →test: defer order; §33.8 abort.
- [ ] WS1-107 Lower async lifecycle on single-thread backend (start eager, poll always-ready, ifPending never). →test: §13 backend-semantics goldens.
- [ ] WS1-108 Lower construction/access/compare derived targets. →test: `Task.new` round-trips.
- [ ] WS1-109 Module init order (imports first, doc order); cyclic-init reject; failing-init traps. →test: §30.2.1 order golden.

---

# WS2 — Linter & diagnostics  (L2)

## 2A. Diagnostic infrastructure (§17, §29 #12)
- [ ] WS2-001 **Diagnostic-code registry** (code→meaning→tier→repair), single source of truth; `sem explain <CODE>`. →test: every emitted code in registry; registry round-trip. §29#12
- [ ] WS2-002 Repair-suggestion format ("Found / Suggested fix") engine. →test: golden repair output for SS1305/1502/1610. §17
- [ ] WS2-003 Tier model T0/T1 correctness, T3 design, T4 style; severity mapping. →test: tier per code.
- [ ] WS2-004 Diagnostic source-mapping: lint on canonical EAV maps back to author's compact/current span (§29 #15). →test: compact-source diagnostic points to compact line.
- [ ] WS2-005 Error recovery: report multiple errors, not bail-on-first. →test: multi-error file yields N diagnostics.

## 2B. Structural invariants — one check + test each (§17 #1–#55)
- [ ] WS2-010 #1 single `is` first row · #2 call activated once (do | cleanup defer) · #3 step-target restrictions.
- [ ] WS2-011 #4 do/start/defer reference in-op entity · #5 effect covered by uses (warn) · #6 ifError predecessor + catch.
- [ ] WS2-012 #7 `do TASK` reject · #8 if/ifFalse Bool · #9 catch var in scope at ifError target.
- [ ] WS2-013 #10 return arity · #11 goto target one `at` · #12 unique label · #13 dead label.
- [ ] WS2-014 #14 loop/while/each/break/continue reject · #15 irreducible-flow warn · #16 owned-resource cleaned on all paths.
- [ ] WS2-015 #17 defers reverse-order · #18 onFailure propagate (catch + Result) · #19 logAndSuppress needs because.
- [ ] WS2-016 #20 started task resolved before return · #21 cancel needs start · #22 ifCanceled needs cancel+join.
- [ ] WS2-017 #23 sqlite column consumed before next read · #24 multi-write needs txn · #25 non-void no out/catch/discards = error.
- [ ] WS2-018 #26 no dotted internal refs · #27 declaration reorderable, steps not · #28 immutable-rebind reject / mutable rebind ok.
- [ ] WS2-019 #29 dup field/variant · #30/#31 branch-else default-only-after-guard formatter warn · #32 dup route reject.
- [ ] WS2-020 #33 template arg=hole names · #34 String→HtmlSafeUrl reject · #35 fallible-no-error-path warn (cleanup-worker exempt).
- [ ] WS2-021 #36 ifOut-before-error warn · #37 alias-dotted only in `for` · #38 entry exports (MD1013) · #39 owns w/o cleanedBy warn.
- [ ] WS2-022 #40 ifOut/ifValue sugar info · #41 cleanup one cleans/call · #42 onFailure iff catch · #43 cleanup worker not `do`-activated.
- [ ] WS2-023 #44 cleanup-worker out/no-catch needs discards · #45 Bool/enum equals-only · #46 entity-name unique in module.
- [ ] WS2-024 #47 binding-name no-shadow · #48 invokes resolution · #49 construction-target match.
- [ ] WS2-025 #50 runtimeBinding declares effects + app-source warn · #51 invokes unambiguous · #52 ifVariant exhaustiveness · #53 bind definite-assignment · #54 suppress code+because · #55 forTarget/forPlatform valid target/platform.

## 2C. Metadata rules (MD10xx, §6, §30.6)
- [ ] WS2-030 MD1001/1002 module purpose+invariant required.
- [ ] WS2-031 MD1011/1012/1013 exported/entry op purpose+invariant+exports.
- [ ] WS2-032 MD1021/1022 private-op tiers; MD1031/1032 generated/runtimeBinding off.
- [ ] WS2-033 MD1040–1048 payload shapes; MD1046 **at-most-one** purpose (not "exactly one").
- [ ] WS2-034 `suppress <CODE> because "…"` scope = subject entity + one code; operation covers its steps/let/labels, not child call/task/cleanup. →test: child-row suppress not covered. §30.6.2

## 2D. Effect / authority / cleanup analysis
- [ ] WS2-040 Effect-union: op effective effects = own + activated call/task/cleanup effects; uses covers union; both-direction check. →test: capability gap on call-level effect reported on op. §15
- [ ] WS2-041 Capability coverage across call graph (§29 #10 algorithm). →test: uncovered transitive effect flagged.
- [ ] WS2-042 Ownership/cleanup graph closure (SS1502) on every success path. →test: missing cleanup on a path = error.
- [ ] WS2-043 forTarget/forPlatform reference-closure (filtered set has no dangling refs); filtering-phase-first. →test: included→pruned ref = hard error per target. §30.3.1

## 2E. Semantics-derived lints (§25, §29 #2)
- [ ] WS2-050 Scope checks: out before do/join unbound; catch off ifError-path; join before start. →test: each unbound case. §25
- [ ] WS2-051 Shared catch/err variable tracking + type-compat warn. →test: incompatible shared err warns. §25
- [ ] WS2-052 Error chaining for `onFailure propagate` (currently punted — spec + lint). →test: propagate without Result reject. §29#2

---

# WS3 — Stdlib, runtime & build  (L3)

## 3A. Capability / effect / async runtime
- [ ] WS3-001 Capability values + grants/uses runtime; effect = capability-mediated. →test: op without cap can't perform effect. §8
- [ ] WS3-002 Cleanup/defer runtime (reverse order, every exit; logAndSuppress logs catch; propagate returns; trap = abort). →test: §15.6 + §33.8.
- [ ] WS3-003 Async single-thread cooperative backend (start/join/poll/cancel/detach). →test: race/timeout resolve deterministically. §13
- [ ] WS3-004 `mode capturedOutputReplay` transcript (record/replay; capability-mediated effects only). →test: replay run deterministic + side-effect-free. §30.1.1
- [ ] WS3-005 Build-time capabilities namespace `build.*` (read-only; runtime effect on configure = error). →test: configure with console.stdout effect rejects. §30.3.2

## 3B. Standard library modules (.semsig + impl)  — each: signatures, error contracts, tests
- [ ] WS3-010 `standard.core` primitives if factored out (or built-in). →test: type availability.
- [ ] WS3-011 `console` (writeLine/writeIntegerLine/writeFloatLine). →test: output goldens.
- [ ] WS3-012 `compare.*` derived comparison primitives (all types; Bool/enum equals-only). →test: each comparator. §13
- [ ] WS3-013 `math.*` (int/float arith, checked variants). →test: ops + checked overflow.
- [ ] WS3-014 `convert.*` (incl Wrapping/Saturating; ConversionError). →test: trunc/trap/round. §33.5
- [ ] WS3-015 `string.concat/join/format` (width/format discipline). →test: format-width lint + runtime. §30.2.2
- [ ] WS3-016 `standard.sqlite` (open/close/queryScalar/step/column; OpenMode; OpenFailure/CloseFailure/QueryFailure; owns/cleanedBy). →test: query + cleanup; column-consume lint. §10/§19
- [ ] WS3-017 `standard.http` (HttpRequest/Response/handlers/route/serve/callNext; HttpSafeUrl). →test: route handler ABI + middleware chain. §14
- [ ] WS3-018 `standard.html` (render/trustFragment/fragmentConcat; HtmlFragment/HtmlTrustedFragment/HtmlSafeUrl; `{{hole}}` + `{{rec.field}}`). →test: auto-escape; href HtmlSafeUrl enforce; rejected hole contexts. §16
- [ ] WS3-019 `standard.assert` (equalInt64/true/matchesGolden → TestResult). →test: pass/fail/golden. §30.5.1
- [ ] WS3-020 `standard.test` (TestResult record + `test.and`; lanes). →test: binary fold; lane grouping. §30.5.1
- [ ] WS3-021 `standard.build` (BuildPlan/BuildTarget; emptyPlan/target/withTarget/withConstant). →test: configure builds plan; merge-by-name replace. §30.3.2
- [ ] WS3-022 Construction/access intrinsics auto-derived from record/enum/error decls. →test: derived `.new`/`.field`/`.variant`/`.case`. §10.5
- [ ] WS3-023 Full per-module API catalogs as `.semsig` + generated docs (External surface, §27). →test: `sem docs` per module.

## 3C. Build, packaging, modules (§28)
- [ ] WS3-030 `build.sem` parser (project rows: module/target/entry/mode/languageVersion/toolchain/require/replace/allowEffect/platform/constant/configure/native*). →test: full-grammar golden. §28.1
- [ ] WS3-031 `build.sem.lock` (generated; `PROJECT is project` + resolved/toolchainResolved/effectSurface). →test: lock is valid EAV; hand-edit refused. §28.1
- [ ] WS3-032 Module discovery by directory (dir+main.sem = module; root named by PROJECT module; internal/ visibility). →test: submodule import path = repo+reldir; internal/ leak rejected. §28.3
- [ ] WS3-033 MVS resolver (highest required; no solver). →test: MVS selection golden. §28.4
- [ ] WS3-034 sha256 content-addressed integrity; digest mismatch = hard error. →test: tampered dep rejects. §28.4
- [ ] WS3-035 `sem mod tidy` lock gen; `sem vendor`; module cache. →test: tidy reproducible; vendor build. §28.4
- [ ] WS3-036 Supply-chain capability allowlist (`allowEffect`); dep requesting un-allowed cap refused. →test: socket-requesting dep rejected. §28.5
- [ ] WS3-037 Platform entity (os/arch/targetRuntime/output/override + per-platform native rows); native-link merge order/dedup. →test: per-platform output + flag dedup. §28.1
- [ ] WS3-038 `configure` op (root module, build-time, excluded from runtime build, not gated). →test: configure runs once pre-compile; not in binary. §30.3.2
- [ ] WS3-039 Entry ABIs (console out ExitCode no-in; wasm export; webServer = server entity); multi-target entry via forTarget. →test: each target ABI; two entries gated. §11/§7
- [ ] WS3-040 target vs targetRuntime vs platform relationship (`target wasm`→`targetRuntime wasm`). →test: mismatch reject. §7

## 3D. FFI & .semsig (§26, §30.4)
- [ ] WS3-050 `.semsig` loader + resolution order (--semsig-path → dep pkg → bundled stdlib; first-target wins). →test: resolution precedence. §26
- [ ] WS3-051 `.semsig` header entity (`semsig`/version/generatedBy/describes); reject unknown schema version. →test: header parse; version-reject. §26
- [ ] WS3-052 `intrinsic` signatures (target/arg/out/catch/async/owns/trustConstraint); app-source intrinsic = warn. →test: §26 + app-decl warn.
- [ ] WS3-053 FFI native-link rows + `is intrinsic` + `.semsig`; OpaquePointer→UInt64 interim. →test: extern binding links. §30.4.1
- [ ] WS3-054 `OP export c <symbol>` (C identifier; one per op; unique; forTarget/forPlatform-gatable) — roadmap stub + lint. →test: dup symbol reject. §30.4.2

---

# WS4 — Tooling, formatter & editor  (L4)

## 4A. Formatter (§22, §29 #11) — the canonicalizer everything rests on
- [ ] WS4-001 `sem fmt` canonical EAV: file-level order per file type (module/build.sem/lock/.semsig/.test.sem); per-kind row order; metadata/forTarget/forPlatform/suppress after structural. →test: ordering golden per file type. §22
- [ ] WS4-002 **Determinism**: total + idempotent + order-stable (`fmt(fmt(x))==fmt(x)`). →test: idempotence property test over corpus. §29#11
- [ ] WS4-003 Sugar lowering on fmt (ifOut/ifValue→compare+if; branch else→goto; call async yes→task; compound defer→cleanup) with deterministic names. →test: each sugar → canonical golden; reuse-before-generate. §13/§15.6
- [ ] WS4-004 `sem fmt --surface current|compact|eav`; **round-trip** current↔EAV, compact↔EAV semantics-preserving (gate-0). →test: round-trip equivalence + no-op-lowering-fails. §21/§23
- [ ] WS4-005 Island formatting must NOT de-indent htmlBody (known prior bug). →test: html island round-trips byte-stable.

## 4B. Agent tools (§24) — bind to existing `sem.*.v1` JSON surfaces
- [ ] WS4-010 `sem slice <entity>` (default + --with-calls/cleanup/tasks/--path/--refs/--for-edit; prompt/json/eav modes; 7-point agent contract; stable sections). →test: slice completeness contract (every binding has def, every label def, etc.). §24
- [ ] WS4-011 `sem explain` (entity summary) + map current `explain <CODE>`. →test: failure-path summary golden. §24
- [ ] WS4-012 `sem query` (entity/kind/effects/uses/labels/cleanup/async-unresolved/refs/types-ambiguous/ownership-leaked). →test: each query. §24
- [ ] WS4-013 `sem doctor` (severity-grouped + suggested `sem add`). →test: SS1502/SS1610 surfaced + fix cmds. §24
- [ ] WS4-014 `sem add` / `sem rename` (structured edits; arg-type validation; semantic rename). →test: add validates signature; rename updates refs, rejects ambiguous. §24
- [ ] WS4-015 `sem trace` (path simulation: steps/live bindings/defers/return). →test: trace per path golden. §24
- [ ] WS4-016 `sem graph` (control/cleanup/async/effects/bindings; DOT/mermaid). →test: graph emit. §24
- [ ] WS4-017 `sem normalize --preview` (row delta + edit-locality). →test: row count + gate eval. §24/§21
- [ ] WS4-018 `sem verify-patch` (entities exist; names collision-free; ownership closes; tasks resolved; arity; cap coverage). →test: each failure class. §24
- [ ] WS4-019 `sem pack` (cached-prefix + task-slice + diagnostics + edit-contract; budget). →test: budget respected; prefix stable. §24
- [ ] WS4-020 `sem diff` (semantic: cleanup/control/effect/route changes). →test: semantic-vs-line diff. §24
- [ ] WS4-021 `sem scaffold` (handler/cleanup/task/sqlite-query/html-template canonical patterns). →test: scaffold output parses+lints clean. §24
- [ ] WS4-022 `sem summarize` / `sem inventory`. →test: counts correct. §24
- [ ] WS4-023 `sem lint --explain <CODE>` (rationale + required pattern). →test: registry-backed. §24
- [ ] WS4-024 Mark/align proposed vs shipping shapes (entity-scoped vs path/code-scoped); MCP tool mappings. →test: --json schema conformance. §24

## 4C. Editor / LSP (§29 #7)
- [ ] WS4-030 Semantic tokens (subject-anchored col1=subject/col2=predicate advantage). →test: token classification golden.
- [ ] WS4-031 Hovers (entity contract from signature/metadata) + inlay (call signature at `do` site — read-locality mitigation). →test: hover content.
- [ ] WS4-032 Completions (per-kind predicates; targets from `.semsig`/docs). →test: predicate completion in each kind.
- [ ] WS4-033 Rename, code actions (apply repair suggestions), symbol index. →test: rename across refs; quick-fix applies SS1502 repair.
- [ ] WS4-034 Diagnostics surfaced from linter (mapped to source span). →test: squiggle on correct row.
- [ ] WS4-035 Change-protocol guard: editor grammar moves with parser (never highlight-only). →test: token set == reserved set.

---

# Cross-cutting

## X1. Conformance & test matrix (§29 #6, project rule)
- [ ] X-001 Conformance matrix tying parser/formatter/linter/lowering/editor goldens together. →test: matrix harness runs all lanes.
- [ ] X-002 Promote §18 + §19 worked examples to executable golden programs. →test: both run to expected output/exit.
- [ ] X-003 No-op-lowering-fails guard for every L1 feature (a stub must break the test). →test: mutation/stub run is red.
- [ ] X-004 Test taxonomy wired: unit/component/integration/e2e/golden + `tag test` discovery + `sem test --lane`. →test: each lane discovered & run. §28.7/§30.5
- [ ] X-005 §2↔§5↔§22↔§30.7 **token-sync drift guard**: every reserved word has a §5 predicate-table home (or is a literal/value), a §22 order slot, and (if §30) a §30.7 entry. →test: automated drift check fails on unsynced token.
- [ ] X-006 Invalid-example corpus (one rejecting fixture per hard-error rule). →test: all reject with the right code.

## X2. Minimal-core migration (§34) — L5, split PRESERVED
- [ ] X-010 §14 webServer → `HttpServer` record + `http.route`/`http.serve` calls; delete webServer keywords from §2; add `.semsig`. →test: migrated handler runs; old keywords gone.
- [ ] X-011 §16 htmlTemplate/`body` → `String`/`storage` + `html.render`/`sql.exec` calls. →test: render equivalence.
- [ ] X-012 §9 error/errorCase → `enum`/`variant`. →test: error programs run as enums.
- [ ] X-013 comparators + ifOut/ifValue → `compare.*` + `branch if` (already fmt-lowered). →test: no comparator keyword needed.
- [ ] X-014 §6 metadata → typed comments. →test: docs still generated from comments.
- [ ] X-015 §28 manifest → build record + `standard.build` (project/target/.../platform/forTarget/forPlatform demoted). →test: build from record.
- [ ] X-016 intrinsic/semsig/trustConstraint → `.semsig` sidecar only. →test: no app-source intrinsic.
- [ ] X-017 **Preserve verbatim** (do NOT migrate): call/task/cleanup split (§34.4), effect/capability boundary (§34.1b), tape/control/type primitives. →test: split cross-use still hard-errors post-migration.
- [ ] X-018 Shrink §2 reserved set to minimal-core as each section migrates; keep §2↔§5 in sync (X-005). →test: drift guard green after each migration.

## X3. Docs, governance, rollout (§29 #8/#13, change protocol)
- [ ] X-020 Keep CLAUDE.md / AGENTS.md / syntax-inventory.md in lockstep with grammar (change protocol). →test: contract-version bump check.
- [ ] X-021 Spec coherence: normative/informative labels, single-source-of-truth per topic, glossary (§29 #13).
- [ ] X-022 Versioning & rollout: feature flags, compatibility mode, deprecation policy, milestones (§29 #8).
- [ ] X-023 Adoption gate instrumentation: row-count (compact +20% / EAV +35%), edit-locality, friction logs, **gate-0 round-trip** (§21).
- [ ] X-024 Reconcile §31 "freeze §§1–17" vs §33/§34 (note post-freeze exceptions). docs-only.

## X4. Roadmap-tracked gaps (§29 #14–#25) — spec-then-build, not blocking L1–L4
- [ ] X-030 #14 runtime value semantics — backend mechanism (region/arena/refcount) for value lifetime.
- [ ] X-031 #15 agent edit loop + diagnostic source-mapping (see WS2-004).
- [ ] X-032 #16 human-authoring validation session (learnability, reviewability, compact ergonomics).
- [ ] X-033 #17 existing-corpus migration (stdlib + apps; prove codemod; coexistence policy).
- [ ] X-034 #18 runtime observability/debugging (traces/panics under goto; logging; source maps).
- [ ] X-035 #19 security threat model (assets/adversaries) distinct from #10 enforcement.
- [ ] X-036 #20 strategic success criteria (vs current syntax; vs competitors; multi-surface cost).
- [ ] X-037 #21 performance/profiling; #22 text/i18n; #23 publishing/distribution workflow; #24 macros/reflection; #25 deployment/runtime config — each: spec → stub → defer.

---

## Definition of Done (per workstream)
- **WS1:** Hello World (§18) + web-handler (§19) parse → lower → run; value/control/type semantics tested with no-op-lowering-fails guards.
- **WS2:** every §17 #1–#55 + MD rule has a passing lint test + a rejecting fixture; diagnostic registry complete; source-mapping works.
- **WS3:** console/sqlite/http/html/test/build modules have `.semsig` + impl + tests; build.sem→lock→run reproducible; supply-chain allowlist enforced.
- **WS4:** `sem fmt` total/idempotent/round-trip green; slice+doctor+verify-patch power the diagnose→slice→edit→verify→summarize loop; editor moves with parser.
- **Cross-cutting:** conformance matrix green; drift guard green; §34 migration completed with split preserved.

## Surface-area coverage ledger (3 iterations)
- **Iteration 1 — structural skeleton:** §1–§16 core grammar/types/calls/control/values + §18/§19 examples → WS1 1A–1H, WS3 stdlib stubs, WS4 fmt.
- **Iteration 2 — invariants & resolutions:** §17 #1–#55, MD rules, §30 edge features, §33 resolutions, §10.6 value semantics, §28 build → WS2 (all), WS1 1H/1I, WS3 3A/3C/3D.
- **Iteration 3 — cross-cutting & forward:** §22 ordering, §24 tooling, §26 .semsig, §29 #1–#25 register, §31 layers, §34 minimal-core migration, conformance/drift/docs → WS4, Cross-cutting X1–X4.
- **Checklist:** every spec section §1–§34 ✓ has ≥1 item; every §29 gap #1–#25 ✓ tracked; every §17 invariant #1–#55 ✓ has a check+fixture; every §33 resolution ✓ has a behavior test; the call/task/cleanup split ✓ preserved across L1 (WS1-044), lint (WS2-010), and migration (X-017).
