#!/usr/bin/env python3
"""eavc — EAV-Steps compiler front end and LLVM backend (lexer, parser, codegen, CLI).

This is the keystone vertical slice for the EAV-Steps v0.3 spec (README.md). It
implements WS1-100 (the lowering ADR) and WS1-101 (parse -> lower -> run Hello
World) from todos.md.

ADR (WS1-100): eavc is **its own backend**. A parsed EAV Program is lowered
*directly to LLVM IR* with ``llvmlite`` and JIT-executed in process. There is no
transpilation to any other surface syntax and no dependency on the reference
compiler — eavc owns lexing, parsing, semantic validation, and code generation.
The no-op-lowering-fails guarantee is concrete: a stubbed code generator emits a
module that fails ``verify()`` or prints nothing.

The front end is split into pure stages so each is testable in isolation:

    tokenize_line(text)        -> list[str]            (lexer, README ss2)
    parse(source_text)         -> Program              (parser, README ss1/ss5)
    lower_to_llvm(program)     -> llvmlite.ir.Module   (codegen, README ss18)
    jit_run(program)           -> int                  (JIT execution)

Scope of this slice: the parser accepts the full four-row-class grammar and all
entity kinds in README ss5 so real programs parse without special-casing; the
code generator targets the *console* program model end to end (Hello World,
ss18). Constructs that only make sense for the webServer/wasm targets are parsed
but rejected by the console code generator with a clear message, rather than
silently mis-lowered.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


# Contract version for the EAV-Steps front end. Bumping this requires updating
# GOVERNANCE.md (the change-protocol lockstep check, X-020).
CONTRACT_VERSION = "eav-0.3"


class EavError(Exception):
    """A lex/parse/lower diagnostic with an optional 1-based source line and an
    optional diagnostic code (see DIAGNOSTICS / `sem explain`)."""

    def __init__(
        self, message: str, line: Optional[int] = None, code: Optional[str] = None
    ) -> None:
        self.message = message
        self.line = line
        self.code = code
        prefix = f"{code}: " if code else ""
        if line is not None:
            super().__init__(f"{prefix}line {line}: {message}")
        else:
            super().__init__(f"{prefix}{message}")


# --------------------------------------------------------------------------
# Diagnostic-code registry (README ss17/ss29 #12) — single source of truth.
# Tier model: T0/T1 correctness (errors), T3 design debt, T4 style (warnings).
# --------------------------------------------------------------------------

DIAGNOSTICS: dict[str, dict] = {
    "SS0002": {
        "tier": "T1",
        "summary": "Entity name is not a valid identifier.",
        "found": "A name with `_`, `-`, or a leading digit.",
        "suggested": "Use camelCase: a letter followed by letters/digits (README §2).",
    },
    "SS0003": {
        "tier": "T1",
        "summary": "Reserved word used as an entity or variable name.",
        "found": "A §2 reserved word in a name position.",
        "suggested": "Rename; arg-slot/field/variant labels are exempt (README §2).",
    },
    "SS1010": {
        "tier": "T1",
        "summary": "`out Result` must carry exactly an OK type and an ERR type.",
        "found": "`out Result` with the wrong number of type arguments.",
        "suggested": "Write `out Result <OkType> <ErrType>` (README §10).",
    },
    "SS1041": {
        "tier": "T0",
        "summary": "`ifError` needs a fallible call with a `catch` row.",
        "found": "`branch ifError CALL` where CALL has no `catch`.",
        "suggested": "Add a `catch <errVar> <ErrType>` row to CALL (README §13, §17 #6).",
    },
    "SS1044": {
        "tier": "T0",
        "summary": "call/task/cleanup activation split violated.",
        "found": "`do` on a task, `start` on a call, or `defer` on a non-cleanup.",
        "suggested": "`do`→call, `start/join/poll/cancel/detach`→task, `defer`→cleanup (README §34.4).",
    },
    "SS1060": {
        "tier": "T1",
        "summary": "Return arity does not match the operation's `out`.",
        "found": "A `return` with the wrong number of values for the out signature.",
        "suggested": "void→no value; single→one value; Result→one value + one `nil` (README §17 #10).",
    },
    "SS1311": {
        "tier": "T0",
        "summary": "goto/branch target has no matching `at` label.",
        "found": "A `goto`/`branch ... goto L` where no `at L` exists.",
        "suggested": "Add `at L <step>` in the same operation, or fix the target (README §17 #11).",
    },
    "SS1502": {
        "tier": "T0",
        "summary": "Rebinding an immutable `let` via call `out`.",
        "found": "A call `out` writing a name declared `let immutable`.",
        "suggested": "Declare the binding `let mutable`, or bind a fresh name (README §12, §17 #28).",
    },
    "SS1503": {
        "tier": "T0",
        "summary": "Owned resource's cleanup not deferred.",
        "found": "A call owns a cleanedBy resource whose cleanup is never `defer`-ed.",
        "suggested": "Add `defer <cleanup>` so it runs on every path (README §15.6, §17 #16).",
    },
    "SS1560": {
        "tier": "T0",
        "summary": "Borrowed view escapes its lifetime.",
        "found": "A `mayEscape no` view's out value is returned out of its operation.",
        "suggested": "Return an owned value, or mark the view `mayEscape yes` only if the borrowed source truly outlives the call (README §32.1 #9).",
    },
    "SS1566": {
        "tier": "T0",
        "summary": "Borrowed view declares cleanup.",
        "found": "A call that `borrows` a resource also declares `owns`/`cleanedBy`.",
        "suggested": "Views borrow and never clean up — drop `owns`/`cleanedBy`; only the owning resource cleans (README §32.1 #9).",
    },
    "SS1564": {
        "tier": "T0",
        "summary": "Use of a consumed (moved) owned handle.",
        "found": "An owned handle is reused after a call consumed it (`arg … consumes yes` / `takesOwnership`).",
        "suggested": "Ownership transferred to the callee — do not reuse the handle after the consuming call; bind the callee's result instead (README §32.1 #9).",
    },
}


# Metadata rules (README ss6) — collected by the linter, not raised at parse.
DIAGNOSTICS.update({
    "MD1001": {"tier": "T1", "summary": "Module is missing a `purpose`.",
               "found": "A module with no purpose row.",
               "suggested": "Add `<module> purpose \"…\"` (README §6)."},
    "MD1002": {"tier": "T1", "summary": "Module is missing an `invariant`.",
               "found": "A module with no invariant row.",
               "suggested": "Add `<module> invariant \"…\"` (README §6)."},
    "MD1011": {"tier": "T1", "summary": "Exported/entry operation missing `purpose`.",
               "found": "A public operation with no purpose.",
               "suggested": "Add a `purpose` row (README §6 tiers)."},
    "MD1012": {"tier": "T1", "summary": "Exported/entry operation missing `invariant`.",
               "found": "A public operation with no invariant.",
               "suggested": "Add an `invariant` row (README §6 tiers)."},
    "MD1021": {"tier": "T3", "summary": "Private operation has no `purpose` (recommended).",
               "found": "A module-private operation with no purpose.",
               "suggested": "Add a `purpose` row, or leave it (warning only)."},
    "MD1046": {"tier": "T1", "summary": "At most one `purpose` row per entity.",
               "found": "An entity with two or more purpose rows.",
               "suggested": "Keep a single `purpose` row (README §6)."},
    "SS0900": {"tier": "T3", "summary": "Advisory lint warning.",
               "found": "A design/usage caution accumulated during parsing.",
               "suggested": "See the message text (effect coverage, dead label, …)."},
    "SS0950": {"tier": "T3", "summary": "Loop makes no progress toward its exit.",
               "found": "A back-edge loop with no exit path, or whose exit guard is never recomputed in the body.",
               "suggested": "Add a reachable exit (return/branch-out) and recompute or mutate the exit guard each iteration (README §13/§33.3)."},
    "SS3095": {"tier": "T1", "summary": "Arithmetic on wall-clock time.",
               "found": "A math.* call with a `WallTime` operand (elapsed/duration or local-time arithmetic).",
               "suggested": "Use a `MonotonicInstant` for durations, or an explicit timezone conversion for calendar math; `WallTime` has no arithmetic (README §30.5.3/§27)."},
    "SS3070": {"tier": "T1", "summary": "Untrusted value reaches a trust-sensitive sink.",
               "found": "An arg whose type is `typeTrust rawExternal` (or secret) is passed to a `trustConstraint` sink slot.",
               "suggested": "Cross a `trustBoundary` validator first so the value becomes `validated`/`trustedInternal` (README §16/§26)."},
    "SS3071": {"tier": "T1", "summary": "Untyped or string-built value into a typed sink.",
               "found": "A plain String (or a `string.concat` result) passed to a `trustConstraint arg <slot> <TrustedType>` sink.",
               "suggested": "Build the required trusted type (e.g. SqlText/HtmlSafeUrl/SafePath) via a constructor or trust boundary; never assemble interpreter input by string concatenation (README §16/§30.2.2)."},
    "SS3072": {"tier": "T1", "summary": "Secret value observed, or hardcoded.",
               "found": "A `typeTrust secret` value reaches an observable sink (console/log), or a secret-typed binding is initialized from a literal.",
               "suggested": "A secret is usable (verify/sign) but never observable — don't print/log it; load it from a capability-gated source, never a source literal (README §30.1.1/§8)."},
    "SS3074": {"tier": "T1", "summary": "Non-constant-time comparison of a secret.",
               "found": "A `math.*`/`compare.*` equality on a `typeTrust secret` operand (timing side-channel).",
               "suggested": "Compare secrets only with `crypto.equalConstantTime` (README §13)."},
    "SS3077": {"tier": "T1", "summary": "Untrusted decode without a size limit.",
               "found": "A decode (json.parse/decode/createDocument/codec.decode) of a `rawExternal` input with no `limit maximumBytes` row.",
               "suggested": "Bound untrusted decoding: add `limit maximumBytes <n>` (and depth/element caps) so malformed input cannot exhaust memory (README §16)."},
    "SS3093": {"tier": "T1", "summary": "Float mixed with exact decimal/money math.",
               "found": "A decimal.* op with a Float operand, or a Float math.* op with a Decimal/Money operand.",
               "suggested": "Keep money/exact values in `Decimal`/`Money` and compute with `decimal.*`; never route them through binary Float arithmetic (README §10.6)."},
    "SS3094": {"tier": "T3", "summary": "Equality on Float operands.",
               "found": "A math.equal/notEqual on Float32/Float64 operands (NaN/epsilon footgun).",
               "suggested": "Compare floats within a tolerance, or use `Decimal`/`decimal.equal` for exact values (README §10.6)."},
    "SS5000": {"tier": "T3", "summary": "Primitive body in application source.",
               "found": "An app operation with a runtimeBinding/intrinsic body.",
               "suggested": "Move it to a .semsig-backed stdlib module (README §17 #50)."},
    "SS3041": {"tier": "T1", "summary": "Multiple `export c` rows on one operation.",
               "found": "An operation with more than one `export c` symbol.",
               "suggested": "Use a single `export c <symbol>` per op (README §30.4.2)."},
    "SS3042": {"tier": "T1", "summary": "`export c` symbol is not a C identifier.",
               "found": "An `export c` symbol with non-C-identifier characters.",
               "suggested": "Use [A-Za-z_][A-Za-z0-9_]* (README §30.4.2)."},
    "SS3043": {"tier": "T1", "summary": "Duplicate `export c` symbol.",
               "found": "Two operations exporting the same C symbol.",
               "suggested": "Export symbols must be unique (README §30.4.2)."},
    "SS0740": {"tier": "T1", "summary": "Invalid platform targetRuntime.",
               "found": "A platform targetRuntime other than native/wasm.",
               "suggested": "Use `native` or `wasm` (README §7)."},
    "SS3022": {"tier": "T0", "summary": "Cyclic module-storage initialization.",
               "found": "Module storage initializers forming a reference cycle.",
               "suggested": "Break the cycle; init is doc-order over a DAG (§30.2.1)."},
    "SS3021": {"tier": "T1", "summary": "Effectful module-storage initializer.",
               "found": "A module storage `value` referencing a call/operation.",
               "suggested": "Use a literal/constant/prior-storage initializer (§30.2.1)."},
    "SS3002": {"tier": "T0", "summary": "configure op declares a runtime effect.",
               "found": "A build-time `configure` op with a non-build.* effect.",
               "suggested": "configure is build-time; use only build.* (README §30.3.2)."},
    "SS2601": {"tier": "T1", "summary": "Unknown .semsig schema version.",
               "found": "A `semsig` header with an unsupported version.",
               "suggested": "Regenerate with a supported toolchain (README §26)."},
    "SS2805": {"tier": "T0", "summary": "Dependency requests an un-allowed effect.",
               "found": "A lock effectSurface effect with no matching build.sem allowEffect.",
               "suggested": "Add an `allowEffect`, or drop the dependency (§28.5)."},
    "SS2804": {"tier": "T0", "summary": "Dependency sha256 digest mismatch.",
               "found": "A resolved dependency's content hash != its lock digest.",
               "suggested": "Re-fetch the dependency; a mismatch is a tamper signal (§28.4)."},
    "SS1323": {"tier": "T0", "summary": "`join` before `start`.",
               "found": "A `join TASK` appearing before the task is started.",
               "suggested": "Start the task before joining it (README §15.5)."},
    "SS1324": {"tier": "T0", "summary": "Task `ifError` before `join`.",
               "found": "A `branch ifError TASK` before the task is joined.",
               "suggested": "Join the task before reading its error (README §13/§15.5)."},
    "SS1320": {"tier": "T0", "summary": "Started task never resolved.",
               "found": "A `start TASK` with no join/poll/cancel/detach.",
               "suggested": "Resolve the task before return (README §17 #20)."},
    "SS1321": {"tier": "T0", "summary": "`cancel` without a prior `start`.",
               "found": "A `cancel TASK` where TASK was never started.",
               "suggested": "Start the task before canceling it (README §17 #21)."},
    "SS1322": {"tier": "T0", "summary": "`ifCanceled` without a `cancel`.",
               "found": "A `branch ifCanceled TASK` where TASK is never canceled.",
               "suggested": "Add a `cancel TASK` (README §17 #22)."},
    "SS1190": {"tier": "T1", "summary": "console entry has `in` parameters.",
               "found": "A console entry operation that declares `in` rows.",
               "suggested": "Console entries take no params; use capabilities (README §11)."},
    "SS1191": {"tier": "T1", "summary": "console entry returns non-ExitCode.",
               "found": "A console entry whose `out` is not ExitCode/Int32.",
               "suggested": "Return ExitCode (alias for Int32) (README §11)."},
    "SS1140": {"tier": "T0", "summary": "`start` in a non-async operation.",
               "found": "A `start` step in an operation that is not `async yes`.",
               "suggested": "Mark the operation `async yes`, or use `do` (README §11)."},
    "SS1633": {"tier": "T0", "summary": "Legacy single-brace HTML hole.",
               "found": "A `{name}` hole in an HTML body.",
               "suggested": "Use double braces `{{name}}` (README §16)."},
    "SS1634": {"tier": "T0", "summary": "URL-attribute hole not HtmlSafeUrl.",
               "found": "A `{{hole}}` in href/src/... filled with a plain String.",
               "suggested": "Type the hole HtmlSafeUrl (README §16, §17 #34)."},
    "SS1635": {"tier": "T1", "summary": "render args do not match template holes.",
               "found": "An html.render whose hole args differ from the `{{holes}}`.",
               "suggested": "Provide exactly one arg per hole (README §17 #33)."},
    "SS3501": {"tier": "T3", "summary": "Fallible call with no error path.",
               "found": "A call with a `catch` but no `branch ifError` for it.",
               "suggested": "Add a `branch ifError CALL goto …`, or `discards` (README §17 #35)."},
    "SS1064": {"tier": "T1", "summary": "Inconsistent binding type across a merge.",
               "found": "A name is bound to incompatible types on different paths to a label.",
               "suggested": "Bind the same name/type on every predecessor path (README §13)."},
    "SS3710": {"tier": "T1", "summary": "Silent newtype coercion across an alias.",
               "found": "An arg type differs from the callee input but resolves to the same base.",
               "suggested": "Pass the alias newtype itself; aliases do not coerce (README §10)."},
    "SS3700": {"tier": "T1", "summary": "Dotted type outside an alias `for`.",
               "found": "A dotted type name in a let/arg/in/out/catch/field position.",
               "suggested": "Use a bare type, or a local alias `for importAlias.Type` (§7)."},
    "SS3900": {"tier": "T3", "summary": "owns without cleanedBy.",
               "found": "A call that owns a resource but declares no cleanedBy.",
               "suggested": "Add `cleanedBy <cleanup>` so the resource is released (§15)."},
    "SS3600": {"tier": "T3", "summary": "ifOut on a fallible call before its error.",
               "found": "An `ifOut` inspecting a call that has a catch.",
               "suggested": "Handle the error (branch ifError) before inspecting the out (§17 #36)."},
    "MD1013": {"tier": "T3", "summary": "Project entry is not exported.",
               "found": "An `entry` entity with no `exports` row.",
               "suggested": "Export the entry entity (README §7)."},
    "SS3201": {"tier": "T0", "summary": "Duplicate webServer route.",
               "found": "Two routes with the same METHOD + PATH.",
               "suggested": "Make each route's method+path unique (§17 #32)."},
    "SS3001": {"tier": "T4", "summary": "`branch else` not after a guard.",
               "found": "A `branch else` that doesn't follow a guard branch.",
               "suggested": "Use `branch else` only as the default after a guard (§17 #30/#31)."},
    "SS1901": {"tier": "T3", "summary": "sqlite column pointer used after step/reset invalidated it.",
               "found": "A `columnText`/`columnBlob`/`columnName` value used after a later step/reset on its statement.",
               "suggested": "Copy or consume the borrowed column value before advancing the statement (README §17 #23)."},
    "SS1902": {"tier": "T3", "summary": "Multi-write sqlite sequence without a transaction.",
               "found": "Two or more prepared+stepped INSERT/UPDATE/DELETE statements with no BEGIN/COMMIT.",
               "suggested": "Bracket multi-write sequences in a transaction (README §17 #24)."},
    "SS2502": {"tier": "T1", "summary": "Binding used before it is in scope.",
               "found": "A call result used before its `do`, or a catch var on the success path.",
               "suggested": "Reference the binding only after it is produced (README §25)."},
    "SS3390": {"tier": "T1", "summary": "Indirect-call arity mismatch.",
               "found": "An `invokes <binding>` with the wrong number of args for its operationType.",
               "suggested": "Pass exactly the operationType's input count (README §33.10)."},
    "SS3391": {"tier": "T1", "summary": "Indirect-call type mismatch.",
               "found": "An indirect call arg/out type that does not match its operationType.",
               "suggested": "Match the operationType input/output types (README §33.10)."},
    "SS3392": {"tier": "T3", "summary": "Operation-reference binding shadows an operation.",
               "found": "A local operationType binding whose name is also a module operation.",
               "suggested": "Rename the binding so `invokes` is unambiguous (README §33.10)."},
    "SS1029": {"tier": "T1", "summary": "Bare return into an alias needs exact type.",
               "found": "A return of a base/sibling type where the out is an alias newtype.",
               "suggested": "Return the alias type itself, or annotate via a typed binding (README §10)."},
    "SS3041C": {"tier": "T1", "summary": "Duplicate project constant.",
                "found": "Two `PROJECT constant` rows with the same name.",
                "suggested": "Use one constant per name (README §28.1)."},
    "SS3041D": {"tier": "T1", "summary": "Local binding shadows a project constant.",
                "found": "A `let` whose name matches a project constant.",
                "suggested": "Rename the local binding (no shadow, README §28.1)."},
    "SS3043": {"tier": "T1", "summary": "Gated configure operation.",
               "found": "A `configure` op carrying a forTarget/forPlatform gate.",
               "suggested": "configure runs once, ungated — remove the gate (README §30.3.2)."},
    "SS3042A": {"tier": "T1", "summary": "Override names an undeclared constant.",
                "found": "A platform `override` whose name is not a project constant.",
                "suggested": "Override only declared project constants (README §28.1)."},
    "SS3042B": {"tier": "T1", "summary": "Override value type mismatch.",
                "found": "A platform override value that does not match the constant's type.",
                "suggested": "Match the constant's declared type (README §28.1)."},
    "SS3044A": {"tier": "T1", "summary": "Owned handle aliased into a second binding.",
                "found": "A `let` initialized from an owned handle.",
                "suggested": "Keep one binding per owned handle (README §15.6)."},
    "SS3044B": {"tier": "T1", "summary": "Cleanup registered twice.",
                "found": "The same cleanup deferred more than once.",
                "suggested": "Defer each cleanup once (README §15.6)."},
    "SS3044C": {"tier": "T1", "summary": "Owned handle escapes via return.",
                "found": "A `return` of an owned handle.",
                "suggested": "Do not return owned handles in v0.3 (README §15.6)."},
    "SS3024": {"tier": "T1", "summary": "Island body kind/type mismatch.",
               "found": "A `body <kind>` that doesn't match the entity's declared type.",
               "suggested": "Match SqlText→sql, JsonText→json, HtmlTemplate→html (README §16)."},
    "SS3024J": {"tier": "T1", "summary": "Malformed json island.",
                "found": "A `body json` island whose content is not valid JSON.",
                "suggested": "Fix the JSON syntax (README §16)."},
    "SS3024Q": {"tier": "T1", "summary": "sql placeholder/arg-count mismatch.",
                "found": "A sql island whose `?` count differs from the call's param args.",
                "suggested": "One `?` per parameter arg (README §16)."},
    "SS3025": {"tier": "T1", "summary": "Trusted fragment minted off-boundary.",
               "found": "An HtmlTrustedFragment produced by a call other than html.trustFragment.",
               "suggested": "Mint trusted fragments only at html.trustFragment (README §16)."},
    "SS2601": {"tier": "T1", "summary": "Invalid webServer route method.",
               "found": "A route method outside GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS.",
               "suggested": "Use a bare standard HTTP method (README §14)."},
    "SS2602": {"tier": "T1", "summary": "Malformed webServer route parameter.",
               "found": "A `:` route segment whose name is not a valid identifier.",
               "suggested": "Write `:name` with an identifier, or `*` for the catch-all (README §14)."},
    "SS2603": {"tier": "T1", "summary": "webServer handler ABI mismatch.",
               "found": "A handler whose inputs/output don't match its role ABI.",
               "suggested": "Match the §14 handler ABI for its role (README §14)."},
    "MD1042": {"tier": "T1", "summary": "purpose payload must be a quoted string.",
               "found": "A `purpose` whose payload is not a quoted string.",
               "suggested": "Write `purpose \"…\"` (README §6)."},
    "MD1043": {"tier": "T1", "summary": "invariant payload must be a quoted string.",
               "found": "An `invariant` whose payload is not a quoted string.",
               "suggested": "Write `invariant \"…\"` (README §6)."},
    "MD1045": {"tier": "T1", "summary": "deprecated payload must be a quoted string.",
               "found": "A `deprecated` whose payload is not a quoted string.",
               "suggested": "Write `deprecated \"…\"` (README §6)."},
    "MD1044": {"tier": "T1", "summary": "tag payload must be a bare identifier.",
               "found": "A `tag` whose payload is quoted or not an identifier.",
               "suggested": "Write `tag someIdentifier` (README §6)."},
    "MD1047": {"tier": "T1", "summary": "owner payload must be a bare identifier.",
               "found": "An `owner` whose payload is quoted or not an identifier.",
               "suggested": "Write `owner someIdentifier` (README §6)."},
    "SS0744": {"tier": "T1", "summary": "Reserved target windowsGui is unspecified.",
               "found": "A project targeting `windowsGui` (GUI module not defined in v0.3).",
               "suggested": "Remove the windowsGui target until the GUI spec lands (README §27)."},
    "SS1085": {"tier": "T1", "summary": "out rebinds immutable module storage.",
               "found": "A call `out` targeting an `immutable` module storage entity.",
               "suggested": "Declare the storage `mutability mutable` (README §12)."},
    "SS1086": {"tier": "T3", "summary": "Module-storage mutation without a storage effect.",
               "found": "An out rebinds module storage but the op declares no `effect write storage.<name>`.",
               "suggested": "Add `effect write storage.<name>` + a covering capability (README §12)."},
    "SS1087": {"tier": "T1", "summary": "`set` targets a non-mutable.",
               "found": "A `set NAME VALUE` whose NAME is an immutable let, an unknown name, or non-mutable module storage.",
               "suggested": "Declare the target `let NAME mutable …` or `mutability mutable` (README §12)."},
    "SS1028": {"tier": "T1", "summary": "Bare variant outside a type-directed position.",
               "found": "An enum variant name used where the type is not statically known.",
               "suggested": "Use variants only in arg/let/return positions (README §10)."},
    "SS1354": {"tier": "T1", "summary": "`bind` on a payloadless variant.",
               "found": "A `branch ifVariant … bind` on a variant that carries no payload.",
               "suggested": "Drop `bind`, or match a data-carrying variant (README §17 #53)."},
    "SS1551": {"tier": "T1", "summary": "Import alias collides with a type name.",
               "found": "An `imports ALIAS …` where ALIAS equals a declared type name.",
               "suggested": "Rename the import alias (README §17 #51)."},
    "SS1552": {"tier": "T1", "summary": "Operation name collides with a builtin namespace.",
               "found": "An operation named compare/console/math.",
               "suggested": "Rename the operation (README §17 #51)."},
    "SS1353": {"tier": "T3", "summary": "Non-exhaustive ifVariant match.",
               "found": "A closed enum matched on a subset of variants with no default arm.",
               "suggested": "Cover every variant or end the series in a default transfer (README §17 #52)."},
    "SS1352": {"tier": "T1", "summary": "ifVariant names an unknown/ambiguous variant.",
               "found": "A `branch ifVariant … VARIANT` not resolvable to one enum.",
               "suggested": "Use a variant that belongs to exactly one enum (§10.5)."},
    "SS1340": {"tier": "T4", "summary": "ifValue/ifOut is comparison sugar.",
               "found": "A `branch ifValue`/`ifOut` guard.",
               "suggested": "Informational; fmt canonicalizes to compare + branch if (§13)."},
    "SS1544": {"tier": "T1", "summary": "cleanup worker out/no-catch needs discards.",
               "found": "A cleanup worker with an `out`, no `catch`, no `discards`.",
               "suggested": "Add `discards \"reason\"` to the worker (§17 #44)."},
    "SS1542": {"tier": "T1", "summary": "cleanup onFailure without a worker catch.",
               "found": "A cleanup `onFailure` whose worker call has no `catch`.",
               "suggested": "Add a `catch` to the worker, or drop onFailure (§17 #42)."},
    "SS1203": {"tier": "T1", "summary": "`let` forward-references a later binding.",
               "found": "A `let` initializer naming a `let` declared later.",
               "suggested": "Reorder so the referenced binding comes first (§12)."},
    "SS2551": {"tier": "T3", "summary": "Shared catch var with incompatible types.",
               "found": "A catch variable reused across calls with different error types.",
               "suggested": "Use distinct catch names, or a common error type (README §25)."},
    "SS1315": {"tier": "T3", "summary": "Irreducible control flow.",
               "found": "A multi-entry loop (CFG not T1-T2 reducible).",
               "suggested": "Restructure to a single-entry loop (README §17 #15)."},
    "SS1326": {"tier": "T1", "summary": "Dotted name in an internal reference.",
               "found": "A `do`/`start`/`defer` (etc.) target containing a dot.",
               "suggested": "Internal refs are bare; dots are external-path only (§3)."},
    "SS1519": {"tier": "T1", "summary": "Propagated error type mismatches the Result slot.",
               "found": "A propagating cleanup whose error type differs from the op's Result error.",
               "suggested": "Match the operation's Result error type (replace semantics, README §29 #2d)."},
    "SS1518": {"tier": "T1", "summary": "`onFailure propagate` with no Result to chain.",
               "found": "A propagating cleanup whose operation doesn't return Result.",
               "suggested": "Make the operation `out Result …`, or use logAndSuppress (§15.6)."},
    "SS1345": {"tier": "T1", "summary": "Ordering comparison on Bool/enum.",
               "found": "A compare.lessThan/greaterThan on a Bool or enum operand.",
               "suggested": "Bool/enum are equals-only; use equal/notEqual (README §17 #45)."},
    "SS3010": {"tier": "T1", "summary": "forTarget names an undeclared target.",
               "found": "A `forTarget X` where X is not a project target.",
               "suggested": "Use a target declared by the project (README §30.3.1)."},
    "SS3011": {"tier": "T1", "summary": "forPlatform names an undeclared platform.",
               "found": "A `forPlatform X` where X is not a declared platform entity.",
               "suggested": "Declare the platform, or fix the name (README §30.3.1)."},
    "SS1702": {"tier": "T0", "summary": "Call activated more than once.",
               "found": "A call reached by two `do`s, or `do`-activated and used as a cleanup worker.",
               "suggested": "Activate a call exactly once (README §17 #2/#43)."},
    "SS5400": {"tier": "T1", "summary": "`suppress` needs a `because` rationale.",
               "found": "A `suppress CODE` row with no `because`.",
               "suggested": "Write `suppress CODE because \"…\"` (README §30.6.2, §17 #54)."},
    "SS5402": {"tier": "T1", "summary": "`suppress` targets a deny-tier diagnostic.",
               "found": "A `suppress CODE` where CODE is tier T0/T1/T2 (soundness/UB/security/structural).",
               "suggested": "Deny-tier diagnostics are non-suppressible — fix the cause. Only advisory T3/T4 codes may be suppressed with a `because` (README §30.6.2)."},
    "SS5401": {"tier": "T1", "summary": "`suppress` names an unknown diagnostic code.",
               "found": "A `suppress CODE` where CODE is not in the registry.",
               "suggested": "Use a real code from `sem explain` (README §30.6.2)."},
})


def explain(code: str) -> dict:
    """Return the registry entry for a diagnostic code (README §29 #12)."""
    if code not in DIAGNOSTICS:
        raise EavError(f"unknown diagnostic code {code!r}")
    return DIAGNOSTICS[code]


@dataclass
class Diagnostic:
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    line: Optional[int] = None
    entity: Optional[str] = None

    def render(self) -> str:
        loc = f"line {self.line}: " if self.line is not None else ""
        return f"{self.severity.upper()} {self.code}: {loc}{self.message}"


def format_repair(code: str) -> str:
    """`Found / Suggested fix` repair text for a code (README §17 repair format)."""
    entry = explain(code)
    return (
        f"{code} ({entry['tier']}): {entry['summary']}\n"
        f"  Found:        {entry['found']}\n"
        f"  Suggested fix: {entry['suggested']}"
    )


# --------------------------------------------------------------------------
# 1. Lexer  (README ss2 — parse rules / lexical rules)
# --------------------------------------------------------------------------


def tokenize_line(text: str) -> list[str]:
    """Whitespace-tokenize one source line, honoring strings and comments.

    Rules implemented from README ss2:
      * A ``#`` outside a string starts a comment (full-line or trailing) and
        ends the row; a ``#`` inside ``"..."`` is a literal character.
      * ``"..."`` keeps its spaces and is returned as a single token *with* its
        surrounding quotes preserved, so the lowering can tell a string literal
        from a bare identifier.
      * Supported escapes inside strings: \\" \\\\ \\n \\t \\xNN. The escape
        ``\\r`` and ``\\0`` are rejected; ``\\u{...}`` is reserved-deferred.
      * Outside strings, runs of non-whitespace are tokens.

    The returned tokens are the row's payload tokens with comments stripped.
    """

    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t":
            i += 1
            continue
        if ch == "#":
            # Comment to end of line (we are outside a string here).
            break
        if ch == '"':
            # Consume a string literal, validating escapes.
            j = i + 1
            buf = ['"']
            closed = False
            while j < n:
                cj = text[j]
                if cj == "\\":
                    if j + 1 >= n:
                        raise EavError("dangling escape at end of string")
                    esc = text[j + 1]
                    if esc in '"\\nt':
                        buf.append("\\" + esc)
                        j += 2
                        continue
                    if esc == "x":
                        hexpart = text[j + 2 : j + 4]
                        if len(hexpart) != 2 or any(
                            c not in "0123456789abcdefABCDEF" for c in hexpart
                        ):
                            raise EavError(
                                r"\x escape needs exactly two hex digits"
                            )
                        buf.append("\\x" + hexpart)
                        j += 4
                        continue
                    if esc in "r0":
                        raise EavError(
                            rf"escape \{esc} is unsupported (README ss2)"
                        )
                    if esc == "u":
                        raise EavError(
                            r"\u{...} codepoint escapes are deferred to i18n "
                            r"(README ss2, ss29 #22)"
                        )
                    raise EavError(rf"unknown escape \{esc}")
                if cj == '"':
                    buf.append('"')
                    j += 1
                    closed = True
                    break
                buf.append(cj)
                j += 1
            if not closed:
                raise EavError("unterminated string literal")
            tokens.append("".join(buf))
            i = j
            continue
        # Bare token: run up to next whitespace, quote, or comment '#'.
        j = i
        while j < n and text[j] not in ' \t"#':
            j += 1
        bare = text[i:j]
        if "=" in bare:
            raise EavError(
                "`=` is not used in EAV-Steps; `let` rows are positional "
                "(`let NAME mutable|immutable TYPE VALUE`) (README ss2/ss12)"
            )
        tokens.append(bare)
        i = j
    return tokens


# --------------------------------------------------------------------------
# 2. Parser & row model  (README ss1 — core row model, ss5 — predicate table)
# --------------------------------------------------------------------------

# Entity kinds that may be introduced with `<name> is <kind>` (README ss2/ss5).
ENTITY_KINDS = {
    "project",
    "module",
    "capability",
    "error",
    "errorCase",
    "record",
    "enum",
    "alias",
    "operation",
    "function",  # normalized to operation (README ss11)
    "call",
    "task",
    "cleanup",
    "storage",
    "htmlTemplate",
    "webServer",
    "intrinsic",
    "platform",
    "operationType",
    "semsig",
}

# Step predicates valid in an operation's body (README ss5).
STEP_PREDICATES = {
    "do",
    "defer",
    "start",
    "join",
    "poll",
    "cancel",
    "detach",
    "branch",
    "return",
    "goto",
    "set",
}

# Island-introducing predicate: indentation after `body <kind>` is semantic
# (README ss2). `storage ... body sql` and `htmlTemplate ... body` are islands.
ISLAND_PREDICATE = "body"

# Internal identifier grammar (README ss2): camelCase, letter-first, no
# underscores/hyphens/leading digits.
_IDENT_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9]*\Z")

# Numeric literal grammar (README ss2/ss33.1). A single `_` may separate digits
# (no leading/trailing/doubled). Decimal rejects octal/0-prefixed forms.
_INT_DEC_RE = re.compile(r"(0|[1-9](_?[0-9])*)\Z")
_INT_HEX_RE = re.compile(r"0x[0-9a-fA-F](_?[0-9a-fA-F])*\Z")
_INT_BIN_RE = re.compile(r"0b[01](_?[01])*\Z")
# Float literal (README ss2): decimal float only; no leading/trailing dot.
_FLOAT_RE = re.compile(r"[0-9]+\.[0-9]+\Z")
# Duration literal (README ss2/ss30.1.2): reserved lexical class, no v0.3 use.
_DURATION_RE = re.compile(r"[0-9]+(ns|us|ms|s|m|h)\Z")


def is_duration_literal(tok: str) -> bool:
    return bool(_DURATION_RE.match(tok))


# Manifest-only token classes (README ss2/ss28): valid only in build.sem/
# build.sem.lock positions and a module's imports path; never as names.
_REPO_PATH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+\Z")
_SEMVER_RE = re.compile(
    r"v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?\Z"
)
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}\Z")


def is_repo_path(tok: str) -> bool:
    return bool(_REPO_PATH_RE.match(tok))


def is_semver(tok: str) -> bool:
    return bool(_SEMVER_RE.match(tok))


def is_sha256_digest(tok: str) -> bool:
    """True for the 64-lowercase-hex body of a `sha256 <hex>` digest token."""
    return bool(_SHA256_HEX_RE.match(tok))


def _parse_semver(v: str) -> tuple:
    """Sort key for a `v`-prefixed semver (README ss28.4). Release sorts above an
    otherwise-equal pre-release; build metadata is ignored for ordering."""
    if not v.startswith("v"):
        raise EavError(f"version {v!r} must be v-prefixed (README ss2)")
    core = v[1:].split("+", 1)[0]
    num, _, pre = core.partition("-")
    parts = num.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise EavError(f"malformed semver {v!r} (README ss2)")
    major, minor, patch = (int(p) for p in parts)
    pre_key = (1,) if pre == "" else (0, pre)  # release > pre-release
    return (major, minor, patch) + pre_key


def mvs_select(requirements: list) -> dict:
    """Minimal Version Selection (README ss28.4): pick the highest required
    version per module — no SAT/solver, just the max of the requirements."""
    best: dict = {}
    for name, ver in requirements:
        key = _parse_semver(ver)
        if name not in best or key > best[name][0]:
            best[name] = (key, ver)
    return {name: ver for name, (key, ver) in best.items()}


SEMSIG_SCHEMA_VERSIONS = {"1.0"}


_SEMSIG_LEGAL_KINDS = {
    "semsig", "intrinsic", "record", "enum", "alias", "error", "errorCase",
}


def load_project(root: str) -> str:
    """Project driver (README §28.2/§28.3): compose the runtime program of a
    project directory. The `project` entity lives in `build.sem` (the manifest,
    §7/§28), so it is prepended; the modules live under `src/` — every
    `src/**/*.sem` (recursively, so each submodule directory's root `main.sem`
    is included) that is not a `*.test.sem`. `build.sem.lock` and tests are not
    part of the runtime program. A flat `<root>/*.sem` layout (no `src/`, no
    `build.sem`) is still accepted for single-file demos."""
    import glob
    import os
    parts: list[str] = []
    build = os.path.join(root, "build.sem")
    if os.path.isfile(build):
        parts.append(open(build, encoding="utf-8").read())
    src_dir = os.path.join(root, "src")
    scan = src_dir if os.path.isdir(src_dir) else root
    files = sorted(
        f for f in glob.glob(os.path.join(scan, "**", "*.sem"), recursive=True)
        if classify_sem_file(f) == "source"
    )
    if not files and not parts:
        raise EavError(f"no source .sem files found under {scan!r} (README ss28.2)")
    parts.extend(open(f, encoding="utf-8").read() for f in files)
    return "\n".join(parts)


