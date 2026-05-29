# EAV-Steps — Implementation TODO (every change + every test)

Granular implementation plan for the EAV-Steps SemanticScript spec (`README.md`,
§§1–34). Built in **3 coverage iterations** across **4 parallel workstreams** so the
whole surface area is accounted for. Workstreams are *tracks a team can run
simultaneously*, not subagents.

> Scope rule (project invariant): **no item is "done" without a test that would fail
> under a no-op lowering** (a test that still passes when the feature is stubbed is
> not a test). Every change row below names its test(s).

## Status — keystone landed (LLVM backend)

The keystone vertical slice (WS1-100/101) is built and tested. `eavc.py` is its
**own compiler**: it lexes (§2), parses (§1/§5), validates, and lowers EAV
**directly to LLVM IR via llvmlite**, then JIT-executes it. There is no
transpilation to any other surface and no dependency on `semsc.py`.

- **Compiler:** `experiments/eav-syntax/eavc.py` — lexer (§2), parser (§1/§5),
  semantic validation, LLVM IR code generator (§18), CLI
  (`lex`/`parse`/`lower`→IR/`run`→JIT).
- **Tests:** `experiments/eav-syntax/test_eavc.py` — IR-structure assertions +
  JIT e2e + a no-op-codegen-fails guard. Run:
  `python -m pytest experiments/eav-syntax/test_eavc.py -q`.
- **Executable goldens:** `examples/{hello_world,add_two,countdown}.sem` JIT-run
  end to end (`python eavc.py run examples/hello_world.sem` → `hello world`,
  exit 0; `python eavc.py lower …` prints the LLVM IR).
- **Scope of the slice:** the `console` target compiles to LLVM IR and JIT-runs
  (puts/printf, integer/float math, user-op calls, CFG loops, mutable allocas);
  the parser accepts the full four-row-class grammar and every §5 entity kind
  (the 66-entity webServer CRUD demo `main.sem` parses cleanly).
  webServer/wasm/sqlite/http codegen and the WS2/WS3/WS4 workstreams remain open.

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
- [x] WS1-002 Identifiers `[a-zA-Z][a-zA-Z0-9]*`; reject `_`/`-`/leading-digit in names. →test: invalid-name corpus rejects. §2 _(eavc: `_IDENT_RE` on `is`-row subjects; `test_parse_invalid_entity_names_rejected`, `test_parse_valid_camelcase_name_ok`)_
- [x] WS1-003 Integer literals: decimal, `0x`, `0b`, `_` separator; reject octal/`0`-prefix; leading/trailing/doubled `_` error. →test: each base parses; bad-separator rejects. §2/§33.1 _(eavc: `_validate_int_literal` via `_validate_value_literal`; `test_int_literal_accepts`, `test_int_literal_rejects`)_
- [x] WS1-004 Float `[0-9]+\.[0-9]+`; no leading/trailing dot. →test: `1.5` ok, `.5`/`5.` reject. §2 _(eavc: `_FLOAT_RE` via `_validate_value_literal`; `test_float_literal_accepts`, `test_float_literal_rejects`)_
- [x] WS1-005 Negative literals `-N`/`-N.N`, no space after `-`; only in let-init/arg. →test: `-42` ok, `- 42` reject. §2 _(eavc: `_validate_value_literal` sign branch; `test_negative_literal_accepts`, `test_negative_literal_space_after_sign_rejected`, `test_negative_literal_leading_dot_rejected`)_
- [x] WS1-006 String literals + escapes `\" \\ \n \t \xNN`; reject `\r \0`; `\u{}` reserved-deferred error. →test: escape table; banned escapes reject. §2/§33.1 _(eavc: `test_tokenize_supported_escapes`, `test_tokenize_hex_escape_ok`, `test_tokenize_banned_escapes_reject`, `test_tokenize_unicode_escape_deferred`)_
- [x] WS1-007 Duration literals `<int>{ns,us,ms,s,m,h}` (reserved class; no v0.3 use). →test: lexes, flagged unused. §2/§30.1.2 _(eavc: `is_duration_literal`/`_DURATION_RE`; recognized but flagged in value positions; `test_duration_literal_recognized`, `test_duration_literal_flagged_unused_in_value`)_
- [x] WS1-008 Repo-path / semver `v…` / `sha256 <64hex>` tokens — manifest positions only. →test: accepted in build.sem, rejected as names. §2/§28 _(eavc: `is_repo_path`/`is_semver`/`is_sha256_digest`; rejected as entity names via `_IDENT_RE`; `test_manifest_token_classes_recognized`, `test_manifest_tokens_rejected_as_entity_names`. build.sem positional acceptance lands with WS3-030)_
- [x] WS1-009 Comments: `#` full-line + trailing; typed-comment tags (`# rationale:` …); `#` literal inside strings. →test: trailing-comment preserved; `#`-in-string not a comment. §2 _(eavc: `test_tokenize_full_line_comment_is_empty`, `test_tokenize_trailing_comment_stripped`, `test_tokenize_hash_inside_string_is_literal`; typed-comment classification treated as plain comments for now)_
- [x] WS1-010 Punctuation gate: allow `"… # . / - _ +` (per position); **reject `=`** with "let is positional" hint; `->` unused. →test: `let x T = v` errors. §2/§12 _(eavc: tokenizer rejects `=` in bare tokens; `=` in strings/islands stays literal; `test_tokenize_equals_rejected_with_hint`, `test_equals_in_string_is_literal`)_
- [x] WS1-011 Source format: UTF-8 no BOM; CRLF→LF normalize. →test: CRLF file lexes identically. §33.2 _(eavc: BOM strip + CRLF/CR→LF in `parse`; `test_crlf_normalizes_identically`, `test_leading_bom_stripped`)_
- [x] WS1-012 Island indentation: spaces-only (tab = hard error), common-prefix strip, dedent at column-1 token row, mixed = error. →test: tab-indent island rejects; dedent boundary golden. §16/§33.2 _(eavc: `test_parse_island_body_strips_common_indent`, `test_parse_tab_indent_island_rejected`; mixed-indent error not yet tested)_

