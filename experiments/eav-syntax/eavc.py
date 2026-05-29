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


class EavError(Exception):
    """A lex/parse/lower diagnostic with an optional 1-based source line."""

    def __init__(self, message: str, line: Optional[int] = None) -> None:
        self.message = message
        self.line = line
        if line is not None:
            super().__init__(f"line {line}: {message}")
        else:
            super().__init__(message)


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
        elif ent.kind == "errorCase" and ent.fact("of") is None:
            raise EavError(
                f"errorCase {ent.name!r} needs an `of <Error>` row (README ss9)",
                ent.line,
            )
        if ent.kind in ("operation", "function"):
            _validate_body_kind(ent)
            _validate_labels(ent, program)
            _validate_return_arity(ent)
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
    _validate_cleanup(program)
    _validate_step_split(program)


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
    if target.startswith("math."):
        return True
    if target.startswith("console."):
        return False
    if "." not in target:
        callee = program.entities.get(target)
        if callee is not None and callee.kind in ("operation", "function"):
            return callee.fact("out") is not None
    return None


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
        elif row.predicate == "branch" and len(row.payload) >= 4 and row.payload[2] == "goto":
            refs.add(row.payload[3])
    for ref in refs:
        if ref not in defs:
            raise EavError(
                f"goto/branch target {ref!r} has no `at {ref}` label in operation "
                f"{op.name!r} (README ss17 #11)",
                op.line,
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
        # records/enums/errors are schema in the console model; represent an
        # opaque handle as i64 (they are not constructed at runtime here).
        return ir.IntType(64)

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
        ops = self.program.of_kind("operation")
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
        return self._literal_or_ref(type_name, tok, builder, sym)

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
        if pred == "return":
            return self._emit_return(op, fn, row, builder, sym)
        if pred == "branch":
            return self._emit_branch(fn, row, builder, sym, label_blocks)
        raise EavError(
            f"step `{pred}` is not modeled by the LLVM console code generator "
            "(todos WS1-106/WS1-107)",
            row.line,
        )

    def _emit_return(self, op, fn, row, builder, sym):
        p = row.payload
        ret_ty = fn.function_type.return_type
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
        raise EavError(
            f"branch guard {guard!r} is not modeled by the LLVM console code "
            "generator (todos WS1-062..066)",
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
            result = builder.call(self.runtime("printf"), [fmt, val])
        elif target == "console.writeFloatLine":
            fmt = self.global_string(b"%g\n\x00")
            val = arg("value", "Float64")
            result = builder.call(self.runtime("printf"), [fmt, val])
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
            raise EavError(
                f"call target {target!r} is not modeled by the LLVM console code "
                "generator (todos WS3 stdlib)",
                call.line,
            )

        self._call_info[call.name] = (result, err)

        out_row = call.fact("out")
        if out_row and out_row.payload and result is not None:
            name = out_row.payload[0]
            if let_mut.get(name) == "immutable":
                raise EavError(
                    f"call {call.name!r} rebinds immutable `let {name}` via out "
                    "(README ss12, ss17 #28); declare it `let mutable`",
                    call.line,
                )
            if let_mut.get(name) == "mutable":
                builder.store(result, sym[name][1])
            else:
                sym[name] = ("val", result)


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
    ):
        sp = sub.add_parser(name)
        sp.add_argument("path", help="EAV source file, or - for stdin")
        sp.set_defaults(func=fn)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except EavError as exc:
        sys.stderr.write(f"eavc: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