def golden_match(produced: str, golden_path: str, expected_digest: str = None,
                 update: bool = False) -> dict:
    """README §30.5.1 / §29 #6: compare produced output to a committed golden and
    verify its sha256. A mismatch fails (never updates implicitly); `update=True`
    rewrites the golden and re-pins the digest (opt-in `--update-golden`)."""
    import hashlib
    import os
    if update:
        os.makedirs(os.path.dirname(os.path.abspath(golden_path)), exist_ok=True)
        with open(golden_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(produced)
    if not os.path.exists(golden_path):
        return {"ok": False, "reason": "missing-golden", "digest": None}
    committed = open(golden_path, encoding="utf-8").read()
    digest = hashlib.sha256(committed.encode("utf-8")).hexdigest()
    content_match = produced == committed
    digest_match = expected_digest is None or digest == expected_digest
    return {"ok": content_match and digest_match, "digest": digest,
            "contentMatch": content_match, "digestMatch": digest_match}


def discover_project_tests(root: str) -> dict:
    """Locate tests by layout (README §28.7): co-located `src/*.test.sem` (unit/
    semantic) and `tests/` suites (integration/e2e), plus `tests/golden/` assets."""
    import glob
    import os
    src_dir = os.path.join(root, "src")
    co_located = sorted(glob.glob(os.path.join(
        src_dir if os.path.isdir(src_dir) else root, "*.test.sem")))
    tests_dir = sorted(glob.glob(os.path.join(root, "tests", "*.sem")))
    golden = sorted(glob.glob(os.path.join(root, "tests", "golden", "*"))) if os.path.isdir(
        os.path.join(root, "tests", "golden")) else []
    return {
        "coLocated": [os.path.relpath(f, root) for f in co_located],
        "testsDir": [os.path.relpath(f, root) for f in tests_dir],
        "golden": [os.path.relpath(f, root) for f in golden if os.path.isfile(f)],
    }


def app_layout_plan(app_dir: str) -> dict:
    """Plan the §28.8 relayout of a flat app into the framework layout: source +
    co-located tests under `src/`, the manifest at the root, output under
    `build/`. Returns the move map without touching the filesystem."""
    import glob
    import os
    moves = []
    for f in sorted(glob.glob(os.path.join(app_dir, "*.sem")) +
                    glob.glob(os.path.join(app_dir, "*.semsig"))):
        base = os.path.basename(f)
        role = classify_sem_file(f)
        dest = (base if role in ("build", "lock")
                else os.path.join("src", base))  # source/test/semsig -> src/
        moves.append({"from": base, "to": dest, "role": role})
    return {"app": os.path.basename(os.path.normpath(app_dir)),
            "moves": moves, "output": "build/"}


def _read_program_source(path: str) -> str:
    """Read a single file, or compose a project directory (WS3-046)."""
    import os
    if path != "-" and os.path.isdir(path):
        return load_project(path)
    return _read_source(path)


def classify_sem_file(path: str) -> str:
    """Role of a file in the `.sem` family (README §28.2): build / lock / semsig /
    test / source / other."""
    import os
    base = os.path.basename(path)
    if base == "build.sem":
        return "build"
    if base == "build.sem.lock":
        return "lock"
    if base.endswith(".semsig"):
        return "semsig"
    if base.endswith(".test.sem"):
        return "test"
    if base.endswith(".sem"):
        return "source"
    return "other"


def load_semsig(source: str) -> Program:
    """Parse a `.semsig` sidecar and validate its header (README ss26). An
    unknown schema `version` is rejected (SS2601)."""
    program = parse(source)
    headers = program.of_kind("semsig")
    if not headers:
        raise EavError("a .semsig file needs a `semsig` header entity (README ss26)")
    # README ss26 / WS4-006: a .semsig holds only intrinsic signatures + the
    # record/enum/alias/error types they reference (plus its header).
    for n in program.order:
        kind = program.entities[n].kind
        if kind not in _SEMSIG_LEGAL_KINDS:
            raise EavError(
                f".semsig may not contain a {kind!r} entity "
                f"({program.entities[n].name!r}); only intrinsic signatures and the "
                f"types they reference are legal (README ss26, WS4-006)",
                program.entities[n].line,
            )
    for sig in headers:
        ver = sig.fact("version")
        v = ver.payload[0].strip('"') if ver and ver.payload else None
        if v not in SEMSIG_SCHEMA_VERSIONS:
            raise EavError(
                f"semsig {sig.name!r} has unknown schema version {v!r}; supported: "
                f"{sorted(SEMSIG_SCHEMA_VERSIONS)} (README ss26)",
                code="SS2601",
            )
    return program


def semsig_targets(program: Program) -> dict:
    """Map intrinsic `target` -> intrinsic entity for a loaded .semsig."""
    out: dict = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "intrinsic":
            t = ent.fact("target")
            if t and t.payload:
                out[t.payload[0]] = ent
    return out


_TYPED_COMMENT_RE = re.compile(
    r"#\s*(rationale|warning|agent|memory|concurrency|timing|failure|security|"
    r"dependency|observability|test|todo|purpose|invariant|note|risk|example):\s*(.*)"
)


def typed_comments(source: str) -> list:
    """Extract typed comments `# tag: text` (README ss2). This is the §34
    direction for §6 metadata — metadata can migrate to typed comments and docs
    are still generated from them (X-014)."""
    out: list = []
    for line in source.replace("\r\n", "\n").split("\n"):
        m = _TYPED_COMMENT_RE.search(line)
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


def docs(semsig_program: Program) -> list:
    """Generate an API catalog from a loaded .semsig (README ss27 `sem docs`):
    one line per intrinsic — `target(arg:Type, …) -> Out [throws Err]` + purpose."""
    out: list[str] = []
    for n in semsig_program.order:
        ent = semsig_program.entities[n]
        if ent.kind != "intrinsic":
            continue
        tgt = ent.fact("target")
        target = tgt.payload[0] if tgt and tgt.payload else ent.name
        params = ", ".join(r.payload[-1] for r in ent.facts("arg") if r.payload)
        orow = ent.fact("out")
        ret = orow.payload[0] if orow and orow.payload else "Void"
        crow = ent.fact("catch")
        throws = f" throws {crow.payload[0]}" if crow and crow.payload else ""
        purpose = ent.fact("purpose")
        doc = f" — {purpose.payload[0].strip(chr(34))}" if purpose and purpose.payload else ""
        out.append(f"{target}({params}) -> {ret}{throws}{doc}")
    return out


def resolve_semsig(target: str, sigs: list):
    """Resolution order (README ss26): scan loaded .semsig Programs in order;
    the first that defines an intrinsic for `target` wins (first-target wins)."""
    for prog in sigs:
        if target in semsig_targets(prog):
            return prog
    return None


def build_empty_plan() -> dict:
    """`standard.build` BuildPlan (README ss30.3.2): build-time data assembled by
    the root module's `configure` op. Pure (no runtime effect)."""
    return {"targets": {}, "constants": {}}


def build_with_target(plan: dict, name: str, kind: str) -> dict:
    """Add/replace a BuildTarget by name (merge-by-name: a later target with the
    same name replaces the earlier one)."""
    out = {"targets": dict(plan["targets"]), "constants": dict(plan["constants"])}
    out["targets"][name] = kind
    return out


def build_with_constant(plan: dict, name: str, value) -> dict:
    out = {"targets": dict(plan["targets"]), "constants": dict(plan["constants"])}
    out["constants"][name] = value
    return out


def merge_native_links(program: Program, platform_name: str) -> dict:
    """Merge native-link rows for a platform (README ss28.1): project-level then
    platform-level `nativeLibrary`/`nativeHeader`/`nativeLinkFlag`, in order with
    duplicates removed (first occurrence wins); plus the platform `output`."""
    plat = program.entities.get(platform_name)
    if plat is None or plat.kind != "platform":
        raise EavError(f"{platform_name!r} is not a platform entity")
    projects = program.of_kind("project")

    def unq(t):
        return t[1:-1] if len(t) >= 2 and t[0] == '"' and t[-1] == '"' else t

    def collect(pred):
        seen: list = []
        for src in projects + [plat]:
            for r in src.facts(pred):
                if r.payload and unq(r.payload[0]) not in seen:
                    seen.append(unq(r.payload[0]))
        return seen

    out = plat.fact("output")
    return {
        "output": unq(out.payload[0]) if out and out.payload else None,
        "libraries": collect("nativeLibrary"),
        "headers": collect("nativeHeader"),
        "linkFlags": collect("nativeLinkFlag"),
    }


def module_path_for(root_module: str, reldir: str) -> str:
    """A submodule's import path = the project root module + its relative
    directory segments (README ss28.3)."""
    parts = [p for p in reldir.replace("\\", "/").split("/") if p]
    return ".".join([root_module] + parts)


def internal_import_allowed(importer_path: str, target_path: str) -> bool:
    """`internal/` visibility (README ss28.3): a module path with an `internal`
    segment is importable only by modules under the parent of that `internal`
    boundary. Returns False for an out-of-tree leak."""
    segs = target_path.split(".")
    if "internal" not in segs:
        return True
    parent = ".".join(segs[: segs.index("internal")])
    return importer_path == parent or importer_path.startswith(parent + ".")


def mod_tidy(build_program: Program) -> str:
    """Generate a `build.sem.lock` from a `build.sem` manifest (README ss28.4):
    MVS-resolved requires (with content digests), toolchainResolved, and the
    effectSurface from allowEffect. Deterministic — `tidy(x) == tidy(x)`."""
    projects = build_program.of_kind("project")
    if not projects:
        raise EavError("no `project` entity in build.sem")
    proj = projects[0]
    selected = mvs_select([
        (r.payload[0], r.payload[1]) for r in proj.facts("require")
        if len(r.payload) >= 2
    ])
    lines = [f"{proj.name} is project"]
    tc = proj.fact("toolchain")
    if tc and tc.payload:
        lines.append(f"{proj.name} toolchainResolved {tc.payload[0]}")
    for repo in sorted(selected):
        ver = selected[repo]
        digest = sha256_hex(f"{repo}@{ver}".encode("utf-8"))  # deterministic stub
        lines.append(f"{proj.name} resolved {repo} {ver} sha256 {digest}")
    for r in proj.facts("allowEffect"):
        if len(r.payload) >= 2:
            lines.append(f"{proj.name} effectSurface {r.payload[0]} {r.payload[1]}")
    return "\n".join(lines) + "\n"


def verify_supply_chain(build_program: Program, lock_program: Program) -> None:
    """Supply-chain allowlist (README ss28.5): every effect in the resolved
    `effectSurface` (lock) must be permitted by an `allowEffect` row (build.sem).
    An un-allowed effect is refused (SS2805)."""
    builds = build_program.of_kind("project")
    locks = lock_program.of_kind("project")
    allowed = {
        (r.payload[0], r.payload[1])
        for proj in builds for r in proj.facts("allowEffect")
        if len(r.payload) >= 2
    }
    surface = [
        (r.payload[0], r.payload[1])
        for proj in locks for r in proj.facts("effectSurface")
        if len(r.payload) >= 2
    ]
    violations = [eff for eff in surface if eff not in allowed]
    if violations:
        raise EavError(
            f"dependency effect surface requests un-allowed effects {violations} "
            f"(not in build.sem allowEffect, README ss28.5)",
            code="SS2805",
        )


def sha256_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def embed_literal_source(path: str, expected_digest: str = None) -> bytes:
    """Compile-time asset embedding (README ss30.3.2): read the file's bytes and,
    if a `literalDigest` is given, verify its sha256 (a mismatch is a hard error)."""
    with open(path, "rb") as fh:
        data = fh.read()
    if expected_digest is not None:
        verify_digest(data, expected_digest)
    return data


def verify_digest(data: bytes, expected_hex: str) -> None:
    """Content-addressed integrity (README ss28.4): a digest mismatch is a hard
    error (tampered dependency)."""
    actual = sha256_hex(data)
    if actual != expected_hex:
        raise EavError(
            f"sha256 digest mismatch: expected {expected_hex}, got {actual} "
            f"(tampered dependency, README ss28.4)",
            code="SS2804",
        )


def _validate_int_literal(tok: str, line: int) -> None:
    """Validate an integer literal token (README ss2/ss33.1). Caller has already
    decided `tok` is a literal attempt (digit-led, no `.`, no sign)."""
    if tok.startswith("0x") or tok.startswith("0b"):
        rx = _INT_HEX_RE if tok[1] == "x" else _INT_BIN_RE
        if not rx.match(tok):
            raise EavError(f"malformed integer literal {tok!r} (README ss33.1)", line)
        return
    if not _INT_DEC_RE.match(tok):
        raise EavError(
            f"malformed integer literal {tok!r}: no octal/0-prefix, no "
            f"leading/trailing/doubled `_` (README ss2)",
            line,
        )

# Reserved words (README ss2). May not be used as entity, variable, or type
# names. Arg-slot/field/variant *labels* are payload tokens and are exempt
# (they are never validated against this set).
RESERVED_WORDS = {
    # literals
    "nil", "true", "false",
    # core syntax
    "is", "at",
    # step predicates and guards
    "do", "defer", "start", "join", "poll", "cancel", "detach", "branch",
    "return", "goto", "set", "if", "ifFalse", "ifOut", "ifValue", "ifVariant",
    "ifError", "ifReady", "ifPending", "ifCanceled", "else", "onFailure",
    "equals", "notEquals", "greaterThan", "lessThan", "bind",
    "propagate", "logAndSuppress", "because",
    # mutability and declaration tokens
    "immutable", "mutable", "yes", "no",
    # entity kind names
    "project", "module", "capability", "error", "errorCase", "record", "enum",
    "alias", "operation", "function", "call", "task", "cleanup", "storage",
    "htmlTemplate", "webServer", "intrinsic", "platform", "operationType",
    "semsig",
    # structural predicate tokens
    "in", "out", "effect", "uses", "memory", "async", "let", "label",
    "field", "variant", "repr", "for", "of", "path", "imports", "exports",
    "scope", "type", "mutability", "value", "body", "literalSource",
    "literalDigest", "grants", "invokes", "arg", "discards", "catch",
    "purpose", "invariant", "note", "rationale", "risk", "example", "tag",
    "deprecated", "owner", "target", "owns", "cleanedBy", "cleans",
    "borrows", "lifetime", "mayEscape",  # WS1-111 borrowed-view rows
    "consumes", "takesOwnership",         # WS1-113 ownership-transfer rows
    "typeTrust",                           # X-070 trust label on a type
    "limit",                               # X-077 decode-limit row
    "trustConstraint", "using", "mode", "forTarget", "forPlatform", "suppress",
    "version", "generatedBy", "describes",
    # manifest predicate tokens
    "languageVersion", "toolchain", "require", "replace", "allowEffect",
    "constant", "configure", "nativeLibrary", "nativeHeader", "nativeLinkFlag",
    "os", "arch", "targetRuntime", "output", "override",
    # generated lock predicate tokens
    "resolved", "toolchainResolved", "effectSurface",
    # interop annotation tokens
    "export", "c",
    # primitive type names
    "Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64",
    "Float32", "Float64", "Bool", "String", "Void", "Byte", "Result",
}

# Universal metadata predicates (README ss6) + universal ss30 declaration
# predicates, valid on every entity kind.
UNIVERSAL_PREDICATES = {
    "purpose", "invariant", "note", "rationale", "risk", "example", "tag",
    "deprecated", "owner", "forTarget", "forPlatform", "suppress",
}

# Structural + step predicates allowed per entity kind (README ss5). `is` is
# implicit (handled before dispatch); `at` labeled steps are operation-only and
# handled separately. Unknown predicate for a kind is a hard parse error.
ALLOWED_PREDICATES: dict[str, set[str]] = {
    "project": {
        "module", "target", "entry", "mode", "languageVersion", "toolchain",
        "require", "replace", "allowEffect", "platform", "constant", "configure",
        "nativeLibrary", "nativeHeader", "nativeLinkFlag",
        "resolved", "toolchainResolved", "effectSurface",
    },
    "module": {"path", "imports", "exports"},
    "capability": {"grants"},
    "error": {"typeTrust"},
    "errorCase": {"of", "payload"},
    "record": {"field", "typeTrust"},
    "enum": {"variant", "repr", "typeTrust"},
    "alias": {"for", "typeTrust"},
    "operation": {
        "in", "out", "effect", "uses", "memory", "async", "label", "let",
        "body", "export",
        "do", "defer", "start", "join", "poll", "cancel", "detach",
        "branch", "return", "goto", "set", "trustConstraint",
    },
    "function": {
        "in", "out", "effect", "uses", "memory", "async", "label", "let",
        "body", "export",
        "do", "defer", "start", "join", "poll", "cancel", "detach",
        "branch", "return", "goto", "set",
    },
    "call": {
        "in", "invokes", "arg", "out", "catch", "discards", "owns",
        "cleanedBy", "effect", "async",  # async = tolerated-deprecated (ss5)
        "borrows", "lifetime", "mayEscape",  # WS1-111 borrowed-view rows
        "takesOwnership",                     # WS1-113 ownership transfer
        "limit",                              # X-077 decode limits
    },
    "task": {
        "in", "invokes", "arg", "out", "catch", "discards", "owns",
        "cleanedBy", "effect",
        "borrows", "lifetime", "mayEscape",  # WS1-111 borrowed-view rows
        "takesOwnership",                     # WS1-113 ownership transfer
        "limit",                              # X-077 decode limits
    },
    "cleanup": {"in", "call", "onFailure", "because", "cleans"},
    "storage": {
        "scope", "type", "mutability", "value", "body", "literalSource",
        "literalDigest",
    },
    "htmlTemplate": {"body"},
    "webServer": {
        "host", "port", "startup", "shutdown", "notFound", "methodNotAllowed",
        "route", "middleware",
    },
    "platform": {
        "os", "arch", "targetRuntime", "output", "override",
        "nativeLibrary", "nativeHeader", "nativeLinkFlag",
    },
    "intrinsic": {"target", "arg", "out", "catch", "async", "owns", "trustConstraint"},
    "semsig": {"version", "generatedBy", "describes"},
    "operationType": {"in", "out"},
}


@dataclass
class Row:
    subject: str
    predicate: str
    payload: list[str]
    line: int
    label: Optional[str] = None  # set for `at LABEL <stepPred> ...` rows


@dataclass
class Entity:
    name: str
    kind: str
    line: int
    rows: list[Row] = field(default_factory=list)

    def facts(self, predicate: str) -> list[Row]:
        return [r for r in self.rows if r.predicate == predicate and r.label is None]

    def fact(self, predicate: str) -> Optional[Row]:
        rows = self.facts(predicate)
        return rows[0] if rows else None


@dataclass
class Program:
    entities: dict[str, Entity] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    islands: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def add(self, entity: Entity) -> None:
        self.entities[entity.name] = entity
        self.order.append(entity.name)

    def of_kind(self, kind: str) -> list[Entity]:
        norm = "operation" if kind == "operation" else kind
        out = []
        for name in self.order:
            ent = self.entities[name]
            k = "operation" if ent.kind == "function" else ent.kind
            if k == norm:
                out.append(ent)
        return out


# Inclusive integer ranges per primitive width (README ss10/ss33.6).
_INT_RANGES = {
    "Int8": (-128, 127), "UInt8": (0, 255),
    "Int16": (-32768, 32767), "UInt16": (0, 65535),
    "Int32": (-2147483648, 2147483647), "UInt32": (0, 4294967295),
    "ExitCode": (-2147483648, 2147483647),
    "Int64": (-(2 ** 63), 2 ** 63 - 1), "UInt64": (0, 2 ** 64 - 1),
}


def _resolve_alias(type_name: str, alias_map: dict) -> str:
    seen: set = set()
    while type_name in alias_map and type_name not in seen:
        seen.add(type_name)
        type_name = alias_map[type_name]
    return _norm_type(type_name)


def _validate_value_literal(
    tok: str, line: int, type_name: str = None, alias_map: dict = None
) -> None:
    """Validate a `let`/`arg` value token if it is a numeric literal attempt.

    Identifiers (binding refs), strings, bool/enum tokens are skipped. A token
    led by a digit is an integer literal (README ss2/ss33.1); when the annotated
    type is an integer primitive, the literal is range-checked (README ss33.6)."""
    if not tok:
        return
    core = tok
    if tok[0] == "-":
        # Negative literal `-N`/`-N.N` (README ss2). No space after `-` (a bare
        # `-` token means the author wrote `- 42`); digits must follow the sign.
        core = tok[1:]
        if not core or not core[0].isdigit():
            raise EavError(
                f"malformed negative literal {tok!r}: write `-N`/`-N.N` with no "
                f"space after `-` and digits after the sign (README ss2)",
                line,
            )
    if is_duration_literal(core):
        raise EavError(
            f"duration literal {tok!r} is a reserved lexical class with no v0.3 "
            f"use (README ss2/ss30.1.2)",
            line,
        )
    if core[0].isdigit():
        if "." in core:
            if not _FLOAT_RE.match(core):
                raise EavError(
                    f"malformed float literal {tok!r}: use [0-9]+.[0-9]+, no "
                    f"trailing dot (README ss2)",
                    line,
                )
        else:
            _validate_int_literal(core, line)
            if type_name is not None:
                resolved = _resolve_alias(type_name, alias_map or {})
                rng = _INT_RANGES.get(resolved)
                if rng is not None:
                    value = _parse_int_literal_value(tok)
                    if not (rng[0] <= value <= rng[1]):
                        raise EavError(
                            f"integer literal {tok!r} is out of range for {resolved} "
                            f"[{rng[0]}, {rng[1]}] (README ss33.6)",
                            line,
                        )
    elif core[0] == ".":
        raise EavError(
            f"malformed float literal {tok!r}: no leading dot (README ss2)", line
        )


def _check_unique_labels(ent: Entity, predicate: str, what: str, cite: str) -> None:
    seen: set[str] = set()
    for row in ent.facts(predicate):
        if not row.payload:
            continue
        name = row.payload[0]
        if name in seen:
            raise EavError(
                f"duplicate {what} {name!r} in {ent.kind} {ent.name!r} ({cite})",
                row.line,
            )
        seen.add(name)


# Reserved words with no §5 predicate home yet — reserved for a future version
# (the drift guard tolerates exactly these; anything else unhomed is a failure).
RESERVED_FUTURE = {"using"}


def token_sync_drift() -> set:
    """X-005 drift guard (README §2↔§5↔§22↔§30.7): every reserved word must have
    a home — a literal/value, a core token, a guard/comparator sub-keyword, an
    entity kind, a primitive type, or a predicate in some §5/§6/§22 set. Returns
    the set of unsynced reserved words (excluding the documented future set)."""
    literals = {"nil", "true", "false", "yes", "no"}
    core = {"is", "at"}
    guards = {
        "if", "ifFalse", "ifOut", "ifValue", "ifVariant", "ifError", "ifReady",
        "ifPending", "ifCanceled", "else", "onFailure", "equals", "notEquals",
        "greaterThan", "lessThan", "bind", "propagate", "logAndSuppress",
        "because", "immutable", "mutable",
        "consumes",  # WS1-113 ownership-transfer sub-keyword on an `arg` row tail
    }
    interop = {"export", "c"}
    homed = set()
    homed |= literals | core | guards | interop
    homed |= ENTITY_KINDS | PRIMITIVE_TYPES | {"Result"}
    homed |= UNIVERSAL_PREDICATES | set(_META_PREDS) | set(_GATE_PREDS)
    for preds in ALLOWED_PREDICATES.values():
        homed |= preds
    return RESERVED_WORDS - homed - RESERVED_FUTURE


# HTML hole analysis (README ss16). URL-bearing attributes require HtmlSafeUrl.
_HTML_URL_ATTRS = ("href", "src", "action", "formaction", "poster")
_HTML_HOLE_RE = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")
_HTML_LEGACY_RE = re.compile(r"(?<!\{)\{[A-Za-z_][\w.]*\}(?!\})")


def html_holes(text: str) -> list:
    """Extract `{{name}}` / `{{rec.field}}` holes from an HTML body, flagging
    those inside a URL-bearing attribute (README ss16). Raises on a legacy
    single-brace hole (a breaking error, not a migration warning)."""
    if _HTML_LEGACY_RE.search(text):
        m = _HTML_LEGACY_RE.search(text)
        raise EavError(
            f"legacy single-brace hole {m.group(0)!r}; use double braces "
            f"{{{{{m.group(0)[1:-1]}}}}} (README ss16)",
            code="SS1633",
        )
    holes = []
    for m in _HTML_HOLE_RE.finditer(text):
        before = text[max(0, m.start() - 60):m.start()]
        am = re.search(r'(\w+)\s*=\s*["\'][^"\']*$', before)
        is_url = bool(am and am.group(1).lower() in _HTML_URL_ATTRS)
        holes.append((m.group(1), is_url))
    return holes


def _predicate_allowed(kind: str, predicate: str) -> bool:
    if predicate in UNIVERSAL_PREDICATES:
        return True
    return predicate in ALLOWED_PREDICATES.get(kind, set())


def _leading_spaces(raw: str) -> int:
    n = 0
    for ch in raw:
        if ch == " ":
            n += 1
        elif ch == "\t":
            raise EavError("island indentation must be spaces, not tabs (README ss2)")
        else:
            break
    return n


def parse(source_text: str) -> Program:
    """Parse EAV-Steps source into a Program (README ss1, ss5).

    Enforces the structural invariants needed to lower safely:
      * Every entity's first row is its `is` row (README ss1, ss17 #1).
      * No duplicate `is` row for one entity (README ss17 #1).
      * `<kind>` after `is` is a known entity kind (README ss5).
      * Column-1 subject + column-2 predicate; `at` introduces a labeled step
        whose label is column 3 and step predicate column 4+ (README ss1).
    """

    program = Program()
    # README ss33.2: UTF-8 with no BOM; CRLF/CR normalize to LF.
    if source_text.startswith("﻿"):
        source_text = source_text[1:]
    raw_lines = source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    i = 0
    n = len(raw_lines)
    current_kind_of: dict[str, str] = {}
    while i < n:
        raw = raw_lines[i]
        lineno = i + 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        tokens = tokenize_line(raw)
        if not tokens:
            i += 1
            continue
        if len(tokens) < 2:
            raise EavError(
                f"row needs at least a subject and predicate, got {tokens!r}",
                lineno,
            )

        subject, predicate = tokens[0], tokens[1]
        payload = tokens[2:]

        # Entity row: `<name> is <kind>`
        if predicate == "is":
            if not payload:
                raise EavError("`is` row needs a kind", lineno)
            kind = payload[0]
            if kind not in ENTITY_KINDS:
                raise EavError(f"unknown entity kind {kind!r} (README ss5)", lineno)
            # README ss11 / WS1-027: `function` is an alias for `operation`.
            # Normalize at parse so downstream sees a single kind and reuses the
            # operation predicate set, metadata table, and lints.
            if kind == "function":
                kind = "operation"
            if subject in RESERVED_WORDS:
                raise EavError(
                    f"reserved word {subject!r} may not be an entity name "
                    f"(README ss2); arg-slot/field/variant labels are exempt",
                    lineno, code="SS0003",
                )
            if not _IDENT_RE.match(subject):
                raise EavError(
                    f"invalid entity name {subject!r}: names are "
                    f"[a-zA-Z][a-zA-Z0-9]* — no underscores, hyphens, or leading "
                    f"digits (README ss2)",
                    lineno, code="SS0002",
                )
            if subject in program.entities:
                raise EavError(
                    f"duplicate `is` row for entity {subject!r} (README ss17 #1)",
                    lineno,
                )
            program.add(Entity(name=subject, kind=kind, line=lineno))
            current_kind_of[subject] = kind
            # README ss12: single-line module-storage form, consistent with the
            # one-line `let NAME MUTABILITY TYPE VALUE`. Extra tokens on the
            # `is storage` row — `NAME is storage <scope> <mutability> <type>
            # [value...]` — populate the scope/mutability/type/value facts so a
            # constant is one row, not five. The verbose multi-row form (each
            # `NAME scope/type/mutability/value` on its own line) stays valid.
            if kind == "storage" and len(payload) > 1:
                inline = payload[1:]
                ent = program.entities[subject]
                slots = ("scope", "mutability", "type")
                for idx, slot_pred in enumerate(slots):
                    if idx < len(inline):
                        ent.rows.append(Row(subject, slot_pred, [inline[idx]], lineno))
                if len(inline) > 3:
                    ent.rows.append(Row(subject, "value", inline[3:], lineno))
            i += 1
            continue

        # Any non-`is` row requires the subject's `is` row to have come first.
        if subject not in program.entities:
            raise EavError(
                f"first row for entity {subject!r} must be its `is` row "
                f"(README ss1, ss17 #1); saw predicate {predicate!r} first",
                lineno,
            )

        entity = program.entities[subject]

        # Labeled step row: `<op> at <label> <stepPred> <payload...>`
        if predicate == "at":
            if entity.kind not in ("operation", "function"):
                raise EavError(
                    f"`at` labeled steps are only valid on operations, not a "
                    f"{entity.kind} entity (README ss1/ss5)",
                    lineno,
                )
            if len(payload) < 2:
                raise EavError(
                    "`at` row needs a label and a step predicate (README ss1)",
                    lineno,
                )
            label = payload[0]
            step_pred = payload[1]
            if step_pred not in ALLOWED_PREDICATES[entity.kind]:
                raise EavError(
                    f"step predicate {step_pred!r} is not valid for an "
                    f"operation (README ss5)",
                    lineno,
                )
            entity.rows.append(
                Row(subject, step_pred, payload[2:], lineno, label=label)
            )
            i += 1
            continue

        # Per-kind predicate dispatch (README ss5, ss17 #22): a predicate must be
        # in the kind's structural/step set or be a universal metadata predicate.
        if not _predicate_allowed(entity.kind, predicate):
            raise EavError(
                f"predicate {predicate!r} is not valid for a {entity.kind} "
                f"entity (README ss5)",
                lineno,
            )

        # Island body: `body <kind>` followed by indented lines (README ss2).
        if predicate == ISLAND_PREDICATE and entity.kind in ("storage", "htmlTemplate"):
            island_kind = payload[0] if payload else ""
            body_lines: list[str] = []
            j = i + 1
            while j < n:
                nxt = raw_lines[j]
                if not nxt.strip():
                    body_lines.append("")
                    j += 1
                    continue
                if _leading_spaces(nxt) > 0:
                    body_lines.append(nxt)
                    j += 1
                    continue
                break
            # Common-prefix strip.
            indented = [b for b in body_lines if b.strip()]
            if indented:
                common = min(_leading_spaces(b) for b in indented)
                body_lines = [b[common:] if b.strip() else "" for b in body_lines]
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            program.islands[(subject, island_kind)] = body_lines
            entity.rows.append(Row(subject, predicate, payload, lineno))
            i = j
            continue

        entity.rows.append(Row(subject, predicate, payload, lineno))
        i += 1

    _validate_program(program)
    return program


# Formatter ordering (README ss22). Metadata + universal gate rows sort after an
# entity's structural rows; entities sort by kind then document order.
_META_PREDS = (
    "purpose", "invariant", "note", "rationale", "risk", "example", "tag",
    "deprecated", "owner",
)
_GATE_PREDS = ("forTarget", "forPlatform", "suppress")
_KIND_ORDER = [
    "project", "module", "capability", "error", "errorCase", "alias", "record",
    "enum", "operationType", "storage", "htmlTemplate", "webServer", "operation",
    "function", "call", "task", "cleanup", "intrinsic", "platform", "semsig",
]


def _emit_rows(ent: Entity, row: Row, program: Program) -> list:
    """Render one row to source line(s), preserving island bodies indented
    (README ss22; never de-indent an island — the known fmt bug, WS4-005).
    Sugar lowering (WS4-003): `branch else … target L` canonicalizes to `goto L`."""
    pred, payload = row.predicate, row.payload
    if pred == "branch" and payload and payload[0] == "else":
        target = payload[payload.index("target") + 1] if "target" in payload else payload[-1]
        pred, payload = "goto", [target]
    if row.label is not None:
        return [f"{ent.name} at {row.label} {pred} {' '.join(payload)}".rstrip()]
    line = f"{ent.name} {pred} {' '.join(payload)}".rstrip()
    if pred == "body" and ent.kind in ("storage", "htmlTemplate"):
        island_kind = payload[0] if payload else ""
        island = program.islands.get((ent.name, island_kind))
        if island is not None:
            return [line] + [("    " + b if b else "") for b in island]
    return [line]


def format_entity(ent: Entity, program: Program) -> str:
    is_op = ent.kind in ("operation", "function")
    # WS4-003 sugar: a `call` with an `async` row promotes to `task` on fmt.
    promote_task = ent.kind == "call" and ent.fact("async") is not None
    emit_kind = "task" if promote_task else ent.kind
    meta, gate, body, decl = [], [], [], []
    for r in ent.rows:
        if promote_task and r.predicate == "async":
            continue  # dropped on promotion to task
        if r.label is not None or (is_op and r.predicate in STEP_PREDICATES) or (
            is_op and r.predicate == "let"
        ):
            body.append(r)
        elif r.predicate in _META_PREDS:
            meta.append(r)
        elif r.predicate in _GATE_PREDS:
            gate.append(r)
        else:
            decl.append(r)
    meta.sort(key=lambda r: (_META_PREDS.index(r.predicate),))  # stable within
    lines = [f"{ent.name} is {emit_kind}"]
    for group in (decl, meta, body, gate):
        for r in group:
            lines.extend(_emit_rows(ent, r, program))
    return "\n".join(lines)


def format_program(program: Program) -> str:
    """Canonicalize a parsed Program to EAV text (README ss22). Deterministic and
    idempotent: `format(parse(format(parse(x)))) == format(parse(x))`."""
    ordered = sorted(
        program.order,
        key=lambda n: (_kind_rank(program.entities[n].kind), program.order.index(n)),
    )
    blocks = [format_entity(program.entities[n], program) for n in ordered]
    return "\n\n".join(blocks).rstrip() + "\n"


def _kind_rank(kind: str) -> int:
    k = "operation" if kind == "function" else kind
    return _KIND_ORDER.index(k) if k in _KIND_ORDER else len(_KIND_ORDER)


# README ss23: the compact authoring profile. Within an operation block the
# subject token is omitted; `operation`/`call`/`task` headers re-anchor it.
COMPACT_HEADERS = {"operation", "call", "task"}
COMPACT_GUARDS = {
    "if", "ifFalse", "ifOut", "ifValue", "ifVariant", "ifError", "ifReady",
    "ifPending", "ifCanceled", "else",
}


def _expand_compact_row(subj: str, toks: list) -> list:
    """Expand one compact bare row (subject elided) to canonical EAV row(s)
    (README ss23 equivalence table)."""
    pred, rest = toks[0], toks[1:]
    if pred in COMPACT_GUARDS:
        # `ifError CALL goto L` -> `SUBJ branch ifError CALL goto L`, etc.
        return [f"{subj} branch {pred} {' '.join(rest)}".rstrip()]
    if pred == "effect" and "using" in rest:
        # `effect ACT RES using CAP` -> effect row + uses row.
        ui = rest.index("using")
        out = [f"{subj} effect {' '.join(rest[:ui])}".rstrip()]
        cap = rest[ui + 1:]
        if cap:
            out.append(f"{subj} uses {' '.join(cap)}")
        return out
    return [f"{subj} {pred} {' '.join(rest)}".rstrip()]


def expand_compact_to_eav(source: str):
    """Expand the compact authoring profile to canonical EAV text (README ss23).

    Returns ``(eav_text, line_map)`` where ``line_map[k]`` is the original
    (1-based) compact line number that produced canonical line ``k`` — the
    source map used to point lint diagnostics back at the author's line
    (WS2-004)."""
    src = source.replace("\r\n", "\n").replace("\r", "\n")
    if src.startswith("﻿"):
        src = src[1:]
    lines = src.split("\n")
    out: list = []
    origin: list = []
    declared: dict = {}
    implicit_op = None
    implicit_subj = None
    in_island = False

    def emit(text: str, ln: int) -> None:
        out.append(text)
        origin.append(ln)

    for idx, raw in enumerate(lines):
        ln = idx + 1
        stripped = raw.strip()
        if in_island and raw[:1] in (" ", "\t"):
            emit(raw, ln)
            continue
        if not stripped or stripped.startswith("#"):
            emit(stripped, ln)
            continue
        in_island = False
        toks = tokenize_line(raw)
        if len(toks) >= 2 and toks[1] == "is":
            kind = toks[2] if len(toks) > 2 else ""
            declared[toks[0]] = kind
            implicit_subj = toks[0]
            if kind in ("operation", "function"):
                implicit_op = toks[0]
            emit(stripped, ln)
            continue
        head = toks[0]
        if head in COMPACT_HEADERS and len(toks) >= 2:
            name = toks[1]
            kind = "operation" if head == "function" else head
            declared[name] = kind
            emit(f"{name} is {head}", ln)
            if head in ("operation", "function"):
                implicit_op = name
            else:
                if implicit_op:
                    emit(f"{name} in {implicit_op}", ln)
                if len(toks) > 2:
                    emit(f"{name} invokes {toks[2]}", ln)
            implicit_subj = name
            continue
        if head in declared:
            emit(stripped, ln)
            if len(toks) >= 2 and toks[1] == "body":
                in_island = True
            continue
        if implicit_subj is None:
            emit(stripped, ln)  # nothing to anchor — let the parser report it
            continue
        for line in _expand_compact_row(implicit_subj, toks):
            emit(line, ln)
    return "\n".join(out), origin


def parse_compact(source: str) -> "Program":
    """Parse compact-profile source by expanding to canonical EAV first."""
    return parse(expand_compact_to_eav(source)[0])


def lint_compact(source: str) -> list:
    """Lint compact-profile source, remapping each diagnostic's line back to the
    author's original compact line via the expansion source map (WS2-004)."""
    eav_text, line_map = expand_compact_to_eav(source)
    program = parse(eav_text)
    diags = lint(program)
    for d in diags:
        if d.line is not None and 1 <= d.line <= len(line_map):
            d.line = line_map[d.line - 1]
    return diags


def _compact_op_block(op: "Entity", program: "Program", children: dict) -> str:
    """Emit one operation as a compact block (subject elided, child call/task
    entities folded in after the steps)."""
    header = "function" if op.kind == "function" else "operation"
    lines = [f"{header} {op.name}"]
    for raw in format_entity(op, program).split("\n")[1:]:
        # drop the leading `NAME ` subject from each canonical row
        lines.append(raw[len(op.name) + 1:] if raw.startswith(op.name + " ") else raw)
    for cn in children.get(op.name, []):
        call = program.entities[cn]
        inv = call.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        kind = "task" if call.kind == "task" else "call"
        lines.append("")
        lines.append(f"{kind} {call.name} {target}".rstrip())
        for raw in format_entity(call, program).split("\n")[1:]:
            body = raw[len(call.name) + 1:] if raw.startswith(call.name + " ") else raw
            if body.startswith("in ") or body.startswith("invokes "):
                continue  # folded into the header
            lines.append(body)
    return "\n".join(lines)


def format_compact(program: "Program") -> str:
    """Emit a program in the compact authoring profile (README ss23). Non-op
    entities stay canonical (compact elides only op/call/task subjects)."""
    children: dict = {}
    for n in program.order:
        e = program.entities[n]
        if e.kind in ("call", "task"):
            owner = e.fact("in")
            if owner and owner.payload:
                children.setdefault(owner.payload[0], []).append(n)
    ordered = sorted(
        program.order,
        key=lambda n: (_kind_rank(program.entities[n].kind), program.order.index(n)),
    )
    folded = {c for kids in children.values() for c in kids}
    blocks: list = []
    for n in ordered:
        e = program.entities[n]
        if e.name in folded:
            continue
        if e.kind in ("operation", "function"):
            blocks.append(_compact_op_block(e, program, children))
        else:
            blocks.append(format_entity(e, program))
    return "\n\n".join(blocks).rstrip() + "\n"


def trace(program: Program, op_name: str) -> list:
    """Simulate the primary (document-order) path through an operation, tracking
    live bindings and defers up to the first return (README ss24 `trace`)."""
    op = program.entities.get(op_name)
    if op is None or op.kind not in ("operation", "function"):
        raise EavError(f"{op_name!r} is not an operation")
    live: set = {r.payload[0] for r in op.facts("in") if r.payload}
    defers: list = []
    lines: list[str] = []
    for row in op.rows:
        if row.label is not None:
            lines.append(f"at {row.label}:")
        pred, p = row.predicate, row.payload
        if pred == "let" and p:
            live.add(p[0])
            lines.append(f"  let {p[0]}  | live: {sorted(live)}")
        elif pred == "do" and p:
            call = program.entities.get(p[0])
            out = call.fact("out") if call else None
            if out and out.payload:
                live.add(out.payload[0])
                lines.append(f"  do {p[0]} -> {out.payload[0]}  | live: {sorted(live)}")
            else:
                lines.append(f"  do {p[0]}")
        elif pred == "defer" and p:
            defers.append(p[0])
            lines.append(f"  defer {p[0]}  | defers: {defers}")
        elif pred == "branch":
            lines.append(f"  branch {' '.join(p)} (fallthrough simulated)")
        elif pred == "goto" and p:
            lines.append(f"  goto {p[0]}")
        elif pred == "return":
            lines.append(f"  return {' '.join(p)}  | defers run (reverse): {defers[::-1]}")
            break
    return lines


def _logical_row_count(program: Program) -> int:
    """Total EAV rows (one `is` row + each fact/step row per entity)."""
    return sum(1 + len(program.entities[n].rows) for n in program.order)


def normalize_preview(source: str) -> dict:
    """Preview normalizing a program to canonical EAV (README ss21/ss24): row
    count, whether formatting would change the bytes, and the gate-0 round-trip
    check (entity set + per-entity row counts preserved through fmt)."""
    program = parse(source)
    formatted = format_program(program)
    reparsed = parse(formatted)
    # fmt reorders entities by kind, so compare the entity *set* and per-entity
    # row counts, not the document order.
    preserved = (
        set(program.order) == set(reparsed.order)
        and all(
            len(program.entities[n].rows) == len(reparsed.entities[n].rows)
            for n in program.order
        )
    )
    return {
        "rowCount": _logical_row_count(program),
        "formattedRowCount": _logical_row_count(reparsed),
        "rowDelta": _logical_row_count(reparsed) - _logical_row_count(program),
        "changed": formatted.strip() != source.strip(),
        "roundTripPreserved": preserved,
    }


def verify_patch(source: str) -> dict:
    """Verify an (edited) program is sound (README ss24 `verify-patch`): it must
    parse (structural hard-errors), lint without error-severity diagnostics, and
    — for a console target — lower to LLVM IR. Returns a structured report."""
    report = {"ok": False, "parsed": False, "lintErrors": [], "lowerable": None,
              "error": None}
    try:
        program = parse(source)
    except EavError as exc:
        report["error"] = str(exc)
        return report
    report["parsed"] = True
    diags = lint(program)
    report["lintErrors"] = [d.render() for d in diags if d.severity == "error"]
    try:
        lower_to_llvm(program)
        report["lowerable"] = True
    except EavError as exc:
        # Non-console targets are intentionally out of scope, not a patch failure.
        report["lowerable"] = False
        report["lowerNote"] = str(exc)
    report["ok"] = not report["lintErrors"]
    return report


def semantic_diff(old: Program, new: Program) -> list:
    """Semantic (not line) diff between two programs: entities added/removed and
    per-operation effect/out changes (README ss24 `diff`)."""
    out: list[str] = []
    old_names, new_names = set(old.order), set(new.order)
    for n in sorted(new_names - old_names):
        out.append(f"+ {new.entities[n].kind} {n}")
    for n in sorted(old_names - new_names):
        out.append(f"- {old.entities[n].kind} {n}")

    def effects(prog, n):
        return {tuple(e.payload[:2]) for e in prog.entities[n].facts("effect")
                if len(e.payload) >= 2}

    def out_sig(prog, n):
        r = prog.entities[n].fact("out")
        return tuple(r.payload) if r and r.payload else ()

    for n in sorted(old_names & new_names):
        if old.entities[n].kind != new.entities[n].kind:
            out.append(f"~ {n}: kind {old.entities[n].kind} -> {new.entities[n].kind}")
            continue
        if old.entities[n].kind in ("operation", "function"):
            ae, be = effects(old, n), effects(new, n)
            for e in sorted(be - ae):
                out.append(f"~ {n}: +effect {' '.join(e)}")
            for e in sorted(ae - be):
                out.append(f"~ {n}: -effect {' '.join(e)}")
            if out_sig(old, n) != out_sig(new, n):
                out.append(f"~ {n}: out {out_sig(old, n)} -> {out_sig(new, n)}")
    return out


def describe(program: Program, name: str) -> str:
    """A human/agent summary of an entity's contract (README ss24 `explain`)."""
    ent = program.entities.get(name)
    if ent is None:
        raise EavError(f"no entity named {name!r}")
    lines = [f"{ent.name} : {ent.kind}"]
    purpose = ent.fact("purpose")
    if purpose and purpose.payload:
        lines.append(f"  purpose  {' '.join(purpose.payload)}")
    for inv in ent.facts("invariant"):
        lines.append(f"  invariant {' '.join(inv.payload)}")
    for pred in ("in", "out", "effect", "uses", "invokes", "arg", "catch", "owns",
                 "cleanedBy", "grants", "field", "variant", "of", "for"):
        for r in ent.facts(pred):
            lines.append(f"  {pred} {' '.join(r.payload)}".rstrip())
    if ent.kind in ("operation", "function"):
        steps = [r for r in ent.rows if r.label is not None or r.predicate in STEP_PREDICATES]
        labels = [r.label for r in ent.rows if r.label is not None]
        lines.append(f"  steps {len(steps)}; labels {labels}")
    return "\n".join(lines)


GRAPH_KINDS = ("calls", "control")


def _call_graph_edges(program: Program) -> list:
    """(callerOp, calleeOp) edges via each op's activated user-op calls."""
    edges: list = []
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        for row in op.rows:
            if row.predicate in ("do", "start") and row.payload:
                call = program.entities.get(row.payload[0])
                if call and call.kind in ("call", "task"):
                    inv = call.fact("invokes")
                    if inv and inv.payload and "." not in inv.payload[0]:
                        callee = program.entities.get(inv.payload[0])
                        if callee and callee.kind in ("operation", "function"):
                            edges.append((op.name, callee.name))
    return edges


def _op_cfg(op: Entity) -> dict:
    """Build the control-flow graph of an operation: nodes are `entry` + each
    label; edges from goto/branch targets and fallthrough."""
    blocks: list = [["entry", []]]
    for row in op.rows:
        if row.label is not None:
            blocks.append([row.label, []])
        if row.label is not None or row.predicate in STEP_PREDICATES:
            blocks[-1][1].append(row)
    cfg: dict = {}
    for i, (name, steps) in enumerate(blocks):
        succ: set = set()
        terminated = False
        for s in steps:
            if s.predicate == "goto" and s.payload:
                succ.add(s.payload[0]); terminated = True; break
            if s.predicate == "return":
                terminated = True; break
            if s.predicate == "branch" and "goto" in s.payload:
                gi = s.payload.index("goto")
                if gi + 1 < len(s.payload):
                    succ.add(s.payload[gi + 1])
        if not terminated and i + 1 < len(blocks):
            succ.add(blocks[i + 1][0])
        cfg[name] = succ
    return cfg


def _is_reducible(cfg: dict, entry: str = "entry") -> bool:
    """T1-T2 interval reduction (README ss13): a CFG is reducible iff it collapses
    to a single node by removing self-loops and merging single-predecessor nodes."""
    known = set(cfg)
    succ = {n: set(cfg[n]) & known for n in cfg}
    nodes = set(succ)
    changed = True
    while changed and len(nodes) > 1:
        changed = False
        for n in nodes:
            if n in succ[n]:
                succ[n].discard(n); changed = True
        preds = {n: set() for n in nodes}
        for n in nodes:
            for s in succ[n]:
                if s in preds:
                    preds[s].add(n)
        for n in list(nodes):
            if n == entry or n not in nodes:
                continue
            if len(preds[n]) == 1:
                p = next(iter(preds[n]))
                if p == n:
                    continue
                succ[p].discard(n)
                succ[p] |= (succ[n] - {n})
                del succ[n]; nodes.discard(n); changed = True
                break
    return len(nodes) == 1


def _lint_variant_exhaustiveness(program: Program) -> list:
    """README ss13 / ss17 #52: a contiguous series of `branch ifVariant VALUE
    VARIANT …` rows over one value is the match. If a closed enum value is
    matched but not every variant is covered, the series must end in a default
    transfer (`goto`/`return`/`branch else`) or fall through to a default arm;
    a series that instead falls straight into a labeled arm — leaving the
    unmatched variants unhandled — warns SS1353."""
    diags: list = []
    enum_variants: dict = {
        e.name: [v.payload[0] for v in e.facts("variant") if v.payload]
        for e in program.of_kind("enum")
    }
    # variant-name -> set of enums declaring it (for resolution)
    owner: dict = {}
    for ename, vs in enum_variants.items():
        for v in vs:
            owner.setdefault(v, set()).add(ename)

    def is_ifvariant(row) -> bool:
        return row.predicate == "branch" and row.payload and row.payload[0] == "ifVariant"

    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        rows = op.rows
        i = 0
        while i < len(rows):
            if not is_ifvariant(rows[i]) or len(rows[i].payload) < 3:
                i += 1
                continue
            value = rows[i].payload[1]
            j = i
            covered: list = []
            while (j < len(rows) and is_ifvariant(rows[j])
                   and len(rows[j].payload) >= 3 and rows[j].payload[1] == value):
                covered.append(rows[j].payload[2])
                j += 1
            # resolve the enum from the matched variants (all must share one enum)
            enums = set.intersection(*(owner.get(v, set()) for v in covered)) if covered else set()
            if len(enums) == 1:
                ename = next(iter(enums))
                all_vs = set(enum_variants[ename])
                if not all_vs.issubset(set(covered)):
                    nxt = rows[j] if j < len(rows) else None
                    has_default = (
                        nxt is not None
                        and nxt.label is None
                        and not (nxt.predicate == "branch" and nxt.payload
                                 and nxt.payload[0] == "ifVariant"
                                 and len(nxt.payload) >= 2 and nxt.payload[1] == value)
                    )
                    if not has_default:
                        missing = sorted(all_vs - set(covered))
                        diags.append(Diagnostic(
                            "SS1353", "warning",
                            f"`ifVariant` series over {value!r} in {op.name!r} does "
                            f"not cover {ename} variant(s) {missing} and has no "
                            f"default transfer/arm (README ss17 #52)",
                            rows[i].line, op.name))
            i = j
    return diags


def _sqlite_kind(target: str):
    """Classify a sqlite.* call target for usage linting (README ss19/ss26)."""
    if not target.startswith("sqlite."):
        return None
    name = target[len("sqlite."):]
    if name.startswith("column") or name in ("step", "next"):
        return "read"
    if name in ("exec", "execute", "run", "insert", "update", "delete", "writeRow"):
        return "write"
    if name in ("beginTransaction", "begin", "transaction", "savepoint"):
        return "txn"
    return None


def _row_refs(row, owned: dict) -> list:
    """Value names a step row reads: a `do`/`join` call's argument values, plus
    return values and branch conditions."""
    p = row.payload
    refs: list = []
    if row.predicate in ("do", "start", "join", "poll") and p:
        call = owned.get(p[0])
        if call:
            refs += [a.payload[2] for a in call.facts("arg") if len(a.payload) >= 3]
    elif row.predicate == "return":
        refs += [t for t in p if t not in ("value", "ok", "error", "nil", "void")]
    elif row.predicate == "branch" and p:
        g = p[0]
        if g in ("if", "ifFalse", "ifVariant") and len(p) >= 2:
            refs.append(p[1])
        elif g in ("ifValue", "ifOut") and len(p) >= 4:
            refs += [p[1], p[3]]
    return refs


# SQL statement classes, read from a `body sql` island's first verb (README
# ss19). Only INSERT/UPDATE/DELETE/REPLACE are row-mutating writes; CREATE/SELECT
# and the transaction verbs are not. Mirrors semsc's _SQL_WRITE_STATEMENT_VERBS.
_SQL_WRITE_VERBS = frozenset({"INSERT", "UPDATE", "DELETE", "REPLACE"})
_SQL_BEGIN_VERBS = frozenset({"BEGIN", "SAVEPOINT"})
_SQL_COMMIT_VERBS = frozenset({"COMMIT", "RELEASE"})
# A live columnText/columnBlob/columnName pointer is SQLite-owned and invalidated
# by step/reset on the SAME statement; sibling column reads do NOT invalidate it
# (semsc _COLUMN_TEXT_INVALIDATORS / _OWNED_COLUMN_SOURCES).
_OWNED_COLUMN_TARGETS = frozenset({
    "sqlite.columnText", "sqlite.columnBlob", "sqlite.columnName",
})
_COLUMN_INVALIDATOR_TARGETS = frozenset({
    "sqlite.stepStatement", "sqlite.resetStatement",
})
_SQLITE_TXN_BEGIN_TARGETS = frozenset({
    "sqlite.beginTransaction", "sqlite.beginImmediateTransaction",
})
_SQLITE_TXN_COMMIT_TARGETS = frozenset({
    "sqlite.commitTransaction",
})


def _sql_first_verb(sql_text: str):
    """The leading SQL keyword (uppercased), skipping `--`/`/* */` comments and
    whitespace. Port of semsc's _sql_first_verb_lint."""
    i, n = 0, len(sql_text)
    while i < n:
        ch = sql_text[i]
        if ch.isspace():
            i += 1
            continue
        if sql_text.startswith("--", i):
            nl = sql_text.find("\n", i + 2)
            if nl == -1:
                return None
            i = nl + 1
            continue
        if sql_text.startswith("/*", i):
            end = sql_text.find("*/", i + 2)
            if end == -1:
                return None
            i = end + 2
            continue
        if ch.isalpha():
            s = i
            while i < n and (sql_text[i].isalpha() or sql_text[i] == "_"):
                i += 1
            return sql_text[s:i].upper()
        return None
    return None


def _lint_sqlite_usage(program: Program) -> list:
    """README ss19 / ss17 #23/#24, aligned with semsc's SS3113/SS3635:

    SS1901 - a `columnText`/`columnBlob`/`columnName` value points into
    SQLite-owned memory that a later `step`/`reset` on the SAME statement
    invalidates. Flag the value used as a call argument that follows such an
    invalidation. Sibling column reads do not invalidate, and copied scalars
    (`columnInt64` etc.) are never tracked.

    SS1902 - an operation that prepares and steps two or more row-mutating
    statements (INSERT/UPDATE/DELETE/REPLACE) must make the transaction boundary
    visible (a begin/commit call pair, or `sqlite.exec` of BEGIN.../COMMIT...)."""
    diags: list = []

    def target_of(call):
        inv = call.fact("invokes")
        return inv.payload[0] if inv and inv.payload else ""

    def sql_text_of(call):
        for a in call.facts("arg"):
            if len(a.payload) >= 3 and a.payload[0] == "sql":
                body = program.islands.get((a.payload[2], "sql"))
                if body is not None:
                    return "\n".join(body)
        return None

    def stmt_arg(call):
        for a in call.facts("arg"):
            if len(a.payload) >= 3 and a.payload[1] == "SqliteStatement":
                return a.payload[2]
        return None

    def out_names(call):
        return [o.payload[0] for o in call.facts("out") if o.payload]

    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        owned = {
            program.entities[c].name: program.entities[c]
            for c in program.order
            if program.entities[c].kind in ("call", "task")
            and (program.entities[c].fact("in") or Row("", "", [], 0)).payload[:1] == [op.name]
        }

        # ---- SS1902: multi-write transaction boundary ----
        write_steps = 0
        has_begin = has_commit = False
        for call in owned.values():
            tgt = target_of(call)
            if tgt in _SQLITE_TXN_BEGIN_TARGETS:
                has_begin = True
                continue
            if tgt in _SQLITE_TXN_COMMIT_TARGETS:
                has_commit = True
                continue
            if tgt == "sqlite.prepareStatement":
                verb = _sql_first_verb(sql_text_of(call) or "")
                if verb in _SQL_WRITE_VERBS:
                    produced = set(out_names(call))
                    stepped = any(
                        target_of(s) == "sqlite.stepStatement"
                        and stmt_arg(s) in produced
                        for s in owned.values())
                    if stepped:
                        write_steps += 1
            elif tgt == "sqlite.exec":
                verb = _sql_first_verb(sql_text_of(call) or "")
                if verb in _SQL_BEGIN_VERBS:
                    has_begin = True
                elif verb in _SQL_COMMIT_VERBS:
                    has_commit = True
        if write_steps >= 2 and not (has_begin and has_commit):
            diags.append(Diagnostic(
                "SS1902", "warning",
                f"{write_steps} row-mutating sqlite statements in {op.name!r} with no "
                f"wrapping transaction; bracket multi-write sequences in BEGIN/COMMIT "
                f"so a later failure cannot leave partial state (README ss17 #24)",
                op.line, op.name))

        # ---- SS1901: column borrow use-after-invalidation ----
        produced: dict = {}        # value name -> (owning statement, produce line)
        invalidations: list = []   # (owning statement, invalidation line)
        label_lines = [r.line for r in op.rows if r.predicate == "at"]
        for row in op.rows:
            if row.predicate not in ("do", "start", "join", "poll") or not row.payload:
                continue
            call = owned.get(row.payload[0])
            if call is None:
                continue
            tgt = target_of(call)
            if tgt in _OWNED_COLUMN_TARGETS:
                for nm in out_names(call):
                    produced[nm] = (stmt_arg(call), row.line)
            if tgt in _COLUMN_INVALIDATOR_TARGETS:
                invalidations.append((stmt_arg(call), row.line))
        if produced and invalidations:
            for row in op.rows:
                if row.predicate not in ("do", "start", "join", "poll") or not row.payload:
                    continue
                call = owned.get(row.payload[0])
                if call is None:
                    continue
                use_line = row.line
                for a in call.facts("arg"):
                    if len(a.payload) < 3 or a.payload[2] not in produced:
                        continue
                    val = a.payload[2]
                    own_stmt, prod_line = produced[val]
                    for inv_stmt, inv_line in invalidations:
                        if not (prod_line < inv_line < use_line):
                            continue
                        if (inv_stmt is not None and own_stmt is not None
                                and inv_stmt != own_stmt):
                            continue
                        if any(inv_line < ln < use_line for ln in label_lines):
                            continue  # a label may put them on different paths
                        diags.append(Diagnostic(
                            "SS1901", "warning",
                            f"sqlite column value {val!r} in {op.name!r} is used after a "
                            f"later step/reset on the same statement invalidated it; copy "
                            f"or consume it before advancing (README ss17 #23)",
                            prod_line, op.name))
                        break
    return diags


def _lint_loop_no_progress(program: Program) -> list:
    """X-100 / README §13, §33.3: a best-effort divergence lint. A back-edge loop
    that provably makes no progress toward an exit warns: either it has no exit
    path at all (no `return`, no branch/goto leaving the loop), or its exit
    guard value is never recomputed/mutated inside the loop body (a loop-invariant
    guard). Halting is undecidable, so this catches only the common footguns and
    never warns when an exit guard is recomputed (e.g. a counting loop)."""
    diags: list = []
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        rows = op.rows
        labels = {r.label: i for i, r in enumerate(rows) if r.label is not None}
        if not labels:
            continue
        owned = {
            program.entities[c].name: program.entities[c]
            for c in program.order
            if program.entities[c].kind in ("call", "task")
            and (program.entities[c].fact("in") or Row("", "", [], 0)).payload[:1] == [op.name]
        }
        for gi, r in enumerate(rows):
            # identify a back-edge: goto/branch-goto to a label at an earlier row
            tgt = None
            if r.predicate == "goto" and r.payload:
                tgt = r.payload[0]
            elif r.predicate == "branch" and len(r.payload) >= 4 and r.payload[2] == "goto":
                tgt = r.payload[3]
            li = labels.get(tgt) if tgt is not None else None
            if li is None or li >= gi:
                continue  # forward edge or unknown target -> not a loop back-edge
            has_return = False
            exit_conds: list = []      # guard value per exit branch (None = unconditional)
            recomputed: set = set()    # values (re)bound/mutated inside the loop body
            for j in range(li, gi + 1):
                rj = rows[j]
                if rj.predicate == "return":
                    has_return = True
                if rj.predicate in ("do", "start", "join", "poll") and rj.payload:
                    call = owned.get(rj.payload[0])
                    if call is not None:
                        for o in call.facts("out"):
                            if o.payload:
                                recomputed.add(o.payload[0])
                if rj.predicate == "set" and rj.payload:
                    recomputed.add(rj.payload[0])
                # an exit is a branch/goto (other than this back-edge) leaving [li, gi]
                t2 = None
                if rj.predicate == "goto" and j != gi and rj.payload:
                    t2 = (rj.payload[0], None)
                elif rj.predicate == "branch" and len(rj.payload) >= 4 and rj.payload[2] == "goto":
                    guard = rj.payload[1] if rj.payload[0] == "if" else None
                    t2 = (rj.payload[3], guard)
                if t2 is not None:
                    ti = labels.get(t2[0])
                    if ti is None or ti < li or ti > gi:
                        exit_conds.append(t2[1])
            if has_return:
                continue
            if not exit_conds:
                diags.append(Diagnostic(
                    "SS0950", "warning",
                    f"loop at {tgt!r} in {op.name!r} has no exit path (no return, no "
                    f"branch/goto leaving the loop) — likely an infinite loop "
                    f"(README §13/§33.3)",
                    rows[li].line, op.name))
                continue
            # exits exist; the loop progresses if any exit is unconditional or its
            # guard is recomputed inside the body. Otherwise the guard is invariant.
            if not any(c is None or c in recomputed for c in exit_conds):
                guards = sorted({c for c in exit_conds if c})
                diags.append(Diagnostic(
                    "SS0950", "warning",
                    f"loop at {tgt!r} in {op.name!r} makes no progress: its exit "
                    f"guard {guards} is never recomputed or mutated in the loop body "
                    f"(README §13/§33.3)",
                    rows[li].line, op.name))
    return diags


def _control_edges(program: Program) -> list:
    """(op, fromLabel|entry, toLabel) control-flow edges from goto/branch."""
    edges: list = []
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        current = "entry"
        for row in op.rows:
            if row.label is not None:
                current = row.label
            if row.predicate == "goto" and row.payload:
                edges.append((op.name, current, row.payload[0]))
            elif row.predicate == "branch" and len(row.payload) >= 4 and row.payload[2] == "goto":
                edges.append((op.name, current, row.payload[3]))
    return edges


def graph(program: Program, kind: str, fmt: str = "dot") -> str:
    """Emit a `calls` or `control` graph as DOT or mermaid (README ss24)."""
    if kind == "calls":
        edges = [(a, b) for a, b in _call_graph_edges(program)]
        pairs = [(a, b) for a, b in edges]
    elif kind == "control":
        pairs = [(f"{op}:{src}", f"{op}:{dst}") for op, src, dst in _control_edges(program)]
    else:
        raise EavError(f"unknown graph kind {kind!r}")
    if fmt == "mermaid":
        body = "\n".join(f"  {a} --> {b}" for a, b in pairs)
        return f"graph TD\n{body}\n"
    body = "\n".join(f'  "{a}" -> "{b}";' for a, b in pairs)
    return f"digraph {kind} {{\n{body}\n}}\n"


SCAFFOLD_PATTERNS = ("console-program", "fallible-write")


def scaffold(pattern: str) -> str:
    """Emit a canonical, ready-to-edit EAV program for a pattern (README ss24).
    The output parses, lints clean, and (where runnable) JIT-executes."""
    if pattern == "console-program":
        return (
            "Scaffold is project\nScaffold module scaffoldModule\n"
            "Scaffold target console\nScaffold entry main\n\n"
            "scaffoldModule is module\nscaffoldModule path examples.scaffold\n"
            "scaffoldModule exports main\n"
            'scaffoldModule purpose "Scaffolded console program"\n'
            'scaffoldModule invariant "main is the only entry operation"\n\n'
            "ExitCode is alias\nExitCode for Int32\n\n"
            "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n\n"
            "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
            "main uses stdoutWriter\nmain memory heap no\nmain async no\n"
            'main purpose "Write a line and exit 0"\n'
            'main invariant "Always returns 0"\n'
            'main let greeting immutable String "edit me"\n'
            "main let okCode immutable ExitCode 0\n"
            "main do writeGreeting\nmain return okCode\n\n"
            "writeGreeting is call\nwriteGreeting in main\n"
            "writeGreeting invokes console.writeLine\n"
            "writeGreeting arg text String greeting\n"
        )
    if pattern == "fallible-write":
        return (
            "Scaffold is project\nScaffold module scaffoldModule\n"
            "Scaffold target console\nScaffold entry main\n\n"
            "scaffoldModule is module\nscaffoldModule path examples.scaffold\n"
            "scaffoldModule exports main\n"
            'scaffoldModule purpose "Scaffolded fallible-write program"\n'
            'scaffoldModule invariant "Handles the write failure path"\n\n'
            "ExitCode is alias\nExitCode for Int32\n\n"
            "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n\n"
            "ConsoleWriteError is error\n\n"
            "WriteFailed is errorCase\nWriteFailed of ConsoleWriteError\n"
            "WriteFailed payload Int32\n\n"
            "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
            "main uses stdoutWriter\nmain memory heap no\nmain async no\n"
            'main purpose "Write a line; return 1 on failure"\n'
            'main invariant "Returns 1 on any write failure"\n'
            'main let greeting immutable String "edit me"\n'
            "main let okCode immutable ExitCode 0\n"
            "main let failCode immutable ExitCode 1\n"
            "main do writeGreeting\n"
            "main branch ifError writeGreeting goto failed\n"
            "main return okCode\n"
            "main at failed return failCode\n\n"
            "writeGreeting is call\nwriteGreeting in main\n"
            "writeGreeting invokes console.writeLine\n"
            "writeGreeting arg text String greeting\n"
            "writeGreeting catch writeError ConsoleWriteError\n"
        )
    raise EavError(f"unknown scaffold pattern {pattern!r}")


QUERY_DIMENSIONS = (
    "effects", "uses", "labels", "calls", "types", "ownership-leaked",
)


def query(program: Program, dimension: str) -> list:
    """Answer a structural query over a program (README ss24 `query`)."""
    rows: list[str] = []
    for name in program.order:
        ent = program.entities[name]
        if dimension == "effects" and ent.kind in ("operation", "function"):
            for e in ent.facts("effect"):
                if len(e.payload) >= 2:
                    rows.append(f"{ent.name} {e.payload[0]} {e.payload[1]}")
        elif dimension == "uses" and ent.kind in ("operation", "function"):
            for u in ent.facts("uses"):
                if u.payload:
                    rows.append(f"{ent.name} {u.payload[0]}")
        elif dimension == "labels" and ent.kind in ("operation", "function"):
            for r in ent.rows:
                if r.label is not None:
                    rows.append(f"{ent.name} {r.label}")
        elif dimension == "calls" and ent.kind in ("call", "task"):
            inv = ent.fact("invokes")
            rows.append(f"{ent.name} {inv.payload[0] if inv and inv.payload else '?'}")
        elif dimension == "types" and ent.kind in ("record", "enum", "alias"):
            rows.append(f"{ent.kind} {ent.name}")
        elif dimension == "ownership-leaked" and ent.kind in ("call", "task"):
            if ent.fact("owns") is not None and ent.fact("cleanedBy") is None:
                rows.append(f"{ent.name} owns without cleanedBy")
    return rows


def rename_entity(source: str, old: str, new: str) -> str:
    """Semantic rename (README ss24 `rename`): rename an entity and every bare
    reference to it, returning canonical EAV. Rejects an unknown source or a
    collision with an existing name."""
    if not _IDENT_RE.match(new) or new in RESERVED_WORDS:
        raise EavError(f"invalid new name {new!r} (README ss2)")
    program = parse(source)
    if old not in program.entities:
        raise EavError(f"no entity named {old!r} to rename")
    if new in program.entities:
        raise EavError(f"rename target {new!r} already exists (collision)")
    for n in program.order:
        ent = program.entities[n]
        for row in ent.rows:
            row.payload = [new if t == old else t for t in row.payload]
            if row.label == old:
                row.label = new
    ent = program.entities.pop(old)
    ent.name = new
    program.entities[new] = ent
    program.order = [new if n == old else n for n in program.order]
    out = format_program(program)
    parse(out)  # the rename must still parse (validity preserved)
    return out


def add_operation(source: str, name: str, out_type: str = "ExitCode") -> str:
    """Structured edit (README ss24 `add`): append a minimal, valid operation
    with a validated signature, returning canonical EAV."""
    if not _IDENT_RE.match(name) or name in RESERVED_WORDS:
        raise EavError(f"invalid operation name {name!r} (README ss2)")
    program = parse(source)
    if name in program.entities:
        raise EavError(f"entity {name!r} already exists")
    stub = (
        f"\n{name} is operation\n{name} out {out_type}\n"
        f'{name} purpose "TODO: describe {name}"\n'
    )
    out = format_program(parse(source + stub))
    return out


def slice_entity(program: Program, name: str, with_calls: bool = True) -> str:
    """The semantic neighborhood of an entity (README ss24 `slice`): the entity
    plus the calls/tasks/cleanups it activates (and cleanup workers), formatted in
    canonical EAV so every activated call has its definition in the slice."""
    root = program.entities.get(name)
    if root is None:
        raise EavError(f"no entity named {name!r}")
    included = [name]
    seen = {name}

    def add(n):
        if n in program.entities and n not in seen:
            seen.add(n)
            included.append(n)

    if with_calls and root.kind in ("operation", "function"):
        for row in root.rows:
            if row.predicate in _STEP_SPLIT and row.payload:
                ref = program.entities.get(row.payload[0])
                if ref is None:
                    continue
                add(ref.name)
                if ref.kind == "cleanup":
                    cr = ref.fact("call")
                    if cr and cr.payload:
                        add(cr.payload[0])
    blocks = [format_entity(program.entities[n], program)
              for n in sorted(included, key=lambda n: (_kind_rank(program.entities[n].kind),))]
    return "\n\n".join(blocks) + "\n"


def pack(program: Program, entity: str, budget: int = 4000) -> str:
    """A budgeted agent context bundle for editing one entity (README ss24
    `pack`): a cached-prefix slice + entity diagnostics + an edit-contract,
    truncated to `budget` characters."""
    parts = ["== slice ==", slice_entity(program, entity).rstrip()]
    rel = [d for d in lint(program) if d.entity in (entity, None)]
    parts.append("== diagnostics ==")
    parts.extend(d.render() for d in rel[:20]) if rel else parts.append("(none)")
    parts.append("== edit-contract ==")
    parts.append("- every binding referenced has a definition in this slice")
    parts.append("- preserve the call/task/cleanup split (do/start/defer)")
    parts.append("- fallible calls keep their catch + error branch")
    text = "\n".join(parts)
    return text[:budget]


def completions(kind: str) -> list:
    """Editor completion (README ss29 #7): the predicates valid for an entity
    kind — its §5 structural/step set plus the universal metadata predicates.
    Derived from the same tables the parser dispatches on (editor moves with the
    parser, never highlight-only)."""
    preds = set(ALLOWED_PREDICATES.get(kind, set())) | UNIVERSAL_PREDICATES
    return sorted(preds)


def semantic_tokens(line: str) -> list:
    """Classify a row's tokens for editor highlighting (README ss29 #7): column 1
    is always the subject, column 2 the predicate — the subject-anchored
    advantage. Returns [(token, role)]."""
    toks = tokenize_line(line)
    if not toks:
        return []
    out = [(toks[0], "subject")]
    if len(toks) > 1:
        out.append((toks[1], "keyword" if toks[1] in ("at", "is") else "predicate"))
    for t in toks[2:]:
        if t.startswith('"'):
            role = "string"
        elif t in RESERVED_WORDS and t[0:1].islower():
            role = "keyword"
        elif t in PRIMITIVE_TYPES or (t[:1].isupper() and _IDENT_RE.match(t)):
            role = "type"
        elif t[:1].isdigit() or (t[:1] == "-" and t[1:2].isdigit()):
            role = "number"
        else:
            role = "name"
        out.append((t, role))
    return out


TEST_LANES = ("unit", "component", "integration", "e2e", "golden")


def discover_tests(program: Program) -> dict:
    """Discover test operations by `tag test` and group them by lane tag
    (README ss28.7/ss30.5). An op tagged `test` with no lane tag is a unit test."""
    result: dict = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("operation", "function"):
            continue
        tags = [r.payload[0] for r in ent.facts("tag") if r.payload]
        if "test" in tags:
            lane = next((t for t in tags if t in TEST_LANES), "unit")
            result.setdefault(lane, []).append(ent.name)
    return result


# CLI subcommand -> MCP tool name (README ss24; proposed vs shipping shapes).
MCP_TOOL_MAP = {
    "lint": "check", "doctor": "doctor", "fmt": "fmt", "explain": "explain",
    "slice": "slice", "query": "query", "inventory": "inventory",
    "verify-patch": "verify_patch", "graph": "graph", "pack": "pack",
    "describe": "explain", "diff": "diff", "trace": "trace",
    "normalize": "normalize", "rename": "rename", "add": "add",
    "scaffold": "scaffold", "run": "eval", "lower": "lower", "test": "test",
}


def diagnostics_json(diags: list) -> str:
    """JSON surface for diagnostics (README ss24 `--json`)."""
    return json.dumps(
        [{"code": d.code, "severity": d.severity, "line": d.line,
          "entity": d.entity, "message": d.message} for d in diags],
        indent=2,
    )


def doctor(program: Program) -> dict:
    """Severity-grouped lint report with per-code suggested fixes (README ss24)."""
    groups: dict = {"error": [], "warning": [], "info": []}
    for d in lint(program):
        groups.setdefault(d.severity, []).append(d)
    return groups


def summarize(program: Program) -> dict:
    """Inventory of a program: entity counts by kind (README ss24 `inventory`)."""
    counts: dict[str, int] = {}
    for name in program.order:
        kind = program.entities[name].kind
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _exported_names(program: Program) -> set:
    """Names that are exported or named as the project entry (README ss7)."""
    names: set = set()
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "module":
            for ex in ent.facts("exports"):
                if ex.payload:
                    names.add(ex.payload[0])
        if ent.kind == "project":
            entry = ent.fact("entry")
            if entry and entry.payload:
                names.add(entry.payload[0])
    return names


def lint(program: Program) -> list:
    """Collect metadata/lint diagnostics without bailing on the first (README
    ss6, ss17, ss29 #12). Parse-time *hard errors* are raised by `parse`; this
    layer reports the softer MD/lint tiers and the warnings parse accumulated."""
    diags: list[Diagnostic] = []
    exported = _exported_names(program)
    for name in program.order:
        ent = program.entities[name]
        if len(ent.facts("purpose")) > 1:
            diags.append(Diagnostic("MD1046", "error",
                                    f"{ent.kind} {ent.name!r} has multiple purpose rows",
                                    ent.line, ent.name))
        if ent.kind == "module":
            if ent.fact("purpose") is None:
                diags.append(Diagnostic("MD1001", "error",
                                        f"module {ent.name!r} is missing a purpose",
                                        ent.line, ent.name))
            if ent.fact("invariant") is None:
                diags.append(Diagnostic("MD1002", "error",
                                        f"module {ent.name!r} is missing an invariant",
                                        ent.line, ent.name))
        elif ent.kind in ("operation", "function"):
            if _op_body_kind(ent) in ("runtimeBinding", "intrinsic"):
                continue  # MD1031/1032: generated/runtimeBinding metadata off
            public = ent.name in exported
            if ent.fact("purpose") is None:
                if public:
                    diags.append(Diagnostic("MD1011", "error",
                                            f"exported/entry operation {ent.name!r} is missing a purpose",
                                            ent.line, ent.name))
                else:
                    diags.append(Diagnostic("MD1021", "warning",
                                            f"operation {ent.name!r} has no purpose (recommended)",
                                            ent.line, ent.name))
            if public and ent.fact("invariant") is None:
                diags.append(Diagnostic("MD1012", "error",
                                        f"exported/entry operation {ent.name!r} is missing an invariant",
                                        ent.line, ent.name))
    # README ss17 #50: a primitive (runtimeBinding/intrinsic) body belongs in a
    # stdlib/.semsig-backed module, not application source. A file that declares
    # a `standard.*` module IS that boundary, so its primitive bodies are exempt.
    is_stdlib_module = any(
        program.entities[n].kind == "module"
        and (program.entities[n].fact("path") or Row("", "", [], 0)).payload[:1]
        and program.entities[n].fact("path").payload[0].startswith("standard.")
        for n in program.order
    )
    if not is_stdlib_module:
        for name in program.order:
            ent = program.entities[name]
            if ent.kind in ("operation", "function") and _op_body_kind(ent) in (
                "runtimeBinding", "intrinsic"
            ):
                diags.append(Diagnostic(
                    "SS5000", "warning",
                    f"operation {ent.name!r} has a `{_op_body_kind(ent)}` body in "
                    f"application source; primitive bodies belong in a .semsig-backed "
                    f"stdlib module (README ss17 #50)",
                    ent.line, ent.name))
    diags.extend(_lint_gates(program))
    diags.extend(_lint_c_exports(program))
    diags.extend(_lint_entry_abi(program))
    diags.extend(_lint_ownership_and_entry_export(program))
    # README ss25 / WS2-051: a catch/err variable reused across calls with
    # incompatible error types warns.
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        catch_types: dict = {}
        for cn in program.order:
            call = program.entities[cn]
            owner = call.fact("in")
            if (call.kind in ("call", "task") and owner and owner.payload
                    and owner.payload[0] == op.name):
                c = call.fact("catch")
                if c and len(c.payload) >= 2:
                    catch_types.setdefault(c.payload[0], set()).add(c.payload[1])
        for var, types in catch_types.items():
            if len(types) > 1:
                diags.append(Diagnostic(
                    "SS2551", "warning",
                    f"catch variable {var!r} is shared across calls with "
                    f"incompatible error types {sorted(types)} (README ss25)",
                    op.line, op.name))
    # README ss17 #15: warn on irreducible control flow (multi-entry loops).
    for n in program.order:
        op = program.entities[n]
        if op.kind in ("operation", "function") and not _is_reducible(_op_cfg(op)):
            diags.append(Diagnostic(
                "SS1315", "warning",
                f"operation {op.name!r} has irreducible control flow "
                f"(a multi-entry loop); prefer structured goto (README ss17 #15)",
                op.line, op.name))
    diags.extend(_lint_variant_exhaustiveness(program))
    diags.extend(_lint_sqlite_usage(program))
    diags.extend(_lint_loop_no_progress(program))
    # X-093 / README §10.6: exact equality on Float operands is a NaN/epsilon
    # footgun — steer to a tolerance compare (or Decimal for exact values).
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if target in ("math.equalFloat64", "math.notEqualFloat64",
                      "math.equalFloat32", "math.notEqualFloat32"):
            diags.append(Diagnostic(
                "SS3094", "warning",
                f"call {ent.name!r} compares Float operands with {target!r}; exact "
                f"Float equality is a NaN/epsilon footgun — compare within a "
                f"tolerance, or use Decimal/`decimal.equal` for exact values "
                f"(README §10.6)",
                ent.line, ent.name))
    # README ss6 / WS2-035: metadata payload-shape checks. Free-text metadata
    # (purpose/invariant/deprecated) carries a quoted string; identifier metadata
    # (tag/owner) carries a bare identifier.
    _QUOTED_META = {"purpose": "MD1042", "invariant": "MD1043", "deprecated": "MD1045"}
    _IDENT_META = {"tag": "MD1044", "owner": "MD1047"}
    for n in program.order:
        ent = program.entities[n]
        for pred, code in _QUOTED_META.items():
            for r in ent.facts(pred):
                if r.payload and not r.payload[-1].startswith('"'):
                    diags.append(Diagnostic(
                        code, "error",
                        f"{pred} on {ent.name!r} must be a quoted string, got "
                        f"{r.payload[-1]!r} (README ss6)",
                        r.line, ent.name))
        for pred, code in _IDENT_META.items():
            for r in ent.facts(pred):
                if r.payload and (r.payload[0].startswith('"')
                                  or not _IDENT_RE.match(r.payload[0])):
                    diags.append(Diagnostic(
                        code, "error",
                        f"{pred} on {ent.name!r} must be a bare identifier, got "
                        f"{r.payload[0]!r} (README ss6)",
                        r.line, ent.name))
    # README ss12 / WS1-085: an out that rebinds module storage should declare a
    # matching `effect write storage.<name>` on the owning op.
    _storages = _storage_entities(program)
    for n in program.order:
        call = program.entities[n]
        if call.kind not in ("call", "task"):
            continue
        out = call.fact("out")
        owner = call.fact("in")
        if not (out and out.payload and owner and owner.payload):
            continue
        st = _storages.get(out.payload[0])
        if st is None or not _is_module_storage(st):
            continue
        mut = st.fact("mutability")
        if not (mut and mut.payload and mut.payload[0] == "mutable"):
            continue
        op = program.entities.get(owner.payload[0])
        want = ["write", f"storage.{out.payload[0]}"]
        has_effect = op is not None and any(
            e.payload[:2] == want for e in op.facts("effect")
        )
        if not has_effect:
            diags.append(Diagnostic(
                "SS1086", "warning",
                f"call {call.name!r} rebinds module storage {out.payload[0]!r} but "
                f"{owner.payload[0]!r} declares no `effect write "
                f"storage.{out.payload[0]}` (README ss12, WS1-085)",
                call.line, owner.payload[0]))
    # README ss33.10 / WS1-057: a local operationType binding whose name is also a
    # module operation resolves to the binding — warn to rename.
    op_names = {
        program.entities[n].name for n in program.order
        if program.entities[n].kind in ("operation", "function")
    }
    optype_names = {
        program.entities[n].name for n in program.order
        if program.entities[n].kind == "operationType"
    }
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        for r in op.facts("let"):
            if (len(r.payload) >= 3 and r.payload[2] in optype_names
                    and r.payload[0] in op_names):
                diags.append(Diagnostic(
                    "SS3392", "warning",
                    f"operation-reference binding {r.payload[0]!r} in {op.name!r} "
                    f"shadows module operation {r.payload[0]!r}; `invokes` resolves "
                    f"to the binding — rename to disambiguate (README ss33.10)",
                    r.line, op.name))
    # README ss17 #30/#31: `branch else` is the default only after a guard branch.
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        prev_was_guard = False
        for row in op.rows:
            if row.predicate == "branch" and row.payload:
                if row.payload[0] == "else" and not prev_was_guard:
                    diags.append(Diagnostic(
                        "SS3001", "warning",
                        "`branch else` should follow a guard branch (it is the "
                        "default-only-after-guard, README ss17 #30/#31)",
                        row.line, op.name))
                prev_was_guard = row.payload[0] != "else"
            elif row.label is None and row.predicate in STEP_PREDICATES:
                prev_was_guard = False
    # README ss17 #35: a fallible call (has `catch`) activated by `do` should have
    # an error path (`branch ifError`); a cleanup worker is exempt.
    cleanup_workers = {
        program.entities[n].fact("call").payload[0]
        for n in program.order
        if program.entities[n].kind == "cleanup" and program.entities[n].fact("call")
        and program.entities[n].fact("call").payload
    }
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        iferror = {
            r.payload[1] for r in op.rows
            if r.predicate == "branch" and len(r.payload) >= 2 and r.payload[0] == "ifError"
        }
        for r in op.rows:
            if r.predicate == "do" and r.payload:
                call = program.entities.get(r.payload[0])
                if (call and call.kind == "call" and call.fact("catch") is not None
                        and call.name not in iferror and call.name not in cleanup_workers):
                    diags.append(Diagnostic(
                        "SS3501", "warning",
                        f"fallible call {call.name!r} has a catch but no "
                        f"`branch ifError` error path (README ss17 #35)",
                        r.line, op.name))
    for name in program.order:
        ent = program.entities[name]
        if ent.kind in ("operation", "function"):
            for row in ent.rows:
                if (row.predicate == "branch" and row.payload
                        and row.payload[0] in ("ifValue", "ifOut")):
                    diags.append(Diagnostic(
                        "SS1340", "info",
                        f"{row.payload[0]} is sugar; fmt canonicalizes it to a "
                        f"compare call + `branch if` (README ss13)",
                        row.line, ent.name))
    for w in program.warnings:
        diags.append(Diagnostic("SS0900", "warning", w))
    diags.extend(_suppress_diagnostics(program, diags))
    return _apply_suppressions(program, diags)


_C_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _lint_c_exports(program: Program) -> list:
    """`OP export c <symbol>` interop annotation (README ss30.4.2): the symbol is
    a C identifier, at most one per operation, and unique across operations."""
    out: list[Diagnostic] = []
    seen: dict[str, str] = {}  # symbol -> op name
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("operation", "function"):
            continue
        exports = [r for r in ent.facts("export") if r.payload and r.payload[0] == "c"]
        if len(exports) > 1:
            out.append(Diagnostic("SS3041", "error",
                                  f"operation {ent.name!r} has multiple `export c` rows "
                                  f"(one per op)", ent.line, ent.name))
        for r in exports:
            sym = r.payload[1] if len(r.payload) >= 2 else ""
            if not _C_IDENT_RE.match(sym):
                out.append(Diagnostic("SS3042", "error",
                                      f"export symbol {sym!r} is not a valid C identifier",
                                      r.line, ent.name))
            elif sym in seen:
                out.append(Diagnostic("SS3043", "error",
                                      f"export symbol {sym!r} is already used by "
                                      f"{seen[sym]!r} (must be unique)", r.line, ent.name))
            else:
                seen[sym] = ent.name
    return out


def _lint_ownership_and_entry_export(program: Program) -> list:
    """WS2-021 lint warnings: #39 a call that `owns` a resource without a
    `cleanedBy` cleanup; #38 the project entry should be exported (MD1013); #36 an
    `ifOut` on a fallible call before its error is handled."""
    out: list[Diagnostic] = []
    exported = _exported_names(program)
    for n in program.order:
        ent = program.entities[n]
        if ent.kind in ("call", "task"):
            if ent.fact("owns") is not None and ent.fact("cleanedBy") is None:
                out.append(Diagnostic("SS3900", "warning",
                                      f"{ent.kind} {ent.name!r} owns a resource but has "
                                      f"no `cleanedBy` cleanup", ent.line, ent.name))
        if ent.kind in ("operation", "function"):
            for row in ent.rows:
                if (row.predicate == "branch" and row.payload and row.payload[0] == "ifOut"):
                    callee = program.entities.get(row.payload[1]) if len(row.payload) > 1 else None
                    if callee and callee.fact("catch") is not None:
                        out.append(Diagnostic("SS3600", "warning",
                                              f"`ifOut {callee.name}` inspects a fallible "
                                              f"call's out before handling its error "
                                              f"(README §17 #36)", row.line, ent.name))
    module_exports = {
        ex.payload[0]
        for n in program.order if program.entities[n].kind == "module"
        for ex in program.entities[n].facts("exports") if ex.payload
    }
    for proj in program.of_kind("project"):
        entry = proj.fact("entry")
        if entry and entry.payload and entry.payload[0] not in module_exports:
            if program.entities.get(entry.payload[0]) is not None:
                out.append(Diagnostic("MD1013", "warning",
                                      f"project entry {entry.payload[0]!r} has no `exports` "
                                      f"row in its module (README §7)", proj.line, entry.payload[0]))
    return out


def _lint_gates(program: Program) -> list:
    """`forTarget`/`forPlatform` reference-closure (README ss30.3.1, ss17 #55): a
    gate value must name a target declared by the project, or a declared
    platform entity."""
    targets: set = set()
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "project":
            for t in ent.facts("target"):
                if t.payload:
                    targets.add(t.payload[0])
    platforms = {n for n in program.order if program.entities[n].kind == "platform"}
    out: list[Diagnostic] = []
    for n in program.order:
        ent = program.entities[n]
        for row in ent.facts("forTarget"):
            if row.payload and row.payload[0] not in targets:
                out.append(Diagnostic("SS3010", "error",
                                      f"forTarget {row.payload[0]!r} is not a target "
                                      f"declared by the project",
                                      row.line, ent.name))
        for row in ent.facts("forPlatform"):
            if row.payload and row.payload[0] not in platforms:
                out.append(Diagnostic("SS3011", "error",
                                      f"forPlatform {row.payload[0]!r} is not a "
                                      f"declared platform entity",
                                      row.line, ent.name))
    return out


def _apply_suppressions(program: Program, diags: list) -> list:
    """Drop diagnostics suppressed by a `suppress CODE because "…"` row on the
    *same* entity (README ss30.6.2, ss17 #54). An operation's suppress covers its
    own rows, not its child call/task/cleanup entities (each is its own subject)."""
    suppressed: set = set()  # (entity, code)
    for name in program.order:
        ent = program.entities[name]
        for row in ent.facts("suppress"):
            # WS2-072: only advisory (T3/T4) codes are suppressible; a deny-tier
            # (T0/T1/T2) suppress is rejected (SS5402) and stays in effect.
            if (row.payload and "because" in row.payload
                    and DIAGNOSTICS.get(row.payload[0], {}).get("tier") in ("T3", "T4")):
                suppressed.add((ent.name, row.payload[0]))
    return [d for d in diags if (d.entity, d.code) not in suppressed]


def _suppress_diagnostics(program: Program, diags: list) -> list:
    """A `suppress CODE` row must carry a real code and a `because` (README
    ss17 #54)."""
    extra: list[Diagnostic] = []
    for name in program.order:
        ent = program.entities[name]
        for row in ent.facts("suppress"):
            if not row.payload:
                continue
            code = row.payload[0]
            if "because" not in row.payload:
                extra.append(Diagnostic("SS5400", "error",
                                        f"`suppress {code}` needs a `because` rationale",
                                        row.line, ent.name))
            elif code not in DIAGNOSTICS:
                extra.append(Diagnostic("SS5401", "error",
                                        f"`suppress {code}` names an unknown diagnostic code",
                                        row.line, ent.name))
            elif DIAGNOSTICS[code].get("tier") in ("T0", "T1", "T2"):
                extra.append(Diagnostic(
                    "SS5402", "error",
                    f"`suppress {code}` targets a deny-tier "
                    f"({DIAGNOSTICS[code].get('tier')}) diagnostic; soundness/UB/"
                    f"security/structural codes are non-suppressible — fix the cause "
                    f"(README §30.6.2)",
                    row.line, ent.name))
    return extra


def _validate_program(program: Program) -> None:
    """Post-parse structural validation for hard-error invariants (README ss10).

    Lint-tier checks live in eavlint.py; this pass enforces only rules the spec
    marks as a *hard error* during parsing.
    """
    alias_map = {
        a.name: a.fact("for").payload[0]
        for a in program.of_kind("alias")
        if a.fact("for") and a.fact("for").payload
    }
    for ent in (program.entities[name] for name in program.order):
        if ent.kind == "call" and ent.fact("async") is not None:
            # README ss5/ss15.5: `async` on a call is tolerated-deprecated; it
            # promotes to a `task` on fmt. Parse it, but record the deprecation.
            program.warnings.append(
                f"{ent.name}: `async` on a call is deprecated; use `is task` "
                f"(README ss5/ss15.5)"
            )
        if ent.kind == "record":
            _check_unique_labels(
                ent, "field", "field name", "README ss10/ss17 #29"
            )
            for fr in ent.facts("field"):
                if fr.payload and fr.payload[0] == "new":
                    raise EavError(
                        f"record {ent.name!r} may not declare a field named `new`; "
                        f"that segment is the constructor target (README ss10.5, "
                        f"ss17 #51)",
                        fr.line,
                    )
        elif ent.kind == "enum":
            _validate_enum(ent)
        elif ent.kind == "webServer":
            seen_routes: set = set()
            for r in ent.facts("route"):
                if len(r.payload) >= 2:
                    key = (r.payload[0], r.payload[1])
                    if key in seen_routes:
                        raise EavError(
                            f"webServer {ent.name!r} has a duplicate route "
                            f"{r.payload[0]} {r.payload[1]} (README ss17 #32)",
                            r.line, code="SS3201",
                        )
                    seen_routes.add(key)
        elif ent.kind == "storage":
            scope = ent.fact("scope")
            value = ent.fact("value")
            if (scope and scope.payload and scope.payload[0] == "module"
                    and value and value.payload):
                ref = program.entities.get(value.payload[0])
                if ref is not None and ref.kind in ("operation", "function", "call", "task"):
                    raise EavError(
                        f"module storage {ent.name!r} initializer references "
                        f"{ref.kind} {ref.name!r}; module-storage init must be "
                        f"effect-free (literal/constant/prior-storage, README ss30.2.1)",
                        ent.line, code="SS3021",
                    )
        elif ent.kind == "platform":
            tr = ent.fact("targetRuntime")
            if tr and tr.payload and tr.payload[0] not in ("native", "wasm"):
                raise EavError(
                    f"platform {ent.name!r} targetRuntime {tr.payload[0]!r} must be "
                    f"`native` or `wasm` (README ss7)",
                    tr.line,
                    code="SS0740",
                )
        elif ent.kind == "errorCase" and ent.fact("of") is None:
            raise EavError(
                f"errorCase {ent.name!r} needs an `of <Error>` row (README ss9)",
                ent.line,
            )
        _check_dotted_types(ent)
        if ent.kind in ("operation", "function"):
            _validate_let_forward_refs(ent)
            _validate_body_kind(ent)
            _validate_labels(ent, program)
            _validate_return_arity(ent)
            _validate_no_shadow(ent)
            _validate_async(ent)
            for row in ent.facts("let"):
                if row.payload and row.payload[0] in RESERVED_WORDS:
                    raise EavError(
                        f"reserved word {row.payload[0]!r} may not be a variable "
                        f"name (README ss2)",
                        row.line, code="SS0003",
                    )
                if len(row.payload) > 3:
                    _validate_value_literal(
                        row.payload[3], row.line, row.payload[2], alias_map
                    )
        if ent.kind in ("call", "task"):
            for row in ent.facts("arg"):
                if len(row.payload) > 2:
                    _validate_value_literal(
                        row.payload[2], row.line, row.payload[1], alias_map
                    )
        for row in ent.facts("out"):
            if row.payload and row.payload[0] == "Result" and len(row.payload) != 3:
                raise EavError(
                    "`out Result` needs exactly an OK type and an ERR type "
                    f"(README ss10), got {row.payload!r}",
                    row.line, code="SS1010",
                )
    _validate_calls(program)
    _validate_binding_consistency(program)
    _validate_invoke_ambiguity(program)
    _validate_variant_payload_bind(program)
    _validate_variant_positions(program)
    _validate_return_exactness(program)
    _validate_storage_mutation(program)
    _validate_set_targets(program)
    _validate_reserved_targets(program)
    _validate_webserver_abi(program)
    _validate_islands(program)
    _validate_ownership_edges(program)
    _validate_view_lifetimes(program)
    _validate_transfer_moves(program)
    _validate_html_trust(program)
    _validate_time_safety(program)
    _validate_numeric_precision(program)
    _validate_trust_flow(program)
    _validate_sink_typing(program)
    _validate_secret_flow(program)
    _validate_decode_limits(program)
    _validate_constants(program)
    _validate_overrides(program)
    _validate_entry_scope(program)
    _validate_module_init_order(program)
    _validate_configure(program)


def _validate_module_init_order(program: Program) -> None:
    """Module-storage init is doc order with no cycles (README ss30.2.1): a
    storage initializer referencing another storage forms a DAG; a cycle is a
    hard error."""
    storages = {
        n for n in program.order
        if program.entities[n].kind == "storage"
        and (program.entities[n].fact("scope") or Row("", "", [], 0)).payload[:1] == ["module"]
    }
    deps: dict = {}
    for s in storages:
        v = program.entities[s].fact("value")
        target = v.payload[0] if v and v.payload else None
        deps[s] = target if target in storages else None

    color: dict = {}  # 0=visiting, 1=done

    def visit(node, stack):
        if color.get(node) == 1:
            return
        if node in stack:
            cycle = " -> ".join(stack[stack.index(node):] + [node])
            raise EavError(
                f"cyclic module-storage initialization: {cycle} (README ss30.2.1)",
                program.entities[node].line, code="SS3022",
            )
        nxt = deps.get(node)
        if nxt is not None:
            visit(nxt, stack + [node])
        color[node] = 1

    for s in storages:
        visit(s, [])
    _validate_html(program)
    _validate_cleanup(program)


def _validate_html(program: Program) -> None:
    """HTML template contracts (README ss16, ss17 #33/#34): legacy single-brace
    holes are a breaking error; an `html.render` call's hole args must match the
    template's `{{holes}}`; a hole in a URL-bearing attribute needs HtmlSafeUrl."""
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "htmlTemplate":
            island = program.islands.get((ent.name, "html"))
            if island is not None:
                html_holes("\n".join(island))  # raises on legacy single-brace
    for n in program.order:
        call = program.entities[n]
        if call.kind != "call":
            continue
        inv = call.fact("invokes")
        if not inv or inv.payload[:1] != ["html.render"]:
            continue
        args = {a.payload[0]: a for a in call.facts("arg")}
        tmpl_arg = args.get("template")
        tmpl = program.entities.get(tmpl_arg.payload[2]) if tmpl_arg and len(tmpl_arg.payload) >= 3 else None
        if tmpl is None or tmpl.kind != "htmlTemplate":
            continue
        island = program.islands.get((tmpl.name, "html"))
        holes = html_holes("\n".join(island)) if island else []
        hole_names = {h for h, _ in holes}
        provided = {name for name in args if name != "template"}
        if provided != hole_names:
            raise EavError(
                f"render {call.name!r} args {sorted(provided)} do not match template "
                f"holes {sorted(hole_names)} (README ss17 #33)",
                call.line, code="SS1635",
            )
        for hole, is_url in holes:
            if is_url:
                a = args.get(hole)
                atype = a.payload[1] if a and len(a.payload) >= 2 else None
                if atype != "HtmlSafeUrl":
                    raise EavError(
                        f"render {call.name!r} hole {hole!r} fills a URL attribute "
                        f"and must be HtmlSafeUrl, got {atype!r} (README ss16, ss17 #34)",
                        call.line, code="SS1634",
                    )


def _check_dotted_types(ent: Entity) -> None:
    """A dotted type reference is valid only in an alias `for` row (README ss3,
    ss7, ss17 #37). Elsewhere — let/arg/in/out/catch/field type positions — a
    dotted type name is a hard error."""
    def check(tok, line):
        if "." in tok:
            raise EavError(
                f"dotted type {tok!r} is only valid in an alias `for` row; "
                f"type references are otherwise bare (README ss3, ss17 #37)",
                line, code="SS3700",
            )
    for r in ent.facts("let"):
        if len(r.payload) >= 3:
            check(r.payload[2], r.line)
    for pred, idx in (("arg", 1), ("in", 1), ("catch", 1), ("field", 1)):
        for r in ent.facts(pred):
            if len(r.payload) > idx:
                check(r.payload[idx], r.line)
    for r in ent.facts("out"):
        for t in r.payload:
            if t not in ("Result", "nil"):
                check(t, r.line)


def _validate_configure(program: Program) -> None:
    """A `configure` op is build-time (README ss30.3.2): it may use only
    build-time (`build.*`) capabilities — a runtime effect is an error."""
    configure_ops = {
        p.payload[0]
        for proj in program.of_kind("project")
        for p in proj.facts("configure")
        if p.payload
    }
    for name in configure_ops:
        op = program.entities.get(name)
        if op is None:
            continue
        for eff in op.facts("effect"):
            resource = eff.payload[1] if len(eff.payload) >= 2 else ""
            if not resource.startswith("build."):
                raise EavError(
                    f"configure op {name!r} declares the runtime effect "
                    f"`{' '.join(eff.payload)}`; configure is build-time and may "
                    f"use only build.* capabilities (README ss30.3.2)",
                    eff.line,
                    code="SS3002",
                )
        # README ss30.3.2 / WS3-043: a configure op runs once, ungated — a
        # `forTarget`/`forPlatform` gate on it is an error.
        for gate in ("forTarget", "forPlatform"):
            grow = op.fact(gate)
            if grow is not None:
                raise EavError(
                    f"configure op {name!r} carries a `{gate}` gate; configure runs "
                    f"once and ungated at build time (README ss30.3.2, WS3-043)",
                    grow.line, code="SS3043",
                )
    _validate_step_split(program)
    _validate_activation_count(program)
    _validate_effect_coverage(program)


def _validate_activation_count(program: Program) -> None:
    """A call is activated exactly once (README ss17 #2): by one `do` step or as
    one cleanup's worker. More than one activation is a hard error (this also
    catches a cleanup worker that is separately `do`-activated, ss17 #43); zero
    activations is an unused-call warning."""
    do_count: dict[str, int] = {}
    cleanup_count: dict[str, int] = {}
    for name in program.order:
        ent = program.entities[name]
        if ent.kind in ("operation", "function"):
            for row in ent.rows:
                if row.predicate == "do" and row.payload:
                    do_count[row.payload[0]] = do_count.get(row.payload[0], 0) + 1
        elif ent.kind == "cleanup":
            cr = ent.fact("call")
            if cr and cr.payload:
                cleanup_count[cr.payload[0]] = cleanup_count.get(cr.payload[0], 0) + 1
    for name in program.order:
        ent = program.entities[name]
        if ent.kind != "call":
            continue
        total = do_count.get(name, 0) + cleanup_count.get(name, 0)
        if total > 1:
            raise EavError(
                f"call {name!r} is activated {total} times; a call is activated "
                f"exactly once (by one `do` or one cleanup worker, README ss17 "
                f"#2/#43)",
                ent.line,
                code="SS1702",
            )
        if total == 0:
            program.warnings.append(
                f"{name}: call is never activated (unused, README ss17 #2)"
            )


def _validate_effect_coverage(program: Program) -> None:
    """An operation's *effective* effects are its own plus those of the calls/
    tasks/cleanups it activates; every effective effect should be covered by a
    `uses` capability (README ss8, ss15, ss17 #5; effect-union WS2-040). An
    uncovered effect — including one introduced by an activated call — warns."""
    cap_grants: dict[str, set] = {}
    for name in program.order:
        ent = program.entities[name]
        if ent.kind == "capability":
            cap_grants[ent.name] = {
                (g.payload[0], g.payload[1])
                for g in ent.facts("grants")
                if len(g.payload) >= 2
            }

    def effects_of(ent: Entity):
        return {
            (e.payload[0], e.payload[1])
            for e in ent.facts("effect")
            if len(e.payload) >= 2
        }

    def invoked_user_op(call: Entity):
        inv = call.fact("invokes")
        if inv and inv.payload and "." not in inv.payload[0]:
            target = program.entities.get(inv.payload[0])
            if target is not None and target.kind in ("operation", "function"):
                return target
        return None

    def _grants_of(op: Entity) -> set:
        cov: set = set()
        for u in op.facts("uses"):
            if u.payload:
                cov |= cap_grants.get(u.payload[0], set())
        return cov

    def _action_covers(grant_action: str, effect_action: str) -> bool:
        # README ss8: a `readWrite` grant subsumes the `read` and `write` actions
        # on the same resource (an op authorized to read+write may do either).
        # Mirrors semsc: `grant_access == "readWrite" and action in {read, write}`.
        return grant_action == effect_action or (
            grant_action == "readWrite" and effect_action in ("read", "write")
        )

    def _covered_by(covered: set, action: str, resource: str) -> bool:
        # README ss8: capability effect paths are hierarchical — a grant of
        # `<action> <prefix>` authorizes every narrower `<action> <prefix>.<sub>`
        # effect (e.g. `read http.request` covers `read http.request.body`).
        # Mirrors semsc's _effect_path_covers; an exact match is the base case.
        for gact, gres in covered:
            if _action_covers(gact, action) and (
                resource == gres or resource.startswith(gres + ".")
            ):
                return True
        return False

    def effective_effects(op: Entity, seen: set) -> set:
        """Transitive effective effects across the call graph (README ss29 #10).
        Authority is caller-granted and does NOT encapsulate: an effect a callee
        triggers is part of every caller's effective set, so each op on the path
        must hold a covering `uses` capability of its own (README ss8; pinned by
        the entropy/clock/process capability tests)."""
        if op.name in seen:
            return set()
        seen.add(op.name)
        eff = set(effects_of(op))
        for row in op.rows:
            if row.predicate not in _STEP_SPLIT or not row.payload:
                continue
            ref = program.entities.get(row.payload[0])
            if ref is None:
                continue
            eff |= effects_of(ref)
            workers = [ref]
            if ref.kind == "cleanup":
                cr = ref.fact("call")
                w = program.entities.get(cr.payload[0]) if cr and cr.payload else None
                if w is not None:
                    workers.append(w)
                    eff |= effects_of(w)
            for w in workers:
                if w.kind in ("call", "task"):
                    callee = invoked_user_op(w)
                    if callee is not None:
                        eff |= effective_effects(callee, seen)
        return eff

    for name in program.order:
        op = program.entities[name]
        if op.kind not in ("operation", "function"):
            continue
        own = _grants_of(op)
        for action, resource in sorted(effective_effects(op, set())):
            if not _covered_by(own, action, resource):
                program.warnings.append(
                    f"{op.name}: effective effect `{action} {resource}` is not "
                    f"covered by a `uses` capability (README ss8, ss17 #5)"
                )


# Activation step -> the entity kind it must reference (README ss13/ss34.4).
_STEP_SPLIT = {
    "do": "call",
    "defer": "cleanup",
    "start": "task",
    "join": "task",
    "poll": "task",
    "cancel": "task",
    "detach": "task",
}


def _validate_step_split(program: Program) -> None:
    """The call/task/cleanup split is non-negotiable (README ss34.4): `do`
    activates a call, `start/join/poll/cancel/detach` a task, `defer` a cleanup.
    Cross-use is a hard error."""
    for name in program.order:
        op = program.entities[name]
        if op.kind not in ("operation", "function"):
            continue
        for row in op.rows:
            expected = _STEP_SPLIT.get(row.predicate)
            if expected is None or not row.payload:
                continue
            if "." in row.payload[0]:
                raise EavError(
                    f"`{row.predicate} {row.payload[0]}` uses a dotted name; internal "
                    f"references are bare (dots are external-path only, README ss3, "
                    f"ss26)",
                    row.line,
                    code="SS1326",
                )
            ref = program.entities.get(row.payload[0])
            if ref is None:
                raise EavError(
                    f"`{row.predicate} {row.payload[0]}` references an undeclared "
                    f"entity (README ss13)",
                    row.line,
                )
            if ref.kind != expected:
                raise EavError(
                    f"`{row.predicate} {ref.name}` targets a {ref.kind}; "
                    f"`{row.predicate}` requires a {expected} "
                    f"(call/task/cleanup split, README ss34.4)",
                    row.line, code="SS1044",
                )
            owner = ref.fact("in")
            if owner and owner.payload and owner.payload[0] != op.name:
                raise EavError(
                    f"`{row.predicate} {ref.name}` activates an entity owned by "
                    f"{owner.payload[0]!r}, not {op.name!r} (README ss17 #4)",
                    row.line,
                )


def _validate_cleanup(program: Program) -> None:
    """Cleanup/ownership invariants (README ss15.6, ss17 #41/#42/#44; ss15).

    Each cleanup entity has exactly one `call` and one `cleans`; `logAndSuppress`
    requires `because`; the cleaned resource must be `owns`-ed by some call; and
    a producer's `cleanedBy` must point to a real cleanup entity."""
    owned = {
        r.payload[0]
        for n in program.order
        for r in program.entities[n].facts("owns")
        if r.payload
    }
    cleanups = {n for n in program.order if program.entities[n].kind == "cleanup"}
    for name in program.order:
        ent = program.entities[name]
        if ent.kind == "cleanup":
            calls = ent.facts("call")
            cleans = ent.facts("cleans")
            if len(calls) != 1:
                raise EavError(
                    f"cleanup {ent.name!r} needs exactly one `call` row "
                    f"(README ss17 #41)",
                    ent.line,
                )
            if len(cleans) != 1:
                raise EavError(
                    f"cleanup {ent.name!r} needs exactly one `cleans` row "
                    f"(README ss15.6)",
                    ent.line,
                )
            onfail = ent.fact("onFailure")
            if onfail and onfail.payload and onfail.payload[0] == "logAndSuppress":
                if ent.fact("because") is None:
                    raise EavError(
                        f"cleanup {ent.name!r} uses `logAndSuppress` but has no "
                        f"`because` rationale (README ss15.6, ss17 #19)",
                        ent.line,
                    )
            if onfail and onfail.payload and onfail.payload[0] == "propagate":
                # README ss29 #2 / ss15.6: a propagating cleanup can only chain its
                # error out of an operation that itself returns a Result.
                owner_row = ent.fact("in")
                owner = program.entities.get(owner_row.payload[0]) if owner_row and owner_row.payload else None
                out = owner.fact("out") if owner else None
                if not (out and out.payload and out.payload[0] == "Result"):
                    raise EavError(
                        f"cleanup {ent.name!r} uses `onFailure propagate` but its "
                        f"operation does not return a Result (nowhere to chain the "
                        f"error, README ss15.6, ss29 #2)",
                        ent.line,
                        code="SS1518",
                    )
                # README ss29 #2d / WS2-053: conflict resolution is **REPLACE** —
                # a propagating cleanup error *replaces* the in-flight error and
                # becomes the operation's error result (causedBy provenance
                # wrapping is deferred). Under replace, the propagated worker error
                # must fit the operation's Result error slot.
                worker_c = program.entities.get(calls[0].payload[0]) if calls[0].payload else None
                catch_row = worker_c.fact("catch") if worker_c else None
                if (catch_row and len(catch_row.payload) >= 2 and len(out.payload) >= 3
                        and catch_row.payload[1] != out.payload[2]):
                    raise EavError(
                        f"cleanup {ent.name!r} propagates {catch_row.payload[1]!r} but "
                        f"{owner.name!r} returns Result error {out.payload[2]!r}; under "
                        f"replace semantics the propagated error must match the "
                        f"operation's error slot (README ss29 #2d, WS2-053)",
                        ent.line, code="SS1519",
                    )
            # README ss17 #42: onFailure is meaningful only if the worker can
            # fail — it requires the worker call to have a `catch`.
            if onfail and onfail.payload:
                worker = program.entities.get(calls[0].payload[0]) if calls[0].payload else None
                if worker is not None and worker.fact("catch") is None:
                    raise EavError(
                        f"cleanup {ent.name!r} declares `onFailure` but its worker "
                        f"{worker.name!r} has no `catch` (nothing to handle, README "
                        f"ss17 #42)",
                        ent.line,
                        code="SS1542",
                    )
            # README ss17 #44: a cleanup worker that produces an `out` but has no
            # `catch` drops a value — it needs an explicit `discards`.
            worker = program.entities.get(calls[0].payload[0]) if calls[0].payload else None
            if (worker is not None and worker.fact("out") is not None
                    and worker.fact("catch") is None and worker.fact("discards") is None):
                raise EavError(
                    f"cleanup worker {worker.name!r} has an `out` and no `catch`; its "
                    f"result is dropped and needs `discards` (README ss17 #44)",
                    worker.line, code="SS1544",
                )
            resource = cleans[0].payload[0] if cleans[0].payload else None
            if resource is not None and resource not in owned:
                raise EavError(
                    f"cleanup {ent.name!r} cleans {resource!r}, which no call "
                    f"`owns` (README ss15.6, ss17 #41)",
                    ent.line,
                )
        if ent.kind in ("call", "task"):
            cb = ent.fact("cleanedBy")
            if cb and cb.payload:
                if cb.payload[0] not in cleanups:
                    raise EavError(
                        f"{ent.kind} {ent.name!r} cleanedBy {cb.payload[0]!r}, which is "
                        f"not a cleanup entity (dangling cleanedBy, README ss15)",
                        ent.line,
                    )
                # README ss17 #16 (SS1502): the cleanup must be `defer`-ed in the
                # owning operation so the resource is released on every path.
                owner_row = ent.fact("in")
                owner = program.entities.get(owner_row.payload[0]) if owner_row and owner_row.payload else None
                deferred = owner is not None and any(
                    r.predicate == "defer" and r.payload and r.payload[0] == cb.payload[0]
                    for r in owner.rows
                )
                if owner is not None and not deferred:
                    raise EavError(
                        f"{ent.kind} {ent.name!r} owns a resource cleaned by "
                        f"{cb.payload[0]!r}, but that cleanup is never `defer`-ed in "
                        f"{owner.name!r} — it would not run on every path (README "
                        f"ss15.6, ss17 #16)",
                        ent.line, code="SS1503",
                    )


def _target_is_nonvoid(target: str, program: Program):
    """Whether a call target yields a value eavc can statically judge: True for
    math.* (arith/compare), False for console.* (void), the callee's `out`
    presence for a bare user op, and None (unknown) for other external targets."""
    if (target.startswith("math.") or target.startswith("compare.")
            or target.startswith("convert.to") or target == "string.concat"
            or target.startswith("assert.") or target == "test.and"):
        return True
    if target.startswith("console."):
        return False
    if "." not in target:
        callee = program.entities.get(target)
        if callee is not None and callee.kind in ("operation", "function"):
            return callee.fact("out") is not None
    return None


def _lint_entry_abi(program: Program) -> list:
    """Entry-point ABIs (README ss11): a `console` entry operation takes no `in`
    parameters and returns ExitCode/Int32. Reported by the linter since it is a
    whole-program (project+target+entry) cross-reference. (wasm/webServer pending.)"""
    alias_map = {
        a.name: a.fact("for").payload[0]
        for a in program.of_kind("alias")
        if a.fact("for") and a.fact("for").payload
    }
    out: list[Diagnostic] = []
    for proj in program.of_kind("project"):
        targets = {t.payload[0] for t in proj.facts("target") if t.payload}
        entry = proj.fact("entry")
        if not entry or not entry.payload or "console" not in targets:
            continue
        ent = program.entities.get(entry.payload[0])
        if ent is None or ent.kind not in ("operation", "function"):
            continue  # webServer entry is a server entity, not an operation
        if ent.facts("in"):
            out.append(Diagnostic("SS1190", "error",
                                  f"console entry {ent.name!r} must take no `in` "
                                  f"parameters (README ss11)", ent.line, ent.name))
        orow = ent.fact("out")
        otype = orow.payload[0] if orow and orow.payload else None
        if _resolve_alias(otype, alias_map) not in ("Int32", "ExitCode"):
            out.append(Diagnostic("SS1191", "error",
                                  f"console entry {ent.name!r} must return ExitCode/"
                                  f"Int32, got {otype!r} (README ss11)", ent.line, ent.name))
    return out


def _validate_calls(program: Program) -> None:
    """Resolve `invokes` and match arg slots (README ss15, ss17 #48/#49).

    A *bare* (dotless) invokes target must name an in-module operation; an
    unresolved bare target is a hard error. For calls into a user operation,
    arg slots must match the callee's `in` names one-to-one (dotted/built-in
    targets are external and not checked here)."""
    ops = {
        name
        for name in program.order
        if program.entities[name].kind in ("operation", "function")
    }
    alias_map = {
        a.name: a.fact("for").payload[0]
        for a in program.of_kind("alias")
        if a.fact("for") and a.fact("for").payload
    }
    newtypes = set(alias_map)
    for name in program.order:
        ent = program.entities[name]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        if not inv or not inv.payload:
            continue
        target = inv.payload[0]
        # README ss17 #25: a non-void result that is neither bound (`out`),
        # caught (`catch`), nor explicitly `discards`-ed is an error.
        nonvoid = _target_is_nonvoid(target, program)
        if nonvoid and not (
            ent.fact("out") or ent.fact("catch") or ent.fact("discards")
        ):
            raise EavError(
                f"call {ent.name!r} drops the non-void result of {target!r}; add "
                f"`out`, `catch`, or `discards \"reason\"` (README ss17 #25)",
                ent.line,
            )
        if "." in target:
            continue  # imported / compiler-derived / intrinsic — external
        if target not in ops:
            # README ss33.9: a bare target may be an `operationType` binding of
            # the owning operation — an indirect call through a function pointer.
            owner_row = ent.fact("in")
            owner = program.entities.get(owner_row.payload[0]) if owner_row and owner_row.payload else None
            owner_lets = {r.payload[0] for r in owner.facts("let") if r.payload} if owner else set()
            if target in owner_lets:
                # README ss33.10 / WS1-057: an indirect call must match the
                # binding's operationType signature (positional arity + types).
                let_type = next(
                    (r.payload[2] for r in owner.facts("let")
                     if r.payload and r.payload[0] == target and len(r.payload) >= 3),
                    None,
                )
                ot = program.entities.get(let_type) if let_type else None
                if ot is not None and ot.kind == "operationType":
                    sig_ins = [r.payload[0] for r in ot.facts("in") if r.payload]
                    call_args = [a for a in ent.facts("arg") if len(a.payload) >= 2]
                    if len(call_args) != len(sig_ins):
                        raise EavError(
                            f"indirect call {ent.name!r} through {target!r} passes "
                            f"{len(call_args)} arg(s) but operationType {let_type!r} "
                            f"takes {len(sig_ins)} (README ss33.10, WS1-057)",
                            ent.line, code="SS3390",
                        )
                    for i, a in enumerate(call_args):
                        if a.payload[1] != sig_ins[i]:
                            raise EavError(
                                f"indirect call {ent.name!r} arg {i} type "
                                f"{a.payload[1]!r} does not match operationType "
                                f"{let_type!r} input {sig_ins[i]!r} (README ss33.10, "
                                f"WS1-057)",
                                ent.line, code="SS3391",
                            )
                    sig_out = ot.fact("out")
                    out_row = ent.fact("out")
                    if (sig_out and sig_out.payload and out_row
                            and len(out_row.payload) >= 2
                            and out_row.payload[1] != sig_out.payload[0]):
                        raise EavError(
                            f"indirect call {ent.name!r} out type "
                            f"{out_row.payload[1]!r} does not match operationType "
                            f"{let_type!r} output {sig_out.payload[0]!r} "
                            f"(README ss33.10, WS1-057)",
                            ent.line, code="SS3391",
                        )
                continue
            raise EavError(
                f"call {ent.name!r} invokes {target!r}, which is not an in-module "
                f"operation (unresolved bare target, README ss15)",
                ent.line,
            )
        callee = program.entities[target]
        in_names = [r.payload[0] for r in callee.facts("in") if r.payload]
        arg_names = [a.payload[0] for a in ent.facts("arg") if a.payload]
        for an in arg_names:
            if an not in in_names:
                raise EavError(
                    f"call {ent.name!r} arg {an!r} is not an input of {target!r} "
                    f"(README ss15, ss17 #49)",
                    ent.line,
                )
        for inn in in_names:
            if inn not in arg_names:
                raise EavError(
                    f"call {ent.name!r} is missing arg {inn!r} required by "
                    f"{target!r} (README ss15)",
                    ent.line,
                )
        # README ss10 / WS1-031: an `alias … for T` is a newtype. An arg whose
        # declared type differs from the callee's input type but resolves to the
        # same base is a silent coercion across a newtype boundary — rejected.
        in_types = {
            r.payload[0]: r.payload[1]
            for r in callee.facts("in") if len(r.payload) >= 2
        }
        for arg in ent.facts("arg"):
            if len(arg.payload) < 2:
                continue
            slot, arg_type = arg.payload[0], arg.payload[1]
            in_type = in_types.get(slot)
            if in_type is None or arg_type == in_type:
                continue
            if (arg_type in newtypes or in_type in newtypes) and (
                _resolve_alias(arg_type, alias_map)
                == _resolve_alias(in_type, alias_map)
            ):
                raise EavError(
                    f"call {ent.name!r} arg {slot!r} passes {arg_type!r} where "
                    f"{target!r} requires {in_type!r}; an alias is a distinct "
                    f"newtype and does not silently coerce (README ss10, WS1-031)",
                    arg.line, code="SS3710",
                )


BUILTIN_NAMESPACES = {"compare", "console", "math"}


def _validate_invoke_ambiguity(program: Program) -> None:
    """README ss17 #51: `invokes` target resolution must be unambiguous. An
    import alias may not equal a declared type name, and a bare operation name
    may not collide with a built-in lowercase namespace (compare/console/math)."""
    type_names = {
        program.entities[n].name
        for n in program.order
        if program.entities[n].kind in ("record", "enum", "alias")
    }
    for n in program.order:
        ent = program.entities[n]
        for r in ent.facts("imports"):
            if r.payload and r.payload[0] in type_names:
                raise EavError(
                    f"import alias {r.payload[0]!r} collides with a declared type "
                    f"name; `invokes`/type resolution would be ambiguous "
                    f"(README ss17 #51)",
                    r.line, code="SS1551",
                )
        if ent.kind in ("operation", "function") and ent.name in BUILTIN_NAMESPACES:
            raise EavError(
                f"operation {ent.name!r} collides with the built-in namespace "
                f"{ent.name!r}; a bare `invokes {ent.name}` would be ambiguous "
                f"(README ss17 #51)",
                ent.line, code="SS1552",
            )


def _storage_entities(program: Program) -> dict:
    return {
        program.entities[n].name: program.entities[n]
        for n in program.order if program.entities[n].kind == "storage"
    }


def _is_module_storage(st: Entity) -> bool:
    scope = st.fact("scope")
    return bool(scope and scope.payload and scope.payload[0] == "module")


def _validate_constants(program: Program) -> None:
    """README ss28.1 / WS3-041: a `PROJECT constant` is a project-global read-only
    value. Duplicate constant names collide (hard error), and a local binding may
    not shadow a constant name (hard error)."""
    seen: dict = {}
    for proj in program.of_kind("project"):
        for c in proj.facts("constant"):
            if not c.payload:
                continue
            if c.payload[0] in seen:
                raise EavError(
                    f"duplicate project constant {c.payload[0]!r} (README ss28.1, "
                    f"WS3-041)",
                    c.line, code="SS3041C",
                )
            seen[c.payload[0]] = c.line
    if not seen:
        return
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        for r in op.facts("let"):
            if r.payload and r.payload[0] in seen:
                raise EavError(
                    f"local binding {r.payload[0]!r} in {op.name!r} shadows the "
                    f"project constant {r.payload[0]!r} (no shadow, README ss28.1, "
                    f"WS3-041)",
                    r.line, code="SS3041D",
                )


def _override_value_matches(value: str, resolved: str) -> bool:
    """Whether a build override literal is well-typed for a resolved primitive."""
    if resolved == "String":
        return value.startswith('"')
    if resolved == "Bool":
        return value in ("true", "false", "yes", "no", "1", "0")
    if resolved in _FLOAT_TYPE_NAMES:
        return value[:1].isdigit() or value[:1] in "-."
    if resolved in _INT_RANGES:
        return value[:1].isdigit() or (value[:1] == "-" and value[1:2].isdigit())
    return True  # unknown/non-primitive type: not statically checkable here


def _validate_overrides(program: Program) -> None:
    """README ss28.1 / WS3-042: a platform `override <name> <value>` must name a
    declared `PROJECT constant` and its value must match the constant's type."""
    consts = {
        c.payload[0]: c.payload[1]
        for proj in program.of_kind("project")
        for c in proj.facts("constant")
        if len(c.payload) >= 2
    }
    alias_map = {
        a.name: a.fact("for").payload[0]
        for a in program.of_kind("alias")
        if a.fact("for") and a.fact("for").payload
    }
    for plat in program.of_kind("platform"):
        for o in plat.facts("override"):
            if len(o.payload) < 2:
                continue
            name, value = o.payload[0], o.payload[1]
            if name not in consts:
                raise EavError(
                    f"platform {plat.name!r} override names {name!r}, which is not a "
                    f"declared project constant (README ss28.1, WS3-042)",
                    o.line, code="SS3042A",
                )
            resolved = _resolve_alias(consts[name], alias_map)
            if not _override_value_matches(value, resolved):
                raise EavError(
                    f"platform {plat.name!r} override {name!r} value {value!r} does "
                    f"not match the constant's type {consts[name]!r} (README ss28.1, "
                    f"WS3-042)",
                    o.line, code="SS3042B",
                )


_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
_HANDLER_ABI = ({"request": "HttpRequest", "response": "HttpResponse"}, "Int32")
_MIDDLEWARE_ABI = (
    {"request": "HttpRequest", "response": "HttpResponse", "next": "NextMiddleware"},
    "Bool",
)
_LIFECYCLE_ABI = ({"serverContext": "ServerContext"}, "ExitCode")


def _validate_webserver_abi(program: Program) -> None:
    """README ss14 / WS2-026: webServer handler ABIs. Route/notFound/
    methodNotAllowed handlers take (request, response) -> Int32; startup/shutdown
    take (serverContext) -> ExitCode; middleware takes (request, response, next)
    -> Bool. Route methods are a fixed bare set; routes are exact-match static
    (no `:param` / `*` wildcards)."""

    def check_abi(opname, abi, line, role):
        want_ins, want_out = abi
        op = program.entities.get(opname)
        if op is None or op.kind not in ("operation", "function"):
            return  # unresolved handler is reported elsewhere
        ins = {r.payload[0]: r.payload[1] for r in op.facts("in") if len(r.payload) >= 2}
        out_row = op.fact("out")
        out_type = out_row.payload[0] if out_row and out_row.payload else None
        if ins != want_ins or out_type != want_out:
            raise EavError(
                f"{role} {opname!r} has the wrong ABI: expected inputs {want_ins} "
                f"-> out {want_out}, got inputs {ins} -> out {out_type} "
                f"(README ss14, WS2-026)",
                line, code="SS2603",
            )

    for ws in program.of_kind("webServer"):
        for r in ws.facts("route"):
            if not r.payload:
                continue
            method = r.payload[0]
            path = r.payload[1] if len(r.payload) >= 2 else ""
            if method not in _HTTP_METHODS:
                raise EavError(
                    f"webServer {ws.name!r} route method {method!r} is not one of "
                    f"{sorted(_HTTP_METHODS)} (README ss14, WS2-026)",
                    r.line, code="SS2601",
                )
            # README ss14: dynamic routing — a `:name` path-parameter segment
            # and the `*` catch-all wildcard are accepted. Their dispatch
            # (param extraction, wildcard fallback) is part of the webServer
            # runtime and lowers with the deferred `target webServer` codegen; a
            # `:` segment must still name a valid identifier so the param binding
            # is well-formed.
            for seg in path.strip('"').split("/"):
                if seg == "*" or not seg.startswith(":"):
                    continue
                if not _IDENT_RE.match(seg[1:]):
                    raise EavError(
                        f"webServer {ws.name!r} route {path!r} has a malformed route "
                        f"parameter {seg!r}; use `:name` with an identifier "
                        f"(README ss14)",
                        r.line, code="SS2602",
                    )
            if len(r.payload) >= 3:
                check_abi(r.payload[2], _HANDLER_ABI, r.line, "route handler")
        for pred, abi in (("notFound", _HANDLER_ABI), ("methodNotAllowed", _HANDLER_ABI),
                          ("startup", _LIFECYCLE_ABI), ("shutdown", _LIFECYCLE_ABI),
                          ("middleware", _MIDDLEWARE_ABI)):
            for row in ws.facts(pred):
                if row.payload:
                    check_abi(row.payload[0], abi, row.line, f"{pred} handler")


def _validate_ownership_edges(program: Program) -> None:
    """README ss15.6 / ss29 #26 / WS2-044: ownership edge discipline. An owned
    handle may not be aliased into a second binding; its cleanup may not be
    registered twice; and it may not escape via `return` (v0.3 has no
    obligation-carrying out type)."""
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        owned: dict = {}  # owned-handle name -> producing call line
        for cn in program.order:
            call = program.entities[cn]
            owner = call.fact("in")
            if (call.kind in ("call", "task") and owner and owner.payload
                    and owner.payload[0] == op.name):
                for o in call.facts("owns"):
                    if o.payload:
                        owned[o.payload[0]] = call.line
        if not owned:
            continue
        # alias: a `let` initialized from an owned handle aliases it
        for r in op.facts("let"):
            if len(r.payload) >= 4 and r.payload[3] in owned:
                raise EavError(
                    f"binding {r.payload[0]!r} in {op.name!r} aliases owned handle "
                    f"{r.payload[3]!r}; an owned handle has a single binding "
                    f"(README ss15.6, WS2-044)",
                    r.line, code="SS3044A",
                )
        # double-cleanup: the same cleanup deferred twice
        seen_defers: set = set()
        for row in op.rows:
            if row.predicate == "defer" and row.payload:
                if row.payload[0] in seen_defers:
                    raise EavError(
                        f"cleanup {row.payload[0]!r} is deferred twice in {op.name!r} "
                        f"(double-cleanup, README ss15.6, WS2-044)",
                        row.line, code="SS3044B",
                    )
                seen_defers.add(row.payload[0])
        # escape: returning an owned handle
        for row in op.rows:
            if row.predicate == "return":
                for t in row.payload:
                    if t in owned:
                        raise EavError(
                            f"owned handle {t!r} escapes via `return` in {op.name!r}; "
                            f"v0.3 has no obligation-carrying out type (README ss15.6, "
                            f"WS2-044)",
                            row.line, code="SS3044C",
                        )


def _validate_islands(program: Program) -> None:
    """README ss16 / WS3-024: an island `body <kind>` must match the entity's
    declared type (SqlText→sql, JsonText→json, HtmlTemplate→html); a `json` island
    must be valid JSON; a `sql` island's `?` placeholder count must equal the
    executing call's parameter-arg count."""
    import json as _json
    kind_for_type = {"SqlText": "sql", "JsonText": "json", "HtmlTemplate": "html"}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("storage", "htmlTemplate"):
            continue
        body = ent.fact("body")
        if not body or not body.payload:
            continue
        kind = body.payload[0]
        type_row = ent.fact("type")
        declared = (type_row.payload[0] if type_row and type_row.payload
                    else ("HtmlTemplate" if ent.kind == "htmlTemplate" else None))
        expected = kind_for_type.get(declared)
        if expected is not None and kind != expected:
            raise EavError(
                f"{ent.name!r} body kind {kind!r} does not match declared type "
                f"{declared!r} (expected {expected!r}, README ss16, WS3-024)",
                body.line, code="SS3024",
            )
        content = "\n".join(program.islands.get((ent.name, kind), []))
        if kind == "json" and content.strip():
            try:
                _json.loads(content)
            except ValueError:
                raise EavError(
                    f"{ent.name!r} json island is not valid JSON (README ss16, "
                    f"WS3-024)",
                    body.line, code="SS3024J",
                )
        if kind == "sql":
            placeholders = content.count("?")
            for cn in program.order:
                call = program.entities[cn]
                if call.kind not in ("call", "task"):
                    continue
                passes = any(
                    len(a.payload) >= 3 and a.payload[2] == ent.name
                    and a.payload[0] in ("sql", "query")
                    for a in call.facts("arg")
                )
                if not passes:
                    continue
                params = [
                    a for a in call.facts("arg")
                    if a.payload and a.payload[0] not in
                    ("sql", "query", "database", "db", "statement")
                ]
                # README ss16 / WS3-024: the placeholder/arg-count check applies to
                # calls that pass params inline. A prepared statement
                # (`sqlite.prepareStatement`) that binds its `?` parameters through
                # separate `bind*` calls passes no inline params, so it is exempt;
                # but a prepare that DOES pass inline params is still checked.
                inv = call.fact("invokes")
                if (inv and inv.payload
                        and inv.payload[0].endswith(".prepareStatement")
                        and not params):
                    continue
                if len(params) != placeholders:
                    raise EavError(
                        f"sql island {ent.name!r} has {placeholders} `?` "
                        f"placeholder(s) but call {call.name!r} passes "
                        f"{len(params)} parameter arg(s) (README ss16, WS3-024)",
                        call.line, code="SS3024Q",
                    )


_EXACT_NUMERIC_TYPES = ("Decimal", "Money")
_FLOAT_TYPES = ("Float32", "Float64")


def _validate_numeric_precision(program: Program) -> None:
    """X-093 / README §10.6: keep exact money/decimal values out of binary Float
    arithmetic. A `decimal.*` op given a Float operand, or a Float `math.*` op
    given a `Decimal`/`Money` operand, is a hard error (SS3093) — the two number
    worlds must not be silently mixed (0.1 is not exact in Float). (The Float
    equality footgun is a separate warning, SS3094, in `lint`.)"""
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        arg_types = [(a.payload[0], a.payload[1]) for a in ent.facts("arg")
                     if len(a.payload) >= 2]
        if target.startswith("decimal."):
            for slot, typ in arg_types:
                if typ in _FLOAT_TYPES:
                    raise EavError(
                        f"call {ent.name!r} passes a {typ} operand {slot!r} to "
                        f"exact {target!r}; decimal/money math has no Float operand "
                        f"(README §10.6)",
                        ent.line, code="SS3093")
        elif target.startswith("math.") and "Float" in target:
            for slot, typ in arg_types:
                if typ in _EXACT_NUMERIC_TYPES:
                    raise EavError(
                        f"call {ent.name!r} routes an exact {typ} operand {slot!r} "
                        f"through Float arithmetic {target!r}; compute money/decimal "
                        f"values with `decimal.*` (README §10.6)",
                        ent.line, code="SS3093")


_TRUST_LABELS = ("rawExternal", "validated", "trustedInternal", "secret")
_UNTRUSTED_AT_SINK = ("rawExternal", "secret")


def _sink_key(ent: Entity) -> str:
    """The name a call's `invokes` uses to reach this sink: an intrinsic is
    reached by its dotted `target`, a user op/function by its entity name."""
    if ent.kind == "intrinsic":
        t = ent.fact("target")
        if t and t.payload:
            return t.payload[0]
    return ent.name


def _validate_trust_flow(program: Program) -> None:
    """X-070 / README §16/§26: typed trust/taint flow. A type carries a trust
    label (`typeTrust <T> rawExternal|validated|trustedInternal|secret`).
    Untrusted input enters as `rawExternal` and becomes trusted only by crossing a
    declared trust boundary (a validator whose output type is `validated`/
    `trustedInternal`). An operation marks a trust-sensitive sink parameter with
    `trustConstraint arg <slot>`; passing a value whose type is `rawExternal` (or
    `secret`) to that slot without a boundary is a hard error (SS3070). Trust is a
    property of the value's declared type, so it propagates over the explicit
    out→arg dataflow without aliasing."""
    label_of = {}
    for n in program.order:
        ent = program.entities[n]
        for r in ent.facts("typeTrust"):
            if r.payload and r.payload[0] in _TRUST_LABELS:
                label_of[ent.name] = r.payload[0]
            elif r.payload:
                raise EavError(
                    f"typeTrust on {ent.name!r} has unknown label {r.payload[0]!r}; "
                    f"expected one of {', '.join(_TRUST_LABELS)} (README §16)",
                    r.line, code="SS3070")
    if not label_of:
        return
    # which arg slots of each operation are trust-sensitive sinks
    sink_slots = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("operation", "function", "intrinsic"):
            continue
        slots = {r.payload[1] for r in ent.facts("trustConstraint")
                 if len(r.payload) >= 2 and r.payload[0] == "arg"}
        if slots:
            sink_slots[_sink_key(ent)] = slots
    if not sink_slots:
        return
    for n in program.order:
        call = program.entities[n]
        if call.kind not in ("call", "task"):
            continue
        inv = call.fact("invokes")
        callee = inv.payload[0] if inv and inv.payload else ""
        slots = sink_slots.get(callee)
        if not slots:
            continue
        for a in call.facts("arg"):
            if len(a.payload) >= 3 and a.payload[0] in slots:
                lbl = label_of.get(a.payload[1])
                if lbl in _UNTRUSTED_AT_SINK:
                    raise EavError(
                        f"call {call.name!r} passes {a.payload[2]!r} (type "
                        f"{a.payload[1]!r}, trust `{lbl}`) into the trust-sensitive "
                        f"slot {a.payload[0]!r} of {callee!r} without a validation "
                        f"boundary (README §16/§26)",
                        call.line, code="SS3070")


def _validate_sink_typing(program: Program) -> None:
    """X-071 / README §16/§30.2.2: every interpreting sink (SQL/HTML/path/URL/…)
    declares the trusted type it requires with `trustConstraint arg <slot>
    <TrustedType>`. The arg must then BE that trusted type (or a
    `validated`/`trustedInternal`-labeled type) — a plain `String` is rejected,
    and a value assembled by `string.concat` may never reach a sink (no
    string-built queries/markup). Hard error SS3071. (`rawExternal`/`secret` into
    a sink is SS3070, X-070.)"""
    label_of = {}
    for n in program.order:
        for r in program.entities[n].facts("typeTrust"):
            if r.payload and r.payload[0] in _TRUST_LABELS:
                label_of[program.entities[n].name] = r.payload[0]
    string_built = set()
    for n in program.order:
        ent = program.entities[n]
        if ent.kind in ("call", "task"):
            inv = ent.fact("invokes")
            if inv and inv.payload and inv.payload[0] == "string.concat":
                for o in ent.facts("out"):
                    if o.payload:
                        string_built.add(o.payload[0])
    # sinks with a REQUIRED trusted type: `trustConstraint arg <slot> <Type>`
    sink_required = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("operation", "function", "intrinsic"):
            continue
        req = {r.payload[1]: r.payload[2] for r in ent.facts("trustConstraint")
               if len(r.payload) >= 3 and r.payload[0] == "arg"}
        if req:
            sink_required[_sink_key(ent)] = req
    if not sink_required:
        return
    for n in program.order:
        call = program.entities[n]
        if call.kind not in ("call", "task"):
            continue
        inv = call.fact("invokes")
        callee = inv.payload[0] if inv and inv.payload else ""
        req = sink_required.get(callee)
        if not req:
            continue
        for a in call.facts("arg"):
            if len(a.payload) < 3 or a.payload[0] not in req:
                continue
            slot, argtype, value = a.payload[0], a.payload[1], a.payload[2]
            required = req[slot]
            if value in string_built:
                raise EavError(
                    f"call {call.name!r} passes a string-built value {value!r} into "
                    f"the {required} sink slot {slot!r} of {callee!r}; build the "
                    f"trusted type, never concatenate interpreter input "
                    f"(README §16/§30.2.2)",
                    call.line, code="SS3071")
            if argtype != required and label_of.get(argtype) not in (
                    "validated", "trustedInternal"):
                raise EavError(
                    f"call {call.name!r} passes {value!r} (type {argtype!r}) into the "
                    f"{required} sink slot {slot!r} of {callee!r}; a raw/untyped value "
                    f"must become a {required} at a trust boundary first "
                    f"(README §16)",
                    call.line, code="SS3071")


_OBSERVABLE_SINK_TARGETS = (
    "console.writeLine", "console.writeIntegerLine", "console.writeFloatLine",
)


def _is_observable_sink(target: str) -> bool:
    # console writes and any log.* call surface a value to a human-readable channel
    return target in _OBSERVABLE_SINK_TARGETS or target.startswith("log.")


def _is_literal_token(tok: str) -> bool:
    if tok.startswith('"'):
        return True
    t = tok.lstrip("-")
    return t.replace(".", "", 1).isdigit() or tok in ("true", "false", "yes", "no")


def _validate_secret_flow(program: Program) -> None:
    """X-072 / README §30.1.1, §8: a `typeTrust secret` value is usable
    (verify/sign/TLS) but never *observable*. Passing a secret-typed value to an
    observable sink (console/log) is a hard error (SS3072), and a secret-typed
    binding may not be initialized from a source literal ("no hardcoded secrets" —
    load it from a capability-gated source). Because secrets can never reach an
    observable/transcript sink, there is nothing to leak into a capturedOutputReplay
    transcript — the compile-time block is stronger than runtime redaction."""
    secret_types = {program.entities[n].name for n in program.order
                    for r in program.entities[n].facts("typeTrust")
                    if r.payload and r.payload[0] == "secret"}
    if not secret_types:
        return
    for n in program.order:
        ent = program.entities[n]
        # no hardcoded secrets: a secret-typed storage/let initialized from a literal
        if ent.kind == "storage":
            tr, vr = ent.fact("type"), ent.fact("value")
            if (tr and tr.payload and tr.payload[0] in secret_types
                    and vr and vr.payload and _is_literal_token(vr.payload[0])):
                raise EavError(
                    f"storage {ent.name!r} is a secret type initialized from a literal "
                    f"{vr.payload[0]!r}; load secrets from a capability-gated source, "
                    f"never a source literal (README §8)",
                    ent.line, code="SS3072")
        if ent.kind in ("operation", "function"):
            for r in ent.facts("let"):
                if (len(r.payload) >= 4 and r.payload[2] in secret_types
                        and _is_literal_token(r.payload[3])):
                    raise EavError(
                        f"binding {r.payload[0]!r} in {ent.name!r} is a secret type "
                        f"initialized from a literal {r.payload[3]!r}; load secrets from "
                        f"a capability-gated source (README §8)",
                        r.line, code="SS3072")
        # no observable secrets: a secret-typed arg into a console/log sink
        if ent.kind in ("call", "task"):
            inv = ent.fact("invokes")
            target = inv.payload[0] if inv and inv.payload else ""
            if _is_observable_sink(target):
                for a in ent.facts("arg"):
                    if len(a.payload) >= 2 and a.payload[1] in secret_types:
                        raise EavError(
                            f"call {ent.name!r} writes a secret value {a.payload[2]!r} "
                            f"to the observable sink {target!r}; a secret is usable but "
                            f"never observable (README §30.1.1)",
                            ent.line, code="SS3072")
            # X-074: a secret may be compared only in constant time. A
            # `math.*`/`compare.*` equality on a secret operand leaks via timing.
            if ((target.startswith("math.") or target.startswith("compare."))
                    and "qual" in target):  # equal / notEqual / Equal
                for a in ent.facts("arg"):
                    if len(a.payload) >= 2 and a.payload[1] in secret_types:
                        raise EavError(
                            f"call {ent.name!r} compares a secret {a.payload[2]!r} with "
                            f"{target!r}; secrets compare only via "
                            f"`crypto.equalConstantTime` (timing side-channel, README §13)",
                            ent.line, code="SS3074")


_DECODE_TARGETS = (
    "json.parse", "json.decode", "json.createDocument", "codec.decode",
)


def _validate_decode_limits(program: Program) -> None:
    """X-077 / README §16: decoding untrusted input must be bounded. A decode
    call (`json.parse`/`json.decode`/`json.createDocument`/`codec.decode`) whose
    input is a `rawExternal`-typed value must carry a `limit maximumBytes <n>` row
    so malformed/hostile input cannot exhaust memory (deserialization-DoS). Missing
    the limit is a hard error (SS3077)."""
    raw_types = {program.entities[n].name for n in program.order
                 for r in program.entities[n].facts("typeTrust")
                 if r.payload and r.payload[0] == "rawExternal"}
    if not raw_types:
        return
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if target not in _DECODE_TARGETS:
            continue
        feeds_untrusted = any(len(a.payload) >= 2 and a.payload[1] in raw_types
                              for a in ent.facts("arg"))
        if not feeds_untrusted:
            continue
        has_byte_limit = any(l.payload and l.payload[0] == "maximumBytes"
                             for l in ent.facts("limit"))
        if not has_byte_limit:
            raise EavError(
                f"call {ent.name!r} decodes untrusted input with {target!r} but "
                f"declares no `limit maximumBytes <n>`; bound untrusted decoding so "
                f"hostile input cannot exhaust memory (README §16)",
                ent.line, code="SS3077")


def _validate_time_safety(program: Program) -> None:
    """X-095 / README §30.5.3: time-safety typing. `WallTime` (UTC/display) and
    `MonotonicInstant` (durations/timeouts) are distinct. Measuring elapsed time
    or doing naive calendar arithmetic on `WallTime` is a hard error — wall-clock
    time has no arithmetic; subtract `MonotonicInstant`s for a duration, or use an
    explicit timezone conversion for calendar math. (Both are 64-bit, Y2038-safe.)"""
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if not (target.startswith("math.")):
            continue
        for a in ent.facts("arg"):
            if len(a.payload) >= 2 and a.payload[1] == "WallTime":
                raise EavError(
                    f"call {ent.name!r} applies {target!r} to a `WallTime` operand "
                    f"{a.payload[0]!r}; wall-clock time has no arithmetic — use a "
                    f"`MonotonicInstant` for durations or an explicit timezone "
                    f"conversion for calendar math (README §30.5.3)",
                    ent.line, code="SS3095",
                )


def _validate_view_lifetimes(program: Program) -> None:
    """WS1-111 / README §32.1 #9: resources clean up; **views** borrow and never
    clean. A call/task whose `out` carries a `borrows <resource>` row is a view:
    - it may not also `owns`/`cleanedBy` (a view does not clean) — SS1566;
    - a `mayEscape no` view may not be returned out of its operation (it would
      outlive the borrowed source) — SS1560.
    This is a lifetime/escape checker over the explicit out→return dataflow, not a
    borrow checker. (A *resource* without cleanup is already SS1503/SS3900.)"""
    # which op owns each call/task
    owner_of = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind in ("call", "task"):
            owner = ent.fact("in")
            if owner and owner.payload:
                owner_of[ent.name] = owner.payload[0]
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task") or ent.fact("borrows") is None:
            continue  # only views (a `borrows` row) are checked here
        if ent.fact("owns") is not None or ent.fact("cleanedBy") is not None:
            raise EavError(
                f"{ent.kind} {ent.name!r} borrows a resource but also declares "
                f"{'owns' if ent.fact('owns') else 'cleanedBy'} — a view does not "
                f"clean up (README §32.1 #9)",
                ent.line, code="SS1566")
        me = ent.fact("mayEscape")
        if not (me and me.payload and me.payload[0] == "no"):
            continue
        out = ent.fact("out")
        view_value = out.payload[0] if out and out.payload else None
        op = program.entities.get(owner_of.get(ent.name))
        if view_value is None or op is None:
            continue
        for row in op.rows:
            if row.predicate == "return" and view_value in row.payload:
                raise EavError(
                    f"view {view_value!r} (borrowed by {ent.name!r}) is `mayEscape no` "
                    f"but is returned out of {op.name!r}; it would outlive its "
                    f"borrowed source (README §32.1 #9)",
                    row.line, code="SS1560")


def _validate_transfer_moves(program: Program) -> None:
    """WS1-113 / README §32.1 #9: ownership transfer is source data. Passing an
    owned handle to a call transfers it only when the row says so — `arg <slot>
    <type> <value> consumes yes` or a call-level `takesOwnership <value>`;
    otherwise the call borrows it and the caller keeps ownership. Once a handle is
    consumed (moved), reusing it is a use-after-move hard error (SS1564). The walk
    is linear over the op's step order and stays conservative across labels (a
    label between the move and the use may be a different path)."""
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        calls = {
            program.entities[c].name: program.entities[c]
            for c in program.order
            if program.entities[c].kind in ("call", "task")
            and (program.entities[c].fact("in") or Row("", "", [], 0)).payload[:1] == [op.name]
        }
        owned: set = set()
        for c in calls.values():
            for o in c.facts("owns"):
                if o.payload:
                    owned.add(o.payload[0])
        if not owned:
            continue
        label_idx = [i for i, r in enumerate(op.rows) if r.label is not None]

        def _uses(call, handle):
            return any(len(a.payload) >= 3 and a.payload[2] == handle
                       for a in call.facts("arg"))

        def _consumed_by(call):
            out: set = set()
            for a in call.facts("arg"):
                p = a.payload
                if (len(p) >= 5 and p[3] == "consumes" and p[4] in ("yes", "true", "1")
                        and p[2] in owned):
                    out.add(p[2])
            for t in call.facts("takesOwnership"):
                if t.payload and t.payload[0] in owned:
                    out.add(t.payload[0])
            return out

        moved: dict = {}  # handle -> row index where it was consumed
        for i, row in enumerate(op.rows):
            if row.predicate in ("do", "start", "join", "poll") and row.payload:
                call = calls.get(row.payload[0])
                if call is None:
                    continue
                for h, mi in moved.items():
                    if _uses(call, h) and not any(mi < li <= i for li in label_idx):
                        raise EavError(
                            f"owned handle {h!r} is used by {call.name!r} in {op.name!r} "
                            f"after it was consumed (moved) — ownership has transferred to "
                            f"the earlier callee (README §32.1 #9)",
                            row.line, code="SS1564")
                for h in _consumed_by(call):
                    moved[h] = i
            elif row.predicate == "return":
                for h, mi in moved.items():
                    if h in row.payload and not any(mi < li <= i for li in label_idx):
                        raise EavError(
                            f"owned handle {h!r} is returned from {op.name!r} after it was "
                            f"consumed (moved) — ownership has transferred away "
                            f"(README §32.1 #9)",
                            row.line, code="SS1564")


def _validate_html_trust(program: Program) -> None:
    """README ss16/ss26 / WS3-025: `HtmlTrustedFragment` bypasses auto-escaping,
    so it may be minted only at the `html.trustFragment` trust boundary. A call
    producing an `HtmlTrustedFragment` from any other target is rejected. (The
    HtmlFragment/HtmlTrustedFragment newtypes are non-interchangeable via the §10
    no-coercion rule, SS3710.)"""
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        out = ent.fact("out")
        if out and len(out.payload) >= 2 and out.payload[1] == "HtmlTrustedFragment":
            inv = ent.fact("invokes")
            target = inv.payload[0] if inv and inv.payload else ""
            if target != "html.trustFragment":
                raise EavError(
                    f"call {ent.name!r} produces an HtmlTrustedFragment from "
                    f"{target!r}; only `html.trustFragment` may mint a trusted "
                    f"fragment (README ss16/ss26, WS3-025)",
                    ent.line, code="SS3025",
                )


def _validate_reserved_targets(program: Program) -> None:
    """README ss7/ss27 / WS3-044: `target windowsGui` is reserved but unspecified
    in v0.3 — using it is a hard compile error (GUI module not defined), not a
    silent fallthrough."""
    for proj in program.of_kind("project"):
        for t in proj.facts("target"):
            if t.payload and t.payload[0] == "windowsGui":
                raise EavError(
                    f"project {proj.name!r} targets `windowsGui`, which is reserved "
                    f"but not defined in v0.3 — the GUI module is unspecified "
                    f"(README ss27, WS3-044)",
                    t.line, code="SS0744",
                )


def _validate_storage_mutation(program: Program) -> None:
    """README ss12 / ss17 #29 / WS1-085: a call `out` targeting a module `storage`
    entity rebinds it; targeting an `immutable` storage entity is a hard error."""
    storages = _storage_entities(program)
    for n in program.order:
        call = program.entities[n]
        if call.kind not in ("call", "task"):
            continue
        out = call.fact("out")
        if not (out and out.payload):
            continue
        st = storages.get(out.payload[0])
        if st is None or not _is_module_storage(st):
            continue
        mut = st.fact("mutability")
        if mut and mut.payload and mut.payload[0] == "immutable":
            raise EavError(
                f"call {call.name!r} rebinds immutable module storage "
                f"{out.payload[0]!r} via out; declare it `mutability mutable` "
                f"(README ss12, ss17 #29, WS1-085)",
                call.line, code="SS1085",
            )


def _validate_set_targets(program: Program) -> None:
    """README ss12: a `set NAME VALUE` step assigns to a mutable binding. NAME must
    be a mutable local (`let NAME mutable …`) of the owning op or a mutable module
    `storage` entity; an immutable target, or an unknown name, is a hard error."""
    storages = _storage_entities(program)
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        local_mut = {
            r.payload[0]: r.payload[1]
            for r in op.facts("let")
            if len(r.payload) >= 2 and r.payload[1] in ("mutable", "immutable")
        }
        for row in op.rows:
            if row.predicate != "set" or not row.payload:
                continue
            name = row.payload[0]
            if len(row.payload) < 2:
                raise EavError(
                    f"`set {name}` needs a value (README ss12)",
                    row.line, code="SS1087",
                )
            if name in local_mut:
                if local_mut[name] == "immutable":
                    raise EavError(
                        f"`set {name}` targets immutable `let {name}`; declare it "
                        f"`let {name} mutable …` (README ss12)",
                        row.line, code="SS1087",
                    )
                continue
            st = storages.get(name)
            if st is not None and _is_module_storage(st):
                mut = st.fact("mutability")
                if mut and mut.payload and mut.payload[0] == "immutable":
                    raise EavError(
                        f"`set {name}` targets immutable module storage {name!r}; "
                        f"declare it `mutability mutable` (README ss12)",
                        row.line, code="SS1087",
                    )
                continue
            raise EavError(
                f"`set {name}` targets {name!r}, which is not a mutable local of "
                f"{op.name!r} or a mutable module storage entity (README ss12)",
                row.line, code="SS1087",
            )


def _validate_return_exactness(program: Program) -> None:
    """README ss10 / WS1-029: an explicitly-written `arg`/`let` type position may
    annotate a base-typed binding to an alias (visible, not silent). But a `return`
    writes no type, so a bare return into an alias `out` requires an *exact* type
    match — returning the base type (or a sibling alias of the same base) where the
    `out` is the alias newtype is rejected (the alias does not coerce here)."""
    alias_map = {
        a.name: a.fact("for").payload[0]
        for a in program.of_kind("alias")
        if a.fact("for") and a.fact("for").payload
    }
    if not alias_map:
        return
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        out_row = op.fact("out")
        if not (out_row and out_row.payload) or out_row.payload[0] == "Result":
            continue
        out_type = out_row.payload[0]
        btypes: dict = {}
        for r in op.facts("in"):
            if len(r.payload) >= 2:
                btypes[r.payload[0]] = r.payload[1]
        for r in op.facts("let"):
            if len(r.payload) >= 3:
                btypes[r.payload[0]] = r.payload[2]
        for cn in program.order:
            call = program.entities[cn]
            owner = call.fact("in")
            if (call.kind in ("call", "task") and owner and owner.payload
                    and owner.payload[0] == op.name):
                o = call.fact("out")
                if o and len(o.payload) >= 2 and o.payload[0] != "Result":
                    btypes[o.payload[0]] = o.payload[1]
        for row in op.rows:
            if row.predicate != "return":
                continue
            for v in (t for t in row.payload
                      if t not in ("value", "ok", "error", "nil", "void")):
                bt = btypes.get(v)
                if bt is None or bt == out_type:
                    continue
                if _resolve_alias(bt, alias_map) == _resolve_alias(out_type, alias_map):
                    raise EavError(
                        f"bare `return {v}` (type {bt!r}) into {op.name!r} out "
                        f"{out_type!r}: a return writes no type, so it must match "
                        f"exactly; an alias does not coerce here (README ss10, WS1-029)",
                        row.line, code="SS1029",
                    )


def _validate_variant_positions(program: Program) -> None:
    """README ss10 / WS1-028: a bare enum variant is valid only in a
    type-directed position (arg value, let initializer, return value). A branch
    condition is a Bool / comparison position, never type-directed, so a bare
    variant name there is a hard error."""
    variants: set = set()
    for e in program.of_kind("enum"):
        for v in e.facts("variant"):
            if v.payload:
                variants.add(v.payload[0])
    if not variants:
        return
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        local = {r.payload[0] for r in op.facts("in") if r.payload}
        local |= {r.payload[0] for r in op.facts("let") if r.payload}
        for row in op.rows:
            if row.predicate != "branch" or not row.payload:
                continue
            guard = row.payload[0]
            operands: list = []
            if guard in ("if", "ifFalse") and len(row.payload) >= 2:
                operands.append(row.payload[1])
            elif guard in ("ifValue", "ifOut") and len(row.payload) >= 4:
                operands += [row.payload[1], row.payload[3]]
            for tok in operands:
                if tok in variants and tok not in local:
                    raise EavError(
                        f"bare variant {tok!r} used in a branch condition — a "
                        f"variant is valid only in a type-directed position "
                        f"(arg/let/return, README ss10, WS1-028)",
                        row.line, code="SS1028",
                    )


def _validate_variant_payload_bind(program: Program) -> None:
    """README ss17 #53: `bind PAYLOAD` on a `branch ifVariant` row is valid only
    when the matched variant declares a payload. Binding a payloadless variant is
    a hard error."""
    has_payload: dict = {}
    var_owner: dict = {}
    for e in program.of_kind("enum"):
        for v in e.facts("variant"):
            if v.payload:
                has_payload[(e.name, v.payload[0])] = len(v.payload) >= 2
                var_owner.setdefault(v.payload[0], set()).add(e.name)
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        for row in op.rows:
            p = row.payload
            if (row.predicate == "branch" and p and p[0] == "ifVariant"
                    and "bind" in p and len(p) >= 3):
                variant = p[2]
                enums = var_owner.get(variant, set())
                if len(enums) == 1:
                    ename = next(iter(enums))
                    if not has_payload.get((ename, variant), False):
                        raise EavError(
                            f"`branch ifVariant … {variant} bind …`: variant "
                            f"{variant!r} of {ename} is payloadless; `bind` requires "
                            f"a data-carrying variant (README ss17 #53)",
                            row.line, code="SS1354",
                        )


def _validate_entry_scope(program: Program) -> None:
    """README ss25 / WS2-050: a binding is in scope only after it is produced.
    Checked over each operation's *entry prefix* (the rows before the first
    label), where textual order equals execution order so there are no false
    positives from jumps:

    - a call's `out` binding is in scope only after the `do`/`join`/`poll` that
      runs it (`out` referenced before its `do` is unbound), and
    - a `catch` variable is in scope only on the matching `ifError` label path,
      so referencing it on the straight-line success path is unbound.

    (`join` before `start` is enforced separately in `_validate_async_lifecycle`.)"""
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        owned = [
            program.entities[c] for c in program.order
            if program.entities[c].kind in ("call", "task")
            and (program.entities[c].fact("in") or Row("", "", [], 0)).payload[:1] == [op.name]
        ]
        # WS2-050 is about call-result (`out`) and `catch` scope specifically;
        # plain `let` ordering is governed by `_validate_let_forward_refs`.
        # Only consider a binding whose producing `do`/`join`/`poll` actually
        # appears in the entry prefix — a *missing* producer is a different rule
        # (e.g. cleanup-worker / unactivated-call) and must not be preempted.
        prefix = []
        for row in op.rows:
            if row.label is not None:
                break
            prefix.append(row)
        activated = {
            r.payload[0] for r in prefix
            if r.predicate in ("do", "start", "join", "poll") and r.payload
        }
        # An out naming a module storage entity *rebinds* a pre-existing global
        # (WS1-085), not a fresh call-result binding — it is in scope before the
        # call, so it is not subject to the produced-before-use rule.
        module_storage_names = {
            program.entities[s].name for s in program.order
            if program.entities[s].kind == "storage"
            and (program.entities[s].fact("scope") or Row("", "", [], 0)).payload[:1] == ["module"]
        }
        live_out: set = set()
        live_catch: set = set()
        for c in owned:
            if c.name not in activated:
                continue
            o = c.fact("out")
            if (o and o.payload and o.payload[0] != "Result"
                    and o.payload[0] not in module_storage_names):
                live_out.add(o.payload[0])
            ct = c.fact("catch")
            if ct and ct.payload:
                live_catch.add(ct.payload[0])
        universe = live_out | live_catch
        bound = {r.payload[0] for r in op.facts("in") if r.payload}
        args_of = {
            call.name: [a.payload[2] for a in call.facts("arg") if len(a.payload) >= 3]
            for call in owned
        }
        for row in prefix:
            p = row.payload
            refs: list = []
            if row.predicate in ("do", "start", "join", "poll") and p:
                refs += args_of.get(p[0], [])
            elif row.predicate == "return":
                refs += [t for t in p if t not in ("value", "ok", "error", "nil", "void")]
            elif row.predicate == "branch" and p:
                g = p[0]
                if g in ("if", "ifFalse", "ifVariant") and len(p) >= 2:
                    refs.append(p[1])
                elif g in ("ifValue", "ifOut") and len(p) >= 4:
                    refs += [p[1], p[3]]
            elif row.predicate == "let" and len(p) >= 4:
                refs.append(p[3])
            for r in refs:
                if r in universe and r not in bound:
                    why = ("a `catch` variable in scope only on the `ifError` path"
                           if r in live_catch else
                           "a call result in scope only after its `do`/`join`")
                    raise EavError(
                        f"{r!r} is used before it is bound in {op.name!r}: it is {why} "
                        f"(README ss25, WS2-050)",
                        row.line, code="SS2502",
                    )
            # produce bindings for the next rows
            if row.predicate in ("do", "start", "join", "poll") and p:
                call = program.entities.get(p[0])
                o = call.fact("out") if call else None
                if o and o.payload and o.payload[0] != "Result":
                    bound.add(o.payload[0])
            elif row.predicate == "let" and p:
                bound.add(p[0])


def _validate_binding_consistency(program: Program) -> None:
    """README ss13 / WS1-064: a value reaching a shared label must have the same
    name and type on every predecessor path (definite assignment).

    `let` names cannot shadow (see `_validate_no_shadow`), so the only way a name
    acquires two declared types within one operation is by being bound on
    distinct branches that merge at a label — once via `let`, once via a call
    `out`, or by two different calls' `out`. A merge that binds one name to
    incompatible types is a definite-assignment error."""
    binds: dict = {}  # opName -> {bindName -> {type -> line}}
    for n in program.order:
        op = program.entities[n]
        if op.kind in ("operation", "function"):
            d = binds.setdefault(op.name, {})
            for r in op.facts("let"):
                if len(r.payload) >= 3:
                    d.setdefault(r.payload[0], {}).setdefault(r.payload[2], r.line)
    for n in program.order:
        ent = program.entities[n]
        if ent.kind in ("call", "task"):
            owner = ent.fact("in")
            outr = ent.fact("out")
            if (owner and owner.payload and outr and len(outr.payload) >= 2
                    and outr.payload[0] != "Result"):
                d = binds.setdefault(owner.payload[0], {})
                d.setdefault(outr.payload[0], {}).setdefault(outr.payload[1], ent.line)
    for opname, d in binds.items():
        for name, types in d.items():
            if len(types) > 1:
                line = min(types.values())
                raise EavError(
                    f"binding {name!r} in {opname!r} is assigned incompatible types "
                    f"{sorted(types)} across paths; a value reaching a shared label "
                    f"must have one type on every predecessor (README ss13, WS1-064)",
                    line, code="SS1064",
                )


def _validate_async(op: Entity) -> None:
    """A `start` step requires `async yes` (README ss11): you can't start a task
    in a synchronous operation."""
    arow = op.fact("async")
    is_async = bool(arow and arow.payload and arow.payload[0] == "yes")
    if not is_async and any(r.predicate == "start" for r in op.rows):
        raise EavError(
            f"operation {op.name!r} has a `start` step but is not `async yes` "
            f"(README ss11)",
            op.line,
            code="SS1140",
        )
    _validate_async_lifecycle(op)


def _validate_async_lifecycle(op: Entity) -> None:
    """Task lifecycle (README ss13, ss17 #20/#21/#22): every started task is
    resolved (join/poll/cancel/detach); `cancel` needs a prior `start`;
    `ifCanceled` needs the task to be `cancel`-ed."""
    started = {r.payload[0] for r in op.rows if r.predicate == "start" and r.payload}
    resolved = {
        r.payload[0]
        for r in op.rows
        if r.predicate in ("join", "poll", "cancel", "detach") and r.payload
    }
    canceled = {r.payload[0] for r in op.rows if r.predicate == "cancel" and r.payload}
    for r in op.rows:
        if r.predicate == "cancel" and r.payload and r.payload[0] not in started:
            raise EavError(
                f"`cancel {r.payload[0]}` has no prior `start` (README ss17 #21)",
                r.line, code="SS1321",
            )
        if (r.predicate == "branch" and len(r.payload) >= 2
                and r.payload[0] == "ifCanceled" and r.payload[1] not in canceled):
            raise EavError(
                f"`branch ifCanceled {r.payload[1]}` needs the task to be "
                f"`cancel`-ed (README ss17 #22)",
                r.line, code="SS1322",
            )
    for task in started - resolved:
        raise EavError(
            f"started task {task!r} is never resolved (join/poll/cancel/detach) "
            f"before return (README ss17 #20)",
            op.line, code="SS1320",
        )
    # Ordered lifecycle (README ss13/ss15.5): join needs a prior start; an
    # `ifError TASK` needs a prior `join` (a task's error is read after join).
    started_so_far: set = set()
    joined_so_far: set = set()
    for row in op.rows:
        if row.predicate == "start" and row.payload:
            started_so_far.add(row.payload[0])
        elif row.predicate == "join" and row.payload:
            if row.payload[0] not in started_so_far:
                raise EavError(
                    f"`join {row.payload[0]}` has no prior `start` (README ss15.5)",
                    row.line, code="SS1323",
                )
            joined_so_far.add(row.payload[0])
        elif (row.predicate == "branch" and len(row.payload) >= 2
              and row.payload[0] == "ifError" and row.payload[1] in started):
            if row.payload[1] not in joined_so_far:
                raise EavError(
                    f"`branch ifError {row.payload[1]}` reads a task's error before "
                    f"`join` (README ss13/ss15.5)",
                    row.line, code="SS1324",
                )


def _validate_let_forward_refs(op: Entity) -> None:
    """`let` initializers may not forward-reference a later `let` (README ss12):
    bindings are positional, defined before use."""
    let_rows = [r for r in op.facts("let") if r.payload]
    index = {r.payload[0]: i for i, r in enumerate(let_rows)}
    for i, r in enumerate(let_rows):
        if len(r.payload) > 3:
            v = r.payload[3]
            if v in index and index[v] > i:
                raise EavError(
                    f"`let {r.payload[0]}` forward-references {v!r}, declared later "
                    f"(README ss12); bindings are positional",
                    r.line, code="SS1203",
                )


def _validate_no_shadow(op: Entity) -> None:
    """Binding names must not shadow (README ss17 #47): a `let` may not reuse a
    parameter name or another `let` name in the same operation."""
    seen: dict[str, str] = {}
    for r in op.facts("in"):
        if r.payload:
            seen[r.payload[0]] = "input"
    for r in op.facts("let"):
        if not r.payload:
            continue
        nm = r.payload[0]
        if nm in seen:
            raise EavError(
                f"binding {nm!r} shadows an existing {seen[nm]} in {op.name!r} "
                f"(README ss17 #47)",
                r.line,
            )
        seen[nm] = "let"


def _op_has_steps(op: Entity) -> bool:
    return any(r.label is not None or r.predicate in STEP_PREDICATES for r in op.rows)


def _op_body_kind(op: Entity) -> str:
    """`steps` (default), `runtimeBinding`, or `intrinsic` (README ss11)."""
    row = op.fact("body")
    if row and row.payload:
        return row.payload[0]
    return "steps"


def _validate_body_kind(op: Entity) -> None:
    """An operation with a `runtimeBinding`/`intrinsic` body has no step rows;
    `body steps` (default) is the stepful form (README ss11)."""
    kind = _op_body_kind(op)
    if kind in ("runtimeBinding", "intrinsic") and _op_has_steps(op):
        raise EavError(
            f"operation {op.name!r} has a `{kind}` body but also carries step rows "
            f"(README ss11); a non-step body has no steps",
            op.line,
        )
    if kind not in ("steps", "runtimeBinding", "intrinsic"):
        raise EavError(
            f"operation {op.name!r} body must be steps|runtimeBinding|intrinsic, "
            f"got {kind!r} (README ss11)",
            op.line,
        )


def _validate_return_arity(op: Entity) -> None:
    """Return arity must match `out` (README ss13, ss17 #10): void -> no value;
    single -> one value; Result -> exactly one filled slot and one `nil`."""
    out_row = op.fact("out")
    is_result = bool(out_row and out_row.payload and out_row.payload[0] == "Result")
    is_void = out_row is None or not out_row.payload
    for row in op.rows:
        if row.predicate != "return":
            continue
        p = [t for t in row.payload if t != "void"]
        if is_void:
            if p:
                raise EavError(
                    f"{op.name!r} returns void but `return` carries a value "
                    f"(README ss17 #10)",
                    row.line, code="SS1060",
                )
        elif is_result:
            nils = p.count("nil")
            if len(p) != 2 or nils != 1:
                raise EavError(
                    f"{op.name!r} returns Result: `return` needs exactly one value "
                    f"and one `nil` (README ss13, ss17 #10), got {row.payload!r}",
                    row.line, code="SS1060",
                )
        else:
            if len(p) != 1 or "nil" in p:
                raise EavError(
                    f"{op.name!r} returns a single value: `return` needs exactly "
                    f"one value (README ss17 #10), got {row.payload!r}",
                    row.line, code="SS1060",
                )


def _validate_labels(op: Entity, program: Program) -> None:
    """Label invariants (README ss13, ss17 #11/#12/#13): every goto/branch target
    has exactly one `at` definition; duplicate labels error; dead labels warn."""
    defs: list[str] = []
    for row in op.rows:
        if row.label is not None:
            if row.label in defs:
                raise EavError(
                    f"duplicate label {row.label!r} in operation {op.name!r} "
                    f"(README ss17 #12)",
                    row.line,
                )
            defs.append(row.label)
    refs: set[str] = set()
    for row in op.rows:
        if row.predicate == "goto" and row.payload:
            refs.add(row.payload[0])
        elif row.predicate == "branch" and "goto" in row.payload:
            gi = row.payload.index("goto")
            if gi + 1 < len(row.payload):
                refs.add(row.payload[gi + 1])
    for ref in refs:
        if ref not in defs:
            raise EavError(
                f"goto/branch target {ref!r} has no `at {ref}` label in operation "
                f"{op.name!r} (README ss17 #11)",
                op.line,
                code="SS1311",
            )
    for label in defs:
        if label not in refs:
            program.warnings.append(
                f"{op.name}: label {label!r} is never targeted (dead label, "
                f"README ss17 #13)"
            )


def _validate_enum(ent: Entity) -> None:
    """Enum invariants (README ss10): unique variants; `repr` only on payloadless
    variants; all-or-none `repr`."""
    _check_unique_labels(ent, "variant", "variant name", "README ss10/ss17 #29")
    payloadless: set[str] = set()
    data_carrying: set[str] = set()
    for row in ent.facts("variant"):
        if not row.payload:
            continue
        name = row.payload[0]
        if len(row.payload) >= 2 and row.payload[1] != "Void":
            data_carrying.add(name)
        else:
            payloadless.add(name)
    repr_rows = ent.facts("repr")
    repr_names = {r.payload[0] for r in repr_rows if r.payload}
    for row in repr_rows:
        if not row.payload:
            continue
        vname = row.payload[0]
        if vname in data_carrying:
            raise EavError(
                f"`repr` is only valid on payloadless variants; {vname!r} carries "
                f"a payload (README ss10)",
                row.line,
            )
        if vname not in payloadless:
            raise EavError(
                f"`repr` names unknown variant {vname!r} of enum {ent.name!r} "
                f"(README ss10)",
                row.line,
            )
    if repr_names and repr_names != payloadless:
        missing = payloadless - repr_names
        raise EavError(
            f"enum {ent.name!r} mixes explicit and auto-assigned discriminants; "
            f"add `repr` for {sorted(missing)} or remove all (README ss10)",
            ent.line,
        )


# --------------------------------------------------------------------------
# 3. Lowering to LLVM IR  (README ss18 — EAV -> LLVM IR via llvmlite)
# --------------------------------------------------------------------------
#
# eavc is its own backend. A parsed EAV Program is lowered *directly* to an
# llvmlite ir.Module and JIT-executed (or emitted as textual IR). There is no
# transpilation to any other surface syntax. The console program model runs end
# to end here; webServer/wasm/sqlite/http targets are rejected with a clear
# message rather than mis-lowered.

from llvmlite import ir
import llvmlite.binding as llvm

# Built-in primitive types (README ss10) — usable with no `is` row. `Byte` is a
# primitive synonym for `UInt8`.
PRIMITIVE_TYPES = {
    "Int8", "Int16", "Int32", "Int64",
    "UInt8", "UInt16", "UInt32", "UInt64",
    "Float32", "Float64",
    "Bool", "String", "Void", "Byte",
}

# EAV primitive type name -> llvmlite IR type. `ExitCode` is the conventional
# `alias for Int32`, resolved here so console entries lower without a type row.
_PRIMITIVE_IR = {
    "Int8": ir.IntType(8), "UInt8": ir.IntType(8), "Byte": ir.IntType(8),
    "Int16": ir.IntType(16), "UInt16": ir.IntType(16),
    "Int32": ir.IntType(32), "UInt32": ir.IntType(32), "ExitCode": ir.IntType(32),
    "Int64": ir.IntType(64), "UInt64": ir.IntType(64),
    "Float32": ir.FloatType(), "Float64": ir.DoubleType(),
    "Bool": ir.IntType(1),
    "String": ir.IntType(8).as_pointer(),
    "Void": ir.VoidType(),
    # FFI interim (README ss30.4.1): opaque handles are carried as UInt64.
    "OpaquePointer": ir.IntType(64),
    "FileHandle": ir.IntType(64),
}

_FLOAT_TYPE_NAMES = {"Float32", "Float64"}

# Integer math targets -> llvmlite IRBuilder binary-op method names.
_INT_BINOPS = {
    "math.addInt64": "add", "math.subtractInt64": "sub",
    "math.multiplyInt64": "mul", "math.divideInt64": "sdiv",
    "math.moduloInt64": "srem",
}
# Float math targets -> IRBuilder fp binary-op method names.
_FLOAT_BINOPS = {
    "math.addFloat64": "fadd", "math.subtractFloat64": "fsub",
    "math.multiplyFloat64": "fmul", "math.divideFloat64": "fdiv",
    "math.fmodFloat64": "frem",
}
# Integer comparison targets -> icmp_signed predicate.
_INT_CMP = {
    "math.equalInt64": "==", "math.notEqualInt64": "!=",
    "math.lessThanInt64": "<", "math.lessThanOrEqualInt64": "<=",
    "math.greaterThanInt64": ">", "math.greaterThanOrEqualInt64": ">=",
}
# Float comparison targets. Ordered comparisons are false when either operand is
# NaN; `notEquals` is unordered so NaN != NaN is true (IEEE-754, README ss10.6).
_FLOAT_CMP_ORDERED = {
    "math.equalFloat64": "==",
    "math.lessThanFloat64": "<", "math.lessThanOrEqualFloat64": "<=",
    "math.greaterThanFloat64": ">", "math.greaterThanOrEqualFloat64": ">=",
}
_FLOAT_CMP_UNORDERED = {"math.notEqualFloat64": "!="}
# WS3-100: pure Float64 unary ops -> LLVM math intrinsics (one `value` arg).
_FLOAT_UNARY_INTRIN = {
    "math.sqrtFloat64": "llvm.sqrt", "math.absFloat64": "llvm.fabs",
    "math.floorFloat64": "llvm.floor", "math.ceilFloat64": "llvm.ceil",
    "math.truncFloat64": "llvm.trunc", "math.roundFloat64": "llvm.round",
    "math.sinFloat64": "llvm.sin", "math.cosFloat64": "llvm.cos",
    "math.expFloat64": "llvm.exp", "math.exp2Float64": "llvm.exp2",
    "math.logFloat64": "llvm.log", "math.log2Float64": "llvm.log2",
    "math.log10Float64": "llvm.log10",
}
# Pure Float64 binary ops -> LLVM intrinsics (`left`,`right`).
_FLOAT_BINARY_INTRIN = {
    "math.powFloat64": "llvm.pow", "math.minFloat64": "llvm.minnum",
    "math.maxFloat64": "llvm.maxnum", "math.copysignFloat64": "llvm.copysign",
}
# Int64 unary ops -> LLVM integer intrinsics (one `value` arg).
_INT_UNARY_INTRIN = {
    "math.popcountInt64": "llvm.ctpop",
    "math.countTrailingZerosInt64": "llvm.cttz",
    "math.countLeadingZerosInt64": "llvm.ctlz",
}
# Int64 ops computed directly from arithmetic/bit/select (no intrinsic).
_MATH_COMPUTED = {
    "math.negateInt64", "math.absInt64", "math.squareInt64", "math.signInt64",
    "math.isEvenInt64", "math.isOddInt64", "math.isPowerOfTwoInt64",
    "math.minInt64", "math.maxInt64", "math.absDiffInt64",
}


def _norm_type(tok: str) -> str:
    """Normalize a type token. `Byte` is a synonym for `UInt8` (README ss10)."""
    return "UInt8" if tok == "Byte" else tok


def _parse_int_literal_value(tok: str) -> int:
    neg = tok.startswith("-")
    body = (tok[1:] if neg else tok).replace("_", "")
    if body.startswith("0x"):
        value = int(body, 16)
    elif body.startswith("0b"):
        value = int(body, 2)
    else:
        value = int(body, 10)
    return -value if neg else value


def _decode_string_literal(tok: str) -> bytes:
    """Decode an EAV string literal token (with quotes) to NUL-terminated bytes,
    applying the README ss2 escape rules."""
    if not (len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"'):
        raise EavError(f"expected a string literal, got {tok!r}")
    inner = tok[1:-1]
    out = bytearray()
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\":
            esc = inner[i + 1]
            if esc == "n":
                out.append(0x0A); i += 2
            elif esc == "t":
                out.append(0x09); i += 2
            elif esc == '"':
                out.append(0x22); i += 2
            elif esc == "\\":
                out.append(0x5C); i += 2
            elif esc == "x":
                out.append(int(inner[i + 2:i + 4], 16)); i += 4
            else:
                raise EavError(f"unsupported escape \\{esc} in {tok!r}")
        else:
            out.extend(ch.encode("utf-8")); i += 1
    out.append(0)
    return bytes(out)


class EavCodegen:
    """Generate an llvmlite ``ir.Module`` from a parsed EAV ``Program`` (console
    program model). Construction is cheap; call :meth:`generate` to emit IR."""

    def __init__(self, program: Program):
        self.program = program
        self.module = ir.Module(name="eav")
        self.module.triple = llvm.get_default_triple()
        self.aliases = {
            a.name: a.fact("for").payload[0]
            for a in program.of_kind("alias")
            if a.fact("for") and a.fact("for").payload
        }
        self.functions: dict[str, ir.Function] = {}
        self._runtime: dict[str, ir.Function] = {}
        # README ss28.1 / WS3-041: project constants are project-global read-only
        # values, visible by bare name in any module.
        self.project_constants = {
            c.payload[0]: (c.payload[1], c.payload[2:])
            for proj in program.of_kind("project")
            for c in proj.facts("constant")
            if len(c.payload) >= 3
        }
        self._str_count = 0
        self.entry_name = "main"
        self._record_layouts: dict[str, tuple] = {}  # name -> (struct_type, field_names)

    # -- types --
    def resolve_type_name(self, name: str) -> str:
        seen: set[str] = set()
        while name in self.aliases and name not in seen:
            seen.add(name)
            name = self.aliases[name]
        return _norm_type(name)

    def ir_type(self, name: str) -> ir.Type:
        resolved = self.resolve_type_name(name)
        if resolved in _PRIMITIVE_IR:
            return _PRIMITIVE_IR[resolved]
        ent = self.program.entities.get(resolved)
        if ent is not None and ent.kind == "record":
            return self._record_layout(ent)[0]
        if ent is not None and ent.kind in ("enum", "error"):
            return ir.IntType(32)  # discriminant (errors are enum-equivalent, §9)
        if ent is not None and ent.kind == "operationType":
            orow = ent.fact("out")
            ret = self.ir_type(orow.payload[0]) if orow and orow.payload else ir.VoidType()
            params = [self.ir_type(r.payload[0]) for r in ent.facts("in") if r.payload]
            return ir.FunctionType(ret, params).as_pointer()  # function pointer (§33.9)
        # other named types: opaque i64 handle in the console model.
        return ir.IntType(64)

    def _error_cases(self, error_name: str) -> list:
        return [
            self.program.entities[n].name
            for n in self.program.order
            if self.program.entities[n].kind == "errorCase"
            and (self.program.entities[n].fact("of") or Row("", "", [], 0)).payload[:1] == [error_name]
        ]

    def _const_value(self, resolved: str, tokens: list):
        """A module-storage initializer constant (README ss12, ss30.2.1):
        effect-free literal of a primitive type."""
        tok = tokens[0] if tokens else "0"
        if resolved == "String":
            return self.global_string(_decode_string_literal(tok))
        if resolved == "Bool":
            return ir.Constant(ir.IntType(1), 1 if tok == "true" else 0)
        if resolved in _FLOAT_TYPE_NAMES:
            return ir.Constant(_PRIMITIVE_IR[resolved], float(tok))
        return ir.Constant(_PRIMITIVE_IR.get(resolved, ir.IntType(64)),
                           _parse_int_literal_value(tok))

    def _literal_tokens_for_storage(self, st: Entity, seen=None):
        """Resolve a module-storage initializer to its underlying literal tokens,
        following references to other immutable module-storage constants — a
        constant may alias another module's constant value (README ss12; e.g.
        `firstTodoClassName String doneTodoClassName`)."""
        seen = seen or set()
        if st.name in seen:
            raise EavError(f"cyclic storage initializer through {st.name!r}",
                           st.line, code="SS1212")
        seen.add(st.name)
        value_row = st.fact("value")
        if not value_row or not value_row.payload:
            return None
        tok = value_row.payload[0]
        ref = self.program.entities.get(tok)
        if ref is not None and ref.kind == "storage":
            return self._literal_tokens_for_storage(ref, seen)
        return value_row.payload

    def _make_module_storage(self, st: Entity) -> None:
        type_row = st.fact("type")
        if not type_row or not type_row.payload:
            return
        resolved = self.resolve_type_name(type_row.payload[0])
        # README ss30.3.2: `literalSource` embeds a file's bytes at compile time;
        # `literalDigest sha256 <hex>` verifies the asset hash.
        src_row = st.fact("literalSource")
        if src_row and src_row.payload:
            dig = st.fact("literalDigest")
            expected = dig.payload[-1] if dig and dig.payload else None
            data = embed_literal_source(src_row.payload[0].strip('"'), expected)
            self.module_storage[st.name] = (self.global_string(data + b"\x00"), "String")
            return
        if resolved not in _PRIMITIVE_IR:
            return  # non-primitive module storage (e.g. SqlText) not modeled here
        gv = ir.GlobalVariable(self.module, _PRIMITIVE_IR[resolved], name=st.name)
        gv.linkage = "internal"
        mut = st.fact("mutability")
        gv.global_constant = bool(
            mut and mut.payload and mut.payload[0] == "immutable"
        )
        value_tokens = self._literal_tokens_for_storage(st)
        if value_tokens:
            gv.initializer = self._const_value(resolved, value_tokens)
        else:
            gv.initializer = ir.Constant(_PRIMITIVE_IR[resolved], 0)
        self.module_storage[st.name] = (gv, type_row.payload[0])

    def _record_layout(self, rec: Entity):
        """(LLVM struct type, ordered field names) for a record, cached."""
        if rec.name in self._record_layouts:
            return self._record_layouts[rec.name]
        fields = [f for f in rec.facts("field") if len(f.payload) >= 2]
        struct_t = ir.LiteralStructType([self.ir_type(f.payload[1]) for f in fields])
        names = [f.payload[0] for f in fields]
        self._record_layouts[rec.name] = (struct_t, names)
        return self._record_layouts[rec.name]

    def is_float_type(self, name: str) -> bool:
        return self.resolve_type_name(name) in _FLOAT_TYPE_NAMES

    # -- runtime + constants --
    def runtime(self, name: str) -> ir.Function:
        if name in self._runtime:
            return self._runtime[name]
        i32 = ir.IntType(32)
        i8p = ir.IntType(8).as_pointer()
        if name == "puts":
            fn = ir.Function(self.module, ir.FunctionType(i32, [i8p]), name="puts")
        elif name == "printf":
            fn = ir.Function(
                self.module, ir.FunctionType(i32, [i8p], var_arg=True), name="printf"
            )
        elif name == "trap":
            fn = ir.Function(
                self.module, ir.FunctionType(ir.VoidType(), []), name="llvm.trap"
            )
        elif name == "strlen":
            fn = ir.Function(self.module, ir.FunctionType(ir.IntType(64), [i8p]),
                             name="strlen")
        elif name == "malloc":
            fn = ir.Function(self.module, ir.FunctionType(i8p, [ir.IntType(64)]),
                             name="malloc")
        elif name in ("strcpy", "strcat"):
            fn = ir.Function(self.module, ir.FunctionType(i8p, [i8p, i8p]), name=name)
        elif name == "strcmp":
            fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [i8p, i8p]),
                             name="strcmp")
        elif name == "eav_http_html_escape":
            fn = ir.Function(self.module, ir.FunctionType(i8p, [i8p]),
                             name="eav_http_html_escape")
        else:
            raise EavError(f"no runtime declaration for {name!r}")
        self._runtime[name] = fn
        return fn

    def global_string(self, data: bytes) -> ir.Value:
        self._str_count += 1
        typ = ir.ArrayType(ir.IntType(8), len(data))
        gv = ir.GlobalVariable(self.module, typ, name=f".str.{self._str_count}")
        gv.global_constant = True
        gv.linkage = "internal"
        gv.initializer = ir.Constant(typ, bytearray(data))
        z = ir.Constant(ir.IntType(32), 0)
        return gv.gep([z, z])

    # -- entry --
    def generate(self) -> ir.Module:
        projects = self.program.of_kind("project")
        if not projects:
            raise EavError("no `project` entity found (README ss7)")
        project = projects[0]
        target_row = project.fact("target")
        target = target_row.payload[0] if target_row and target_row.payload else "console"
        if target != "console":
            raise EavError(
                "the LLVM console code generator only supports `target console`, "
                f"got {target!r}; webServer/wasm lowering is out of scope (todos WS3)"
            )
        entry_row = project.fact("entry")
        if entry_row and entry_row.payload:
            self.entry_name = entry_row.payload[0]
        self.module_storage: dict[str, tuple] = {}
        for st in self.program.of_kind("storage"):
            scope = st.fact("scope")
            if scope and scope.payload and scope.payload[0] == "module":
                self._make_module_storage(st)
        # README ss30.3.2: a `configure` op runs at build time and is excluded
        # from the runtime build — it is not lowered into the program module.
        configure_ops = {
            p.payload[0]
            for proj in self.program.of_kind("project")
            for p in proj.facts("configure")
            if p.payload
        }
        ops = [o for o in self.program.of_kind("operation") if o.name not in configure_ops]
        for op in ops:
            self.functions[op.name] = self._declare_function(op)
        for op in ops:
            # runtimeBinding/intrinsic bodies stay bare declarations (extern);
            # full FFI symbol binding is WS3-052/053. Only `body steps` defines.
            if _op_body_kind(op) == "steps":
                self._define_function(op)
        return self.module

    def _signature(self, op: Entity):
        out_row = op.fact("out")
        if out_row and out_row.payload:
            head = out_row.payload[0]
            ret = self.ir_type(out_row.payload[1] if head == "Result" else head)
        else:
            ret = ir.VoidType()
        params = [
            self.ir_type(r.payload[1]) for r in op.facts("in") if len(r.payload) >= 2
        ]
        return ret, params

    def _declare_function(self, op: Entity) -> ir.Function:
        ret, params = self._signature(op)
        body = op.fact("body")
        if (body and body.payload and body.payload[0] == "runtimeBinding"
                and len(body.payload) >= 2):
            # README ss11/ss26: a `body runtimeBinding <symbol>` operation lowers
            # to a bare extern declaration named after the bound ABI symbol;
            # calls to the operation become direct calls to that symbol. The
            # compiler stays domain-agnostic — it carries no per-library (sqlite/
            # http/…) knowledge; the stdlib `.sem`/`.semsig` owns that. The op's
            # `in` types are the parameter ABI and `out` the return ABI.
            symbol = body.payload[1]
            existing = self.module.globals.get(symbol)
            if isinstance(existing, ir.Function):
                return existing
            return ir.Function(
                self.module, ir.FunctionType(ret, params), name=symbol
            )
        fn = ir.Function(self.module, ir.FunctionType(ret, params), name=op.name)
        for param, in_row in zip(fn.args, op.facts("in")):
            param.name = in_row.payload[0]
        return fn

    # -- body --
    def _define_function(self, op: Entity) -> None:
        fn = self.functions[op.name]
        let_mut = {
            r.payload[0]: r.payload[1]
            for r in op.facts("let")
            if len(r.payload) >= 2 and r.payload[1] in ("mutable", "immutable")
        }
        sym: dict[str, tuple] = {}
        for param, in_row in zip(fn.args, op.facts("in")):
            sym[in_row.payload[0]] = ("val", param)

        entry = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry)

        # Pre-create a block per label so forward gotos resolve.
        label_blocks: dict[str, ir.Block] = {}
        for row in op.rows:
            if row.label is not None and row.label not in label_blocks:
                label_blocks[row.label] = fn.append_basic_block(row.label)

        self._call_info: dict[str, tuple] = {}
        self._cont_count = 0
        self._defers: list = []  # cleanup entities, in registration order

        for row in op.rows:
            if row.label is not None:
                blk = label_blocks[row.label]
                if not builder.block.is_terminated:
                    builder.branch(blk)
                builder = ir.IRBuilder(blk)
                builder = self._emit_step(op, fn, row, builder, sym, let_mut, label_blocks)
                continue
            if row.predicate == "let":
                self._emit_let(op, row, builder, sym, let_mut)
                continue
            if row.predicate in STEP_PREDICATES:
                builder = self._emit_step(
                    op, fn, row, builder, sym, let_mut, label_blocks
                )

        if not builder.block.is_terminated:
            self._emit_defers(builder, sym)
            ret = fn.function_type.return_type
            if isinstance(ret, ir.VoidType):
                builder.ret_void()
            else:
                builder.ret(ir.Constant(ret, 0))

    def _emit_let(self, op, row, builder, sym, let_mut) -> None:
        p = row.payload
        name, mut, typ = p[0], p[1], p[2]
        value = self._literal_or_ref(typ, " ".join(p[3:]), builder, sym) if len(p) > 3 else None
        if mut == "mutable":
            slot = builder.alloca(self.ir_type(typ), name=name)
            if value is not None:
                builder.store(value, slot)
            sym[name] = ("ptr", slot, typ)
        else:
            sym[name] = ("val", value)

    def _literal_or_ref(self, type_name: str, tok: str, builder, sym):
        if tok in sym:
            return self._load(sym[tok], builder)
        resolved = self.resolve_type_name(type_name)
        # README ss33.9: an operationType-typed value referencing an operation is
        # that operation's function pointer (a first-class operation reference).
        ote = self.program.entities.get(resolved)
        if ote is not None and ote.kind == "operationType" and tok in self.functions:
            return self.functions[tok]
        # README ss10 / WS1-028: a bare enum variant is valid in a type-directed
        # position (the resolved type is that enum); it lowers to its discriminant.
        # README ss28.1 / WS3-041: a bare reference to a project constant reads
        # its build value (project-global, no import).
        if tok in getattr(self, "project_constants", {}):
            ctype, cval = self.project_constants[tok]
            return self._const_value(self.resolve_type_name(ctype), list(cval))
        if ote is not None and ote.kind == "enum":
            variants = [v.payload[0] for v in ote.facts("variant") if v.payload]
            if tok in variants:
                repr_map = {
                    r.payload[0]: int(r.payload[1])
                    for r in ote.facts("repr") if len(r.payload) >= 2
                }
                disc = repr_map.get(tok, variants.index(tok))
                return ir.Constant(ir.IntType(32), disc)
        # Not a binding -> must be a well-formed literal of the expected type.
        # An unbound identifier here is an out-of-scope reference (README ss25).
        if resolved == "String":
            if tok.startswith('"'):
                return self.global_string(_decode_string_literal(tok))
            raise EavError(f"{tok!r} is not in scope (expected a String binding)")
        if resolved == "Bool":
            if tok in ("true", "false"):  # README ss4: yes/no are not Bool values
                return ir.Constant(ir.IntType(1), 1 if tok == "true" else 0)
            raise EavError(f"{tok!r} is not in scope (expected a Bool binding or true/false)")
        if resolved in _FLOAT_TYPE_NAMES:
            if tok[:1].isdigit() or tok[:1] in "-.":
                return ir.Constant(self.ir_type(type_name), float(tok))
            raise EavError(f"{tok!r} is not in scope (expected a Float binding)")
        if tok[:1].isdigit() or (tok[:1] == "-" and tok[1:2].isdigit()):
            return ir.Constant(self.ir_type(type_name), _parse_int_literal_value(tok))
        raise EavError(f"{tok!r} is not in scope (expected an integer binding)")

    def _load(self, entry, builder):
        if entry[0] == "val":
            return entry[1]
        return builder.load(entry[1])

    def _read_module_storage(self, tok, builder):
        ref = self.module_storage[tok][0]
        # A GlobalVariable holds a value to load; a literalSource embeds an i8*
        # pointer directly (no load).
        return builder.load(ref) if isinstance(ref, ir.GlobalVariable) else ref

    def _resolve(self, tok, type_name, builder, sym):
        if tok in sym:
            return self._load(sym[tok], builder)
        if tok in getattr(self, "module_storage", {}):
            return self._read_module_storage(tok, builder)
        return self._literal_or_ref(type_name, tok, builder, sym)

    def _resolve_as(self, tok, llvm_type, builder, sym):
        """Resolve a token to a value of a given LLVM type: load a binding, or
        build a literal constant of that type (used by ifValue/ifOut operands)."""
        if tok in sym:
            return self._load(sym[tok], builder)
        if tok in getattr(self, "module_storage", {}):
            return self._read_module_storage(tok, builder)
        if isinstance(llvm_type, (ir.FloatType, ir.DoubleType)):
            return ir.Constant(llvm_type, float(tok))
        return ir.Constant(llvm_type, _parse_int_literal_value(tok))

    def _emit_step(self, op, fn, row, builder, sym, let_mut, label_blocks):
        pred = row.predicate
        p = row.payload
        if pred == "do":
            call = self.program.entities.get(p[0]) if p else None
            if call is None or call.kind not in ("call", "task"):
                raise EavError(f"`do {p[0] if p else ''}` is not a call (README ss15)", row.line)
            if call.kind == "task":
                raise EavError(
                    f"`do {p[0]}` activates a task; tasks use start/join "
                    "(README ss34.4)",
                    row.line,
                )
            self._emit_call(call, builder, sym, let_mut)
            return builder
        if pred == "goto":
            builder.branch(label_blocks[p[0]])
            return builder
        if pred == "set":
            # README ss12: `set NAME VALUE` assigns VALUE to a mutable local
            # (`let NAME mutable …`) or a mutable module-storage entity. Unlike an
            # out-rebind, the value may be a literal/const/binding — there is no
            # producing call. Lowered to a store into the alloca / global.
            name = p[0]
            value_tok = " ".join(p[1:])
            binding = sym.get(name)
            if binding is not None and binding[0] == "ptr":
                typ = binding[2]
                builder.store(self._resolve(value_tok, typ, builder, sym), binding[1])
                return builder
            ms = getattr(self, "module_storage", {}).get(name)
            if ms is not None and isinstance(ms[0], ir.GlobalVariable):
                builder.store(self._resolve(value_tok, ms[1], builder, sym), ms[0])
                return builder
            raise EavError(
                f"`set {name}` targets {name!r}, which is not a mutable local "
                f"(`let {name} mutable …`) or mutable module storage (README ss12)",
                row.line, code="SS1087",
            )
        if pred == "defer":
            # README ss15.6: register the cleanup; its worker runs (in reverse
            # registration order) before each return. Nothing emitted here.
            cleanup = self.program.entities.get(p[0]) if p else None
            if cleanup is not None:
                self._defers.append(cleanup)
            return builder
        if pred == "start":
            # Single-thread backend (README ss13): `start` runs the task eagerly;
            # its result is available immediately (poll always-ready, join cheap).
            task = self.program.entities.get(p[0]) if p else None
            if task is not None and task.kind == "task":
                self._emit_call(task, builder, sym, let_mut)
            return builder
        if pred in ("join", "poll", "cancel", "detach"):
            # join/poll/cancel/detach: no-ops on the single-thread backend; the
            # task already completed at `start` (README ss13).
            return builder
        if pred == "return":
            return self._emit_return(op, fn, row, builder, sym)
        if pred == "branch":
            return self._emit_branch(fn, row, builder, sym, label_blocks)
        raise EavError(
            f"step `{pred}` is not modeled by the LLVM console code generator "
            "(todos WS1-107 async)",
            row.line,
        )

    def _emit_defers(self, builder, sym) -> None:
        """Run registered defers' worker calls in reverse order (README ss15.6,
        ss33.8). Called immediately before each return / fallthrough exit."""
        for cleanup in reversed(self._defers):
            cr = cleanup.fact("call")
            worker = self.program.entities.get(cr.payload[0]) if cr and cr.payload else None
            if worker is not None and worker.kind in ("call", "task"):
                self._emit_call(worker, builder, sym, {})

    def _emit_return(self, op, fn, row, builder, sym):
        p = row.payload
        ret_ty = fn.function_type.return_type
        self._emit_defers(builder, sym)
        if not p or (len(p) == 1 and p[0] == "void"):
            builder.ret_void()
            return builder
        out_row = op.fact("out")
        type_hint = "Int64"
        if out_row and out_row.payload:
            type_hint = out_row.payload[0] if out_row.payload[0] != "Result" else out_row.payload[1]
        token = p[0] if p[0] not in ("nil",) else (p[1] if len(p) > 1 else p[0])
        builder.ret(self._resolve(token, type_hint, builder, sym))
        return builder

    def _emit_branch(self, fn, row, builder, sym, label_blocks):
        p = row.payload
        guard = p[0]
        if guard == "ifError":
            callee = self.program.entities.get(p[1])
            if callee is None or callee.fact("catch") is None:
                raise EavError(
                    f"`branch ifError {p[1]}` needs {p[1]!r} to be a fallible call "
                    f"with a `catch` row (README ss13, ss17 #6)",
                    row.line,
                    code="SS1041",
                )
            info = self._call_info.get(p[1])
            err = info[1] if info and info[1] is not None else ir.Constant(ir.IntType(1), 0)
            cont = self._new_cont(fn)
            builder.cbranch(err, label_blocks[p[3]], cont)
            return ir.IRBuilder(cont)
        if guard == "if":
            cond = self._resolve(p[1], "Bool", builder, sym)
            cont = self._new_cont(fn)
            builder.cbranch(cond, label_blocks[p[3]], cont)
            return ir.IRBuilder(cont)
        if guard == "ifFalse":
            cond = self._resolve(p[1], "Bool", builder, sym)
            cont = self._new_cont(fn)
            builder.cbranch(cond, cont, label_blocks[p[3]])
            return ir.IRBuilder(cont)
        if guard == "ifVariant":
            # README ss13/ss10.5: `branch ifVariant VALUE VARIANT goto L` narrows a
            # payloadless enum value by comparing its discriminant. (bind PAYLOAD
            # for data-carrying variants is pending.)
            value_tok, variant = p[1], p[2]
            gi = p.index("goto")
            label = p[gi + 1]
            matches = [
                e for e in self.program.of_kind("enum")
                if variant in [v.payload[0] for v in e.facts("variant") if v.payload]
            ]
            if len(matches) != 1:
                raise EavError(
                    f"`ifVariant … {variant}`: variant {variant!r} is unknown or "
                    f"ambiguous across enums (README ss10.5)",
                    row.line, code="SS1352",
                )
            enum_ent = matches[0]
            variants = [v.payload[0] for v in enum_ent.facts("variant") if v.payload]
            repr_map = {r.payload[0]: int(r.payload[1]) for r in enum_ent.facts("repr") if len(r.payload) >= 2}
            disc = repr_map.get(variant, variants.index(variant))
            lv = self._resolve(value_tok, "Int32", builder, sym)
            cond = builder.icmp_signed("==", lv, ir.Constant(ir.IntType(32), disc))
            cont = self._new_cont(fn)
            builder.cbranch(cond, label_blocks[label], cont)
            return ir.IRBuilder(cont)
        if guard in ("ifValue", "ifOut"):
            # README ss13 sugar: `branch ifValue X <cmp> Y goto L` (and `ifOut
            # CALL <cmp> Y`) lower to a comparison + conditional branch.
            gi = p.index("goto")
            label = p[gi + 1]
            left_tok, cmp_tok, right_tok = p[1], p[2], p[3]
            if guard == "ifOut":
                callee = self.program.entities.get(p[1])
                orow = callee.fact("out") if callee else None
                if not (orow and orow.payload):
                    raise EavError(f"`ifOut {p[1]}` needs an `out` binding", row.line)
                left_tok = orow.payload[0]
            preds = {"equals": "==", "notEquals": "!=", "lessThan": "<",
                     "lessThanOrEqual": "<=", "greaterThan": ">",
                     "greaterThanOrEqual": ">="}
            if cmp_tok not in preds:
                raise EavError(f"unknown comparator {cmp_tok!r} in {guard} (README ss13)", row.line)
            lx = self._resolve(left_tok, "Int64", builder, sym)
            ly = self._resolve_as(right_tok, lx.type, builder, sym)
            if isinstance(lx.type, (ir.FloatType, ir.DoubleType)):
                cond = (builder.fcmp_unordered("!=", lx, ly) if cmp_tok == "notEquals"
                        else builder.fcmp_ordered(preds[cmp_tok], lx, ly))
            else:
                cond = builder.icmp_signed(preds[cmp_tok], lx, ly)
            cont = self._new_cont(fn)
            builder.cbranch(cond, label_blocks[label], cont)
            return ir.IRBuilder(cont)
        if guard == "ifReady":
            # README ss13: single-thread tasks are always ready after `start`,
            # so `ifReady` is unconditionally taken; the fallthrough (pending)
            # path is emitted into a fresh, unreachable continuation block.
            builder.branch(label_blocks[p[3]])
            return ir.IRBuilder(self._new_cont(fn))
        if guard in ("ifPending", "ifCanceled"):
            # Never taken on the single-thread backend (never pending; not
            # canceled unless `cancel` ran) — fall through (README ss13).
            return builder
        raise EavError(
            f"branch guard {guard!r} is not modeled by the LLVM console code "
            "generator (todos WS1-066 sugar)",
            row.line,
        )

    def _new_cont(self, fn) -> ir.Block:
        self._cont_count += 1
        return fn.append_basic_block(f"cont{self._cont_count}")

    def _emit_math_computed(self, target, arg, builder):
        """Pure Int64 math ops (WS3-100) computed from arithmetic/bit/select."""
        i64 = ir.IntType(64)
        zero = ir.Constant(i64, 0)
        one = ir.Constant(i64, 1)
        if target == "math.negateInt64":
            return builder.sub(zero, arg("value", "Int64"))
        if target == "math.squareInt64":
            v = arg("value", "Int64")
            return builder.mul(v, v)
        if target == "math.absInt64":
            v = arg("value", "Int64")
            return builder.select(builder.icmp_signed("<", v, zero), builder.sub(zero, v), v)
        if target == "math.signInt64":
            v = arg("value", "Int64")
            return builder.select(
                builder.icmp_signed(">", v, zero), one,
                builder.select(builder.icmp_signed("<", v, zero),
                               ir.Constant(i64, -1), zero))
        if target == "math.isEvenInt64":
            return builder.icmp_signed("==", builder.and_(arg("value", "Int64"), one), zero)
        if target == "math.isOddInt64":
            return builder.icmp_signed("==", builder.and_(arg("value", "Int64"), one), one)
        if target == "math.isPowerOfTwoInt64":
            v = arg("value", "Int64")
            positive = builder.icmp_signed(">", v, zero)
            masked = builder.and_(v, builder.sub(v, one))
            return builder.and_(positive, builder.icmp_signed("==", masked, zero))
        if target == "math.minInt64":
            left, right = arg("left", "Int64"), arg("right", "Int64")
            return builder.select(builder.icmp_signed("<", left, right), left, right)
        if target == "math.maxInt64":
            left, right = arg("left", "Int64"), arg("right", "Int64")
            return builder.select(builder.icmp_signed(">", left, right), left, right)
        if target == "math.absDiffInt64":
            diff = builder.sub(arg("left", "Int64"), arg("right", "Int64"))
            return builder.select(builder.icmp_signed("<", diff, zero),
                                  builder.sub(zero, diff), diff)
        raise EavError(f"unhandled computed math target {target!r}")

    def _concat(self, builder, left, right):
        """Heap-concatenate two NUL-terminated i8* strings (README ss30.2.2)."""
        la = builder.call(self.runtime("strlen"), [left])
        lb = builder.call(self.runtime("strlen"), [right])
        total = builder.add(builder.add(la, lb), ir.Constant(ir.IntType(64), 1))
        buf = builder.call(self.runtime("malloc"), [total])
        builder.call(self.runtime("strcpy"), [buf, left])
        builder.call(self.runtime("strcat"), [buf, right])
        return buf

    def _emit_html_render(self, call, args, builder, sym):
        """Lower `html.render`: interleave the template's literal segments with
        its hole values (text holes auto-escaped, HtmlSafeUrl passed through),
        concatenated into one rendered HTML string (README ss16, X-011)."""
        tmpl_arg = args.get("template")
        tmpl_name = tmpl_arg.payload[2] if tmpl_arg and len(tmpl_arg.payload) >= 3 else None
        island = self.program.islands.get((tmpl_name, "html"), [])
        text = "\n".join(island)
        parts = __import__("re").split(r"\{\{\s*([\w.]+)\s*\}\}", text)
        result = None
        for i, part in enumerate(parts):
            if i % 2 == 0:  # literal segment
                if part == "":
                    continue
                piece = self.global_string(part.encode("utf-8") + b"\x00")
            else:  # hole name -> its (escaped) value
                a = args.get(part)
                if a is None or len(a.payload) < 3:
                    continue
                val = self._resolve(a.payload[2], a.payload[1], builder, sym)
                # Text holes are auto-escaped; pass through values that are already
                # safe HTML: an HtmlSafeUrl, or a rendered/trusted fragment nested
                # into an outer template (escaping it again would corrupt the
                # already-escaped markup). README ss16 §10 fragment newtypes.
                if a.payload[1] not in ("HtmlSafeUrl", "HtmlFragment", "HtmlTrustedFragment"):
                    val = builder.call(self.runtime("eav_http_html_escape"), [val])
                piece = val
            result = piece if result is None else self._concat(builder, result, piece)
        return result if result is not None else self.global_string(b"\x00")

    def _emit_call(self, call, builder, sym, let_mut) -> None:
        target_row = call.fact("invokes")
        if not target_row or not target_row.payload:
            raise EavError(f"call {call.name!r} missing `invokes` (README ss15)", call.line)
        target = target_row.payload[0]
        args = {a.payload[0]: a for a in call.facts("arg")}

        def arg(slot, default_type):
            a = args.get(slot)
            if a is None:
                raise EavError(f"call {call.name!r} missing arg {slot!r}", call.line)
            return self._resolve(a.payload[2], a.payload[1], builder, sym)

        result = None
        err = None
        if target == "console.writeLine":
            res = builder.call(self.runtime("puts"), [arg("text", "String")])
            err = builder.icmp_signed("<", res, ir.Constant(ir.IntType(32), 0))
            result = res
        elif target == "console.writeIntegerLine":
            fmt = self.global_string(b"%lld\n\x00")
            val = arg("value", "Int64")
            if isinstance(val.type, ir.IntType) and val.type.width < 64:
                val = builder.zext(val, ir.IntType(64))  # Bool/narrow -> i64 for %lld
            result = builder.call(self.runtime("printf"), [fmt, val])
        elif target == "assert.equalInt64":
            result = builder.icmp_signed("==", arg("left", "Int64"), arg("right", "Int64"))
        elif target == "assert.true":
            result = arg("value", "Bool")
        elif target == "test.and":
            result = builder.and_(arg("left", "Bool"), arg("right", "Bool"))
        elif target == "console.writeFloatLine":
            fmt = self.global_string(b"%g\n\x00")
            val = arg("value", "Float64")
            result = builder.call(self.runtime("printf"), [fmt, val])
        elif target in ("math.divideInt64", "math.moduloInt64"):
            left = arg("left", "Int64")
            right = arg("right", "Int64")
            self._guard_div_zero(builder, right)
            method = builder.sdiv if target == "math.divideInt64" else builder.srem
            result = method(left, right)
        elif target in _INT_BINOPS:
            method = getattr(builder, _INT_BINOPS[target])
            result = method(arg("left", "Int64"), arg("right", "Int64"))
        elif target in _FLOAT_BINOPS:
            method = getattr(builder, _FLOAT_BINOPS[target])
            result = method(arg("left", "Float64"), arg("right", "Float64"))
        elif target in _INT_CMP:
            result = builder.icmp_signed(
                _INT_CMP[target], arg("left", "Int64"), arg("right", "Int64")
            )
        elif target in _FLOAT_CMP_ORDERED:
            result = builder.fcmp_ordered(
                _FLOAT_CMP_ORDERED[target], arg("left", "Float64"), arg("right", "Float64")
            )
        elif target in _FLOAT_CMP_UNORDERED:
            result = builder.fcmp_unordered(
                _FLOAT_CMP_UNORDERED[target], arg("left", "Float64"), arg("right", "Float64")
            )
        elif target in _FLOAT_UNARY_INTRIN:
            fn = self.module.declare_intrinsic(_FLOAT_UNARY_INTRIN[target], [ir.DoubleType()])
            result = builder.call(fn, [arg("value", "Float64")])
        elif target in _FLOAT_BINARY_INTRIN:
            fn = self.module.declare_intrinsic(_FLOAT_BINARY_INTRIN[target], [ir.DoubleType()])
            result = builder.call(fn, [arg("left", "Float64"), arg("right", "Float64")])
        elif target in _INT_UNARY_INTRIN:
            i64 = ir.IntType(64)
            fn = self.module.declare_intrinsic(_INT_UNARY_INTRIN[target], [i64])
            if target == "math.popcountInt64":
                result = builder.call(fn, [arg("value", "Int64")])
            else:  # cttz/ctlz take (value, is_zero_poison:i1)
                result = builder.call(fn, [arg("value", "Int64"), ir.Constant(ir.IntType(1), 0)])
        elif target in _MATH_COMPUTED:
            result = self._emit_math_computed(target, arg, builder)
        elif target.startswith("compare."):
            result = self._emit_compare(target, args, builder, sym, call)
        elif target.startswith("convert.to"):
            result = self._emit_convert(target, args, builder, sym, call)
        elif target == "string.concat":
            # README ss30.2.2: heap-concatenate two NUL-terminated strings.
            result = self._concat(builder, arg("left", "String"), arg("right", "String"))
        elif target == "html.render":
            # README ss16: render an htmlTemplate island, auto-escaping `{{holes}}`
            # by sink context. Split the template on holes and concat the literal
            # segments with the (escaped) hole values in order.
            result = self._emit_html_render(call, args, builder, sym)
        elif target in sym:
            # README ss33.9: indirect call through an operationType binding.
            fnptr = self._load(sym[target], builder)
            vals = [
                self._resolve(a.payload[2], a.payload[1], builder, sym)
                for a in call.facts("arg")
            ]
            result = builder.call(fnptr, vals)
        elif target in self.functions:
            callee = self.program.entities[target]
            vals = []
            for in_row in callee.facts("in"):
                a = args.get(in_row.payload[0])
                if a is None:
                    raise EavError(
                        f"call {call.name!r} missing arg {in_row.payload[0]!r} for "
                        f"{target!r}",
                        call.line,
                    )
                vals.append(self._resolve(a.payload[2], a.payload[1], builder, sym))
            result = builder.call(self.functions[target], vals)
        else:
            result = self._emit_derived_target(target, call, args, builder, sym)

        self._call_info[call.name] = (result, err)

        # README ss17 #9: bind the catch variable so the error value is in scope
        # at the ifError target (the catch dominates the branch). Modeled as the
        # error discriminant (i32) in the console subset.
        catch_row = call.fact("catch")
        if catch_row and catch_row.payload:
            sym[catch_row.payload[0]] = ("val", ir.Constant(ir.IntType(32), 0))

        out_row = call.fact("out")
        if out_row and out_row.payload and result is not None:
            name = out_row.payload[0]
            if let_mut.get(name) == "immutable":
                raise EavError(
                    f"call {call.name!r} rebinds immutable `let {name}` via out "
                    "(README ss12, ss17 #28); declare it `let mutable`",
                    call.line,
                    code="SS1502",
                )
            if let_mut.get(name) == "mutable":
                builder.store(result, sym[name][1])
            elif name in getattr(self, "module_storage", {}):
                # README ss12 / WS1-085: out naming a (mutable) module storage
                # entity rebinds the global in place.
                ref = self.module_storage[name][0]
                if isinstance(ref, ir.GlobalVariable):
                    builder.store(result, ref)
                else:
                    sym[name] = ("val", result)
            else:
                sym[name] = ("val", result)


    _CMP_OPS = {
        "equal": "==", "notEqual": "!=", "lessThanOrEqual": "<=",
        "greaterThanOrEqual": ">=", "lessThan": "<", "greaterThan": ">",
    }

    def _emit_compare(self, target, args, builder, sym, call):
        """Compiler-derived `compare.<op><Type>` primitive (README ss13). Ordering
        on Bool/enum operands is rejected (Bool/enum are equals-only, ss17 #45)."""
        suffix = target[len("compare."):]
        op = typ = None
        for cand in sorted(self._CMP_OPS, key=len, reverse=True):
            if suffix.startswith(cand):
                op, typ = cand, suffix[len(cand):]
                break
        if op is None or not typ:
            raise EavError(f"unrecognized compare target {target!r}", call.line)
        ordering = op in ("lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual")
        resolved = self.resolve_type_name(typ)
        ent = self.program.entities.get(resolved)
        is_enum = ent is not None and ent.kind == "enum"
        is_record = ent is not None and ent.kind == "record"
        if ordering and (resolved in ("Bool", "String") or is_enum or is_record):
            raise EavError(
                f"{target!r}: Bool, String, enum, and record support "
                f"equals/notEquals only, not ordering (README ss10.6/ss33.7, ss17 #45)",
                call.line,
                code="SS1345",
            )
        left = self._resolve(args["left"].payload[2], typ, builder, sym) if "left" in args else None
        right = self._resolve(args["right"].payload[2], typ, builder, sym) if "right" in args else None
        if left is None or right is None:
            raise EavError(f"{target!r} needs left and right args", call.line)
        if is_record:
            # README ss33.7: records compare by deep fieldwise equality.
            _struct_t, field_names = self._record_layout(ent)
            field_rows = [f for f in ent.facts("field") if len(f.payload) >= 2]
            acc = None
            for i, frow in enumerate(field_rows):
                fl = builder.extract_value(left, i)
                fr = builder.extract_value(right, i)
                if self.is_float_type(frow.payload[1]):
                    feq = builder.fcmp_ordered("==", fl, fr)
                else:
                    feq = builder.icmp_signed("==", fl, fr)
                acc = feq if acc is None else builder.and_(acc, feq)
            if acc is None:
                acc = ir.Constant(ir.IntType(1), 1)
            return acc if op == "equal" else builder.not_(acc)
        if resolved == "String":
            # README ss10.6: String equality is bytewise (strcmp), no normalization.
            cmp = builder.call(self.runtime("strcmp"), [left, right])
            pred = "==" if op == "equal" else "!="
            return builder.icmp_signed(pred, cmp, ir.Constant(ir.IntType(32), 0))
        if self.is_float_type(typ):
            if op == "notEqual":
                return builder.fcmp_unordered("!=", left, right)
            return builder.fcmp_ordered(self._CMP_OPS[op], left, right)
        return builder.icmp_signed(self._CMP_OPS[op], left, right)

    def _emit_convert(self, target, args, builder, sym, call):
        """Explicit numeric conversion `convert.to<Type>` (README ss33.5): int
        widen=sext / narrow=trunc, int->float=sitofp, float->int=fptosi (trunc
        toward zero), float widen/narrow=fpext/fptrunc."""
        dst_name = target[len("convert.to"):]
        dst = self.ir_type(dst_name)
        if not args:
            raise EavError(f"{target!r} needs one input arg", call.line)
        a = next(iter(args.values()))
        src_name = a.payload[1]
        val = self._resolve(a.payload[2], src_name, builder, sym)
        src = val.type
        src_float = self.is_float_type(src_name)
        dst_float = self.resolve_type_name(dst_name) in _FLOAT_TYPE_NAMES
        if src_float and dst_float:
            dst_bits = 64 if self.resolve_type_name(dst_name) == "Float64" else 32
            src_bits = 64 if self.resolve_type_name(src_name) == "Float64" else 32
            if dst_bits == src_bits:
                return val
            return builder.fpext(val, dst) if dst_bits > src_bits else builder.fptrunc(val, dst)
        if src_float and not dst_float:
            return builder.fptosi(val, dst)
        if not src_float and dst_float:
            return builder.sitofp(val, dst)
        # int -> int
        if dst.width > src.width:
            return builder.sext(val, dst)
        if dst.width < src.width:
            return builder.trunc(val, dst)
        return val

    def _guard_div_zero(self, builder, divisor) -> None:
        """Trap on integer divide/modulo by zero (README ss10.6): no UB. Emits a
        zero-check that branches to `llvm.trap`; the builder continues on the
        nonzero path."""
        fn = builder.function
        iszero = builder.icmp_signed("==", divisor, ir.Constant(divisor.type, 0))
        trap_bb = fn.append_basic_block("divByZero")
        cont_bb = fn.append_basic_block("divCont")
        builder.cbranch(iszero, trap_bb, cont_bb)
        tb = ir.IRBuilder(trap_bb)
        tb.call(self.runtime("trap"), [])
        tb.unreachable()
        builder.position_at_end(cont_bb)

    def _emit_derived_target(self, target, call, args, builder, sym):
        """Compiler-derived construction/access targets (README ss10.5): a record
        `<Record>.new`/`<Record>.<field>` and a payloadless `<Enum>.<variant>`."""
        head, _, tail = target.rpartition(".")
        ent = self.program.entities.get(head)
        if ent is not None and ent.kind == "record":
            struct_t, field_names = self._record_layout(ent)
            if tail == "new":
                value = ir.Constant(struct_t, ir.Undefined)
                for idx, fname in enumerate(field_names):
                    a = args.get(fname)
                    if a is None:
                        raise EavError(
                            f"call {call.name!r} to {target!r} is missing field arg "
                            f"{fname!r} (README ss10.5)",
                            call.line,
                        )
                    fval = self._resolve(a.payload[2], a.payload[1], builder, sym)
                    value = builder.insert_value(value, fval, idx)
                return value
            if tail in field_names:
                rec_arg = args.get("record") or next(iter(args.values()), None)
                if rec_arg is None:
                    raise EavError(
                        f"call {call.name!r} to field access {target!r} needs the "
                        f"record as its arg (README ss10.5)",
                        call.line,
                    )
                recval = self._resolve(rec_arg.payload[2], rec_arg.payload[1], builder, sym)
                return builder.extract_value(recval, field_names.index(tail))
            raise EavError(
                f"{target!r}: record {head!r} has no field {tail!r} (README ss10.5)",
                call.line,
            )
        if ent is not None and ent.kind == "enum":
            variants = [v.payload[0] for v in ent.facts("variant") if v.payload]
            if tail not in variants:
                raise EavError(
                    f"{target!r}: enum {head!r} has no variant {tail!r} "
                    f"(README ss10.5)",
                    call.line,
                )
            repr_map = {
                r.payload[0]: int(r.payload[1])
                for r in ent.facts("repr")
                if len(r.payload) >= 2
            }
            disc = repr_map.get(tail, variants.index(tail))
            return ir.Constant(ir.IntType(32), disc)
        if ent is not None and ent.kind == "error":
            # README ss9/ss34: error cases are enum-equivalent — `<Error>.<case>`
            # lowers to the case's discriminant (declaration order).
            cases = self._error_cases(head)
            if tail not in cases:
                raise EavError(
                    f"{target!r}: error {head!r} has no case {tail!r} (README ss9)",
                    call.line,
                )
            return ir.Constant(ir.IntType(32), cases.index(tail))
        raise EavError(
            f"call target {target!r} is not modeled by the LLVM console code "
            "generator (todos WS3 stdlib)",
            call.line,
        )


