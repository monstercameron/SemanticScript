"""The predicate shape table (enforcement plan step 1, LR-09, LR-18, LR-42).

One table states, for every entity kind:
- which predicates it may carry,
- the exact token shape of each predicate (one or more alternatives),
- how many rows of it there must be,
- the order the rows come in.

The parser enforces this table and nothing else decides row shapes. The same
data renders the grammar reference (`refined grammar`).
"""
from __future__ import annotations

import re
from typing import Union

Slot = Union[str, frozenset]

LOWER = re.compile(r"[a-z][a-zA-Z0-9]*\Z")
UPPER = re.compile(r"[A-Z][a-zA-Z0-9]*\Z")
INT = re.compile(r"-?[0-9]+\Z")
FLOAT = re.compile(r"-?[0-9]+\.[0-9]+\Z")

# LR-42 A5: the only reserved words. Everything else is fixed by position.
RESERVED = frozenset({"true", "false", "none", "caller", "unset", "unbounded", "static", "begin"})

# LR-42 A3: built-in types are never prefixed.
BUILTIN_TYPES = frozenset({
    "Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64",
    "Float32", "Float64", "Bool", "Byte", "String", "Bytes", "Region", "ExitCode",
})

EFFECT_VERBS = frozenset({"read", "write", "readWrite", "listen", "connect", "spawn"})
INPUT_MODES = frozenset({"value", "borrowed", "borrowedMutable", "owned"})
ARG_MODES = frozenset({"copy", "lend", "lendMutable", "give"})
MODE_PAIRS = {"value": "copy", "borrowed": "lend", "borrowedMutable": "lendMutable", "owned": "give"}
LOOP_KINDS = frozenset({"counted", "while", "doWhile", "forEach", "forever"})
RISK_CATEGORIES = frozenset({"security", "failure", "timing", "concurrency", "memory", "data"})


def kw(*words: str) -> frozenset:
    return frozenset(words)


NONE = kw("none")
BOOL = kw("true", "false")


def is_name(t: str) -> bool:
    return bool(LOWER.match(t)) and t not in RESERVED


def is_label(t: str) -> bool:
    return bool(LOWER.match(t)) and (t not in RESERVED or t == "begin")


def is_type(t: str) -> bool:
    if t in BUILTIN_TYPES or UPPER.match(t):
        return True
    parts = t.split(".")
    return len(parts) == 2 and bool(LOWER.match(parts[0])) and bool(UPPER.match(parts[1]))


def is_path(t: str) -> bool:
    return all(LOWER.match(p) for p in t.split("."))


def is_resource(t: str) -> bool:
    parts = t.split(".")
    return len(parts) >= 2 and all(LOWER.match(p) for p in parts)


def is_target(t: str) -> bool:
    """`op`, `Type.member`, `module.op`, `module.Type.member`."""
    p = t.split(".")
    if len(p) == 1:
        return is_name(t)
    if len(p) == 2:
        return (bool(UPPER.match(p[0])) or p[0] in BUILTIN_TYPES or bool(LOWER.match(p[0]))) \
            and bool(LOWER.match(p[1]))
    if len(p) == 3:
        return bool(LOWER.match(p[0])) and bool(UPPER.match(p[1])) and bool(LOWER.match(p[2]))
    return False


def is_variant(t: str) -> bool:
    p = t.split(".")
    if len(p) == 2:
        return bool(UPPER.match(p[0])) and bool(LOWER.match(p[1]))
    if len(p) == 3:
        return bool(LOWER.match(p[0])) and bool(UPPER.match(p[1])) and bool(LOWER.match(p[2]))
    return False


def is_literal(t: str, kind: str) -> bool:
    if kind == "string":
        return True
    return bool(INT.match(t) or FLOAT.match(t) or t in BOOL or is_variant(t))


