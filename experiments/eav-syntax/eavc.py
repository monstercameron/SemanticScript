#!/usr/bin/env python3
"""eavc — EAV-Steps front end (lexer, parser, lowering, CLI).

This is the keystone vertical slice for the EAV-Steps v0.3 spec (README.md). It
implements WS1-100 (the lowering ADR) and WS1-101 (parse -> lower -> run Hello
World) from todos.md.

ADR (WS1-100): EAV-Steps is lowered as a *second front end* that normalizes
canonical EAV source into the existing v0.1 verb-led SemanticScript text, which
the reference compiler (``SemanticScript/compiler/semsc.py``) already parses,
lowers, and runs. We do not fork the backend AST: we reuse the entire existing
compile/run pipeline by emitting the v0.1 surface it already accepts. This keeps
the EAV experiment anchored to a real, executable backend instead of a parallel
stub, and makes the no-op-lowering-fails guarantee concrete -- a stubbed
lowering produces a program that does not compile or does not print.

The front end is intentionally split into three pure stages so each is testable
in isolation:

    tokenize_line(text)        -> list[str]            (lexer, README ss2)
    parse(source_text)         -> Program              (parser, README ss1/ss5)
    lower_to_v01(program)      -> str                  (lowering, README ss18)

Scope of this slice: the parser accepts the full four-row-class grammar and all
entity kinds in README ss5 so real programs parse without special-casing; the
lowering targets the *console* program model end to end (Hello World, ss18).
Constructs that only make sense for the webServer/wasm targets are parsed but
rejected by the console lowering with a clear message, rather than silently
dropped.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
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


def _validate_value_literal(tok: str, line: int) -> None:
    """Validate a `let`/`arg` value token if it is a numeric literal attempt.

    Identifiers (binding refs), strings, bool/enum tokens are skipped. A token
    led by a digit is an integer literal (README ss2/ss33.1)."""
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
    for ent in (program.entities[name] for name in program.order):
        if ent.kind == "record":
            _check_unique_labels(
                ent, "field", "field name", "README ss10/ss17 #29"
            )
        elif ent.kind == "enum":
            _validate_enum(ent)
        if ent.kind in ("operation", "function"):
            for row in ent.facts("let"):
                if row.payload and row.payload[0] in RESERVED_WORDS:
                    raise EavError(
                        f"reserved word {row.payload[0]!r} may not be a variable "
                        f"name (README ss2)",
                        row.line,
                    )
                if len(row.payload) > 3:
                    _validate_value_literal(row.payload[3], row.line)
        if ent.kind in ("call", "task"):
            for row in ent.facts("arg"):
                if len(row.payload) > 2:
                    _validate_value_literal(row.payload[2], row.line)
        for row in ent.facts("out"):
            if row.payload and row.payload[0] == "Result" and len(row.payload) != 3:
                raise EavError(
                    "`out Result` needs exactly an OK type and an ERR type "
                    f"(README ss10), got {row.payload!r}",
                    row.line,
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
# 3. Lowering  (README ss18 — EAV -> v0.1 verb-led SemanticScript)
# --------------------------------------------------------------------------

# Aliases that name a type the reference compiler already knows built-in; we do
# not re-declare these with a `type` row (it already treats ExitCode as i32).
BUILTIN_ALIASES = {"ExitCode"}

# Operation declaration predicates, emitted before the body in v0.1.
_OP_DECL_PREDS = {"in", "out", "effect", "uses", "memory", "async", "purpose",
                  "invariant", "note", "rationale", "risk", "example", "tag",
                  "deprecated", "owner", "label", "export", "body"}


# Built-in primitive types (README ss10) — usable with no `is` row. `Byte` is a
# primitive synonym for `UInt8` (same width, freely interchangeable at the ABI).
PRIMITIVE_TYPES = {
    "Int8", "Int16", "Int32", "Int64",
    "UInt8", "UInt16", "UInt32", "UInt64",
    "Float32", "Float64",
    "Bool", "String", "Void", "Byte",
}


def _norm_type(tok: str) -> str:
    """Normalize a type token for lowering. `Byte` lowers to `UInt8` (README ss10)."""
    return "UInt8" if tok == "Byte" else tok


def lower_to_v01(program: Program) -> str:
    """Lower a parsed EAV Program to v0.1 verb-led source text (console target).

    Returns text the reference compiler accepts. Raises EavError for constructs
    that the console lowering does not model (webServer/wasm/sqlite/http), so a
    caller never gets a silently-wrong program.
    """

    projects = program.of_kind("project")
    if not projects:
        raise EavError("no `project` entity found (README ss7)")
    project = projects[0]

    target_row = project.fact("target")
    target = target_row.payload[0] if target_row and target_row.payload else "console"
    if target != "console":
        raise EavError(
            f"console lowering only supports `target console`, got {target!r}; "
            "webServer/wasm lowering is out of scope for this slice (todos WS3)"
        )

    module_row = project.fact("module")
    module_entity = None
    if module_row and module_row.payload:
        module_entity = program.entities.get(module_row.payload[0])
    module_path = "examples.program"
    if module_entity is not None:
        path_row = module_entity.fact("path")
        if path_row and path_row.payload:
            module_path = path_row.payload[0]

    entry_row = project.fact("entry")
    if not entry_row or not entry_row.payload:
        raise EavError("project needs an `entry` row (README ss7)")
    entry_op = entry_row.payload[0]

    out: list[str] = []
    out.append(f"project {project.name}")
    out.append("target console")
    out.append("runtime native 1")
    out.append(f"module {module_path}")
    out.append(f"entry console {entry_op}")
    out.append("")

    # Imports (alias path) from the module entity.
    if module_entity is not None:
        for row in module_entity.facts("imports"):
            if len(row.payload) >= 2:
                out.append(f"import {row.payload[0]} {row.payload[1]}")

    # Aliases -> `type NAME BASE` (skip compiler built-ins).
    for alias in program.of_kind("alias"):
        if alias.name in BUILTIN_ALIASES:
            continue
        for_row = alias.fact("for")
        if for_row and for_row.payload:
            out.append(f"type {alias.name} {for_row.payload[0]}")

    # Records -> `record` + `field` rows (schema/metadata; ss10).
    for rec in program.of_kind("record"):
        out.append(f"record {rec.name}")
        for fr in rec.facts("field"):
            if len(fr.payload) >= 2:
                out.append(f"field {rec.name} {fr.payload[0]} {_norm_type(fr.payload[1])}")

    # Errors and error cases (README ss9).
    for err in program.of_kind("error"):
        out.append(f"error {err.name}")
    for case in program.of_kind("errorCase"):
        of_row = case.fact("of")
        if not of_row or not of_row.payload:
            raise EavError(f"errorCase {case.name!r} missing `of` (README ss9)", case.line)
        parent = of_row.payload[0]
        payload_row = case.fact("payload")
        if payload_row and payload_row.payload and payload_row.payload[0] != "Void":
            out.append(f"errorCase {parent} {case.name} {payload_row.payload[0]}")
        else:
            out.append(f"errorCase {parent} {case.name}")

    # Capabilities (README ss8): grants <action> <resource> -> resource action.
    for cap in program.of_kind("capability"):
        for gr in cap.facts("grants"):
            if len(gr.payload) >= 2:
                action, resource = gr.payload[0], gr.payload[1]
                out.append(f"capability {cap.name} {resource} {action}")

    out.append("")

    # Operations.
    for op in program.of_kind("operation"):
        _lower_operation(program, op, out)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _lower_operation(program: Program, op: Entity, out: list[str]) -> None:
    out.append(f"operation {op.name}")

    # Declaration rows first, in a stable order.
    for row in op.facts("in"):
        if len(row.payload) >= 2:
            out.append(f"input operation {op.name} {row.payload[0]} {row.payload[1]}")

    out_row = op.fact("out")
    if out_row and out_row.payload:
        out.append(f"output operation {op.name} {' '.join(out_row.payload)}")

    for row in op.facts("effect"):
        out.append(f"effect {op.name} {' '.join(row.payload)}")

    for row in op.facts("memory"):
        out.append(f"memory {op.name} {' '.join(row.payload)}")

    async_row = op.fact("async")
    if async_row and async_row.payload:
        out.append(f"async {op.name} {async_row.payload[0]}")

    purpose_row = op.fact("purpose")
    if purpose_row and purpose_row.payload:
        out.append(f"purpose operation {op.name} {purpose_row.payload[0]}")

    for row in op.facts("invariant"):
        out.append(f"invariant operation {op.name} {row.payload[0]}")

    for row in op.facts("uses"):
        if row.payload:
            out.append(f"useCapability {op.name} {row.payload[0]}")

    # Mutability of each `let` name in this op. An `out` to a `let mutable` is a
    # rebind (README ss12) lowered via `set storage`; an `out` to a `let
    # immutable` is a hard error (README ss12, ss17 #28).
    let_mut = {
        r.payload[0]: r.payload[1]
        for r in op.facts("let")
        if len(r.payload) >= 2 and r.payload[1] in ("mutable", "immutable")
    }

    # Body rows in document order. `let` -> storage; steps -> verb rows.
    for row in op.rows:
        if row.label is not None:
            out.append(f"label {row.label}")
            _lower_step(program, op, row, out, let_mut)
            continue
        if row.predicate == "let":
            _lower_let(op, row, out)
        elif row.predicate in STEP_PREDICATES:
            _lower_step(program, op, row, out, let_mut)
        # declaration predicates already emitted; ignore here.


def _lower_let(op: Entity, row: Row, out: list[str]) -> None:
    # let NAME mutable|immutable TYPE [VALUE]
    p = row.payload
    if len(p) < 3:
        raise EavError(f"`let` row needs NAME MUT TYPE [VALUE], got {p!r}", row.line)
    name, mut, typ = p[0], p[1], _norm_type(p[2])
    if mut not in ("mutable", "immutable"):
        raise EavError(f"`let` mutability must be mutable|immutable, got {mut!r}", row.line)
    value = " ".join(p[3:]) if len(p) > 3 else ""
    if value:
        out.append(f"storage local {mut} {name} {typ} {value}")
    else:
        out.append(f"storage local {mut} {name} {typ}")


def _lower_step(
    program: Program, op: Entity, row: Row, out: list[str], let_mut: dict[str, str]
) -> None:
    pred = row.predicate
    p = row.payload
    if pred == "do":
        if not p:
            raise EavError("`do` needs a call name", row.line)
        call_name = p[0]
        call = program.entities.get(call_name)
        if call is None or call.kind not in ("call", "task"):
            raise EavError(
                f"`do {call_name}` does not name a call entity (README ss15)", row.line
            )
        if call.kind == "task":
            raise EavError(
                f"`do {call_name}` activates a task; tasks use start/join "
                "(README ss34.4)",
                row.line,
            )
        _lower_call(call, out, let_mut)
        return
    if pred == "branch":
        _lower_branch(row, out)
        return
    if pred == "goto":
        if not p:
            raise EavError("`goto` needs a label", row.line)
        out.append(f"jump target {p[0]}")
        return
    if pred == "return":
        _lower_return(op, row, out)
        return
    if pred in ("start", "join", "poll", "cancel", "detach", "defer"):
        raise EavError(
            f"step `{pred}` is not modeled by the console lowering slice "
            "(todos WS1-106/WS1-107)",
            row.line,
        )
    raise EavError(f"unsupported step predicate {pred!r}", row.line)


def _lower_call(call: Entity, out: list[str], let_mut: dict[str, str]) -> None:
    invokes_row = call.fact("invokes")
    if not invokes_row or not invokes_row.payload:
        raise EavError(f"call {call.name!r} missing `invokes` (README ss15)", call.line)
    target = invokes_row.payload[0]
    out.append(f"call {call.name} {target}")
    for arg in call.facts("arg"):
        # arg SLOT TYPE VALUE
        if len(arg.payload) < 3:
            raise EavError(
                f"`arg` row needs SLOT TYPE VALUE, got {arg.payload!r}", arg.line
            )
        slot, typ = arg.payload[0], _norm_type(arg.payload[1])
        value = " ".join(arg.payload[2:])
        out.append(f"argument {call.name} {slot} {typ} {value}")
    out.append(f"run {call.name}")

    out_row = call.fact("out")
    catch_row = call.fact("catch")
    has_out = out_row is not None and bool(out_row.payload)
    has_catch = catch_row is not None and bool(catch_row.payload)

    # An `out` to a `let mutable` name is a rebind (README ss12): bind to a fresh
    # temp, then `set storage` the mutable binding. An `out` to a `let immutable`
    # is a hard error (README ss12, ss17 #28). Otherwise it is a fresh bind.
    out_name = out_row.payload[0] if has_out else None
    out_type = (
        _norm_type(out_row.payload[1])
        if has_out and len(out_row.payload) >= 2
        else None
    )
    if has_out and let_mut.get(out_name) == "immutable":
        raise EavError(
            f"call {call.name!r} rebinds immutable `let {out_name}` via out "
            "(README ss12, ss17 #28); declare it `let mutable`",
            call.line,
        )
    is_rebind = has_out and let_mut.get(out_name) == "mutable"
    bind_target = f"{out_name}Rebind{call.line}" if is_rebind else out_name

    if has_out and has_catch:
        out.append(f"bind ok {bind_target} {out_type} {call.name}")
        out.append(
            f"bind error {catch_row.payload[0]} {catch_row.payload[1]} {call.name}"
        )
    elif has_out:
        out.append(f"bind value {bind_target} {out_type} {call.name}")
    elif has_catch:
        out.append(f"ignore void source {call.name}")
        out.append(
            f"bind error {catch_row.payload[0]} {catch_row.payload[1]} {call.name}"
        )
    else:
        out.append(f"ignore void source {call.name}")

    if is_rebind:
        out.append(f"set storage {out_name} {bind_target}")


def _lower_branch(row: Row, out: list[str]) -> None:
    p = row.payload
    if not p:
        raise EavError("`branch` needs a guard (README ss13)", row.line)
    guard = p[0]
    if guard == "ifError":
        # branch ifError CALL goto LABEL
        if len(p) != 4 or p[2] != "goto":
            raise EavError(
                "expected `branch ifError CALL goto LABEL` (README ss13)", row.line
            )
        out.append(f"branch error source {p[1]} target {p[3]}")
        return
    if guard == "if":
        # branch if COND goto LABEL
        if len(p) != 4 or p[2] != "goto":
            raise EavError(
                "expected `branch if COND goto LABEL` (README ss13)", row.line
            )
        out.append(f"branch if condition {p[1]} target {p[3]}")
        return
    if guard == "ifFalse":
        # branch ifFalse COND goto LABEL — jump to LABEL when COND is false.
        # v0.1 has only "branch if condition ... target" (true-taken), so invert
        # via a deterministic skip label: take the goto only on the false path.
        if len(p) != 4 or p[2] != "goto":
            raise EavError(
                "expected `branch ifFalse COND goto LABEL` (README ss13)", row.line
            )
        cond, label = p[1], p[3]
        skip = f"ifFalseSkip{row.line}"
        out.append(f"branch if condition {cond} target {skip}")
        out.append(f"jump target {label}")
        out.append(f"label {skip}")
        return
    raise EavError(
        f"branch guard {guard!r} is not modeled by the console lowering slice "
        "(todos WS1-062..066)",
        row.line,
    )


def _lower_return(op: Entity, row: Row, out: list[str]) -> None:
    p = row.payload
    out_row = op.fact("out")
    is_result = bool(out_row and out_row.payload and out_row.payload[0] == "Result")
    if not p:
        out.append("return void")
        return
    if is_result:
        # return OK nil | return nil ERR
        if len(p) == 2 and p[1] == "nil":
            out.append(f"return ok {p[0]}")
        elif len(p) == 2 and p[0] == "nil":
            out.append(f"return error {p[1]}")
        else:
            # single token but Result-typed: treat as ok value
            out.append(f"return ok {p[0]}")
        return
    out.append(f"return value {p[0]}")


# --------------------------------------------------------------------------
# 4. CLI
# --------------------------------------------------------------------------


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def _semsc_path() -> str:
    return os.path.join(_repo_root(), "SemanticScript", "compiler", "semsc.py")


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
    program = parse(_read_source(args.path))
    sys.stdout.write(lower_to_v01(program))
    return 0


def cmd_run(args) -> int:
    program = parse(_read_source(args.path))
    v01 = lower_to_v01(program)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sscript", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(v01)
        tmp = tf.name
    try:
        proc = subprocess.run(
            [sys.executable, _semsc_path(), tmp, "--run"],
            capture_output=True,
            text=True,
        )
        sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        return proc.returncode
    finally:
        os.unlink(tmp)


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