def lower_to_llvm(program: Program) -> ir.Module:
    """Lower a parsed EAV Program to an llvmlite ir.Module (console model)."""
    return EavCodegen(program).generate()


_NATIVE_INIT_DONE = False


def _ensure_native_init() -> None:
    global _NATIVE_INIT_DONE
    if not _NATIVE_INIT_DONE:
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        _NATIVE_INIT_DONE = True


def _bundle_dir() -> str:
    """Directory holding bundled data (std/, sigs/, runtime/). When frozen by
    PyInstaller (X-025), data lives under sys._MEIPASS; otherwise alongside
    eavc.py."""
    import os
    base = getattr(sys, "_MEIPASS", None)
    return base or os.path.dirname(os.path.abspath(__file__))


def _runtime_dir() -> str:
    import os
    return os.path.join(_bundle_dir(), "runtime")


def _find_c_compiler():
    """Locate a C compiler for building native runtime libraries, mirroring the
    reference toolchain: EAVC_CC, then clang on PATH / the common Windows LLVM
    install, then `zig cc`. Returns a command prefix list or None."""
    import os
    from shutil import which
    env = os.environ.get("EAVC_CC")
    if env:
        return [env] if os.path.exists(env) else env.split()
    clang = which("clang") or (
        "C:/Program Files/LLVM/bin/clang.exe"
        if os.path.exists("C:/Program Files/LLVM/bin/clang.exe") else None
    )
    if clang:
        return [clang]
    zig = which("zig")
    if zig:
        return [zig, "cc"]
    return None