SLOT_CHECKS = {
    "name": lambda tok: tok.kind == "word" and is_name(tok.raw),
    "label": lambda tok: tok.kind == "word" and is_label(tok.raw),
    "Type": lambda tok: tok.kind == "word" and is_type(tok.raw),
    "string": lambda tok: tok.kind == "string",
    "int": lambda tok: tok.kind == "word" and bool(re.match(r"[0-9]+\Z", tok.raw)),
    "path": lambda tok: tok.kind == "word" and is_path(tok.raw),
    "resource": lambda tok: tok.kind == "word" and is_resource(tok.raw),
    "target": lambda tok: tok.kind == "word" and is_target(tok.raw),
    "variant": lambda tok: tok.kind == "word" and is_variant(tok.raw),
    "exportName": lambda tok: tok.kind == "word" and (is_name(tok.raw) or bool(UPPER.match(tok.raw))),
    "letValue": lambda tok: is_literal(tok.raw, tok.kind) or (tok.kind == "word" and (is_name(tok.raw) or tok.raw == "unset")),
    "cellValue": lambda tok: is_literal(tok.raw, tok.kind) or (tok.kind == "word" and is_name(tok.raw)),
}

SLOT_LABELS = {
    "name": "<name>", "label": "<label>", "Type": "<Type>", "string": '"<text>"', "int": "<integer>",
    "path": "<dotted.path>", "resource": "<module.resource>", "target": "<target>", "variant": "<Enum.variant>",
    "exportName": "<name>", "letValue": "<literal|name|unset>", "cellValue": "<literal|name>",
}


def render(pattern: tuple) -> str:
    out = []
    for s in pattern:
        if isinstance(s, frozenset):
            out.append("|".join(sorted(s)))
        elif s.endswith("+"):
            out.append(SLOT_LABELS[s[:-1]] + "...")
        else:
            out.append(SLOT_LABELS[s])
    return " ".join(out)


def match_pattern(pattern: tuple, tokens: list) -> bool:
    if pattern and isinstance(pattern[-1], str) and pattern[-1].endswith("+"):
        fixed, rep = pattern[:-1], pattern[-1][:-1]
        if len(tokens) < len(fixed) + 1:
            return False
        return all(_slot_ok(s, t) for s, t in zip(fixed, tokens)) and \
            all(SLOT_CHECKS[rep](t) for t in tokens[len(fixed):])
    if len(tokens) != len(pattern):
        return False
    return all(_slot_ok(s, t) for s, t in zip(pattern, tokens))


def _slot_ok(slot: Slot, tok) -> bool:
    if isinstance(slot, frozenset):
        return tok.kind == "word" and tok.raw in slot
    return SLOT_CHECKS[slot](tok)


# ---------------------------------------------------------------- context rows (LR-06, LR-21, LR-42 A17, A22)

CONTEXT_ORDER = ["purpose", "invariant", "verifies", "rationale", "risk", "note", "todo", "deprecated"]
CONTEXT_SHAPES = {
    "purpose": [("string",)],
    "invariant": [(NONE,), ("name", "string")],
    "verifies": [("name", "name")],
    "rationale": [("string",)],
    "risk": [(RISK_CATEGORIES, "string")],
    "note": [("string",)],
    "todo": [("string",)],
    "deprecated": [("string",)],
}
# Kinds that must state a purpose (LR-06 rule 1).
PURPOSE_REQUIRED = frozenset({"project", "module", "operation", "test", "capability", "record", "enum",
                              "table", "instance", "operationInstance", "operationType"})
# LR-42 decision D-4 (Part 4): invariants live only on operations, because only
# operations can be named by a test's `verifies` row.
INVARIANT_KINDS = frozenset({"operation"})
VERIFIES_KINDS = frozenset({"test"})

# ---------------------------------------------------------------- structural shapes

_OP_HEADER = {
    "typeParam": [(NONE,), ("Type", kw("plain", "any"))],
    "input": [(NONE,), ("name", "Type", INPUT_MODES)],
    "output": [(NONE,), ("Type",)],
    "outputOwner": [(NONE,), (kw("caller"),), ("name",)],
    "raises": [(NONE,), ("Type",)],
    "effect": [(NONE,), (EFFECT_VERBS, "resource")],
    "uses": [(NONE,), ("name",)],
    "memory": [(kw("heap"), BOOL)],
    "async": [(BOOL,)],
    "maxRecursion": [(NONE,), ("int",)],
    "label": "LABEL",  # dispatched on the label fact (LABEL_FACTS)
    "let": [("name", kw("immutable", "mutable"), "Type", "letValue")],
    "at": "STEP",  # dispatched on the step verb (STEPS)
}
_OP_SKELETON = [("typeParam", "some"), ("input", "some"), ("output", "one"), ("outputOwner", "one"), ("raises", "one"),
                ("effect", "some"), ("uses", "some"), ("memory", "one"), ("async", "one"),
                ("maxRecursion", "one"), ("label", "any"), ("let", "any"), ("at", "any")]

