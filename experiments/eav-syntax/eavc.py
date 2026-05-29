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
    "SS1340": {"tier": "T4", "summary": "ifValue/ifOut is comparison sugar.",
               "found": "A `branch ifValue`/`ifOut` guard.",
               "suggested": "Informational; fmt canonicalizes to compare + branch if (§13)."},
    "SS1542": {"tier": "T1", "summary": "cleanup onFailure without a worker catch.",
               "found": "A cleanup `onFailure` whose worker call has no `catch`.",
               "suggested": "Add a `catch` to the worker, or drop onFailure (§17 #42)."},
    "SS1326": {"tier": "T1", "summary": "Dotted name in an internal reference.",
               "found": "A `do`/`start`/`defer` (etc.) target containing a dot.",
               "suggested": "Internal refs are bare; dots are external-path only (§3)."},
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


def load_semsig(source: str) -> Program:
    """Parse a `.semsig` sidecar and validate its header (README ss26). An
    unknown schema `version` is rejected (SS2601)."""
    program = parse(source)
    headers = program.of_kind("semsig")
    if not headers:
        raise EavError("a .semsig file needs a `semsig` header entity (README ss26)")
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


def resolve_semsig(target: str, sigs: list):
    """Resolution order (README ss26): scan loaded .semsig Programs in order;
    the first that defines an intrinsic for `target` wins (first-target wins)."""
    for prog in sigs:
        if target in semsig_targets(prog):
            return prog
    return None


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
    "return", "goto", "if", "ifFalse", "ifOut", "ifValue", "ifVariant",
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
    "error": set(),
    "errorCase": {"of", "payload"},
    "record": {"field"},
    "enum": {"variant", "repr"},
    "alias": {"for"},
    "operation": {
        "in", "out", "effect", "uses", "memory", "async", "label", "let",
        "body", "export",
        "do", "defer", "start", "join", "poll", "cancel", "detach",
        "branch", "return", "goto",
    },
    "function": {
        "in", "out", "effect", "uses", "memory", "async", "label", "let",
        "body", "export",
        "do", "defer", "start", "join", "poll", "cancel", "detach",
        "branch", "return", "goto",
    },
    "call": {
        "in", "invokes", "arg", "out", "catch", "discards", "owns",
        "cleanedBy", "effect", "async",  # async = tolerated-deprecated (ss5)
    },
    "task": {
        "in", "invokes", "arg", "out", "catch", "discards", "owns",
        "cleanedBy", "effect",
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
            if subject in RESERVED_WORDS:
                raise EavError(
                    f"reserved word {subject!r} may not be an entity name "
                    f"(README ss2); arg-slot/field/variant labels are exempt",
                    lineno,
                )
            if not _IDENT_RE.match(subject):
                raise EavError(
                    f"invalid entity name {subject!r}: names are "
                    f"[a-zA-Z][a-zA-Z0-9]* — no underscores, hyphens, or leading "
                    f"digits (README ss2)",
                    lineno,
                )
            if subject in program.entities:
                raise EavError(
                    f"duplicate `is` row for entity {subject!r} (README ss17 #1)",
                    lineno,
                )
            program.add(Entity(name=subject, kind=kind, line=lineno))
            current_kind_of[subject] = kind
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
    for name in program.order:
        ent = program.entities[name]
        if ent.kind in ("operation", "function") and _op_body_kind(ent) in (
            "runtimeBinding", "intrinsic"
        ):
            # README ss17 #50: primitive bodies belong in a stdlib/.semsig-backed
            # module, not application source.
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
            if row.payload and "because" in row.payload:
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
                        row.line,
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
                    row.line,
                )
    _validate_calls(program)
    _validate_configure(program)
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

    def effective_effects(op: Entity, seen: set):
        """Transitive effective effects across the call graph (README ss29 #10)."""
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
        covered: set = set()
        for u in op.facts("uses"):
            if u.payload:
                covered |= cap_grants.get(u.payload[0], set())
        for action, resource in sorted(effective_effects(op, set())):
            if (action, resource) not in covered:
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
                    row.line,
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
            resource = cleans[0].payload[0] if cleans[0].payload else None
            if resource is not None and resource not in owned:
                raise EavError(
                    f"cleanup {ent.name!r} cleans {resource!r}, which no call "
                    f"`owns` (README ss15.6, ss17 #41)",
                    ent.line,
                )
        if ent.kind in ("call", "task"):
            cb = ent.fact("cleanedBy")
            if cb and cb.payload and cb.payload[0] not in cleanups:
                raise EavError(
                    f"{ent.kind} {ent.name!r} cleanedBy {cb.payload[0]!r}, which is "
                    f"not a cleanup entity (dangling cleanedBy, README ss15)",
                    ent.line,
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
                    row.line,
                )
        elif is_result:
            nils = p.count("nil")
            if len(p) != 2 or nils != 1:
                raise EavError(
                    f"{op.name!r} returns Result: `return` needs exactly one value "
                    f"and one `nil` (README ss13, ss17 #10), got {row.payload!r}",
                    row.line,
                )
        else:
            if len(p) != 1 or "nil" in p:
                raise EavError(
                    f"{op.name!r} returns a single value: `return` needs exactly "
                    f"one value (README ss17 #10), got {row.payload!r}",
                    row.line,
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

    def _make_module_storage(self, st: Entity) -> None:
        type_row = st.fact("type")
        if not type_row or not type_row.payload:
            return
        resolved = self.resolve_type_name(type_row.payload[0])
        if resolved not in _PRIMITIVE_IR:
            return  # non-primitive module storage (e.g. SqlText) not modeled here
        gv = ir.GlobalVariable(self.module, _PRIMITIVE_IR[resolved], name=st.name)
        gv.linkage = "internal"
        mut = st.fact("mutability")
        gv.global_constant = bool(
            mut and mut.payload and mut.payload[0] == "immutable"
        )
        value_row = st.fact("value")
        if value_row and value_row.payload:
            gv.initializer = self._const_value(resolved, value_row.payload)
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

    def _resolve(self, tok, type_name, builder, sym):
        if tok in sym:
            return self._load(sym[tok], builder)
        if tok in getattr(self, "module_storage", {}):
            return builder.load(self.module_storage[tok][0])
        return self._literal_or_ref(type_name, tok, builder, sym)

    def _resolve_as(self, tok, llvm_type, builder, sym):
        """Resolve a token to a value of a given LLVM type: load a binding, or
        build a literal constant of that type (used by ifValue/ifOut operands)."""
        if tok in sym:
            return self._load(sym[tok], builder)
        if tok in getattr(self, "module_storage", {}):
            return builder.load(self.module_storage[tok][0])
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
        elif target.startswith("compare."):
            result = self._emit_compare(target, args, builder, sym, call)
        elif target.startswith("convert.to"):
            result = self._emit_convert(target, args, builder, sym, call)
        elif target == "string.concat":
            # README ss30.2.2: heap-concatenate two NUL-terminated strings.
            left = arg("left", "String")
            right = arg("right", "String")
            la = builder.call(self.runtime("strlen"), [left])
            lb = builder.call(self.runtime("strlen"), [right])
            total = builder.add(builder.add(la, lb), ir.Constant(ir.IntType(64), 1))
            buf = builder.call(self.runtime("malloc"), [total])
            builder.call(self.runtime("strcpy"), [buf, left])
            builder.call(self.runtime("strcat"), [buf, right])
            result = buf
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


def jit_run(program: Program) -> int:
    """JIT-compile and execute the program's entry operation; return its exit
    code. stdout is the C runtime's, flushed when this process exits."""
    import ctypes

    module = lower_to_llvm(program)
    _ensure_native_init()
    mod = llvm.parse_assembly(str(module))
    mod.verify()
    tm = llvm.Target.from_default_triple().create_target_machine()
    engine = llvm.create_mcjit_compiler(mod, tm)
    engine.finalize_object()
    engine.run_static_constructors()
    addr = engine.get_function_address(_entry_name(program))
    cmain = ctypes.CFUNCTYPE(ctypes.c_int)(addr)
    return cmain()


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
    program = parse(_read_source(args.path))
    sys.stdout.flush()
    return jit_run(program)


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
    """Print the canonical EAV formatting of a program."""
    program = parse(_read_source(args.path))
    sys.stdout.write(format_program(program))
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
    """Print the semantic slice of an entity."""
    program = parse(_read_source(args.path))
    try:
        sys.stdout.write(slice_entity(program, args.entity))
        return 0
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


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
        ("fmt", cmd_fmt),
        ("doctor", cmd_doctor),
    ):
        sp = sub.add_parser(name)
        sp.add_argument("path", help="EAV source file, or - for stdin")
        sp.set_defaults(func=fn)

    sp_lint = sub.add_parser("lint", help="lint a program (or --explain a code)")
    sp_lint.add_argument("path", nargs="?", help="EAV source file, or - for stdin")
    sp_lint.add_argument("--explain", metavar="CODE", help="explain a diagnostic code")
    sp_lint.set_defaults(func=cmd_lint)

    sp_explain = sub.add_parser("explain", help="explain a diagnostic code")
    sp_explain.add_argument("code", help="diagnostic code, e.g. SS1502")
    sp_explain.set_defaults(func=cmd_explain)

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