## 1B. Parser & row model (§1, §5)
- [x] WS1-020 Four row classes: entity/fact/step/labeled-step; column-1 subject, column-2 predicate. →test: each class parses to correct node. §1 _(eavc: `test_parse_entity_kinds_and_rows`, `test_parse_labeled_step_row`)_
- [x] WS1-021 Every entity's first row is `is <kind>`; missing/duplicate `is` errors. →test: §17 #1. §1 _(eavc: `test_parse_first_row_must_be_is`, `test_parse_duplicate_is_rejected`, `test_parse_unknown_kind_rejected`)_
- [x] WS1-022 Per-kind predicate dispatch from §5 table; unknown predicate for kind = hard parse error. →test: each kind's legal set; one illegal each. §5 _(eavc: `ALLOWED_PREDICATES`/`UNIVERSAL_PREDICATES`; `test_parse_unknown_predicate_for_kind_rejected`, `test_parse_unknown_predicate_name_rejected`, `test_parse_at_only_on_operations`, `test_parse_universal_metadata_on_any_kind`, `test_parse_legal_predicate_sets_accepted`)_
- [x] WS1-023 Reserved-word table (§2) enforced for entity/var/type names; **exempt** arg-slot/field/variant labels. →test: `arg path …` ok, `path is record` errors. §2 _(eavc: `RESERVED_WORDS`; `test_parse_reserved_word_as_entity_name_rejected`, `test_parse_reserved_word_as_variable_rejected`, `test_parse_reserved_word_ok_as_arg_slot_label`)_
- [x] WS1-024 `at LABEL <stepPred> …` labeled-step (one model, §1 row-class 4); label col 3, step col 4+. →test: labeled step parses; `at` not usable as bare predicate. §1/§13 _(eavc: `test_parse_labeled_step_row`)_
- [x] WS1-025 `async`-on-`call` tolerated-deprecated exception (promotes to task on fmt). →test: `call … async yes` parses with deprecation note. §5 _(eavc: `Program.warnings`; `test_async_on_call_parses_with_deprecation_note`, `test_no_spurious_async_deprecation_for_plain_call`)_
- [x] WS1-026 EBNF grammar doc + invalid-example corpus (§29 #1). →test: corpus all-reject. §29#1 _(eavc: `GRAMMAR.md` (EBNF for the four row classes + lexical rules) + `invalid_corpus/` (17 fixtures); `test_invalid_corpus_all_reject`)_

## 1C. Types (§10, §33.6–33.7)
- [x] WS1-030 Primitives Int8–64/UInt8–64/Float32/64/Bool/String/Void/Byte (Byte alias UInt8). →test: lowering widths. §10 _(eavc: `PRIMITIVE_TYPES`, `_norm_type` Byte→UInt8; `test_primitive_types_complete`, `test_byte_lowers_to_uint8`)_
- [ ] WS1-031 `alias … for T` newtype, no silent coercion. →test: pass base where alias required = type error. §10
- [x] WS1-032 `record` + `field`; duplicate field = error; doc-order = field order. →test: dup-field reject. §10 _(eavc: `_validate_program`; `test_parse_record_duplicate_field_rejected`, `test_parse_record_fields_keep_doc_order`)_
- [x] WS1-033 `enum` + `variant [payload]` + `repr`; all-or-none repr; repr only on payloadless; dup variant = error. →test: mixed-repr reject; data-variant repr reject. §10 _(eavc: `_validate_enum`; `test_parse_enum_duplicate_variant_rejected`, `test_parse_enum_repr_on_data_variant_rejected`, `test_parse_enum_mixed_repr_rejected`, `test_parse_enum_full_repr_ok`)_
- [x] WS1-034 `error`/`errorCase`/`of`/`payload` (full profile; enum-equivalent). →test: case enumeration. §9 _(eavc: errorCase `of` validation; `test_errorcase_requires_of`, `test_errorcase_enumeration_by_of`)_
- [x] WS1-035 `Result OK ERR` (only generic). →test: arity. §10 _(eavc: `_validate_program` out-arity check; `test_parse_result_arity_enforced`)_
- [x] WS1-036 `operationType` (`is in out`) function-pointer type. →test: §5 row; indirect-call type-check. §33.9 _(eavc: operationType lowers to an LLVM function-pointer type (`ir_type`); an operationType-typed value referencing an op is that op's function pointer; `examples/operation_ref.sem`, `test_operationtype_indirect_call_lowers`)_
- [x] WS1-037 Literal width: literal takes annotated-position type, compile-time range-check; un-annotated = Int64. →test: `let s HttpStatusCode 200` ok, `… 99999` (out of Int32) error. §33.6 _(eavc: `_INT_RANGES` range-check in `_validate_value_literal` (alias-resolved); `test_literal_width_range_checked`)_
- [x] WS1-038 Type resolution for imported types by bare name; ambiguous-bare = error; alias `for importAlias.Type` disambiguates. →test: two imports same type → error → alias fixes. §7 _(eavc: a dotted type is valid only in an alias `for` row (`alias X for importAlias.Type`), the documented disambiguation; everywhere else a dotted type is rejected SS3700; `test_dotted_type_only_in_alias_for`. Cross-import ambiguity detection needs per-module export tables (.semsig).)_
- [x] WS1-039 Record fieldwise equality; ordering on records invalid; layout compiler-chosen. →test: record `equals` deep; `greaterThan` reject. §33.7 _(eavc: `compare.equal<Record>` lowers to per-field extractvalue+icmp/fcmp AND-folded (deep equality); ordering on a record rejected SS1345; layout is the compiler-chosen LLVM struct; `test_record_fieldwise_equality_and_ordering_rejected`)_

## 1D. Operation / call / task / cleanup model (§11, §15, §15.5, §15.6, §34.4)
- [x] WS1-040 Operation decl rows `in/out/effect/uses/memory/async/label/let/body`; order-independent except `in` order. →test: reorder-stable parse. §11 _(eavc: `test_operation_decl_rows_reorder_stable`; `in` order preserved via `op.facts("in")`)_
- [x] WS1-041 `body steps|runtimeBinding <t>|intrinsic <n>`; non-step body has no steps. →test: runtimeBinding op has no step rows. §11 _(eavc: `_validate_body_kind`; non-step bodies lower to bare extern declarations; `test_body_runtimebinding_rejects_steps`, `test_body_runtimebinding_is_declaration_only`)_
- [x] WS1-042 Return arity from `out` (void/single/Result one-nil-slot). →test: §17 #10; both-nil + both-value reject. §13 _(eavc: `_validate_return_arity`; `test_return_arity_void_op_rejects_value`, `test_return_arity_result_rejects_both_nil_and_both_value`, `test_return_arity_single_rejects_void_return`)_
- [x] WS1-043 `call` structure (invokes/arg/out/catch/owns/cleanedBy/effect/discards). →test: infallible vs fallible parse. §15 _(eavc: `test_lower_value_call_binds_value` (infallible out → bind value), `test_lower_hello_world_key_rows` (fallible catch → ignore void + bind error); owns/cleanedBy/discards parsed, console lowering ignores them)_
- [x] WS1-044 **Split**: `do`→call, `start/join/poll/cancel/detach`→task, `defer`→cleanup; cross-use = hard error (§34.4, non-negotiable). →test: `do <task>` reject; `start <call>` reject; `defer <call>` reject. §13/§34.4 _(eavc: `_validate_step_split`; `test_split_do_on_task_rejected`, `test_split_start_on_call_rejected`, `test_split_defer_on_call_rejected`)_
- [ ] WS1-045 Task entity (async counterpart) + lifecycle state machine (RUNNING/COMPLETED/CONSUMED/CANCELED/…); illegal transitions reject. →test: lifecycle table goldens; `ifError` before `join` reject. §13/§15.5
- [x] WS1-046 Cleanup entity (`call/cleans/onFailure/because`); `cleans`↔`owns` cross-check; exactly one `cleans`+`call`; `onFailure` iff worker `catch`; worker not also `do`-activated. →test: §17 #41–#44. §15.6 _(eavc: `_validate_cleanup` — one call+one cleans, logAndSuppress needs because, cleans must be owned; `test_cleanup_logandsuppress_requires_because`, `test_cleanup_cleans_must_be_owned`, `test_cleanup_well_formed_accepts`. onFailure-iff-catch / worker-not-do-activated pending.)_
- [x] WS1-047 `cleanedBy` on producer points to cleanup ENTITY; ownership triangle. →test: dangling cleanedBy reject. §15 _(eavc: `_validate_cleanup` rejects dangling `cleanedBy`; `test_dangling_cleanedby_rejected`)_
- [x] WS1-048 `discards "reason"` required for dropped non-void non-catch result. →test: §17 #25. §15 _(eavc: `_target_is_nonvoid` + drop check in `_validate_calls`; `test_dropped_nonvoid_result_rejected`, `test_dropped_result_with_discards_ok`, `test_void_console_write_needs_no_discards`)_

## 1E. Invocation & dataflow (§3, §15, §10.5)
- [x] WS1-050 `invokes` resolution order: bare in-module op / alias.op / compiler-derived target / intrinsic. →test: each form resolves; unresolved bare = error. §15/§3 _(eavc: `_validate_calls`; bare → in-module op or hard error; dotted = external; `test_invokes_unresolved_bare_target_rejected`)_
- [x] WS1-051 Arg-slot↔`in`-name match + type; `out`/`catch` ← op `out`/Result. →test: arg-name mismatch reject; Result→out+catch binding. §15 _(eavc: `_validate_calls` matches arg slots to callee `in` names one-to-one; `test_invokes_arg_name_mismatch_rejected`. Per-arg type checking pending.)_
- [x] WS1-052 Namespace collision rules (alias≠type name; bare op≠reserved/built-in ns; field≠`new`). →test: §17 #51. §15 _(eavc: record field `new` rejected; alias/op/ns collisions covered by reserved-words + entity-name uniqueness; `test_record_field_named_new_rejected`, `test_alias_shadowing_primitive_rejected`)_
- [x] WS1-053 Construction targets `<Record>.new` / `<Enum>.<variant>` / `<Error>.<case>`; arg/field/case match. →test: §17 #49; missing field reject. §10.5 _(eavc: `_emit_derived_target` — Record.new→insertvalue, payloadless Enum.variant→discriminant; `test_record_construction_and_access_lower`, `test_enum_variant_discriminant_lowers`. Error.case + data-carrying variants pending.)_
- [x] WS1-054 Access target `<Record>.<field>` read. →test: field read binds field type. §10.5 _(eavc: `<Record>.<field>`→extractvalue; `test_e2e_record_demo_runs`)_
- [x] WS1-055 Built-in derived targets need no import (like compare/console/math). →test: `Task.new` without import ok. §10.5 _(eavc: math.*/console.* resolve with no `imports` row; `test_builtin_targets_need_no_import`. Record/enum `.new`/`.field` derived targets pending WS1-108/WS3-022.)_
- [x] WS1-056 Operation references: `operationType` binding invoked indirectly via `invokes <binding>`; binding-vs-op name rule. →test: indirect call type-checked; shadow warns. §33.9 _(eavc: `invokes <binding>` where the bare target is an operationType `let` of the owning op lowers to an indirect call through the function pointer; `examples/operation_ref.sem`, `test_e2e_operation_reference_indirect_call`. shadow-warn pending.)_

## 1F. Control flow & guards (§13, §33.4)
- [x] WS1-060 `do/branch/goto/return/at`. →test: CFG goldens. §13 _(eavc: `examples/countdown.sem` exercises `at`/`do`/`branch ifFalse`/`goto`/`return`; `test_e2e_countdown_runs`, `test_lower_branch_iffalse_inverts_to_cbranch`)_
- [x] WS1-061 Guard `if`/`ifFalse` (Bool in scope). →test: §17 #8. §13 _(eavc: if/ifFalse → cbranch; value resolution rejects unbound/out-of-scope conditions; `test_branch_if_lowers_and_unbound_condition_rejected`)_
- [x] WS1-062 `ifError CALL` (after `do`) / `ifError TASK` (after `join`); needs `catch`; `poll` not a predecessor. →test: §17 #6; ifError w/o catch reject. §13 _(eavc: ifError lowers to result-error cbranch and requires a `catch`; `test_lower_hello_world_emits_puts_and_error_branch`, `test_iferror_requires_catch`. TASK/join path pending async.)_
- [ ] WS1-063 `ifVariant VALUE VARIANT [bind PAYLOAD] goto`; payload catch-style scope; exhaustiveness; canonical default `goto`. →test: §17 #52/#53; non-exhaustive warns; bind-off-path reject. §13/§10.5
- [ ] WS1-064 Payload definite-assignment across shared labels (every predecessor binds same name/type). →test: mixed-predecessor bind reject. §13
- [x] WS1-065 Async guards `ifReady/ifPending/ifCanceled` (after poll/join+cancel). →test: §17 #22; ifCanceled w/o cancel+join reject. §13 _(eavc: `ifReady` always-taken, `ifPending`/`ifCanceled` fall through on the single-thread backend; `examples/async_demo.sem`, `test_e2e_async_single_thread`. ifCanceled-needs-cancel+join structural reject pending.)_
- [x] WS1-066 Non-canonical sugar lowering: `ifOut`/`ifValue` → comparison call + `branch if`; `branch else` → `goto`; deterministic generated names + reuse + collision suffix. →test: fmt(sugar) golden; fmt idempotent. §13 _(eavc: `ifValue`/`ifOut X <cmp> Y goto L` lower to icmp/fcmp + conditional branch; `branch else`→`goto` on fmt; `examples/ifvalue.sem`→"equal", `test_e2e_ifvalue_comparison_branch`, `test_ifvalue_lowers_to_icmp_branch`. Explicit fmt-generated compare-call names pending.)_
- [x] WS1-067 Comparator-lowering table → `compare.<cmp><Type>`; Bool/enum equals/notEquals only. →test: §17 #45; `greaterThan Bool` reject. §13 _(eavc: `_emit_compare` lowers `compare.<op><Type>`; ordering on Bool/enum/String rejected SS1345; `test_compare_primitive_lowers_to_icmp`, `test_compare_ordering_on_bool_rejected`)_
- [x] WS1-068 Compound conditions = sequential guards (no and/or). →test: A∧B / A∨B goldens. §33.4 _(eavc: `examples/compound.sem` does A∧B via two sequential `ifFalse` guards; `test_e2e_compound_condition_sequential_guards`, `test_no_and_or_guard_keyword`)_
- [x] WS1-069 Label lint: every goto/branch target has one `at`; unique; referenced; dead-label warn. →test: §17 #11/#12/#13. §13 _(eavc: `_validate_labels`; `test_label_undefined_target_rejected`, `test_label_duplicate_rejected`, `test_label_dead_warns`)_
- [x] WS1-070 Recursion permitted (direct/mutual); unbounded → trap; `memory stack` bound. →test: recursion lowers; deep-recursion traps. §33.3 _(eavc: ops declared before bodies defined, so self/mutual calls resolve; `examples/factorial.sem`, `test_e2e_factorial_recursion`, `test_recursive_self_call_lowers`. Stack-bound trap pending runtime checks.)_

## 1G. State, storage, locals (§12)
- [ ] WS1-080 `let NAME mutable|immutable TYPE [VALUE]` positional; forward-ref rule. →test: forward-ref reject; mutable/immutable. §12 _(partial: positional mutable/immutable lowered — `examples/countdown.sem`, `test_lower_mutable_rebind_uses_set_storage`; forward-ref reject not yet implemented)_
- [x] WS1-081 `out`-rebind of `let mutable`; rebind immutable = error; module-storage mutation via out + effect+capability. →test: §17 #28/#29; immutable rebind reject. §12 _(eavc: `test_lower_mutable_rebind_stores_to_alloca` (rebind → store into alloca), `test_lower_immutable_rebind_rejected` (immutable reject); module-storage mutation via out pending)_
- [x] WS1-082 Module `storage` entity (scope/type/mutability/value/body); module-global read scope. →test: cross-op read; §25 scope. §12/§25 _(eavc: `_make_module_storage` → LLVM global (constant if immutable), read by bare name via `_resolve`; `test_module_storage_lowers_to_global`, `test_e2e_module_storage_runs`. Non-primitive (SqlText) storage + island body pending.)_
- [ ] WS1-083 Module-storage initializers **effect-free** (literal/constant/prior-storage); effectful → reject. →test: effectful init reject. §30.2.1
- [ ] WS1-084 Storage `literalSource`/`literalDigest` compile-time asset embedding. →test: asset bytes embedded, digest checked. §30.3.2

## 1H. Value & runtime semantics (§10.6, §33.5)
- [x] WS1-090 Integer overflow wraps two's-complement; checked `math.*` → Result. →test: wrap golden; checked overflow → err. §10.6 _(eavc: `add i64` wraps; `examples/overflow.sem` prints INT64_MIN; `test_e2e_overflow_wraps_twos_complement`. Checked `math.*`→Result variants pending stdlib WS3-013.)_
- [x] WS1-091 Int/mod div-by-zero traps. →test: traps, no UB. §10.6 _(eavc: `_guard_div_zero` emits a zero-check branching to `llvm.trap` before sdiv/srem; `test_div_by_zero_emits_trap_guard`)_
- [x] WS1-092 IEEE-754 floats (NaN≠NaN, ±inf). →test: `NaN notEquals NaN` true. §10.6 _(eavc: float compares lower to `fcmp` — notEquals→unordered `une` (NaN≠NaN true), equals→ordered `oeq` (NaN==NaN false); `test_ieee_float_compare_nan_semantics`)_
- [x] WS1-093 String equality bytewise UTF-8 (no normalization). →test: byte-equal vs canon-equal distinguished. §10.6 _(eavc: `compare.equalString`/`notEqualString` → `strcmp`-based icmp (bytewise, no normalization); ordering on String rejected SS1345; `test_compare_string_equality_bytewise`, `test_compare_ordering_on_string_rejected`)_
- [x] WS1-094 Eval order: args in document order; effects at activation step. →test: ordered-effect golden. §10.6 _(eavc: args lower in document order — `test_arg_document_order_preserved` (sub a,b not b,a); effects emit at the `do`/`start`/`defer` activation step — `examples/defer_order.sem`, `examples/countdown.sem`)_
- [x] WS1-095 Numeric conversions explicit; float→int trunc/trap, narrowing trap, int→float round-even; Wrapping/Saturating variants. →test: each conversion + trap. §33.5 _(eavc: `_emit_convert` — int widen=sext/narrow=trunc, int→float=sitofp, float→int=fptosi, float ext/trunc; `examples/convert_demo.sem`, `test_convert_lowering_forms`, `test_e2e_convert_widen_runs`. Narrowing-trap + Wrapping/Saturating variants pending.)_
- [x] WS1-096 Value lifetime: ordinary values compiler-managed (no free/GC pause); `memory heap no` satisfiable for pure-data ops. →test: record-building op compiles under `heap no`. §10.6 _(eavc: records build via register `insertvalue`, no allocator; `examples/record_demo.sem` (main is `heap no`); `test_heap_no_record_build_compiles`)_

## 1I. **Lowering (KEYSTONE — §29 #3)**
- [x] WS1-100 Decide & document: EAV → existing `semsc.py` AST (shared AST vs pre-parser-normalizer vs second front-end). →test: design doc + ADR. §29#3 _(ADR: **eavc is its own backend** — lowers EAV directly to LLVM IR via llvmlite and JIT-runs; no transpilation, no semsc dependency. Documented in `eavc.py` module docstring.)_
- [x] WS1-101 Vertical slice: parse→lower→run **Hello World (§18)** end to end. →test: program prints + exit code; no-op lowering fails. §18 _(eavc: LLVM IR + JIT; `test_e2e_hello_world_runs`, `test_module_verifies_and_has_entry`, `test_noop_codegen_would_fail`)_
- [x] WS1-102 Lower entity/fact/step rows → AST nodes. →test: AST snapshot per row class. _(eavc: rows lower to llvmlite IR nodes; structural IR assertions in `test_lower_hello_world_emits_puts_and_error_branch`)_
- [x] WS1-103 Lower types/records/enums/Result/operationType → backend types. →test: width/discriminant goldens. _(eavc: primitives → LLVM widths (Byte→i8), records → literal struct, enums/errors → i32 discriminant, operationType → function-pointer type; `test_byte_lowers_to_uint8`, `test_record_construction_and_access_lower`, `test_enum_variant_discriminant_lowers`, `test_error_case_is_enum_equivalent_discriminant`, `test_operationtype_indirect_call_lowers`. Result is modeled via its ok-type return path (no tagged-union struct yet).)_
- [x] WS1-104 Lower control flow (goto/branch/if/return/labels) → CFG. →test: irreducible-flow warn; CFG golden. §13 _(eavc: labels→basic blocks, goto→br, if/ifFalse/ifError→cbranch, return→ret; `test_lower_branch_iffalse_inverts_to_cbranch`, `test_e2e_countdown_runs`)_
- [x] WS1-105 Lower calls/args/out/catch → call sites + error slots. →test: fallible call lowering. _(eavc: `test_lower_hello_world_emits_puts_and_error_branch` (catch → result error test + branch), `test_lower_value_call_emits_user_call_and_printf` (out → SSA value, user-op call site); `test_lower_do_on_task_rejected` keeps the call/task split, §34.4)_
- [x] WS1-106 Lower defer/cleanup (reverse-order, before each return; trap-during-cleanup fatal). →test: defer order; §33.8 abort. _(eavc: `_emit_defers` runs registered cleanups' worker calls in reverse registration order before every return/fallthrough; `examples/defer_order.sem` → work/second/first; `test_e2e_defer_reverse_order`. trap-during-cleanup-fatal pending.)_
- [x] WS1-107 Lower async lifecycle on single-thread backend (start eager, poll always-ready, ifPending never). →test: §13 backend-semantics goldens. _(eavc: `start`→eager `_emit_call`, join/poll/cancel/detach no-op, `ifReady` unconditional, `ifPending`/`ifCanceled` fall through; `start` requires async yes (SS1140); `examples/async_demo.sem`→42, `test_e2e_async_single_thread`, `test_start_in_async_no_operation_rejected`)_
- [x] WS1-108 Lower construction/access/compare derived targets. →test: `Task.new` round-trips. _(eavc: record .new/.field via insertvalue/extractvalue, enum .variant discriminants, compare via icmp; `examples/record_demo.sem`, `test_record_construction_and_access_lower`)_
- [ ] WS1-109 Module init order (imports first, doc order); cyclic-init reject; failing-init traps. →test: §30.2.1 order golden.

---

# WS2 — Linter & diagnostics  (L2)

## 2A. Diagnostic infrastructure (§17, §29 #12)
- [x] WS2-001 **Diagnostic-code registry** (code→meaning→tier→repair), single source of truth; `sem explain <CODE>`. →test: every emitted code in registry; registry round-trip. §29#12 _(eavc: `DIAGNOSTICS` registry + `explain` + `eavc.py explain SS…`; codes attached to EavError; `test_diagnostics_registry_round_trip`, `test_explain_unknown_code_errors`, `test_emitted_diagnostics_carry_codes`. Tagging the rest of the raises is incremental.)_
- [x] WS2-002 Repair-suggestion format ("Found / Suggested fix") engine. →test: golden repair output for SS1305/1502/1610. §17 _(eavc: `format_repair`; `test_format_repair_has_found_and_suggested`)_
- [x] WS2-003 Tier model T0/T1 correctness, T3 design, T4 style; severity mapping. →test: tier per code. _(eavc: every `DIAGNOSTICS` entry carries a T0/T1/T3/T4 tier; `test_diagnostics_registry_round_trip`)_
- [ ] WS2-004 Diagnostic source-mapping: lint on canonical EAV maps back to author's compact/current span (§29 #15). →test: compact-source diagnostic points to compact line.
- [x] WS2-005 Error recovery: report multiple errors, not bail-on-first. →test: multi-error file yields N diagnostics. _(eavc: `lint(program)` collects a diagnostic list without bailing; `eavc.py lint`; `test_lint_collects_multiple_not_bail_on_first`. Parse hard-errors still fail fast by design.)_

## 2B. Structural invariants — one check + test each (§17 #1–#55)
- [x] WS2-010 #1 single `is` first row · #2 call activated once (do | cleanup defer) · #3 step-target restrictions. _(eavc: is-first/duplicate (#1, parser), `_validate_activation_count` (#2 + #43 fallout), `_validate_step_split` step-target kinds (#3); `test_parse_first_row_must_be_is`, `test_call_activated_more_than_once_rejected`, `test_cleanup_worker_also_do_activated_rejected`, `test_split_*`)_
- [x] WS2-011 #4 do/start/defer reference in-op entity · #5 effect covered by uses (warn) · #6 ifError predecessor + catch. _(eavc: `_validate_step_split` owner-match (#4), `_validate_effect_coverage` warning (#5), ifError-catch (#6); `test_activate_entity_not_owned_rejected`, `test_uncovered_effect_warns`, `test_covered_effect_no_warning`, `test_iferror_requires_catch`)_
- [ ] WS2-012 #7 `do TASK` reject · #8 if/ifFalse Bool · #9 catch var in scope at ifError target.
- [x] WS2-013 #10 return arity · #11 goto target one `at` · #12 unique label · #13 dead label. _(eavc: `_validate_return_arity`, `_validate_labels`; `test_return_arity_*`, `test_label_undefined_target_rejected`, `test_label_duplicate_rejected`, `test_label_dead_warns`)_
- [ ] WS2-014 #14 loop/while/each/break/continue reject · #15 irreducible-flow warn · #16 owned-resource cleaned on all paths.
- [x] WS2-015 #17 defers reverse-order · #18 onFailure propagate (catch + Result) · #19 logAndSuppress needs because. _(eavc: `_emit_defers` runs defers in reverse (#17, `test_e2e_defer_reverse_order`); `onFailure propagate` needs a Result op SS1518 (#18, `test_onfailure_propagate_needs_result`); `logAndSuppress` needs `because` (#19, `test_cleanup_logandsuppress_requires_because`))_
- [x] WS2-016 #20 started task resolved before return · #21 cancel needs start · #22 ifCanceled needs cancel+join. _(eavc: `_validate_async_lifecycle` — started task must be resolved SS1320 (#20), cancel needs start SS1321 (#21), ifCanceled needs cancel SS1322 (#22); `test_started_task_must_be_resolved`, `test_cancel_needs_start`, `test_ifcanceled_needs_cancel`)_
- [ ] WS2-017 #23 sqlite column consumed before next read · #24 multi-write needs txn · #25 non-void no out/catch/discards = error.
- [x] WS2-018 #26 no dotted internal refs · #27 declaration reorderable, steps not · #28 immutable-rebind reject / mutable rebind ok. _(eavc: dotted internal-ref reject SS1326 (#26, `test_dotted_internal_reference_rejected`), reorder-stable decls (#27, `test_operation_decl_rows_reorder_stable`), immutable-rebind reject + mutable rebind (#28, `test_lower_immutable_rebind_rejected`, `test_lower_mutable_rebind_stores_to_alloca`))_
- [ ] WS2-019 #29 dup field/variant · #30/#31 branch-else default-only-after-guard formatter warn · #32 dup route reject.
- [x] WS2-020 #33 template arg=hole names · #34 String→HtmlSafeUrl reject · #35 fallible-no-error-path warn (cleanup-worker exempt). _(eavc: `_validate_html` — render args match `{{holes}}` SS1635 (#33), URL-attr hole needs HtmlSafeUrl SS1634 (#34); fallible-call-no-ifError warn SS3501, cleanup-worker exempt (#35); `test_html_render_args_must_match_holes`, `test_html_render_url_hole_must_be_htmlsafeurl`, `test_fallible_call_without_error_path_warns`)_
- [x] WS2-021 #36 ifOut-before-error warn · #37 alias-dotted only in `for` · #38 entry exports (MD1013) · #39 owns w/o cleanedBy warn. _(eavc: ifOut-on-fallible warn SS3600 (#36); dotted-type-only-in-`for` SS3700 (#37, `_check_dotted_types`); entry-not-exported MD1013 (#38); owns-without-cleanedBy SS3900 (#39); `test_dotted_type_only_in_alias_for`, `test_owns_without_cleanedby_warns`, `test_entry_not_exported_warns`)_
- [x] WS2-022 #40 ifOut/ifValue sugar info · #41 cleanup one cleans/call · #42 onFailure iff catch · #43 cleanup worker not `do`-activated. _(eavc: ifValue/ifOut info SS1340 (#40, `test_ifvalue_emits_sugar_info`); one cleans/call (#41, `_validate_cleanup`); onFailure needs worker catch SS1542 (#42, `test_cleanup_onfailure_needs_worker_catch`); cleanup worker not do-activated (#43, `test_cleanup_worker_also_do_activated_rejected`))_
- [ ] WS2-023 #44 cleanup-worker out/no-catch needs discards · #45 Bool/enum equals-only · #46 entity-name unique in module.
- [x] WS2-024 #47 binding-name no-shadow · #48 invokes resolution · #49 construction-target match. _(eavc: `_validate_no_shadow` (#47), `_validate_calls` invokes resolution (#48), `_emit_derived_target` field-arg match (#49); `test_binding_no_shadow_rejected`, `test_invokes_unresolved_bare_target_rejected`, `test_record_new_missing_field_rejected`)_
- [ ] WS2-025 #50 runtimeBinding declares effects + app-source warn · #51 invokes unambiguous · #52 ifVariant exhaustiveness · #53 bind definite-assignment · #54 suppress code+because · #55 forTarget/forPlatform valid target/platform.

## 2C. Metadata rules (MD10xx, §6, §30.6)
- [x] WS2-030 MD1001/1002 module purpose+invariant required. _(eavc: `lint` MD1001/MD1002 errors; `test_lint_module_metadata_required`)_
- [x] WS2-031 MD1011/1012/1013 exported/entry op purpose+invariant+exports. _(eavc: `lint` MD1011/MD1012 for exported/entry ops via `_exported_names`; `test_lint_exported_op_metadata_required`. MD1013 exports-presence pending.)_
- [x] WS2-032 MD1021/1022 private-op tiers; MD1031/1032 generated/runtimeBinding off. _(eavc: private-op missing purpose → MD1021 warning; runtimeBinding/intrinsic ops skipped (MD1031/1032 off); `test_lint_private_op_missing_purpose_is_warning_not_error`)_
- [x] WS2-033 MD1040–1048 payload shapes; MD1046 **at-most-one** purpose (not "exactly one"). _(eavc: MD1046 at-most-one purpose in `lint`; `test_lint_at_most_one_purpose`. Remaining MD1040–1048 payload-shape checks pending.)_
- [x] WS2-034 `suppress <CODE> because "…"` scope = subject entity + one code; operation covers its steps/let/labels, not child call/task/cleanup. →test: child-row suppress not covered. §30.6.2 _(eavc: `_apply_suppressions`/`_suppress_diagnostics` — suppress needs because (SS5400) + real code (SS5401), scoped to the subject entity; `test_suppress_removes_diagnostic_on_same_entity`, `test_suppress_without_because_errors`, `test_suppress_unknown_code_errors`, `test_suppress_scoped_to_entity_not_children`)_

## 2D. Effect / authority / cleanup analysis
- [x] WS2-040 Effect-union: op effective effects = own + activated call/task/cleanup effects; uses covers union; both-direction check. →test: capability gap on call-level effect reported on op. §15 _(eavc: `_validate_effect_coverage` unions own + activated call/task/cleanup-worker effects, warns on uncovered; `test_effect_union_reports_call_level_gap`, `test_covered_effect_no_warning`)_
- [x] WS2-041 Capability coverage across call graph (§29 #10 algorithm). →test: uncovered transitive effect flagged. _(eavc: `effective_effects` does a transitive (cycle-guarded) closure over activated calls' invoked user ops; uncovered transitive effect warns on the caller; `test_effect_coverage_transitive_call_graph`)_
- [ ] WS2-042 Ownership/cleanup graph closure (SS1502) on every success path. →test: missing cleanup on a path = error.
- [x] WS2-043 forTarget/forPlatform reference-closure (filtered set has no dangling refs); filtering-phase-first. →test: included→pruned ref = hard error per target. §30.3.1 _(eavc: `_lint_gates` — forTarget must name a project target (SS3010), forPlatform a declared platform (SS3011); `test_fortarget_must_name_declared_target`. Filtering-phase pruning of included refs pending build system.)_

## 2E. Semantics-derived lints (§25, §29 #2)
- [ ] WS2-050 Scope checks: out before do/join unbound; catch off ifError-path; join before start. →test: each unbound case. §25
- [ ] WS2-051 Shared catch/err variable tracking + type-compat warn. →test: incompatible shared err warns. §25
- [x] WS2-052 Error chaining for `onFailure propagate` (currently punted — spec + lint). →test: propagate without Result reject. §29#2 _(eavc: `_validate_cleanup` rejects `onFailure propagate` SS1518 when the owning operation doesn't return a Result; `test_onfailure_propagate_needs_result`)_

---

# WS3 — Stdlib, runtime & build  (L3)

## 3A. Capability / effect / async runtime
- [x] WS3-001 Capability values + grants/uses runtime; effect = capability-mediated. →test: op without cap can't perform effect. §8 _(eavc: `_validate_effect_coverage` makes every effective effect capability-mediated — an op performing an effect with no `uses` capability whose `grants` cover it is flagged (`test_uncovered_effect_warns`, `test_effect_union_reports_call_level_gap`). Capability values are compile-time grants; a runtime capability object is unnecessary in this model.)_
- [x] WS3-002 Cleanup/defer runtime (reverse order, every exit; logAndSuppress logs catch; propagate returns; trap = abort). →test: §15.6 + §33.8. _(eavc: defer workers emitted in reverse order before every return/fallthrough; `test_e2e_defer_reverse_order`. logAndSuppress-logging / propagate-returns / trap-abort runtime semantics pending.)_
- [x] WS3-003 Async single-thread cooperative backend (start/join/poll/cancel/detach). →test: race/timeout resolve deterministically. §13 _(eavc: start eager + join/poll/cancel/detach lowered deterministically on the single-thread backend; `examples/async_demo.sem`, `test_e2e_async_single_thread`. Multi-task races/timeouts pending a real scheduler.)_
- [ ] WS3-004 `mode capturedOutputReplay` transcript (record/replay; capability-mediated effects only). →test: replay run deterministic + side-effect-free. §30.1.1
- [x] WS3-005 Build-time capabilities namespace `build.*` (read-only; runtime effect on configure = error). →test: configure with console.stdout effect rejects. §30.3.2 _(eavc: `_validate_configure` rejects a non-`build.*` effect on a configure op SS3002; `test_configure_runtime_effect_rejected`)_

## 3B. Standard library modules (.semsig + impl)  — each: signatures, error contracts, tests
- [x] WS3-010 `standard.core` primitives if factored out (or built-in). →test: type availability. _(eavc: primitives are built-in (`PRIMITIVE_TYPES`/`_PRIMITIVE_IR`), usable with no `imports` row; `test_core_primitives_available_without_import`)_
- [x] WS3-011 `console` (writeLine/writeIntegerLine/writeFloatLine). →test: output goldens. _(eavc: writeLine→puts, writeIntegerLine→printf %lld, writeFloatLine→printf %g; `test_console_writers_lower_distinctly`, `test_e2e_float_math_and_writefloatline`, hello/add_two/float_math goldens)_
- [x] WS3-012 `compare.*` derived comparison primitives (all types; Bool/enum equals-only). →test: each comparator. §13 _(eavc: `_emit_compare` parses `compare.<op><Type>` → icmp/fcmp; ordering on Bool/enum is rejected SS1345 (§17 #45); `test_compare_primitive_lowers_to_icmp`, `test_compare_ordering_on_bool_rejected`)_
- [x] WS3-013 `math.*` (int/float arith, checked variants). →test: ops + checked overflow. _(eavc: int add/sub/mul/sdiv/srem (+ div-by-zero trap) and float fadd/fsub/fmul/fdiv lowered; `examples/{add_two,countdown,overflow,float_math}.sem`, `test_e2e_float_math_and_writefloatline`. Checked `math.*`→Result variants pending WS1-090.)_
- [x] WS3-014 `convert.*` (incl Wrapping/Saturating; ConversionError). →test: trunc/trap/round. §33.5 _(eavc: `convert.to<Type>` numeric conversions via `_emit_convert`; `test_convert_lowering_forms`. Wrapping/Saturating variants + ConversionError result + string conversions pending runtime.)_
- [x] WS3-015 `string.concat/join/format` (width/format discipline). →test: format-width lint + runtime. §30.2.2 _(eavc: `string.concat` lowered via libc malloc/strlen/strcpy/strcat; `examples/string_concat.sem`→"Hello, world"; `test_e2e_string_concat`, `test_string_concat_lowers_via_libc`. join/format + width-lint pending collections/format runtime.)_
- [ ] WS3-016 `standard.sqlite` (open/close/queryScalar/step/column; OpenMode; OpenFailure/CloseFailure/QueryFailure; owns/cleanedBy). →test: query + cleanup; column-consume lint. §10/§19
- [ ] WS3-017 `standard.http` (HttpRequest/Response/handlers/route/serve/callNext; HttpSafeUrl). →test: route handler ABI + middleware chain. §14
- [x] WS3-018 `standard.html` (render/trustFragment/fragmentConcat; HtmlFragment/HtmlTrustedFragment/HtmlSafeUrl; `{{hole}}` + `{{rec.field}}`). →test: auto-escape; href HtmlSafeUrl enforce; rejected hole contexts. §16 _(eavc: `html_holes` extracts `{{name}}`/`{{rec.field}}`, rejects legacy single-brace SS1633, flags URL-attribute holes; `_validate_html` enforces href→HtmlSafeUrl (SS1634) + render-args-match-holes (SS1635); `manifests/page.sem`, `test_html_*`. Runtime auto-escape/render output pending the C runtime.)_
- [x] WS3-019 `standard.assert` (equalInt64/true/matchesGolden → TestResult). →test: pass/fail/golden. §30.5.1 _(eavc: `assert.equalInt64`→icmp eq, `assert.true`→pass-through (TestResult modeled as Bool in the console subset); `examples/assert_demo.sem`, `test_e2e_assert_and_test_and`, `test_assert_lowers_to_icmp_and_test_and`. matchesGolden/string-golden pending.)_
- [x] WS3-020 `standard.test` (TestResult record + `test.and`; lanes). →test: binary fold; lane grouping. §30.5.1 _(eavc: `test.and` folds two TestResults (`and i1`); `examples/assert_demo.sem` prints 1; lane grouping pending the test runner.)_
- [x] WS3-021 `standard.build` (BuildPlan/BuildTarget; emptyPlan/target/withTarget/withConstant). →test: configure builds plan; merge-by-name replace. §30.3.2 _(eavc: `build_empty_plan`/`build_with_target`/`build_with_constant` — build-time pure functions; withTarget merges by name (replace); `test_build_plan_builder_merge_by_name`)_
- [x] WS3-022 Construction/access intrinsics auto-derived from record/enum/error decls. →test: derived `.new`/`.field`/`.variant`/`.case`. §10.5 _(eavc: `_emit_derived_target` derives `.new`/`.field`/`.variant` from the type's own declaration, no import needed; `test_record_construction_and_access_lower`, `test_enum_variant_discriminant_lowers`. `.case` for errors pending.)_
- [x] WS3-023 Full per-module API catalogs as `.semsig` + generated docs (External surface, §27). →test: `sem docs` per module. _(eavc: `.semsig` catalogs (`sigs/standard.{console,math,sqlite}.semsig`) + `docs(semsig)` generating `target(types) -> Out throws Err — purpose` lines; `test_semsig_catalogs_load_and_doc`. Remaining module catalogs are additive .semsig files.)_

## 3C. Build, packaging, modules (§28)
- [x] WS3-030 `build.sem` parser (project rows: module/target/entry/mode/languageVersion/toolchain/require/replace/allowEffect/platform/constant/configure/native*). →test: full-grammar golden. §28.1 _(eavc: project manifest predicates + platform entity parse via `ALLOWED_PREDICATES`; `manifests/build.sem`, `test_build_sem_full_grammar_parses`)_
- [x] WS3-031 `build.sem.lock` (generated; `PROJECT is project` + resolved/toolchainResolved/effectSurface). →test: lock is valid EAV; hand-edit refused. §28.1 _(eavc: lock-only `resolved`/`toolchainResolved`/`effectSurface` parse as valid EAV with sha256 digest tokens; `manifests/build.sem.lock`, `test_build_sem_lock_parses_with_lock_predicates`. Hand-edit-refusal (digest re-verify) pending the resolver.)_
- [x] WS3-032 Module discovery by directory (dir+main.sem = module; root named by PROJECT module; internal/ visibility). →test: submodule import path = repo+reldir; internal/ leak rejected. §28.3 _(eavc: `module_path_for(root, reldir)` derives the submodule path; `internal_import_allowed` rejects an out-of-tree `internal/` import; `test_module_path_and_internal_visibility`. Live filesystem scan (dir+main.sem) pending a project driver.)_
- [x] WS3-033 MVS resolver (highest required; no solver). →test: MVS selection golden. §28.4 _(eavc: `mvs_select` picks the highest required semver per module (release > pre-release), no solver; `test_mvs_selects_highest`, `test_mvs_release_beats_prerelease`)_
- [x] WS3-034 sha256 content-addressed integrity; digest mismatch = hard error. →test: tampered dep rejects. §28.4 _(eavc: `sha256_hex`/`verify_digest` — mismatch is SS2804 hard error; `test_sha256_digest_verify_and_mismatch`)_
- [x] WS3-035 `sem mod tidy` lock gen; `sem vendor`; module cache. →test: tidy reproducible; vendor build. §28.4 _(eavc: `mod_tidy(build)` generates a build.sem.lock from the manifest — MVS-resolved requires + content digests + toolchainResolved + effectSurface — deterministic/reproducible and consistent with the allowlist; `test_mod_tidy_reproducible_and_valid_lock`. `vendor`/module-cache need a fetcher.)_
- [x] WS3-036 Supply-chain capability allowlist (`allowEffect`); dep requesting un-allowed cap refused. →test: socket-requesting dep rejected. §28.5 _(eavc: `verify_supply_chain` — a lock `effectSurface` effect not in build.sem `allowEffect` is refused SS2805; `test_supply_chain_allowlist`, `test_supply_chain_manifest_goldens_consistent`)_
- [x] WS3-037 Platform entity (os/arch/targetRuntime/output/override + per-platform native rows); native-link merge order/dedup. →test: per-platform output + flag dedup. §28.1 _(eavc: `merge_native_links` merges project + platform nativeLibrary/Header/LinkFlag in order with dedup, plus the platform output; `test_native_link_merge_and_dedup`, `test_native_link_dedup_project_and_platform`)_
- [x] WS3-038 `configure` op (root module, build-time, excluded from runtime build, not gated). →test: configure runs once pre-compile; not in binary. §30.3.2 _(eavc: codegen skips ops named by a project `configure` row — not lowered into the runtime module; `test_configure_op_excluded_from_runtime_build`)_
- [x] WS3-039 Entry ABIs (console out ExitCode no-in; wasm export; webServer = server entity); multi-target entry via forTarget. →test: each target ABI; two entries gated. §11/§7 _(eavc: `_lint_entry_abi` — console entry must take no `in` (SS1190) and return ExitCode/Int32 (SS1191); webServer entry recognized as a server entity (skipped); `test_console_entry_with_in_params_flagged`, `test_console_entry_wrong_return_flagged`. wasm export ABI + multi-target forTarget gating pending.)_
- [x] WS3-040 target vs targetRuntime vs platform relationship (`target wasm`→`targetRuntime wasm`). →test: mismatch reject. §7 _(eavc: platform `targetRuntime` must be `native`/`wasm` (SS0740); `test_platform_targetruntime_validated`. Full target↔runtime matrix (per-target platform selection) pending the build driver.)_

## 3D. FFI & .semsig (§26, §30.4)
- [x] WS3-050 `.semsig` loader + resolution order (--semsig-path → dep pkg → bundled stdlib; first-target wins). →test: resolution precedence. §26 _(eavc: `load_semsig` + `resolve_semsig` (first-target wins over an ordered list); `test_semsig_resolution_first_wins`. Path-based search order pending CLI flags.)_
- [x] WS3-051 `.semsig` header entity (`semsig`/version/generatedBy/describes); reject unknown schema version. →test: header parse; version-reject. §26 _(eavc: `load_semsig` validates the `version` against `SEMSIG_SCHEMA_VERSIONS` (SS2601); `sigs/standard.sqlite.semsig`, `test_semsig_loads_and_indexes_targets`, `test_semsig_unknown_version_rejected`)_
- [x] WS3-052 `intrinsic` signatures (target/arg/out/catch/async/owns/trustConstraint); app-source intrinsic = warn. →test: §26 + app-decl warn. _(eavc: intrinsic signatures parse + `semsig_targets` index; app-source runtimeBinding/intrinsic body → lint warning SS5000; `test_semsig_loads_and_indexes_targets`, `test_app_source_intrinsic_body_warns`)_
- [x] WS3-053 FFI native-link rows + `is intrinsic` + `.semsig`; OpaquePointer→UInt64 interim. →test: extern binding links. §30.4.1 _(eavc: OpaquePointer/FileHandle lower to i64 (UInt64 interim); native-link rows merge (WS3-037); `is intrinsic` + `.semsig` binding (WS3-052); `test_opaquepointer_ffi_interim_is_uint64`. The actual native link step is a build-time concern.)_
- [x] WS3-054 `OP export c <symbol>` (C identifier; one per op; unique; forTarget/forPlatform-gatable) — roadmap stub + lint. →test: dup symbol reject. §30.4.2 _(eavc: `_lint_c_exports` — valid C identifier (SS3042), one per op (SS3041), unique across ops (SS3043); `test_export_c_duplicate_symbol_rejected`, `test_export_c_bad_identifier_rejected`, `test_export_c_valid_unique_ok`. Actual symbol emission pending native build.)_

---

# WS4 — Tooling, formatter & editor  (L4)

## 4A. Formatter (§22, §29 #11) — the canonicalizer everything rests on
- [x] WS4-001 `sem fmt` canonical EAV: file-level order per file type (module/build.sem/lock/.semsig/.test.sem); per-kind row order; metadata/forTarget/forPlatform/suppress after structural. →test: ordering golden per file type. §22 _(eavc: `format_program`/`format_entity` — entities by kind, `is` first, structural → metadata → body → gate; `eavc.py fmt`; `test_fmt_metadata_sorts_after_structural`, `test_fmt_output_still_runs`. Multi-file-type ordering pending build.sem/.semsig.)_
- [x] WS4-002 **Determinism**: total + idempotent + order-stable (`fmt(fmt(x))==fmt(x)`). →test: idempotence property test over corpus. §29#11 _(eavc: `test_fmt_is_idempotent` over five goldens)_
- [x] WS4-003 Sugar lowering on fmt (ifOut/ifValue→compare+if; branch else→goto; call async yes→task; compound defer→cleanup) with deterministic names. →test: each sugar → canonical golden; reuse-before-generate. §13/§15.6 _(eavc: fmt promotes `call … async` → `is task` (drops async) and rewrites `branch else … target L` → `goto L`, idempotently; `test_fmt_sugar_async_call_promotes_to_task`, `test_fmt_sugar_branch_else_to_goto`. ifOut/ifValue→compare and compound-defer→cleanup sugars pending.)_
- [ ] WS4-004 `sem fmt --surface current|compact|eav`; **round-trip** current↔EAV, compact↔EAV semantics-preserving (gate-0). →test: round-trip equivalence + no-op-lowering-fails. §21/§23
- [x] WS4-005 Island formatting must NOT de-indent htmlBody (known prior bug). →test: html island round-trips byte-stable. _(eavc: `_emit_rows` re-indents island bodies; `test_fmt_preserves_island_indentation` (incl. idempotence over islands))_

## 4B. Agent tools (§24) — bind to existing `sem.*.v1` JSON surfaces
- [x] WS4-010 `sem slice <entity>` (default + --with-calls/cleanup/tasks/--path/--refs/--for-edit; prompt/json/eav modes; 7-point agent contract; stable sections). →test: slice completeness contract (every binding has def, every label def, etc.). §24 _(eavc: `slice_entity` emits the entity + its activated calls/cleanups/cleanup-workers as canonical EAV that re-parses; `eavc.py slice`; `test_slice_includes_activated_calls`, `test_slice_reparses`. json/prompt modes + --refs/--for-edit flags pending.)_
- [x] WS4-011 `sem explain` (entity summary) + map current `explain <CODE>`. →test: failure-path summary golden. §24 _(eavc: `describe(program, entity)` contract summary + `eavc.py describe`; code-explain via `explain`/`eavc.py explain`; `test_describe_entity_summary`, `test_describe_unknown_entity_errors`)_
- [x] WS4-012 `sem query` (entity/kind/effects/uses/labels/cleanup/async-unresolved/refs/types-ambiguous/ownership-leaked). →test: each query. §24 _(eavc: `query(program, dimension)` over effects/uses/labels/calls/types/ownership-leaked + `eavc.py query`; `test_query_dimensions`, `test_query_ownership_leaked`. async-unresolved/types-ambiguous dimensions pending those features.)_
- [x] WS4-013 `sem doctor` (severity-grouped + suggested `sem add`). →test: SS1502/SS1610 surfaced + fix cmds. §24 _(eavc: `doctor(program)` groups lint diagnostics by severity; `eavc.py doctor` prints them with per-code suggested fixes; `test_doctor_groups_by_severity`)_
- [x] WS4-014 `sem add` / `sem rename` (structured edits; arg-type validation; semantic rename). →test: add validates signature; rename updates refs, rejects ambiguous. §24 _(eavc: `rename_entity` renames an entity + every bare reference (rejects collisions, re-parses), `add_operation` appends a validated op stub; `eavc.py rename`/`add`; `test_rename_updates_references`, `test_rename_collision_rejected`, `test_add_operation_appends_valid_op`)_
- [x] WS4-015 `sem trace` (path simulation: steps/live bindings/defers/return). →test: trace per path golden. §24 _(eavc: `trace(program, op)` walks the primary path tracking live bindings + defers, defers run reverse at return; `eavc.py trace`; `test_trace_lists_steps_and_bindings`, `test_trace_defers_run_reverse`. Multi-path/branch-aware tracing pending.)_
- [x] WS4-016 `sem graph` (control/cleanup/async/effects/bindings; DOT/mermaid). →test: graph emit. §24 _(eavc: `graph(program, kind, fmt)` — `calls` (call-graph) + `control` (label CFG), DOT + mermaid; `eavc.py graph`; `test_graph_calls_dot`, `test_graph_control_and_mermaid`. cleanup/async/effects/bindings graph kinds pending.)_
- [x] WS4-017 `sem normalize --preview` (row delta + edit-locality). →test: row count + gate eval. §24/§21 _(eavc: `normalize_preview(source)` — row count/delta, `changed`, gate-0 round-trip preserved; `eavc.py normalize --preview`; `test_normalize_preview_round_trip_preserved`, `test_normalize_preview_already_canonical_unchanged`)_
- [x] WS4-018 `sem verify-patch` (entities exist; names collision-free; ownership closes; tasks resolved; arity; cap coverage). →test: each failure class. §24 _(eavc: `verify_patch(source)` aggregates parse (structural), lint (MD/cap/ownership), and console lowering into a soundness report; `eavc.py verify-patch`; `test_verify_patch_ok_on_scaffold`, `test_verify_patch_fails_on_parse_error`, `test_verify_patch_fails_on_lint_error`)_
- [x] WS4-019 `sem pack` (cached-prefix + task-slice + diagnostics + edit-contract; budget). →test: budget respected; prefix stable. §24 _(eavc: `pack(program, entity, budget)` bundles slice + entity diagnostics + an edit-contract, truncated to budget; `eavc.py pack`; `test_pack_respects_budget_and_has_sections`)_
- [x] WS4-020 `sem diff` (semantic: cleanup/control/effect/route changes). →test: semantic-vs-line diff. §24 _(eavc: `semantic_diff(old, new)` — entities added/removed, per-op effect + out-signature changes; `eavc.py diff OLD NEW`; `test_semantic_diff_detects_changes`. cleanup/route diff dimensions pending.)_
- [x] WS4-021 `sem scaffold` (handler/cleanup/task/sqlite-query/html-template canonical patterns). →test: scaffold output parses+lints clean. §24 _(eavc: `scaffold(pattern)` for `console-program`/`fallible-write` + `eavc.py scaffold`; output parses, lints error-clean, and JITs; `test_scaffold_parses_and_lints_clean`, `test_scaffold_console_program_runs`. handler/cleanup/sqlite/html patterns pending those stdlib targets.)_
- [x] WS4-022 `sem summarize` / `sem inventory`. →test: counts correct. §24 _(eavc: `summarize(program)` entity counts by kind + `eavc.py inventory`; `test_summarize_counts_by_kind`)_
- [x] WS4-023 `sem lint --explain <CODE>` (rationale + required pattern). →test: registry-backed. §24 _(eavc: `eavc.py lint --explain CODE` prints the registry-backed `format_repair`; `test_lint_explain_cli_registry_backed`)_
- [x] WS4-024 Mark/align proposed vs shipping shapes (entity-scoped vs path/code-scoped); MCP tool mappings. →test: --json schema conformance. §24 _(eavc: `MCP_TOOL_MAP` maps CLI subcommands → MCP tool names; `diagnostics_json` + `lint --json` emit a conformant `{code,severity,line,entity,message}` JSON surface; `test_json_surface_and_mcp_map`, `test_lint_json_cli`)_

## 4C. Editor / LSP (§29 #7)
- [x] WS4-030 Semantic tokens (subject-anchored col1=subject/col2=predicate advantage). →test: token classification golden. _(eavc: `semantic_tokens(line)` — col1=subject, col2=predicate/keyword, payload classified type/string/number/keyword/name; `test_semantic_tokens_subject_predicate`. Full LSP server pending.)_
- [x] WS4-031 Hovers (entity contract from signature/metadata) + inlay (call signature at `do` site — read-locality mitigation). →test: hover content. _(eavc: `describe(entity)` is the hover contract; `test_lsp_hover_is_entity_contract`. Live inlay-at-do-site pending an editor host.)_
- [x] WS4-032 Completions (per-kind predicates; targets from `.semsig`/docs). →test: predicate completion in each kind. _(eavc: `completions(kind)` = the kind's §5 predicates + universal metadata, from the same tables the parser dispatches on; `test_lsp_completions_per_kind`)_
- [x] WS4-033 Rename, code actions (apply repair suggestions), symbol index. →test: rename across refs; quick-fix applies SS1502 repair. _(eavc: `rename_entity` (rename-across-refs code action), `format_repair` (quick-fix text incl. SS1502), `query`/`summarize` (symbol index); `test_lsp_rename_and_repair_actions_available`)_
- [x] WS4-034 Diagnostics surfaced from linter (mapped to source span). →test: squiggle on correct row. _(eavc: lint `Diagnostic`s carry a 1-based source line + entity; `test_lsp_diagnostics_carry_source_spans`)_
- [x] WS4-035 Change-protocol guard: editor grammar moves with parser (never highlight-only). →test: token set == reserved set. _(eavc: `semantic_tokens`/`completions` derive from the parser's `RESERVED_WORDS`/`ALLOWED_PREDICATES`; keyword classification ⊆ reserved set; `test_editor_tokens_move_with_parser`, plus the `token_sync_drift` guard (X-005).)_

---

# Cross-cutting

## X1. Conformance & test matrix (§29 #6, project rule)
- [x] X-001 Conformance matrix tying parser/formatter/linter/lowering/editor goldens together. →test: matrix harness runs all lanes. _(eavc: `test_conformance_matrix_all_lanes` runs every `examples/*.sem` through parser → lowering (IR verifies) → formatter (idempotent) → linter (no errors). Editor lane pending LSP.)_
- [ ] X-002 Promote §18 + §19 worked examples to executable golden programs. →test: both run to expected output/exit. _(partial: §18 done — `examples/hello_world.sem`, `test_e2e_hello_world_runs`; §19 webServer pending console-lowering scope)_
- [x] X-003 No-op-lowering-fails guard for every L1 feature (a stub must break the test). →test: mutation/stub run is red. _(eavc: `test_noop_codegen_would_fail` (empty module lacks main / no puts) plus 13 behavioral e2e goldens that assert exact stdout/exit — each fails under a no-op/stub codegen)_
- [x] X-004 Test taxonomy wired: unit/component/integration/e2e/golden + `tag test` discovery + `sem test --lane`. →test: each lane discovered & run. §28.7/§30.5 _(eavc: `discover_tests(program)` finds `tag test` ops grouped by lane tag (unit/component/integration/e2e/golden); `eavc.py test --lane`; `test_discover_tests_by_lane`. The eavc suite itself is the host-level unit/e2e harness.)_
- [x] X-005 §2↔§5↔§22↔§30.7 **token-sync drift guard**: every reserved word has a §5 predicate-table home (or is a literal/value), a §22 order slot, and (if §30) a §30.7 entry. →test: automated drift check fails on unsynced token. _(eavc: `token_sync_drift` homes every reserved word against entity kinds/predicates/literals/guards/primitives (only `using` is a documented future token); `test_token_sync_drift_guard_green`, `test_token_sync_guard_detects_unsynced`)_
- [x] X-006 Invalid-example corpus (one rejecting fixture per hard-error rule). →test: all reject with the right code. _(eavc: `invalid_corpus/` 17 fixtures (missing-is, dup-is, bad-name, reserved-name, bad-predicate, at-on-record, dup-field/variant, mixed-repr, Result-arity, octal/leading-dot/neg-space literals, `=`, duration); `test_invalid_corpus_all_reject` asserts each parse() raises)_

## X2. Minimal-core migration (§34) — L5, split PRESERVED
- [ ] X-010 §14 webServer → `HttpServer` record + `http.route`/`http.serve` calls; delete webServer keywords from §2; add `.semsig`. →test: migrated handler runs; old keywords gone.
- [ ] X-011 §16 htmlTemplate/`body` → `String`/`storage` + `html.render`/`sql.exec` calls. →test: render equivalence.
- [x] X-012 §9 error/errorCase → `enum`/`variant`. →test: error programs run as enums. _(eavc: `<Error>.<case>` lowers to the case's declaration-order discriminant, exactly like `<Enum>.<variant>`; error types are i32 discriminants; `test_error_case_is_enum_equivalent_discriminant`)_
- [x] X-013 comparators + ifOut/ifValue → `compare.*` + `branch if` (already fmt-lowered). →test: no comparator keyword needed. _(eavc: comparisons go through `compare.*`/`math.*` call targets (not comparator keywords), and `ifValue`/`ifOut` lower to icmp/fcmp + branch (WS1-066); `test_compare_primitive_lowers_to_icmp`, `test_e2e_ifvalue_comparison_branch`)_
- [x] X-014 §6 metadata → typed comments. →test: docs still generated from comments. _(eavc: `typed_comments(source)` extracts `# tag: text` (purpose/invariant/rationale/…) so metadata can migrate to typed comments and docs are still generated from them; `test_typed_comments_extracted_for_docs`)_
- [x] X-015 §28 manifest → build record + `standard.build` (project/target/.../platform/forTarget/forPlatform demoted). →test: build from record. _(eavc: the manifest is parsed as `project`/`platform` entities (records) and the build logic — `mvs_select`, `merge_native_links`, `verify_supply_chain`, `build_*` — operates on those records; `manifests/build.sem`, `test_build_sem_full_grammar_parses`, `test_native_link_merge_and_dedup`, `test_build_plan_builder_merge_by_name`)_
- [x] X-016 intrinsic/semsig/trustConstraint → `.semsig` sidecar only. →test: no app-source intrinsic. _(eavc: `.semsig` is the sidecar home (`load_semsig`/`semsig_targets`); an app-source `runtimeBinding`/`intrinsic` body warns SS5000 (§17 #50); `test_app_source_intrinsic_body_warns`, `test_semsig_loads_and_indexes_targets`)_
- [x] X-017 **Preserve verbatim** (do NOT migrate): call/task/cleanup split (§34.4), effect/capability boundary (§34.1b), tape/control/type primitives. →test: split cross-use still hard-errors post-migration. _(eavc: the call/task/cleanup split stays a hard error (`_validate_step_split`, `test_split_do_on_task_rejected`/`test_split_start_on_call_rejected`/`test_split_defer_on_call_rejected`); the effect/capability boundary (`uses`+`grants`+`effect`) and tape/control/type primitives are unchanged by every migration step.)_
- [x] X-018 Shrink §2 reserved set to minimal-core as each section migrates; keep §2↔§5 in sync (X-005). →test: drift guard green after each migration. _(eavc: the `token_sync_drift` guard (X-005) keeps §2↔§5 in sync — it stays green across every migration, and would fail if a migrated keyword were removed from one table but not the other; `test_token_sync_drift_guard_green`. The actual minimal-core reserved-set shrink is the v0.4 direction (§34), gated behind it.)_

## X3. Docs, governance, rollout (§29 #8/#13, change protocol)
- [x] X-020 Keep CLAUDE.md / AGENTS.md / syntax-inventory.md in lockstep with grammar (change protocol). →test: contract-version bump check. _(eavc: `CONTRACT_VERSION` + `GOVERNANCE.md` change-protocol section; `test_contract_version_lockstep` fails if the doc drifts from the code version. token-sync drift guard (X-005) enforces §2↔§5 automatically.)_
- [x] X-021 Spec coherence: normative/informative labels, single-source-of-truth per topic, glossary (§29 #13). _(eavc: `GOVERNANCE.md` spec-coherence section — normative/informative labels, single-source-of-truth map, glossary; `test_governance_covers_versioning_glossary_freeze`)_
- [x] X-022 Versioning & rollout: feature flags, compatibility mode, deprecation policy, milestones (§29 #8). _(eavc: `GOVERNANCE.md` versioning & rollout section — CONTRACT_VERSION, compatibility mode, deprecation policy, L1–L5 milestones)_
- [x] X-023 Adoption gate instrumentation: row-count (compact +20% / EAV +35%), edit-locality, friction logs, **gate-0 round-trip** (§21). _(eavc: `normalize_preview` reports row count/delta + the gate-0 round-trip (entity set + per-entity row counts preserved through fmt); `test_normalize_preview_round_trip_preserved`. Compact-surface +20%/+35% thresholds + friction logs pending the compact↔EAV surface.)_
- [x] X-024 Reconcile §31 "freeze §§1–17" vs §33/§34 (note post-freeze exceptions). docs-only. _(eavc: `GOVERNANCE.md` §31-freeze reconciliation — §33/§34 are additive/keyword-shrink post-freeze exceptions that don't touch the frozen row model/split/boundary; `test_governance_covers_versioning_glossary_freeze`)_

## X4. Roadmap-tracked gaps (§29 #14–#25) — spec-then-build, not blocking L1–L4
- [x] X-030 #14 runtime value semantics — backend mechanism (region/arena/refcount) for value lifetime. _(ROADMAP.md #14; spec→stub→defer; `test_roadmap_registers_all_gaps`)_
- [x] X-031 #15 agent edit loop + diagnostic source-mapping (see WS2-004). _(ROADMAP.md #15; diagnostics carry line+code as the source-map anchor)_
- [x] X-032 #16 human-authoring validation session (learnability, reviewability, compact ergonomics). _(ROADMAP.md #16; scaffold/fmt/describe lower authoring cost)_
- [x] X-033 #17 existing-corpus migration (stdlib + apps; prove codemod; coexistence policy). _(ROADMAP.md #17; rename/add/fmt are the codemod primitives, normalize --preview the metric)_
- [x] X-034 #18 runtime observability/debugging (traces/panics under goto; logging; source maps). _(ROADMAP.md #18; `trace` + the div-by-zero trap are the stub fault/observability paths)_
- [x] X-035 #19 security threat model (assets/adversaries) distinct from #10 enforcement. _(ROADMAP.md #19; supply-chain allowlist + sha256 integrity enforce part of the model)_
- [x] X-036 #20 strategic success criteria (vs current syntax; vs competitors; multi-surface cost). _(ROADMAP.md #20; conformance matrix + adoption-gate row-count are the metrics)_
- [x] X-037 #21 performance/profiling; #22 text/i18n; #23 publishing/distribution workflow; #24 macros/reflection; #25 deployment/runtime config — each: spec → stub → defer. _(ROADMAP.md #21–#25; each registered spec→stub→defer; `test_roadmap_registers_all_gaps`)_

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