def _shared_lib_suffix() -> str:
    if sys.platform == "win32":
        return ".dll"
    if sys.platform == "darwin":
        return ".dylib"
    return ".so"


def _ensure_runtime_lib(lib: dict):
    """Build (cached) one native runtime library described by runtime/manifest.json
    and return its path, or None if no C compiler is available. The compiler is
    domain-agnostic — it only compiles the `sources` the manifest lists; the
    sqlite/http knowledge lives in those C sources and the `.sem` stdlib."""
    import os
    import subprocess
    rt = _runtime_dir()
    build_dir = os.path.join(rt, "_build")
    out = os.path.join(build_dir, lib["name"] + _shared_lib_suffix())
    sources = [os.path.normpath(os.path.join(rt, s)) for s in lib["sources"]]
    manifest = os.path.join(rt, "manifest.json")
    inputs = [p for p in (sources + [manifest]) if os.path.exists(p)]
    if os.path.exists(out) and all(
        os.path.getmtime(out) >= os.path.getmtime(p) for p in inputs
    ):
        return out  # cached and fresh
    cc = _find_c_compiler()
    if cc is None:
        return None
    os.makedirs(build_dir, exist_ok=True)
    cmd = list(cc) + ["-O2", "-shared", "-o", out] + sources
    for inc in lib.get("include", []):
        cmd.append("-I" + os.path.normpath(os.path.join(rt, inc)))
    for d in lib.get("defines", []):
        cmd.append("-D" + d)
    for libname in lib.get("libs", []):
        cmd.append("-l" + libname)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise EavError(
            f"failed to build runtime library {lib['name']!r}: {proc.stderr.strip()}"
        )
    return out