_CALL_SHAPES = {
    "in": [("name",)],
    "invokes": [("target",)],
    "invokesReference": [("name",)],
    "arg": [(NONE,), ("name", "Type", "name", ARG_MODES)],
    "out": [(NONE,), ("name", "Type")],
    "ownedBy": [(NONE,), ("name",)],
    "cleanedBy": [(NONE,), ("name",)],
    "borrows": [(NONE,), ("name",)],
    "catch": [(NONE,), ("name", "Type")],
}
_CALL_SKELETON = [("in", "one"), ("invokes|invokesReference", "one"), ("arg", "some"), ("out", "one"),
                  ("ownedBy", "one"), ("cleanedBy", "one"), ("borrows", "one"), ("catch", "one")]

KINDS: dict[str, dict] = {
    "project": {
        "shapes": {"target": [(kw("console", "library"),)], "module": [("path",)],
                   "entry": [(NONE,), ("target",)]},
        "skeleton": [("target", "one"), ("module", "some"), ("entry", "one")],
    },
    "module": {
        "shapes": {"path": [("path",)], "imports": [(NONE,), ("path",)], "exports": [(NONE,), ("exportName",)]},
        "skeleton": [("path", "one"), ("imports", "some"), ("exports", "some")],
    },
    "record": {
        "shapes": {"typeParam": [(NONE,), ("Type", kw("plain", "any"))], "field": [("name", "Type")]},
        "skeleton": [("typeParam", "some"), ("field", "some")],
    },
    "enum": {
        "shapes": {"typeParam": [(NONE,), ("Type", kw("plain", "any"))], "variant": [("name", NONE), ("name", "Type")]},
        "skeleton": [("typeParam", "some"), ("variant", "some")],
    },
    "alias": {
        "shapes": {"for": [("Type",)], "indexes": [(NONE,), ("Type",)]},
        "skeleton": [("for", "one"), ("indexes", "one")],
    },
    "instance": {
        "shapes": {"instantiates": [("Type", "Type+")]},
        "skeleton": [("instantiates", "one")],
    },
    "table": {
        "shapes": {"of": [("Type",)], "row": [("name", "int")], "cell": [("name", "name", "cellValue")]},
        "skeleton": [("of", "one"), ("row", "some"), ("cell", "some")],
    },
    "capability": {
        "shapes": {"grants": [(EFFECT_VERBS, "resource")], "scope": [(NONE,), ("string",)]},
        "skeleton": [("grants", "some"), ("scope", "one")],
    },
    "operationInstance": {
        "shapes": {"instantiates": [("name", "Type+")]},
        "skeleton": [("instantiates", "one")],
    },
    "operationType": {
        "shapes": {k: _OP_HEADER[k] for k in ("input", "output", "outputOwner", "raises", "effect", "async")},
        "skeleton": [("input", "some"), ("output", "one"), ("outputOwner", "one"), ("raises", "one"),
                     ("effect", "some"), ("async", "one")],
    },
    "operation": {"shapes": _OP_HEADER, "skeleton": _OP_SKELETON},
    "test": {"shapes": _OP_HEADER, "skeleton": _OP_SKELETON},
    "call": {"shapes": _CALL_SHAPES, "skeleton": _CALL_SKELETON},
    "task": {"shapes": _CALL_SHAPES, "skeleton": _CALL_SKELETON},
    "cleanup": {
        "shapes": {"in": [("name",)], "call": [("name",)], "cleans": [("name",)],
                   "onFailure": [(kw("suppress", "trap"),)], "because": [("string",)]},
        "skeleton": [("in", "one"), ("call", "one"), ("cleans", "one"), ("onFailure", "one"), ("because", "one")],
    },
    "region": {
        "shapes": {"in": [("name",)], "strategy": [(kw("arena"),)], "capacity": [("int",)],
                   "released": [(kw("atReturn", "atProcessExit"),)]},
        "skeleton": [("in", "one"), ("strategy", "one"), ("capacity", "one"), ("released", "one")],
    },
    "taskGroup": {
        "shapes": {"in": [("name",)], "limit": [("int",)]},
        "skeleton": [("in", "one"), ("limit", "one")],
    },
}

