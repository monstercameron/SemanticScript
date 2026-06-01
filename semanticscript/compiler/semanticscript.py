#!/usr/bin/env python3
"""semanticscript — EAV-Steps compiler front end and LLVM backend (lexer, parser, codegen, CLI).

This is the keystone vertical slice for the EAV-Steps v0.3 spec (README.md). It
implements WS1-100 (the lowering ADR) and WS1-101 (parse -> lower -> run Hello
World) from todos.md.

ADR (WS1-100): semanticscript is **its own backend**. A parsed EAV Program is lowered
*directly to LLVM IR* with ``llvmlite`` and JIT-executed in process. There is no
transpilation to any other surface syntax and no dependency on the reference
compiler — semanticscript owns lexing, parsing, semantic validation, and code generation.
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
CONTRACT_VERSION = "eav-0.3.1"


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
    "SS1011": {
        "tier": "T1",
        "summary": "Type alias chain is circular.",
        "found": "An `alias … for …` chain that cycles back on itself.",
        "suggested": "Break the cycle so the alias resolves to a concrete type (README §10/§17/WS2-089).",
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
    "SS0802": {"tier": "T3", "summary": "Capability declared but never used.",
               "found": "A `capability` entity whose name appears in no operation's `uses` row.",
               "suggested": "Remove the unused capability, or `uses` it from the op that needs the effect (README §17/WS2-080)."},
    "SS0810": {"tier": "T3", "summary": "Unreachable operation step.",
               "found": "A step that follows an unconditional `return`/`goto`/`jump` with no intervening `at` label.",
               "suggested": "Remove the dead step, or guard it behind a reachable label/branch (README §13/WS2-080)."},
    "SS0806": {"tier": "T3", "summary": "Module storage declared but never used.",
               "found": "A `storage` entity whose name is never referenced by any operation (no read or `set`).",
               "suggested": "Remove the unused storage, or read/`set` it where intended (README §17/WS2-080)."},
    "SS0803": {"tier": "T4", "summary": "Error case declared but never used.",
               "found": "An `errorCase` whose name is never constructed (`makeError`) or matched.",
               "suggested": "Construct/match the case, or remove it (README §17/WS2-080)."},
    "SS0804": {"tier": "T3", "summary": "Local const declared but never used.",
               "found": "An immutable `let` whose name is never referenced in the operation.",
               "suggested": "Remove the unused const, or use it (README §17/WS2-080)."},
    "SS0805": {"tier": "T3", "summary": "Operation input never used.",
               "found": "An `in` parameter whose name never appears in the operation body.",
               "suggested": "Use the input, or drop it from the signature (README §17/WS2-080)."},
    "SS0807": {"tier": "T3", "summary": "Call binding never used.",
               "found": "A call/task `out` binding whose name is never read.",
               "suggested": "Read the binding, `discards \"…\"` the result, or drop the `out` (README §17/WS2-080)."},
    "SS0808": {"tier": "T3", "summary": "Dead store.",
               "found": "A `set X` whose value is overwritten by a later `set X` before any read.",
               "suggested": "Remove the dead store, or read X between the writes (README §17/WS2-080)."},
    "SS0809": {"tier": "T3", "summary": "Dead storage initializer.",
               "found": "A mutable `storage` written but whose value is never read.",
               "suggested": "Read the storage, or remove it if the writes are pointless (README §17/WS2-080)."},
    "SS0811": {"tier": "T3", "summary": "Duplicate single-valued declaration.",
               "found": "Two rows of a single-valued predicate (purpose/path/out/…) on one entity.",
               "suggested": "Keep one declaration row (README §17/WS2-080)."},
    "SS0812": {"tier": "T4", "summary": "Immutable const duplicated across operations.",
               "found": "The same `let … immutable T V` declared in two or more operations.",
               "suggested": "Hoist it to a module `storage` constant (README §17/WS2-080)."},
    "SS0820": {"tier": "T3", "summary": "Embedded literal lacks a content digest.",
               "found": "A `storage` with a `literalSource` embed but no `literalDigest` row.",
               "suggested": "Add `literalDigest <name> sha256 <hex>` so the embed is tamper-evident (README §30.3.2/WS1-084)."},
    "SS0821": {"tier": "T1", "summary": "Heap allocation under `memory heap no`.",
               "found": "An operation declares `memory heap no` yet activates a heap allocation.",
               "suggested": "Drop `heap no`, or remove the heap allocation (README §1J/WS2-084)."},
    "SS0822": {"tier": "T1", "summary": "Record alignment is not a power of two.",
               "found": "A `record … align N` (or field `align N`) where N is not a positive power of two.",
               "suggested": "Use a power-of-two alignment: 1, 2, 4, 8, 16, … (README §10.6/WS2-084)."},
    "SS0823": {"tier": "T2", "summary": "Array type declared with zero length.",
               "found": "An `array … length 0` declaration — a zero-length array can hold no elements.",
               "suggested": "Give the array a positive length, or model emptiness differently (README §10.6/WS2-084)."},
    "SS0824": {"tier": "T3", "summary": "Inline type memory exceeds its inline capacity.",
               "found": "A type pinned `memory inline` whose byte size exceeds its declared `inlineCapacity`.",
               "suggested": "Raise the inline capacity, or move the type to heap/spill memory (README §10.6/WS2-084)."},
    "SS0825": {"tier": "T3", "summary": "Embedded literal lacks an explicit encoding.",
               "found": "A `storage` with `literalSource` but no `literalEncoding` row to pin the byte interpretation.",
               "suggested": "Add `literalEncoding <name> <utf8|ascii|binary|…>` (README §30.3.2/WS2-084)."},
    "SS0826": {"tier": "T3", "summary": "Large static string inlined as a local literal.",
               "found": "A `let … immutable String \"…\"` whose literal exceeds the inline-literal threshold.",
               "suggested": "Move the payload to a `storage` with `literalSource`/`literalDigest` so it is an audited embed (README §30.3.2/WS2-084)."},
    "SS0827": {"tier": "T4", "summary": "Magic printable-ASCII byte literal.",
               "found": "A `let … immutable Byte N` where N is a printable-ASCII code (32–126) written as a bare number.",
               "suggested": "Name the constant or use a documented character code so the intent is legible (README §10.6/WS2-084)."},
    "SS0828": {"tier": "T3", "summary": "Inline-capacity type has no spill allocator.",
               "found": "An alias pinned `memory inline` with an `inlineCapacity` but no `allocator` row for the overflow path.",
               "suggested": "Declare an `allocator` for values that exceed the inline capacity, or drop the cap (README §10.6/WS2-084)."},
    "SS0829": {"tier": "T1", "summary": "Local frame exceeds the declared stack budget.",
               "found": "An operation declares `memory stack N` yet its locals' estimated size exceeds N bytes.",
               "suggested": "Raise the stack budget, or move large locals to heap/embedded storage (README §1J/WS2-084)."},
    "SS0950": {"tier": "T3", "summary": "Loop makes no progress toward its exit.",
               "found": "A back-edge loop with no exit path, or whose exit guard is never recomputed in the body.",
               "suggested": "Add a reachable exit (return/branch-out) and recompute or mutate the exit guard each iteration (README §13/§33.3)."},
    "SS0951": {"tier": "T1", "summary": "Unbounded loop over an untrusted size.",
               "found": "A back-edge loop whose exit guard reads a `typeTrust rawExternal`/`secret` value, with no `maxIterations <n>` row on the owning operation.",
               "suggested": "Bound a loop driven by untrusted input with `maxIterations <n>` so a hostile size cannot spin the process (R-082, README §13/§27)."},
    "SS3095": {"tier": "T1", "summary": "Arithmetic on wall-clock time.",
               "found": "A math.* call with a `WallTime` operand (elapsed/duration or local-time arithmetic).",
               "suggested": "Use a `MonotonicInstant` for durations, or an explicit timezone conversion for calendar math; `WallTime` has no arithmetic (README §30.5.3/§27)."},
    "SS3070": {"tier": "T1", "summary": "Untrusted value reaches a trust-sensitive sink.",
               "found": "An arg whose type is `typeTrust rawExternal` (or secret) is passed to a `trustConstraint` sink slot.",
               "suggested": "Cross a `trustBoundary` validator first so the value becomes `validated`/`trustedInternal` (README §16/§26)."},
    "SS3071": {"tier": "T1", "summary": "Wrong-type, untyped, or string-built value into a typed sink.",
               "found": "A `trustConstraint arg <slot> <TrustedType>` sink received a value that is not exactly that type — a plain String, a `string.concat` result, or a value safe for another context (R-071: a `validated`/`trustedInternal` label is not a cross-context credential).",
               "suggested": "Build the EXACT required trusted type (e.g. SqlText/HtmlSafeUrl/SafePath) via a constructor or trust boundary; never assemble interpreter input by string concatenation, and never route a value validated for one context into another (README §16/§30.2.2, R-071)."},
    "SS3072": {"tier": "T1", "summary": "Secret value observed, or hardcoded.",
               "found": "A `typeTrust secret` value reaches an observable sink (console/log), or a secret-typed binding is initialized from a literal.",
               "suggested": "A secret is usable (verify/sign) but never observable — don't print/log it; load it from a capability-gated source, never a source literal (README §30.1.1/§8)."},
    "SS3074": {"tier": "T1", "summary": "Non-constant-time comparison of a secret.",
               "found": "A `math.*`/`compare.*` equality on a `typeTrust secret` operand (timing side-channel).",
               "suggested": "Compare secrets only with `crypto.equalConstantTime` (README §13)."},
    "SS3077": {"tier": "T1", "summary": "Untrusted decode without a size limit.",
               "found": "A decode (json.parse/decode/createDocument/codec.decode) of a `rawExternal` input with no `limit maximumBytes` row.",
               "suggested": "Bound untrusted decoding: add `limit maximumBytes <n>` (and depth/element caps) so malformed input cannot exhaust memory (README §16)."},
    "SS3073": {"tier": "T1", "summary": "Deterministic RNG feeding a security generator.",
               "found": "A value drawn from `random.deterministic`/seeded RNG is passed to a key/token/nonce/salt generator.",
               "suggested": "Security material must be drawn from the CSPRNG (`random.entropy`); a seeded RNG is for reproducible non-security use only (README §30.5.3)."},
    "SS3076": {"tier": "T1", "summary": "Path traversal / absolute-escape literal at a filesystem op.",
               "found": "An `fs.*` path argument is a literal containing a `..` segment or an absolute root.",
               "suggested": "Confine paths under a root with `fs.resolveWithin <root>` (producing a SafePath); never pass a `..`/absolute path literal to a filesystem op (README §8/§27)."},
    "SS3075": {"tier": "T1", "summary": "Outbound request to an internal/loopback address (SSRF).",
               "found": "A `net.*`/`http.*` URL literal targets localhost / a private / link-local / cloud-metadata address.",
               "suggested": "Outbound requests go to allowlisted external hosts via an `HttpSafeUrl`; never hardcode an internal address (SSRF defense, README §8/§27)."},
    "SS3078": {"tier": "T1", "summary": "Unbounded external call over untrusted input.",
               "found": "A `net.*`/`http.*`/`sqlite.*`/`db.*`/`fs.*` call with a `rawExternal` arg and no `timeout`/`budget` row.",
               "suggested": "Bound external I/O over untrusted input with a `timeout <budget>` (or `budget …`) row so a slow/hostile peer cannot stall the process (README §27)."},
    "SS3079": {"tier": "T1", "summary": "Internal error disclosed to a client.",
               "found": "A `typeTrust trustedInternal` error reaches a `clientResponse` sink slot with no `errorBoundary` mapping.",
               "suggested": "Map the internal error to a client-safe error with `errorBoundary <InternalError> <ClientError>` before it reaches the response (information-disclosure defense, README §16/§25)."},
    "SS3096": {"tier": "T1", "summary": "Unvalidated bytes-to-text conversion.",
               "found": "A bytes->text decode of a `rawExternal` source whose `out` type is not a `validated`/`trustedInternal` text type.",
               "suggested": "Decode untrusted bytes through a trust boundary that handles invalid UTF-8 explicitly and yields a `validated` text type (README §10.6/§16)."},
    "SS3080": {"tier": "T1", "summary": "Security opt-out without a `because`.",
               "found": "An `optOut <protection>` row (disable-auto-escape / allow-plaintext / skip-csrf / widen-allowlist) with no `because` rationale.",
               "suggested": "Every protection opt-out must be explicit and justified: `optOut <protection> because \"…\"` (README §14)."},
    "SS1561": {"tier": "T1", "summary": "Use after region release.",
               "found": "A value allocated in a region is used after that region was released.",
               "suggested": "Do not use a region-allocated value past its `releaseRegion`; the arena's memory is gone (README §29 #14)."},
    "SS1565": {"tier": "T1", "summary": "Double region release.",
               "found": "A region is `releaseRegion`-d twice in one operation.",
               "suggested": "Release each region exactly once (README §29 #14)."},
    "SS1570": {"tier": "T1", "summary": "Region missing strategy/scope.",
               "found": "A `region` without a `strategy` (arena|fixedBuffer|general) or without a `scope`.",
               "suggested": "Declare `strategy <arena|fixedBuffer|general>` and `scope <op>` on the region (README §29 #14)."},
    "SS1571": {"tier": "T1", "summary": "View missing lifetime.",
               "found": "A call/task that `borrows` a resource declares no `lifetime`.",
               "suggested": "A borrowed view must name what it borrows from: add `lifetime <region|resource>` (README §32.1 #9)."},
    "SS1569": {"tier": "T1", "summary": "Unsafe FFI allocator missing its wrapping rows.",
               "found": "An `unsafe yes` binding without all of `wrapsAs`/`cleanedBy`/`allocator`.",
               "suggested": "A foreign allocator must re-enter as an owned resource: declare `wrapsAs <OwnedType>` + `cleanedBy <freeTarget>` + `allocator <region|c.heap>` (README §26/§30.4)."},
    "SS1568": {"tier": "T1", "summary": "Bounds-checked buffer read with no error path.",
               "found": "A `buffer.get`/`buffer.at`/`buffer.read` call with no `catch` for its BufferBoundsError.",
               "suggested": "A bounds-checked read is fallible — bind `catch <e> BufferBoundsError` and branch on the out-of-bounds error (README §10.6)."},
    "SS1562": {"tier": "T1", "summary": "Region free/allocate mismatch.",
               "found": "An `allocateIn`/`releaseRegion` names an undeclared region, or an op releases a region it never allocated into.",
               "suggested": "Allocate and release the same declared `region`; wrong-region free is unrepresentable when both name the same region (README §29 #14)."},
    "SS1563": {"tier": "T1", "summary": "Allocation without an allocator capability.",
               "found": "An op that `allocateIn` a region has no `uses` capability granting `allocate heap.<region>` (or `allocate heap`).",
               "suggested": "Grant + `uses` an allocator capability (`grants allocate heap.<region>`) for the region (README §8/§29 #14)."},
    "SS3086": {"tier": "T1", "summary": "Weak password-hash cost.",
               "found": "A bcrypt.hashPassword with a constant cost below the safe minimum.",
               "suggested": "Use a cost >= 10 (12 recommended) so password hashing stays expensive (README §8)."},
    "SS3087": {"tier": "T1", "summary": "Non-constant shell command.",
               "found": "A shell/exec call whose command is not a compile-time constant (command injection).",
               "suggested": "Build the command from a constant + an argv list, never a runtime-assembled command string (README §16/§30.2.2)."},
    "SS3088": {"tier": "T1", "summary": "Non-constant format string.",
               "found": "A printf-family call whose format argument is not a compile-time constant (format-string injection).",
               "suggested": "The format string must be a literal/constant; pass dynamic values as arguments (README §30.2.2)."},
    "SS3092": {"tier": "T1", "summary": "Precondition statically violated at a call.",
               "found": "A call passes a literal that violates the callee's `requires <cond> <param>`.",
               "suggested": "Pass a value satisfying the precondition; a satisfying literal is discharged (no runtime check), an unknown value gets a runtime assert (README §6/§10.6)."},
    "SS3091": {"tier": "T1", "summary": "Operation called in a disallowed typestate.",
               "found": "A transition op invoked on a value not in the required `from` state (e.g. a closed handle reused).",
               "suggested": "Follow the type's `typestate` protocol — the op is only allowed from the declared state (README §13/§15.6)."},
    "SS3085": {"tier": "T1", "summary": "Out-of-order guard acquisition (deadlock risk).",
               "found": "An op accesses a lower-rank guarded resource after a higher-rank one.",
               "suggested": "Acquire guards in non-decreasing `guardRank` order so a fixed total order prevents deadlock (README §27/§17)."},
    "SS3083": {"tier": "T1", "summary": "Unguarded shared-state access.",
               "found": "A `readShared`/`setShared` with no `protectedBy`, or a token that isn't the state's declared `guard`.",
               "suggested": "Access shared state only while holding its guard token: `… protectedBy <the sharedState's guard>` (README §8/§27)."},
    "SS3084": {"tier": "T1", "summary": "Unsupported shared-state scope.",
               "found": "A `sharedState` whose `scope` is not `process` or `module`.",
               "suggested": "A sharedState scope must be `process` or `module` (README §8)."},
    "SS3110": {"tier": "T1", "summary": "Integer operand width drift.",
               "found": "A math.* op whose two operands have different declared integer widths.",
               "suggested": "Convert one operand explicitly (e.g. math.convert*) so both operands share a width; EAV has no implicit integer widening (README §10.6)."},
    "SS3111": {"tier": "T1", "summary": "Constant integer UB (div-by-zero / over-wide shift).",
               "found": "A divide/modulo by a constant 0, or a shift by a constant >= the operand width.",
               "suggested": "Constant division/modulo by zero and shifts >= the type width are undefined — fix the constant (README §10.6/§33.5)."},
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
    "SS3045": {"tier": "T1", "summary": "Duplicate `export c` symbol.",
               "found": "Two operations exporting the same C symbol.",
               "suggested": "Export symbols must be unique (README §30.4.2)."},
    "SS3046": {"tier": "T1", "summary": "`literalSource` asset not found.",
               "found": "A compile-time `literalSource` embed whose file could not "
                        "be read (R-124).",
               "suggested": "Check the path and run from the project root; the embed "
                            "is resolved at compile time (README §30.3.2)."},
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
    "SS2620": {"tier": "T1", "summary": "Unknown .semsig schema version.",
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
    "SS1192": {"tier": "T1", "summary": "No entry enabled for a built target.",
               "found": "A project target with zero `entry` ops enabled (every "
                        "entry is `forTarget`-gated to a different target, and "
                        "there is no unqualified default).",
               "suggested": "Add an unqualified `entry`, or a `forTarget <target>` "
                            "entry for this target (README §7/WS3-160)."},
    "SS1193": {"tier": "T1", "summary": "Multiple entries enabled for one target.",
               "found": "Two or more `entry` ops are enabled for the same target "
                        "(both `forTarget`-gated to it, or two unqualified entries).",
               "suggested": "Gate each entry with a distinct `forTarget`, leaving "
                            "exactly one enabled per target (README §7/WS3-160)."},
    "SS1194": {"tier": "T1", "summary": "Project entry names no declared operation.",
               "found": "A project `entry` token that resolves to no declared "
                        "entity, so it would be handed to the JIT as a null "
                        "address and called at runtime (R-104).",
               "suggested": "Name a declared operation (or a webServer entity) for "
                            "the project entry (README §7/§11)."},
    "SS1195": {"tier": "T1", "summary": "runtimeBinding symbol no library provides.",
               "found": "A `body runtimeBinding ss_*` symbol that no native runtime "
                        "library in runtime/manifest.json provides, so it would "
                        "resolve to a null address and crash at first call (R-105).",
               "suggested": "Fix the symbol name, or add a providing library to the "
                            "runtime manifest (README §26)."},
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
    "SS1030": {"tier": "T1", "summary": "Call `out` binding type disagrees with the callee's return type.",
               "found": "A direct call binds its result to a type that differs from the invoked operation's declared `out` type.",
               "suggested": "Bind the result to the callee's exact return type (an alias is a distinct newtype and does not silently coerce) (README §10/§15/WS2-089)."},
    "SS1031": {"tier": "T1", "summary": "`branch if`/`ifFalse` condition is not a Bool.",
               "found": "A `branch if <cond>` / `branch ifFalse <cond>` whose condition binding is a non-Bool type.",
               "suggested": "Branch on a Bool — compute a comparison/predicate first and branch on its result (README §13/WS2-089)."},
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
    # R-080: fail-closed island indentation. The island body shares a common
    # leading-space prefix (README §16/§33.2); a non-blank line shallower than
    # the island's first body line is a visually ambiguous paste, not a deeper
    # nesting, so it is rejected rather than silently re-anchored to column 1.
    "SS3024I": {"tier": "T1", "summary": "Inconsistent island indentation.",
                "found": "A `body <kind>` island whose lines do not share a common "
                         "leading-space prefix (a line dedents below the island anchor "
                         "or mixes tabs/spaces).",
                "suggested": "Indent every island line to at least the first body line, "
                             "spaces only (README §16, §33.2)."},
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
    # WS2-093: an op with no `effect` rows claims purity; its transitive effective
    # set must be empty for that claim to be sound (deny-tier — purity is a real
    # guarantee callers rely on, e.g. `memory heap no` / const-fold safety).
    "SS1705": {"tier": "T0", "summary": "Pure operation has a non-empty effective effect set.",
               "found": "An op with no `effect` rows that transitively activates a call/task/cleanup carrying an effect.",
               "suggested": "Declare the effects it actually causes (`effect <action> <resource>`), or stop activating the effectful target — a pure op must be provably side-effect-free (README §10.6/§30.3.2, WS2-093)."},
    # WS2-091: an op's contract must be *complete* — every effect it can cause
    # (effective set) is either declared on the op (`effect`) or authorized by a
    # covering `uses` capability. An effect that is neither declared nor covered
    # is a genuinely hidden effect leaking up from a callee (deny-tier).
    "SS1706": {"tier": "T0", "summary": "Operation can cause an effect it neither declares nor is authorized for.",
               "found": "An effect that flows up from an activated call/task/cleanup, absent from the op's own `effect` rows AND not covered by any `uses` capability the op holds.",
               "suggested": "Declare it (`effect <action> <resource>`) or authorize it with a covering `uses` capability — the contract must list every effect the op can cause (README §15/§17 #5, WS2-091)."},
    "SS1707": {"tier": "T1", "summary": "operationType effect bound exceeded.",
               "found": "An operation bound as a value of an `operationType` whose "
                        "effective effects are not a subset of the operationType's "
                        "declared effect bound (behavior-as-data effect escape).",
               "suggested": "Add the missing effect(s) to the operationType bound, or "
                            "bind an operation within the bound (README §33.9/WS2-092)."},
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
    """Return the registry entry for a diagnostic code (README §29 #12). Covers
    both the compile-time band (DIAGNOSTICS, SS####/MD####) and the runtime trap
    band (RUNTIME_DIAGNOSTICS, SSR####; WS1-136)."""
    if code in DIAGNOSTICS:
        return DIAGNOSTICS[code]
    if code in RUNTIME_DIAGNOSTICS:
        return RUNTIME_DIAGNOSTICS[code]
    raise EavError(f"unknown diagnostic code {code!r}")


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
    """`Found / Suggested fix` repair text for a code (README §17 repair format).
    Runtime trap codes (SSR####) carry a kind + repair instead of tier/found."""
    entry = explain(code)
    if "repair" in entry:  # runtime trap band (WS1-136)
        return (
            f"{code} (runtime trap · {entry['kind']}): {entry['summary']}\n"
            f"  Repair: {entry['repair']}"
        )
    return (
        f"{code} ({entry['tier']}): {entry['summary']}\n"
        f"  Found:        {entry['found']}\n"
        f"  Suggested fix: {entry['suggested']}"
    )


def _filter_diagnostics_strict(diags: list[Diagnostic], strict: bool) -> list[Diagnostic]:
    """Filter diagnostics by tier when --strict is enabled. WS2-071.

    Rules:
    - Default (strict=False): deny-tier (T0/T1/T2) are errors; T3/T4 are warnings
    - Strict (strict=True): additionally block T3 (opinionated tier)
    - T4 (style) never blocks

    When strict=True, diagnostics with tier T3 have their severity promoted to error.
    """
    if not strict:
        return diags
    result = []
    for d in diags:
        entry = explain(d.code)
        tier = entry.get("tier", "T4")
        if tier == "T3" and d.severity == "warning":
            # Promote T3 warnings to errors in strict mode (SS2071)
            result.append(Diagnostic(
                code=d.code,
                severity="error",
                message=d.message,
                line=d.line,
                entity=d.entity,
            ))
        else:
            result.append(d)
    return result


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
    "sharedState",  # WS2-083 guarded cross-task mutable state
    "region",       # WS1-112 allocation region (arena/fixedBuffer/general)
    "typestate",    # X-091 protocol/state-machine over a type
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
    "readShared",
    "setShared",
    "allocateIn",
    "releaseRegion",
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


def _semver_identifier_key(identifier: str) -> tuple:
    """SemVer §11.4 per-identifier precedence (R-010): a numeric identifier
    compares numerically and ranks *below* any alphanumeric identifier, which
    compares in ASCII order. The leading `0`/`1` discriminant encodes that
    numeric-below-alphanumeric rule; the trailing slots keep the two cases
    shape-comparable so list comparison never mixes an int with a str."""
    if identifier.isdigit():
        return (0, int(identifier), "")
    return (1, 0, identifier)


def _parse_semver(v: str) -> tuple:
    """Sort key for a `v`-prefixed semver (README ss28.4 / SemVer §11). Release
    sorts above an otherwise-equal pre-release; pre-release precedence follows
    SemVer §11.4 (R-010) — each dot-separated identifier is compared by
    `_semver_identifier_key`, and a longer identifier list outranks an
    equal-prefix shorter one (Python list comparison gives this for free). Build
    metadata (after `+`) is ignored for ordering."""
    if not v.startswith("v"):
        raise EavError(f"version {v!r} must be v-prefixed (README ss2)")
    core = v[1:].split("+", 1)[0]
    num, _, pre = core.partition("-")
    parts = num.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise EavError(f"malformed semver {v!r} (README ss2)")
    major, minor, patch = (int(p) for p in parts)
    if pre == "":
        pre_key = (1,)  # release outranks any pre-release of the same core
    else:
        pre_key = (0, [_semver_identifier_key(i) for i in pre.split(".")])
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


def is_project_root(root: str) -> bool:
    """True when a directory is an app/project root (README §28.2): it carries a
    `build.sem` manifest or a `src/` module tree. R-003: only such directories
    compose into a single runtime program; a bare directory of unrelated fixtures
    (the experiment workspace) is not a project and must not be composed."""
    import os
    return (os.path.isfile(os.path.join(root, "build.sem"))
            or os.path.isdir(os.path.join(root, "src")))


def load_project(root: str) -> str:
    """Project driver (README §28.2/§28.3): compose the runtime program of a
    project directory. The `project` entity lives in `build.sem` (the manifest,
    §7/§28), so it is prepended; the modules live under `src/` — every
    `src/**/*.sem` (recursively, so each submodule directory's root `main.sem`
    is included) that is not a `*.test.sem`. `build.sem.lock` and tests are not
    part of the runtime program. A flat `<root>/*.sem` layout (no `src/`, no
    `build.sem`) is still accepted for single-file demos.

    R-003: composition fails closed for a non-project directory. When there is no
    `src/` module tree the flat fallback scans only the *top level* (non-recursive)
    — never the whole subtree — so a workspace directory of unrelated fixtures
    (`apps/`, `examples/`, `std/`, `invalid_corpus/`, …) cannot be silently glued
    into one program and report a misleading compiler error from a negative
    fixture. The recursive `**` scan is reserved for a real `src/` tree."""
    import glob
    import os
    parts: list[str] = []
    build = os.path.join(root, "build.sem")
    if os.path.isfile(build):
        parts.append(open(build, encoding="utf-8").read())
    src_dir = os.path.join(root, "src")
    if os.path.isdir(src_dir):
        # a real module tree may nest submodules, so recurse under `src/` only.
        candidates = glob.glob(os.path.join(src_dir, "**", "*.sem"), recursive=True)
    else:
        # flat single-file-demo fallback: top-level files only (R-003). A bare
        # workspace root is not a project, so we never recurse into its children.
        candidates = glob.glob(os.path.join(root, "*.sem"))
    files = sorted(f for f in candidates if classify_sem_file(f) == "source")
    if not files and not parts:
        raise EavError(f"no source .sem files found under {root!r} (README ss28.2)")
    parts.extend(open(f, encoding="utf-8").read() for f in files)
    return "\n".join(parts)


# R-003: directories that hold build/cache/asset output, not checkable source.
# The negative-fixture corpus is excluded by design — those files are meant to
# fail and are only exercised by the dedicated negative-corpus test.
_WORKSPACE_SKIP_DIRS = frozenset({
    "invalid_corpus", "dist", "build", "_build", "_pyi_build", "__pycache__",
    "assets", "runtime", "docs", ".git",
    # R-094: a root `check .` must not walk vendored, generated, legacy, or
    # editor-dependency trees (a normal checkout after `npm install` would
    # otherwise false-fail on node_modules, libuv, the legacy product, etc.).
    "node_modules", "third_party", "legacy", "experiments", "vscode-semanticscript",
    ".github", ".venv", "venv",
})


def discover_workspace(root: str) -> list:
    """R-003: enumerate the independently-checkable children of a *workspace*
    directory (one that is not itself a project root). The experiment root holds
    unrelated fixtures — apps, examples, std modules, signatures, manifests — that
    must each be checked on their own, never composed into one program.

    Returns an ordered list of `{"path", "kind", "name"}` children:
      * a subdirectory that `is_project_root` -> kind "project" (checked as a unit;
        the walk does not descend into it);
      * any other `.sem`/`.semsig` file -> kind "file";
    Excludes `_WORKSPACE_SKIP_DIRS` (notably `invalid_corpus/`, whose negative
    fixtures are intentionally malformed) so they never leak into normal checks."""
    import os
    children: list = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune skip dirs in place so os.walk does not descend into them.
        dirnames[:] = [d for d in dirnames if d not in _WORKSPACE_SKIP_DIRS]
        # a project root is checked as one unit; do not walk its internals.
        project_dirs = [d for d in dirnames if is_project_root(os.path.join(dirpath, d))]
        for d in project_dirs:
            full = os.path.join(dirpath, d)
            children.append({"path": full, "kind": "project",
                             "name": os.path.relpath(full, root)})
        dirnames[:] = [d for d in dirnames if d not in project_dirs]
        for f in filenames:
            if classify_sem_file(f) in ("source", "semsig", "build"):
                full = os.path.join(dirpath, f)
                children.append({"path": full, "kind": "file",
                                 "name": os.path.relpath(full, root)})
    children.sort(key=lambda c: c["name"].replace("\\", "/"))
    return children


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
    """Locate tests by layout (README §28.7): co-located `src/**/*.test.sem`
    (unit/semantic) and `tests/**/*.sem` suites (integration/e2e), plus
    `tests/golden/` assets. R-006: both scans recurse so a submodule's
    `src/feature/feature.test.sem` and a nested `tests/integration/case.sem` are
    found, not only the top level. The `tests/golden/` directory holds fixtures,
    not test sources, so it is excluded from the suite scan."""
    import glob
    import os
    src_dir = os.path.join(root, "src")
    base = src_dir if os.path.isdir(src_dir) else root
    co_located = sorted(glob.glob(
        os.path.join(base, "**", "*.test.sem"), recursive=True))
    golden_dir = os.path.normpath(os.path.join(root, "tests", "golden"))
    tests_dir = sorted(
        f for f in glob.glob(os.path.join(root, "tests", "**", "*.sem"), recursive=True)
        if not os.path.normpath(f).startswith(golden_dir + os.sep))
    golden = sorted(glob.glob(os.path.join(root, "tests", "golden", "*"))) if os.path.isdir(
        golden_dir) else []
    return {
        "coLocated": [os.path.relpath(f, root) for f in co_located],
        "testsDir": [os.path.relpath(f, root) for f in tests_dir],
        "golden": [os.path.relpath(f, root) for f in golden if os.path.isfile(f)],
    }


def load_test_project(root: str) -> Program:
    """R-007: compose a project's *runtime* program with its companion test
    sources into one `Program`, so `tag test` operations that live in
    `src/**/*.test.sem` are actually executable.

    `load_project` deliberately excludes `*.test.sem` (tests are not part of the
    shipped runtime program), so `cmd_test` on a project directory previously ran
    zero generated tests — a scaffold's `checkGreetingLength` was discovered by
    layout but never composed in, so the test runner saw an empty program.

    The composition runs `load_project` for the runtime program, then merges each
    co-located test file (discovered via `discover_project_tests`, which recurses
    per R-006) at the Program level. A test file is its own standalone program —
    it carries a throwaway `project` entity (so it can be checked alone) and may
    redeclare shared types like `ExitCode`. Those would collide on a flat text
    concat (duplicate `is` row, two `project` entities), so the merge:
      * drops the test file's `project` entity (the runtime project from
        `build.sem` is authoritative); and
      * skips any entity whose name already exists in the runtime program
        (runtime declarations win — e.g. the shared `ExitCode` alias).
    The remaining test-only entities (the `tag test` operations and any test
    helper types/modules) are appended, along with their indentation islands."""
    runtime = parse_compact(load_project(root))
    discovered = discover_project_tests(root)
    for rel in discovered["coLocated"]:
        import os
        test_source = open(os.path.join(root, rel), encoding="utf-8").read()
        test_program = parse_compact(test_source)
        for name in test_program.order:
            entity = test_program.entities[name]
            # the runtime project (build.sem) is authoritative; a test file's own
            # project/duplicate entity is throwaway scaffolding for standalone runs.
            if entity.kind == "project" or name in runtime.entities:
                continue
            runtime.add(entity)
            # carry the merged entity's indentation islands (body sql/html/...).
            for island_key, island_lines in test_program.islands.items():
                if island_key[0] == name:
                    runtime.islands[island_key] = island_lines
    return runtime


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
    unknown schema `version` is rejected (SS2620)."""
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
                code="SS2620",  # R-160: was SS2601 (shadowed by webServer route-method)
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


def _line_comment(text: str) -> Optional[str]:
    """Return the comment portion of a line (from the first *unquoted* `#` to the
    end), or None if the line has no comment. String-aware so `# security:` text
    inside a `"..."` literal is not mistaken for a typed comment (README §2).

    R-080: typed-comment retention reuses this so a `# security:` note that is
    actually source data (e.g. inside a quoted value) is never harvested as
    metadata, only genuine comments are."""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "#":
            return text[i:]
        if ch == '"':
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        i += 1
    return None


def _typed_comment_from_comment(comment: Optional[str]) -> Optional[tuple[str, str]]:
    """Match an already-extracted line comment against the typed-comment grammar,
    returning (tag, text) or None. Split from _typed_comment_of_line so a caller
    that already computed the comment (the parse loop) does not rescan the line."""
    if comment is None:
        return None
    m = _TYPED_COMMENT_RE.match(comment)
    if m:
        return (m.group(1), m.group(2).strip())
    return None


def _typed_comment_of_line(text: str) -> Optional[tuple[str, str]]:
    """Match a single line's (string-aware) comment against the typed-comment
    grammar, returning (tag, text) or None (README §2, R-080)."""
    return _typed_comment_from_comment(_line_comment(text))


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


_PLATFORM_ARCH_TRIPLE = {
    "amd64": "x86_64", "x86_64": "x86_64", "x64": "x86_64",
    "arm64": "aarch64", "aarch64": "aarch64",
    "x86": "i686", "i686": "i686", "i386": "i686",
    "wasm32": "wasm32",
}


def _platform_triple(plat: "Entity") -> str:
    """Map a `platform` entity's os/arch/targetRuntime to an LLVM target triple
    (R-017, README §28.1). A wasm/wasi runtime wins; otherwise os+arch select the
    triple. Unspecified/unknown os falls back to the host triple, so a platform
    that only carries native-link rows still builds for the host."""
    import llvmlite.binding as _llvm

    def val(pred):
        row = plat.fact(pred)
        return (row.payload[0].lower() if row and row.payload else "")

    os_name, arch, runtime = val("os"), val("arch"), val("targetRuntime")
    # `targetRuntime` is `native` or `wasm` (SS0740); a wasm runtime is a wasm32
    # emscripten triple regardless of os/arch.
    if runtime == "wasm":
        return "wasm32-unknown-emscripten"
    machine = _PLATFORM_ARCH_TRIPLE.get(arch, "x86_64")
    if os_name in ("windows", "win", "win32"):
        return f"{machine}-pc-windows-msvc"
    if os_name in ("macos", "darwin", "osx"):
        return f"{'arm64' if machine == 'aarch64' else machine}-apple-darwin"
    if os_name in ("linux",):
        return f"{machine}-unknown-linux-gnu"
    return _llvm.get_default_triple()


def _resolve_build_platform(program: Program, name: Optional[str]) -> Optional["Entity"]:
    """Resolve a `--platform NAME` to its declared `platform` entity (R-017).
    `None` means the host default (no platform filtering, host triple). An
    unknown name raises an EavError naming the declared platforms."""
    if name is None:
        return None
    ent = program.entities.get(name)
    if ent is None or ent.kind != "platform":
        declared = sorted(n for n in program.order
                          if program.entities[n].kind == "platform")
        raise EavError(
            f"unknown platform {name!r}; declared platforms: {declared} "
            f"(README §28.1/§30.3.1)")
    return ent


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


# X-083 threat-model coverage matrix (README §29 #19). Each row maps a
# vulnerability class to its asset, the EAV defense (a real diagnostic code, an
# external mechanism, or an explicit out-of-language note), status, and the
# owning todo. `security_matrix_markdown` renders it; a test (X-083) asserts every
# named diagnostic code exists in DIAGNOSTICS and every row is classified.
SECURITY_COVERAGE = [
    {"vuln": "SQL/HTML/path/URL injection", "asset": "trust", "todo": "X-070/X-071",
     "code": "SS3071", "status": "covered",
     "note": "typed trust flow + sink-typing; raw String / string-built input rejected at sinks"},
    {"vuln": "Untrusted value at a trust-sensitive sink", "asset": "trust", "todo": "X-070",
     "code": "SS3070", "status": "covered",
     "note": "rawExternal/secret value into a trustConstraint sink is rejected"},
    {"vuln": "Secret disclosure (logs/transcripts/source)", "asset": "confidentiality",
     "todo": "X-072", "code": "SS3072", "status": "covered",
     "note": "secret value to an observable sink, or a hardcoded secret literal, is rejected"},
    {"vuln": "Timing side-channel on secret compare", "asset": "confidentiality",
     "todo": "X-074", "code": "SS3074", "status": "covered",
     "note": "secrets compare only via crypto.equalConstantTime"},
    {"vuln": "Weak/predictable crypto randomness + nonce reuse", "asset": "confidentiality",
     "todo": "X-073", "code": "SS3073", "status": "covered",
     "note": "security material needs the CSPRNG; nonces/IVs are affine"},
    {"vuln": "SSRF (server-side request forgery)", "asset": "authority", "todo": "X-075",
     "code": "SS3075", "status": "covered",
     "note": "internal/loopback/metadata URL literal rejected; HttpSafeUrl required"},
    {"vuln": "Path traversal / absolute-escape", "asset": "authority", "todo": "X-076",
     "code": "SS3076", "status": "covered",
     "note": "../ or absolute fs path literal rejected; SafePath required"},
    {"vuln": "Deserialization DoS / type confusion", "asset": "availability", "todo": "X-077",
     "code": "SS3077", "status": "covered",
     "note": "untrusted decode requires a size limit"},
    {"vuln": "Resource-exhaustion DoS (slow peer)", "asset": "availability", "todo": "X-078",
     "code": "SS3078", "status": "covered",
     "note": "external I/O over untrusted input requires a timeout/budget"},
    {"vuln": "Information disclosure via error detail", "asset": "confidentiality",
     "todo": "X-079", "code": "SS3079", "status": "covered",
     "note": "internal error to a client-response sink requires an errorBoundary mapping"},
    {"vuln": "Insecure-by-default web surface", "asset": "authority", "todo": "X-080",
     "code": "SS3080", "status": "covered",
     "note": "every protection opt-out requires an explicit `because`"},
    {"vuln": "Supply-chain effect escalation", "asset": "supply-chain", "todo": "X-081",
     "code": "SS2805", "status": "covered",
     "note": "fail-closed: dependency effect surface must be in the root allowlist; no transitive escalation"},
    {"vuln": "Malformed-UTF-8 corruption at input boundary", "asset": "trust",
     "todo": "X-096", "code": "SS3096", "status": "covered",
     "note": "bytes->text decode of untrusted input must yield a validated text type"},
    {"vuln": "Float used for money/exact value", "asset": "correctness", "todo": "X-093",
     "code": "SS3093", "status": "covered",
     "note": "Decimal/Money kept out of Float arithmetic; Float equality warns (SS3094)"},
    {"vuln": "Wall-clock arithmetic / elapsed-time bug", "asset": "correctness",
     "todo": "X-095", "code": "SS3095", "status": "covered",
     "note": "WallTime has no arithmetic; durations use MonotonicInstant"},
    {"vuln": "Use-after-free / use-after-move / view escape", "asset": "memory",
     "todo": "WS1-111/113", "code": "SS1564", "status": "covered",
     "note": "borrowed-view escape (SS1560), view-with-cleanup (SS1566), use-after-move (SS1564)"},
    {"vuln": "Per-record authorization / session / business logic", "asset": "authority",
     "todo": None, "code": None, "status": "out-of-language",
     "note": "application-domain authZ; the stdlib seam is capabilities + the trust types, but the policy is app code"},
    {"vuln": "Off-by-one / logic bugs", "asset": "correctness", "todo": None, "code": None,
     "status": "out-of-language",
     "note": "inherent app-logic class; mitigated by tests/goldens, not a language invariant"},
]


def security_matrix_markdown() -> str:
    """Render SECURITY_COVERAGE as a Markdown table (X-083 living matrix)."""
    return _coverage_markdown("EAV threat-model coverage matrix (X-083)",
                              SECURITY_COVERAGE)


# X-101 defect-class coverage ledger (README §29 #19): extends the X-083 security
# matrix to ALL defect families — memory (§1J), correctness/reliability (X7) —
# with partial (🟡) rows for defenses whose runtime is still deferred and
# out-of-language rows for inherent/app-only classes plus their review seam.
_ADDITIONAL_DEFECT_LEDGER = [
    {"vuln": "Leak / double-free of plain values (no GC)", "asset": "memory",
     "todo": "WS1-110", "code": None, "status": "partial",
     "note": "value-class move + free-at-last-use; ownership rules drafted, codegen pending"},
    {"vuln": "Wrong-region / arena allocation safety", "asset": "memory",
     "todo": "WS1-112", "code": None, "status": "partial",
     "note": "region entity + allocator-as-capability; allocation runtime pending"},
    {"vuln": "Buffer/slice out-of-bounds (no OOB/UB)", "asset": "memory",
     "todo": "WS1-115", "code": None, "status": "partial",
     "note": "bounds-checked Buffer/Slice with view lifetimes; buffer runtime pending"},
    {"vuln": "Owned-resource leak (file/db/handle)", "asset": "reliability",
     "todo": "WS1-114", "code": "SS1503", "status": "covered",
     "note": "owns/cleanedBy + defer on every path; explicit ordering rows pending (WS1-114)"},
    {"vuln": "Divergence / infinite loop", "asset": "correctness",
     "todo": "X-100", "code": "SS0950", "status": "covered",
     "note": "no-progress / no-exit-path loop lint"},
    {"vuln": "Source-observable nondeterminism", "asset": "correctness",
     "todo": "X-094", "code": None, "status": "partial",
     "note": "clock/random-as-capability + capturedOutputReplay done; collection ordering pends the collections runtime"},
    {"vuln": "Unchecked pre/postconditions", "asset": "correctness",
     "todo": "X-092", "code": None, "status": "partial",
     "note": "invariant/guarantee are metadata; statically-discharged/trapping requires/ensures pending"},
    {"vuln": "Protocol/typestate misuse", "asset": "correctness",
     "todo": "X-091", "code": "SS1564", "status": "partial",
     "note": "resource open/use/close + move lifecycle enforced; general typestate machine pending"},
    {"vuln": "Error-context loss on propagate", "asset": "reliability",
     "todo": "X-099", "code": None, "status": "partial",
     "note": "onFailure propagate exists; causedBy provenance chaining pending"},
    {"vuln": "Data race / TOCTOU outside guards", "asset": "correctness",
     "todo": None, "code": None, "status": "out-of-language",
     "note": "single-thread backend is race-free; the concurrent backend gates X-082/X-090; race-to-trust outside guards is app discipline + review"},
]
DEFECT_LEDGER = SECURITY_COVERAGE + _ADDITIONAL_DEFECT_LEDGER


def _coverage_markdown(title: str, rows_data: list) -> str:
    icon = {"covered": "✅", "partial": "🟡", "out-of-language": "—"}
    rows = ["| Defect class | Asset | EAV defense | Status | Owning todo |",
            "| --- | --- | --- | --- | --- |"]
    for r in rows_data:
        defense = r["code"] or r["note"]
        rows.append(
            f"| {r['vuln']} | {r['asset']} | {defense} | {icon.get(r['status'], r['status'])} "
            f"| {r['todo'] or 'n/a (out-of-language)'} |")
    return f"# {title}\n\n" + "\n".join(rows) + "\n"


def defect_ledger_markdown() -> str:
    """Render the full defect-class ledger as Markdown (X-101)."""
    return _coverage_markdown("EAV defect-class coverage ledger (X-101)", DEFECT_LEDGER)


def _effect_surface(lock_program: Program) -> set:
    return {
        (r.payload[0], r.payload[1])
        for proj in lock_program.of_kind("project")
        for r in proj.facts("effectSurface")
        if len(r.payload) >= 2
    }


def supply_chain_diff(old_lock: Program, new_lock: Program) -> list:
    """X-081 / README §28.5 (WS4-020): the effects newly present in `new_lock`'s
    resolved `effectSurface` that were absent from `old_lock`. A dependency newly
    requesting an effect is a reviewable supply-chain change (a `sem diff`
    finding) on top of the fail-closed allowlist (verify_supply_chain / SS2805).
    Because the effect surface is the transitive closure, a transitive dependency
    that newly asks for authority surfaces here too — and is still blocked by the
    root allowlist (no transitive capability escalation)."""
    return sorted(_effect_surface(new_lock) - _effect_surface(old_lock))


def sha256_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def embed_literal_source(path: str, expected_digest: str = None) -> bytes:
    """Compile-time asset embedding (README ss30.3.2): read the file's bytes and,
    if a `literalDigest` is given, verify its sha256 (a mismatch is a hard error).

    R-124: a missing/unreadable asset is a structured compile diagnostic (SS3046),
    not a raw FileNotFoundError traceback (build) or an SSR0001 runtime-trap
    mislabel (run --json) — asset resolution is deterministic, not a runtime fault."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise EavError(
            f"literalSource asset {path!r} could not be read at compile time: "
            f"{exc} (resolve it relative to the project root, README §30.3.2)",
            code="SS3046")
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
    "literalDigest", "literalEncoding",  # WS2-084 embed encoding/digest rows
    "align", "layout", "inlineCapacity", "arrayLength",  # WS2-084 layout rows
    "grants", "invokes", "arg", "discards", "catch",
    "purpose", "invariant", "note", "rationale", "risk", "example", "tag",
    "deprecated", "owner", "target", "owns", "cleanedBy", "cleans",
    "borrows", "lifetime", "mayEscape",  # WS1-111 borrowed-view rows
    "consumes", "takesOwnership",         # WS1-113 ownership-transfer rows
    "outParam",                           # WS3-016 FFI out-param ABI marker
    "useRetry",                           # R-041 bounded-retry call row
    "typeParam",                          # R-039 generic type parameter
    "instantiates",                       # R-039 named generic-record instantiation
    "sharedState", "guard", "protectedBy", "readShared", "setShared",  # WS2-083
    "guardRank",                           # X-090 lock-acquisition order
    "region", "strategy", "capacity", "allocateIn", "releaseRegion",  # WS1-112
    "unsafe", "wrapsAs", "allocator",      # WS1-116 FFI allocation wrapping
    "typestate", "state", "initial", "allows",  # X-091 typestate
    "requires", "ensures",                 # X-092 checked contracts
    "typeTrust",                           # X-070 trust label on a type
    "limit",                               # X-077 decode-limit row
    "timeout", "budget",                   # X-078 DoS-bound rows
    "maxIterations",                       # R-082 loop iteration bound
    "clientResponse", "errorBoundary",     # X-079 error-disclosure rows
    "optOut",                              # X-080 protection opt-out row
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
        "resolved", "toolchainResolved", "effectSurface", "optOut",
    },
    "module": {"path", "imports", "exports"},
    "capability": {"grants"},
    "sharedState": {"scope", "type", "mutability", "value", "guard", "owner",
                    "guardRank"},
    "region": {"strategy", "scope", "capacity"},
    "typestate": {"for", "state", "initial", "allows"},
    "error": {"typeTrust"},
    "errorCase": {"of", "payload"},
    # R-039: a record may be generic (`typeParam T` + fields typed `T`) or a
    # named monomorphic instantiation (`instantiates Base <TypeArgs…>`).
    "record": {"field", "typeTrust", "align", "layout", "typeParam",
               "instantiates"},  # WS2-084 layout rows
    # R-039/R-054: an enum may be generic (`typeParam T`, variants typed `T`) or
    # a named monomorphic instantiation (`instantiates Base <TypeArgs…>`).
    "enum": {"variant", "repr", "typeTrust", "typeParam", "instantiates"},
    # WS2-084: aliases carry the type-memory parity rows — `memory <inline|heap|
    # spill|region>`, `inlineCapacity N`, `layout`, `arrayLength N`, `allocator`.
    "alias": {"for", "typeTrust", "memory", "inlineCapacity", "layout",
              "arrayLength", "allocator"},
    "operation": {
        "in", "out", "effect", "uses", "memory", "async", "label", "let",
        "body", "export",
        "do", "defer", "start", "join", "poll", "cancel", "detach",
        "branch", "return", "goto", "set", "trustConstraint", "errorBoundary",
        "optOut", "readShared", "setShared", "allocateIn", "releaseRegion",
        "unsafe", "wrapsAs", "allocator", "cleanedBy",  # WS1-116 FFI allocator op
        "requires", "ensures",  # X-092 checked contracts
        "maxIterations",  # R-082 loop iteration bound for untrusted-size loops
        "outParam",  # WS3-016 FFI out-param ABI on a runtimeBinding op
        "typeParam",  # R-039 generic type parameter (monomorphized)
    },
    "function": {
        "in", "out", "effect", "uses", "memory", "async", "label", "let",
        "body", "export",
        "do", "defer", "start", "join", "poll", "cancel", "detach",
        "branch", "return", "goto", "set", "errorBoundary", "optOut",
        "readShared", "setShared", "allocateIn", "releaseRegion",
        "unsafe", "wrapsAs", "allocator", "cleanedBy",  # WS1-116 FFI allocator op
        "requires", "ensures",  # X-092 checked contracts
        "maxIterations",  # R-082 loop iteration bound for untrusted-size loops
        "outParam",  # WS3-016 FFI out-param ABI on a runtimeBinding op
        "typeParam",  # R-039 generic type parameter (monomorphized)
    },
    "call": {
        "in", "invokes", "arg", "out", "catch", "discards", "owns",
        "cleanedBy", "effect", "async",  # async = tolerated-deprecated (ss5)
        "borrows", "lifetime", "mayEscape",  # WS1-111 borrowed-view rows
        "takesOwnership",                     # WS1-113 ownership transfer
        "limit",                              # X-077 decode limits
        "timeout", "budget",                  # X-078 DoS bounds
        "useRetry",                           # R-041 bounded retry of a fallible call
    },
    "task": {
        "in", "invokes", "arg", "out", "catch", "discards", "owns",
        "cleanedBy", "effect",
        "borrows", "lifetime", "mayEscape",  # WS1-111 borrowed-view rows
        "takesOwnership",                     # WS1-113 ownership transfer
        "limit",                              # X-077 decode limits
        "timeout", "budget",                  # X-078 DoS bounds
    },
    "cleanup": {"in", "call", "onFailure", "because", "cleans"},
    "storage": {
        "scope", "type", "mutability", "value", "body", "literalSource",
        "literalDigest", "literalEncoding",  # WS2-084 embed encoding row
    },
    "htmlTemplate": {"body"},
    "webServer": {
        "host", "port", "startup", "shutdown", "notFound", "methodNotAllowed",
        "route", "middleware", "optOut",
    },
    "platform": {
        "os", "arch", "targetRuntime", "output", "override",
        "nativeLibrary", "nativeHeader", "nativeLinkFlag",
    },
    "intrinsic": {"target", "arg", "out", "catch", "async", "owns",
                  "trustConstraint", "clientResponse",
                  "borrows", "lifetime", "mayEscape",  # WS1-111 view rows on a sig
                  "unsafe", "wrapsAs", "allocator", "cleanedBy"},  # WS1-116 FFI
    "semsig": {"version", "generatedBy", "describes"},
    "operationType": {"in", "out", "effect"},  # WS2-092: effect bound (§33.9)
}


@dataclass
class Row:
    subject: str
    predicate: str
    payload: list[str]
    line: int
    label: Optional[str] = None  # set for `at LABEL <stepPred> ...` rows
    comment: Optional[str] = None  # R-086: trailing `# ...` preserved by fmt


@dataclass
class Entity:
    name: str
    kind: str
    line: int
    rows: list[Row] = field(default_factory=list)
    # R-086: comments preserved by fmt. `lead` are full-line `# ...` lines that
    # precede the entity (its header block); `comment` is a trailing comment on
    # the `is` row; `trailing` are full-line comments after the last entity (EOF).
    lead: list[str] = field(default_factory=list)
    comment: Optional[str] = None
    trailing: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Backing store for the lazy fact index (see _fact_index). Not dataclass
        # fields, so they stay out of eq/repr.
        self._idx = None
        self._idx_len = -1

    def _fact_index(self) -> dict:
        """Lazy `predicate -> [Row,...]` index over the (label-less) rows. Rebuilt
        only when the row count changes, so it stays correct across the appends
        that happen during parse while making the millions of fact()/facts()
        lookups in validate + lower O(1) instead of an O(rows) scan each."""
        if self._idx_len != len(self.rows):
            idx: dict = {}
            for r in self.rows:
                if r.label is None:
                    idx.setdefault(r.predicate, []).append(r)
            self._idx = idx
            self._idx_len = len(self.rows)
        return self._idx

    def facts(self, predicate: str) -> list[Row]:
        return list(self._fact_index().get(predicate, ()))

    def fact(self, predicate: str) -> Optional[Row]:
        rows = self._fact_index().get(predicate)
        return rows[0] if rows else None


@dataclass
class Program:
    entities: dict[str, Entity] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    islands: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # R-080: typed comments (`# <tag>: text`, README §2/§34) retained as
    # structured metadata so important `# security:`/`# failure:` notes survive
    # into docs/describe surfaces instead of disappearing. Each item is
    # (tag, text, line); line is 1-based for the source row carrying the comment.
    typed_comments: list[tuple[str, str, int]] = field(default_factory=list)

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
        "guard", "protectedBy",  # WS2-083 sharedState guard sub-keywords
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
            raise EavError(
                "island indentation must be spaces, not tabs (README ss2/ss16)",
                code="SS3024I",
            )
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
    pending_lead: list[str] = []  # R-086: buffered full-line `# ...` comments
    while i < n:
        raw = raw_lines[i]
        lineno = i + 1
        stripped = raw.strip()
        # R-080: retain typed comments (`# <tag>: text`) as structured metadata.
        # Harvested here at the top of the row loop, so both full-line and
        # trailing typed comments are captured; island body lines are consumed by
        # the island block (which sets `i = j`) and never re-enter this loop, so
        # foreign-content `#` text (CSS/SQL comments) is correctly excluded.
        line_cmt = _line_comment(raw)  # computed once; reused for row comments below
        tc = _typed_comment_from_comment(line_cmt)
        if tc is not None:
            program.typed_comments.append((tc[0], tc[1], lineno))
        if not stripped:
            i += 1
            continue
        if stripped.startswith("#"):
            pending_lead.append(stripped)  # R-086: preserve full-line comments
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
            # R-086: full-line comments preceding this entity become its header
            # block; a trailing comment on the `is` line is preserved in place.
            _new_ent = program.entities[subject]
            _new_ent.lead = list(pending_lead)
            _new_ent.comment = line_cmt
            pending_lead.clear()
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
            if pending_lead:  # R-086
                entity.lead.extend(pending_lead)
                pending_lead.clear()
            _lr = Row(subject, step_pred, payload[2:], lineno, label=label)
            _lr.comment = line_cmt
            entity.rows.append(_lr)
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
            # R-080: fail-closed indentation. The first non-blank body line is
            # the island anchor; every subsequent non-blank line must be indented
            # at least as deep (deeper = nested HTML/JSON/SQL, which is fine). A
            # line shallower than the anchor — but still indented — is a visually
            # ambiguous paste (README §16/§33.2): the old common-prefix strip
            # would silently re-anchor it to column 1 and corrupt the island, so
            # we reject it instead. The anchor is the common prefix stripped
            # uniformly, preserving relative nesting verbatim.
            indented = [b for b in body_lines if b.strip()]
            if indented:
                base = _leading_spaces(indented[0])
                for b in indented[1:]:
                    if _leading_spaces(b) < base:
                        raise EavError(
                            f"inconsistent island indentation in {subject!r} "
                            f"{island_kind!r} body: line {b.strip()!r} is indented "
                            f"less than the island's first line (anchor {base} "
                            f"spaces); island lines share a common leading-space "
                            f"prefix and may only nest deeper (README ss16/ss33.2)",
                            lineno,
                            code="SS3024I",
                        )
                body_lines = [b[base:] if b.strip() else "" for b in body_lines]
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            program.islands[(subject, island_kind)] = body_lines
            if pending_lead:  # R-086
                entity.lead.extend(pending_lead)
                pending_lead.clear()
            _ir = Row(subject, predicate, payload, lineno)
            _ir.comment = line_cmt
            entity.rows.append(_ir)
            i = j
            continue

        if pending_lead:  # R-086
            entity.lead.extend(pending_lead)
            pending_lead.clear()
        _gr = Row(subject, predicate, payload, lineno)
        _gr.comment = line_cmt
        entity.rows.append(_gr)
        i += 1

    # R-086: full-line comments trailing the final entity (no following row).
    if pending_lead and program.order:
        program.entities[program.order[-1]].trailing.extend(pending_lead)
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
        out = [f"{ent.name} at {row.label} {pred} {' '.join(payload)}".rstrip()]
    else:
        line = f"{ent.name} {pred} {' '.join(payload)}".rstrip()
        out = [line]
        if pred == "body" and ent.kind in ("storage", "htmlTemplate"):
            island_kind = payload[0] if payload else ""
            island = program.islands.get((ent.name, island_kind))
            if island is not None:
                out = [line] + [("    " + b if b else "") for b in island]
    if row.comment:  # R-086: trailing comment preserved in place on its row
        out[0] = f"{out[0]}  {row.comment}"
    return out


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
    # R-086: full-line comments preceding the entity form its header block; a
    # trailing comment on the `is` line is preserved in place.
    is_line = f"{ent.name} is {emit_kind}"
    if ent.comment:
        is_line = f"{is_line}  {ent.comment}"
    lines = list(ent.lead) + [is_line]
    for group in (decl, meta, body, gate):
        for r in group:
            lines.extend(_emit_rows(ent, r, program))
    lines.extend(ent.trailing)
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


def entity_typed_comments(program: Program, name: str) -> list:
    """R-080: typed comments (`# <tag>: text`) attributed to one entity by source
    proximity — comments within the entity's row span, plus a short preamble
    window of comment/blank lines immediately above its `is` row (the idiomatic
    place for a `# security:`/`# failure:` note). Returns [(tag, text, line)] in
    source order so important notes are reviewable per-entity, not just globally.
    """
    if not program.typed_comments:
        return []
    ent = program.entities.get(name)
    if ent is None:
        raise EavError(f"no entity named {name!r}")
    row_lines = [ent.line] + [r.line for r in ent.rows]
    start, end = min(row_lines), max(row_lines)
    # Lines occupied by any *other* entity's `is` row — a typed comment above
    # `start` belongs to this entity only until one of those lines is crossed.
    other_is_lines = sorted(
        o.line for o in program.entities.values() if o.name != name
    )
    prev_is = max((ln for ln in other_is_lines if ln < start), default=0)
    # Attribute a comment to this entity when it sits inside the row span, or in
    # the preamble window between the previous entity's `is` row and this one.
    return [
        (tag, text, ln)
        for (tag, text, ln) in program.typed_comments
        if (start <= ln <= end) or (prev_is < ln < start)
    ]


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
    # R-080: surface retained typed comments so a `# security:`/`# failure:`
    # note attached to this entity is reviewable in the contract summary.
    for tag, text, _ln in entity_typed_comments(program, name):
        lines.append(f"  # {tag}: {text}")
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


def _branch_goto_target_and_guards(row, owned: dict):
    """R-082: for any `branch <guard> … goto LABEL` row, return
    `(label, guard_names)` where `guard_names` is the set of value/call names
    whose recomputation inside a loop body constitutes progress toward this
    exit. Returns `(None, set())` for a non-goto branch (e.g. `branch else`).

    Payload layouts (see `_emit_branch` / `_row_refs`):
      if|ifFalse|ifVariant VALUE goto L         -> guard {VALUE}
      ifValue LEFT cmp RIGHT goto L             -> guard {LEFT, RIGHT}
      ifOut CALL cmp RIGHT goto L               -> guard {CALL, CALL.out, RIGHT}
      ifError|ifReady|ifPending|ifCanceled CALL goto L -> guard {CALL}
    For ifOut/ifError/ifReady the call name itself is a guard: re-running the
    call recomputes its `out`/readiness/error, which the X-115 logic could not
    see because it only tracked bound value names, not the back-edge call."""
    p = row.payload
    if not p or "goto" not in p:
        return None, set()
    guard = p[0]
    label = p[p.index("goto") + 1] if p.index("goto") + 1 < len(p) else None
    if label is None:
        return None, set()
    guards: set = set()
    if guard in ("if", "ifFalse", "ifVariant") and len(p) >= 2:
        guards.add(p[1])
    elif guard == "ifValue" and len(p) >= 4:
        guards.update({p[1], p[3]})
    elif guard == "ifOut" and len(p) >= 4:
        # The inspected value is the call's `out` binding; recomputing it (by
        # re-running the call) or the right operand both make progress.
        guards.add(p[1])  # the call name (re-run = recompute)
        guards.add(p[3])  # right operand
        call = owned.get(p[1])
        if call is not None:
            for o in call.facts("out"):
                if o.payload:
                    guards.add(o.payload[0])
    elif guard in ("ifError", "ifReady", "ifPending", "ifCanceled") and len(p) >= 2:
        guards.add(p[1])  # the fallible/async call; re-running it re-decides
    return label, guards


def _lint_loop_no_progress(program: Program) -> list:
    """X-100 / R-082 / README §13, §33.3: a best-effort divergence lint. A
    back-edge loop that provably makes no progress toward an exit warns: either
    it has no exit path at all (no `return`, no branch/goto leaving the loop), or
    none of its exit guards is ever recomputed/mutated inside the loop body (a
    loop-invariant guard). Halting is undecidable, so this catches only the
    common footguns and never warns when an exit guard is recomputed (a counting
    loop, or a guard whose helper-call inputs are mutated each turn).

    R-082 widened guard recognition beyond bare `if`/`ifFalse` to every branch
    form (`ifValue`, `ifOut`, `ifError`, async readiness), and now counts
    helper-mediated progress: re-running a guard-producing call, rebinding its
    `out`, or mutating any of that call's input args all keep the loop live."""
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
        # R-082: map each owned call to its input arg value names, so a guard
        # recomputed via a helper whose inputs are mutated each turn counts as
        # progress even when the guard's own `out` name is not directly rebound.
        call_inputs = {
            name: {a.payload[2] for a in c.facts("arg") if len(a.payload) >= 3}
            for name, c in owned.items()
        }
        # producer[outName] = the call name that binds it (helper guard producer)
        producer: dict = {}
        for name, c in owned.items():
            for o in c.facts("out"):
                if o.payload:
                    producer[o.payload[0]] = name
        for gi, r in enumerate(rows):
            # identify a back-edge: a bare goto, or any branch-goto form, to a
            # label at an earlier row. R-082: branch back-edges may use any guard
            # form, so resolve the target through the shared helper rather than a
            # fixed payload[3] slot (which only fit if/ifFalse/ifVariant).
            tgt = None
            if r.predicate == "goto" and r.payload:
                tgt = r.payload[0]
            elif r.predicate == "branch":
                tgt = _branch_goto_target_and_guards(r, owned)[0]
            li = labels.get(tgt) if tgt is not None else None
            # R-089: `li == gi` is a self-loop (`at L goto L`) — a back-edge, not
            # a forward edge. Only a strictly-later target (`li > gi`) is forward.
            if li is None or li > gi:
                continue  # forward edge or unknown target -> not a loop back-edge
            has_return = False
            exit_guards: list = []     # set of guard names per exit (empty = unconditional)
            recomputed: set = set()    # values/calls (re)bound/mutated inside the loop body
            for j in range(li, gi + 1):
                rj = rows[j]
                if rj.predicate == "return":
                    has_return = True
                if rj.predicate in ("do", "start", "join", "poll") and rj.payload:
                    # R-082: re-running a call inside the body is itself progress
                    # for ifOut/ifError/ifReady guards keyed on the call name; it
                    # also recomputes the call's `out` bindings.
                    recomputed.add(rj.payload[0])
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
                    t2 = (rj.payload[0], set())
                elif rj.predicate == "branch":
                    label, guards = _branch_goto_target_and_guards(rj, owned)
                    if label is not None:
                        t2 = (label, guards)
                if t2 is not None:
                    ti = labels.get(t2[0])
                    if ti is None or ti < li or ti > gi:
                        exit_guards.append(t2[1])
            if has_return:
                continue
            if not exit_guards:
                diags.append(Diagnostic(
                    "SS0950", "warning",
                    f"loop at {tgt!r} in {op.name!r} has no exit path (no return, no "
                    f"branch/goto leaving the loop) — likely an infinite loop "
                    f"(README §13/§33.3)",
                    rows[li].line, op.name))
                continue

            def _exit_progresses(guard_set: set) -> bool:
                # An unconditional exit (bare goto) always progresses.
                if not guard_set:
                    return True
                for g in guard_set:
                    if g in recomputed:
                        return True
                    # R-082 helper-mediated progress: the guard is produced by a
                    # body call whose inputs are mutated/recomputed each turn, so
                    # its value changes even though its own name is not re-bound.
                    src_call = producer.get(g, g if g in call_inputs else None)
                    if src_call is not None and (call_inputs.get(src_call, set()) & recomputed):
                        return True
                return False

            # exits exist; the loop progresses if ANY exit can change toward being
            # taken. Otherwise every exit guard is loop-invariant -> no progress.
            if not any(_exit_progresses(g) for g in exit_guards):
                guards = sorted({g for gs in exit_guards for g in gs})
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
def _structured_diags(diags: list) -> list:
    """Structured diagnostic objects for every `--json` surface (R-090): a
    machine-readable {code,severity,line,entity,message} carrying the rendered
    text as a separate field, so consumers never have to regex-parse a string."""
    return [{"code": d.code, "severity": d.severity, "line": d.line,
             "entity": d.entity, "message": d.message, "rendered": d.render()}
            for d in diags]


def diagnostics_json(diags: list) -> str:
    """JSON surface for diagnostics (README ss24 `--json`)."""
    return json.dumps(_structured_diags(diags), indent=2)


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
            kind = _op_body_kind(ent)
            if ent.kind in ("operation", "function") and kind in (
                "runtimeBinding", "intrinsic"
            ):
                # A runtimeBinding to the project's own native-runtime namespace
                # (`ss_*`) or the wasm DOM host adapter (`dom_*`) is the sanctioned
                # platform seam, not ad-hoc app-source FFI. Only raw libc (`c.*`,
                # bare libc names) and bare `intrinsic` bodies are the debt this
                # lint targets (those have safe stdlib wrappers).
                if kind == "runtimeBinding" and _is_platform_runtime_symbol(ent):
                    continue
                diags.append(Diagnostic(
                    "SS5000", "warning",
                    f"operation {ent.name!r} has a `{kind}` body in "
                    f"application source; primitive bodies belong in a .semsig-backed "
                    f"stdlib module (README ss17 #50)",
                    ent.line, ent.name))
    diags.extend(_lint_gates(program))
    diags.extend(_lint_c_exports(program))
    diags.extend(_lint_entry_abi(program))
    diags.extend(_lint_runtime_bindings(program))
    diags.extend(_lint_multitarget_entry(program))
    diags.extend(_lint_operationtype_effect_bound(program))
    diags.extend(_lint_dead_unused(program))
    diags.extend(_lint_memory_layout(program))
    diags.extend(_lint_circular_type_alias(program))
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
    # footgun — steer to a tolerance compare (or Decimal for exact values). The
    # footgun is comparing two *computed* floats that "should" be equal; comparing
    # against an exact, named float constant or a float literal (e.g. `x == 0.0`,
    # a sign/zero test) is an explicit, intentional check and is not flagged.
    _float_const_names = set()
    for n in program.order:
        e = program.entities[n]
        for r in e.rows:
            if (r.predicate == "let" and len(r.payload) >= 4
                    and r.payload[1] == "immutable"
                    and r.payload[2] in ("Float64", "Float32")):
                _float_const_names.add(r.payload[0])

    def _is_exact_float_operand(v: str) -> bool:
        if v in _float_const_names:
            return True
        t = v.lstrip("-")
        return "." in t and t.replace(".", "", 1).isdigit()

    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if target in ("math.equalFloat64", "math.notEqualFloat64",
                      "math.equalFloat32", "math.notEqualFloat32"):
            operands = [a.payload[2] for a in ent.facts("arg")
                        if len(a.payload) >= 3]
            if any(_is_exact_float_operand(v) for v in operands):
                continue
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
                out.append(Diagnostic("SS3045", "error",  # R-160: was SS3043 (shadowed by gated-configure)
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
    _validate_branch_condition(program)
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
    _validate_random_source(program)
    _validate_nonce_affinity(program)
    _validate_path_traversal(program)
    _validate_ssrf(program)
    _validate_dos_bounds(program)
    _validate_untrusted_loop_bounds(program)
    _validate_error_disclosure(program)
    _validate_utf8_boundary(program)
    _validate_protection_optout(program)
    _validate_shared_state(program)
    _validate_security_parity(program)
    _validate_contracts(program)
    _validate_typestate(program)
    _validate_lock_ordering(program)
    _validate_regions(program)
    _validate_buffer_access(program)
    _validate_ffi_wrapping(program)
    _validate_numeric_ub(program)
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
    _validate_purity(program)
    _validate_effect_completeness(program)


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


# --------------------------------------------------------------------------
# Effect-system primitives (README ss8/ss15/ss17 #5, effect-union WS2-040).
# Extracted to module scope (was nested in _validate_effect_coverage) so the
# coverage check (WS2-040), the completeness check (WS2-091), and the purity
# proof (WS2-093) all compute the *same* effective-effect set from one source of
# truth instead of three drifting copies.
# --------------------------------------------------------------------------

def _effect_rows_of(ent: Entity) -> set:
    """The (action, resource) pairs an entity *itself* declares via `effect`."""
    return {
        (e.payload[0], e.payload[1])
        for e in ent.facts("effect")
        if len(e.payload) >= 2
    }


def _capability_grants(program: Program) -> dict:
    """name -> set of (action, resource) pairs each `capability` grants."""
    grants: dict[str, set] = {}
    for name in program.order:
        ent = program.entities[name]
        if ent.kind == "capability":
            grants[ent.name] = {
                (g.payload[0], g.payload[1])
                for g in ent.facts("grants")
                if len(g.payload) >= 2
            }
    return grants


def _op_capability_grants(op: Entity, cap_grants: dict) -> set:
    """The (action, resource) pairs an op holds via its own `uses` capabilities."""
    cov: set = set()
    for u in op.facts("uses"):
        if u.payload:
            cov |= cap_grants.get(u.payload[0], set())
    return cov


def _effect_action_covers(grant_action: str, effect_action: str) -> bool:
    # README ss8: a `readWrite` grant subsumes the `read` and `write` actions
    # on the same resource (an op authorized to read+write may do either).
    # Mirrors semsc: `grant_access == "readWrite" and action in {read, write}`.
    return grant_action == effect_action or (
        grant_action == "readWrite" and effect_action in ("read", "write")
    )


def _effect_path_covers(covered: set, action: str, resource: str) -> bool:
    # README ss8: capability effect paths are hierarchical — a grant of
    # `<action> <prefix>` authorizes every narrower `<action> <prefix>.<sub>`
    # effect (e.g. `read http.request` covers `read http.request.body`).
    # Mirrors semsc's _effect_path_covers; an exact match is the base case.
    for gact, gres in covered:
        if _effect_action_covers(gact, action) and (
            resource == gres or resource.startswith(gres + ".")
        ):
            return True
    return False


def _invoked_user_op(program: Program, call: Entity):
    """The user operation/function a call/task `invokes`, or None for an external
    (dotted) target or an unresolved bare name."""
    inv = call.fact("invokes")
    if inv and inv.payload and "." not in inv.payload[0]:
        target = program.entities.get(inv.payload[0])
        if target is not None and target.kind in ("operation", "function"):
            return target
    return None


def _effective_effects(program: Program, op: Entity, seen: set) -> set:
    """Transitive effective effects across the call graph (README ss29 #10).
    Authority is caller-granted and does NOT encapsulate: an effect a callee
    triggers is part of every caller's effective set, so each op on the path
    must declare/cover it (README ss8; pinned by the entropy/clock/process
    capability tests and the WS2-091 completeness / WS2-093 purity gates)."""
    if op.name in seen:
        return set()
    seen.add(op.name)
    eff = set(_effect_rows_of(op))
    # WS2-092: local operationType value bindings (`let fn … <OpType> <op>`)
    # contribute the operationType's declared effect bound when invoked
    # indirectly, so behavior-passed-as-data cannot escape the effect union.
    ot_bindings = {
        r.payload[0]: program.entities[r.payload[2]]
        for r in op.rows
        if r.predicate == "let" and len(r.payload) >= 3
        and r.payload[2] in program.entities
        and program.entities[r.payload[2]].kind == "operationType"
    }
    for row in op.rows:
        if row.predicate not in _STEP_SPLIT or not row.payload:
            continue
        ref = program.entities.get(row.payload[0])
        if ref is None:
            continue
        eff |= _effect_rows_of(ref)
        workers = [ref]
        if ref.kind == "cleanup":
            cr = ref.fact("call")
            w = program.entities.get(cr.payload[0]) if cr and cr.payload else None
            if w is not None:
                workers.append(w)
                eff |= _effect_rows_of(w)
        for w in workers:
            if w.kind in ("call", "task"):
                inv = w.fact("invokes")
                itgt = inv.payload[0] if inv and inv.payload else None
                if itgt in ot_bindings:  # WS2-092: indirect call via operationType
                    eff |= _effect_rows_of(ot_bindings[itgt])
                callee = _invoked_user_op(program, w)
                if callee is not None:
                    eff |= _effective_effects(program, callee, seen)
    return eff


def _activates_opaque_target(program: Program, op: Entity) -> bool:
    """True if the op activates any call/task/cleanup-worker whose `invokes` target
    is external (dotted, e.g. `console.writeLine`) or unresolved. Such a target's
    effects are NOT modeled by `_effective_effects` (only `effect` rows on the
    activated entity and user-op callees are), so we cannot prove what it does or
    does not perform — over-declaration cannot be soundly decided for such an op."""
    for row in op.rows:
        if row.predicate not in _STEP_SPLIT or not row.payload:
            continue
        ref = program.entities.get(row.payload[0])
        if ref is None:
            continue
        workers = [ref]
        if ref.kind == "cleanup":
            cr = ref.fact("call")
            w = program.entities.get(cr.payload[0]) if cr and cr.payload else None
            if w is not None:
                workers.append(w)
        for w in workers:
            if w.kind in ("call", "task"):
                inv = w.fact("invokes")
                target = inv.payload[0] if inv and inv.payload else None
                if target is None:
                    return True  # unresolved activation: assume it may have effects
                if "." in target:
                    # external/dotted target with no `effect` row on the call is an
                    # effect we cannot see — don't risk a false over-declaration.
                    if not _effect_rows_of(w):
                        return True
    return False


def _activated_effects(program: Program, op: Entity) -> set:
    """The effects an op causes *through what it activates* — the own effects of
    every directly-activated call/task/cleanup (and a cleanup's worker) plus their
    transitive effective sets — but NOT the op's own top-level `effect` rows.

    WS2-091 over-declaration needs this distinction: `_effective_effects` unions
    the op's own declarations into the result, so `declared ⊆ effective` always
    holds and `declared - effective` can never expose an over-declared row. An
    effect is over-declared exactly when the op declares it yet *nothing it
    activates* produces it — which is precisely `declared - activated`."""
    activated: set = set()
    for row in op.rows:
        if row.predicate not in _STEP_SPLIT or not row.payload:
            continue
        ref = program.entities.get(row.payload[0])
        if ref is None:
            continue
        activated |= _effect_rows_of(ref)
        workers = [ref]
        if ref.kind == "cleanup":
            cr = ref.fact("call")
            w = program.entities.get(cr.payload[0]) if cr and cr.payload else None
            if w is not None:
                workers.append(w)
                activated |= _effect_rows_of(w)
        for w in workers:
            if w.kind in ("call", "task"):
                callee = _invoked_user_op(program, w)
                if callee is not None:
                    # the callee's full effective set (its own + its activations)
                    activated |= _effective_effects(program, callee, set())
    return activated


def _validate_effect_coverage(program: Program) -> None:
    """An operation's *effective* effects are its own plus those of the calls/
    tasks/cleanups it activates; every effective effect should be covered by a
    `uses` capability (README ss8, ss15, ss17 #5; effect-union WS2-040). An
    uncovered effect — including one introduced by an activated call — warns."""
    cap_grants = _capability_grants(program)
    for name in program.order:
        op = program.entities[name]
        if op.kind not in ("operation", "function"):
            continue
        own = _op_capability_grants(op, cap_grants)
        for action, resource in sorted(_effective_effects(program, op, set())):
            if not _effect_path_covers(own, action, resource):
                program.warnings.append(
                    f"{op.name}: effective effect `{action} {resource}` is not "
                    f"covered by a `uses` capability (README ss8, ss17 #5)"
                )


def _validate_purity(program: Program) -> None:
    """WS2-093 (purity proof, README ss10.6/ss30.3.2): an operation with NO own
    `effect` rows is asserting it is pure (side-effect-free). For that assertion
    to be *sound* its transitive effective-effect set must be empty — a "pure"
    op that activates (directly or transitively) any effectful call/task/cleanup
    is lying, and callers that rely on the purity guarantee (`memory heap no`,
    const-folding/replay safety) would be unsound. This is deny-tier (T0): purity
    is a contract, not a hint, so the gate refuses to lower the unproven op.

    Why effective (not own) effects: an op can carry zero `effect` rows yet still
    cause effects through the calls it activates — that hidden flow is exactly
    what makes a naive purity claim unsound, so we prove emptiness over the full
    transitive union built by `_effective_effects` (the same machinery WS2-040
    coverage uses), not just the op's own declarations."""
    for name in program.order:
        op = program.entities[name]
        if op.kind not in ("operation", "function"):
            continue
        # An op declaring its own effects is not claiming purity — WS2-091
        # completeness governs that case, not this purity proof.
        if _effect_rows_of(op):
            continue
        effective = _effective_effects(program, op, set())
        if effective:
            action, resource = sorted(effective)[0]
            raise EavError(
                f"operation {op.name!r} declares no `effect` rows (claiming purity) "
                f"but transitively causes the effect `{action} {resource}`; a pure "
                f"op must be provably side-effect-free — declare the effects it "
                f"actually performs or stop activating the effectful target "
                f"(README ss10.6/ss30.3.2, WS2-093)",
                op.line, code="SS1705",
            )


def _validate_effect_completeness(program: Program) -> None:
    """WS2-091 (completeness — no undeclared effect, README ss15/ss17 #5): an
    operation's contract must list every effect it can cause. The op's *effective*
    set (own ∪ transitively-activated call/task/cleanup effects) must be contained
    in what the op itself authorizes: an effect is acceptable iff it is either
    (a) declared on the op via an `effect` row, or (b) covered by a `uses`
    capability the op holds. An effect that is *neither declared nor covered* is a
    genuinely hidden effect leaking up from a callee — the op can cause it but its
    contract is silent and unauthorized about it. That is deny-tier (T0): the
    no-undefined-execution guarantee requires the contract to be complete.

    Why "declared OR covered" (not "declared" alone): the ported web apps follow a
    legitimate delegation pattern where a handler holds the *covering capability*
    for a transitive effect (authorizing itself) without restating every callee
    effect as its own `effect` row. Holding the capability is an explicit, in-source
    authorization — the effect is not hidden — so it satisfies completeness. Only an
    effect with neither a declaration nor an authorization is the genuine undeclared
    leak this gate refuses (matches the todo's "flag only when genuinely
    undeclared/uncovered" refinement and keeps the app-port surfaces clean).

    Over-declaration (an `effect` row whose action/resource never appears in the
    effective set) is *safe* — the op claims more authority than it exercises — so
    it is at most a T3 advisory warning (SS0900), never a blocker.

    A no-`effect` op claiming purity is governed by WS2-093 (`_validate_purity`),
    which runs first; by the time this gate runs such an op is either already
    rejected (impure) or has an empty effective set (vacuously complete)."""
    cap_grants = _capability_grants(program)
    for name in program.order:
        op = program.entities[name]
        if op.kind not in ("operation", "function"):
            continue
        declared = _effect_rows_of(op)
        covered = _op_capability_grants(op, cap_grants)
        effective = _effective_effects(program, op, set())
        # Completeness: every effect the op can cause is declared or authorized.
        for action, resource in sorted(effective):
            if (action, resource) in declared:
                continue
            if _effect_path_covers(covered, action, resource):
                continue
            raise EavError(
                f"operation {op.name!r} can cause the effect `{action} {resource}` "
                f"(it flows up from an activated call/task/cleanup) but neither "
                f"declares it with an `effect` row nor holds a covering `uses` "
                f"capability; an operation's effect contract must be complete — "
                f"declare or authorize every effect it can cause "
                f"(README ss15/ss17 #5, WS2-091)",
                op.line, code="SS1706",
            )
        # Over-declaration is safe (declared more authority than exercised) — a
        # T3 advisory, not a blocker. An effect is over-declared when the op
        # declares it yet nothing it activates produces it. We measure against the
        # *activated* effects (not `_effective_effects`, which folds the op's own
        # declarations back in and would mask every over-declaration).
        #
        # Soundness guard: an op that activates any external/dotted or unresolved
        # target (e.g. `console.writeLine`, a stdlib `runtimeBinding`) performs
        # effects we cannot see — its declared `effect` rows are often the ONLY
        # in-source signal that such a call is effectful. Claiming those rows are
        # over-declared would be a false positive (it fires on the ported apps'
        # console/HTTP handlers), so we only advise over-declaration when the op's
        # entire activation surface resolves to known entities whose effects we
        # fully account for. README ss17 #5 / WS2-091.
        if _activates_opaque_target(program, op):
            continue
        # A runtimeBinding/intrinsic op performs its declared effects through the
        # native seam, not through a visible step the linter can see, so its
        # `effect` rows are the contract for that primitive — never over-declared.
        if _op_body_kind(op) in ("runtimeBinding", "intrinsic"):
            continue
        activated = _activated_effects(program, op)
        for action, resource in sorted(declared - activated):
            program.warnings.append(
                f"{op.name}: declares the effect `{action} {resource}` but never "
                f"performs it (over-declared; safe but unnecessary, README ss17 #5, "
                f"WS2-091)"
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
    """Whether a call target yields a value semanticscript can statically judge: True for
    math.* (arith/compare), False for console.* (void), the callee's `out`
    presence for a bare user op, and None (unknown) for other external targets."""
    if (target.startswith("math.") or target.startswith("compare.")
            or target.startswith("convert.to") or target == "string.concat"
            or target.startswith("assert.") or target == "test.and"):
        return True
    if target == "test.summary":  # returns the failure count as an ExitCode
        return True
    if target.startswith("console.") or target.startswith("test.assert"):
        return False  # the test.assert* harness calls are void (report + tally)
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
        if not entry or not entry.payload:
            continue
        ent = program.entities.get(entry.payload[0])
        # R-104: the entry must name a *declared* entity (regardless of target).
        # A dangling name would be handed to get_function_address and called as a
        # null address at runtime; reject it here instead of advertising green.
        if ent is None:
            out.append(Diagnostic(
                "SS1194", "error",
                f"project entry {entry.payload[0]!r} names no declared operation "
                f"(README §7/§11)", proj.line, proj.name))
            continue
        if "console" not in targets:
            continue
        if ent.kind not in ("operation", "function"):
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


def _lint_runtime_bindings(program: Program) -> list:
    """R-105: a `body runtimeBinding ss_*` symbol that no native runtime library
    provides resolves to null and crashes at first call — report it (SS1195) so
    `check` rejects it instead of advertising green and crashing at run."""
    unresolved = _unresolved_runtime_symbols(program)
    if not unresolved:
        return []
    out: list[Diagnostic] = []
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("operation", "function"):
            continue
        body = ent.fact("body")
        if (body and body.payload and body.payload[0] == "runtimeBinding"
                and len(body.payload) >= 2 and body.payload[1] in unresolved):
            out.append(Diagnostic(
                "SS1195", "error",
                f"operation {ent.name!r} binds runtime symbol {body.payload[1]!r}, "
                f"which no native runtime library provides (runtime/manifest.json); "
                f"check the symbol name (README §26)", ent.line, ent.name))
    return out


def _lint_dead_unused(program: Program) -> list:
    """WS2-080 dead/unused parity (README §17). Advisory (T3) checks ported from
    the semsc linter:
      * SS0802 — a `capability` declared but never named by any `uses`.
      * SS0810 — a step that is unreachable because it follows an unconditional
        control-flow exit (`return`/`goto`/`jump`) with no intervening label.
    (unused-call already warns via _validate_activation_count; dead labels via
    the label validator.)"""
    out: list[Diagnostic] = []
    used_caps: set = set()
    for n in program.order:
        for r in program.entities[n].facts("uses"):
            if r.payload:
                used_caps.add(r.payload[0])
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "capability" and ent.name not in used_caps:
            out.append(Diagnostic(
                "SS0802", "warning",
                f"capability {ent.name!r} is declared but never used by any "
                f"operation's `uses` (README §17/WS2-080)",
                ent.line, ent.name))
    # SS0806: a module `storage` whose name never appears in another entity's row
    # (never read or written by any operation).
    referenced: set = set()
    for n in program.order:
        sub = program.entities[n].name
        for r in program.entities[n].rows:
            for tok in r.payload:
                referenced.add((sub, tok))
    for n in program.order:
        ent = program.entities[n]
        if ent.kind != "storage":
            continue
        if not any(tok == ent.name and sub != ent.name for (sub, tok) in referenced):
            out.append(Diagnostic(
                "SS0806", "warning",
                f"module storage {ent.name!r} is declared but never read or "
                f"written by any operation (README §17/WS2-080)",
                ent.line, ent.name))
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        terminated = False
        for r in op.rows:
            if r.label is not None:
                terminated = False  # a labeled row is a jump target -> reachable
            elif terminated and r.predicate in STEP_PREDICATES:
                out.append(Diagnostic(
                    "SS0810", "warning",
                    f"step {r.predicate!r} in {op.name!r} is unreachable: it "
                    f"follows an unconditional control-flow exit with no "
                    f"intervening label (README §13/WS2-080)",
                    r.line, op.name))
            if r.predicate in ("return", "goto", "jump"):
                terminated = True
    # --- reference-based unused checks (per operation scope) ---
    from collections import Counter
    owned_by: dict = {}
    for n in program.order:
        e = program.entities[n]
        if e.kind in ("call", "task", "cleanup"):
            inr = e.fact("in")
            if inr and inr.payload:
                owned_by.setdefault(inr.payload[0], []).append(e)
    # errorCase references: a `Type.Case` or bare `Case` token anywhere.
    ec_ref: set = set()
    for n in program.order:
        for r in program.entities[n].rows:
            for tok in r.payload:
                ec_ref.add(tok)
                if "." in tok:
                    ec_ref.add(tok.split(".")[-1])
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "errorCase" and ent.name not in ec_ref:
            out.append(Diagnostic(
                "SS0803", "warning",
                f"error case {ent.name!r} is declared but never constructed or "
                f"matched (README §17/WS2-080)", ent.line, ent.name))
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        # runtimeBinding/intrinsic ops have no EAV body — their inputs/consts are
        # consumed by the native impl, so don't flag them as unused.
        body_row = op.fact("body") or op.fact("operationBody")
        if (body_row is not None and body_row.payload
                and body_row.payload[0] in ("runtimeBinding", "intrinsic", "abstract")):
            continue
        cnt: Counter = Counter()
        for m in [op] + owned_by.get(op.name, []):
            for r in m.rows:
                for tok in r.payload:
                    cnt[tok] += 1
        for r in op.facts("in"):  # SS0805 unused input
            # ABI/injected-context inputs (a webServer handler's request/response,
            # a middleware's `next` continuation, a GUI handler's session/event)
            # are mandated by the operation's role ABI, so they are not "unused"
            # dead parameters even when a given handler does not read them.
            in_type = r.payload[1] if len(r.payload) >= 2 else ""
            if (r.payload and cnt[r.payload[0]] == 1
                    and in_type not in _ABI_CONTEXT_INPUT_TYPES):
                out.append(Diagnostic(
                    "SS0805", "warning",
                    f"input {r.payload[0]!r} of {op.name!r} is never used in the "
                    f"body (README §17/WS2-080)", r.line, op.name))
        for r in op.rows:  # SS0804 unused immutable local const
            if (r.predicate == "let" and len(r.payload) >= 2
                    and r.payload[1] == "immutable" and cnt[r.payload[0]] == 1):
                out.append(Diagnostic(
                    "SS0804", "warning",
                    f"local const {r.payload[0]!r} in {op.name!r} is declared but "
                    f"never used (README §17/WS2-080)", r.line, op.name))
        for m in owned_by.get(op.name, []):  # SS0807 unused call out-binding
            for r in m.facts("out"):
                if r.payload and cnt[r.payload[0]] == 1:
                    out.append(Diagnostic(
                        "SS0807", "warning",
                        f"call binding {r.payload[0]!r} in {op.name!r} is bound but "
                        f"never used — discard it or drop the `out` (README §17/WS2-080)",
                        r.line, op.name))
        # SS0808 dead store: two consecutive `set X` with no read of X between
        # (conservative: straight-line within the op + its owned-call arg reads).
        member_rows = [r for m in [op] + owned_by.get(op.name, []) for r in m.rows]
        pending: dict = {}  # name -> the row of an as-yet-unread `set`
        for r in op.rows:
            if r.label is not None or r.predicate in ("branch", "goto", "jump", "return"):
                pending.clear()  # control flow: stop tracking (stay conservative)
                continue
            reads = set(r.payload[1:]) if r.predicate == "set" else set(r.payload)
            for tok in reads:
                pending.pop(tok, None)
            if r.predicate == "set" and r.payload:
                tgt = r.payload[0]
                if tgt in pending:
                    out.append(Diagnostic(
                        "SS0808", "warning",
                        f"dead store: {tgt!r} in {op.name!r} is set again before the "
                        f"earlier value is read (README §17/WS2-080)",
                        pending[tgt].line, op.name))
                pending[tgt] = r
    # SS0809 dead storage initializer: a mutable storage written but never read.
    for n in program.order:
        st = program.entities[n]
        if st.kind != "storage":
            continue
        if (st.fact("mutability") and st.fact("mutability").payload
                and st.fact("mutability").payload[0] != "mutable"):
            continue
        written = read = False
        for m in program.order:
            owner = program.entities[m]
            if owner.name == st.name:
                continue
            for r in owner.rows:
                if r.predicate == "set" and r.payload and r.payload[0] == st.name:
                    written = True
                    if st.name in r.payload[1:]:
                        read = True
                elif st.name in r.payload:
                    read = True
        if written and not read:
            out.append(Diagnostic(
                "SS0809", "warning",
                f"module storage {st.name!r} is written but its value is never read "
                f"— the initializer and stores are dead (README §17/WS2-080)",
                st.line, st.name))
    # SS0811 duplicate single-valued declaration row on one entity.
    single_valued = {"purpose", "path", "for", "scope", "mutability", "type",
                     "value", "memory", "async", "out"}
    for n in program.order:
        ent = program.entities[n]
        seen_pred: set = set()
        for r in ent.rows:
            if r.label is not None or r.predicate not in single_valued:
                continue
            if r.predicate in seen_pred:
                out.append(Diagnostic(
                    "SS0811", "warning",
                    f"{ent.kind} {ent.name!r} has a duplicate {r.predicate!r} row "
                    f"(single-valued declaration, README §17/WS2-080)",
                    r.line, ent.name))
            seen_pred.add(r.predicate)
    # SS0812 the same immutable const declared identically in two+ operations
    # (a hoist-to-module-storage candidate).
    const_sites: dict = {}
    _SS0812_TRIVIAL_LITERALS = {"0", "1", "-1", "true", "false", "yes", "no"}
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        for r in op.rows:
            if (r.predicate == "let" and len(r.payload) >= 4
                    and r.payload[1] == "immutable"):
                key = (r.payload[0], r.payload[2], r.payload[3])
                const_sites.setdefault(key, []).append((op.name, r))
    for key, sites in const_sites.items():
        if len({s[0] for s in sites}) >= 2:
            _name, _ty, _val = key
            # Trivial literals (0, 1, -1, booleans) are idiomatic to declare as a
            # named local in each operation that needs them; hoisting them to a
            # module global is not cleaner, so they are exempt from the
            # hoist-candidate advisory (only substantive shared constants —
            # strings, magic numbers, paths — are worth flagging).
            if _val in _SS0812_TRIVIAL_LITERALS:
                continue
            ops = sorted({s[0] for s in sites})
            out.append(Diagnostic(
                "SS0812", "warning",
                f"immutable const {_name!r} ({_ty} {_val}) is declared identically "
                f"in operations {ops} — consider hoisting to module storage "
                f"(README §17/WS2-080)", sites[0][1].line, sites[0][0]))
    return out


_HEAP_ALLOC_TARGETS = (
    "c.malloc", "c.calloc", "c.realloc", "memory.allocateMemoryBytes",
    "buffer.create",
)

# Estimated byte size of a primitive type, for stack-budget and inline-capacity
# checks (README §6 lowering table). Aggregates/Strings are pointer-width.
_PRIM_BYTES = {
    "Bool": 1, "Byte": 1, "Int8": 1, "UInt8": 1,
    "Int16": 2, "UInt16": 2, "Int32": 4, "UInt32": 4, "ExitCode": 4,
    "Float32": 4, "Int64": 8, "UInt64": 8, "Float64": 8,
    "String": 8, "OpaquePointer": 8, "FileHandle": 8,
}
_LARGE_LITERAL_BYTES = 256  # WS2-084: inline String literals above this should embed


def _layout_int(tok: str):
    """Parse an EAV integer payload token (underscores allowed), else None."""
    try:
        return int(str(tok).replace("_", ""))
    except (TypeError, ValueError):
        return None


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _lint_memory_layout(program: Program) -> list:
    """WS2-084 memory/layout parity (README §1J/§10.6/§30.3.2). All nine parity
    checks, on the EAV layout grammar (`align`/`layout` on records, `memory`/
    `inlineCapacity`/`arrayLength`/`allocator` on aliases, `literalEncoding` on
    storage, `memory stack N` on operations):
      SS0820 literal-without-digest        SS0825 literal-encoding-missing
      SS0821 memory-heap-contradiction     SS0826 large-local-static-literal
      SS0822 record-align-power-of-two     SS0827 magic-ascii-byte-literal
      SS0823 array-length-zero             SS0828 inline-capacity-without-spill
      SS0824 inline-capacity-overrun       SS0829 stack-limit-overrun"""
    out: list[Diagnostic] = []
    for n in program.order:
        st = program.entities[n]
        if st.kind == "storage" and st.fact("literalSource") is not None:
            if st.fact("literalDigest") is None:
                out.append(Diagnostic(
                    "SS0820", "warning",
                    f"embedded literal {st.name!r} has a `literalSource` but no "
                    f"`literalDigest` — the embed is not tamper-evident (README "
                    f"§30.3.2/WS1-084)", st.line, st.name))
            if st.fact("literalEncoding") is None:
                out.append(Diagnostic(
                    "SS0825", "warning",
                    f"embedded literal {st.name!r} has a `literalSource` but no "
                    f"`literalEncoding` — its byte interpretation is unpinned "
                    f"(README §30.3.2/WS2-084)", st.line, st.name))

    # SS0822 record-align-power-of-two.
    for rec in program.of_kind("record"):
        ar = rec.fact("align")
        if ar and ar.payload:
            n = _layout_int(ar.payload[0])
            if n is not None and not _is_power_of_two(n):
                out.append(Diagnostic(
                    "SS0822", "warning",
                    f"record {rec.name!r} declares `align {ar.payload[0]}` — "
                    f"alignment must be a positive power of two (README "
                    f"§10.6/WS2-084)", rec.line, rec.name))

    # Alias type-memory parity: SS0823, SS0824, SS0828.
    for al in program.of_kind("alias"):
        lr = al.fact("arrayLength")
        if lr and lr.payload:
            n = _layout_int(lr.payload[0])
            if n == 0:
                out.append(Diagnostic(
                    "SS0823", "warning",
                    f"array alias {al.name!r} declares `arrayLength 0` — a "
                    f"zero-length array holds no elements (README §10.6/WS2-084)",
                    al.line, al.name))
        mr = al.fact("memory")
        is_inline = bool(mr and "inline" in mr.payload)
        cap_row = al.fact("inlineCapacity")
        if is_inline and cap_row and cap_row.payload:
            cap = _layout_int(cap_row.payload[0])
            forr = al.fact("for")
            elem = forr.payload[0] if forr and forr.payload else None
            size = _PRIM_BYTES.get(elem)
            if cap is not None and size is not None and size > cap:
                out.append(Diagnostic(
                    "SS0824", "warning",
                    f"alias {al.name!r} is `memory inline` with `inlineCapacity "
                    f"{cap}` but its {elem} value needs {size} bytes — it cannot "
                    f"fit inline (README §10.6/WS2-084)", al.line, al.name))
            if al.fact("allocator") is None:
                out.append(Diagnostic(
                    "SS0828", "warning",
                    f"alias {al.name!r} is `memory inline` with an "
                    f"`inlineCapacity` but declares no `allocator` for the spill "
                    f"path — over-capacity values have nowhere to go (README "
                    f"§10.6/WS2-084)", al.line, al.name))

    owned_by: dict = {}
    for n in program.order:
        e = program.entities[n]
        if e.kind in ("call", "task", "cleanup"):
            inr = e.fact("in")
            if inr and inr.payload:
                owned_by.setdefault(inr.payload[0], []).append(e)

    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        mrow = op.fact("memory")
        mpay = mrow.payload if mrow else []
        # SS0821 memory-heap-contradiction.
        if mrow and "heap" in mpay and "no" in mpay[mpay.index("heap"):]:
            for w in owned_by.get(op.name, []):
                inv = w.fact("invokes")
                tgt = inv.payload[0] if inv and inv.payload else None
                if tgt in _HEAP_ALLOC_TARGETS:
                    out.append(Diagnostic(
                        "SS0821", "warning",
                        f"operation {op.name!r} declares `memory heap no` but "
                        f"activates a heap allocation ({tgt}) — contradiction "
                        f"(README §1J/WS2-084)", op.line, op.name))
                    break
        # Per-op local literal checks: SS0826, SS0827.
        for lr in op.facts("let"):
            p = lr.payload
            if len(p) < 4:
                continue
            typ, val = p[2], p[3]
            if typ == "String" and val.startswith('"') and val.endswith('"'):
                if len(val) - 2 > _LARGE_LITERAL_BYTES:
                    out.append(Diagnostic(
                        "SS0826", "warning",
                        f"local {p[0]!r} inlines a {len(val) - 2}-byte String "
                        f"literal (> {_LARGE_LITERAL_BYTES}) — move it to an "
                        f"audited `literalSource` embed (README §30.3.2/WS2-084)",
                        lr.line, op.name))
            if typ in ("Byte", "Int8", "UInt8"):
                bval = _layout_int(val)
                if bval is not None and 32 <= bval <= 126:
                    out.append(Diagnostic(
                        "SS0827", "warning",
                        f"local {p[0]!r} is `{typ} {val}`, the printable-ASCII "
                        f"code for {chr(bval)!r} — name the constant so the intent "
                        f"is legible (README §10.6/WS2-084)", lr.line, op.name))
        # SS0829 stack-limit-overrun.
        if mrow and "stack" in mpay:
            si = mpay.index("stack")
            budget = _layout_int(mpay[si + 1]) if si + 1 < len(mpay) else None
            if budget is not None:
                used = 0
                for lr in op.facts("let"):
                    if len(lr.payload) >= 3:
                        used += _PRIM_BYTES.get(lr.payload[2], 8)
                if used > budget:
                    out.append(Diagnostic(
                        "SS0829", "warning",
                        f"operation {op.name!r} declares `memory stack {budget}` "
                        f"but its locals need about {used} bytes — the frame "
                        f"overruns its budget (README §1J/WS2-084)",
                        op.line, op.name))
    return out


def _lint_circular_type_alias(program: Program) -> list:
    """WS2-089 (§10/§17): an `alias … for …` chain that cycles back on itself
    never resolves to a concrete type — `_resolve_alias` bails out on the
    revisit and silently yields an unresolved alias name, so flag the cycle
    explicitly. Aliases that terminate at a primitive/record/enum are fine."""
    out: list[Diagnostic] = []
    targets = {
        a.name: a.fact("for").payload[0]
        for a in program.of_kind("alias")
        if a.fact("for") and a.fact("for").payload
    }
    reported: set = set()
    for start in targets:
        path: list[str] = []
        cur = start
        while cur in targets:
            if cur in path:
                cycle = path[path.index(cur):]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    ent = program.entities[cur]
                    chain = " → ".join(cycle + [cur])
                    out.append(Diagnostic(
                        "SS1011", "error",
                        f"type alias {cur!r} is circular: {chain} — it never "
                        f"resolves to a concrete type (README §10/§17/WS2-089)",
                        ent.line, cur))
                break
            path.append(cur)
            cur = targets[cur]
    return out


def _lint_operationtype_effect_bound(program: Program) -> list:
    """WS2-092 (§33.9): an operation bound as a value of an `operationType` may
    not perform effects beyond that operationType's declared effect bound —
    behavior passed as data cannot smuggle an undeclared effect. (The indirect
    call's effects are unioned into the caller by `_effective_effects`.)"""
    out: list[Diagnostic] = []
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        for r in op.rows:
            if r.predicate != "let" or len(r.payload) < 4:
                continue
            ot = program.entities.get(r.payload[2])
            bound = program.entities.get(r.payload[3])
            if (ot is None or ot.kind != "operationType" or bound is None
                    or bound.kind not in ("operation", "function")):
                continue
            escape = _effective_effects(program, bound, set()) - _effect_rows_of(ot)
            if escape:
                pretty = sorted(f"{a} {res}" for a, res in escape)
                out.append(Diagnostic(
                    "SS1707", "error",
                    f"operation {bound.name!r} bound as operationType {ot.name!r} in "
                    f"{op.name!r} performs effect(s) {pretty} outside the "
                    f"operationType's effect bound — behavior passed as data may not "
                    f"exceed its declared effects (README §33.9/WS2-092)",
                    r.line, op.name))
    return out


def _lint_multitarget_entry(program: Program) -> list:
    """Multi-target entry gating (README §7, WS3-160): a project may repeat
    `entry`, each gated by a `forTarget` on the named entry entity. Exactly one
    entry must be enabled per built target — an entry is enabled for target T if
    its entity carries `forTarget T`, or (when no entry is target-specific for T)
    if it carries no `forTarget` at all (the unqualified default). Zero or two
    enabled entries for a target is a hard error (SS1192 / SS1193). A project with
    no `entry` is library mode and is not gated."""
    out: list[Diagnostic] = []
    for proj in program.of_kind("project"):
        targets = [t.payload[0] for t in proj.facts("target") if t.payload]
        entries = [e.payload[0] for e in proj.facts("entry") if e.payload]
        if not targets or not entries:
            continue
        gated = {}
        for name in entries:
            ent = program.entities.get(name)
            gated[name] = ({r.payload[0] for r in ent.facts("forTarget") if r.payload}
                           if ent else set())
        unqualified = [n for n in entries if not gated[n]]
        for tgt in targets:
            specific = [n for n in entries if tgt in gated[n]]
            enabled = specific if specific else unqualified
            if len(enabled) == 0:
                out.append(Diagnostic(
                    "SS1192", "error",
                    f"project {proj.name!r} has no entry enabled for target {tgt!r}: "
                    f"every entry is gated to another target and there is no "
                    f"unqualified default (README §7/WS3-160)",
                    proj.line, proj.name))
            elif len(enabled) > 1:
                out.append(Diagnostic(
                    "SS1193", "error",
                    f"project {proj.name!r} enables {len(enabled)} entries "
                    f"{sorted(enabled)} for target {tgt!r}; exactly one must be "
                    f"enabled — gate them with distinct `forTarget` (README §7/WS3-160)",
                    proj.line, proj.name))
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
        # R-039: the callee's `typeParam` names match any concrete arg/out type —
        # the instantiation is checked structurally per call, not against `T`.
        tparams = {r.payload[0] for r in callee.facts("typeParam") if r.payload}
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
            if in_type is None or arg_type == in_type or in_type in tparams:
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
        # WS2-089 bind-return-type-domain: the call's `out` binding type must be
        # the callee's declared return type exactly. A Result-returning callee
        # binds its OK type via `out` (errors flow through `catch`). A same-base
        # alias mismatch is a silent newtype coercion, just like the arg case.
        callee_out = callee.fact("out")
        out_row = ent.fact("out")
        if (callee_out and callee_out.payload and out_row
                and len(out_row.payload) >= 2):
            co = callee_out.payload
            expected = co[1] if co[0] == "Result" and len(co) >= 2 else co[0]
            bind_type = out_row.payload[1]
            if (expected not in (None, "Void") and expected not in tparams
                    and bind_type != expected):
                same_base = (_resolve_alias(bind_type, alias_map)
                             == _resolve_alias(expected, alias_map))
                if not same_base:
                    raise EavError(
                        f"call {ent.name!r} binds the result of {target!r} as "
                        f"{bind_type!r} but {target!r} returns {expected!r} "
                        f"(README ss10/ss15, WS2-089)",
                        out_row.line, code="SS1030",
                    )
                if bind_type in newtypes or expected in newtypes:
                    raise EavError(
                        f"call {ent.name!r} binds the result of {target!r} as "
                        f"{bind_type!r} where {target!r} returns {expected!r}; an "
                        f"alias is a distinct newtype and does not silently coerce "
                        f"(README ss10, WS2-089)",
                        out_row.line, code="SS1030",
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
    <TrustedType>`. R-071: the arg must then BE EXACTLY that trusted type — a
    `validated`/`trustedInternal` label is no longer a universal sink credential,
    so a value safe for one context (e.g. `SqlText`) cannot satisfy a different
    sink (e.g. an `HtmlSafeUrl` slot); a plain `String` is rejected, and a value
    assembled by `string.concat` may never reach a sink (no string-built
    queries/markup). Hard error SS3071. (`rawExternal`/`secret` into a sink is
    SS3070, X-070.)"""
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
            if argtype != required:
                raise EavError(
                    f"call {call.name!r} passes {value!r} (type {argtype!r}) into the "
                    f"{required} sink slot {slot!r} of {callee!r}: a trust-sensitive "
                    f"sink requires exactly its safe type — a validated/trustedInternal "
                    f"value of another type is a cross-context bypass. Convert {value!r} "
                    f"to {required} at a trust boundary first (README §16, R-071)",
                    call.line, code="SS3071")


_OBSERVABLE_SINK_TARGETS = (
    "console.writeLine", "console.writeIntegerLine", "console.writeFloatLine",
    # R-072: HTML render surfaces a value into a client-visible document
    "html.render",
)

# R-072: JSON serialization prefixes that surface a value into a wire-format
# representation (json.serialize, json.encode, json.stringify, json.serializeDocument, …)
_OBSERVABLE_SINK_JSON_PREFIXES = (
    "json.serial",   # json.serialize / json.serializeDocument
    "json.encode",   # json.encode*
    "json.stringify",  # json.stringify*
)


def _is_observable_sink(target: str) -> bool:
    # console writes, log.*, html.render, and JSON serialization surface a value to
    # a human-readable or wire-format channel (R-072 extends the original X-072 set)
    if target in _OBSERVABLE_SINK_TARGETS:
        return True
    if target.startswith("log."):
        return True
    for prefix in _OBSERVABLE_SINK_JSON_PREFIXES:
        if target.startswith(prefix):
            return True
    return False


def _is_literal_token(tok: str) -> bool:
    if tok.startswith('"'):
        return True
    t = tok.lstrip("-")
    return t.replace(".", "", 1).isdigit() or tok in ("true", "false", "yes", "no")


def _validate_secret_flow(program: Program) -> None:
    """X-072 / R-072 / README §30.1.1, §8: a `typeTrust secret` value is usable
    (verify/sign/TLS) but never *observable*. Passing a secret-typed value to an
    observable sink (console/log/html.render/json.serialize*/error-constructor/
    clientResponse) is a hard error (SS3072), and a secret-typed binding may not be
    initialized from a source literal ("no hardcoded secrets" — load it from a
    capability-gated source).

    R-072 extension adds:
    - html.render:             a secret rendered into an HTML document leaks to HTTP clients
    - json.serialize*/encode*/ stringify*: a secret serialized to JSON leaks over the wire
    - Error-case constructors: a secret passed as a payload into an error constructor
      (call invokes ErrorDomain.ErrorCase) embeds it in an error report
    - clientResponse slots:   a secret reaching a client-response parameter leaks to the
      HTTP client (complements the trustedInternal check in X-079 / SS3079)

    capturedOutputReplay transcript: because a secret can never reach stdout (the
    console/log blocks above fire first), it can never enter a captured-output-replay
    transcript either — the compile-time block is stronger than runtime redaction, so
    there is no separate transcript check needed."""
    secret_types = {program.entities[n].name for n in program.order
                    for r in program.entities[n].facts("typeTrust")
                    if r.payload and r.payload[0] == "secret"}
    if not secret_types:
        return

    # Collect error-type names so we can detect error-case constructor calls
    # (a call that invokes ErrorDomain.ErrorCase, where ErrorDomain is a known error).
    # R-072: a secret passed as the payload of an error constructor ends up in the error
    # report and can surface in logs, responses, or UI — reject at compile time.
    error_types = {program.entities[n].name for n in program.order
                   if program.entities[n].kind == "error"}

    # Collect clientResponse slot names per callee key so we can detect a secret
    # reaching a client-facing response parameter (R-072 / complement to X-079).
    client_slots: dict = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("operation", "function", "intrinsic"):
            continue
        slots = {r.payload[1] for r in ent.facts("clientResponse")
                 if len(r.payload) >= 2 and r.payload[0] == "arg"}
        if slots:
            client_slots[_sink_key(ent)] = slots

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
        # no observable secrets: a secret-typed arg into an observable sink
        if ent.kind in ("call", "task"):
            inv = ent.fact("invokes")
            target = inv.payload[0] if inv and inv.payload else ""
            if _is_observable_sink(target):
                for a in ent.facts("arg"):
                    # html.render: skip the 'template' slot — only hole args carry
                    # user data that would be rendered into the document
                    if target == "html.render" and len(a.payload) >= 1 and a.payload[0] == "template":
                        continue
                    if len(a.payload) >= 2 and a.payload[1] in secret_types:
                        _val = a.payload[2] if len(a.payload) >= 3 else "?"
                        raise EavError(
                            f"call {ent.name!r} writes a secret value {_val!r} "
                            f"to the observable sink {target!r}; a secret is usable but "
                            f"never observable (README §30.1.1, R-072)",
                            ent.line, code="SS3072")

            # R-072: error-case constructor — a call that invokes ErrorDomain.ErrorCase
            # where ErrorDomain is a known error type embeds its arg in an error report.
            if "." in target:
                domain = target.split(".", 1)[0]
                if domain in error_types:
                    for a in ent.facts("arg"):
                        if len(a.payload) >= 2 and a.payload[1] in secret_types:
                            _val = a.payload[2] if len(a.payload) >= 3 else "?"
                            raise EavError(
                                f"call {ent.name!r} passes a secret value {_val!r} "
                                f"into the error constructor {target!r}; secrets in error "
                                f"payloads can surface in logs, responses, and diagnostics "
                                f"(README §30.1.1, R-072)",
                                ent.line, code="SS3072")

            # R-072: clientResponse sink — a secret reaching a client-response parameter
            # leaks to the HTTP client (complements X-079 / SS3079 for trustedInternal).
            resp_slots = client_slots.get(target)
            if resp_slots:
                for a in ent.facts("arg"):
                    if (len(a.payload) >= 2 and a.payload[0] in resp_slots
                            and a.payload[1] in secret_types):
                        _val = a.payload[2] if len(a.payload) >= 3 else "?"
                        raise EavError(
                            f"call {ent.name!r} sends a secret value {_val!r} "
                            f"to the client-response slot {a.payload[0]!r} of "
                            f"{target!r}; a secret must never reach a client-facing "
                            f"response (README §30.1.1, R-072)",
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


_DETERMINISTIC_RANDOM_TARGETS = (
    "random.deterministic", "random.seeded", "random.seededInt64",
    "random.fromSeed", "random.pseudo",
)
_SECURITY_GEN_TARGETS = (
    "crypto.generateToken", "crypto.generateNonce", "crypto.generateSalt",
    "crypto.generateKey", "crypto.randomBytes", "bcrypt.randomBytes",
)


def _validate_random_source(program: Program) -> None:
    """X-073 / README §30.5.3: security material (keys/tokens/nonces/salts) must
    come from the CSPRNG, never a seeded/deterministic RNG. A value drawn from a
    deterministic-random target that flows into a security generator is a hard
    error (SS3073). (The seeded RNG remains valid for reproducible non-security
    use; entropy vs deterministic is a capability distinction, §30.5.3.)"""
    deterministic = set()
    for n in program.order:
        ent = program.entities[n]
        if ent.kind in ("call", "task"):
            inv = ent.fact("invokes")
            if inv and inv.payload and inv.payload[0] in _DETERMINISTIC_RANDOM_TARGETS:
                for o in ent.facts("out"):
                    if o.payload:
                        deterministic.add(o.payload[0])
    if not deterministic:
        return
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if target not in _SECURITY_GEN_TARGETS:
            continue
        for a in ent.facts("arg"):
            if len(a.payload) >= 3 and a.payload[2] in deterministic:
                raise EavError(
                    f"call {ent.name!r} seeds security generator {target!r} with the "
                    f"deterministic-RNG value {a.payload[2]!r}; security material must "
                    f"come from the CSPRNG (`random.entropy`), not a seeded RNG "
                    f"(README §30.5.3)",
                    ent.line, code="SS3073")


def _validate_nonce_affinity(program: Program) -> None:
    """X-073 / README §30.5.3: a nonce/IV is affine — consumed on use. A value
    produced by `crypto.generateNonce`/`generateIv` that is consumed by two or
    more cryptographic calls is a nonce-reuse hard error (SS3073); reusing a
    nonce across encryptions breaks the cipher's security."""
    nonce_values = set()
    for n in program.order:
        ent = program.entities[n]
        if ent.kind in ("call", "task"):
            inv = ent.fact("invokes")
            if inv and inv.payload and inv.payload[0] in (
                    "crypto.generateNonce", "crypto.generateIv"):
                for o in ent.facts("out"):
                    if o.payload:
                        nonce_values.add(o.payload[0])
    if not nonce_values:
        return
    crypto_uses: dict = {}  # nonce value -> first consuming call name
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if not (target.startswith("crypto.") or target.startswith("cipher.")
                or target.startswith("aead.")):
            continue
        if target in ("crypto.generateNonce", "crypto.generateIv"):
            continue
        for a in ent.facts("arg"):
            val = a.payload[2] if len(a.payload) >= 3 else None
            if val in nonce_values:
                if val in crypto_uses:
                    raise EavError(
                        f"nonce {val!r} is consumed again by {ent.name!r} after "
                        f"{crypto_uses[val]!r}; a nonce/IV is affine — reusing one "
                        f"across encryptions is a security failure (README §30.5.3)",
                        ent.line, code="SS3073")
                crypto_uses[val] = ent.name


def _decode_literal_for_validation(tok: str) -> str:
    """Decode a quoted string literal to its text for the security validators
    (R-091): `\\xNN` / `\\n` / `\\t` / `\\"` / `\\\\` are resolved *before* the
    path-traversal and SSRF checks run, so an escaped `..` (`"\\x2e\\x2e/"`) or an
    escaped private host (`"127\\x2e0\\x2e0\\x2e1"`) cannot slip past. Falls back
    to a bare quote-strip if the token is not a well-formed literal."""
    if not (len(tok) >= 2 and tok.startswith('"') and tok.endswith('"')):
        return tok.strip('"')
    try:
        return _decode_string_literal(tok)[:-1].decode("utf-8", "surrogateescape")
    except (EavError, ValueError, IndexError):
        return tok.strip('"')


def _validate_path_traversal(program: Program) -> None:
    """X-076 / README §8/§27: a filesystem path must be confined under a root. A
    literal `fs.*` path argument that contains a `..` segment or is absolute is an
    obvious traversal/escape — a hard error (SS3076). (Raw-String paths into an
    `fs.*` sink that requires `SafePath` are caught by sink-typing, X-071/SS3071;
    runtime confinement rides `fs.resolveWithin`.)"""
    literals = {}  # binding name -> unquoted literal string
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "storage":
            tr, vr = ent.fact("type"), ent.fact("value")
            if (tr and tr.payload and tr.payload[0] == "String"
                    and vr and vr.payload and vr.payload[0].startswith('"')):
                literals[ent.name] = _decode_literal_for_validation(vr.payload[0])
        if ent.kind in ("operation", "function"):
            for r in ent.facts("let"):
                if (len(r.payload) >= 4 and r.payload[2] == "String"
                        and r.payload[3].startswith('"')):
                    literals[r.payload[0]] = _decode_literal_for_validation(r.payload[3])

    def _is_traversal(path: str) -> bool:
        segs = path.replace("\\", "/").split("/")
        return ".." in segs or path.startswith("/") or (len(path) > 1 and path[1] == ":")

    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if not (target.startswith("fs.") or target.startswith("filesystem.")):
            continue
        for a in ent.facts("arg"):
            if len(a.payload) < 3:
                continue
            val = a.payload[2]
            lit = (_decode_literal_for_validation(val) if val.startswith('"')
                   else literals.get(val))
            if lit is not None and _is_traversal(lit):
                raise EavError(
                    f"call {ent.name!r} passes the path {lit!r} to {target!r}; a `..` or "
                    f"absolute path escapes its root — confine it with "
                    f"`fs.resolveWithin <root>` (README §8)",
                    ent.line, code="SS3076")


_NET_REQUEST_PREFIXES = ("net.", "http.")
_INTERNAL_HOST_MARKERS = (
    "localhost", "127.", "0.0.0.0", "169.254.", "[::1]", "::1",
    "10.", "192.168.", "metadata.google", "169.254.169.254",
)


def _url_host(url: str) -> str:
    s = url
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0]
    return s.lower()


def _is_internal_host(host: str) -> bool:
    if any(host == m or host.startswith(m) for m in _INTERNAL_HOST_MARKERS):
        return True
    # 172.16.0.0/12 private range
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return True
    return False


def _validate_ssrf(program: Program) -> None:
    """X-075 / README §8/§27: an outbound request must go to an allowlisted
    external host. A `net.*`/`http.*` URL literal that targets localhost, a
    private/link-local range, or the cloud-metadata address is a hard error
    (SS3075, SSRF defense). (Raw-String URLs into an `HttpSafeUrl` sink are caught
    by sink-typing, X-071/SS3071; the runtime allowlist rides the net capability.)"""
    literals = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "storage":
            tr, vr = ent.fact("type"), ent.fact("value")
            if (tr and tr.payload and vr and vr.payload
                    and vr.payload[0].startswith('"')):
                literals[ent.name] = _decode_literal_for_validation(vr.payload[0])
        if ent.kind in ("operation", "function"):
            for r in ent.facts("let"):
                if len(r.payload) >= 4 and r.payload[3].startswith('"'):
                    literals[r.payload[0]] = _decode_literal_for_validation(r.payload[3])
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if not any(target.startswith(p) for p in _NET_REQUEST_PREFIXES):
            continue
        for a in ent.facts("arg"):
            if len(a.payload) < 3:
                continue
            val = a.payload[2]
            lit = (_decode_literal_for_validation(val) if val.startswith('"')
                   else literals.get(val))
            if lit is None or "://" not in lit and "." not in lit:
                continue
            # R-091: a decoded CR/LF/NUL in a URL enables request/header injection.
            if any(c in lit for c in ("\r", "\n", "\x00")):
                raise EavError(
                    f"call {ent.name!r} passes a URL with an embedded control byte "
                    f"(CR/LF/NUL) to {target!r}; this enables request/header "
                    f"injection (SSRF, README §8)", ent.line, code="SS3075")
            if _is_internal_host(_url_host(lit)):
                raise EavError(
                    f"call {ent.name!r} sends an outbound request to the internal "
                    f"address {lit!r} via {target!r}; outbound requests go to "
                    f"allowlisted external hosts only (SSRF, README §8)",
                    ent.line, code="SS3075")


_EXTERNAL_IO_PREFIXES = ("net.", "http.", "sqlite.", "db.", "database.", "fs.",
                         "filesystem.")


def _validate_dos_bounds(program: Program) -> None:
    """X-078 / README §27: an effectful external call over untrusted input must be
    bounded. A `net.*`/`http.*`/`sqlite.*`/`db.*`/`fs.*` call that takes a
    `rawExternal`-typed argument must carry a `timeout` or `budget` row so a slow
    or hostile peer cannot stall the process; missing it is a hard error
    (SS3078)."""
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
        if not any(target.startswith(p) for p in _EXTERNAL_IO_PREFIXES):
            continue
        if not any(len(a.payload) >= 2 and a.payload[1] in raw_types
                   for a in ent.facts("arg")):
            continue
        if ent.fact("timeout") is None and ent.fact("budget") is None:
            raise EavError(
                f"call {ent.name!r} performs external I/O ({target!r}) over untrusted "
                f"input but declares no `timeout`/`budget`; bound it so a slow or "
                f"hostile peer cannot stall the process (README §27)",
                ent.line, code="SS3078")


def _validate_untrusted_loop_bounds(program: Program) -> None:
    """R-082 / README §13/§27: a back-edge loop whose exit is decided by an
    untrusted value (a `typeTrust rawExternal`/`secret`-typed size/count) must
    carry an explicit `maxIterations <n>` row on the owning operation, else it is
    rejected (SS0951). A hostile peer can otherwise pick an enormous size and spin
    the process — the loop analogue of the X-078 external-I/O bound.

    The trigger is type-driven and narrow on purpose: only loops whose exit guard
    (or a guard-producing call's input) reads a value typed `rawExternal`/`secret`
    fire. A loop over a trusted/internal size, a fixed capacity, or a validated
    length never trips this, so existing fixed-capacity buffer loops stay legal."""
    untrusted_types = {
        program.entities[n].name for n in program.order
        for r in program.entities[n].facts("typeTrust")
        if r.payload and r.payload[0] in ("rawExternal", "secret")
    }
    if not untrusted_types:
        return  # no untrusted-typed values exist -> nothing to bound
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
        # value -> declared type, from inputs, lets, and owned-call outputs.
        value_type: dict = {}
        for r in op.facts("in"):
            if len(r.payload) >= 2:
                value_type[r.payload[0]] = r.payload[1]
        for r in op.facts("let"):
            if len(r.payload) >= 3:
                value_type[r.payload[0]] = r.payload[2]
        for c in owned.values():
            for o in c.facts("out"):
                if len(o.payload) >= 2:
                    value_type[o.payload[0]] = o.payload[1]
        call_inputs = {
            name: [a.payload[2] for a in c.facts("arg") if len(a.payload) >= 3]
            for name, c in owned.items()
        }
        # producer[outName] = the call whose `out` binds it, so a Bool guard
        # computed from an untrusted operand is traced back to that operand.
        producer: dict = {}
        for name, c in owned.items():
            for o in c.facts("out"):
                if o.payload:
                    producer[o.payload[0]] = name

        def _guard_is_untrusted(guard_names: set) -> bool:
            for g in guard_names:
                if value_type.get(g) in untrusted_types:
                    return True
                # The guard may name a call (ifOut/ifError) or be a value bound
                # by a call's `out` (if/ifFalse over a comparison result). Either
                # way, an untrusted input to that producing call decides the exit.
                src_call = g if g in call_inputs else producer.get(g)
                for inp in call_inputs.get(src_call, ()):
                    if value_type.get(inp) in untrusted_types:
                        return True
            return False

        for gi, r in enumerate(rows):
            tgt = None
            if r.predicate == "goto" and r.payload:
                tgt = r.payload[0]
            elif r.predicate == "branch":
                tgt = _branch_goto_target_and_guards(r, owned)[0]
            li = labels.get(tgt) if tgt is not None else None
            if li is None or li >= gi:
                continue  # forward edge / unknown target -> not a back-edge loop
            untrusted_exit = False
            for j in range(li, gi + 1):
                rj = rows[j]
                if rj.predicate != "branch":
                    continue
                label, guards = _branch_goto_target_and_guards(rj, owned)
                if label is None:
                    continue
                ti = labels.get(label)
                if ti is None or ti < li or ti > gi:  # an exit branch
                    if _guard_is_untrusted(guards):
                        untrusted_exit = True
            if untrusted_exit and op.fact("maxIterations") is None:
                raise EavError(
                    f"loop at {tgt!r} in {op.name!r} iterates under an untrusted "
                    f"(`rawExternal`/`secret`) size but declares no "
                    f"`maxIterations <n>`; bound it so a hostile size cannot spin "
                    f"the process (R-082, README §13/§27)",
                    rows[li].line, code="SS0951")


def _validate_error_disclosure(program: Program) -> None:
    """X-079 / README §16/§25: an internal error/trap detail (`typeTrust
    trustedInternal` error) may not reach a client-facing response sink (a
    `clientResponse arg <slot>`) without an explicit `errorBoundary
    <InternalError> <ClientError>` mapping on the calling op. Returning a raw
    internal error to a client is an information-disclosure hard error (SS3079)."""
    internal_errors = {program.entities[n].name for n in program.order
                       if program.entities[n].kind == "error"
                       for r in program.entities[n].facts("typeTrust")
                       if r.payload and r.payload[0] == "trustedInternal"}
    if not internal_errors:
        return
    client_slots = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("operation", "function", "intrinsic"):
            continue
        slots = {r.payload[1] for r in ent.facts("clientResponse")
                 if len(r.payload) >= 2 and r.payload[0] == "arg"}
        if slots:
            client_slots[_sink_key(ent)] = slots
    if not client_slots:
        return
    for n in program.order:
        call = program.entities[n]
        if call.kind not in ("call", "task"):
            continue
        inv = call.fact("invokes")
        callee = inv.payload[0] if inv and inv.payload else ""
        slots = client_slots.get(callee)
        if not slots:
            continue
        owner = call.fact("in")
        op = program.entities.get(owner.payload[0]) if owner and owner.payload else None
        mapped = {b.payload[0] for b in (op.facts("errorBoundary") if op else [])
                  if b.payload}
        for a in call.facts("arg"):
            if (len(a.payload) >= 3 and a.payload[0] in slots
                    and a.payload[1] in internal_errors and a.payload[1] not in mapped):
                raise EavError(
                    f"call {call.name!r} sends the internal error {a.payload[1]!r} to the "
                    f"client-response slot {a.payload[0]!r} of {callee!r}; map it with "
                    f"`errorBoundary {a.payload[1]} <ClientError>` first (README §16/§25)",
                    call.line, code="SS3079")


_UTF8_DECODE_TARGETS = (
    "bytes.toText", "string.fromBytes", "text.fromUtf8", "text.decodeUtf8",
    "utf8.decode",
)


def _validate_utf8_boundary(program: Program) -> None:
    """X-096 / README §10.6/§16: bytes crossing an input boundary become text only
    through a validator that handles invalid UTF-8 explicitly. A bytes->text decode
    (`bytes.toText`/`string.fromBytes`/`text.fromUtf8`/…) of a `rawExternal` source
    must bind its result to a `validated`/`trustedInternal` text type — otherwise
    invalid UTF-8 could silently corrupt an internal `String` (SS3096)."""
    label_of = {program.entities[n].name: r.payload[0]
                for n in program.order
                for r in program.entities[n].facts("typeTrust")
                if r.payload and r.payload[0] in _TRUST_LABELS}
    raw_types = {t for t, l in label_of.items() if l == "rawExternal"}
    if not raw_types:
        return
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if target not in _UTF8_DECODE_TARGETS:
            continue
        if not any(len(a.payload) >= 2 and a.payload[1] in raw_types
                   for a in ent.facts("arg")):
            continue
        out = ent.fact("out")
        out_type = out.payload[1] if out and len(out.payload) >= 2 else None
        if label_of.get(out_type) not in ("validated", "trustedInternal"):
            raise EavError(
                f"call {ent.name!r} decodes untrusted bytes with {target!r} into "
                f"{out_type!r}, which is not a validated text type; cross a UTF-8 "
                f"validation boundary that yields a `validated` type (README §10.6)",
                ent.line, code="SS3096")


def _validate_protection_optout(program: Program) -> None:
    """X-080 / README §14: secure-by-default — every protection opt-out (disable
    auto-escape, allow plaintext cookies, skip CSRF, widen the host allowlist, …)
    must be an explicit, justified row: `optOut <protection> because "…"`. An
    opt-out with no `because` is a hard error (SS3080), keeping every weakened
    default greppable and accountable."""
    for n in program.order:
        ent = program.entities[n]
        for r in ent.facts("optOut"):
            if not r.payload:
                continue
            if "because" not in r.payload:
                raise EavError(
                    f"{ent.kind} {ent.name!r} opts out of protection {r.payload[0]!r} "
                    f"without a `because`; every security opt-out must be explicit and "
                    f"justified (README §14)",
                    r.line, code="SS3080")


_INT_WIDTHS = {"Int8": 8, "UInt8": 8, "Byte": 8, "Int16": 16, "UInt16": 16,
               "Int32": 32, "UInt32": 32, "ExitCode": 32, "Int64": 64, "UInt64": 64}


_REGION_STRATEGIES = ("arena", "fixedBuffer", "general")


def _validate_ffi_wrapping(program: Program) -> None:
    """WS1-116 / README §26/§30.4: a `runtimeBinding`/`intrinsic` that allocates
    foreign memory is `unsafe yes` and must re-enter app source as an owned
    resource — declaring `wrapsAs <OwnedType>` (the opaque wrapper, never the raw
    pointer), `cleanedBy <freeTarget>`, and `allocator <region|c.heap>`. Missing
    any of those rows on an unsafe allocating binding is a hard error (SS1569)."""
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("intrinsic", "operation", "function"):
            continue
        u = ent.fact("unsafe")
        if not (u and u.payload and u.payload[0] in ("yes", "true", "1")):
            continue
        missing = [r for r in ("wrapsAs", "cleanedBy", "allocator")
                   if ent.fact(r) is None]
        if missing:
            raise EavError(
                f"{ent.kind} {ent.name!r} is an `unsafe yes` foreign allocator but is "
                f"missing {', '.join(missing)}; a foreign allocation must re-enter as an "
                f"owned resource (`wrapsAs`+`cleanedBy`+`allocator`) (README §26/§30.4)",
                ent.line, code="SS1569")


_BUFFER_FALLIBLE_READS = ("buffer.get", "buffer.at", "buffer.read", "buffer.byteAt")


def _validate_buffer_access(program: Program) -> None:
    """WS1-115 / README §10.6: a bounds-checked buffer read is fallible — an
    out-of-bounds index is a `BufferBoundsError`, never UB. A `buffer.get`/`at`/
    `read` call must bind a `catch` for that error (and branch on it); a read with
    no error path silently drops the bounds failure and is a hard error (SS1568).
    (App source has no indexing/offset syntax, so this is the only access path.)"""
    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if target in _BUFFER_FALLIBLE_READS and ent.fact("catch") is None:
            raise EavError(
                f"call {ent.name!r} reads a buffer with {target!r} but has no `catch` "
                f"for its BufferBoundsError; a bounds-checked read is fallible and its "
                f"out-of-bounds error must be handled (README §10.6)",
                ent.line, code="SS1568")


_CONTRACT_CONDS = ("nonNegative", "positive", "nonZero")


def _contract_holds(cond: str, value: int):
    """Evaluate a numeric precondition on a literal. Returns True/False, or None
    if `cond` is unknown (not statically decidable here)."""
    if cond == "nonNegative":
        return value >= 0
    if cond == "positive":
        return value > 0
    if cond == "nonZero":
        return value != 0
    return None


_PRINTF_TARGETS = ("c.printf", "printf", "console.format", "c.fprintf", "c.sprintf")
_SHELL_TARGETS = ("shell.run", "shell.exec", "process.exec", "c.system", "os.exec",
                  "c.popen")
_BCRYPT_HASH_TARGETS = ("bcrypt.hashPassword", "bcrypt.hash")
_MIN_BCRYPT_COST = 10

# WS2-086: the semsc security-lint names reconciled to the EAV X6 diagnostics.
SECURITY_LINT_PARITY = {
    "insecure-pseudorandom": "SS3073",            # X-073 CSPRNG vs deterministic
    "weak-password-hash-cost": "SS3086",          # new (this batch)
    "shell-command-not-constant": "SS3087",       # new (this batch)
    "format-string-must-be-constant": "SS3088",   # new (this batch)
    "hardcoded-secret": "SS3072",                 # X-072 secret-typed values
    "unguarded-http-input": "SS3077",             # X-077 untrusted decode limits
    "untrusted-http-html-hydration": "SS3071",    # X-071 sink-typing / auto-escape
    "unescaped-json-string-interpolation": "SS3071",  # X-071 no string-built sinks
}


def _validate_security_parity(program: Program) -> None:
    """WS2-086 / X6: port the remaining semsc security lints. A `bcrypt.hashPassword`
    with a constant cost < 10 is rejected (SS3086); a shell/exec command that is
    not a compile-time constant is rejected (SS3087, command injection); a
    printf-family format that is not constant is rejected (SS3088, format-string
    injection). The other names in SECURITY_LINT_PARITY are the existing X-071/072/
    073/077 checks (reconciled, not re-implemented)."""
    const_names, int_const = set(), {}
    for n in program.order:
        ent = program.entities[n]
        rows = []
        if ent.kind == "storage":
            vr = ent.fact("value")
            if vr and vr.payload:
                rows.append((ent.name, vr.payload[0]))
        if ent.kind in ("operation", "function"):
            rows += [(r.payload[0], r.payload[3]) for r in ent.facts("let")
                     if len(r.payload) >= 4]
        for nm, val in rows:
            if val.startswith('"') or val.lstrip("-").isdigit() or val in ("true", "false"):
                const_names.add(nm)
                if val.lstrip("-").isdigit():
                    int_const[nm] = int(val)

    def is_const(tok):
        return (tok.startswith('"') or tok.lstrip("-").isdigit()
                or tok in ("true", "false") or tok in const_names)

    def const_int(tok):
        return int(tok) if tok.lstrip("-").isdigit() else int_const.get(tok)

    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        args = {a.payload[0]: a.payload[2] for a in ent.facts("arg") if len(a.payload) >= 3}
        if target in _BCRYPT_HASH_TARGETS and "cost" in args:
            ci = const_int(args["cost"])
            if ci is not None and ci < _MIN_BCRYPT_COST:
                raise EavError(
                    f"call {ent.name!r} hashes a password with cost {ci} (< "
                    f"{_MIN_BCRYPT_COST}); use a cost >= {_MIN_BCRYPT_COST} (README §8)",
                    ent.line, code="SS3086")
        if target in _SHELL_TARGETS:
            for slot in ("command", "cmd", "commandLine"):
                if slot in args and not is_const(args[slot]):
                    raise EavError(
                        f"call {ent.name!r} runs a non-constant shell command "
                        f"{args[slot]!r} via {target!r}; the command must be constant — "
                        f"pass dynamic data as argv, never a built command string "
                        f"(README §16/§30.2.2)",
                        ent.line, code="SS3087")
        if target in _PRINTF_TARGETS and "format" in args and not is_const(args["format"]):
            raise EavError(
                f"call {ent.name!r} uses a non-constant format {args['format']!r} in "
                f"{target!r}; the format string must be constant — pass dynamic values "
                f"as arguments (README §30.2.2)",
                ent.line, code="SS3088")


def _validate_contracts(program: Program) -> None:
    """X-092 / README §6/§10.6: a `requires <cond> <param>` precondition on an op
    is checked at each call site — a literal arg violating it is a hard error
    (SS3092), a satisfying literal is statically discharged (no runtime check,
    handled in codegen), and an unknown arg gets a runtime assert (codegen). Only
    numeric conditions (nonNegative/positive/nonZero) are statically evaluated."""
    int_const = {}  # binding -> int (module + per-op lets)
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "storage":
            tr, vr = ent.fact("type"), ent.fact("value")
            if tr and vr and vr.payload and vr.payload[0].lstrip("-").isdigit():
                int_const[ent.name] = int(vr.payload[0])
        if ent.kind in ("operation", "function"):
            for r in ent.facts("let"):
                if len(r.payload) >= 4 and r.payload[3].lstrip("-").isdigit():
                    int_const[r.payload[0]] = int(r.payload[3])
    for n in program.order:
        call = program.entities[n]
        if call.kind not in ("call", "task"):
            continue
        inv = call.fact("invokes")
        callee = program.entities.get(inv.payload[0]) if inv and inv.payload else None
        if callee is None or callee.kind not in ("operation", "function"):
            continue
        args = {a.payload[0]: a.payload[2] for a in call.facts("arg") if len(a.payload) >= 3}
        for req in callee.facts("requires"):
            if len(req.payload) < 2:
                continue
            cond, param = req.payload[0], req.payload[1]
            val = args.get(param)
            if val is None:
                continue
            lit = int(val) if val.lstrip("-").isdigit() else int_const.get(val)
            if lit is None:
                continue  # runtime value -> codegen asserts it
            if _contract_holds(cond, lit) is False:
                raise EavError(
                    f"call {call.name!r} passes {val} for {param!r}, violating "
                    f"{callee.name!r}'s precondition `requires {cond} {param}` "
                    f"(README §6)", call.line, code="SS3092")


def _validate_typestate(program: Program) -> None:
    """X-091 / README §13/§15.6: a `typestate <T>` declares a protocol over a type
    — `state`s, an `initial` state, and `allows <from> <target> <to>` transitions.
    A transition op invoked on a value not in its required `from` state is a hard
    error (SS3091): the resource open→use→close contract and the task lifecycle are
    one mechanism. Flow-sensitive but linear — a value's state is tracked once
    known (produced in-op or after a prior transition); an input's state is unknown
    until first transitioned, so it is not pre-judged (no false positives)."""
    ts = {}  # governed type -> {target: (from, to)}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind != "typestate":
            continue
        gov = ent.fact("for")
        if not (gov and gov.payload):
            continue
        trans = {a.payload[1]: (a.payload[0], a.payload[2])
                 for a in ent.facts("allows") if len(a.payload) >= 3}
        if trans:
            ts[gov.payload[0]] = trans
    if not ts:
        return
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        calls = {program.entities[c].name: program.entities[c]
                 for c in program.order
                 if program.entities[c].kind in ("call", "task")
                 and (program.entities[c].fact("in") or Row("", "", [], 0)).payload[:1] == [op.name]}
        value_state = {}  # value name -> known current state
        for row in op.rows:
            if row.predicate not in ("do", "start", "join", "poll") or not row.payload:
                continue
            call = calls.get(row.payload[0])
            if call is None:
                continue
            inv = call.fact("invokes")
            target = inv.payload[0] if inv and inv.payload else ""
            for gtype, trans in ts.items():
                tr = trans.get(target)
                if tr is None:
                    continue
                frm, to = tr
                out = call.fact("out")
                if out and len(out.payload) >= 2 and out.payload[1] == gtype:
                    value_state[out.payload[0]] = to  # producer: fresh value in `to`
                else:
                    for a in call.facts("arg"):
                        if len(a.payload) >= 3 and a.payload[1] == gtype:
                            v = a.payload[2]
                            cur = value_state.get(v)
                            if cur is not None and cur != frm:
                                raise EavError(
                                    f"{op.name!r} calls {target!r} on {v!r} in state "
                                    f"{cur!r}, but it is only allowed from {frm!r} "
                                    f"(typestate protocol, README §13)",
                                    row.line, code="SS3091")
                            value_state[v] = to
                            break


def _validate_lock_ordering(program: Program) -> None:
    """X-090 / README §27: deadlock-free acquisition ordering. A guarded
    `sharedState` may declare a `guardRank N`; within an op, guarded resources
    must be accessed in non-decreasing rank order (a fixed total order over locks
    prevents deadlock). Accessing a lower-rank guard after a higher-rank one is a
    hard error (SS3085). The single-thread backend is trivially deadlock-free, so
    this gates the concurrent backend."""
    rank = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "sharedState":
            r = ent.fact("guardRank")
            if r and r.payload and r.payload[0].lstrip("-").isdigit():
                rank[ent.name] = int(r.payload[0])
    if not rank:
        return
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        max_rank, max_state = None, None
        for row in op.rows:
            if row.predicate not in ("readShared", "setShared") or not row.payload:
                continue
            state = row.payload[2] if row.predicate == "readShared" else row.payload[0]
            if state not in rank:
                continue
            r = rank[state]
            if max_rank is not None and r < max_rank and state != max_state:
                raise EavError(
                    f"{op.name!r} acquires guard {state!r} (rank {r}) after "
                    f"{max_state!r} (rank {max_rank}); acquire guards in non-decreasing "
                    f"rank order to stay deadlock-free (README §27)",
                    row.line, code="SS3085")
            if max_rank is None or r > max_rank:
                max_rank, max_state = r, state


def _validate_regions(program: Program) -> None:
    """WS1-112 / README §29 #14: a `region` (strategy arena|fixedBuffer|general)
    is an allocation scope. Objects are `allocateIn <region>` and the whole region
    is freed by `releaseRegion <region>`. Allocating requires an allocator
    capability covering `allocate heap.<region>` (SS1563), and an `allocateIn`/
    `releaseRegion` must name a declared region, with each release matching an
    allocation in the same op — so wrong-region free is unrepresentable (SS1562)."""
    regions = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind != "region":
            continue
        strat = ent.fact("strategy")
        if not (strat and strat.payload and strat.payload[0] in _REGION_STRATEGIES):
            raise EavError(  # WS1-120 SS1570
                f"region {ent.name!r} needs a `strategy` of "
                f"{', '.join(_REGION_STRATEGIES)} (README §29 #14)",
                ent.line, code="SS1570")
        if ent.fact("scope") is None:
            raise EavError(  # WS1-120 SS1570
                f"region {ent.name!r} needs a `scope <op>` (README §29 #14)",
                ent.line, code="SS1570")
        regions[ent.name] = strat.payload[0]
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        grants = set()
        for u in op.facts("uses"):
            cap = program.entities.get(u.payload[0]) if u.payload else None
            if cap and cap.kind == "capability":
                for g in cap.facts("grants"):
                    if len(g.payload) >= 2:
                        grants.add((g.payload[0], g.payload[1]))

        def _alloc_covered(region):
            for act, res in grants:
                if act == "allocate" and (res == "heap" or res == f"heap.{region}"):
                    return True
            return False

        calls = {program.entities[c].name: program.entities[c]
                 for c in program.order
                 if program.entities[c].kind in ("call", "task")
                 and (program.entities[c].fact("in") or Row("", "", [], 0)).payload[:1] == [op.name]}
        allocated, released, var_region = set(), set(), {}
        for row in op.rows:
            # SS1561: a value allocated in a region used after its release
            refs = []
            if row.predicate in ("do", "start", "join", "poll") and row.payload:
                c = calls.get(row.payload[0])
                if c is not None:
                    refs = [a.payload[2] for a in c.facts("arg") if len(a.payload) >= 3]
            elif row.predicate == "return":
                refs = [t for t in row.payload
                        if t not in ("value", "ok", "error", "nil", "void")]
            for r in refs:
                if var_region.get(r) in released:
                    raise EavError(
                        f"{op.name!r} uses {r!r} after its region "
                        f"{var_region[r]!r} was released (use-after-region-release, "
                        f"README §29 #14)", row.line, code="SS1561")
            if row.predicate == "allocateIn" and row.payload:
                region = row.payload[0]
                if region not in regions:
                    raise EavError(
                        f"{op.name!r} allocates in undeclared region {region!r} "
                        f"(README §29 #14)", row.line, code="SS1562")
                if not _alloc_covered(region):
                    raise EavError(
                        f"{op.name!r} allocates in region {region!r} without an allocator "
                        f"capability granting `allocate heap.{region}` (README §8)",
                        row.line, code="SS1563")
                allocated.add(region)
                if len(row.payload) >= 2:
                    var_region[row.payload[1]] = region
            elif row.predicate == "releaseRegion" and row.payload:
                region = row.payload[0]
                if region not in regions:
                    raise EavError(
                        f"{op.name!r} releases undeclared region {region!r} "
                        f"(README §29 #14)", row.line, code="SS1562")
                if region not in allocated:
                    raise EavError(
                        f"{op.name!r} releases region {region!r} but never allocated in it "
                        f"(free/allocate mismatch, README §29 #14)",
                        row.line, code="SS1562")
                if region in released:
                    raise EavError(  # WS1-120 SS1565
                        f"{op.name!r} releases region {region!r} twice "
                        f"(double-release, README §29 #14)", row.line, code="SS1565")
                released.add(region)


def _validate_shared_state(program: Program) -> None:
    """WS2-083 / README §8/§27: guarded cross-task mutable state. A `sharedState`
    entity declares a `guard <token>`; every `readShared`/`setShared` of it must be
    `protectedBy` that exact token (holding the guard) — an unguarded or
    wrong-token access is a hard error (SS3083). The `scope` must be `process` or
    `module` (SS3084)."""
    guard_of = {}
    for n in program.order:
        ent = program.entities[n]
        if ent.kind != "sharedState":
            continue
        scope = ent.fact("scope")
        if scope and scope.payload and scope.payload[0] not in ("process", "module"):
            raise EavError(
                f"sharedState {ent.name!r} has scope {scope.payload[0]!r}; a shared "
                f"state must be `process` or `module` scope (README §8)",
                scope.line, code="SS3084")
        g = ent.fact("guard")
        guard_of[ent.name] = g.payload[0] if g and g.payload else None
    if not guard_of:
        return
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
        for row in op.rows:
            if row.predicate not in ("readShared", "setShared") or not row.payload:
                continue
            # readShared <var> <Type> <state> protectedBy <token>
            # setShared  <state> <value> protectedBy <token>
            state = row.payload[2] if row.predicate == "readShared" else row.payload[0]
            if state not in guard_of:
                continue
            token = row.payload[row.payload.index("protectedBy") + 1] \
                if "protectedBy" in row.payload else None
            if token != guard_of[state]:
                raise EavError(
                    f"{op.name!r} accesses shared state {state!r} "
                    f"{'without holding' if token is None else 'with the wrong'} its guard "
                    f"token (expected `protectedBy {guard_of[state]}`) (README §8/§27)",
                    row.line, code="SS3083")


def _validate_numeric_ub(program: Program) -> None:
    """WS2-085 / README §10.6/§33.5: numeric undefined-behavior parity. A `math.*`
    op whose two operands have different declared integer widths is rejected
    (SS3110 — EAV has no implicit widening); a divide/modulo by a constant 0 or a
    shift by a constant >= the operand width is rejected (SS3111). (The runtime
    div-by-zero guard remains for non-constant divisors.)"""
    int_const = {}  # binding name -> int value
    for n in program.order:
        ent = program.entities[n]
        rows = []
        if ent.kind == "storage":
            tr, vr = ent.fact("type"), ent.fact("value")
            if tr and tr.payload and vr and vr.payload:
                rows.append((ent.name, tr.payload[0], vr.payload[0]))
        if ent.kind in ("operation", "function"):
            for r in ent.facts("let"):
                if len(r.payload) >= 4:
                    rows.append((r.payload[0], r.payload[2], r.payload[3]))
        for name, typ, val in rows:
            if typ in _INT_WIDTHS:
                t = val.lstrip("-")
                if t.isdigit():
                    int_const[name] = int(val)

    def const_int(tok):
        t = tok.lstrip("-")
        if t.isdigit():
            return int(tok)
        return int_const.get(tok)

    for n in program.order:
        ent = program.entities[n]
        if ent.kind not in ("call", "task"):
            continue
        inv = ent.fact("invokes")
        target = inv.payload[0] if inv and inv.payload else ""
        if not target.startswith("math."):
            continue
        by_slot = {a.payload[0]: a.payload for a in ent.facts("arg")
                   if len(a.payload) >= 3}
        left, right = by_slot.get("left"), by_slot.get("right")
        # width drift
        if left and right:
            lw, rw = _INT_WIDTHS.get(left[1]), _INT_WIDTHS.get(right[1])
            if lw and rw and lw != rw:
                raise EavError(
                    f"call {ent.name!r} mixes operand widths ({left[1]} vs {right[1]}) "
                    f"in {target!r}; convert one operand explicitly — EAV has no "
                    f"implicit integer widening (README §10.6)",
                    ent.line, code="SS3110")
        # constant divide/modulo by zero
        if right and ("divide" in target.lower() or "modulo" in target.lower()):
            if const_int(right[2]) == 0:
                raise EavError(
                    f"call {ent.name!r} divides by the constant 0 in {target!r}; "
                    f"constant division/modulo by zero is undefined (README §33.5)",
                    ent.line, code="SS3111")
        # constant shift >= operand width
        if right and "shift" in target.lower():
            width = 64 if "64" in target else 32 if "32" in target else None
            amt = const_int(right[2])
            if width is not None and amt is not None and amt >= width:
                raise EavError(
                    f"call {ent.name!r} shifts by the constant {amt} in {target!r} "
                    f"(>= the {width}-bit operand width); the result is undefined "
                    f"(README §33.5)",
                    ent.line, code="SS3111")


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
        if ent.fact("lifetime") is None:  # WS1-120 SS1571
            raise EavError(
                f"{ent.kind} {ent.name!r} borrows a resource but declares no "
                f"`lifetime` — a view must name what it borrows from (README §32.1 #9)",
                ent.line, code="SS1571")
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

    # WS1-122 seam: a call to a view-producing intrinsic INHERITS the intrinsic's
    # `mayEscape no` view-ness. The stdlib `.semsig` publishes the lifetime
    # annotation (e.g. `memory.allocateIn`/`buffer.slice` declare a borrowed view)
    # and the language enforces it at every call site — neither hard-codes the
    # other. So returning a borrowed View/Slice out of an op is rejected (SS1560)
    # without the caller re-declaring the rows.
    intrinsic_view_noescape = set()
    for n in program.order:
        ent = program.entities[n]
        if ent.kind == "intrinsic" and ent.fact("borrows") is not None:
            t, me = ent.fact("target"), ent.fact("mayEscape")
            if t and t.payload and me and me.payload and me.payload[0] == "no":
                intrinsic_view_noescape.add(t.payload[0])
    if intrinsic_view_noescape:
        for n in program.order:
            ent = program.entities[n]
            if ent.kind not in ("call", "task") or ent.fact("borrows") is not None:
                continue  # calls with their own `borrows` row are handled above
            inv = ent.fact("invokes")
            target = inv.payload[0] if inv and inv.payload else ""
            if target not in intrinsic_view_noescape:
                continue
            out = ent.fact("out")
            view_value = out.payload[0] if out and out.payload else None
            op = program.entities.get(owner_of.get(ent.name))
            if view_value is None or op is None:
                continue
            for row in op.rows:
                if row.predicate == "return" and view_value in row.payload:
                    raise EavError(
                        f"view {view_value!r} from {target!r} is a borrowed view "
                        f"(`mayEscape no` in its contract) but is returned out of "
                        f"{op.name!r}; it would outlive its borrowed source "
                        f"(README §32.1 #9)",
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


def _validate_branch_condition(program: Program) -> None:
    """README ss13 / WS2-089 (branch-semantics): a `branch if <cond>` /
    `branch ifFalse <cond>` is a Bool position. When the condition operand
    resolves to a known non-Bool binding type it is a hard error — branch on a
    comparison/predicate result, not a raw scalar. (Forms with their own operand
    grammar — ifValue/ifVariant/ifError/ifReady/ifPending/ifCanceled/ifOut — are
    handled by their own rules and skipped here.) Unknown operands are skipped to
    avoid false positives on bindings sourced outside the local btype map."""
    alias_map = {
        a.name: a.fact("for").payload[0]
        for a in program.of_kind("alias")
        if a.fact("for") and a.fact("for").payload
    }
    for n in program.order:
        op = program.entities[n]
        if op.kind not in ("operation", "function"):
            continue
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
            if row.predicate != "branch" or len(row.payload) < 2:
                continue
            if row.payload[0] not in ("if", "ifFalse"):
                continue
            cond = row.payload[1]
            bt = btypes.get(cond)
            if bt is None:
                continue
            if _resolve_alias(bt, alias_map) != "Bool":
                raise EavError(
                    f"`branch {row.payload[0]} {cond}` in {op.name!r} branches on "
                    f"{cond!r} of type {bt!r}, not Bool; branch on a "
                    f"comparison/predicate result (README ss13, WS2-089)",
                    row.line, code="SS1031",
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


# The project's own native-runtime symbol namespaces: `ss_*` (the C runtime under
# runtime/) and `dom_*` (the wasm DOM host adapter). A runtimeBinding to one of
# these is the sanctioned platform seam (README §11/§26), distinct from ad-hoc
# raw-libc (`c.*`, bare libc) FFI which has safe stdlib wrappers.
_PLATFORM_RUNTIME_PREFIXES = ("ss_", "dom_")

# Types that represent an operation's ABI-injected context or continuation: a
# webServer handler's request/response, a middleware's `next`, the lifecycle
# serverContext, and the GUI handler session/event. An `in` parameter of one of
# these types is mandated by the operation's role ABI (README §14), so it is not
# a dead parameter even when a given handler never reads it (SS0805 exempt).
_ABI_CONTEXT_INPUT_TYPES = frozenset({
    "HttpRequest", "HttpResponse", "NextMiddleware", "ServerContext",
    "GuiSession", "GuiEvent",
})


def _is_platform_runtime_symbol(op: Entity) -> bool:
    """True if `op`'s runtimeBinding target is a project native-runtime symbol."""
    row = op.fact("body")
    if not row or len(row.payload) < 2:
        return False
    symbol = row.payload[1]
    return symbol.startswith(_PLATFORM_RUNTIME_PREFIXES)


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
# semanticscript is its own backend. A parsed EAV Program is lowered *directly* to an
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
# Bitwise ops (shift/and/or/xor) round out the integer ALU: the linter already
# guards over-wide constant shifts (SS3111), so these complete a feature whose
# validation predated its codegen. shiftRight is arithmetic (sign-preserving)
# because Int64 is signed (README §10.6).
_INT_BINOPS = {
    "math.addInt64": "add", "math.subtractInt64": "sub",
    "math.multiplyInt64": "mul", "math.divideInt64": "sdiv",
    "math.moduloInt64": "srem",
    "math.shiftLeftInt64": "shl", "math.shiftRightInt64": "ashr",
    "math.bitAndInt64": "and_", "math.bitOrInt64": "or_",
    "math.bitXorInt64": "xor",
    # Int32 width variants (operands resolve to their declared i32; the op is
    # width-agnostic). APP-RUN-6 taskforge-web mixes Int32 and Int64 arithmetic.
    "math.addInt32": "add", "math.subtractInt32": "sub",
    "math.multiplyInt32": "mul", "math.divideInt32": "sdiv",
    "math.moduloInt32": "srem",
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
    "math.equalInt32": "==", "math.notEqualInt32": "!=",
    "math.lessThanInt32": "<", "math.lessThanOrEqualInt32": "<=",
    "math.greaterThanInt32": ">", "math.greaterThanOrEqualInt32": ">=",
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

    def __init__(self, program: Program, platform: Optional["Entity"] = None):
        self.program = program
        # R-017: the build platform (a resolved `platform` entity, or None for
        # host) drives the module triple and `forPlatform` inclusion.
        self.build_platform = platform
        self.module = ir.Module(name="eav")
        self.module.triple = (_platform_triple(platform) if platform is not None
                              else llvm.get_default_triple())
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
        if ent is not None and ent.kind == "enum":
            # R-054: an enum whose variants carry data lowers to a tagged union
            # {i32 tag, payload}; a plain discriminant enum stays i32 (unchanged).
            pt = self._enum_payload_type(ent)
            if pt is not None:
                return ir.LiteralStructType([ir.IntType(32), pt])
            return ir.IntType(32)
        if ent is not None and ent.kind == "error":
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
        # README §2: a `body <kind>` island (json/sql/html/...) embeds its indented
        # text as a String constant — e.g. a JsonText storage holding a static JSON
        # response body. The island lines are captured by the parser into
        # `program.islands`; join them verbatim and embed as a NUL-terminated blob.
        body_row = st.fact("body")
        if body_row and body_row.payload:
            island = getattr(self.program, "islands", {}).get(
                (st.name, body_row.payload[0]))
            if island is not None:
                text = "\n".join(island).strip()
                self.module_storage[st.name] = (
                    self.global_string(text.encode("utf-8") + b"\x00"), "String")
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
            pt = _PRIMITIVE_IR[resolved]
            # a pointer (String) zero-init is `null`, not the integer 0
            gv.initializer = ir.Constant(pt, None if isinstance(pt, ir.PointerType) else 0)
        self.module_storage[st.name] = (gv, type_row.payload[0])

    def _record_layout(self, rec: Entity):
        """(LLVM struct type, ordered field names) for a record, cached. R-039: a
        named instantiation `R instantiates Base T…` takes Base's fields with the
        generic `typeParam`s substituted by the concrete type args."""
        if rec.name in self._record_layouts:
            return self._record_layouts[rec.name]
        inst = rec.fact("instantiates")
        if inst and inst.payload:
            base = self.program.entities[inst.payload[0]]
            tps = [r.payload[0] for r in base.facts("typeParam") if r.payload]
            sub = dict(zip(tps, inst.payload[1:]))
            fields = [f for f in base.facts("field") if len(f.payload) >= 2]
            field_types = [sub.get(f.payload[1], f.payload[1]) for f in fields]
        else:
            fields = [f for f in rec.facts("field") if len(f.payload) >= 2]
            field_types = [f.payload[1] for f in fields]
        struct_t = ir.LiteralStructType([self.ir_type(t) for t in field_types])
        names = [f.payload[0] for f in fields]
        self._record_layouts[rec.name] = (struct_t, names)
        return self._record_layouts[rec.name]

    # -- R-054/R-039 data-carrying (and generic) enum variants --
    def _enum_base(self, ent: Entity):
        """(base enum, typeParam→concrete substitution), following an
        `instantiates Base T…` named instantiation (a generic enum)."""
        inst = ent.fact("instantiates")
        if inst and inst.payload:
            base = self.program.entities[inst.payload[0]]
            tps = [r.payload[0] for r in base.facts("typeParam") if r.payload]
            return base, dict(zip(tps, inst.payload[1:]))
        return ent, {}

    def _enum_variant_names(self, ent: Entity) -> list:
        base, _ = self._enum_base(ent)
        return [v.payload[0] for v in base.facts("variant") if v.payload]

    def _enum_repr_map(self, ent: Entity) -> dict:
        base, _ = self._enum_base(ent)
        return {r.payload[0]: int(r.payload[1])
                for r in base.facts("repr") if len(r.payload) >= 2}

    def _enum_payload_type(self, ent: Entity):
        """The IR type carried by an enum's data variants, or None for a plain
        (payloadless) discriminant enum. All data variants share one payload
        type in this minimal model (e.g. Option<T> = none | some T)."""
        base, sub = self._enum_base(ent)
        for v in base.facts("variant"):
            if len(v.payload) >= 2:
                return self.ir_type(sub.get(v.payload[1], v.payload[1]))
        return None

    def _enum_variant_has_payload(self, ent: Entity, variant: str) -> bool:
        base, _ = self._enum_base(ent)
        for v in base.facts("variant"):
            if v.payload and v.payload[0] == variant:
                return len(v.payload) >= 2
        return False

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
        elif name == "free":
            fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [i8p]),
                             name="free")
        elif name == "realloc":
            fn = ir.Function(self.module,
                             ir.FunctionType(i8p, [i8p, ir.IntType(64)]),
                             name="realloc")
        elif name in ("strcpy", "strcat"):
            fn = ir.Function(self.module, ir.FunctionType(i8p, [i8p, i8p]), name=name)
        elif name == "strcmp":
            fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [i8p, i8p]),
                             name="strcmp")
        elif name == "ss_http_html_escape_str":
            fn = ir.Function(self.module, ir.FunctionType(i8p, [i8p]),
                             name="ss_http_html_escape_str")
        elif name == "ss_http_serve_routes":
            # APP-RUN-5 webServer entry: int(host, port, count, methods**,
            # paths**, handlers**) -> blocks in the server loop.
            i32 = ir.IntType(32)
            i8pp = i8p.as_pointer()
            fn = ir.Function(self.module,
                             ir.FunctionType(i32, [i8p, i32, i32, i8pp, i8pp, i8pp]),
                             name="ss_http_serve_routes")
        elif name == "ss_net_fetch_text":
            # APP-RUN-1: HTTP-GET client — char *ss_net_fetch_text(const char *url).
            fn = ir.Function(self.module, ir.FunctionType(i8p, [i8p]),
                             name="ss_net_fetch_text")
        elif name == "ss_net_free_text":
            fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [i8p]),
                             name="ss_net_free_text")
        elif name in ("ss_event_open_stream", "ss_event_subscribe",
                      "ss_event_append", "ss_event_receive",
                      "ss_event_ack", "ss_event_close_subscription",
                      "ss_event_close_stream"):
            # APP-RUN-3 event pub/sub: opaque handles + ids are Int64; strings
            # are i8*. Signatures: open(name,cap)->h, subscribe(h,type,key)->h,
            # append(h,type,key,payload)->id, receive(sub)->id, ack(sub,id)->(),
            # close_subscription(sub)->(), close_stream(h)->().
            i64 = ir.IntType(64)
            sigs = {
                "ss_event_open_stream": ir.FunctionType(i64, [i8p, i64]),
                "ss_event_subscribe": ir.FunctionType(i64, [i64, i8p, i8p]),
                "ss_event_append": ir.FunctionType(i64, [i64, i8p, i8p, i8p]),
                "ss_event_receive": ir.FunctionType(i64, [i64]),
                "ss_event_ack": ir.FunctionType(ir.VoidType(), [i64, i64]),
                "ss_event_close_subscription": ir.FunctionType(ir.VoidType(), [i64]),
                "ss_event_close_stream": ir.FunctionType(ir.VoidType(), [i64]),
            }
            fn = ir.Function(self.module, sigs[name], name=name)
        elif name == "ss_panic":
            # WS1-130 structured-trap helper: prints a crash report
            # (code · kind · op · row · reason · operands) to stderr and exits.
            i64 = ir.IntType(64)
            fn = ir.Function(
                self.module,
                ir.FunctionType(ir.VoidType(), [i8p, i8p, i8p, i32, i8p, i64, i64]),
                name="ss_panic")
            fn.attributes.add("noreturn")
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
        if target not in ("console", "webServer"):
            raise EavError(
                "the LLVM code generator supports `target console` and "
                f"`target webServer`, got {target!r}; wasm lowering is out of scope "
                "(todos WS3)"
            )
        entry_row = project.fact("entry")
        if entry_row and entry_row.payload:
            self.entry_name = entry_row.payload[0]
        self.module_storage: dict[str, tuple] = {}
        for st in self.program.of_kind("storage"):
            scope = st.fact("scope")
            if scope and scope.payload and scope.payload[0] == "module":
                self._make_module_storage(st)
        # WS2-083: a sharedState lowers to a process/module global (single-thread
        # backend — the guard token is a no-op; readShared/setShared are load/store).
        for ss in self.program.of_kind("sharedState"):
            self._make_module_storage(ss)
        # README ss30.3.2: a `configure` op runs at build time and is excluded
        # from the runtime build — it is not lowered into the program module.
        configure_ops = {
            p.payload[0]
            for proj in self.program.of_kind("project")
            for p in proj.facts("configure")
            if p.payload
        }
        # R-017 / README §30.3.1: when building for a specific platform, exclude
        # operations gated `forPlatform <other>` so e.g. linuxX64-only code is
        # absent from a windows build. A host build (no `--platform`) applies no
        # platform filtering, preserving existing behavior.
        build_plat_name = self.build_platform.name if self.build_platform else None

        def _included_for_platform(op: Entity) -> bool:
            gates = [r.payload[0] for r in op.facts("forPlatform") if r.payload]
            if not gates or build_plat_name is None:
                return True
            return build_plat_name in gates

        ops = [o for o in self.program.of_kind("operation")
               if o.name not in configure_ops and _included_for_platform(o)]
        # R-039 monomorphizing generics: a generic op (>=1 `typeParam`) is not
        # emitted directly; each distinct instantiation inferred from a call's
        # arg types is emitted as a substituted clone, and calls resolve to it.
        generic_ops = {o.name: o for o in ops if o.facts("typeParam")}
        clones = []
        if generic_ops:
            seen = set()
            for cn in self.program.order:
                c = self.program.entities[cn]
                if c.kind not in ("call", "task"):
                    continue
                inv = c.fact("invokes")
                tgt = inv.payload[0] if inv and inv.payload else None
                if tgt not in generic_ops:
                    continue
                typeargs = self._infer_typeargs(generic_ops[tgt], c)
                if (tgt, typeargs) in seen:
                    continue
                seen.add((tgt, typeargs))
                clones.append(self._make_mono_clone(generic_ops[tgt], typeargs))
        emit_ops = [o for o in ops if o.name not in generic_ops] + clones
        for op in emit_ops:
            self.functions[op.name] = self._declare_function(op)
        for op in emit_ops:
            # runtimeBinding/intrinsic bodies stay bare declarations (extern);
            # full FFI symbol binding is WS3-052/053. Only `body steps` defines.
            if _op_body_kind(op) == "steps":
                self._define_function(op)
        if target == "webServer":
            self._emit_webserver_entry()
        return self.module

    def _emit_webserver_entry(self) -> None:
        """APP-RUN-5: synthesize the `webServer` entry as an i32() function named
        after the project entry (jit_run/build_executable call it). It builds the
        route table (parallel method/path/handler arrays — handlers are the
        lowered `int(request,response)` ops) and calls ss_http_serve_routes, which
        assembles the SSHttpServerConfig and blocks in the server loop."""
        servers = self.program.of_kind("webServer")
        ws = next((s for s in servers if s.name == self.entry_name),
                  servers[0] if servers else None)
        if ws is None:
            raise EavError("webServer target has no webServer entity (README §14)")
        i8p = ir.IntType(8).as_pointer()
        i8pp = i8p.as_pointer()
        i32 = ir.IntType(32)
        def _unquote(tok):
            return tok[1:-1] if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"' else tok
        host_row, port_row = ws.fact("host"), ws.fact("port")
        host = _unquote(host_row.payload[0]) if host_row and host_row.payload else "127.0.0.1"
        port = int(port_row.payload[0]) if port_row and port_row.payload else 8080
        routes = [r.payload for r in ws.facts("route") if len(r.payload) >= 3]
        n = len(routes)
        fn = ir.Function(self.module, ir.FunctionType(i32, []), name=self.entry_name)
        b = ir.IRBuilder(fn.append_basic_block("entry"))
        methods = b.alloca(ir.ArrayType(i8p, n))
        paths = b.alloca(ir.ArrayType(i8p, n))
        handlers = b.alloca(ir.ArrayType(i8p, n))
        for i, payload in enumerate(routes):
            method, path, handler_name = payload[0], _unquote(payload[1]), payload[2]
            hfn = self.functions.get(handler_name)
            if hfn is None:
                raise EavError(
                    f"webServer {ws.name!r} route handler {handler_name!r} is not a "
                    "defined operation (README §14)", ws.line)
            idx = [i32(0), i32(i)]
            b.store(self.global_string(method.encode("utf-8") + b"\x00"),
                    b.gep(methods, idx))
            b.store(self.global_string(path.encode("utf-8") + b"\x00"),
                    b.gep(paths, idx))
            b.store(b.bitcast(hfn, i8p), b.gep(handlers, idx))
        r = b.call(self.runtime("ss_http_serve_routes"),
                   [self.global_string(host.encode("utf-8") + b"\x00"),
                    i32(port), i32(n),
                    b.bitcast(methods, i8pp), b.bitcast(paths, i8pp),
                    b.bitcast(handlers, i8pp)])
        b.ret(r)

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
            if op.fact("outParam") is not None:
                # WS3-016 FFI out-param ABI: the C symbol writes the result
                # through a trailing pointer and returns an i32 status (0 = ok).
                # `int symbol(in..., T* out)` instead of `T symbol(in...)`. This
                # is the seam C APIs that return through out-params (sqlite/http/
                # …) bind through — the value never crosses by-value.
                sig = ir.FunctionType(ir.IntType(32), params + [ret.as_pointer()])
            else:
                sig = ir.FunctionType(ret, params)
            return ir.Function(self.module, sig, name=symbol)
        fn = ir.Function(self.module, ir.FunctionType(ret, params), name=op.name)
        for param, in_row in zip(fn.args, op.facts("in")):
            param.name = in_row.payload[0]
        return fn

    # -- body --
    def _compute_recursive_ops(self) -> set:
        """The set of user operations that can reach themselves through the
        call graph (direct or mutual recursion). Only these are instrumented
        with the WS1-131 depth guard, so non-recursive ops pay nothing."""
        ops = {n for n in self.program.order
               if self.program.entities[n].kind in ("operation", "function")}
        graph: dict[str, set] = {n: set() for n in ops}
        for cn in self.program.order:
            c = self.program.entities[cn]
            if c.kind not in ("call", "task"):
                continue
            owner, inv = c.fact("in"), c.fact("invokes")
            if owner and owner.payload and inv and inv.payload:
                o, t = owner.payload[0], inv.payload[0]
                if o in graph and t in ops:
                    graph[o].add(t)
        recursive: set = set()
        for start in graph:
            seen, stack = set(), list(graph[start])
            while stack:
                node = stack.pop()
                if node == start:
                    recursive.add(start)
                    break
                if node not in seen:
                    seen.add(node)
                    stack.extend(graph.get(node, ()))
        return recursive

    def _depth_counter(self):
        """The shared `__ss_call_depth` global backing the recursion guard."""
        if getattr(self, "_depth_gv_cache", None) is None:
            i64 = ir.IntType(64)
            gv = ir.GlobalVariable(self.module, i64, name="__ss_call_depth")
            gv.linkage = "internal"
            gv.initializer = ir.Constant(i64, 0)
            self._depth_gv_cache = gv
        return self._depth_gv_cache

    # -- R-039 monomorphizing generics --
    @staticmethod
    def _mangle(name: str, typeargs: tuple) -> str:
        """Stable LLVM name for a generic instantiation, e.g. genId__Int64."""
        return name + "".join("__" + t for t in typeargs)

    @staticmethod
    def _typeparam_names(op: Entity) -> list:
        return [r.payload[0] for r in op.facts("typeParam") if r.payload]

    def _infer_typeargs(self, gen: Entity, call: Entity) -> tuple:
        """Bind each `typeParam` of a generic op from the concrete type of the
        call arg in the slot whose declared param type is that parameter."""
        tps = self._typeparam_names(gen)
        in_type = {r.payload[0]: r.payload[1]
                   for r in gen.facts("in") if len(r.payload) >= 2}
        arg_type = {a.payload[0]: a.payload[1]
                    for a in call.facts("arg") if len(a.payload) >= 2}
        binding: dict = {}
        for slot, ptype in in_type.items():
            if ptype in tps and slot in arg_type:
                binding[ptype] = arg_type[slot]
        return tuple(binding.get(t, "Int64") for t in tps)

    def _make_mono_clone(self, gen: Entity, typeargs: tuple) -> Entity:
        """A concrete copy of a generic op with each `typeParam` substituted by
        its concrete type in every row payload (in/out/let/return type positions);
        the `typeParam` rows themselves are dropped."""
        sub = dict(zip(self._typeparam_names(gen), typeargs))
        mangled = self._mangle(gen.name, typeargs)
        clone = Entity(name=mangled, kind="operation", line=gen.line)
        for r in gen.rows:
            if r.predicate == "typeParam":
                continue
            new_payload = [sub.get(tok, tok) for tok in r.payload]
            clone.rows.append(
                Row(mangled, r.predicate, new_payload, r.line, label=r.label))
        return clone

    def _define_function(self, op: Entity) -> None:
        fn = self.functions[op.name]
        if not hasattr(self, "_recursive_ops"):
            self._recursive_ops = self._compute_recursive_ops()
        let_mut = {
            r.payload[0]: r.payload[1]
            for r in op.facts("let")
            if len(r.payload) >= 2 and r.payload[1] in ("mutable", "immutable")
        }
        sym: dict[str, tuple] = {}
        for param, in_row in zip(fn.args, op.facts("in")):
            sym[in_row.payload[0]] = ("val", param)

        # Per-op binding → declared-type-name map (in / let / owned-call out), so
        # `ifVariant` can resolve a value's exact enum type (e.g. a generic-enum
        # instantiation) rather than guessing from the variant name.
        self._binding_types = {}
        for r in op.facts("in"):
            if len(r.payload) >= 2:
                self._binding_types[r.payload[0]] = r.payload[1]
        for r in op.facts("let"):
            if len(r.payload) >= 3:
                self._binding_types[r.payload[0]] = r.payload[2]
        for cn in self.program.order:
            c = self.program.entities[cn]
            if c.kind in ("call", "task"):
                owner = c.fact("in")
                o = c.fact("out")
                if (owner and owner.payload and owner.payload[0] == op.name
                        and o and len(o.payload) >= 2):
                    self._binding_types[o.payload[0]] = o.payload[1]

        entry = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry)

        # WS1-131 recursion-depth guard: a statically-recursive op bumps the
        # shared depth counter on entry and traps (SSR0013) past the limit;
        # _emit_defers decrements it on every exit. Non-recursive ops skip this.
        self._depth_gv = None
        if op.name in self._recursive_ops:
            i64 = ir.IntType(64)
            gv = self._depth_counter()
            depth = builder.add(builder.load(gv), ir.Constant(i64, 1))
            builder.store(depth, gv)
            over = builder.icmp_signed(">", depth,
                                       ir.Constant(i64, EAV_RECURSION_LIMIT))
            bad = fn.append_basic_block("recursionLimit")
            ok = fn.append_basic_block("recursionOk")
            builder.cbranch(over, bad, ok)
            tb = ir.IRBuilder(bad)
            self._emit_panic(
                tb, "SSR0013", "recursion-depth-exceeded",
                f"call depth exceeded the limit of {EAV_RECURSION_LIMIT} "
                f"(likely unbounded recursion)", op.name, op.line, depth,
                ir.Constant(i64, EAV_RECURSION_LIMIT))
            tb.unreachable()
            builder = ir.IRBuilder(ok)
            self._depth_gv = gv

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
        # README §12 / WS1-085: a bare reference to a module-storage constant
        # reads the module global (e.g. a `let` initialized from a default const).
        ms = getattr(self, "module_storage", {})
        if tok in ms:
            ref = ms[tok][0]
            return builder.load(ref) if isinstance(ref, ir.GlobalVariable) else ref
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

    def _entry_alloca(self, builder, ir_ty, name):
        """Allocate a zero-initialized slot at the top of the function's entry
        block — which dominates every other block. Required for an owned handle
        whose deferred cleanup is re-emitted at multiple return points (README
        §15.6): the creation-block SSA value need not dominate those returns, but
        a load from an entry slot always does. The zero init makes a cleanup that
        runs before creation (any path) release a null handle harmlessly."""
        entry = builder.function.blocks[0]
        tmp = ir.IRBuilder()
        if entry.instructions:
            tmp.position_before(entry.instructions[0])
        else:
            tmp.position_at_end(entry)
        slot = tmp.alloca(ir_ty, name=name)
        tmp.store(ir.Constant(
            ir_ty, None if isinstance(ir_ty, ir.PointerType) else 0), slot)
        return slot

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
        if pred == "allocateIn":
            # WS1-112: `allocateIn <region> <var> <Type>` allocates a slab in the
            # region (single-thread: a malloc), binds <var> to the pointer, and
            # tracks it under the region so releaseRegion frees the whole arena.
            region, var = p[0], p[1]
            slab = builder.call(self.runtime("malloc"),
                                [ir.Constant(ir.IntType(64), 8)])
            sym[var] = ("val", slab)
            sym.setdefault("__rgn_" + region, []).append(slab)
            return builder
        if pred == "releaseRegion":
            # WS1-112: free every slab allocated in the region (arena free-once).
            region = p[0]
            for slab in sym.get("__rgn_" + region, []):
                builder.call(self.runtime("free"), [slab])
            sym["__rgn_" + region] = []
            return builder
        if pred == "readShared":
            # WS2-083: `readShared <var> <Type> <state> protectedBy <token>` loads
            # the shared-state global into a fresh immutable local (guard is a
            # single-thread no-op).
            var, state = p[0], p[2]
            gv, typ = self.module_storage[state]
            sym[var] = ("val", builder.load(gv))
            return builder
        if pred == "setShared":
            # WS2-083: `setShared <state> <value> protectedBy <token>` stores into
            # the shared-state global.
            state, value_tok = p[0], p[1]
            gv, typ = self.module_storage[state]
            builder.store(self._resolve(value_tok, typ, builder, sym), gv)
            return builder
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
        ss33.8). Called immediately before each return / fallthrough exit. For a
        recursion-guarded op it also decrements the WS1-131 depth counter, so the
        counter tracks live depth across every exit path."""
        if getattr(self, "_depth_gv", None) is not None:
            i64 = ir.IntType(64)
            dec = builder.sub(builder.load(self._depth_gv), ir.Constant(i64, 1))
            builder.store(dec, self._depth_gv)
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
        # `return nil [<err>]` on a Result/handle op: the function's IR result is
        # its OK type, so yield that type's null/zero sentinel. (Returning the Err
        # value would be a different IR type than the result; the error is
        # detected out-of-band — the caller null-checks the handle.)
        if p[0] == "nil":
            builder.ret(ir.Constant(
                ret_ty, None if isinstance(ret_ty, ir.PointerType) else 0))
            return builder
        builder.ret(self._resolve(p[0], type_hint, builder, sym))
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
            # README ss13/ss10.5: `branch ifVariant VALUE VARIANT [bind P] goto L`
            # narrows an enum value. For a plain enum it compares the i32
            # discriminant; for a data enum (R-054) it compares the tag of the
            # {i32 tag, payload} tagged union and, with `bind P`, extracts the
            # payload into P for the matched arm.
            value_tok, variant = p[1], p[2]
            bind_name = p[p.index("bind") + 1] if "bind" in p else None
            label = p[p.index("goto") + 1]
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
            # Prefer the value's declared enum type (so a generic-enum
            # instantiation resolves to its concrete payload type); fall back to
            # the variant-name match for a plain enum.
            vtype = getattr(self, "_binding_types", {}).get(value_tok)
            vent = self.program.entities.get(vtype) if vtype else None
            enum_ent = vent if (vent is not None and vent.kind == "enum") else matches[0]
            variants = self._enum_variant_names(enum_ent)
            disc = self._enum_repr_map(enum_ent).get(variant, variants.index(variant))
            pt = self._enum_payload_type(enum_ent)
            lv = self._resolve(value_tok, enum_ent.name, builder, sym)
            if pt is not None:
                if bind_name is not None:
                    sym[bind_name] = ("val", builder.extract_value(lv, 1))
                cond = builder.icmp_signed(
                    "==", builder.extract_value(lv, 0),
                    ir.Constant(ir.IntType(32), disc))
            else:
                cond = builder.icmp_signed(
                    "==", lv, ir.Constant(ir.IntType(32), disc))
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

    def _concat(self, builder, left, right, line=0):
        """Heap-concatenate two NUL-terminated i8* strings (README ss30.2.2).
        R-136: the malloc result is null-guarded before the strcpy/strcat so an
        OOM is a structured trap (SSR0022), not a write through a null pointer."""
        la = builder.call(self.runtime("strlen"), [left])
        lb = builder.call(self.runtime("strlen"), [right])
        total = builder.add(builder.add(la, lb), ir.Constant(ir.IntType(64), 1))
        buf = builder.call(self.runtime("malloc"), [total])
        self._guard_alloc(builder, buf, "string.concat", line)  # R-136
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
                    val = builder.call(self.runtime("ss_http_html_escape_str"), [val])
                piece = val
            result = (piece if result is None
                      else self._concat(builder, result, piece, call.line))
        return result if result is not None else self.global_string(b"\x00")

    # --- standard.test harness (README §35; std/standard.test.sem) ---------
    # A built-in assertion + reporting surface backing the `test.*` namespace.
    # Two internal module globals tally pass/fail across a program run; each
    # assertion prints a PASS/FAIL line and `test.summary` prints the totals and
    # returns the failure count as a process ExitCode.
    def _test_counter(self, which):
        key = "__test_" + which
        g = self.module.globals.get(key)
        if g is None:
            g = ir.GlobalVariable(self.module, ir.IntType(64), key)
            g.linkage = "internal"
            g.initializer = ir.Constant(ir.IntType(64), 0)
        return g

    def _test_tally(self, builder, eq):
        """`eq` is an i1: bump the passed/failed counters and return the
        PASS/FAIL status string (i8*) for the report line."""
        i64 = ir.IntType(64)
        passG, failG = self._test_counter("passed"), self._test_counter("failed")
        builder.store(builder.add(builder.load(passG), builder.zext(eq, i64)), passG)
        not_eq = builder.xor(eq, ir.Constant(ir.IntType(1), 1))
        builder.store(builder.add(builder.load(failG), builder.zext(not_eq, i64)), failG)
        return builder.select(eq, self.global_string(b"PASS\x00"),
                              self.global_string(b"FAIL\x00"))

    def _emit_test_call(self, target, builder, arg):
        """Lower a `test.*` harness call; returns the call result value."""
        i32 = ir.IntType(32)
        if target == "test.assertEqualInt64":
            i64 = ir.IntType(64)
            exp, act = arg("expected", "Int64"), arg("actual", "Int64")
            # a Bool/narrow integer (e.g. a comparison result) widens to i64 so it
            # compares and prints the same way console.writeIntegerLine shows it.
            if isinstance(exp.type, ir.IntType) and exp.type.width < 64:
                exp = builder.zext(exp, i64)
            if isinstance(act.type, ir.IntType) and act.type.width < 64:
                act = builder.zext(act, i64)
            status = self._test_tally(builder, builder.icmp_signed("==", exp, act))
            fmt = self.global_string(b"%s  %s  (expected %lld, actual %lld)\n\x00")
            return builder.call(self.runtime("printf"),
                                [fmt, status, arg("name", "String"), exp, act])
        if target == "test.assertEqualFloat64":
            exp, act = arg("expected", "Float64"), arg("actual", "Float64")
            status = self._test_tally(builder, builder.fcmp_ordered("==", exp, act))
            fmt = self.global_string(b"%s  %s  (expected %g, actual %g)\n\x00")
            return builder.call(self.runtime("printf"),
                                [fmt, status, arg("name", "String"), exp, act])
        if target == "test.assertTrue":
            status = self._test_tally(builder, arg("value", "Bool"))
            fmt = self.global_string(b"%s  %s\n\x00")
            return builder.call(self.runtime("printf"),
                                [fmt, status, arg("name", "String")])
        if target == "test.assertFalse":
            cond = arg("value", "Bool")
            not_cond = builder.xor(cond, ir.Constant(ir.IntType(1), 1))
            status = self._test_tally(builder, not_cond)  # passes iff cond is false
            fmt = self.global_string(b"%s  %s  (expected false)\n\x00")
            return builder.call(self.runtime("printf"),
                                [fmt, status, arg("name", "String")])
        if target == "test.assertNotEqualInt64":
            i64 = ir.IntType(64)
            exp, act = arg("expected", "Int64"), arg("actual", "Int64")
            if isinstance(exp.type, ir.IntType) and exp.type.width < 64:
                exp = builder.zext(exp, i64)
            if isinstance(act.type, ir.IntType) and act.type.width < 64:
                act = builder.zext(act, i64)
            status = self._test_tally(builder, builder.icmp_signed("!=", exp, act))
            fmt = self.global_string(b"%s  %s  (expected != %lld, actual %lld)\n\x00")
            return builder.call(self.runtime("printf"),
                                [fmt, status, arg("name", "String"), exp, act])
        if target == "test.assertEqualText":
            exp, act = arg("expected", "String"), arg("actual", "String")
            cmp = builder.call(self.runtime("strcmp"), [exp, act])
            status = self._test_tally(builder, builder.icmp_signed("==", cmp,
                                                                   ir.Constant(i32, 0)))
            fmt = self.global_string(b'%s  %s  (expected "%s", actual "%s")\n\x00')
            return builder.call(self.runtime("printf"),
                                [fmt, status, arg("name", "String"), exp, act])
        if target == "test.assertNotEqualText":
            exp, act = arg("expected", "String"), arg("actual", "String")
            cmp = builder.call(self.runtime("strcmp"), [exp, act])
            status = self._test_tally(builder, builder.icmp_signed("!=", cmp,
                                                                   ir.Constant(i32, 0)))
            fmt = self.global_string(b'%s  %s  (expected != "%s", actual "%s")\n\x00')
            return builder.call(self.runtime("printf"),
                                [fmt, status, arg("name", "String"), exp, act])
        if target == "test.summary":
            passG, failG = self._test_counter("passed"), self._test_counter("failed")
            p, f = builder.load(passG), builder.load(failG)
            fmt = self.global_string(b"---- %lld passed, %lld failed ----\n\x00")
            builder.call(self.runtime("printf"), [fmt, p, f])
            return builder.trunc(f, i32)  # exit code = number of failures
        raise EavError(f"unknown test target {target!r}")

    def _runtime_extern(self, name, ret_ty, arg_types):
        """Get-or-declare a cached extern `name` with the given signature. The
        runtime-intrinsic families (net/event/gui/http/sqlite/json/bcrypt/log/c)
        all bind their native/shim symbols through this."""
        fn = self._runtime.get(name)
        if fn is None:
            fn = ir.Function(self.module,
                             ir.FunctionType(ret_ty, list(arg_types)), name=name)
            self._runtime[name] = fn
        return fn

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
        elif target.startswith("test.assert") or target == "test.summary":
            result = self._emit_test_call(target, builder, arg)
        elif target == "console.writeFloatLine":
            fmt = self.global_string(b"%g\n\x00")
            val = arg("value", "Float64")
            result = builder.call(self.runtime("printf"), [fmt, val])
        elif target.startswith("buffer."):
            # WS1-119: a length-carrying buffer laid out as [i64 len][n bytes][1
            # scratch]. Access is bounds-checked: an out-of-bounds index sets the
            # fallible error (`err`) and is redirected to the scratch byte, so a
            # bad index is a BufferBoundsError, never an out-of-bounds load/store.
            i8 = ir.IntType(8)
            i64 = ir.IntType(64)

            def _load_len(buf):
                return builder.load(builder.bitcast(buf, i64.as_pointer()))

            def _safe_off(buf, idx):
                length = _load_len(buf)
                oob = builder.or_(builder.icmp_signed(">=", idx, length),
                                  builder.icmp_signed("<", idx, ir.Constant(i64, 0)))
                scratch = builder.add(ir.Constant(i64, 8), length)  # the scratch byte
                inb = builder.add(ir.Constant(i64, 8), idx)
                return oob, builder.select(oob, scratch, inb)

            if target == "buffer.create":
                n = arg("size", "Int64")
                self._guard_buffer_size(builder, n, target, call.line)  # R-135
                total = builder.add(n, ir.Constant(i64, 9))  # 8 len + n + 1 scratch
                ptr = builder.call(self.runtime("malloc"), [total])
                self._guard_alloc_nonnull(builder, ptr, target, call.line)  # R-135
                builder.store(n, builder.bitcast(ptr, i64.as_pointer()))
                result = ptr
            elif target == "buffer.length":
                result = _load_len(arg("buffer", "OpaquePointer"))
            elif target == "buffer.get":
                buf = arg("buffer", "OpaquePointer")
                err, off = _safe_off(buf, arg("index", "Int64"))
                result = builder.load(builder.gep(buf, [off]))  # i8 (Byte)
            elif target == "buffer.set":
                buf = arg("buffer", "OpaquePointer")
                err, off = _safe_off(buf, arg("index", "Int64"))
                val = arg("value", "Byte")
                if val.type != i8:
                    val = builder.trunc(val, i8) if val.type.width > 8 else builder.zext(val, i8)
                builder.store(val, builder.gep(buf, [off]))
                result = ir.Constant(ir.IntType(32), 0)
            elif target == "buffer.slice":
                buf = arg("buffer", "OpaquePointer")
                start = arg("start", "Int64")
                length = arg("length", "Int64")
                buflen = _load_len(buf)
                end = builder.add(start, length)
                err = builder.or_(builder.icmp_signed(">", end, buflen),
                                  builder.icmp_signed("<", start, ir.Constant(i64, 0)))
                off = builder.select(err, builder.add(ir.Constant(i64, 8), buflen),
                                     builder.add(ir.Constant(i64, 8), start))
                result = builder.gep(buf, [off])  # a view pointer into the buffer
            else:
                result = ir.Constant(ir.IntType(32), 0)
        elif target.startswith("list."):
            # R-061 collections runtime: a growable Int64 list behind a STABLE
            # handle. Header (malloc'd, never moves): i64[3] = [count, capacity,
            # dataPtrBits]. Data (malloc'd, realloc'd on growth): capacity × i64.
            # The handle is the header pointer, so append's realloc of the data
            # buffer never dangles the caller's handle. list.get is bounds-checked
            # (OOB sets the fallible ListError `err` and reads a safe in-bounds
            # slot — never an out-of-bounds load).
            i64 = ir.IntType(64)
            i8p = ir.IntType(8).as_pointer()
            i64p = i64.as_pointer()
            _INIT_CAP = 4

            def _slot(b, h, n):  # &header[n]
                return b.gep(b.bitcast(h, i64p), [ir.Constant(i64, n)])

            if target == "list.create":
                hdr = builder.call(self.runtime("malloc"), [ir.Constant(i64, 24)])
                self._guard_alloc(builder, hdr, "list.create", call.line)  # R-137
                builder.store(ir.Constant(i64, 0), _slot(builder, hdr, 0))
                builder.store(ir.Constant(i64, _INIT_CAP), _slot(builder, hdr, 1))
                data = builder.call(self.runtime("malloc"),
                                    [ir.Constant(i64, _INIT_CAP * 8)])
                self._guard_alloc(builder, data, "list.create", call.line)  # R-137
                builder.store(builder.ptrtoint(data, i64), _slot(builder, hdr, 2))
                result = hdr
            elif target == "list.length":
                h = arg("list", "OpaquePointer")
                result = builder.load(_slot(builder, h, 0))
            elif target == "list.append":
                h = arg("list", "OpaquePointer")
                v = arg("value", "Int64")
                count = builder.load(_slot(builder, h, 0))
                cap = builder.load(_slot(builder, h, 1))
                fn = builder.function
                grow_bb = fn.append_basic_block("listGrow")
                cont_bb = fn.append_basic_block("listAppendCont")
                builder.cbranch(builder.icmp_signed("==", count, cap),
                                grow_bb, cont_bb)
                gb = ir.IRBuilder(grow_bb)
                newcap = gb.mul(cap, ir.Constant(i64, 2))
                olddata = gb.inttoptr(gb.load(_slot(gb, h, 2)), i8p)
                newdata = gb.call(self.runtime("realloc"),
                                  [olddata, gb.mul(newcap, ir.Constant(i64, 8))])
                self._guard_alloc(gb, newdata, "list.append", call.line)  # R-137
                gb.store(newcap, _slot(gb, h, 1))
                gb.store(gb.ptrtoint(newdata, i64), _slot(gb, h, 2))
                gb.branch(cont_bb)
                builder.position_at_end(cont_bb)
                data = builder.inttoptr(builder.load(_slot(builder, h, 2)), i64p)
                builder.store(v, builder.gep(data, [count]))
                builder.store(builder.add(count, ir.Constant(i64, 1)),
                              _slot(builder, h, 0))
                result = ir.Constant(ir.IntType(32), 0)
            elif target == "list.get":
                h = arg("list", "OpaquePointer")
                idx = arg("index", "Int64")
                count = builder.load(_slot(builder, h, 0))
                oob = builder.or_(
                    builder.icmp_signed("<", idx, ir.Constant(i64, 0)),
                    builder.icmp_signed(">=", idx, count))
                safe = builder.select(oob, ir.Constant(i64, 0), idx)
                data = builder.inttoptr(builder.load(_slot(builder, h, 2)), i64p)
                result = builder.load(builder.gep(data, [safe]))
                err = oob
            elif target == "list.release":
                h = arg("list", "OpaquePointer")
                data = builder.inttoptr(builder.load(_slot(builder, h, 2)), i8p)
                builder.call(self.runtime("free"), [data])
                builder.call(self.runtime("free"), [h])
                result = ir.Constant(ir.IntType(32), 0)
            else:
                result = ir.Constant(ir.IntType(32), 0)
        elif target.startswith("map."):
            # R-061 collections runtime: a String->Int64 map. Same stable-handle
            # header as the list (i64[3] = [count, capacity, dataPtrBits]) but each
            # entry is a pair [keyPtrBits, value] (16 bytes). Lookup is a linear
            # strcmp scan in **insertion order** (deterministic, X-094) — fine for
            # the demo scale, and the insertion-order layout is what `each` will
            # iterate. map.get of a missing key sets the fallible MapError (`err`).
            i64 = ir.IntType(64)
            i32 = ir.IntType(32)
            i8p = ir.IntType(8).as_pointer()
            i64p = i64.as_pointer()
            c1, c2 = ir.Constant(i64, 1), ir.Constant(i64, 2)
            _INIT_CAP = 4

            def _slot(b, h, n):
                return b.gep(b.bitcast(h, i64p), [ir.Constant(i64, n)])

            def _map_find(h, key):
                # Returns (found:i1, idx:i64, data:i64*); builder ends at `done`.
                # On a hit idx is the entry index; on a miss idx == count.
                fn = builder.function
                found_p = builder.alloca(ir.IntType(1))
                idx_p = builder.alloca(i64)
                builder.store(ir.Constant(ir.IntType(1), 0), found_p)
                builder.store(ir.Constant(i64, 0), idx_p)
                count = builder.load(_slot(builder, h, 0))
                data = builder.inttoptr(builder.load(_slot(builder, h, 2)), i64p)
                cond = fn.append_basic_block("mapCond")
                body = fn.append_basic_block("mapBody")
                matchb = fn.append_basic_block("mapMatch")
                nextb = fn.append_basic_block("mapNext")
                done = fn.append_basic_block("mapDone")
                builder.branch(cond)
                cb = ir.IRBuilder(cond)
                i = cb.load(idx_p)
                cb.cbranch(cb.icmp_signed(">=", i, count), done, body)
                bb = ir.IRBuilder(body)
                kp = bb.inttoptr(
                    bb.load(bb.gep(data, [bb.mul(i, c2)])), i8p)
                cmp = bb.call(self.runtime("strcmp"), [key, kp])
                bb.cbranch(bb.icmp_signed("==", cmp, ir.Constant(i32, 0)),
                           matchb, nextb)
                mb = ir.IRBuilder(matchb)
                mb.store(ir.Constant(ir.IntType(1), 1), found_p)
                mb.branch(done)
                nb = ir.IRBuilder(nextb)
                nb.store(nb.add(i, c1), idx_p)
                nb.branch(cond)
                builder.position_at_end(done)
                return builder.load(found_p), builder.load(idx_p), data

            if target == "map.create":
                hdr = builder.call(self.runtime("malloc"), [ir.Constant(i64, 24)])
                self._guard_alloc(builder, hdr, "map.create", call.line)  # R-137
                builder.store(ir.Constant(i64, 0), _slot(builder, hdr, 0))
                builder.store(ir.Constant(i64, _INIT_CAP), _slot(builder, hdr, 1))
                data = builder.call(self.runtime("malloc"),
                                    [ir.Constant(i64, _INIT_CAP * 16)])
                self._guard_alloc(builder, data, "map.create", call.line)  # R-137
                builder.store(builder.ptrtoint(data, i64), _slot(builder, hdr, 2))
                result = hdr
            elif target == "map.size":
                h = arg("map", "OpaquePointer")
                result = builder.load(_slot(builder, h, 0))
            elif target == "map.get":
                h = arg("map", "OpaquePointer")
                key = arg("key", "String")
                found, idx, data = _map_find(h, key)
                safe = builder.select(found, idx, ir.Constant(i64, 0))
                result = builder.load(
                    builder.gep(data, [builder.add(builder.mul(safe, c2), c1)]))
                err = builder.xor(found, ir.Constant(ir.IntType(1), 1))
            elif target == "map.put":
                h = arg("map", "OpaquePointer")
                key = arg("key", "String")
                value = arg("value", "Int64")
                found, idx, data = _map_find(h, key)
                fn = builder.function
                rep_p = builder.alloca(i32)
                upd = fn.append_basic_block("mapPutUpdate")
                ins = fn.append_basic_block("mapPutInsert")
                pdone = fn.append_basic_block("mapPutDone")
                builder.cbranch(found, upd, ins)
                ub = ir.IRBuilder(upd)
                ub.store(value,
                         ub.gep(data, [ub.add(ub.mul(idx, c2), c1)]))
                ub.store(ir.Constant(i32, 1), rep_p)
                ub.branch(pdone)
                ib = ir.IRBuilder(ins)
                count = ib.load(_slot(ib, h, 0))
                cap = ib.load(_slot(ib, h, 1))
                grow = fn.append_basic_block("mapGrow")
                afterg = fn.append_basic_block("mapAfterGrow")
                ib.cbranch(ib.icmp_signed("==", count, cap), grow, afterg)
                gb = ir.IRBuilder(grow)
                newcap = gb.mul(cap, c2)
                olddata = gb.inttoptr(gb.load(_slot(gb, h, 2)), i8p)
                newdata = gb.call(self.runtime("realloc"),
                                  [olddata, gb.mul(newcap, ir.Constant(i64, 16))])
                self._guard_alloc(gb, newdata, "map.put", call.line)  # R-137
                gb.store(newcap, _slot(gb, h, 1))
                gb.store(gb.ptrtoint(newdata, i64), _slot(gb, h, 2))
                gb.branch(afterg)
                ab = ir.IRBuilder(afterg)
                data2 = ab.inttoptr(ab.load(_slot(ab, h, 2)), i64p)
                base = ab.mul(count, c2)
                ab.store(ab.ptrtoint(key, i64), ab.gep(data2, [base]))
                ab.store(value, ab.gep(data2, [ab.add(base, c1)]))
                ab.store(ab.add(count, c1), _slot(ab, h, 0))
                ab.store(ir.Constant(i32, 0), rep_p)
                ab.branch(pdone)
                builder.position_at_end(pdone)
                result = builder.load(rep_p)
            elif target == "map.release":
                h = arg("map", "OpaquePointer")
                data = builder.inttoptr(builder.load(_slot(builder, h, 2)), i8p)
                builder.call(self.runtime("free"), [data])
                builder.call(self.runtime("free"), [h])
                result = ir.Constant(ir.IntType(32), 0)
            else:
                result = ir.Constant(ir.IntType(32), 0)
        elif target in ("math.divideInt64", "math.moduloInt64"):
            left = arg("left", "Int64")
            right = arg("right", "Int64")
            kind_label = ("divide-by-zero" if target == "math.divideInt64"
                          else "modulo-by-zero")
            owner_row = call.fact("in")
            op_name = (owner_row.payload[0] if owner_row and owner_row.payload
                       else call.name)
            self._guard_div_zero(builder, right, left, kind_label, op_name, call.line)
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
            # These are binary: double (double, double). Declare with the full
            # signature so minnum/maxnum/copysign don't get a 1-arg declaration
            # that LLVM rejects as an incompatible intrinsic signature.
            dbl = ir.DoubleType()
            fn = self.module.declare_intrinsic(
                _FLOAT_BINARY_INTRIN[target], [dbl],
                ir.FunctionType(dbl, [dbl, dbl]))
            result = builder.call(fn, [arg("left", "Float64"), arg("right", "Float64")])
        elif target in _INT_UNARY_INTRIN:
            i64 = ir.IntType(64)
            if target == "math.popcountInt64":
                # llvm.ctpop.i64 : i64 (i64)
                fn = self.module.declare_intrinsic(
                    _INT_UNARY_INTRIN[target], [i64],
                    ir.FunctionType(i64, [i64]))
                result = builder.call(fn, [arg("value", "Int64")])
            else:
                # llvm.ctlz/cttz.i64 : i64 (i64, i1 is_zero_poison) — the second
                # operand is part of the intrinsic signature, so the declaration
                # must include it or LLVM asserts on an arg-count mismatch.
                i1 = ir.IntType(1)
                fn = self.module.declare_intrinsic(
                    _INT_UNARY_INTRIN[target], [i64],
                    ir.FunctionType(i64, [i64, i1]))
                result = builder.call(fn, [arg("value", "Int64"), ir.Constant(i1, 0)])
        elif target in _MATH_COMPUTED:
            result = self._emit_math_computed(target, arg, builder)
        elif target.startswith("compare."):
            result = self._emit_compare(target, args, builder, sym, call)
        elif target.startswith("convert.to"):
            result = self._emit_convert(target, args, builder, sym, call)
        elif target.startswith("decimal."):
            # R-067: Decimal/Money are scaled Int64 — fixed scale 2 (raw value is
            # the amount * 100). add/subtract/equal are scale-invariant integer
            # ops; multiply divides the raw product by 100 and divide scales the
            # dividend by 100, both truncating toward zero (sdiv). Overflow and
            # divide-by-zero set the fallible DecimalError flag (`err`) that
            # `branch ifError` consumes — never a silent wrap or UB.
            i64 = ir.IntType(64)
            hundred = ir.Constant(i64, 100)
            if target == "decimal.add":
                result, err = self._overflow_op("sadd", builder,
                                                arg("left", "Decimal"), arg("right", "Decimal"))
            elif target == "decimal.subtract":
                result, err = self._overflow_op("ssub", builder,
                                                arg("left", "Decimal"), arg("right", "Decimal"))
            elif target == "decimal.multiply":
                product, err = self._overflow_op("smul", builder,
                                                 arg("left", "Decimal"), arg("right", "Decimal"))
                result = builder.sdiv(product, hundred)  # rescale, toward zero
            elif target == "decimal.divide":
                dividend = arg("left", "Decimal")
                divisor = arg("right", "Decimal")
                scaled, overflow = self._overflow_op("smul", builder, dividend, hundred)
                is_zero = builder.icmp_signed("==", divisor, ir.Constant(i64, 0))
                # avoid UB: divide by 1 on the zero path; the err flag carries the
                # DecimalError so the result on that path is never observed.
                safe_divisor = builder.select(is_zero, ir.Constant(i64, 1), divisor)
                result = builder.sdiv(scaled, safe_divisor)
                err = builder.or_(is_zero, overflow)
            elif target == "decimal.equal":
                result = builder.icmp_signed("==", arg("left", "Decimal"), arg("right", "Decimal"))
            else:
                raise EavError(
                    f"decimal target {target!r} is not modeled by the code "
                    f"generator (R-067 lowers add/subtract/multiply/divide/equal)",
                    call.line)
        elif target == "string.concat":
            # README ss30.2.2: heap-concatenate two NUL-terminated strings.
            result = self._concat(builder, arg("left", "String"),
                                   arg("right", "String"), call.line)
        elif target == "html.render":
            # README ss16: render an htmlTemplate island, auto-escaping `{{holes}}`
            # by sink context. Split the template on holes and concat the literal
            # segments with the (escaped) hole values in order.
            result = self._emit_html_render(call, args, builder, sym)
        elif target == "net.fetchText":
            # APP-RUN-1: high-level HTTP-GET client. The arg is a record whose
            # `url` String field is fetched (ss_net_fetch_text, winsock GET); the
            # result is the call's `out` record with the fetched body in its
            # `body` field. Field names resolve by name (fallback: field 0), so
            # the compiler stays agnostic to the app's record naming.
            req_arg = args.get("request") or next(iter(args.values()), None)
            if req_arg is None:
                raise EavError(
                    f"call {call.name!r} to net.fetchText needs a request record arg",
                    call.line)
            req_val = self._resolve(req_arg.payload[2], req_arg.payload[1], builder, sym)
            req_ent = self.program.entities.get(req_arg.payload[1])
            _, req_fields = self._record_layout(req_ent)
            url_idx = req_fields.index("url") if "url" in req_fields else 0
            url_val = builder.extract_value(req_val, url_idx)
            body = builder.call(self.runtime("ss_net_fetch_text"), [url_val])
            out_row = call.fact("out")
            resp_ent = self.program.entities.get(out_row.payload[1]) if out_row else None
            if resp_ent is None:
                raise EavError(
                    f"call {call.name!r} to net.fetchText needs an `out` response record",
                    call.line)
            resp_struct_t, resp_fields = self._record_layout(resp_ent)
            body_idx = resp_fields.index("body") if "body" in resp_fields else 0
            result = builder.insert_value(
                ir.Constant(resp_struct_t, ir.Undefined), body, body_idx)
        elif target == "net.freeTextBody":
            # Release a heap-owned response body copy (ss_net_free_text -> free).
            body_arg = args.get("body") or next(iter(args.values()), None)
            if body_arg is not None:
                body_val = self._resolve(body_arg.payload[2], body_arg.payload[1], builder, sym)
                builder.call(self.runtime("ss_net_free_text"), [body_val])
        elif target == "event.openProcessStream":
            # APP-RUN-3: in-process pub/sub (ss_event runtime). Handles + ids are
            # Int64 (OpaquePointer); receive ignores its out-buffer args.
            result = builder.call(self.runtime("ss_event_open_stream"),
                                  [arg("streamName", "String"), arg("queueCapacity", "Int64")])
        elif target == "event.subscribeStream":
            result = builder.call(self.runtime("ss_event_subscribe"),
                                  [arg("stream", "OpaquePointer"),
                                   arg("eventType", "String"), arg("eventKey", "String")])
        elif target == "event.appendEvent":
            result = builder.call(self.runtime("ss_event_append"),
                                  [arg("stream", "OpaquePointer"), arg("eventType", "String"),
                                   arg("eventKey", "String"), arg("payloadJson", "String")])
        elif target == "event.receiveEvent":
            result = builder.call(self.runtime("ss_event_receive"),
                                  [arg("subscription", "OpaquePointer")])
        elif target == "event.acknowledgeEvent":
            builder.call(self.runtime("ss_event_ack"),
                         [arg("subscription", "OpaquePointer"), arg("eventId", "Int64")])
        elif target == "event.closeSubscription":
            builder.call(self.runtime("ss_event_close_subscription"),
                         [arg("subscription", "OpaquePointer")])
        elif target == "event.closeStream":
            builder.call(self.runtime("ss_event_close_stream"),
                         [arg("stream", "OpaquePointer")])
        elif target.startswith("gui."):
            # APP-RUN-4: headless widget runtime. Resolve the call's args in
            # source order, derive the extern signature from their IR types + the
            # `out` type (void when discarded), and call the ss_widget_* stub.
            # Opaque handles are i64, GuiText is i8*, the GuiEventHandler resolves
            # to a function pointer (passed through; not fired headlessly).
            name = target[len("gui."):]
            sym_name = _gui_runtime_symbol(target)
            vals = [self._resolve(a.payload[2], a.payload[1], builder, sym)
                    for a in call.facts("arg")]
            # Fixed return type per gui.* — a given target is called both with
            # `out Int32` and with `discards`, so the extern signature must be
            # consistent (deriving it from a single call's out row mismatches the
            # other). Creators hand back an i64 handle, textBoxText an i8* String,
            # every other mutator/query a 0/-1 status int.
            if name.endswith("Create"):
                ret_ty = ir.IntType(64)
            elif name == "textBoxText":
                ret_ty = ir.IntType(8).as_pointer()
            else:
                ret_ty = ir.IntType(32)
            fn = self._runtime_extern(sym_name, ret_ty, [v.type for v in vals])
            r = builder.call(fn, vals)
            if call.fact("out") is not None:
                result = r
        elif target.startswith("http.") and target not in ("html.render",):
            # APP-RUN-5: request/response/multipart accessors over the legacy
            # ss_http_* runtime. Resolve args in order (handles are i64, names/
            # bodies i8*, status i32); fixed return type per family (getters ->
            # i8* String/bytes, *Length -> i64, response* -> i32 status) so the
            # extern signature is consistent across discard/capture call sites.
            name = target[len("http."):]
            sym_name = "ss_http_" + _camel_to_snake(name)
            vals = [self._resolve(a.payload[2], a.payload[1], builder, sym)
                    for a in call.facts("arg")]
            if name.endswith("Length") or name == "nowMillis":
                ret_ty = ir.IntType(64)                       # millis / byte counts
            elif (name.startswith("response") or name == "ensureDirectory"
                  or name == "valueIsEmpty"):
                ret_ty = ir.IntType(32)                       # status ints
            else:
                ret_ty = ir.IntType(8).as_pointer()           # request*/multipart* getters
            fn = self._runtime_extern(sym_name, ret_ty, [v.type for v in vals])
            r = builder.call(fn, vals)
            if call.fact("out") is not None:
                result = r
        elif target == "pointer.isNull":
            # APP-RUN-5/6: null-guard a nullable runtime read (a missing header /
            # query param / body comes back as a null pointer). True iff null.
            a0 = next(iter(call.facts("arg")), None)
            v = self._resolve(a0.payload[2], a0.payload[1], builder, sym)
            if isinstance(v.type, ir.PointerType):
                result = builder.icmp_unsigned("==", v, ir.Constant(v.type, None))
            else:
                result = builder.icmp_signed("==", v, ir.Constant(v.type, 0))
        elif target in ("pointer.offset", "pointer.loadByte", "pointer.storeByte"):
            # APP-RUN-2: explicit byte-addressed pointer ops over an OpaquePointer
            # (an Int64 address). `offset` returns base+n; `loadByte`/`storeByte`
            # reinterpret base+n as a byte address and load (zero-extended to Int32)
            # or store (the low byte of value). The reinterpret is the intrinsic's
            # defined semantics, not an implicit coercion of mismatched types.
            a = list(call.facts("arg"))
            i8ptr = ir.IntType(8).as_pointer()

            def _as_i64(val):
                if isinstance(val.type, ir.PointerType):
                    return builder.ptrtoint(val, ir.IntType(64))
                return val
            base = _as_i64(self._resolve(a[0].payload[2], a[0].payload[1], builder, sym))
            off = self._resolve(a[1].payload[2], a[1].payload[1], builder, sym)
            addr = builder.add(base, off)
            if target == "pointer.offset":
                result = addr
            elif target == "pointer.loadByte":
                self._guard_pointer_nonnull(builder, addr, target, call.line)  # R-130
                byte = builder.load(builder.inttoptr(addr, i8ptr))
                result = builder.zext(byte, ir.IntType(32))
            else:  # pointer.storeByte
                self._guard_pointer_nonnull(builder, addr, target, call.line)  # R-130
                value = self._resolve(a[2].payload[2], a[2].payload[1], builder, sym)
                builder.store(builder.trunc(value, ir.IntType(8)),
                              builder.inttoptr(addr, i8ptr))
        elif _family_intrinsic(target) is not None:
            # APP-RUN-6: sqlite/json/bcrypt/log intrinsic -> a native/shim symbol.
            symbol, retkind, arg_idx = _family_intrinsic(target)
            arg_rows = list(call.facts("arg"))
            if arg_idx is not None:  # resolve only the selected args (skip e.g. unused mode)
                arg_rows = [arg_rows[i] for i in arg_idx]
            vals = [self._resolve(a.payload[2], a.payload[1], builder, sym)
                    for a in arg_rows]
            ret_ty = {"h": ir.IntType(64), "i": ir.IntType(32),
                      "s": ir.IntType(8).as_pointer(), "v": ir.VoidType()}[retkind]
            fn = self._runtime_extern(symbol, ret_ty, [v.type for v in vals])
            r = builder.call(fn, vals)
            if retkind != "v" and call.fact("out") is not None:
                result = r
        elif target in ("sqlite.stepResultIsDone", "sqlite.stepResultIsRow"):
            # The step result code is the raw sqlite3_step return: SQLITE_ROW=100,
            # SQLITE_DONE=101. The predicate is an equality test.
            a0 = next(iter(call.facts("arg")), None)
            v = self._resolve(a0.payload[2], a0.payload[1], builder, sym)
            code = 101 if target.endswith("Done") else 100
            result = builder.icmp_signed("==", v, ir.Constant(v.type, code))
        elif target.startswith("c."):
            # APP-RUN-6: libc access. `c.snprintf` is the variadic formatter; the
            # rest go through ss_c_* shims (ss_libc.c) declared to take/return
            # Int64 for OpaquePointer handles and const char* for String, so the
            # app's declared arg/out types match the symbol exactly — no coercion.
            # The explicit pointer<->String reinterpret is `c.cString` (ss_c_cString).
            libc = target[len("c."):]
            vals = [self._resolve(a.payload[2], a.payload[1], builder, sym)
                    for a in call.facts("arg")]
            out_row = call.fact("out")
            out_ty = (self.ir_type(out_row.payload[1])
                      if out_row and len(out_row.payload) >= 2 else None)
            if libc in _VARIADIC_LIBC:
                # Variadic formatters bind to exported ss_c_* shims (ss_libc.c
                # forwards each to its v*-counterpart), never the raw libc symbol:
                # on Windows the UCRT `snprintf`/`printf`/`fprintf` are header
                # inlines with no exported symbol, so an MCJIT relocation cannot
                # resolve them. The extern is var_arg so each call site supplies
                # its own argument list past the fixed prefix.
                sym_name = "ss_c_" + libc
                fn = self.module.globals.get(sym_name)
                if not isinstance(fn, ir.Function):
                    nfixed = min(_VARIADIC_LIBC[libc], len(vals))
                    fn = ir.Function(self.module,
                                     ir.FunctionType(ir.IntType(32),
                                                     [v.type for v in vals[:nfixed]],
                                                     var_arg=True),
                                     name=sym_name)
                r = builder.call(fn, vals)
                if out_ty is not None:
                    result = r
            else:
                sym_name = "ss_c_" + libc
                ret_ty = _libc_ret_types().get(
                    libc, out_ty if out_ty is not None else ir.VoidType())
                fn = self._runtime_extern(sym_name, ret_ty, [v.type for v in vals])
                r = builder.call(fn, vals)
                if (out_ty is not None and out_row is not None
                        and not isinstance(ret_ty, ir.VoidType)):
                    result = r
        elif target in sym:
            # README ss33.9: indirect call through an operationType binding.
            fnptr = self._load(sym[target], builder)
            vals = [
                self._resolve(a.payload[2], a.payload[1], builder, sym)
                for a in call.facts("arg")
            ]
            result = builder.call(fnptr, vals)
        elif target in self.functions or (
                "." in target and target.rsplit(".", 1)[1] in self.functions) or (
                self.program.entities.get(target) is not None
                and self.program.entities[target].facts("typeParam")):
            # A module-aliased call to a co-loaded app op (e.g.
            # `components.renderPageShellHead`) — the op is registered under its
            # bare name, so strip the import alias to its tail.
            if target not in self.functions and self.program.entities.get(target) is None:
                target = target.rsplit(".", 1)[1]
            callee = self.program.entities[target]
            # R-039: a call to a generic op resolves to the monomorphized clone
            # for the instantiation inferred from this call's arg types.
            if callee.facts("typeParam"):
                eff_target = self._mangle(
                    target, self._infer_typeargs(callee, call))
            else:
                eff_target = target
            # X-092: enforce the callee's `requires` preconditions at the call site.
            # A provably-good literal arg is discharged (no check emitted); any other
            # value gets a runtime assert that traps on violation.
            reqs = {r.payload[1]: r.payload[0] for r in callee.facts("requires")
                    if len(r.payload) >= 2}
            vals = []
            for in_row in callee.facts("in"):
                a = args.get(in_row.payload[0])
                if a is None:
                    raise EavError(
                        f"call {call.name!r} missing arg {in_row.payload[0]!r} for "
                        f"{target!r}",
                        call.line,
                    )
                v = self._resolve(a.payload[2], a.payload[1], builder, sym)
                cond = reqs.get(in_row.payload[0])
                if cond is not None:
                    tok = a.payload[2]
                    discharged = tok.lstrip("-").isdigit() and \
                        _contract_holds(cond, int(tok)) is True
                    if not discharged:
                        self._emit_contract_check(builder, cond, v, call)
                vals.append(v)
            if (callee.fact("outParam") is not None
                    and _op_body_kind(callee) == "runtimeBinding"):
                # WS3-016 FFI out-param ABI: allocate the result slot, pass its
                # address as the trailing arg, call (returns an i32 status), then
                # load the written value. A non-zero status is the fallible error.
                out_row = callee.fact("out")
                out_ty = self.ir_type(out_row.payload[0]) if out_row and out_row.payload \
                    else ir.IntType(64)
                slot = builder.alloca(out_ty)
                i32 = ir.IntType(32)
                retry_row = call.fact("useRetry")
                max_attempts = 1
                if retry_row and retry_row.payload:
                    try:
                        max_attempts = max(1, int(str(retry_row.payload[0]).replace("_", "")))
                    except ValueError:
                        max_attempts = 1
                if max_attempts > 1:
                    # R-041 bounded retry: re-invoke the fallible out-param call up
                    # to `max_attempts` times, stopping on the first ok (status 0).
                    fn = builder.function
                    attempts_p = builder.alloca(i32)
                    status_p = builder.alloca(i32)
                    builder.store(ir.Constant(i32, 1), attempts_p)
                    rhead = fn.append_basic_block("retryHead")
                    rdone = fn.append_basic_block("retryDone")
                    builder.branch(rhead)
                    builder.position_at_end(rhead)
                    st = builder.call(self.functions[eff_target], vals + [slot])
                    builder.store(st, status_p)
                    att = builder.load(attempts_p)
                    builder.store(builder.add(att, ir.Constant(i32, 1)), attempts_p)
                    not_ok = builder.icmp_signed("!=", st, ir.Constant(i32, 0))
                    more = builder.icmp_signed("<", att, ir.Constant(i32, max_attempts))
                    builder.cbranch(builder.and_(not_ok, more), rhead, rdone)
                    builder.position_at_end(rdone)
                    status = builder.load(status_p)
                else:
                    status = builder.call(self.functions[eff_target], vals + [slot])
                result = builder.load(slot)
                err = builder.icmp_signed("!=", status, ir.Constant(i32, 0))
            else:
                result = builder.call(self.functions[eff_target], vals)
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
            elif any(o.payload and o.payload[0] == name
                     for o in call.facts("owns")) and isinstance(
                         result.type, (ir.IntType, ir.PointerType)):
                # README §15.6: this call owns `name`, whose cleanup is re-emitted
                # at every return by _emit_defers. The creation-block SSA value may
                # not dominate those returns, so back the handle with an entry-block
                # slot; all later reads (including the defer worker) load from it.
                # Inserting at the entry top shifts the builder's index-based anchor
                # in the current block, so re-anchor to its end before storing.
                cur_block = builder.block
                slot = self._entry_alloca(builder, result.type, name + ".own")
                builder.position_at_end(cur_block)
                builder.store(result, slot)
                typ_tok = (out_row.payload[1]
                           if len(out_row.payload) > 1 else name)
                sym[name] = ("ptr", slot, typ_tok)
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
        # Resolve each operand by its own *declared* type, not the compare
        # suffix: an enum operand (e.g. `right ScreenMode EditMode`) compared via
        # `compare.equalInt32` must resolve the bare variant `EditMode` through its
        # enum (-> i32 discriminant), which a fixed `Int32` hint can't do. In the
        # common case the declared type already equals the suffix.
        left = (self._resolve(args["left"].payload[2], args["left"].payload[1],
                              builder, sym) if "left" in args else None)
        right = (self._resolve(args["right"].payload[2], args["right"].payload[1],
                               builder, sym) if "right" in args else None)
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
            # WS1-131/R-076: narrowing is checked, not a silent truncation. If
            # the value does not round-trip through the destination width it does
            # not fit, so trap with a structured panic instead of dropping bits.
            narrowed = builder.trunc(val, dst)
            roundtrip = builder.sext(narrowed, src)
            overflow = builder.icmp_signed("!=", roundtrip, val)
            fn = builder.function
            bad_bb = fn.append_basic_block("narrowOverflow")
            ok_bb = fn.append_basic_block("narrowOk")
            builder.cbranch(overflow, bad_bb, ok_bb)
            tb = ir.IRBuilder(bad_bb)
            owner_row = call.fact("in")
            op_name = (owner_row.payload[0] if owner_row and owner_row.payload
                       else call.name)
            self._emit_panic(
                tb, "SSR0012", "narrowing-overflow",
                f"value does not fit the target type {dst_name!r} "
                f"({dst.width}-bit)", op_name, call.line, val,
                ir.Constant(ir.IntType(64), dst.width))
            tb.unreachable()
            builder.position_at_end(ok_bb)
            return narrowed
        return val

    def _emit_contract_check(self, builder, cond, value, call) -> None:
        """X-092: trap if a numeric precondition is violated at runtime (a runtime
        assert that traps, not UB). Discharged literals never reach here. On
        violation it raises a structured `ss_panic` (WS1-130/WS1-131)."""
        z = ir.Constant(value.type, 0)
        if cond == "nonNegative":
            bad = builder.icmp_signed("<", value, z)
        elif cond == "positive":
            bad = builder.icmp_signed("<=", value, z)
        elif cond == "nonZero":
            bad = builder.icmp_signed("==", value, z)
        else:
            return
        owner_row = call.fact("in")
        op_name = (owner_row.payload[0] if owner_row and owner_row.payload
                   else call.name)
        fn = builder.function
        trap_bb = fn.append_basic_block("requireViolated")
        cont_bb = fn.append_basic_block("requireOk")
        builder.cbranch(bad, trap_bb, cont_bb)
        tb = ir.IRBuilder(trap_bb)
        self._emit_panic(
            tb, "SSR0011", "contract-violation",
            f"precondition {cond!r} violated on a call to {call.name!r}",
            op_name, call.line, value, None)
        tb.unreachable()
        builder.position_at_end(cont_bb)

    def _overflow_op(self, op: str, builder, left, right):
        """Call `llvm.{op}.with.overflow.i64` (op in sadd/ssub/smul) and return
        (result_i64, overflow_i1) (R-067). llvmlite's `declare_intrinsic` reports
        the wrong signature for these, so the intrinsic is declared by hand with
        its canonical `{i64, i1} (i64, i64)` type and cached on the module."""
        i64 = ir.IntType(64)
        name = f"llvm.{op}.with.overflow.i64"
        fn = self.module.globals.get(name)
        if fn is None:
            agg_ty = ir.LiteralStructType([i64, ir.IntType(1)])
            fn = ir.Function(self.module, ir.FunctionType(agg_ty, [i64, i64]), name=name)
        aggregate = builder.call(fn, [left, right])
        return builder.extract_value(aggregate, 0), builder.extract_value(aggregate, 1)

    def _emit_panic(self, b, code, kind, reason, op_name, line, left, right) -> None:
        """WS1-130/WS1-131: emit a structured `ss_panic(...)` call at a guard
        site — the no-UB trap reports `code · kind · op · row · reason · operands`
        to stderr and terminates, instead of a bare `llvm.trap` (silent SIGILL).
        `left`/`right` are the i64 operands at the site (0 for the absent one)."""
        # WS1-136 emission-coverage guard: a trap code emitted into a program
        # must be a registered runtime diagnostic (so `explain` always resolves
        # it and the band stays complete).
        assert code in RUNTIME_DIAGNOSTICS, f"unregistered runtime code {code!r}"
        i32, i64 = ir.IntType(32), ir.IntType(64)

        def s(text):
            return self.global_string(text.encode("utf-8") + b"\x00")

        def w(v):
            if v is None:
                return ir.Constant(i64, 0)
            if v.type == i64:
                return v
            return b.sext(v, i64) if v.type.width < 64 else b.trunc(v, i64)

        b.call(self.runtime("ss_panic"),
               [s(code), s(kind), s(op_name), ir.Constant(i32, int(line)),
                s(reason), w(left), w(right)])

    def _guard_div_zero(self, builder, divisor, dividend, kind_label,
                        op_name, line) -> None:
        """Trap on integer divide/modulo by zero (README ss10.6): no UB. Emits a
        zero-check that branches to a structured `ss_panic` (WS1-130); the
        builder continues on the nonzero path."""
        fn = builder.function
        iszero = builder.icmp_signed("==", divisor, ir.Constant(divisor.type, 0))
        trap_bb = fn.append_basic_block("divByZero")
        cont_bb = fn.append_basic_block("divCont")
        builder.cbranch(iszero, trap_bb, cont_bb)
        tb = ir.IRBuilder(trap_bb)
        self._emit_panic(
            tb, "SSR0010", kind_label,
            "integer divide/modulo by zero is undefined (README ss10.6/ss33.5)",
            op_name, line, dividend, divisor)
        tb.unreachable()
        builder.position_at_end(cont_bb)

    def _guard_buffer_size(self, builder, size, op_name, line) -> None:
        """R-135: a `buffer.create` size must be non-negative — a negative length
        would flow into `malloc(size + 9)` and an unchecked length store. Emits a
        check that branches to a structured `ss_panic` (SSR0020); the builder
        continues on the valid path."""
        fn = builder.function
        bad = builder.icmp_signed("<", size, ir.Constant(size.type, 0))
        trap_bb = fn.append_basic_block("bufSizeBad")
        cont_bb = fn.append_basic_block("bufSizeCont")
        builder.cbranch(bad, trap_bb, cont_bb)
        tb = ir.IRBuilder(trap_bb)
        self._emit_panic(
            tb, "SSR0020", "buffer-size",
            "buffer.create size must be non-negative (README ss10.6)",
            op_name, line, size, None)
        tb.unreachable()
        builder.position_at_end(cont_bb)

    def _guard_pointer_nonnull(self, builder, addr_i64, op_name, line) -> None:
        """R-130: trap on a null/zero target address before a raw byte load/store,
        so a null deref is a structured ss_panic (SSR0021) instead of UB / a
        silent segfault. Valid (non-null) addresses continue unaffected."""
        i64 = ir.IntType(64)
        fn = builder.function
        isnull = builder.icmp_unsigned("==", addr_i64, ir.Constant(i64, 0))
        trap_bb = fn.append_basic_block("ptrNull")
        cont_bb = fn.append_basic_block("ptrCont")
        builder.cbranch(isnull, trap_bb, cont_bb)
        tb = ir.IRBuilder(trap_bb)
        self._emit_panic(
            tb, "SSR0021", "null-pointer",
            "raw byte load/store through a null pointer (README ss30.4)",
            op_name, line, addr_i64, None)
        tb.unreachable()
        builder.position_at_end(cont_bb)

    def _guard_alloc(self, builder, ptr, op_name, line) -> None:
        """R-137: trap if a list/map allocation (malloc/realloc) returned NULL,
        before storing the data pointer or elements through it — out-of-memory
        becomes a structured ss_panic (SSR0022), not a store through NULL. Works
        with any IRBuilder (the append/growth path uses the grow-block builder)."""
        i64 = ir.IntType(64)
        fn = builder.function
        isnull = builder.icmp_unsigned(
            "==", builder.ptrtoint(ptr, i64), ir.Constant(i64, 0))
        trap_bb = fn.append_basic_block("allocFail")
        cont_bb = fn.append_basic_block("allocFailCont")
        builder.cbranch(isnull, trap_bb, cont_bb)
        tb = ir.IRBuilder(trap_bb)
        self._emit_panic(
            tb, "SSR0022", "alloc-failed",
            "allocation failed (out of memory)",
            op_name, line, None, None)
        tb.unreachable()
        builder.position_at_end(cont_bb)

    def _guard_alloc_nonnull(self, builder, ptr, op_name, line) -> None:
        """R-135: trap if an allocation returned NULL (e.g. a size too large to
        satisfy) instead of storing through the null pointer."""
        i64 = ir.IntType(64)
        fn = builder.function
        isnull = builder.icmp_unsigned(
            "==", builder.ptrtoint(ptr, i64), ir.Constant(i64, 0))
        trap_bb = fn.append_basic_block("allocNull")
        cont_bb = fn.append_basic_block("allocCont")
        builder.cbranch(isnull, trap_bb, cont_bb)
        tb = ir.IRBuilder(trap_bb)
        self._emit_panic(
            tb, "SSR0020", "buffer-size",
            "buffer.create allocation failed (size too large)",
            op_name, line, None, None)
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
            variants = self._enum_variant_names(ent)
            if tail not in variants:
                raise EavError(
                    f"{target!r}: enum {head!r} has no variant {tail!r} "
                    f"(README ss10.5)",
                    call.line,
                )
            disc = self._enum_repr_map(ent).get(tail, variants.index(tail))
            pt = self._enum_payload_type(ent)
            if pt is None:
                return ir.Constant(ir.IntType(32), disc)
            # R-054: a data enum value is {i32 tag, payload}. A data variant
            # construction (`Enum.some <payloadArg>`) inserts the payload; a
            # payloadless variant (`Enum.none`) leaves a zero payload.
            struct_t = ir.LiteralStructType([ir.IntType(32), pt])
            val = builder.insert_value(
                ir.Constant(struct_t, ir.Undefined),
                ir.Constant(ir.IntType(32), disc), 0)
            if self._enum_variant_has_payload(ent, tail):
                pa = next(iter(args.values()), None)
                pv = (self._resolve(pa.payload[2], pa.payload[1], builder, sym)
                      if pa is not None else ir.Constant(pt, 0))
                val = builder.insert_value(val, pv, 1)
            else:
                val = builder.insert_value(val, ir.Constant(pt, 0), 1)
            return val
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


def lower_to_llvm(program: Program, platform: Optional[str] = None) -> ir.Module:
    """Lower a parsed EAV Program to an llvmlite ir.Module (console model). R-017:
    `platform` names a declared `platform` entity to build for (host default when
    None) — it sets the module triple and applies `forPlatform` filtering."""
    plat = _resolve_build_platform(program, platform)
    return EavCodegen(program, plat).generate()


_NATIVE_INIT_DONE = False


def _ensure_native_init() -> None:
    global _NATIVE_INIT_DONE
    if not _NATIVE_INIT_DONE:
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        _NATIVE_INIT_DONE = True


def _bundle_dir() -> str:
    """Directory holding bundled data (std/, sigs/, runtime/) — the
    `semanticscript/` package root. When frozen by PyInstaller (X-025), the
    bundle preserves the repo layout (`_MEIPASS/semanticscript/{std,sigs,runtime}`
    with `_MEIPASS/third_party` and `_MEIPASS/version.json` alongside), so the
    package root is `_MEIPASS/semanticscript`; otherwise it is the parent of this
    file's `compiler/` directory (semanticscript/compiler/semanticscript.py ->
    semanticscript/). Keeping the structure means manifest-relative paths and the
    relative `#include`s inside the runtime C sources resolve identically in both
    modes."""
    import os
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "semanticscript")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _runtime_dir() -> str:
    import os
    return os.path.join(_bundle_dir(), "runtime")


def _runtime_link_path(rel: str) -> str:
    """Resolve a runtime-manifest source/include path (relative to `runtime/`,
    e.g. `../../third_party/sqlite/sqlite3.c`) to an absolute path. The frozen
    bundle preserves the repo's directory structure (semanticscript/runtime +
    third_party), so the same relative paths — and the relative `#include`s
    inside the runtime C sources — resolve identically whether running from a
    checkout or from the PyInstaller _MEIPASS extraction."""
    import os
    return os.path.normpath(os.path.join(_runtime_dir(), rel))


def _runtime_cache_dir(create: bool = True) -> str:
    """A user-writable cache directory for native build artifacts (R-015). The
    runtime bundle (`_runtime_dir`) can be read-only — a packaged install or a
    PyInstaller `_MEIPASS` extraction — and is shared, so compiled runtime
    libraries and scratch IR must NOT be written beside the bundled sources.
    They live here instead. Override with `SEMANTICSCRIPT_CACHE_DIR`.

    R-118: pass `create=False` for read-only inspection (a diagnostic like
    `status` must not mutate the filesystem). When creating, a bad override (e.g.
    a path that is an existing file) is a clean EavError, not a raw traceback."""
    import os
    import tempfile
    base = os.environ.get("SEMANTICSCRIPT_CACHE_DIR") or os.path.join(
        tempfile.gettempdir(), "semanticscript-cache")
    if create:
        try:
            os.makedirs(base, exist_ok=True)
        except OSError as exc:
            raise EavError(
                f"runtime cache dir {base!r} is not usable: {exc} "
                f"(check SEMANTICSCRIPT_CACHE_DIR)")
    return base


def _find_c_compiler():
    """Locate a C compiler for building native runtime libraries, mirroring the
    reference toolchain: SEMANTICSCRIPT_CC, then clang on PATH / the common Windows LLVM
    install, then `zig cc`. Returns a command prefix list or None."""
    import os
    import shlex
    from shutil import which
    env = os.environ.get("SEMANTICSCRIPT_CC")
    if env:
        # R-113: a whole-string path (may contain spaces) is taken verbatim;
        # otherwise the command is shlex-parsed and its executable VERIFIED — an
        # invalid SEMANTICSCRIPT_CC must read as "no compiler" (degraded) so
        # readiness/status don't green-light a build that crashes at launch.
        if os.path.exists(env):
            return [env]
        try:
            parts = shlex.split(env, posix=(os.name != "nt"))
        except ValueError:
            parts = env.split()
        if parts:
            exe = parts[0].strip('"')
            if which(exe) or os.path.exists(exe):
                return [exe] + parts[1:]
        return None  # set but unresolvable -> treated as absent
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


# R-018: the canonical platform-section keys the runtime manifest understands.
# Anything outside this set in a `platforms` block is rejected so a typo like
# `platforms.win` never silently drops Windows-only link inputs (e.g. ws2_32).
_RUNTIME_MANIFEST_PLATFORMS = ("windows", "linux", "macos", "wasi")

# R-018: optional `compiler.<driver>` overlay keys for driver-specific flags
# (e.g. MSVC `.lib` link shapes vs GNU `-l`). Validated the same way as the
# platform keys so unknown driver overlays fail closed instead of being ignored.
_RUNTIME_MANIFEST_COMPILERS = ("gnu", "clang", "msvc", "zig")


def _host_platform_name() -> str:
    """R-018: map the running host's `sys.platform` to a runtime-manifest platform
    key (`windows`/`linux`/`macos`/`wasi`). This is what `_ensure_runtime_lib` and
    `build_executable` pass to the resolver on a real (non-cross) build, so the
    actual compile on this host keeps using the real platform's link inputs."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("wasi") or sys.platform.startswith("emscripten"):
        return "wasi"
    # Other Unixes (BSDs) link like Linux for our manifest's purposes.
    return "linux"


def _resolve_runtime_links(library: dict, platform: str,
                           compiler: Optional[str] = None) -> dict:
    """R-018: pure resolver — given one runtime-manifest `library` entry and a
    target `platform` (`windows`/`linux`/`macos`/`wasi`), return the merged
    source/include/define/lib set for that host WITHOUT compiling. The flat
    top-level fields are the cross-platform base; `platforms.<platform>` adds
    host-specific entries (R-013: Winsock `ws2_32` is windows-only), and an
    optional `compiler.<driver>` overlay (`gnu`/`clang`/`msvc`/`zig`) adds
    driver-specific entries. Order is base -> platform -> compiler with
    first-occurrence-wins de-duplication so the plan is deterministic.

    Tests drive this with an explicit `platform=` so a Linux/macOS resolved link
    set can be asserted on a Windows host without a Linux machine.
    """
    if platform not in _RUNTIME_MANIFEST_PLATFORMS:
        raise EavError(
            f"unknown runtime platform {platform!r}; "
            f"expected one of {', '.join(_RUNTIME_MANIFEST_PLATFORMS)}"
        )
    platforms = library.get("platforms", {}) or {}
    unknown = [k for k in platforms if k not in _RUNTIME_MANIFEST_PLATFORMS]
    if unknown:
        raise EavError(
            f"runtime library {library.get('name')!r} declares unknown "
            f"platform key(s) {sorted(unknown)}; expected one of "
            f"{', '.join(_RUNTIME_MANIFEST_PLATFORMS)}"
        )
    compilers = library.get("compiler", {}) or {}
    unknown_cc = [k for k in compilers if k not in _RUNTIME_MANIFEST_COMPILERS]
    if unknown_cc:
        raise EavError(
            f"runtime library {library.get('name')!r} declares unknown "
            f"compiler overlay key(s) {sorted(unknown_cc)}; expected one of "
            f"{', '.join(_RUNTIME_MANIFEST_COMPILERS)}"
        )
    overlays = [library, platforms.get(platform, {})]
    if compiler is not None:
        overlays.append(compilers.get(compiler, {}))

    def merged(field: str) -> list:
        seen: list = []
        for layer in overlays:
            for value in layer.get(field, []) or []:
                if value not in seen:
                    seen.append(value)  # base then platform then compiler order
        return seen

    return {
        "name": library.get("name"),
        "provides": list(library.get("provides", []) or []),
        "sources": merged("sources"),
        "include": merged("include"),
        "defines": merged("defines"),
        "libs": merged("libs"),
        # Symbols the library binds straight to a legacy `ss_*` runtime function
        # (no shim). On a Windows/MSVC-style link only `dllexport`/`/EXPORT:`
        # symbols enter the DLL export table that ctypes (the JIT symbol
        # resolver) reads, so these must be force-exported. Empty on POSIX,
        # where shared-object default visibility already exports them.
        "exports": merged("exports"),
    }


def _compiler_identity(cc) -> str:
    """A stable identity for the C compiler command (R-021): the command plus its
    reported version line, so switching clang->zig or bumping the compiler version
    keys a different runtime cache. `None` (no compiler) is its own identity."""
    if not cc:
        return "none"
    import subprocess
    version = ""
    try:
        probe = subprocess.run(list(cc) + ["--version"],
                               capture_output=True, text=True, timeout=15)
        lines = (probe.stdout or probe.stderr or "").splitlines()
        version = lines[0].strip() if lines else ""
    except (OSError, subprocess.SubprocessError):
        version = ""
    return " ".join(cc) + "|" + version


def _runtime_cache_key(resolved: dict, platform: str, compiler_id: str,
                       runtime_dir: str) -> str:
    """A digest keying a cached runtime library (R-021) by everything that makes
    the compiled artifact ABI-incompatible if it changes: the target platform,
    the compiler identity, the resolved defines/includes/libs, and the byte
    content of every source file. Two platform builds, a changed define, or a
    different compiler therefore land on distinct cache paths and can never load
    a stale incompatible library."""
    import hashlib
    import os
    digest = hashlib.sha256()
    for part in (platform, compiler_id):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    for field in ("defines", "include", "libs", "exports"):
        for value in resolved.get(field, []):
            digest.update(f"{field}={value}".encode("utf-8"))
            digest.update(b"\0")
    for source in resolved.get("sources", []):
        path = os.path.normpath(os.path.join(runtime_dir, source))
        try:
            with open(path, "rb") as handle:
                digest.update(hashlib.sha256(handle.read()).digest())
        except OSError:
            digest.update(source.encode("utf-8"))
    # R-106: the source bytes alone are not enough — a changed *header* (an ABI
    # struct/signature change in a `.h` the sources `#include`) must also
    # invalidate the cache, as must the runtime manifest. Hash every header in the
    # resolved include directories (sorted, content-addressed) plus the manifest,
    # so a stale ABI-incompatible library can never survive a header change.
    import glob
    headers: set = set()
    for inc in resolved.get("include", []):
        inc_dir = os.path.normpath(os.path.join(runtime_dir, inc))
        for hdr in glob.glob(os.path.join(inc_dir, "*.h")):
            headers.add(os.path.normpath(hdr))
    for hdr in sorted(headers):
        try:
            with open(hdr, "rb") as handle:
                digest.update(b"hdr:")
                digest.update(hashlib.sha256(handle.read()).digest())
        except OSError:
            pass
    try:
        with open(os.path.join(runtime_dir, "manifest.json"), "rb") as handle:
            digest.update(b"manifest:")
            digest.update(hashlib.sha256(handle.read()).digest())
    except OSError:
        pass
    return digest.hexdigest()[:16]


def _runtime_lib_cache_path(lib: dict, platform: Optional[str] = None,
                            compiler_id: Optional[str] = None) -> str:
    """The cache file path for a runtime library, keyed per R-021. Pure: computes
    the path without compiling, so tests can assert that two platforms (or a
    changed define) resolve to distinct paths."""
    import os
    rt = _runtime_dir()
    plat = platform or _host_platform_name()
    resolved = _resolve_runtime_links(lib, plat)
    cid = compiler_id if compiler_id is not None else _compiler_identity(_find_c_compiler())
    key = _runtime_cache_key(resolved, plat, cid, rt)
    build_dir = os.path.join(_runtime_cache_dir(), "_build")
    return os.path.join(build_dir, f"{lib['name']}-{key}{_shared_lib_suffix()}")


def _ensure_runtime_lib(lib: dict, platform: Optional[str] = None):
    """Build (cached) one native runtime library described by runtime/manifest.json
    and return its path, or None if no C compiler is available. The compiler is
    domain-agnostic — it only compiles the `sources` the manifest lists; the
    sqlite/http knowledge lives in those C sources and the `.sem` stdlib.

    R-018/R-013: link inputs are resolved through `_resolve_runtime_links` for
    the given `platform` (host platform by default) so Windows-only libs such as
    ws2_32 are appended on Windows but never on a resolved POSIX plan. R-021: the
    cache path is keyed by platform + compiler identity + defines/includes/libs +
    source content, so an incompatible cached artifact is never reused."""
    import os
    import subprocess
    rt = _runtime_dir()
    plat = platform or _host_platform_name()
    resolved = _resolve_runtime_links(lib, plat)
    cc = _find_c_compiler()
    # R-015: the compiled shared library lands in the user-writable cache, not
    # under the (possibly read-only/shared) runtime bundle. R-021: keyed by the
    # full ABI-relevant input set, so existence of the keyed file means it was
    # built from exactly these inputs (no stale reuse, no mtime guessing).
    build_dir = os.path.join(_runtime_cache_dir(), "_build")
    out = _runtime_lib_cache_path(lib, plat, _compiler_identity(cc))
    if os.path.exists(out):
        return out  # cached: the key already encodes platform/compiler/sources
    if cc is None:
        return None
    sources = [_runtime_link_path(s) for s in resolved["sources"]]
    os.makedirs(build_dir, exist_ok=True)
    # R-106: build to a per-process temp file, then publish atomically with
    # os.replace — a concurrent build (or a crash mid-link) can never leave a
    # partial library at `out` that a reader would load.
    out_tmp = f"{out}.tmp{os.getpid()}"
    cmd = list(cc) + ["-O2", "-shared", "-o", out_tmp]
    # The runtime DLL is loaded into the JIT process, so it must match the JIT's
    # target arch, not clang's native default. On this ARM64 host llvmlite is
    # x64-emulated (JIT triple x86_64-pc-windows-msvc) while clang defaults to
    # ARM64 — loading the native DLL fails WinError 193. Pin clang to the JIT
    # triple so the architectures agree (a no-op when they already match).
    jit_triple = ""
    try:
        jit_triple = llvm.get_default_triple() or ""
        if jit_triple:
            cmd.append("--target=" + jit_triple)
    except Exception:
        pass
    cmd += sources
    for inc in resolved["include"]:
        cmd.append("-I" + _runtime_link_path(inc))
    for d in resolved["defines"]:
        cmd.append("-D" + d)
    for libname in resolved["libs"]:
        cmd.append("-l" + libname)
    # Force-export the legacy symbols this library binds directly (no shim).
    # MSVC-style links (lld-link, used for the x86_64-pc-windows-msvc JIT
    # triple) export nothing unless dllexport/`/EXPORT:`-named, so a directly
    # bound legacy symbol would be absent from the export table the JIT resolver
    # reads — its address would resolve to null and the call would fault. POSIX
    # shared objects export default-visibility symbols already, so this is a
    # Windows-only concern (`/EXPORT:` is lld-link/MSVC syntax).
    if "msvc" in jit_triple:
        for sym in resolved.get("exports", []):
            cmd.append("-Wl,/EXPORT:" + sym)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=_build_timeout_seconds())
    except subprocess.TimeoutExpired:  # R-107
        raise EavError(
            f"building runtime library {lib['name']!r} exceeded "
            f"{_build_timeout_seconds():g}s and was terminated "
            f"(set SEMANTICSCRIPT_BUILD_TIMEOUT to adjust)")
    except OSError as exc:  # R-113: a bad compiler command fails to launch
        raise EavError(
            f"could not launch the C compiler {cmd[0]!r} to build runtime library "
            f"{lib['name']!r}: {exc} (check SEMANTICSCRIPT_CC or install clang/zig)")
    if proc.returncode != 0:
        try:
            if os.path.exists(out_tmp):
                os.unlink(out_tmp)
        except OSError:
            pass
        raise EavError(
            f"failed to build runtime library {lib['name']!r}: {proc.stderr.strip()}"
        )
    os.replace(out_tmp, out)  # R-106: atomic publish
    return out


def _referenced_runtime_symbols(program: Program) -> set:
    """The ABI symbols a program needs: every `body runtimeBinding` symbol, plus
    `ss_http_html_escape_str` when any call lowers `html.render` (auto-escape)."""
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
            if inv and inv.payload:
                target = inv.payload[0]
                if target == "html.render":
                    out.add("ss_http_html_escape_str")
                elif target == "net.fetchText":      # APP-RUN-1 HTTP client
                    out.add("ss_net_fetch_text")
                elif target == "net.freeTextBody":
                    out.add("ss_net_free_text")
                elif target in _EVENT_RUNTIME_SYMBOLS:  # APP-RUN-3 pub/sub
                    out.add(_EVENT_RUNTIME_SYMBOLS[target])
                elif target.startswith("gui."):         # APP-RUN-4 widgets
                    out.add(_gui_runtime_symbol(target))
                elif target.startswith("http.") and target != "html.render":
                    out.add("ss_http_" + _camel_to_snake(target[len("http."):]))
                elif _family_intrinsic(target) is not None:  # APP-RUN-6 families
                    out.add(_family_intrinsic(target)[0])
                elif target.startswith("c."):
                    out.add("ss_c_" + target[len("c."):])  # libc shims (incl. snprintf)
    # APP-RUN-5: the webServer entry calls the multi-route server runtime.
    if program.of_kind("webServer"):
        out.add("ss_http_serve_routes")
    return out


def _camel_to_snake(name: str) -> str:
    """`requestQueryParam` -> `request_query_param`."""
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# APP-RUN-6: runtime-intrinsic families for taskforge-web. Each method maps to a
# (symbol, return-kind, arg-indices) triple. return-kind: "h"=i64 handle/int64,
# "i"=i32 status, "s"=i8* string, "v"=void. arg-indices=None passes every arg in
# order; a tuple selects a subset (sqlite.openDatabase drops its unused mode arg).
# sqlite -> the ss_sqlite_* shims; json -> the ss_json.c direct-return shim;
# bcrypt/log -> the native runtimes directly (force-exported in the manifest).
_FAMILY_RT = {
    "sqlite": {
        "openDatabase": ("ss_sqlite_open", "h", (0,)),
        "exec": ("ss_sqlite_exec", "i", None),
        "prepareStatement": ("ss_sqlite_prepare", "h", None),
        "stepStatement": ("ss_sqlite_step", "i", None),
        "bindInt64": ("ss_sqlite_bind_int64", "i", None),
        "bindText": ("ss_sqlite_bind_text", "i", None),
        "columnInt64": ("ss_sqlite_column_int64", "h", None),
        "columnText": ("ss_sqlite_column_text", "s", None),
        "finalizeStatement": ("ss_sqlite_finalize", "i", None),
        "closeDatabase": ("ss_sqlite_close", "i", None),
    },
    "json": {
        "createEmptyDocument": ("ss_json_create_empty", "h", None),
        "createDocument": ("ss_json_from_text", "h", None),
        "documentRoot": ("ss_json_root", "h", None),
        "destroyDocument": ("ss_json_destroy", "v", None),
        "serializeDocument": ("ss_json_serialize", "s", None),
        "setObjectFieldString": ("ss_json_set_field_string", "i", None),
        "setObjectFieldInt64": ("ss_json_set_field_int64", "i", None),
        "setObjectFieldBool": ("ss_json_set_field_bool", "i", None),
        "setObjectFieldObject": ("ss_json_set_field_object", "h", None),
        "setObjectFieldArray": ("ss_json_set_field_array", "h", None),
        "appendArrayElementObject": ("ss_json_append_object", "h", None),
        "objectFieldAt": ("ss_json_field_at", "h", None),
        "cursorInt64": ("ss_json_read_int64", "h", None),
        "cursorString": ("ss_json_read_string", "s", None),
    },
    "bcrypt": {
        "hashPassword": ("ss_bcrypt_hash", "i", None),
        "verifyPassword": ("ss_bcrypt_verify", "i", None),
        "randomBytes": ("ss_random_bytes", "i", None),
        "base64UrlEncode": ("ss_base64url_encode", "i", None),
    },
    "log": {
        "logInfo": ("ss_log_info", "i", None),
        "logWarn": ("ss_log_warn", "i", None),
        "openLogFile": ("ss_log_set_path", "i", None),
    },
}


def _family_intrinsic(target: str):
    """Return the (symbol, return-kind, arg-indices) spec for a runtime-family
    intrinsic call target, or None."""
    if "." not in target:
        return None
    fam, meth = target.split(".", 1)
    return _FAMILY_RT.get(fam, {}).get(meth)


def _gui_runtime_symbol(target: str) -> str:
    """`gui.applicationCreate` -> `ss_widget_application_create` (the headless
    widget runtime; ss_widget_ avoids the real Win32 ss_gui_* symbols)."""
    return "ss_widget_" + _camel_to_snake(target[len("gui."):])


_EVENT_RUNTIME_SYMBOLS = {
    "event.openProcessStream": "ss_event_open_stream",
    "event.subscribeStream": "ss_event_subscribe",
    "event.appendEvent": "ss_event_append",
    "event.receiveEvent": "ss_event_receive",
    "event.acknowledgeEvent": "ss_event_ack",
    "event.closeSubscription": "ss_event_close_subscription",
    "event.closeStream": "ss_event_close_stream",
}

# Variadic libc formatters (`c.*`) → count of fixed (non-variadic) leading args.
# These bind to exported ss_c_* shims (ss_libc.c) rather than the raw libc symbol
# because the UCRT versions are header inlines with no exported symbol on Windows.
_VARIADIC_LIBC = {"snprintf": 3, "printf": 1, "fprintf": 2}

# Fixed return type per non-variadic libc seam (`c.*` → ss_c_*). Pinned here (not
# derived from a call's `out`/`discards`) so the one cached extern per symbol is
# stable across call sites — a value-returning libc fn called as `discards` at one
# site and `out` at another must still agree on a single IR signature. Matches the
# ss_libc.c shim return types exactly.
def _libc_ret_types():
    i32, i64 = ir.IntType(32), ir.IntType(64)
    void, i8p = ir.VoidType(), ir.IntType(8).as_pointer()
    return {
        "putchar": i32, "puts": i32, "fflush": i32, "fclose": i32,
        "strcmp": i32, "terminalReadKey": i32,
        "malloc": i64, "fopen": i64, "fgets": i64, "memmove": i64,
        "strlen": i64, "atoll": i64,
        "free": void, "memset": void,
        "cString": i8p, "cstring": i8p,
    }


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


# Runtime `ss_*` symbols the compiler registers directly with the JIT (Python-
# backed callbacks), so they are NOT in runtime/manifest.json yet resolve fine:
# the panic hook and the out-param-ABI FFI demo symbols. Excluded from the R-105
# unresolved-symbol check (a native build links their C counterparts).
_COMPILER_PROVIDED_RUNTIME_SYMBOLS = frozenset({"ss_panic", "ss_ffi_add", "ss_ffi_count"})


def _unresolved_runtime_symbols(program: Program) -> set:
    """R-105: project runtime symbols (`ss_*`) a program references — via a
    `body runtimeBinding` row or a lowered intrinsic — that NO native runtime
    library in runtime/manifest.json provides (and that the compiler does not
    register directly). Such a symbol falls through to the JIT's default
    resolver, resolves to null, and crashes at first call with no diagnostic.
    libc/system symbols (not `ss_`-prefixed) are intentionally left to the
    default resolver and are not reported. Returns an empty set when the manifest
    is absent (can't verify — don't false-positive)."""
    import json
    import os
    ss_refs = {s for s in _referenced_runtime_symbols(program)
               if s.startswith("ss_") and s not in _COMPILER_PROVIDED_RUNTIME_SYMBOLS}
    if not ss_refs:
        return set()
    manifest_path = os.path.join(_runtime_dir(), "manifest.json")
    if not os.path.exists(manifest_path):
        return set()
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    prefixes = [p for lib in manifest.get("libraries", []) for p in lib.get("provides", [])]
    return {s for s in ss_refs if not any(s.startswith(p) for p in prefixes)}


def build_link_plan(program: Program, platform: Optional[str] = None,
                    compiler: Optional[str] = None) -> dict:
    """R-018: a dry-run native link plan — for each runtime library the program
    references, the resolved source/include/define/lib set for `platform` (host
    platform by default) WITHOUT compiling. This is the JSON-serializable view of
    exactly what `build_executable`/`_ensure_runtime_lib` will pass to the C
    compiler, so cross-platform link inputs (R-013: Windows-only ws2_32) can be
    inspected and asserted without a build."""
    resolved_platform = platform or _host_platform_name()
    libraries = [
        _resolve_runtime_links(lib, resolved_platform, compiler)
        for lib in _runtime_libs_for(program)
    ]
    return {
        "platform": resolved_platform,
        "compiler": compiler,
        "libraries": libraries,
    }


# WS1-130/WS1-136: the runtime trap-code band. Mirrors the compile-time
# DIAGNOSTICS registry but for guard sites that fire during execution; each maps
# a structured `ss_panic` kind to a code + summary + repair hint. (Seed set —
# WS1-131 routes the remaining trap kinds — OOB / narrowing / recursion — through
# ss_panic with their own SSR#### codes.)
RUNTIME_DIAGNOSTICS = {
    "SSR0010": {"kind": "divide-by-zero",
                "summary": "Integer divide/modulo by zero at runtime.",
                "repair": "Guard the divisor (`branch if`) or prove it non-zero before dividing."},
    "SSR0011": {"kind": "contract-violation",
                "summary": "A numeric precondition (nonNegative/positive/nonZero) failed at runtime.",
                "repair": "Validate or clamp the value before the call, or relax the operation's `requires`."},
    "SSR0012": {"kind": "narrowing-overflow",
                "summary": "A narrowing numeric conversion lost data at runtime (value out of target range).",
                "repair": "Range-check the value before converting, or keep the wider type."},
    "SSR0013": {"kind": "recursion-depth-exceeded",
                "summary": "Recursive call depth exceeded the runtime limit (likely unbounded recursion).",
                "repair": "Add or fix the base case, or convert the recursion to a bounded loop."},
    "SSR0020": {"kind": "buffer-size",
                "summary": "buffer.create size is negative, or the allocation for it failed (R-135).",
                "repair": "Validate the size is non-negative and within memory before creating the buffer."},
    "SSR0021": {"kind": "null-pointer",
                "summary": "Raw byte load/store through a null pointer (R-130).",
                "repair": "Guard the pointer with `pointer.isNull` before `pointer.loadByte`/`storeByte`."},
    "SSR0022": {"kind": "alloc-failed",
                "summary": "A collection allocation (list/map create or growth) returned NULL (R-137).",
                "repair": "The process is out of memory; reduce the working set or the collection size."},
}

# WS1-131: logical recursion-depth bound. A statically-recursive operation
# increments a shared depth counter on entry and traps with a structured
# `ss_panic` (SSR0013) past this limit — a runaway-recursion signal that fires
# (for typical small frames) before the native stack guard would, and is well
# above any legitimate recursion depth in practice.
EAV_RECURSION_LIMIT = 10000

_EAV_PANIC_CFUNC = None  # kept alive so the JIT-registered callback survives GC


def _ss_panic_py(code, kind, op, row, reason, left, right) -> None:
    """In-process implementation of the WS1-130 `ss_panic` ABI for the JIT (the
    native build links the C `ss_panic` instead). Prints the structured crash
    report to stderr and terminates the process with code 134 (the conventional
    abort/trap status), so a trapping program reports *why* it died rather than
    dying on a silent SIGILL."""
    import os
    import sys

    def d(p):
        return p.decode("utf-8", "replace") if p else ""

    report = (
        f"\nEAV PANIC {d(code)} {d(kind)}\n"
        f"  op:       {d(op)}\n"
        f"  at line:  {row}\n"
        f"  reason:   {d(reason)}\n"
        f"  operands: left={left} right={right}\n"
    )
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.write(report)
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(134)


_EAV_FFI_ADD_CFUNC = None  # kept alive so the JIT-registered callback survives GC
_EAV_FFI_COUNT_CFUNC = None
_EAV_FFI_COUNT_N = [0]  # per-process invocation counter for the retry demo


def _ss_ffi_count_py(out_ptr) -> int:
    """In-process impl of the R-041 retry demo symbol
    `int ss_ffi_count(int64_t *out)`: increments a per-process counter, writes
    it through the out-pointer, and ALWAYS returns a non-zero (error) status — so
    a `useRetry N` call invokes it exactly N times and the written value ends at
    N, proving the bounded retry re-invoked the call."""
    _EAV_FFI_COUNT_N[0] += 1
    out_ptr[0] = _EAV_FFI_COUNT_N[0]
    return 1


def _ss_ffi_add_py(a, b, out_ptr) -> int:
    """In-process implementation of the WS3-016 FFI out-param ABI demo symbol
    `int ss_ffi_add(int64_t a, int64_t b, int64_t *out)`: writes a+b through the
    out-pointer and returns 0 (ok), or returns a non-zero status (1) for a
    negative `a` without writing — exercising the status->error seam (the shape
    sqlite/http C APIs use). Proves the out-param ABI end-to-end in the JIT (the
    native build links the C `ss_ffi_add`)."""
    if a < 0:
        return 1
    out_ptr[0] = a + b
    return 0


def _register_panic_symbol() -> None:
    """Register the in-process `ss_panic` callback (compiler-injected at guard
    sites) and the `ss_ffi_add` out-param-ABI demo symbol with the JIT, before
    every JIT run."""
    import ctypes
    global _EAV_PANIC_CFUNC, _EAV_FFI_ADD_CFUNC, _EAV_FFI_COUNT_CFUNC
    if _EAV_PANIC_CFUNC is None:
        cft = ctypes.CFUNCTYPE(
            None, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_int32, ctypes.c_char_p, ctypes.c_int64, ctypes.c_int64)
        _EAV_PANIC_CFUNC = cft(_ss_panic_py)
    llvm.add_symbol(
        "ss_panic", ctypes.cast(_EAV_PANIC_CFUNC, ctypes.c_void_p).value)
    if _EAV_FFI_ADD_CFUNC is None:
        cft2 = ctypes.CFUNCTYPE(
            ctypes.c_int32, ctypes.c_int64, ctypes.c_int64,
            ctypes.POINTER(ctypes.c_int64))
        _EAV_FFI_ADD_CFUNC = cft2(_ss_ffi_add_py)
    llvm.add_symbol(
        "ss_ffi_add", ctypes.cast(_EAV_FFI_ADD_CFUNC, ctypes.c_void_p).value)
    if _EAV_FFI_COUNT_CFUNC is None:
        cft3 = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(ctypes.c_int64))
        _EAV_FFI_COUNT_CFUNC = cft3(_ss_ffi_count_py)
    llvm.add_symbol(
        "ss_ffi_count", ctypes.cast(_EAV_FFI_COUNT_CFUNC, ctypes.c_void_p).value)


_LOADED_RUNTIME_DLLS: list = []


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
    # R-105: a referenced ss_* symbol that no runtime library provides would
    # resolve to null and crash at first call — reject it before JIT finalization.
    unresolved = _unresolved_runtime_symbols(program)
    if unresolved:
        raise EavError(
            f"runtimeBinding symbol(s) {sorted(unresolved)} are not provided by "
            f"any native runtime library (runtime/manifest.json); check the symbol "
            f"name or add a providing library", code="SS1195")
    for lib in _runtime_libs_for(program):
        path = _ensure_runtime_lib(lib)
        prefixes = lib.get("provides", [])
        needed = {s for s in referenced if any(s.startswith(p) for p in prefixes)}
        if path is None:
            raise EavError(
                f"program uses runtime symbols {sorted(needed)} provided by "
                f"{lib['name']!r}, but no C compiler was found to build it "
                f"(set SEMANTICSCRIPT_CC, or install clang/zig)"
            )
        # Keep the loaded library alive for the process lifetime. The addresses
        # registered with the JIT below point into this DLL; if the CDLL handle
        # were dropped here, CPython would FreeLibrary it on return and Windows
        # could unmap it before `finalize_object` bakes the addresses into the
        # call sites — leaving a runtime symbol resolved to a null/stale pointer
        # that faults when first called (observed as a call to 0x0).
        cdll = ctypes.CDLL(path)
        _LOADED_RUNTIME_DLLS.append(cdll)
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
    _register_panic_symbol()
    _register_runtime_symbols(program)
    mod = llvm.parse_assembly(str(module))
    mod.verify()
    tm = llvm.Target.from_default_triple().create_target_machine()
    engine = llvm.create_mcjit_compiler(mod, tm)
    engine.finalize_object()
    engine.run_static_constructors()
    entry_name = entry or _entry_name(program)
    addr = engine.get_function_address(entry_name)
    if not addr:  # R-104: a dangling entry resolves to address 0 — never call it
        raise EavError(
            f"entry {entry_name!r} resolved to a null address (no such function "
            f"was emitted); the project entry must name a declared operation")
    cmain = ctypes.CFUNCTYPE(ctypes.c_int)(addr)
    return cmain()


def _record_run_entry(source: str, entry: str):
    """R-102: run one operation as the entry in an isolated child, returning
    (stdout, stderr, exitCode). A test op that traps (ss_panic -> 134) or hangs
    kills only the child — the test runner survives and records the result."""
    import os
    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "run", "-", "--entry", entry],
            input=source, capture_output=True, text=True, encoding="utf-8",
            timeout=_eval_timeout_seconds(),
        )
    except subprocess.TimeoutExpired as exc:
        err = _decode_stream(exc.stderr) + (
            f"\nsemanticscript: eval timeout — test '{entry}' exceeded "
            f"{_eval_timeout_seconds():g}s and was terminated\n")
        return _decode_stream(exc.stdout), err, _EVAL_TIMEOUT_EXIT
    return proc.stdout, proc.stderr, proc.returncode


def run_tests(program: Program, lane: Optional[str] = None) -> dict:
    """Execute every `tag test` operation by running it as an entry in an isolated
    child and treating a 0 exit as a pass (sem.test.v1; WS3-026/WS4-119). Project
    semantic preflight (lint errors) runs first and blocks the runtime lane.

    R-102: each op runs in its own child (over the program's canonical source), so
    a runtime trap or hang in one test is captured (status error/timeout + panic)
    instead of killing the whole runner.
    R-007: an optional `lane` restricts execution to one discovered lane."""
    selected_lane = lane  # the loop below rebinds `lane`; remember the request
    diags = lint(program)
    preflight_ok = not any(d.severity == "error" for d in diags)
    lanes = discover_tests(program)
    if lane is not None:
        lanes = {lane: lanes.get(lane, [])}
    tests: list = []
    if preflight_ok:
        source = format_program(program)  # canonical, runnable source for the child
        for lane in sorted(lanes):
            for op in lanes[lane]:
                out, err, code = _record_run_entry(source, op)
                run_status, panic = _classify_run(out, err, code)
                if run_status == "ok":
                    status = "pass"
                elif run_status == "timed-out":
                    status = "timeout"
                elif run_status == "crashed" or panic is not None:
                    status = "error"
                else:
                    status = "fail"
                rec = {"name": op, "lane": lane, "status": status, "exitCode": code}
                if panic is not None:
                    rec["panic"] = panic
                if status in ("error", "timeout") and err.strip():
                    rec["error"] = err.strip().splitlines()[-1][:200]
                tests.append(rec)
    # R-158: an explicitly selected lane that discovers zero tests is `no-tests`,
    # not a vacuous `pass` — a misspelled/unimplemented lane must not green CI.
    selected_empty = selected_lane is not None and preflight_ok and not tests
    runtime_status = ("not-run" if not preflight_ok
                      else "no-tests" if selected_empty
                      else "pass" if all(t["status"] == "pass" for t in tests)
                      else "fail")
    composite = ("blocked" if not preflight_ok
                 else "no-tests" if selected_empty
                 else "pass" if runtime_status == "pass" else "fail")
    return {
        "preflightStatus": "ok" if preflight_ok else "lint-diagnostics",
        "runtimeHarnessStatus": runtime_status,
        "compositeStatus": composite,
        "tests": tests,
    }


def _eval_timeout_seconds() -> float:
    """R-101: the eval/replay subprocess budget. A hostile or buggy program (an
    infinite loop, a stuck runtime call) must not wedge `eval`, replay, the test
    runner, or an agent repair loop forever. Configurable via the
    SEMANTICSCRIPT_EVAL_TIMEOUT env var (seconds); default 30."""
    import os
    try:
        v = float(os.environ.get("SEMANTICSCRIPT_EVAL_TIMEOUT", "") or 30)
        return v if v > 0 else 30.0
    except ValueError:
        return 30.0


def _build_timeout_seconds() -> float:
    """R-107: the native build subprocess budget (clang/link/runtime-lib). A
    wedged toolchain process must not hang the CLI/CI forever. Configurable via
    SEMANTICSCRIPT_BUILD_TIMEOUT (seconds); default 300."""
    import os
    try:
        v = float(os.environ.get("SEMANTICSCRIPT_BUILD_TIMEOUT", "") or 300)
        return v if v > 0 else 300.0
    except ValueError:
        return 300.0


_EVAL_TIMEOUT_EXIT = 124  # conventional "killed by timeout" exit code


def _decode_stream(s) -> str:
    return s.decode("utf-8", "replace") if isinstance(s, (bytes, bytearray)) else (s or "")


def _record_run(source: str):
    """Run a program in a clean subprocess, capturing (stdout, exitCode). A fresh
    process is the record substrate: it is exactly the capability-mediated output
    a replay must reproduce. R-101: bounded by the eval timeout."""
    import os
    import subprocess
    # UTF-8 stdin pipe to match the child's UTF-8 stream reconfigure (README §33.2).
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "run", "-"],
            input=source, capture_output=True, text=True, encoding="utf-8",
            timeout=_eval_timeout_seconds(),
        )
    except subprocess.TimeoutExpired as exc:
        return _decode_stream(exc.stdout), _EVAL_TIMEOUT_EXIT
    return proc.stdout, proc.returncode


def _record_run_full(source: str):
    """Like `_record_run`, but also returns stderr. `eval` needs the compiler/
    runtime diagnostics, not only stdout (R-008): a parse/compile failure surfaces
    on stderr (`semanticscript: …`) and must reach the caller, not be dropped.
    R-101: bounded by the eval timeout; a timeout returns a clear status."""
    import os
    import subprocess
    # EAV source/output is UTF-8 (README §33.2); the child reconfigures its
    # std streams to UTF-8, so the stdin pipe must be UTF-8 too — otherwise a
    # non-ASCII source byte (e.g. an em-dash in a comment) is mis-encoded as
    # cp1252 on Windows and the child fails to decode it.
    timeout = _eval_timeout_seconds()
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "run", "-"],
            input=source, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        err = _decode_stream(exc.stderr)
        err += (f"\nsemanticscript: eval timeout — execution exceeded {timeout:g}s "
                f"and was terminated (set SEMANTICSCRIPT_EVAL_TIMEOUT to adjust)\n")
        return _decode_stream(exc.stdout), err, _EVAL_TIMEOUT_EXIT
    return proc.stdout, proc.stderr, proc.returncode


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
    result = {
        # R-009: a non-reproducible record is not a valid replay. `ok` follows
        # `deterministic` instead of being unconditionally true, so a caller
        # cannot mistake a clock/random-backed divergence for a clean replay.
        "ok": deterministic,
        "status": "ok" if deterministic else "nondeterministic",
        "mode": mode,
        "transcript": transcript,
        "exitCode": exit1,
        "deterministic": deterministic,
        # replay re-emits the recorded transcript without executing the program,
        # so no capability-mediated effect is performed: side-effect-free.
        "replayStdout": out1,
        "sideEffectFree": True,
    }
    if not deterministic:
        # surface both record runs so the divergence is diagnosable rather than
        # collapsed into a single buried boolean (R-009).
        result["records"] = [
            {"stdout": out1, "exitCode": exit1},
            {"stdout": out2, "exitCode": exit2},
        ]
    return result


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


def cmd_emit_ir(args) -> int:
    """Emit textual LLVM IR — a named, `-o`-aware superset of `lower` with an
    optional `--optimized` pass. (TOOL-3, parity with the legacy `emit-ir`.)"""
    program = parse_compact(_read_program_source(args.path))
    text = str(lower_to_llvm(program))
    if getattr(args, "optimized", False):
        try:
            import llvmlite.binding as llvm
            _ensure_native_init()
            mod = llvm.parse_assembly(text)
            mod.verify()
            tm = llvm.Target.from_default_triple().create_target_machine()
            pto = llvm.create_pipeline_tuning_options(speed_level=2, size_level=0)
            pb = llvm.create_pass_builder(tm, pto)
            pb.getModulePassManager().run(mod, pb)
            text = str(mod)
        except Exception as exc:  # pragma: no cover - toolchain-dependent
            sys.stderr.write(
                f"semanticscript: --optimized unavailable ({exc}); "
                "emitting unoptimized IR\n")
    out = getattr(args, "output", None)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stderr.write(f"semanticscript: wrote IR to {out}\n")
    else:
        sys.stdout.write(text)
    return 0


def cmd_inspect_ir(args) -> int:
    """Structured summary of the lowered LLVM module — defined functions (with
    block/instruction counts), declared externs, and globals (sem.inspectIr.v1).
    (TOOL-3, parity with the legacy `inspect-ir`.)"""
    import llvmlite.binding as llvm
    program = parse_compact(_read_program_source(args.path))
    text = str(lower_to_llvm(program))
    _ensure_native_init()
    mod = llvm.parse_assembly(text)
    mod.verify()
    funcs, externs = [], []
    for fn in mod.functions:
        if fn.is_declaration:
            externs.append(fn.name)
            continue
        blocks = list(fn.blocks)
        ninstr = sum(len(list(b.instructions)) for b in blocks)
        funcs.append({"name": fn.name, "blocks": len(blocks),
                      "instructions": ninstr})
    funcs.sort(key=lambda f: -f["instructions"])
    externs.sort()
    global_count = sum(1 for _ in mod.global_variables)
    summary = dict(functionCount=len(funcs), externCount=len(externs),
                   globalCount=global_count, irBytes=len(text),
                   functions=funcs, externs=externs)
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope("sem.inspectIr.v1", **summary) + "\n")
    else:
        print(f"functions: {len(funcs)}  externs: {len(externs)}  "
              f"globals: {global_count}  ir-bytes: {len(text)}")
        for f in funcs[:30]:
            print(f"  {f['name']}: {f['blocks']} blocks, "
                  f"{f['instructions']} instrs")
    return 0


def _dir_bytes(path: str) -> int:
    """Total byte size of the files under `path` (0 if it does not exist)."""
    import os
    total = 0
    for root, _dirs, files in os.walk(path):
        for fname in files:
            try:
                total += os.path.getsize(os.path.join(root, fname))
            except OSError:
                pass
    return total


def _release_version() -> Optional[str]:
    """The release version from version.json, if available. In a normal checkout
    it sits one level above the `semanticscript/` package root; a PyInstaller
    build bundles it flat under the bundle root (`_MEIPASS/version.json`), so try
    the bundled location first."""
    import json
    import os
    candidates = [
        os.path.join(_bundle_dir(), "version.json"),                 # frozen bundle
        os.path.normpath(os.path.join(_bundle_dir(), "..", "version.json")),  # checkout
    ]
    for candidate in candidates:
        try:
            with open(candidate, encoding="utf-8") as fh:
                return json.load(fh).get("version")
        except (OSError, ValueError):
            continue
    return None


def cmd_status(args) -> int:
    """Toolchain self-diagnostic: versions, compiler path, C-toolchain
    availability, runtime cache, and platform/triple (sem.status.v1). (TOOL-4)"""
    import os
    import platform
    import llvmlite
    import llvmlite.binding as llvm
    _ensure_native_init()  # register the native target before querying the triple
    cc = _find_c_compiler()
    cache = _runtime_cache_dir(create=False)  # R-118: status must not mutate the fs
    build = os.path.join(cache, "_build")
    # R-118: a cache override that exists as a non-directory is unusable — report
    # it (degraded) rather than crashing on a later makedirs.
    cache_usable = not (os.path.exists(cache) and not os.path.isdir(cache))
    info = {
        "contractVersion": CONTRACT_VERSION,
        "releaseVersion": _release_version(),
        "compiler": os.path.abspath(__file__),
        "python": platform.python_version(),
        "llvmlite": llvmlite.__version__,
        "platform": _host_platform_name(),
        "triple": llvm.Target.from_default_triple().triple,
        "cCompiler": (cc[0] if cc else None),
        "cCompilerAvailable": cc is not None,
        "runtimeCacheDir": cache,
        "runtimeCacheUsable": cache_usable,
        "runtimeCacheBytes": _dir_bytes(build) if cache_usable else 0,
    }
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope("sem.status.v1", **info) + "\n")
    else:
        for key, value in info.items():
            print(f"{key}: {value}")
    return 0


def cmd_clean(args) -> int:
    """Clear the cached native runtime/build artifacts (sem.clean.v1). (TOOL-4)"""
    import os
    import shutil
    cache = _runtime_cache_dir(create=False)  # R-118: inspect, don't create
    build = os.path.join(cache, "_build")
    files_removed, bytes_freed = 0, 0
    if os.path.isdir(build):
        for root, _dirs, files in os.walk(build):
            for fname in files:
                try:
                    bytes_freed += os.path.getsize(os.path.join(root, fname))
                    files_removed += 1
                except OSError:
                    pass
        shutil.rmtree(build, ignore_errors=True)
    # R-118: report partial-deletion survivors (e.g. a runtime DLL transiently
    # locked on Windows) instead of silently ignoring them — but `clean` is
    # best-effort cache clearing, so a survivor is informational in the envelope,
    # NOT a command failure: a flaky nonzero exit would break tooling/CI that just
    # wants the cache cleared and reads the rc.
    failures = []
    if os.path.isdir(build):
        for root, _dirs, files in os.walk(build):
            for fname in files:
                failures.append(os.path.relpath(os.path.join(root, fname), build))
    files_removed = max(0, files_removed - len(failures))
    info = {"ok": True, "cacheDir": cache, "filesRemoved": files_removed,
            "bytesFreed": bytes_freed, "deletionFailures": failures}
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope("sem.clean.v1", **info) + "\n")
    else:
        msg = f"cleaned {files_removed} files ({bytes_freed} bytes) from {build}"
        if failures:
            msg += f"; {len(failures)} could not be removed (in use?)"
        print(msg)
    return 0


def _all_diagnostics() -> dict:
    """Every diagnostic code — compile-time (SS/MD) + runtime (SSR) — merged."""
    return {**DIAGNOSTICS, **RUNTIME_DIAGNOSTICS}


def cmd_index(args) -> int:
    """Catalog every diagnostic code (compile-time + runtime) with tier + summary
    (sem.codeIndex.v1). The companion to `explain <code>`. (TOOL-5)"""
    entries = [{"code": code, "tier": spec.get("tier", ""),
                "summary": spec.get("summary", "")}
               for code, spec in sorted(_all_diagnostics().items())]
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope("sem.codeIndex.v1",
                                        count=len(entries), codes=entries) + "\n")
    else:
        for e in entries:
            print(f"{e['code']} ({e['tier']}): {e['summary']}")
    return 0


def _tokenize(text: str) -> list:
    """Lowercase alphanumeric word tokens."""
    import re
    return re.findall(r"[a-z0-9]+", text.lower())


def _spec_sections() -> list:
    """The language guide chunked by heading: [{title, text}]. Best-effort — the
    guide may be absent in a frozen build."""
    import os
    import re
    path = os.path.normpath(os.path.join(_bundle_dir(), "..", "docs", "LANGUAGE.md"))
    try:
        with open(path, encoding="utf-8") as fh:
            md = fh.read()
    except OSError:
        return []
    sections, title, buf = [], "LANGUAGE", []
    for line in md.splitlines():
        m = re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            if buf:
                sections.append({"title": title, "text": "\n".join(buf)[:2000]})
            title, buf = m.group(1).strip(), [m.group(1).strip()]
        else:
            buf.append(line)
    if buf:
        sections.append({"title": title, "text": "\n".join(buf)[:2000]})
    return sections


def _search_corpus(path: Optional[str] = None) -> list:
    """A multi-source searchable corpus for agentic retrieval. Each doc is
    {source, id, kind, title, text, ref} — `ref` is the command that fetches the
    full document. Sources: diagnostics, skills, task templates, agent rules, the
    language guide, and (when `path` is given) the project's entities."""
    docs = []
    for code, spec in _all_diagnostics().items():
        docs.append({
            "source": "diagnostic", "id": code, "kind": spec.get("tier", ""),
            "title": spec.get("summary", ""),
            "text": " ".join([code, spec.get("tier", ""), spec.get("summary", ""),
                              spec.get("found", ""), spec.get("suggested", "")]),
            "ref": f"explain {code}"})
    for name, sk in EAV_SKILLS.items():
        docs.append({"source": "skill", "id": name, "kind": "skill",
                     "title": sk["summary"],
                     "text": " ".join([name, sk["summary"], sk["body"]]),
                     "ref": f"skills {name}"})
    for name, tpl in EAV_TASK_TEMPLATES.items():
        text = " ".join([name] + tpl.get("rowsToAdd", [])
                        + tpl.get("rowsToVerify", []) + tpl.get("lintRules", []))
        docs.append({"source": "template", "id": name, "kind": "pattern",
                     "title": f"how to {name.replace('-', ' ')}",
                     "text": text, "ref": f"task {name}"})
    docs.append({"source": "rules", "id": "agent-rules", "kind": "rules",
                 "title": "EAV agent rules", "text": EAV_AGENT_RULES,
                 "ref": "agent-docs"})
    for sec in _spec_sections():
        docs.append({"source": "spec", "id": sec["title"], "kind": "spec",
                     "title": sec["title"], "text": sec["text"], "ref": "docs/LANGUAGE.md"})
    if path:
        try:
            program = parse_compact(_read_program_source(path))
            for n in program.order:
                e = program.entities[n]
                parts = [e.name, e.kind]
                for r in e.rows:
                    parts.append(r.predicate)
                    parts.extend(str(p) for p in r.payload)
                docs.append({"source": "entity", "id": e.name, "kind": e.kind,
                             "title": e.name, "text": " ".join(parts),
                             "ref": f"docs {path} --get {e.name}"})
        except (EavError, OSError):
            pass
    return docs


def _snippet(text: str, qterms: list, width: int = 160) -> str:
    """A text window around the earliest query-term hit."""
    low = text.lower()
    pos = min((p for p in (low.find(t) for t in qterms) if p != -1), default=-1)
    if pos == -1:
        return " ".join(text.split())[:width]
    start = max(0, pos - width // 3)
    chunk = " ".join(text[start:start + width].split())
    return ("…" if start else "") + chunk + ("…" if start + width < len(text) else "")


def _tfidf_rank(query: str, docs: list, limit: int) -> list:
    """Rank `docs` against `query` by TF-IDF with a title boost and prefix-
    tolerant matching. Returns [{source, id, kind, title, ref, score, snippet}]."""
    import math
    qterms = [t for t in _tokenize(query) if len(t) >= 2]
    if not qterms:
        return []
    doc_tokens = [_tokenize(d["text"]) for d in docs]
    df = {}
    for toks in doc_tokens:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    n_docs = len(docs)

    def idf(term):
        return math.log((n_docs + 1) / (df.get(term, 0) + 1)) + 1.0

    scored = []
    for doc, toks in zip(docs, doc_tokens):
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        title_toks = set(_tokenize(doc["title"]))
        score = 0.0
        for qt in qterms:
            freq = tf.get(qt, 0)
            if freq == 0 and len(qt) >= 3:  # prefix-tolerant (down-weighted)
                freq = sum(c for t, c in tf.items() if t.startswith(qt)) * 0.5
            if freq:
                contrib = (1 + math.log(freq)) * idf(qt)
                if qt in title_toks:
                    contrib *= 3.0
                score += contrib
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    return [{"source": d["source"], "id": d["id"], "kind": d["kind"],
             "title": d["title"], "ref": d["ref"], "score": round(s, 3),
             "snippet": _snippet(d["text"], qterms)}
            for s, d in scored[:limit]]


def cmd_search(args) -> int:
    """Unified relevance-ranked retrieval (TF-IDF) over the diagnostic registry,
    skills, task templates, agent rules, the spec, and — with `--path` — a
    project's entities (sem.search.v1). Real cross-source retrieval for agentic
    coding; `--source` filters by source. (TOOL-8)"""
    path = getattr(args, "path", None)
    # R-128: if --path is given it must actually index — an unreadable or
    # unparseable project is a path-error, not a silent fallback to generic docs
    # that an agent would mistake for "local entities were searched".
    if path:
        try:
            parse_compact(_read_program_source(path))
        except (EavError, OSError) as exc:
            if getattr(args, "json", False):
                sys.stdout.write(_json_envelope(
                    "sem.search.v1", ok=False, status="path-error", query=args.query,
                    path=path, count=0, matches=[], error=str(exc)) + "\n")
            else:
                sys.stderr.write(f"semanticscript: search --path {path!r}: {exc}\n")
            return 2
    docs = _search_corpus(path)
    wanted = getattr(args, "source", None)
    if wanted:
        docs = [d for d in docs if d["source"] in set(wanted)]
    results = _tfidf_rank(args.query, docs, getattr(args, "limit", None) or 20)
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope(
            "sem.search.v1", query=args.query, count=len(results),
            matches=results) + "\n")
    else:
        for r in results:
            print(f"[{r['source']}] {r['id']} ({r['kind']}) score {r['score']}")
            print(f"    {r['title']}")
            if r["snippet"]:
                print(f"    {r['snippet']}")
            print(f"    → {r['ref']}")
    return 0


def _program_target(program: Program) -> str:
    """The project's `target` (console by default)."""
    for ent in program.entities.values():
        if ent.kind == "project":
            row = ent.fact("target")
            if row and row.payload:
                return row.payload[0]
    return "console"


def cmd_bench(args) -> int:
    """Benchmark the pipeline — parse / lower / end-to-end JIT-run — reporting the
    best of N runs in milliseconds (sem.bench.v1). The run phase is skipped for a
    non-terminating target (e.g. webServer). (TOOL-6)"""
    import os
    import time
    runs = max(1, getattr(args, "runs", None) or 5)
    src = _read_program_source(args.path)
    # A project's `literalSource`/db paths are project-relative (the app is meant
    # to run from its own directory, like the test harness does with cwd=appdir),
    # so chdir into a project root for the lower/run phases — otherwise embeds
    # such as taskforge-web's `sql/schema.sql` fail to resolve.
    _bench_cwd = os.getcwd()
    # R-109: restore cwd on EVERY exit (parse/lower failure included), not only
    # after a clean loop — an in-process caller (MCP/test harness) must not be
    # left in the project directory when a bad project aborts the benchmark.
    try:
        if os.path.isdir(args.path) and is_project_root(args.path):
            os.chdir(args.path)
        runnable = _program_target(parse(src)) == "console"
        # R-108: a runtime trap in the JIT'd program would hard-exit (ss_panic ->
        # 134) and take the whole bench process with it, before sem.bench.v1 is
        # written. Probe the program once in an isolated child to classify its run
        # (ok / crashed / nonzero-exit / timed-out); only time the in-process run
        # when that child run was clean, so a trapping or hanging program is
        # reported as a benchmark result instead of killing the command.
        run_status = None
        if runnable:
            p_out, p_err, p_code = _record_run_full(src)
            run_status, _ = _classify_run(p_out, p_err, p_code)
        time_run = runnable and run_status == "ok"
        parse_t, lower_t, run_t = [], [], []
        for _ in range(runs):
            t0 = time.perf_counter()
            prog = parse(src)
            t1 = time.perf_counter()
            lower_to_llvm(prog)
            t2 = time.perf_counter()
            parse_t.append(t1 - t0)
            lower_t.append(t2 - t1)
            if time_run:
                t3 = time.perf_counter()
                # The JIT'd program writes to the OS stdout (fd 1) from the C
                # runtime, which Python-level redirection can't capture; mute fd 1
                # at the OS level so it doesn't pollute bench's own (--json).
                sys.stdout.flush()
                devnull = os.open(os.devnull, os.O_WRONLY)
                saved = os.dup(1)
                os.dup2(devnull, 1)
                try:
                    jit_run(prog)
                except OSError:
                    pass  # a trapping program still yields a timing
                finally:
                    sys.stdout.flush()
                    os.dup2(saved, 1)
                    os.close(saved)
                    os.close(devnull)
                run_t.append(time.perf_counter() - t3)
    finally:
        if os.getcwd() != _bench_cwd:
            os.chdir(_bench_cwd)

    def ms(xs):
        return round(min(xs) * 1000, 3) if xs else None
    result = {
        "path": args.path, "runs": runs, "runnable": runnable,
        "runStatus": run_status,
        "parseMsBest": ms(parse_t), "lowerMsBest": ms(lower_t),
        "runMsBest": ms(run_t),
    }
    totals = [v for v in (result["parseMsBest"], result["lowerMsBest"],
                          result["runMsBest"]) if v is not None]
    result["totalMsBest"] = round(sum(totals), 3)
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope("sem.bench.v1", **result) + "\n")
    else:
        run_s = f" run {result['runMsBest']}ms" if runnable else " (run skipped)"
        print(f"bench {args.path} (best of {runs}): "
              f"parse {result['parseMsBest']}ms lower {result['lowerMsBest']}ms"
              f"{run_s}")
    return 0


def cmd_repin(args) -> int:
    """Re-pin dependencies: regenerate `build.sem.lock` from a `build.sem`
    manifest via MVS (deterministic). `--check` verifies the existing lock is
    current without writing (CI gate). (TOOL-7; sem.repin.v1)

    The network/registry-dependent legacy ops (download/get/latest/update/self)
    are deferred until a package registry exists (no remote fetch in beta)."""
    import os
    path = args.path
    if os.path.isdir(path):
        build_path = os.path.join(path, "build.sem")
    else:
        build_path = path  # a build.sem manifest (or any project manifest)
    want_json = getattr(args, "json", False)

    def _repin_fail(msg, status):
        # R-115: a repin failure is a sem.repin.v1 envelope under --json, not a
        # plaintext stderr line an agent can't parse.
        if want_json:
            sys.stdout.write(_json_envelope(
                "sem.repin.v1", ok=False, status=status, error=msg) + "\n")
        else:
            sys.stderr.write(f"semanticscript: {msg}\n")
        return 2

    if not os.path.exists(build_path):
        return _repin_fail(f"no build.sem at {build_path}", "path-error")
    try:
        with open(build_path, encoding="utf-8") as fh:
            build_program = parse(fh.read())
        lock_text = mod_tidy(build_program)
    except (EavError, OSError) as exc:
        return _repin_fail(str(exc), "compiler-error")
    if not lock_text.endswith("\n"):
        lock_text += "\n"
    lock_path = os.path.join(os.path.dirname(os.path.abspath(build_path)),
                             "build.sem.lock")
    existing = ""
    if os.path.exists(lock_path):
        with open(lock_path, encoding="utf-8") as fh:
            existing = fh.read()
    up_to_date = existing == lock_text

    if getattr(args, "check", False):
        if getattr(args, "json", False):
            sys.stdout.write(_json_envelope(
                "sem.repin.v1", lockPath=lock_path, upToDate=up_to_date,
                wrote=False) + "\n")
        else:
            print(f"build.sem.lock {'up to date' if up_to_date else 'STALE'}: "
                  f"{lock_path}")
        return 0 if up_to_date else 1

    # R-115: write the lock atomically (temp + fsync + replace) so a crash or a
    # concurrent run can never truncate the existing lock that future checks treat
    # as a source-of-truth input.
    _tmp = f"{lock_path}.tmp{os.getpid()}"
    with open(_tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lock_text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(_tmp, lock_path)
    if want_json:
        sys.stdout.write(_json_envelope(
            "sem.repin.v1", lockPath=lock_path, upToDate=True,
            wrote=not up_to_date) + "\n")
    else:
        print(f"{'unchanged' if up_to_date else 'wrote'} {lock_path}")
    return 0


def _is_trap_returncode(rc: int) -> bool:
    """True if a subprocess return code indicates a hardware/guard trap — a POSIX
    fatal signal or a Windows NTSTATUS exception code — rather than a normal
    nonzero exit (R-088)."""
    if rc < 0:
        return True  # POSIX: killed by a signal (SIGILL/SIGSEGV/SIGFPE/SIGABRT)
    return (rc & 0xFFFFFFFF) >= 0xC0000000  # Windows NTSTATUS exception band


def cmd_run(args) -> int:
    """JIT-compile and execute the program; return its process exit code.

    R-088: by default the JIT'd entry runs in an isolated subprocess, so a
    runtime trap surfaces as the child's exit code/signal and is reported here as
    a clean, stable trap status — never an uncaught Python traceback. WS1-130:
    guard sites (divide/modulo by zero, violated numeric preconditions) now lower
    to a structured `ss_panic` that prints `code · kind · op · row · reason ·
    operands` to stderr and exits 134; a residual bare trap (overflow / deep
    recursion, not yet routed through ss_panic) still surfaces as SSR0001."""
    # R-095: `run --json` is a machine-readable run — capture the program's
    # stdout/stderr/exitCode into a sem.run.v1 envelope (with a structured panic
    # on a trap) instead of streaming raw output past the `--json` request.
    if getattr(args, "json", False):
        src = _read_program_source(args.path)
        entry = getattr(args, "entry", None)
        # R-162: --strict gates the JSON run too — a strict lint error is reported
        # as a lint-error envelope, not silently skipped.
        if getattr(args, "strict", False):
            try:
                strict_errs = [d for d in _filter_diagnostics_strict(lint(parse_compact(src)), True)
                               if d.severity == "error"]
            except EavError:
                strict_errs = []  # a parse error surfaces through the run below
            if strict_errs:
                sys.stdout.write(_json_envelope(
                    "sem.run.v1", ok=False, status="lint-error", exitCode=1,
                    stdout="", stderr="\n".join(d.render() for d in strict_errs),
                    stdoutLines=[]) + "\n")
                return 1
        # R-159: honor --entry by running that operation as the entry in the child.
        if entry:
            out, err, code = _record_run_entry(src, entry)
        else:
            out, err, code = _record_run_full(src)
        status, panic = _classify_run(out, err, code)
        payload = dict(
            ok=(code == 0), status=status, exitCode=code, stdout=out, stderr=err,
            stdoutLines=_stdout_lines(out))  # R-127
        if panic is not None:
            payload["panic"] = panic
        sys.stdout.write(_json_envelope("sem.run.v1", **payload) + "\n")
        return code

    program = parse_compact(_read_program_source(args.path))
    # WS2-071: --strict blocks T3 warnings
    if getattr(args, "strict", False):
        diags = lint(program)
        diags = _filter_diagnostics_strict(diags, True)
        errors = [d for d in diags if d.severity == "error"]
        if errors:
            for d in errors:
                sys.stderr.write(d.render() + "\n")
            return 1
    import os

    def _trap_report(detail: str) -> None:
        sys.stdout.flush()
        sys.stderr.write(
            "semanticscript: SSR0001: program trapped at runtime (guard trap / illegal "
            "instruction — e.g. divide-by-zero, out-of-bounds, overflow, or deep "
            f"recursion); {detail}\n")

    # Windows surfaces a JIT guard trap as a catchable in-process OSError, so it
    # needs no subprocess; a stdin program and the isolated POSIX child also run
    # in-process. POSIX delegates to an isolated child (below) because a trap
    # there is an uncatchable fatal signal.
    entry = getattr(args, "entry", None)  # R-102: run a named op as the entry
    if getattr(args, "jit_child", False) or args.path == "-" or os.name == "nt":
        sys.stdout.flush()
        try:
            return jit_run(program, entry=entry)
        except OSError as exc:
            _trap_report(str(exc))
            return 134  # stable "aborted" exit (128 + SIGABRT)
    import subprocess
    sys.stdout.flush()
    child_argv = [sys.executable, os.path.abspath(__file__), "run",
                  "--_jit-child", args.path]
    if entry:
        child_argv += ["--entry", entry]
    child = subprocess.run(child_argv)
    rc = child.returncode
    if _is_trap_returncode(rc):
        _trap_report(f"isolated child terminated with {rc & 0xFFFFFFFF:#010x}")
        return 134
    return rc


def build_executable(program: Program, out_path: str,
                     platform: Optional[str] = None) -> str:
    """Compile a program to a native executable: lower to LLVM IR, then drive a C
    compiler over the IR plus any native runtime sources the program's
    runtimeBinding symbols need (manifest-driven). Returns the exe path. R-017:
    `platform` selects the declared `platform` entity to lower for (triple +
    forPlatform); a real cross-toolchain for a non-host triple is out of scope
    (R-031), so the host compiler still drives the link."""
    import os
    import subprocess
    import tempfile
    module = lower_to_llvm(program, platform)
    cc = _find_c_compiler()
    if cc is None:
        raise EavError("no C compiler found to build an executable "
                       "(set SEMANTICSCRIPT_CC, or install clang/zig)")
    rt = _runtime_dir()
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    # R-015: write scratch IR into the (writable) output directory, never into
    # the runtime bundle, which may be read-only or shared across concurrent
    # builds. mkstemp keeps the name unique so parallel builds do not collide.
    ll_fd, ll_path = tempfile.mkstemp(suffix=".ll", dir=out_dir)
    with os.fdopen(ll_fd, "w", encoding="utf-8") as fh:
        fh.write(str(module))
    cmd = list(cc) + ["-O2", ll_path, "-o", out_path]
    # Pin clang to the module's own target triple. On an ARM64 host where llvmlite
    # is x64-emulated, the IR triple is x86_64 while clang defaults to ARM64, so
    # clang would "override the module target triple" and fail the link. Passing
    # the module triple makes the architectures agree (a no-op when they already
    # match, e.g. an x64 CI host). Mirrors the runtime-lib build above.
    if getattr(module, "triple", ""):
        cmd.append("--target=" + module.triple)
    # A native exe needs a `main` symbol so the linker infers the console
    # subsystem + CRT startup. The console entry op is conventionally named
    # `main`, but the webServer (and any non-`main` entry) is named after the
    # project entry, leaving no `main` and a "subsystem must be defined" link
    # error. Emit a tiny C `main` that tail-calls the named entry (its IR
    # signature is `i32()` — a console entry returns ExitCode, SS1191).
    wrap_path = None
    entry_fn = _entry_name(program)
    if entry_fn != "main":
        wrap_fd, wrap_path = tempfile.mkstemp(suffix=".c", dir=out_dir)
        with os.fdopen(wrap_fd, "w", encoding="utf-8") as fh:
            fh.write(f"extern int {entry_fn}(void);\n"
                     f"int main(void) {{ return {entry_fn}(); }}\n")
        cmd.append(wrap_path)
    # WS1-130: the structured-trap helper `ss_panic` is compiler-injected at
    # guard sites (not a program runtimeBinding), so it is always linked in.
    # WS3-016: `ss_ffi_add` is the FFI out-param ABI demo symbol — always linked
    # so a program binding it builds natively (the JIT registers it in-process).
    # ss_native_libc.c: a real `printf` symbol for the native link — the UCRT
    # exposes printf only as a header inline, so the IR's direct printf call
    # (console integer/float output) is otherwise undefined at link time.
    for _always in ("ss_panic.c", "ss_ffi.c", "ss_native_libc.c"):
        _src = os.path.normpath(os.path.join(rt, _always))
        if os.path.exists(_src):
            cmd.append(_src)
    # R-018/R-013: resolve each runtime library's link inputs for the host
    # platform so Windows-only libs (ws2_32) are appended on Windows and
    # POSIX-only libs (pthread/dl/m) are appended on Unix — never both.
    for lib in _runtime_libs_for(program):
        resolved = _resolve_runtime_links(lib, _host_platform_name())
        for s in resolved["sources"]:
            cmd.append(_runtime_link_path(s))
        for inc in resolved["include"]:
            cmd.append("-I" + _runtime_link_path(inc))
        for d in resolved["defines"]:
            cmd.append("-D" + d)
        for libname in resolved["libs"]:
            cmd.append("-l" + libname)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=_build_timeout_seconds())
    except subprocess.TimeoutExpired:  # R-107
        raise EavError(
            f"native build exceeded {_build_timeout_seconds():g}s and was "
            f"terminated (set SEMANTICSCRIPT_BUILD_TIMEOUT to adjust)")
    finally:
        for _scratch in (ll_path, wrap_path):
            if _scratch:
                try:
                    os.unlink(_scratch)
                except OSError:
                    pass
    if proc.returncode != 0:
        raise EavError(f"native build failed: {proc.stderr.strip()}")
    return out_path


_WASM_RUNNER = """\
// Generated by `semanticscript wasm`. Run with: node <this file>
const fs = require('fs');
const path = require('path');
const bytes = fs.readFileSync(path.join(__dirname, %(wasm)r));
// R-122: auto-stub any host imports so the module always instantiates (a
// no-import pure-compute module ignores this). A module that imports console /
// DOM / runtime host functions needs a REAL host adapter for those effects —
// these stubs are no-ops that return 0, so only the module's pure logic runs.
const importObject = new Proxy({}, { get: () =>
  new Proxy({}, { get: () => (() => 0) }) });
WebAssembly.instantiate(bytes, importObject).then(({ instance }) => {
  const result = instance.exports[%(entry)r]();
  console.log(%(entry)r + '() = ' + result);
  process.exit((result | 0) & 0xff);
});
"""


def _wasm_import_count(data: bytes) -> int:
    """Count the imports declared in a `.wasm` binary's import section (R-122), so
    `wasm` can tell the user whether the module needs a host adapter. 0 means a
    self-contained pure-compute module the generated runner runs as-is."""
    if data[:4] != b"\x00asm":
        return 0

    def uleb(p):
        result = shift = 0
        while p < len(data):
            byte = data[p]
            p += 1
            result |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                break
            shift += 7
        return result, p

    pos = 8  # 4-byte magic + 4-byte version
    while pos < len(data):
        sec_id = data[pos]
        pos += 1
        size, pos = uleb(pos)
        if sec_id == 2:  # the import section
            count, _ = uleb(pos)
            return count
        pos += size
    return 0


def build_wasm(program: Program, out_path: str):
    """Lower a program to a WebAssembly module (WS3-161): emit LLVM IR with the
    wasm32 triple, then drive clang `--target=wasm32` + wasm-ld to a `.wasm` that
    exports the entry operation. Under `-nostdlib` there is no console/heap
    runtime, so this targets the pure-compute subset whose result is the entry's
    i32 return (run under node). Returns (wasm_path, entry_name)."""
    import os
    import subprocess
    import tempfile
    module = lower_to_llvm(program)
    module.triple = "wasm32-unknown-unknown"
    try:
        module.data_layout = ""
    except Exception:
        pass
    entry = _entry_name(program)
    cc = _find_c_compiler()
    if cc is None:
        raise EavError("no clang found to build wasm (set SEMANTICSCRIPT_CC, or install LLVM)")
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    ll_fd, ll_path = tempfile.mkstemp(suffix=".ll", dir=out_dir)
    with os.fdopen(ll_fd, "w", encoding="utf-8") as fh:
        fh.write(str(module))
    cmd = list(cc) + ["--target=wasm32", "-nostdlib", "-Wl,--no-entry",
                      "-Wl,--export=" + entry,
                      # Undefined symbols (a program's runtimeBinding targets,
                      # e.g. the DOM `dom_*` host functions) become wasm imports
                      # the JS/browser host supplies — the wasm<->JS interop the
                      # DOM adapter relies on (WS3-161/§document).
                      "-Wl,--allow-undefined", "-O2", "-o", out_path, ll_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=_build_timeout_seconds())
    except subprocess.TimeoutExpired:  # R-107
        raise EavError(
            f"wasm build exceeded {_build_timeout_seconds():g}s and was "
            f"terminated (set SEMANTICSCRIPT_BUILD_TIMEOUT to adjust)")
    finally:
        try:
            os.unlink(ll_path)
        except OSError:
            pass
    if proc.returncode != 0:
        raise EavError(f"wasm build failed: {proc.stderr.strip()}")
    return out_path, entry


def cmd_wasm(args) -> int:
    """Compile a pure-compute program to a `.wasm` module + a node runner."""
    import os
    program = parse_compact(_read_program_source(args.path))
    out = getattr(args, "output", None) or (os.path.splitext(args.path)[0] + ".wasm")
    wasm_path, entry = build_wasm(program, out)
    runner = os.path.splitext(wasm_path)[0] + ".run.cjs"
    with open(runner, "w", encoding="utf-8") as fh:
        fh.write(_WASM_RUNNER % {"wasm": os.path.basename(wasm_path), "entry": entry})
    # R-122: report the import set. A module with imports is not a turnkey
    # artifact — the generated runner stubs the host so it instantiates, but
    # console/DOM/runtime effects need a real host adapter for correct behavior.
    with open(wasm_path, "rb") as fh:
        imports = _wasm_import_count(fh.read())
    sys.stdout.write(
        f"wasm:   {wasm_path}\nrunner: {runner}\nentry:  {entry}\nimports: {imports}\n")
    if imports:
        sys.stdout.write(
            f"note:   this module imports {imports} host function(s); the generated "
            f"runner stubs them (effects are no-ops). Provide a real host adapter "
            f"for console/DOM/runtime behavior.\n")
    return 0


# Versioned JSON surfaces semanticscript exposes (the sem.*.v1 contract, WS4-111).
# Every versioned machine surface a command can emit. R-123: this must list
# exactly the `sem.*.v1` envelopes the commands actually write — no more, no less
# — so `version --json` is a trustworthy contract-discovery surface. The
# test_version_surface_registry_complete conformance test keeps it in lockstep.
SEM_SURFACES = (
    "sem.version.v1", "sem.agentDocs.v1", "sem.skills.v1", "sem.check.v1",
    "sem.readiness.v1", "sem.eval.v1", "sem.deps.v1", "sem.fixPlan.v1",
    "sem.context.v1", "sem.symbols.v1", "sem.patch.v1", "sem.test.v1",
    "sem.size.v1", "sem.dev.v1", "sem.slice.v1", "sem.docs.v1",
    "sem.docsIndex.v1", "sem.docsSearch.v1", "sem.task.v1", "sem.new.v1",
    "sem.build.v1", "sem.run.v1", "sem.error.v1",
    # R-123: surfaces that were live but unlisted.
    "sem.bench.v1", "sem.clean.v1", "sem.codeIndex.v1", "sem.graph.v1",
    "sem.inspectIr.v1", "sem.lint.v1", "sem.query.v1", "sem.repin.v1",
    "sem.search.v1", "sem.status.v1",
)

# R-053: standard.* catalogs that ship a `.semsig` contract but whose runtime is
# deferred. They are explicitly *experimental* — owned and parked here, distinct
# from the semsc-only libc mirrors — and are NOT part of the sanctioned v0.3
# surface (not advertised as ready). Promotion to sanctioned requires a real
# runtime plus a runtime smoke test; until then app ports may reference them but
# execution stays deferred. (bcrypt -> R-066, event -> R-064, gui -> R-042,
# log -> R-065.)
EXPERIMENTAL_STDLIB_MODULES = frozenset({"bcrypt", "event", "gui", "log"})

EAV_AGENT_RULES = (
    "EAV-Steps: flat semantic tape, one row = one record, column-1 subject, "
    "column-2 predicate. No expressions/infix/parens/commas/braces. Every entity "
    "opens with `<name> is <kind>`; calls are multi-row (is call / in OP / invokes "
    "TARGET / arg / out|catch|discards). Effects need a covering `uses`+`grants` "
    "capability. Stable loop: check -> fix --plan -> patch -> fmt --check -> test. "
    "Run (JIT) with `semanticscript run <file|dir>`; build a native exe (console "
    "or webServer) with `semanticscript build <path> -o out` (clang/zig needed for "
    "the native runtime). The compiler is self-contained under `semanticscript/`; "
    "worked apps live in `apps/`; start at docs/getting-started.md (the full "
    "language guide is docs/LANGUAGE.md). Agent surface: `agent-docs`, `skills "
    "[name]`, `search <query>` (ranked retrieval), `explain <CODE>`, `check --json`, "
    "`eval`, `docs <file>`, and the stdio `mcp` server (19 tools)."
)

# name -> {summary, body}. `skills` (no arg) lists summaries; `skills <name>`
# returns the full body (the legacy list-vs-get contract). Content tracks the
# current toolchain — self-contained runtime, native build, the apps, the MCP.
EAV_SKILLS = {
    "eav-start": {
        "summary": "Load version-matched rules, then inspect with check/graph/slice.",
        "body": (
            "Start every EAV task by loading the rules (`semanticscript agent-docs`) "
            "and the syntax skill (`semanticscript skills eav-syntax`). Inspect a "
            "program before editing: `check --json` (parse+lint), `symbols`/`context` "
            "(entity graph + project envelope), `graph`/`slice` (dependencies), `size` "
            "(footprint). Edit with the stable loop: `check` -> `fix --plan` (repair "
            "plan from diagnostics) -> `patch` (apply) -> `fmt --check` -> `test`. "
            "Never hand-edit IR; the compiler owns lowering."),
    },
    "eav-syntax": {
        "summary": "Subject-first rows; runtimeBinding for native ABIs; §26 .semsig.",
        "body": (
            "Every line is `<subject> <predicate> <payload>` — token 1 is the subject, "
            "token 2 the predicate. No expressions, infix, parens, commas, or braces. "
            "An entity opens with `<name> is <kind>` (operation/call/capability/record/"
            "enum/error/storage/webServer/module/project/alias/...). A call is several "
            "rows: `is call`, `in <owner>`, `invokes <target>`, `arg <slot> <Type> "
            "<value>`, then `out <bind> <Type>` | `catch <err> <ErrType>` | `discards "
            "\"why\"`. An operation declares `out`, `effect`, `uses` (a capability that "
            "`grants` the effect), and `do <call>` steps. Native ABIs bind through "
            "`body runtimeBinding <symbol>` with the typed contract in a §26 `.semsig`. "
            "Islands: `body json|sql|html` + indented content embed literally."),
    },
    "eav-run": {
        "summary": "JIT with `semanticscript run`; native exe with `semanticscript build`.",
        "body": (
            "Run a single file or a project directory with `semanticscript run <path>` "
            "(JIT via llvmlite; no C compiler needed for pure console/compute). Build a "
            "standalone native executable with `semanticscript build <path> -o out` — "
            "works for `target console` and `target webServer`; needs clang or `zig cc` "
            "for the native runtime libs (sqlite/http/json/bcrypt/...). A project is a "
            "directory with `build.sem` + `src/`. See `apps/` for runnable examples and "
            "`docs/getting-started.md` for a hello-world."),
    },
    "eav-toolchain": {
        "summary": "The CLI + the stdio MCP server surface.",
        "body": (
            "Core: `run build wasm check lint fmt test eval`. Inspect: `lower`/`emit-ir`/"
            "`inspect-ir` (IR), `symbols context deps graph slice size describe trace`. "
            "Agent: `agent-docs`, `skills`, `search <query>` (relevance-ranked retrieval "
            "across diagnostics/skills/templates/the language guide/a project — the "
            "agentic search), `explain <CODE>`, `docs <file>` (per-file entity docs/get/"
            "search), `query <dim>`, `index`, `status`, `fix --plan` + `patch`/"
            "`verify-patch`, `scaffold`/`new`. Structured output is a versioned "
            "`sem.<tool>.v1` JSON envelope (pass `--json` where offered). The `mcp` "
            "subcommand is a stdio JSON-RPC server exposing 19 tools — version, "
            "agent_docs, skills, readiness, status, index, search, explain, docs, check, "
            "graph, query, deps, context, symbols, size, eval, fix_plan, test."),
    },
    "eav-apps": {
        "summary": "Worked patterns under apps/ (web API, TUI, HTTP).",
        "body": (
            "Learn idioms from the runnable apps: `taskforge-web` (a sqlite+bcrypt+json"
            "+log JSON REST API on the `webServer` target — auth, sessions, CRUD), "
            "`taskforge-tui` (a console state machine over `c.*`/`pointer.*` byte ops), "
            "`http-runtime-gauntlet` (the `webServer` codegen + `http.*` request/"
            "response), `taskforge-api-client` (a `net.fetchText` HTTP client), and "
            "`event-stream-smoke`/`desktop-window-smoke` (event + headless GUI "
            "runtimes). All are e2e-tested in `tests/test_apps.py`."),
    },
}


def _next_command(argv: list, description: str, replayable: bool = True) -> dict:
    """A machine-facing next-step descriptor (README §24/§32.3 #20)."""
    return {"argv": argv, "command": "semanticscript " + " ".join(argv),
            "replayable": replayable, "description": description}


def _json_envelope(surface: str, **payload) -> str:
    import json
    body = {"surface": surface, "version": "v1", "ok": True}
    body.update(payload)
    return json.dumps(body, indent=2)


# MCP tool registry. Each entry is data-driven so tools/list (the advertised
# inputSchema) and _mcp_dispatch (the argv it builds) never drift:
#   argv : the CLI prefix (usually `--json` so the agent gets a sem.<tool>.v1 body)
#   desc : the one-line tool description shown to the agent
#   path : True if the CLI takes a positional source/project `path` (-> required)
#   args : extra inputs as (name, positional?, required?, description); positionals
#          are appended in declared order (before `path`), flags become `--name v`.
# Keep this in sync with the `eav-toolchain` skill body, which names the set.
EAV_MCP_TOOLS = {
    # --- registry-free / agent guidance ---
    "version": {"argv": ["version", "--json"], "desc": "Contract + release version surface",
                "path": False, "args": []},
    "agent_docs": {"argv": ["agent-docs"], "desc": "Version-matched SemanticScript agent rules",
                   "path": False, "args": []},
    "skills": {"argv": ["skills"], "desc": "SemanticScript agent skills (list; pass `skill` for a body)",
               "path": False, "args": [("skill", True, False, "skill name to fetch its full body")]},
    "readiness": {"argv": ["readiness", "--json"], "desc": "Environment lane status",
                  "path": False, "args": []},
    "status": {"argv": ["status", "--json"], "desc": "Toolchain + native-target status",
               "path": False, "args": []},
    "index": {"argv": ["index", "--json"], "desc": "Repository code index (entities, diagnostics, surfaces)",
              "path": False, "args": []},
    # --- relevance-ranked retrieval / docs (the agentic search surface) ---
    "search": {"argv": ["search", "--json"],
               "desc": "Relevance-ranked retrieval across diagnostics, skills, task templates, "
                       "the language guide, and (with `path`) a project's entities — the agentic search",
               "path": False,
               "args": [("query", True, True, "natural-language search query"),
                        ("source", False, False, "restrict to one source: diagnostic|skill|template|rules|spec|entity"),
                        ("limit", False, False, "max results (default 8)"),
                        ("path", False, False, "also index this project's entities")]},
    "explain": {"argv": ["explain"], "desc": "Explain one diagnostic code (tier, cause, suggested fix)",
                "path": False, "args": [("code", True, True, "diagnostic code, e.g. SS1502")]},
    "docs": {"argv": ["docs"], "desc": "Per-file entity docs (list; pass `get` for one entity, `search` to rank)",
             "path": True,
             "args": [("search", False, False, "keyword-ranked query within the file"),
                      ("get", False, False, "entity name to fetch (fuzzy-tolerant)")]},
    # --- program analysis (require a source/project path) ---
    "check": {"argv": ["check"], "desc": "Source lane: parse + lint status", "path": True, "args": []},
    "graph": {"argv": ["graph", "--json"], "desc": "Call / control-flow graph",
              "path": True, "args": [("kind", False, False, "calls|control (default calls)")]},
    "query": {"argv": ["query", "--json"],
              "desc": "Query a semantic dimension of a program (e.g. effects, capabilities, calls)",
              "path": True, "args": [("dimension", True, True, "dimension to extract, e.g. effects")]},
    "deps": {"argv": ["deps"], "desc": "Dependency graph", "path": True, "args": []},
    "context": {"argv": ["context"], "desc": "Project envelope", "path": True, "args": []},
    "symbols": {"argv": ["symbols"], "desc": "Full entity graph", "path": True, "args": []},
    "size": {"argv": ["size"], "desc": "Footprint probe", "path": True, "args": []},
    "eval": {"argv": ["eval"], "desc": "JIT-run a snippet", "path": True, "args": []},
    "fix_plan": {"argv": ["fix", "--plan"], "desc": "Repair plan from diagnostics", "path": True, "args": []},
    "test": {"argv": ["test"], "desc": "Run tag-test operations", "path": True, "args": []},
}


def _mcp_dispatch(tool: str, arguments: dict):
    """Run a tool by building its argv and capturing (stdout, stderr, exitCode).
    R-126: stderr and the integer rc are captured too, so a failed tool call can
    surface its actionable diagnostic instead of looking like an empty success."""
    import contextlib
    import io
    spec = EAV_MCP_TOOLS.get(tool)
    if spec is None:
        return f'{{"error": "unknown tool {tool}"}}', "", 2
    argv = list(spec["argv"])
    # positional args (in declared order), then the source/project path,
    for name, positional, _req, _desc in spec["args"]:
        if positional and arguments.get(name) is not None:
            argv.append(str(arguments[name]))
    if spec["path"] and arguments.get("path") is not None:
        argv.append(str(arguments["path"]))
    # then flag args.
    for name, positional, _req, _desc in spec["args"]:
        if not positional and arguments.get(name) is not None:
            argv += [f"--{name}", str(arguments[name])]
    out_buf, err_buf, rc = io.StringIO(), io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = main(argv) or 0
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return out_buf.getvalue(), err_buf.getvalue(), rc


def mcp_handle(request: dict):
    """Handle one MCP JSON-RPC request (initialize / tools/list / tools/call).

    Returns the response dict, or None for a JSON-RPC *notification* — a request
    with no `id` member (e.g. `notifications/initialized`), which per the spec
    must not be answered (R-111)."""
    # R-125: a non-object top-level frame (e.g. a JSON-array batch or a bare
    # scalar) is an invalid request, not a server crash.
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {
            "code": -32600,
            "message": "invalid request: expected a JSON object (batches are not supported)"}}
    method = request.get("method")
    if "id" not in request:
        return None  # notification: acknowledged silently, no response
    rid = request.get("id")
    base = {"jsonrpc": "2.0", "id": rid}
    if method == "initialize":
        return {**base, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "semanticscript", "version": CONTRACT_VERSION},
            "capabilities": {"tools": {}}}}
    if method == "tools/list":
        # R-117: an accurate per-tool path schema. Most path tools accept a single
        # file OR a project directory (they read via _read_program_source); the
        # snippet/repair tools read a single file only, so they must not advertise
        # a project path that would fail at runtime.
        single_file = {"eval", "fix_plan"}
        tools = []
        for name, spec in EAV_MCP_TOOLS.items():
            props, required = {}, []
            if spec["path"]:
                props["path"] = {"type": "string", "description": (
                    "SemanticScript source file"
                    if name in single_file
                    else "SemanticScript source file or project directory")}
                required.append("path")
            for argname, _positional, req, desc in spec["args"]:
                props[argname] = {"type": "string", "description": desc}
                if req:
                    required.append(argname)
            schema = {"type": "object", "properties": props}
            if required:
                schema["required"] = required
            tools.append({"name": name, "description": spec["desc"], "inputSchema": schema})
        return {**base, "result": {"tools": tools}}
    if method == "tools/call":
        params = request.get("params", {})
        if not isinstance(params, dict):  # R-125
            return {**base, "error": {"code": -32602,
                                      "message": "invalid params: expected an object"}}
        name = params.get("name", "")
        if name not in EAV_MCP_TOOLS:
            # R-011: an unknown or missing tool is a JSON-RPC error (invalid
            # params), not a text-content "success" that masks the failure.
            return {**base, "error": {
                "code": -32602,
                "message": (f"unknown tool: {name!r}" if name
                            else "missing tool name"),
                "data": {"available": sorted(EAV_MCP_TOOLS)}}}
        # R-099: validate required inputs up front. A missing required arg used to
        # let argparse fail to stderr while an empty stdout was wrapped as a
        # successful tools/call — a masked failure. Now it is a JSON-RPC error.
        spec = EAV_MCP_TOOLS[name]
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):  # R-125
            return {**base, "error": {"code": -32602,
                                      "message": "invalid arguments: expected an object"}}
        required = (["path"] if spec["path"] else []) + [a[0] for a in spec["args"] if a[2]]
        missing = [r for r in required if arguments.get(r) in (None, "")]
        if missing:
            return {**base, "error": {
                "code": -32602,
                "message": f"missing required argument(s) for {name!r}: {', '.join(missing)}",
                "data": {"required": required}}}
        text, stderr, rc = _mcp_dispatch(name, arguments)
        # R-126: a failed tool call is not an empty success — surface the rc and
        # the actionable diagnostic (the envelope on stdout, else stderr) and mark
        # the result as an error so the agent doesn't read a failure as success.
        content_text = text if text.strip() else stderr.strip()
        result = {"content": [{"type": "text", "text": content_text}]}
        if rc != 0:
            result["isError"] = True
        return {**base, "result": result}
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
    """The canonical `semanticscript new` skeleton (§28.2) as a {relpath: content} map."""
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
        f'{pas} languageVersion "1.0"\n{pas} toolchain "semanticscript"\n'
    )
    return {
        "build.sem": build,
        "src/main.sem": main,
        "src/main.test.sem": test,
        ".gitignore": "dist/\n",
        "tests/golden/.gitkeep": "",
    }


def cmd_new(args) -> int:
    """Scaffold a canonical EAV project tree (§28.2). R-005: refuse to clobber
    existing scaffold files unless `--force` — a mistyped path must not destroy
    an existing `build.sem`/`src/main.sem`. The collision list is reported in
    `sem.new.v1` so the failure is machine-readable, mirroring the §32.3 #20
    stale-file protection used by the patch loop."""
    import os
    root = args.path
    if getattr(args, "enable_docs_index", False):
        # R-004: the flag implied scaffolding work, but persistent docs-index
        # generation is not implemented yet (tracked by R-051). Reject it with a
        # structured diagnostic instead of silently no-op'ing an explicit flag.
        sys.stdout.write(_json_envelope(
            "sem.new.v1", ok=False, status="unsupported-flag", root=root,
            unsupported=["--enable-docs-index"], created=[],
            hint="persistent docs-index scaffolding is not implemented yet "
                 "(R-051); run `new` without --enable-docs-index, or use the "
                 "in-memory `docs search` surface") + "\n")
        return 2
    files = _new_project_files(os.path.basename(os.path.normpath(root)))
    collisions = sorted(
        rel for rel in files
        if os.path.exists(os.path.join(root, rel))
    )
    if collisions and not getattr(args, "force", False):
        sys.stdout.write(_json_envelope(
            "sem.new.v1", ok=False, status="collision", root=root,
            collisions=collisions, created=[],
            hint="pass --force to overwrite the listed files") + "\n")
        return 2
    created = []
    for rel, content in files.items():
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        created.append(rel)
    sys.stdout.write(_json_envelope(
        "sem.new.v1", ok=True, status="created", root=root,
        created=sorted(created), overwritten=collisions) + "\n")
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
            # R-011: surface a JSON-RPC parse error instead of silently dropping
            # the line, so a malformed request is observable to the client.
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        try:
            response = mcp_handle(request)
        except Exception as exc:  # R-125: a malformed frame must not kill the loop
            rid = request.get("id") if isinstance(request, dict) else None
            response = {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32603, "message": f"internal error: {exc}"}}
        if response is not None:  # R-111: notifications (no id) get no reply
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


def cmd_version(args) -> int:
    """Emit the semanticscript contract version surface (sem.version.v1)."""
    if getattr(args, "json", False):
        sys.stdout.write(_json_envelope(
            "sem.version.v1", contractVersion=CONTRACT_VERSION, compiler="semanticscript",
            surfaces=list(SEM_SURFACES)) + "\n")
    else:
        sys.stdout.write(f"semanticscript {CONTRACT_VERSION}\n")
    return 0


def cmd_agent_docs(args) -> int:
    """Emit the version-matched EAV agent rules (sem.agentDocs.v1)."""
    sys.stdout.write(_json_envelope(
        "sem.agentDocs.v1", contractVersion=CONTRACT_VERSION,
        rules=EAV_AGENT_RULES) + "\n")
    return 0


def cmd_skills(args) -> int:
    """List EAV agent skills, or get full skill bodies by name (sem.skills.v1).

    `skills` with no names lists summaries; `skills <name>...` returns the full
    body for each named skill — the legacy list-vs-get contract."""
    names = getattr(args, "names", None)
    if names:
        items, missing = [], []
        for k in names:
            spec = EAV_SKILLS.get(k)
            if spec is not None:
                items.append({"name": k, "summary": spec["summary"],
                              "body": spec["body"]})
            else:
                missing.append(k)
        if missing:
            # R-121: a requested skill that doesn't exist is NOT an empty success —
            # an agent typo would otherwise proceed without the rule bundle it
            # asked for. Report it with the valid skill names.
            sys.stdout.write(_json_envelope(
                "sem.skills.v1", ok=False, status="not-found", skills=items,
                missing=missing, available=sorted(EAV_SKILLS)) + "\n")
            return 1
    else:
        items = [{"name": k, "summary": v["summary"]}
                 for k, v in EAV_SKILLS.items()]
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


def _source_declares_project(source_text: str) -> bool:
    """R-008: detect a real `<name> is project` entity row by lexing rows, not a
    raw substring search. Comments and string literals therefore cannot
    masquerade as a project declaration — `# … is project` is a comment row, and
    `"is project"` lexes to a single string token, not the `is`/`project`
    sequence."""
    if source_text.startswith("﻿"):
        source_text = source_text[1:]
    for raw in source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = tokenize_line(raw)
        except EavError:
            continue
        if len(tokens) >= 3 and tokens[1] == "is" and tokens[2] == "project":
            return True
    return False


def _parse_panic(stderr: str) -> Optional[dict]:
    """WS1-135: parse an `ss_panic` crash block out of captured stderr into a
    structured `panic` object for the sem.eval.v1 / run --json envelope. Returns
    None when the program did not trap through ss_panic."""
    import re
    m = re.search(r"EAV PANIC (SSR\d+) (\S+)", stderr)
    if not m:
        return None
    code, kind = m.group(1), m.group(2)

    def field(label):
        mm = re.search(label + r":[ \t]*(.+)", stderr)
        return mm.group(1).strip() if mm else None

    row = field("at line")
    operands = field("operands") or ""
    lm = re.search(r"left=(-?\d+)", operands)
    rm = re.search(r"right=(-?\d+)", operands)
    return {
        "code": code,
        "kind": kind,
        "op": field("op"),
        "row": int(row) if row and row.isdigit() else row,
        "reason": field("reason"),
        "operands": {
            "left": int(lm.group(1)) if lm else None,
            "right": int(rm.group(1)) if rm else None,
        },
    }


def _stdout_lines(out: str) -> list:
    """Split captured stdout into lines, dropping the single trailing element that
    a final newline produces. R-127: empty stdout is *no* lines (`[]`), not one
    blank line (`[""]`); a trailing newline does not add a phantom empty line."""
    lines = out.split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def _classify_run(out: str, err: str, code: int):
    """Map a captured (stdout, stderr, exitCode) run to a (status, panic) pair,
    shared by `eval --json` and `run --json` so the two surfaces never diverge."""
    if code == _EVAL_TIMEOUT_EXIT and "eval timeout" in err:
        return "timed-out", None  # R-101
    panic = _parse_panic(err)  # WS1-135
    if code == 0:
        status = "ok"
    elif panic is not None:
        status = "crashed"
    elif err.startswith("semanticscript:") or "\nsemanticscript:" in err:
        status = "compile-failed"  # parse/compile failure via main's EavError handler
    else:
        status = "nonzero-exit"
    return status, panic


def _unscaffold_lines(text: str, offset: int) -> str:
    """R-112: rewrite `line N` references in an eval snippet's diagnostics back
    from wrapped (scaffold-offset) coordinates to the user's snippet line numbers.
    Leaves a reference at or above the snippet boundary untouched if subtracting
    would underflow (a diagnostic genuinely in the scaffold prologue)."""
    import re
    if offset <= 0:
        return text

    def fix(m):
        n = int(m.group(1)) - offset
        return f"line {n}" if n >= 1 else m.group(0)

    return re.sub(r"\bline (\d+)", fix, text)


def cmd_eval(args) -> int:
    """Run a snippet through the JIT without scaffolding (sem.eval.v1): if the
    source declares no `project` entity, wrap it in a minimal console program,
    then JIT-run and return captured stdout/stderr + exit code and a status.

    R-008: project detection is lexical (not a substring), so a snippet whose
    comment or string text mentions `is project` still wraps and runs; and the
    payload carries stderr + a `status` so a compile failure is actionable
    instead of a bare `ok:false` with the diagnostic dropped.

    WS2-071: --strict blocks T3 warnings before running."""
    src = _read_source(args.path)
    wrapped = not _source_declares_project(src)
    # R-112: when the snippet is wrapped, the scaffold shifts every line number;
    # rewrite diagnostics/panic rows back to the user's snippet coordinates so an
    # editor or agent points its repair at the right line.
    offset = _EVAL_SCAFFOLD.count("\n") if wrapped else 0
    if wrapped:
        src = _EVAL_SCAFFOLD + src
    # WS2-071: --strict blocks T3 warnings
    if getattr(args, "strict", False):
        try:
            program = parse(src)
            diags = lint(program)
            diags = _filter_diagnostics_strict(diags, True)
            errors = [d for d in diags if d.severity == "error"]
            if errors:
                out, err = "", "\n".join(d.render() for d in errors)
                err = _unscaffold_lines(err, offset)
                code = 1
                status = "lint-error"
                sys.stdout.write(_json_envelope(
                    "sem.eval.v1", ok=False, status=status, exitCode=code, wrapped=wrapped,
                    stdout=out, stderr=err,
                    stdoutLines=[]) + "\n")
                return code  # R-100: ok:false exits nonzero
        except EavError:
            pass  # Fall through to _record_run_full which will catch the error
    out, err, code = _record_run_full(src)
    status, panic = _classify_run(out, err, code)
    if offset:
        err = _unscaffold_lines(err, offset)
        if panic is not None and isinstance(panic.get("row"), int):
            panic = {**panic, "row": panic["row"] - offset}
    payload = dict(
        ok=(code == 0), status=status, exitCode=code, wrapped=wrapped,
        stdout=out, stderr=err,
        stdoutLines=_stdout_lines(out))  # R-127
    if panic is not None:
        payload["panic"] = panic
    sys.stdout.write(_json_envelope("sem.eval.v1", **payload) + "\n")
    # R-100: process exit mirrors the program exit (0 iff ok); the program's
    # own exit code is preserved in the envelope's `exitCode` for the consumer.
    return code


def cmd_deps(args) -> int:
    """Dependency graph (sem.deps.v1): module `imports` + project `require` rows."""
    program = parse_compact(_read_program_source(args.path))
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
    program = parse_compact(_read_program_source(args.path))
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
    program = parse_compact(_read_program_source(args.path))
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
    entries = _doc_entries(parse_compact(_read_program_source(args.path)))
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
        fuzzy = False
        if match is None:  # near-miss name -> closest entity (agentic-friendly)
            import difflib
            close = difflib.get_close_matches(
                args.get, [e["name"] for e in entries], n=1, cutoff=0.5)
            if close:
                match = next(e for e in entries if e["name"] == close[0])
                fuzzy = True
        sys.stdout.write(_json_envelope(
            "sem.docs.v1", ok=(match is not None), fuzzyMatch=fuzzy,
            entity=match) + "\n")
    else:
        sys.stdout.write(_json_envelope(
            "sem.docsIndex.v1", count=len(entries),
            entries=[{"name": e["name"], "kind": e["kind"]} for e in entries]) + "\n")
    return 0


def cmd_dev(args) -> int:
    """Dev contract (sem.dev.v1): one check+runnability cycle reporting whether
    the surface is close to runnable (a single tick of the watch/restart loop)."""
    program = parse_compact(_read_program_source(args.path))
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
    program = parse_compact(_read_program_source(args.path))
    by_kind: dict = {}
    rows = 0
    for n in program.order:
        ent = program.entities[n]
        by_kind[ent.kind] = by_kind.get(ent.kind, 0) + 1
        rows += 1 + len(ent.rows)
    sys.stdout.write(_json_envelope(
        "sem.size.v1", entities=len(program.order), rows=rows, byKind=by_kind) + "\n")
    return 0


def _check_program_status(path: str) -> dict:
    """R-003: classify one checkable surface (a single file or a composed project
    directory) into the source-lane status used by `check`. Shared by the
    single-program path and the per-child workspace summaries so the two cannot
    drift. A parse failure is `compiler-error`; otherwise the lint severity picks
    `lint-diagnostics` / `ok-with-warnings` / `ok`."""
    try:
        program = parse_compact(_read_program_source(path))
    except EavError as exc:
        return {"status": "compiler-error", "ok": False, "diagnostics": [str(exc)]}
    diags = lint(program)
    errors = [d for d in diags if d.severity == "error"]
    warnings = [d for d in diags if d.severity == "warning"]
    status = ("lint-diagnostics" if errors
              else "ok-with-warnings" if warnings else "ok")
    return {"status": status, "ok": status in ("ok", "ok-with-warnings"),
            "diagnostics": [d.render() for d in diags]}


def check_workspace(root: str) -> dict:
    """R-003: check a *workspace* directory (not itself a project root) by checking
    each child independently and never composing unrelated fixtures into one
    program. Each app/example/std/signature/manifest child gets its own source
    lane status; `invalid_corpus/` and build/cache/asset dirs are excluded. The
    top-level status is `workspace`; `ok` is true only when every child is clean.
    This replaces the old behavior where the bare experiment root was glued into
    one program and reported a misleading `compiler-error` from a negative
    fixture's `=` token."""
    children = discover_workspace(root)
    summaries = []
    all_ok = True
    for child in children:
        result = _check_program_status(child["path"])
        all_ok = all_ok and result["ok"]
        summaries.append({"name": child["name"].replace("\\", "/"),
                          "kind": child["kind"], "status": result["status"],
                          "ok": result["ok"],
                          "diagnostics": result["diagnostics"]})
    return {"status": "workspace", "ok": all_ok,
            "childCount": len(summaries), "children": summaries}


def cmd_check(args) -> int:
    """Source lane (sem.check.v1): parse + lint, classify ok / ok-with-warnings /
    lint-diagnostics / compiler-error (README check/readiness split).

    R-003: a directory that is not itself a project root is treated as a workspace
    — each child app/example/std/signature is checked independently and reported
    with per-child summaries, instead of composing every unrelated fixture into one
    program and surfacing a misleading compiler error from a negative fixture."""
    import os
    if (args.path != "-" and os.path.isdir(args.path)
            and not is_project_root(args.path)):
        report = check_workspace(args.path)
        sys.stdout.write(_json_envelope("sem.check.v1", **report) + "\n")
        return 0 if report["ok"] else 1
    try:
        program = parse_compact(_read_program_source(args.path))
    except EavError as exc:
        sys.stdout.write(_json_envelope(
            "sem.check.v1", status="compiler-error", ok=False,
            diagnostics=[str(exc)]) + "\n")
        return 1  # R-093: a compiler error is a nonzero exit, matching the workspace lane
    diags = lint(program)
    diags = _filter_diagnostics_strict(diags, getattr(args, "strict", False))
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
    # R-080: surface retained typed comments (`# security:`/`# failure:` …) on
    # the machine-facing check envelope so important notes stay reviewable in
    # downstream tooling instead of disappearing.
    typed = [{"tag": t, "text": txt, "line": ln}
             for (t, txt, ln) in program.typed_comments]
    sys.stdout.write(_json_envelope(
        "sem.check.v1", status=status, ok=(status in ("ok", "ok-with-warnings")),
        diagnostics=_structured_diags(diags), typedComments=typed,
        nextCommands=nxt) + "\n")
    # R-093: error-severity diagnostics (incl. --strict-promoted warnings) exit
    # nonzero; clean and warning-only single files stay 0, matching the workspace lane.
    return 1 if status == "lint-diagnostics" else 0


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


def _default_build_output(path: str, explicit_output: Optional[str]) -> str:
    """Resolve the build output path (README §28.2). R-014: a project-directory
    build lands under the gitignored `dist/` directory (`<dir>/dist/app`), never
    the project root, so a replayed `build <root>` does not drop an unignored
    binary beside the source. A single-file build sits next to its source, and an
    explicit `--output` always wins."""
    import os
    if explicit_output:
        return explicit_output
    suffix = ".exe" if sys.platform == "win32" else ""
    if path == "-":
        return "a" + suffix
    if os.path.isdir(path):
        return os.path.join(path, "dist", "app" + suffix)
    return os.path.splitext(path)[0] + suffix


def cmd_build(args) -> int:
    """Compile a program to a native executable (IR -> clang -> exe). R-017: an
    optional `--platform NAME` selects a declared `platform` entity (triple +
    forPlatform + its `output` row); an unknown platform exits with a structured
    sem.build.v1 error."""
    import os
    program = parse_compact(_read_program_source(args.path))
    platform = getattr(args, "platform", None)
    try:
        plat = _resolve_build_platform(program, platform)
    except EavError as exc:
        declared = sorted(n for n in program.order
                          if program.entities[n].kind == "platform")
        sys.stdout.write(_json_envelope(
            "sem.build.v1", ok=False, status="unknown-platform",
            platform=platform, declared=declared, message=str(exc)) + "\n")
        return 2
    # a platform's `output` row is the default output when no --output is given
    out_path = args.output
    if not out_path and plat is not None:
        links = merge_native_links(program, plat.name)
        if links.get("output"):
            base = args.path if os.path.isdir(args.path) else os.path.dirname(
                os.path.abspath(args.path))
            out_path = os.path.join(base, links["output"])
    out_path = _default_build_output(args.path, out_path)
    try:
        sys.stdout.write(build_executable(program, out_path, platform) + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2


def cmd_trace(args) -> int:
    """Print a primary-path trace of an operation."""
    program = parse(_read_source(args.path))
    try:
        for line in trace(program, args.operation):
            sys.stdout.write(line + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
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
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2


def cmd_graph(args) -> int:
    """Emit a calls/control graph as DOT or mermaid. R-087: `--json` wraps the
    rendered graph in a versioned sem.graph.v1 envelope (and a parse/render
    error becomes a compiler-error envelope, never an argparse/plaintext error)."""
    want_json = getattr(args, "json", False)
    try:
        program = parse(_read_program_source(args.path))  # R-117: accept a project dir too
        text = graph(program, args.kind, args.format)
    except EavError as exc:
        if want_json:
            sys.stdout.write(_json_envelope(
                "sem.graph.v1", status="compiler-error", ok=False,
                diagnostics=[f"semanticscript: {exc}"]) + "\n")
            return 1
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2
    if want_json:
        sys.stdout.write(_json_envelope(
            "sem.graph.v1", status="ok", kind=args.kind,
            format=args.format, graph=text) + "\n")
    else:
        sys.stdout.write(text)
    return 0


def cmd_scaffold(args) -> int:
    """Print a canonical scaffold for a pattern."""
    try:
        sys.stdout.write(scaffold(args.pattern))
        return 0
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
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
        # README §24: drift check — exit nonzero if the file is not EXACTLY
        # canonical. R-114: compare byte-for-byte (including boundary whitespace
        # and the terminal newline) so CI can't accept a file that a later `fmt`
        # or patch would churn while the check claimed the tree was clean.
        if formatted != src:
            reason = ("fmt drift — boundary whitespace / terminal newline differs"
                      if formatted.strip() == src.strip() else "fmt drift")
            sys.stderr.write(
                f"semanticscript: {reason} — run `semanticscript fmt` to canonicalize\n")
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
    """Apply a repair plan (sem.patch.v1). R-016: load and validate the plan JSON
    named on the command line and honor `--dry-run`/`--apply`, instead of
    emitting a canned suggestions-only payload regardless of input. A missing or
    corrupt plan is now a distinct, reportable error — indistinguishable before
    from a valid plan. semanticscript `fix` plans are suggestions-only today
    (`planUsable:false`), so there is nothing machine-applicable to apply; that
    is reported faithfully only after a valid plan is actually read."""
    import json
    import os
    plan_path = getattr(args, "plan", None)
    dry_run = getattr(args, "dry_run", False)
    if not plan_path:
        sys.stdout.write(_json_envelope(
            "sem.patch.v1", ok=False, status="no-plan", applied=0, dryRun=dry_run,
            note="no plan file given; pass the saved `fix --json` plan "
                 "(sem.fixPlan.v1) to patch") + "\n")
        return 2
    if not os.path.isfile(plan_path):
        sys.stdout.write(_json_envelope(
            "sem.patch.v1", ok=False, status="missing-plan", applied=0,
            dryRun=dry_run, plan=plan_path,
            note="plan file does not exist") + "\n")
        return 2
    try:
        plan = json.loads(open(plan_path, encoding="utf-8").read())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        sys.stdout.write(_json_envelope(
            "sem.patch.v1", ok=False, status="corrupt-plan", applied=0,
            dryRun=dry_run, plan=plan_path,
            note=f"plan is not valid JSON: {exc}") + "\n")
        return 2
    if not isinstance(plan, dict) or plan.get("surface") != "sem.fixPlan.v1":
        sys.stdout.write(_json_envelope(
            "sem.patch.v1", ok=False, status="invalid-plan", applied=0,
            dryRun=dry_run, plan=plan_path,
            note="plan is not a sem.fixPlan.v1 envelope (run `fix --json`)") + "\n")
        return 2
    if not bool(plan.get("planUsable")):
        # a suggestions-only plan has no machine-applicable edits — report that
        # honestly whether the caller asked for --dry-run or --apply.
        sys.stdout.write(_json_envelope(
            "sem.patch.v1", ok=True, status="suggestions-only", applied=0,
            dryRun=dry_run, plan=plan_path,
            suggestions=len(plan.get("diagnostics", []) or []),
            note="plan is suggestions-only; apply the suggested repairs manually") + "\n")
        return 0
    # planUsable plans would be applied/dry-run here once semanticscript emits
    # machine-applicable edits; until then an actionable plan is unexpected input.
    sys.stdout.write(_json_envelope(
        "sem.patch.v1", ok=False, status="unsupported-plan", applied=0,
        dryRun=dry_run, plan=plan_path,
        note="machine-applicable plan edits are not implemented yet") + "\n")
    return 2


def cmd_query(args) -> int:
    """Print the result of a structural query (`--dimension`)."""
    want_json = getattr(args, "json", False)
    try:
        program = parse(_read_program_source(args.path))  # R-117: accept a project dir too
    except EavError as exc:
        if want_json:
            sys.stdout.write(_json_envelope(
                "sem.query.v1", status="compiler-error", ok=False,
                diagnostics=[f"semanticscript: {exc}"]) + "\n")
            return 1
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2
    if args.dimension not in QUERY_DIMENSIONS:
        if want_json:
            sys.stdout.write(_json_envelope(
                "sem.query.v1", status="tool-error", ok=False,
                message=f"unknown query dimension {args.dimension!r}",
                dimensions=sorted(QUERY_DIMENSIONS)) + "\n")
            return 2
        sys.stderr.write(
            f"semanticscript: unknown query dimension {args.dimension!r}; choose from "
            f"{', '.join(QUERY_DIMENSIONS)}\n"
        )
        return 2
    results = list(query(program, args.dimension))
    if want_json:
        sys.stdout.write(_json_envelope(
            "sem.query.v1", status="ok", dimension=args.dimension,
            results=results) + "\n")
    else:
        for line in results:
            sys.stdout.write(line + "\n")
    return 0


def cmd_rename(args) -> int:
    """Rename an entity and all references; print the updated source."""
    try:
        sys.stdout.write(rename_entity(_read_source(args.path), args.old, args.new))
        return 0
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2


def cmd_add(args) -> int:
    """Append a scaffolded operation; print the updated source."""
    try:
        sys.stdout.write(add_operation(_read_source(args.path), args.name, args.out))
        return 0
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2


def cmd_pack(args) -> int:
    """Print a budgeted context bundle for editing an entity."""
    program = parse(_read_source(args.path))
    try:
        sys.stdout.write(pack(program, args.entity, args.budget) + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2


def cmd_slice(args) -> int:
    """Print the semantic slice of an entity (sem.slice.v1 with --json)."""
    program = parse(_read_source(args.path))
    try:
        text = slice_entity(program, args.entity)
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
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
    """Discover (--discover) or execute `tag test` operations (sem.test.v1).

    R-007: when the path is a project directory, compose the runtime program with
    its companion `*.test.sem` sources (`load_test_project`) so co-located test
    operations are actually executed — `load_project` alone excludes test files,
    so a scaffold's `checkGreetingLength` would otherwise never run.

    WS2-071: --strict blocks T3 warnings before running tests."""
    import os
    try:
        if (args.path != "-" and os.path.isdir(args.path)
                and is_project_root(args.path)):
            program = load_test_project(args.path)
        else:
            program = parse_compact(_read_program_source(args.path))
    except EavError as exc:
        sys.stdout.write(_json_envelope(
            "sem.test.v1", ok=False, status="compiler-error",
            preflightStatus="compiler-error", runtimeHarnessStatus="not-run",
            compositeStatus="blocked", tests=[], diagnostics=[str(exc)]) + "\n")
        return 1
    # WS2-071: --strict blocks T3 warnings
    if getattr(args, "strict", False):
        diags = lint(program)
        diags = _filter_diagnostics_strict(diags, True)
        errors = [d for d in diags if d.severity == "error"]
        if errors:
            sys.stdout.write(_json_envelope(
                "sem.test.v1", ok=False, status="lint-error",
                preflightStatus="lint-error", runtimeHarnessStatus="not-run",
                compositeStatus="blocked", tests=[],
                diagnostics=[d.render() for d in errors]) + "\n")
            return 1
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
    report = run_tests(program, lane=getattr(args, "lane", None))
    # R-102: only a clean `pass` is ok — a lint-`blocked` preflight, an error, or
    # a failing test is ok:false so an envelope consumer can't read a blocked run
    # as success (the process exit already distinguishes pass from not-pass).
    # R-158: a selected lane that found zero tests is `no-tests` (ok:false) unless
    # the caller opts in with --allow-empty.
    composite = report["compositeStatus"]
    ok = composite == "pass" or (composite == "no-tests"
                                 and getattr(args, "allow_empty", False))
    sys.stdout.write(_json_envelope("sem.test.v1", ok=ok, **report) + "\n")
    return 0 if ok else 1


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
            sys.stderr.write(f"semanticscript: {exc}\n")
            return 2
    want_json = getattr(args, "json", False)
    try:
        program = parse(_read_source(args.path))
    except EavError as exc:
        # R-085: a parse error on `lint --json` must still be a versioned
        # `sem.lint.v1` envelope (never plaintext), so MCP/agent consumers can
        # distinguish compiler-error from lint-diagnostics.
        if want_json:
            sys.stdout.write(_json_envelope(
                "sem.lint.v1", status="compiler-error", ok=False,
                diagnostics=[{"code": exc.code, "severity": "error",
                              "line": exc.line, "entity": None,
                              "message": exc.message, "rendered": f"semanticscript: {exc}"}]) + "\n")
            return 1
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2
    diags = lint(program)
    errors = [d for d in diags if d.severity == "error"]
    warnings = [d for d in diags if d.severity == "warning"]
    if want_json:
        # R-085: success is a `sem.*.v1` envelope with structured diagnostics,
        # not the legacy bare array.
        status = ("lint-diagnostics" if errors
                  else "ok-with-warnings" if warnings else "ok")
        sys.stdout.write(_json_envelope(
            "sem.lint.v1", status=status,
            ok=(status in ("ok", "ok-with-warnings")),
            diagnostics=_structured_diags(diags)) + "\n")
    else:
        for d in diags:
            sys.stdout.write(d.render() + "\n")
        if not diags:
            sys.stdout.write("no lint diagnostics\n")
    return 1 if errors else 0


def cmd_explain(args) -> int:
    """Print the registry entry + repair for a diagnostic code."""
    try:
        sys.stdout.write(format_repair(args.code) + "\n")
        return 0
    except EavError as exc:
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2


def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        # R-001: turn a directory/unreadable-path OSError (e.g. PermissionError or
        # IsADirectoryError on a project dir) into an EavError so `main` reports a
        # stable `semanticscript: …` message and exit 2 instead of a raw Python traceback.
        import os
        if os.path.isdir(path):
            raise EavError(
                f"{path!r} is a directory; this command reads a single file — "
                f"pass a .sem file, or use a project-aware command (README ss24)")
        raise EavError(f"cannot read {path!r}: {exc.strerror or exc}")


def main(argv: Optional[list[str]] = None) -> int:
    # EAV source and output are UTF-8 (README §33.2). On Windows the default
    # console encoding is cp1252, which cannot encode characters that legitimately
    # appear in source (em-dashes in comments, Unicode string literals) and would
    # crash `fmt`/`run` output or corrupt a `fmt -` stdin pipe; force UTF-8 on
    # every standard stream so source round-trips through pipes intact.
    for _stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="semanticscript", description="EAV-Steps front end (lex/parse/lower/run)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn in (
        ("lex", cmd_lex),
        ("parse", cmd_parse),
        ("lower", cmd_lower),
        ("inventory", cmd_inventory),
        ("doctor", cmd_doctor),
    ):
        sp = sub.add_parser(name)
        sp.add_argument("path", help="EAV source file, or - for stdin")
        sp.set_defaults(func=fn)

    # TOOL-3: IR inspection — emit-ir (optionally optimized, -o aware) + inspect-ir
    sp_emit = sub.add_parser("emit-ir", help="emit textual LLVM IR (optionally optimized)")
    sp_emit.add_argument("path", help="EAV/compact source file or project, or - for stdin")
    sp_emit.add_argument("--optimized", action="store_true", help="run LLVM -O2 passes")
    sp_emit.add_argument("--output", "-o", help="write IR to this path instead of stdout")
    sp_emit.set_defaults(func=cmd_emit_ir)
    sp_inspect = sub.add_parser("inspect-ir", help="structured summary of the lowered module")
    sp_inspect.add_argument("path", help="EAV/compact source file or project, or - for stdin")
    sp_inspect.add_argument("--json", action="store_true")
    sp_inspect.set_defaults(func=cmd_inspect_ir)

    # TOOL-4: toolchain self-diagnostic + cache clean
    sp_status = sub.add_parser("status", help="toolchain self-diagnostic (versions, C toolchain, cache, platform)")
    sp_status.add_argument("--json", action="store_true")
    sp_status.set_defaults(func=cmd_status)
    sp_clean = sub.add_parser("clean", help="clear the cached native runtime/build artifacts")
    sp_clean.add_argument("--json", action="store_true")
    sp_clean.set_defaults(func=cmd_clean)

    # TOOL-5: diagnostic-code catalog + keyword search
    sp_index = sub.add_parser("index", help="catalog every diagnostic code (tier + summary)")
    sp_index.add_argument("--json", action="store_true")
    sp_index.set_defaults(func=cmd_index)
    sp_search = sub.add_parser("search", help="relevance-ranked retrieval across docs/diagnostics/skills/templates/spec")
    sp_search.add_argument("query", help="search terms")
    sp_search.add_argument("--source", nargs="*",
                           choices=["diagnostic", "skill", "template", "rules", "spec", "entity"],
                           help="restrict to these corpus sources")
    sp_search.add_argument("--path", help="include this project's entities in the corpus")
    sp_search.add_argument("--limit", type=int, default=20, help="max results (default 20)")
    sp_search.add_argument("--json", action="store_true")
    sp_search.set_defaults(func=cmd_search)

    # TOOL-6: pipeline benchmark
    sp_bench = sub.add_parser("bench", help="benchmark parse/lower/JIT-run (best of N)")
    sp_bench.add_argument("path", help="EAV/compact source file or project, or - for stdin")
    sp_bench.add_argument("--runs", type=int, default=5, help="iterations (default 5)")
    sp_bench.add_argument("--json", action="store_true")
    sp_bench.set_defaults(func=cmd_bench)

    # TOOL-7: re-pin dependencies (regenerate build.sem.lock via MVS)
    sp_repin = sub.add_parser("repin", help="regenerate build.sem.lock from build.sem (MVS)")
    sp_repin.add_argument("path", help="project directory or build.sem manifest")
    sp_repin.add_argument("--check", action="store_true", help="verify the lock is current, do not write")
    sp_repin.add_argument("--json", action="store_true")
    sp_repin.set_defaults(func=cmd_repin)

    # run needs --strict flag (WS2-071)
    sp_run = sub.add_parser("run", help="JIT-compile and execute")
    sp_run.add_argument("path", help="EAV source file, or - for stdin")
    sp_run.add_argument("--strict", action="store_true",
                        help="block T3 opinionated warnings (in addition to T0/T1/T2)")
    sp_run.add_argument("--json", action="store_true")
    sp_run.add_argument("--entry", default=None,
                        help="run a named operation as the entry (used by the "
                             "isolated test runner, R-102)")
    sp_run.add_argument("--_jit-child", dest="jit_child", action="store_true",
                        help=argparse.SUPPRESS)  # R-088: internal isolated JIT child
    sp_run.set_defaults(func=cmd_run)

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
    sp_eval.add_argument("--strict", action="store_true",
                         help="block T3 opinionated warnings (in addition to T0/T1/T2)")
    sp_eval.add_argument("--json", action="store_true")
    sp_eval.set_defaults(func=cmd_eval)

    sp_check = sub.add_parser("check", help="source lane: parse + lint status")
    sp_check.add_argument("path", help="EAV/compact source file, or - for stdin")
    sp_check.add_argument("--json", action="store_true")
    sp_check.add_argument("--strict", action="store_true",
                          help="block T3 opinionated warnings (in addition to T0/T1/T2)")
    sp_check.set_defaults(func=cmd_check)

    sp_readiness = sub.add_parser("readiness", help="environment lane: toolchain status")
    sp_readiness.add_argument("--json", action="store_true")
    sp_readiness.set_defaults(func=cmd_readiness)

    sp_mcp = sub.add_parser("mcp", help="run the MCP stdio JSON-RPC server")
    sp_mcp.set_defaults(func=cmd_mcp)

    sp_new = sub.add_parser("new", help="scaffold a canonical EAV project tree")
    sp_new.add_argument("path", help="project root directory to create")
    sp_new.add_argument("--enable-docs-index", action="store_true")
    sp_new.add_argument("--force", action="store_true",
                        help="overwrite existing scaffold files (default: refuse)")
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
    sp_build.add_argument("--platform", help="declared platform entity to build for "
                          "(triple/forPlatform/output); host default when omitted")
    sp_build.set_defaults(func=cmd_build)

    sp_wasm = sub.add_parser("wasm", help="compile a pure-compute program to a "
                             ".wasm module + node runner (WS3-161)")
    sp_wasm.add_argument("path", help="EAV/compact source file, or - for stdin")
    sp_wasm.add_argument("--output", "-o", help="output .wasm path")
    sp_wasm.set_defaults(func=cmd_wasm)

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
    sp_test.add_argument("--allow-empty", dest="allow_empty", action="store_true",
                         help="treat a selected lane with zero tests as pass (R-158)")
    sp_test.add_argument("--discover", action="store_true",
                         help="list test ops instead of executing them")
    sp_test.add_argument("--strict", action="store_true",
                         help="block T3 opinionated warnings (in addition to T0/T1/T2)")
    sp_test.add_argument("--json", action="store_true")
    sp_test.set_defaults(func=cmd_test)

    sp_query = sub.add_parser("query", help="structural query over a program")
    sp_query.add_argument("dimension", help=f"one of: {', '.join(QUERY_DIMENSIONS)}")
    sp_query.add_argument("path", help="EAV source file, or - for stdin")
    sp_query.add_argument("--json", action="store_true",
                          help="emit a sem.query.v1 envelope (R-087)")
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
    sp_graph.add_argument("--json", action="store_true",
                          help="emit a sem.graph.v1 envelope (R-087)")
    sp_graph.set_defaults(func=cmd_graph)

    args = parser.parse_args(argv)

    def _emit_json_error(exc, status: str) -> None:
        # R-098: when a JSON-capable command fails before its own envelope is
        # written, emit a structured sem.error.v1 (ok:false + a machine-readable
        # diagnostic) instead of a plaintext `semanticscript: …` on stderr, so an
        # MCP/agent consumer can distinguish compiler-error / io-error.
        name = getattr(getattr(args, "func", None), "__name__", "cmd")
        name = name[4:].replace("_", "-") if name.startswith("cmd_") else name
        diag = {"code": getattr(exc, "code", None), "severity": "error",
                "line": getattr(exc, "line", None),
                "message": getattr(exc, "message", str(exc)),
                "rendered": f"semanticscript: {exc}"}
        sys.stdout.write(_json_envelope(
            "sem.error.v1", ok=False, status=status, command=name,
            diagnostics=[diag]) + "\n")

    try:
        return args.func(args)
    except EavError as exc:
        if getattr(args, "json", False):
            _emit_json_error(exc, "compiler-error")
            return 2
        sys.stderr.write(f"semanticscript: {exc}\n")
        return 2
    except OSError as exc:
        if getattr(args, "json", False):
            _emit_json_error(exc, "io-error")
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