def _referenced_runtime_symbols(program: Program) -> set:
    """The ABI symbols a program needs: every `body runtimeBinding` symbol, plus
    `eav_http_html_escape` when any call lowers `html.render` (auto-escape)."""
    out: set = set()
    for n in program.order:
        ent = program.entities[n]
        if ent.kind in ("operation", "function"):
            body = ent.fact("body")
            if (body and body.payload and body.payload[0] == "runtimeBinding"
                    and len(body.payload) >= 2):
                out.add(body.payload[1])
        if ent.kind in ("call", "task"):
            inv = ent.fact("invokes")
            if inv and inv.payload and inv.payload[0] == "html.render":
                out.add("eav_http_html_escape")
    return out


def _runtime_libs_for(program: Program) -> list:
    """Native runtime libraries (from runtime/manifest.json) whose `provides`
    prefixes match a runtimeBinding symbol the program references."""
    import json
    import os
    referenced = _referenced_runtime_symbols(program)
    manifest_path = os.path.join(_runtime_dir(), "manifest.json")
    if not referenced or not os.path.exists(manifest_path):
        return []
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    return [
        lib for lib in manifest.get("libraries", [])
        if any(s.startswith(p) for s in referenced for p in lib.get("provides", []))
    ]


def _register_runtime_symbols(program: Program) -> None:
    """Resolve the program's `runtimeBinding` symbols that a native runtime
    library provides, building and loading that library and registering each
    symbol with the JIT. Symbols not matched by any library (e.g. libc `abs`)
    are left to the JIT's default resolver. Driven entirely by
    runtime/manifest.json — no per-library logic in the compiler."""
    import ctypes
    import json
    import os
    referenced = _referenced_runtime_symbols(program)
    if not referenced:
        return
    for lib in _runtime_libs_for(program):
        path = _ensure_runtime_lib(lib)
        prefixes = lib.get("provides", [])
        needed = {s for s in referenced if any(s.startswith(p) for p in prefixes)}
        if path is None:
            raise EavError(
                f"program uses runtime symbols {sorted(needed)} provided by "
                f"{lib['name']!r}, but no C compiler was found to build it "
                f"(set EAVC_CC, or install clang/zig)"
            )
        cdll = ctypes.CDLL(path)
        for sym in needed:
            try:
                addr = ctypes.cast(getattr(cdll, sym), ctypes.c_void_p).value
            except AttributeError:
                continue
            llvm.add_symbol(sym, addr)