# Kinds whose entity name is a type (upper case); every other kind is lower case.
TYPE_KINDS = frozenset({"record", "enum", "alias", "instance", "operationType"})
# Kinds owned by one operation through their `in` row (LR-02): names are scoped to that operation.
OWNED_KINDS = frozenset({"call", "task", "cleanup", "region", "taskGroup"})
# Kinds that only appear in build.sem.
PROJECT_KINDS = frozenset({"project"})

# ---------------------------------------------------------------- block labels (LR-23, LR-42 A13)

LABEL_ORDER = ["loopKind", "within", "maxIterations", "counter", "over", "because",
               "purpose", "rationale", "risk", "note", "todo"]
LABEL_FACTS = {
    "loopKind": [(LOOP_KINDS | NONE,)],
    "within": [(NONE,), ("label",)],
    "maxIterations": [("int",), ("name",), (kw("unbounded"),)],
    "counter": [("name",)],
    "over": [("name",)],
    "because": [("string",)],
    "purpose": [("string",)],
    "rationale": [("string",)],
    "risk": [(RISK_CATEGORIES, "string")],
    "note": [("string",)],
    "todo": [("string",)],
}

# ---------------------------------------------------------------- steps (LR-16, LR-30, LR-33, LR-42)

_G, _E = kw("goto"), kw("else")
STEPS = {
    "do": [("name",)],
    "start": [("name",), ("name", kw("into"), "name")],
    "join": [("name",)],
    "cancel": [("name",)],
    "awaitSlot": [("name",)],
    "defer": [("name",)],
    "set": [("name", "name")],
    "goto": [("label",)],
    "branch": [
        (kw("if"), "name", _G, "label", _E, _G, "label"),
        (kw("ifError"), "name", _G, "label", _E, _G, "label"),
        (kw("ifNext"), "name", kw("bind"), "name", "Type", _G, "label", _E, _G, "label"),
    ],
    "match": [("name", "Type")],
    "case": [("variant", kw("bind"), NONE, NONE, _G, "label"), ("variant", kw("bind"), "name", "Type", _G, "label")],
    "return": [(kw("ok"), NONE), (kw("ok"), "name"), (kw("error"), "name")],
}
TERMINATORS = frozenset({"return", "goto", "branch", "case"})