def jit_run(program: Program, entry: Optional[str] = None) -> int:
    """JIT-compile and execute an operation; return its exit code. With `entry`
    set, run that operation instead of the project entry (used by the test
    runner). stdout is the C runtime's, flushed when this process exits."""
    import ctypes

    module = lower_to_llvm(program)
    _ensure_native_init()
    _register_runtime_symbols(program)
    mod = llvm.parse_assembly(str(module))
    mod.verify()
    tm = llvm.Target.from_default_triple().create_target_machine()
    engine = llvm.create_mcjit_compiler(mod, tm)
    engine.finalize_object()
    engine.run_static_constructors()
    addr = engine.get_function_address(entry or _entry_name(program))
    cmain = ctypes.CFUNCTYPE(ctypes.c_int)(addr)
    return cmain()


def run_tests(program: Program) -> dict:
    """Execute every `tag test` operation by JIT-running it as an entry and
    treating a 0 exit as a pass (sem.test.v1; WS3-026/WS4-119). Project semantic
    preflight (lint errors) runs first and blocks the runtime lane."""
    diags = lint(program)
    preflight_ok = not any(d.severity == "error" for d in diags)
    lanes = discover_tests(program)
    tests: list = []
    if preflight_ok:
        for lane in sorted(lanes):
            for op in lanes[lane]:
                try:
                    code = jit_run(program, entry=op)
                    status = "pass" if code == 0 else "fail"
                except EavError as exc:
                    status, code = "error", None
                    tests.append({"name": op, "lane": lane, "status": status,
                                  "error": str(exc)})
                    continue
                tests.append({"name": op, "lane": lane, "status": status, "exitCode": code})
    runtime_status = ("not-run" if not preflight_ok
                      else "pass" if all(t["status"] == "pass" for t in tests)
                      else "fail")
    composite = ("blocked" if not preflight_ok
                 else "pass" if runtime_status == "pass" else "fail")
    return {
        "preflightStatus": "ok" if preflight_ok else "lint-diagnostics",
        "runtimeHarnessStatus": runtime_status,
        "compositeStatus": composite,
        "tests": tests,
    }


def _record_run(source: str):
    """Run a program in a clean subprocess, capturing (stdout, exitCode). A fresh
    process is the record substrate: it is exactly the capability-mediated output
    a replay must reproduce."""
    import os
    import subprocess
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "run", "-"],
        input=source, capture_output=True, text=True,
    )
    return proc.stdout, proc.returncode


def captured_output_replay(source: str) -> dict:
    """README ss30.1.1: `mode capturedOutputReplay` determinism mode.

    Record-runs the program (capturing the capability-mediated console
    transcript), confirms the run is deterministic across record runs, then
    serves a side-effect-free *replay* from the recorded transcript — no
    capability effect is re-performed on replay. The transcript wire format is
    intentionally simple (ordered output lines); §30.1.1 leaves it unfrozen in
    v0.3."""
    program = parse(source)
    proj = program.of_kind("project")
    mode = None
    if proj:
        m = proj[0].fact("mode")
        mode = m.payload[0] if m and m.payload else None
    if mode != "capturedOutputReplay":
        raise EavError(
            "captured_output_replay requires `mode capturedOutputReplay` on the "
            "project (README ss30.1.1)"
        )
    out1, exit1 = _record_run(source)
    out2, exit2 = _record_run(source)
    deterministic = (out1 == out2) and (exit1 == exit2)
    transcript = out1.split("\n")[:-1] if out1.endswith("\n") else out1.split("\n")
    return {
        "ok": True,
        "mode": mode,
        "transcript": transcript,
        "exitCode": exit1,
        "deterministic": deterministic,
        # replay re-emits the recorded transcript without executing the program,
        # so no capability-mediated effect is performed: side-effect-free.
        "replayStdout": out1,
        "sideEffectFree": True,
    }


def _entry_name(program: Program) -> str:
    projects = program.of_kind("project")
    if projects:
        row = projects[0].fact("entry")
        if row and row.payload:
            return row.payload[0]
    return "main"


# --------------------------------------------------------------------------
# 4. CLI
# --------------------------------------------------------------------------


def cmd_lex(args) -> int:
    text = _read_source(args.path)
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        toks = tokenize_line(line)
        if toks:
            print(f"{n}: {toks}")
    return 0


def cmd_parse(args) -> int:
    program = parse(_read_source(args.path))
    for name in program.order:
        ent = program.entities[name]
        print(f"{ent.kind} {ent.name}  ({len(ent.rows)} rows)")
    return 0


def cmd_lower(args) -> int:
    """Emit textual LLVM IR for the program."""
    program = parse(_read_source(args.path))
    sys.stdout.write(str(lower_to_llvm(program)))
    return 0