def textmate_grammar() -> dict:
    """The editor grammar, generated from this table so highlighting never drifts from the parser."""
    predicates = sorted({p for spec in KINDS.values() for g, _c in spec["skeleton"] for p in g.split("|")}
                        | set(CONTEXT_ORDER) - {"is", "at"})
    steps = sorted(STEPS)
    words = set()
    for alts in list(STEPS.values()) + list(LABEL_FACTS.values()) + \
            [a for spec in KINDS.values() for a in spec["shapes"].values() if isinstance(a, list)]:
        for alt in alts:
            for s in alt:
                if isinstance(s, frozenset):
                    words |= s
    words -= RESERVED
    alt = lambda xs: "|".join(sorted(xs, key=lambda x: (-len(x), x)))  # noqa: E731
    return {
        "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
        "name": "SemanticScript",
        "scopeName": "source.semanticscript",
        "comment": "Generated by `refined grammar --textmate` from semanticscript/compiler/refined/shapes.py.",
        "patterns": [
            {"include": "#comment"}, {"include": "#entity"}, {"include": "#step"}, {"include": "#label"},
            {"include": "#fact"}, {"include": "#string"}, {"include": "#literal"}, {"include": "#word"},
            {"include": "#type"},
        ],
        "repository": {
            "comment": {"name": "comment.line.number-sign.semanticscript", "match": "(?:^|(?<=[ \\t]))#.*$"},
            "string": {
                "name": "string.quoted.double.semanticscript", "begin": "\"", "end": "\"",
                "patterns": [{"name": "constant.character.escape.semanticscript",
                              "match": "\\\\(?:[\"\\\\nt]|x[0-9A-Fa-f]{2})"}],
            },
            "entity": {
                "match": f"^([A-Za-z][A-Za-z0-9]*)[ \\t]+(is)[ \\t]+({alt(KINDS)})\\b",
                "captures": {"1": {"name": "entity.name.semanticscript"}, "2": {"name": "keyword.other.semanticscript"},
                             "3": {"name": "storage.type.semanticscript"}},
            },
            "step": {
                "match": f"^([a-z][A-Za-z0-9]*)[ \\t]+(at)[ \\t]+([a-z][A-Za-z0-9]*)[ \\t]+({alt(steps)})\\b",
                "captures": {"1": {"name": "variable.other.subject.semanticscript"},
                             "2": {"name": "keyword.other.semanticscript"},
                             "3": {"name": "entity.name.label.semanticscript"},
                             "4": {"name": "keyword.control.semanticscript"}},
            },
            "label": {
                "match": f"^([a-z][A-Za-z0-9]*)[ \\t]+(label)[ \\t]+([a-z][A-Za-z0-9]*)[ \\t]+({alt(LABEL_FACTS)})\\b",
                "captures": {"1": {"name": "variable.other.subject.semanticscript"},
                             "2": {"name": "keyword.other.semanticscript"},
                             "3": {"name": "entity.name.label.semanticscript"},
                             "4": {"name": "keyword.other.semanticscript"}},
            },
            "fact": {
                "match": f"^([A-Za-z][A-Za-z0-9]*)[ \\t]+({alt(predicates)})\\b",
                "captures": {"1": {"name": "variable.other.subject.semanticscript"},
                             "2": {"name": "keyword.other.semanticscript"}},
            },
            "literal": {"patterns": [
                {"name": "constant.language.semanticscript", "match": f"\\b(?:{alt(RESERVED)})\\b"},
                {"name": "constant.numeric.semanticscript", "match": "(?<![A-Za-z0-9.])-?[0-9]+(?:\\.[0-9]+)?\\b"},
            ]},
            "word": {"name": "keyword.operator.semanticscript", "match": f"(?<![A-Za-z0-9.])(?:{alt(words)})\\b"},
            "type": {"name": "entity.name.type.semanticscript",
                     "match": "\\b(?:[a-z][A-Za-z0-9]*\\.)?[A-Z][A-Za-z0-9]*(?:\\.[a-z][A-Za-z0-9]*)?\\b"},
        },
    }


def grammar_markdown() -> str:
    """Render the shape table as a Markdown reference."""
    out = ["# Refined syntax: row shapes", "",
           "Generated from `semanticscript/compiler/refined/shapes.py`. Do not edit by hand.", "",
           "Every row is `<subject> <predicate> <payload>`. Context rows (" +
           ", ".join(f"`{c}`" for c in CONTEXT_ORDER) + ") come directly after the `is` row, in that order.", ""]
    card_text = {"one": "exactly one", "some": "one or more (`none` alone when empty)", "any": "zero or more"}
    for kind, spec in KINDS.items():
        out += [f"## `{kind}`", "", "| Predicate | Rows | Shape |", "| --- | --- | --- |"]
        for pred, card in spec["skeleton"]:
            for p in pred.split("|"):
                shapes = spec["shapes"][p]
                if shapes == "LABEL":
                    forms = [f"{render(('label',))} {f} {render(alt)}" for f in LABEL_ORDER for alt in LABEL_FACTS[f]]
                elif shapes == "STEP":
                    forms = [f"{render(('label',))} {v} {render(alt)}" for v in STEPS for alt in STEPS[v]]
                else:
                    forms = [render(alt) for alt in shapes]
                cell = "<br>".join("`" + f.replace("|", "\\|") + "`" for f in forms)
                out.append(f"| `{p}` | {card_text[card]} | {cell} |")
        out.append("")
    return "\n".join(out)