def cmd_run(args) -> int:
    """JIT-compile and execute the program; return its process exit code."""
    program = parse(_read_program_source(args.path))
    sys.stdout.flush()
    return jit_run(program)


def build_executable(program: Program, out_path: str) -> str:
    """Compile a program to a native executable: lower to LLVM IR, then drive a C
    compiler over the IR plus any native runtime sources the program's
    runtimeBinding symbols need (manifest-driven). Returns the exe path."""
    import os
    import subprocess
    import tempfile
    module = lower_to_llvm(program)
    cc = _find_c_compiler()
    if cc is None:
        raise EavError("no C compiler found to build an executable "
                       "(set EAVC_CC, or install clang/zig)")
    rt = _runtime_dir()
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    ll_fd, ll_path = tempfile.mkstemp(suffix=".ll", dir=rt)
    with os.fdopen(ll_fd, "w", encoding="utf-8") as fh:
        fh.write(str(module))
    cmd = list(cc) + ["-O2", ll_path, "-o", out_path]
    for lib in _runtime_libs_for(program):
        for s in lib["sources"]:
            cmd.append(os.path.normpath(os.path.join(rt, s)))
        for inc in lib.get("include", []):
            cmd.append("-I" + os.path.normpath(os.path.join(rt, inc)))
        for d in lib.get("defines", []):
            cmd.append("-D" + d)
        for libname in lib.get("libs", []):
            cmd.append("-l" + libname)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        try:
            os.unlink(ll_path)
        except OSError:
            pass
    if proc.returncode != 0:
        raise EavError(f"native build failed: {proc.stderr.strip()}")
    return out_path


# Versioned JSON surfaces eavc exposes (the sem.*.v1 contract, WS4-111).
SEM_SURFACES = (
    "sem.version.v1", "sem.agentDocs.v1", "sem.skills.v1", "sem.check.v1",
    "sem.readiness.v1", "sem.eval.v1", "sem.deps.v1", "sem.fixPlan.v1",
    "sem.context.v1", "sem.symbols.v1", "sem.patch.v1", "sem.test.v1",
    "sem.size.v1", "sem.dev.v1", "sem.slice.v1", "sem.docs.v1",
    "sem.docsIndex.v1", "sem.docsSearch.v1", "sem.task.v1", "sem.new.v1",
)

EAV_AGENT_RULES = (
    "EAV-Steps: flat semantic tape, one row = one record, column-1 subject, "
    "column-2 predicate. No expressions/infix/parens/commas/braces. Calls are "
    "multi-row (is call / in OP / invokes TARGET / arg / out|catch|discards). "
    "Effects need a covering capability. Use the stable loop: check -> "
    "fix --plan -> patch -> fmt --check -> test. Build/run with `eavc build` / "
    "`eavc run`."
)

EAV_SKILLS = {
    "eav-start": "Load version-matched rules, then inspect with check/graph/slice.",
    "eav-syntax": "Subject-first rows; runtimeBinding for native ABIs; §26 .semsig.",
    "eav-run": "JIT with `eavc run`; native exe with `eavc build`.",
}


def _next_command(argv: list, description: str, replayable: bool = True) -> dict:
    """A machine-facing next-step descriptor (README §24/§32.3 #20)."""
    return {"argv": argv, "command": "eavc " + " ".join(argv),
            "replayable": replayable, "description": description}


def _json_envelope(surface: str, **payload) -> str:
    import json
    body = {"surface": surface, "version": "v1", "ok": True}
    body.update(payload)
    return json.dumps(body, indent=2)


EAV_MCP_TOOLS = {
    "version": (["version", "--json"], "Contract version surface"),
    "agent_docs": (["agent-docs"], "Version-matched EAV agent rules"),
    "check": (["check"], "Source lane: parse + lint status"),
    "readiness": (["readiness", "--json"], "Environment lane status"),
    "deps": (["deps"], "Dependency graph"),
    "context": (["context"], "Project envelope"),
    "symbols": (["symbols"], "Full entity graph"),
    "size": (["size"], "Footprint probe"),
    "eval": (["eval"], "JIT-run a snippet"),
    "fix_plan": (["fix", "--plan"], "Repair plan from diagnostics"),
    "docs": (["docs"], "Docs catalog (list/get/search)"),
    "test": (["test"], "Run tag-test operations"),
}


def _mcp_dispatch(tool: str, arguments: dict) -> str:
    """Run a tool by building its argv and capturing stdout (MCP tools/call)."""
    import contextlib
    import io
    spec = EAV_MCP_TOOLS.get(tool)
    if spec is None:
        return f'{{"error": "unknown tool {tool}"}}'
    argv = list(spec[0])
    if "path" in arguments:
        argv.append(arguments["path"])
    for flag in ("search", "get"):
        if arguments.get(flag):
            argv += [f"--{flag}", arguments[flag]]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            main(argv)
    except SystemExit:
        pass
    return buf.getvalue()


def mcp_handle(request: dict) -> dict:
    """Handle one MCP JSON-RPC request (initialize / tools/list / tools/call)."""
    method = request.get("method")
    rid = request.get("id")
    base = {"jsonrpc": "2.0", "id": rid}
    if method == "initialize":
        return {**base, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "eavc", "version": CONTRACT_VERSION},
            "capabilities": {"tools": {}}}}
    if method == "tools/list":
        return {**base, "result": {"tools": [
            {"name": name, "description": desc,
             "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}}
            for name, (_argv, desc) in EAV_MCP_TOOLS.items()]}}
    if method == "tools/call":
        params = request.get("params", {})
        text = _mcp_dispatch(params.get("name", ""), params.get("arguments", {}))
        return {**base, "result": {"content": [{"type": "text", "text": text}]}}
    return {**base, "error": {"code": -32601, "message": f"method not found: {method}"}}


EAV_TASK_TEMPLATES = {
    "add-route": {
        "rowsToAdd": ["<server> route <METHOD> <path> <handler>",
                      "<handler> is operation", "<handler> in request HttpRequest",
                      "<handler> in response HttpResponse", "<handler> out Int32"],
        "rowsToVerify": ["route method is a bare GET/POST/... verb",
                         "path is exact-match static (no :param / *)"],
        "lintRules": ["SS2601", "SS2602", "SS2603"],
    },
    "add-db-query": {
        "rowsToAdd": ["openDb invokes openInMemory / out db SqliteDatabase / owns db",
                      "prepare invokes prepareStatement", "step invokes stepStatement",
                      "read invokes columnText / out value",
                      "finalize invokes finalizeStatement", "close invokes closeDatabase"],
        "rowsToVerify": ["column result consumed before the next read/step",
                         "db handle owns + cleanedBy + defer on every path"],
        "lintRules": ["SS1901", "SS1902", "SS1503"],
    },
    "add-cleanup": {
        "rowsToAdd": ["<producer> owns <handle>", "<producer> cleanedBy <cleanup>",
                      "<cleanup> is cleanup / in <op> / call <worker> / cleans <handle> / because \"…\"",
                      "<op> defer <cleanup>"],
        "rowsToVerify": ["cleanup deferred on every path the handle is live",
                         "worker has a catch if onFailure is declared"],
        "lintRules": ["SS1503", "SS1542", "SS1544", "SS3044B"],
    },
    "add-async-fanout": {
        "rowsToAdd": ["<op> async yes", "<op> start <task>", "<op> join <task>",
                      "<task> is task / in <op> / invokes <target>"],
        "rowsToVerify": ["every started task is resolved (join/poll/cancel/detach)",
                         "ifError on a task comes after join"],
        "lintRules": ["SS1140", "SS1320"],
    },
    "convert-to-eav": {
        "rowsToAdd": ["<name> is <kind> as the first row of every entity",
                      "subject-first rows; `call` becomes is/in/invokes + arg + out"],
        "rowsToVerify": ["no expressions/infix/parens/commas; effects covered by uses"],
        "lintRules": ["run `check` — zero error-severity diagnostics"],
    },
}


def _new_project_files(name: str) -> dict:
    """The canonical `eavc new` skeleton (§28.2) as a {relpath: content} map."""
    pas = "".join(p[:1].upper() + p[1:] for p in __import__("re").split(r"[^A-Za-z0-9]+", name) if p) or "App"
    mod = pas[:1].lower() + pas[1:]
    main = (
        f"{mod} is module\n{mod} path src.main\n{mod} exports main\n"
        f'{mod} purpose "Entry module for {pas}"\n{mod} invariant "main is the only entry"\n\n'
        "ExitCode is alias\nExitCode for Int32\nExitCode purpose \"Process exit status\"\n\n"
        "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
        'stdoutWriter purpose "Allow controlled stdout writes"\n\n'
        "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
        "main uses stdoutWriter\nmain async no\n"
        f'main purpose "Greet from {pas}"\nmain invariant "Writes one greeting line"\n'
        f'main let greeting immutable String "hello from {pas}"\n'
        "main let okCode immutable ExitCode 0\nmain do writeGreeting\nmain return okCode\n\n"
        "writeGreeting is call\nwriteGreeting in main\nwriteGreeting invokes console.writeLine\n"
        "writeGreeting arg text String greeting\n"
    )
    test = (
        f"{pas}Tests is project\n{pas}Tests module {mod}Tests\n{pas}Tests target console\n"
        f"{pas}Tests entry checkGreetingLength\n\n"
        f"{mod}Tests is module\n{mod}Tests path src.mainTest\n{mod}Tests exports checkGreetingLength\n"
        f'{mod}Tests purpose "Unit tests for {pas}"\n{mod}Tests invariant "All tag-test ops pass"\n\n'
        "ExitCode is alias\nExitCode for Int32\n\n"
        "checkGreetingLength is operation\ncheckGreetingLength out ExitCode\n"
        "checkGreetingLength async no\ncheckGreetingLength tag test\n"
        'checkGreetingLength purpose "Smoke test stub"\ncheckGreetingLength invariant "Returns 0"\n'
        "checkGreetingLength let pass immutable ExitCode 0\ncheckGreetingLength return pass\n"
    )
    build = (
        f"{pas} is project\n{pas} module {mod}\n{pas} target console\n{pas} entry main\n"
        f'{pas} languageVersion "1.0"\n{pas} toolchain "eavc"\n'
    )
    return {
        "build.sem": build,
        "src/main.sem": main,
        "src/main.test.sem": test,
        ".gitignore": "dist/\n",
        "tests/golden/.gitkeep": "",
    }


def cmd_new(args) -> int:
    """Scaffold a canonical EAV project tree (§28.2)."""
    import os
    root = args.path
    files = _new_project_files(os.path.basename(os.path.normpath(root)))
    created = []
    for rel, content in files.items():
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        created.append(rel)
    sys.stdout.write(_json_envelope("sem.new.v1", root=root, created=sorted(created)) + "\n")
    return 0


def cmd_task(args) -> int:
    """Emit an agent workflow checklist for a template (sem.task.v1)."""
    tmpl = EAV_TASK_TEMPLATES.get(args.template)
    if tmpl is None:
        sys.stdout.write(_json_envelope(
            "sem.task.v1", ok=False,
            available=sorted(EAV_TASK_TEMPLATES)) + "\n")
        return 2
    sys.stdout.write(_json_envelope("sem.task.v1", template=args.template, **tmpl) + "\n")
    return 0


def cmd_mcp(args) -> int:
    """Run the MCP stdio JSON-RPC server (one request per line)."""
    import json
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        sys.stdout.write(json.dumps(mcp_handle(request)) + "\n")
        sys.stdout.flush()
    return 0


def cmd_version(args) -> int:
    """Emit the eavc contract version surface (sem.version.v1)."""
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope(
            "sem.version.v1", contractVersion=CONTRACT_VERSION, compiler="eavc",
            surfaces=list(SEM_SURFACES)) + "\n")
    else:
        sys.stdout.write(f"eavc {CONTRACT_VERSION}\n")
    return 0


def cmd_agent_docs(args) -> int:
    """Emit the version-matched EAV agent rules (sem.agentDocs.v1)."""
    sys.stdout.write(_json_envelope(
        "sem.agentDocs.v1", contractVersion=CONTRACT_VERSION,
        rules=EAV_AGENT_RULES) + "\n")
    return 0


def cmd_skills(args) -> int:
    """List or get EAV agent skills (sem.skills.v1)."""
    names = getattr(args, "names", None)
    items = [
        {"name": k, "summary": v}
        for k, v in EAV_SKILLS.items()
        if not names or k in names
    ]
    sys.stdout.write(_json_envelope("sem.skills.v1", skills=items) + "\n")
    return 0


_EVAL_SCAFFOLD = (
    "EvalProgram is project\nEvalProgram module evalModule\n"
    "EvalProgram target console\nEvalProgram entry main\n"
    "evalModule is module\nevalModule path eval.program\n"
    "evalModule exports main\nevalModule purpose \"Eval snippet\"\n"
    "evalModule invariant \"Runs the evaluated snippet\"\n"
    "ExitCode is alias\nExitCode for Int32\n"
)


def cmd_eval(args) -> int:
    """Run a snippet through the JIT without scaffolding (sem.eval.v1): if the
    source has no `project`, wrap it in a minimal console program, then JIT-run
    and return captured stdout + exit code."""
    src = _read_source(args.path)
    if "is project" not in src:
        src = _EVAL_SCAFFOLD + src
    out, code = _record_run(src)
    sys.stdout.write(_json_envelope(
        "sem.eval.v1", ok=(code == 0), exitCode=code,
        stdout=out, stdoutLines=out.split("\n")[:-1] if out.endswith("\n") else out.split("\n")) + "\n")
    return 0


def cmd_deps(args) -> int:
    """Dependency graph (sem.deps.v1): module `imports` + project `require` rows."""
    program = parse_compact(_read_source(args.path))
    imports, requires = [], []
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "module":
            for r in ent.facts("imports"):
                if r.payload:
                    imports.append({"alias": r.payload[0],
                                    "path": r.payload[1] if len(r.payload) > 1 else None})
        if ent.kind == "project":
            for r in ent.facts("require"):
                if r.payload:
                    requires.append({"path": r.payload[0],
                                     "version": r.payload[1] if len(r.payload) > 1 else None})
    sys.stdout.write(_json_envelope("sem.deps.v1", imports=imports, requires=requires) + "\n")
    return 0


def cmd_context(args) -> int:
    """Project envelope (sem.context.v1): target(s), entry, mode, modules."""
    program = parse_compact(_read_source(args.path))
    projects = program.of_kind("project")
    proj = projects[0] if projects else None

    def vals(ent, pred):
        return [r.payload[0] for r in ent.facts(pred) if r.payload]

    ctx = {
        "project": proj.name if proj else None,
        "targets": vals(proj, "target") if proj else [],
        "entry": (proj.fact("entry").payload[0]
                  if proj and proj.fact("entry") and proj.fact("entry").payload else None),
        "mode": (proj.fact("mode").payload[0]
                 if proj and proj.fact("mode") and proj.fact("mode").payload else None),
        "modules": [program.entities[n].name for n in program.order
                    if program.entities[n].kind == "module"],
    }
    sys.stdout.write(_json_envelope("sem.context.v1", **ctx) + "\n")
    return 0


def cmd_symbols(args) -> int:
    """Full source graph (sem.symbols.v1): every entity with kind + row count."""
    program = parse_compact(_read_source(args.path))
    symbols = [
        {"name": program.entities[n].name, "kind": program.entities[n].kind,
         "rows": len(program.entities[n].rows), "line": program.entities[n].line}
        for n in program.order
    ]
    sys.stdout.write(_json_envelope("sem.symbols.v1", symbols=symbols) + "\n")
    return 0


def _doc_entries(program: Program) -> list:
    out = []
    for n in program.order:
        e = program.entities[n]
        purpose = e.fact("purpose")
        ptext = (purpose.payload[-1].strip('"') if purpose and purpose.payload else "")
        out.append({"name": e.name, "kind": e.kind, "purpose": ptext})
    return out


def cmd_docs(args) -> int:
    """Docs catalog over program entities (no third-party dep): list / get / a
    keyword-ranked `--search` (sem.docsIndex.v1 / sem.docs.v1 / sem.docsSearch.v1)."""
    entries = _doc_entries(parse_compact(_read_source(args.path)))
    if getattr(args, "search", None):
        terms = [t for t in args.search.lower().split() if t]
        scored = []
        for e in entries:
            hay = (e["name"] + " " + e["purpose"]).lower()
            score = sum(hay.count(t) for t in terms)
            if score:
                scored.append({**e, "score": score})
        scored.sort(key=lambda x: (-x["score"], x["name"]))
        sys.stdout.write(_json_envelope(
            "sem.docsSearch.v1", query=args.search, results=scored[:10]) + "\n")
    elif getattr(args, "get", None):
        match = next((e for e in entries if e["name"] == args.get), None)
        sys.stdout.write(_json_envelope(
            "sem.docs.v1", ok=(match is not None), entity=match) + "\n")
    else:
        sys.stdout.write(_json_envelope(
            "sem.docsIndex.v1", count=len(entries),
            entries=[{"name": e["name"], "kind": e["kind"]} for e in entries]) + "\n")
    return 0


def cmd_dev(args) -> int:
    """Dev contract (sem.dev.v1): one check+runnability cycle reporting whether
    the surface is close to runnable (a single tick of the watch/restart loop)."""
    program = parse_compact(_read_source(args.path))
    diags = lint(program)
    errors = [d for d in diags if d.severity == "error"]
    projects = program.of_kind("project")
    target = (projects[0].fact("target").payload[0]
              if projects and projects[0].fact("target") and projects[0].fact("target").payload
              else None)
    runnable = not errors and target == "console"
    nxt = ([_next_command(["run", args.path], "JIT-run"),
            _next_command(["build", args.path], "compile to a native exe")]
           if runnable else
           [_next_command(["check", args.path], "resolve source diagnostics first")])
    sys.stdout.write(_json_envelope(
        "sem.dev.v1", checkStatus=("lint-diagnostics" if errors else "ok"),
        runnable=runnable, target=target, nextCommands=nxt) + "\n")
    return 0


def cmd_size(args) -> int:
    """Cheap footprint probe (sem.size.v1): entity + row counts by kind."""
    program = parse_compact(_read_source(args.path))
    by_kind: dict = {}
    rows = 0
    for n in program.order:
        ent = program.entities[n]
        by_kind[ent.kind] = by_kind.get(ent.kind, 0) + 1
        rows += 1 + len(ent.rows)
    sys.stdout.write(_json_envelope(
        "sem.size.v1", entities=len(program.order), rows=rows, byKind=by_kind) + "\n")
    return 0


def cmd_check(args) -> int:
    """Source lane (sem.check.v1): parse + lint, classify ok / ok-with-warnings /
    lint-diagnostics / compiler-error (README check/readiness split)."""
    try:
        program = parse_compact(_read_program_source(args.path))
    except EavError as exc:
        sys.stdout.write(_json_envelope(
            "sem.check.v1", status="compiler-error", ok=False,
            diagnostics=[str(exc)]) + "\n")
        return 0
    diags = lint(program)
    errors = [d for d in diags if d.severity == "error"]
    warnings = [d for d in diags if d.severity == "warning"]
    status = ("lint-diagnostics" if errors
              else "ok-with-warnings" if warnings else "ok")
    # README §24/§32.3 #20: machine-facing next steps.
    if status == "lint-diagnostics":
        nxt = [_next_command(["fix", args.path, "--plan"],
                             "derive a repair plan for the errors")]
    elif status == "ok-with-warnings":
        nxt = [_next_command(["fix", args.path, "--plan", "--include-warnings"],
                             "review warning cleanup"),
               _next_command(["test", args.path], "run the test operations")]
    else:
        nxt = [_next_command(["test", args.path], "run the test operations"),
               _next_command(["build", args.path], "compile to a native exe")]
    sys.stdout.write(_json_envelope(
        "sem.check.v1", status=status, ok=(status in ("ok", "ok-with-warnings")),
        diagnostics=[d.render() for d in diags], nextCommands=nxt) + "\n")
    return 0


def cmd_readiness(args) -> int:
    """Environment lane (sem.readiness.v1): toolchain availability. Exits nonzero
    unless ok (README readiness lane)."""
    cc = _find_c_compiler()
    try:
        import llvmlite  # noqa: F401
        have_llvm = True
    except ImportError:
        have_llvm = False
    ok = bool(cc) and have_llvm
    status = "ok" if ok else "degraded"
    sys.stdout.write(_json_envelope(
        "sem.readiness.v1", status=status, ok=ok,
        cCompiler=bool(cc), llvmlite=have_llvm) + "\n")
    return 0 if ok else 1


def cmd_build(args) -> int:
    """Compile a program to a native executable (IR -> clang -> exe)."""
    import os
    program = parse_compact(_read_program_source(args.path))
    default = (os.path.splitext(args.path)[0] if args.path != "-"
               and not os.path.isdir(args.path) else
               os.path.join(args.path, "app") if os.path.isdir(args.path) else "a")
    out_path = args.output or (default + (".exe" if sys.platform == "win32" else ""))
    try:
        sys.stdout.write(build_executable(program, out_path) + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_trace(args) -> int:
    """Print a primary-path trace of an operation."""
    program = parse(_read_source(args.path))
    try:
        for line in trace(program, args.operation):
            sys.stdout.write(line + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_normalize(args) -> int:
    """Preview normalizing a program (row delta + round-trip gate)."""
    p = normalize_preview(_read_source(args.path))
    sys.stdout.write(
        f"rows {p['rowCount']} -> {p['formattedRowCount']} (delta {p['rowDelta']:+d})\n"
        f"changed: {p['changed']}\n"
        f"round-trip preserved (gate-0): {p['roundTripPreserved']}\n"
    )
    return 0


def cmd_verify_patch(args) -> int:
    """Verify a program is sound; exit 1 if not."""
    report = verify_patch(_read_source(args.path))
    if report["error"]:
        sys.stdout.write(f"FAIL (parse): {report['error']}\n")
        return 1
    for e in report["lintErrors"]:
        sys.stdout.write(f"FAIL (lint): {e}\n")
    sys.stdout.write("OK\n" if report["ok"] else "FAIL\n")
    return 0 if report["ok"] else 1


def cmd_diff(args) -> int:
    """Print the semantic diff between two programs."""
    old = parse(_read_source(args.old))
    new = parse(_read_source(args.new))
    for line in semantic_diff(old, new):
        sys.stdout.write(line + "\n")
    return 0


def cmd_describe(args) -> int:
    """Summarize an entity's contract."""
    program = parse(_read_source(args.path))
    try:
        sys.stdout.write(describe(program, args.entity) + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_graph(args) -> int:
    """Emit a calls/control graph as DOT or mermaid."""
    program = parse(_read_source(args.path))
    try:
        sys.stdout.write(graph(program, args.kind, args.format))
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_scaffold(args) -> int:
    """Print a canonical scaffold for a pattern."""
    try:
        sys.stdout.write(scaffold(args.pattern))
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_fmt(args) -> int:
    """Print a program in the requested surface (canonical EAV or compact).

    Input may be either canonical EAV or compact-profile source; compact is
    expanded first, so `fmt --surface eav` canonicalizes compact and
    `fmt --surface compact` round-trips it (README ss23/ss24)."""
    src = _read_source(args.path)
    program = parse_compact(src)
    surface = getattr(args, "surface", "eav")
    formatted = (format_compact(program) if surface == "compact"
                 else format_program(program))
    if getattr(args, "check", False):
        # README §24: drift check — exit nonzero if the source is not already
        # canonically formatted (keeps diffs/patch landings stable).
        if formatted.strip() != src.strip():
            sys.stderr.write("eavc: fmt drift — run `eavc fmt` to canonicalize\n")
            return 1
        return 0
    sys.stdout.write(formatted)
    return 0


def cmd_fix(args) -> int:
    """Derive a repair plan from lint diagnostics (sem.fixPlan.v1). Blocker-first
    by default; `--include-warnings` adds cleanup guidance. The plan is
    suggestions-only (machine-applicable auto-edits are future work)."""
    program = parse_compact(_read_source(args.path))
    diags = lint(program)
    targeted = (diags if getattr(args, "include_warnings", False)
                else [d for d in diags if d.severity == "error"])
    items = []
    for d in targeted:
        entry = DIAGNOSTICS.get(d.code, {})
        items.append({"code": d.code, "severity": d.severity, "line": d.line,
                      "message": d.message, "found": entry.get("found"),
                      "suggested": entry.get("suggested")})
    status = "suggestions-only" if items else "ok"
    sys.stdout.write(_json_envelope(
        "sem.fixPlan.v1", status=status, planUsable=False, diagnostics=items) + "\n")
    return 0


def cmd_patch(args) -> int:
    """Apply a repair plan (sem.patch.v1). eavc plans are suggestions-only, so
    patch reports that no machine-applicable edits are available rather than
    mutating source blindly."""
    sys.stdout.write(_json_envelope(
        "sem.patch.v1", status="suggestions-only", applied=0,
        note="plan is suggestions-only; apply the suggested repairs manually") + "\n")
    return 0


def cmd_query(args) -> int:
    """Print the result of a structural query (`--dimension`)."""
    program = parse(_read_source(args.path))
    if args.dimension not in QUERY_DIMENSIONS:
        sys.stderr.write(
            f"eavc: unknown query dimension {args.dimension!r}; choose from "
            f"{', '.join(QUERY_DIMENSIONS)}\n"
        )
        return 2
    for line in query(program, args.dimension):
        sys.stdout.write(line + "\n")
    return 0


def cmd_rename(args) -> int:
    """Rename an entity and all references; print the updated source."""
    try:
        sys.stdout.write(rename_entity(_read_source(args.path), args.old, args.new))
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_add(args) -> int:
    """Append a scaffolded operation; print the updated source."""
    try:
        sys.stdout.write(add_operation(_read_source(args.path), args.name, args.out))
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_pack(args) -> int:
    """Print a budgeted context bundle for editing an entity."""
    program = parse(_read_source(args.path))
    try:
        sys.stdout.write(pack(program, args.entity, args.budget) + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def cmd_slice(args) -> int:
    """Print the semantic slice of an entity (sem.slice.v1 with --json)."""
    program = parse(_read_source(args.path))
    try:
        text = slice_entity(program, args.entity)
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2
    if getattr(args, "json", False):
        ent = program.entities.get(args.entity)
        sys.stdout.write(_json_envelope(
            "sem.slice.v1", entity=args.entity,
            kind=ent.kind if ent else None, slice=text) + "\n")
    else:
        sys.stdout.write(text)
    return 0


def cmd_test(args) -> int:
    """Discover (--discover) or execute `tag test` operations (sem.test.v1)."""
    program = parse_compact(_read_source(args.path))
    if getattr(args, "discover", False):
        lanes = discover_tests(program)
        selected = {args.lane: lanes.get(args.lane, [])} if args.lane else lanes
        total = 0
        for lane in sorted(selected):
            for op in selected[lane]:
                sys.stdout.write(f"{lane}: {op}\n")
                total += 1
        sys.stdout.write(f"{total} test operation(s)\n")
        return 0
    report = run_tests(program)
    sys.stdout.write(_json_envelope(
        "sem.test.v1", ok=(report["compositeStatus"] in ("pass", "blocked")),
        **report) + "\n")
    return 0 if report["compositeStatus"] == "pass" else 1


def cmd_doctor(args) -> int:
    """Print a severity-grouped diagnostic report with suggested fixes."""
    groups = doctor(parse(_read_source(args.path)))
    total = sum(len(v) for v in groups.values())
    for severity in ("error", "warning", "info"):
        for d in groups.get(severity, []):
            sys.stdout.write(d.render() + "\n")
            if severity == "error" and d.code in DIAGNOSTICS:
                sys.stdout.write("    " + DIAGNOSTICS[d.code]["suggested"] + "\n")
    if total == 0:
        sys.stdout.write("healthy: no diagnostics\n")
    return 1 if groups.get("error") else 0


def cmd_inventory(args) -> int:
    """Print entity counts by kind."""
    program = parse(_read_source(args.path))
    counts = summarize(program)
    for kind in sorted(counts):
        sys.stdout.write(f"{counts[kind]:4d}  {kind}\n")
    sys.stdout.write(f"{sum(counts.values()):4d}  total\n")
    return 0


def cmd_lint(args) -> int:
    """Lint a program: print all MD/lint diagnostics; exit 1 if any are errors.
    With `--explain CODE`, print the registry rationale + required pattern."""
    if getattr(args, "explain", None):
        try:
            sys.stdout.write(format_repair(args.explain) + "\n")
            return 0
        except EavError as exc:
            sys.stderr.write(f"eavc: {exc}\n")
            return 2
    program = parse(_read_source(args.path))
    diags = lint(program)
    if getattr(args, "json", False):
        sys.stdout.write(diagnostics_json(diags) + "\n")
    else:
        for d in diags:
            sys.stdout.write(d.render() + "\n")
        if not diags:
            sys.stdout.write("no lint diagnostics\n")
    return 1 if any(d.severity == "error" for d in diags) else 0


def cmd_explain(args) -> int:
    """Print the registry entry + repair for a diagnostic code."""
    try:
        sys.stdout.write(format_repair(args.code) + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eavc", description="EAV-Steps front end (lex/parse/lower/run)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn in (
        ("lex", cmd_lex),
        ("parse", cmd_parse),
        ("lower", cmd_lower),
        ("run", cmd_run),
        ("inventory", cmd_inventory),
        ("doctor", cmd_doctor),
    ):
        sp = sub.add_parser(name)
        sp.add_argument("path", help="EAV source file, or - for stdin")
        sp.set_defaults(func=fn)

    for cname, cfn, chelp in (
        ("deps", cmd_deps, "dependency graph (imports + require)"),
        ("context", cmd_context, "project envelope"),
        ("symbols", cmd_symbols, "full entity graph"),
        ("size", cmd_size, "cheap footprint probe"),
        ("dev", cmd_dev, "one dev check+runnability tick"),
    ):
        sp = sub.add_parser(cname, help=chelp)
        sp.add_argument("path", help="EAV/compact source file, or - for stdin")
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=cfn)

    sp_docs = sub.add_parser("docs", help="docs catalog (list/get/search)")
    sp_docs.add_argument("path", help="EAV/compact source file, or - for stdin")
    sp_docs.add_argument("--search", help="keyword-ranked search query")
    sp_docs.add_argument("--get", help="entity name to fetch")
    sp_docs.add_argument("--json", action="store_true")
    sp_docs.set_defaults(func=cmd_docs)

    sp_eval = sub.add_parser("eval", help="JIT-run a snippet (auto-wrapped)")
    sp_eval.add_argument("path", help="EAV snippet/program file, or - for stdin")
    sp_eval.add_argument("--json", action="store_true")
    sp_eval.set_defaults(func=cmd_eval)

    sp_check = sub.add_parser("check", help="source lane: parse + lint status")
    sp_check.add_argument("path", help="EAV/compact source file, or - for stdin")
    sp_check.add_argument("--json", action="store_true")
    sp_check.set_defaults(func=cmd_check)

    sp_readiness = sub.add_parser("readiness", help="environment lane: toolchain status")
    sp_readiness.add_argument("--json", action="store_true")
    sp_readiness.set_defaults(func=cmd_readiness)

    sp_mcp = sub.add_parser("mcp", help="run the MCP stdio JSON-RPC server")
    sp_mcp.set_defaults(func=cmd_mcp)

    sp_new = sub.add_parser("new", help="scaffold a canonical EAV project tree")
    sp_new.add_argument("path", help="project root directory to create")
    sp_new.add_argument("--enable-docs-index", action="store_true")
    sp_new.set_defaults(func=cmd_new)

    sp_task = sub.add_parser("task", help="emit an agent workflow checklist")
    sp_task.add_argument("template", help="one of: " + ", ".join(sorted(EAV_TASK_TEMPLATES)))
    sp_task.add_argument("--json", action="store_true")
    sp_task.set_defaults(func=cmd_task)

    sp_version = sub.add_parser("version", help="emit the contract version surface")
    sp_version.add_argument("--json", action="store_true", help="emit JSON envelope")
    sp_version.set_defaults(func=cmd_version)

    sp_agentdocs = sub.add_parser("agent-docs", help="emit version-matched agent rules")
    sp_agentdocs.add_argument("--json", action="store_true")
    sp_agentdocs.set_defaults(func=cmd_agent_docs)

    sp_skills = sub.add_parser("skills", help="list or get EAV agent skills")
    sp_skills.add_argument("names", nargs="*", help="optional skill names to filter")
    sp_skills.add_argument("--json", action="store_true")
    sp_skills.set_defaults(func=cmd_skills)

    sp_build = sub.add_parser("build", help="compile a program to a native exe")
    sp_build.add_argument("path", help="EAV/compact source file, or - for stdin")
    sp_build.add_argument("--output", "-o", help="output executable path")
    sp_build.set_defaults(func=cmd_build)

    sp_fmt = sub.add_parser("fmt", help="format a program to a surface")
    sp_fmt.add_argument("path", help="EAV/compact source file, or - for stdin")
    sp_fmt.add_argument(
        "--surface", choices=("eav", "compact"), default="eav",
        help="output surface: canonical EAV (default) or compact profile",
    )
    sp_fmt.add_argument("--check", action="store_true",
                        help="exit nonzero if the source is not canonically formatted")
    sp_fmt.set_defaults(func=cmd_fmt)

    sp_fix = sub.add_parser("fix", help="derive a repair plan from diagnostics")
    sp_fix.add_argument("path", help="EAV/compact source file, or - for stdin")
    sp_fix.add_argument("--plan", action="store_true", help="emit the plan (default)")
    sp_fix.add_argument("--include-warnings", action="store_true")
    sp_fix.add_argument("--json", action="store_true")
    sp_fix.set_defaults(func=cmd_fix)

    sp_patch = sub.add_parser("patch", help="apply a repair plan")
    sp_patch.add_argument("plan", nargs="?", help="plan JSON file")
    sp_patch.add_argument("--apply", action="store_true")
    sp_patch.add_argument("--dry-run", action="store_true")
    sp_patch.add_argument("--json", action="store_true")
    sp_patch.set_defaults(func=cmd_patch)

    sp_lint = sub.add_parser("lint", help="lint a program (or --explain a code)")
    sp_lint.add_argument("path", nargs="?", help="EAV source file, or - for stdin")
    sp_lint.add_argument("--explain", metavar="CODE", help="explain a diagnostic code")
    sp_lint.add_argument("--json", action="store_true", help="emit diagnostics as JSON")
    sp_lint.set_defaults(func=cmd_lint)

    sp_explain = sub.add_parser("explain", help="explain a diagnostic code")
    sp_explain.add_argument("code", help="diagnostic code, e.g. SS1502")
    sp_explain.set_defaults(func=cmd_explain)

    sp_test = sub.add_parser("test", help="discover `tag test` ops (by lane)")
    sp_test.add_argument("path", help="EAV source file, or - for stdin")
    sp_test.add_argument("--lane", choices=TEST_LANES, default=None)
    sp_test.add_argument("--discover", action="store_true",
                         help="list test ops instead of executing them")
    sp_test.add_argument("--json", action="store_true")
    sp_test.set_defaults(func=cmd_test)

    sp_query = sub.add_parser("query", help="structural query over a program")
    sp_query.add_argument("dimension", help=f"one of: {', '.join(QUERY_DIMENSIONS)}")
    sp_query.add_argument("path", help="EAV source file, or - for stdin")
    sp_query.set_defaults(func=cmd_query)

    sp_scaffold = sub.add_parser("scaffold", help="emit a canonical pattern")
    sp_scaffold.add_argument("pattern", help=f"one of: {', '.join(SCAFFOLD_PATTERNS)}")
    sp_scaffold.set_defaults(func=cmd_scaffold)

    sp_verify = sub.add_parser("verify-patch", help="verify a program is sound")
    sp_verify.add_argument("path", help="EAV source file, or - for stdin")
    sp_verify.set_defaults(func=cmd_verify_patch)

    sp_trace = sub.add_parser("trace", help="primary-path trace of an operation")
    sp_trace.add_argument("path", help="EAV source file, or - for stdin")
    sp_trace.add_argument("operation", help="operation name")
    sp_trace.set_defaults(func=cmd_trace)

    sp_norm = sub.add_parser("normalize", help="preview normalizing to canonical EAV")
    sp_norm.add_argument("path", help="EAV source file, or - for stdin")
    sp_norm.add_argument("--preview", action="store_true", help="(default) preview only")
    sp_norm.set_defaults(func=cmd_normalize)

    sp_diff = sub.add_parser("diff", help="semantic diff between two programs")
    sp_diff.add_argument("old", help="old EAV source file")
    sp_diff.add_argument("new", help="new EAV source file")
    sp_diff.set_defaults(func=cmd_diff)

    sp_rename = sub.add_parser("rename", help="rename an entity and its references")
    sp_rename.add_argument("path", help="EAV source file, or - for stdin")
    sp_rename.add_argument("old")
    sp_rename.add_argument("new")
    sp_rename.set_defaults(func=cmd_rename)

    sp_add = sub.add_parser("add", help="append a scaffolded operation")
    sp_add.add_argument("path", help="EAV source file, or - for stdin")
    sp_add.add_argument("name")
    sp_add.add_argument("--out", default="ExitCode")
    sp_add.set_defaults(func=cmd_add)

    sp_slice = sub.add_parser("slice", help="semantic slice of an entity")
    sp_slice.add_argument("path", help="EAV source file, or - for stdin")
    sp_slice.add_argument("entity", help="entity name")
    sp_slice.add_argument("--json", action="store_true")
    sp_slice.set_defaults(func=cmd_slice)

    sp_pack = sub.add_parser("pack", help="budgeted context bundle for an entity")
    sp_pack.add_argument("path", help="EAV source file, or - for stdin")
    sp_pack.add_argument("entity", help="entity name")
    sp_pack.add_argument("--budget", type=int, default=4000)
    sp_pack.set_defaults(func=cmd_pack)

    sp_describe = sub.add_parser("describe", help="summarize an entity's contract")
    sp_describe.add_argument("path", help="EAV source file, or - for stdin")
    sp_describe.add_argument("entity", help="entity name")
    sp_describe.set_defaults(func=cmd_describe)

    sp_graph = sub.add_parser("graph", help="emit a calls/control graph")
    sp_graph.add_argument("path", help="EAV source file, or - for stdin")
    sp_graph.add_argument("--kind", default="calls", choices=GRAPH_KINDS)
    sp_graph.add_argument("--format", default="dot", choices=("dot", "mermaid"))
    sp_graph.set_defaults(func=cmd_graph)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
