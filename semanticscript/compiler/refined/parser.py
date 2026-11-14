"""Rows to entities, then shape, skeleton, and cardinality checks (plan steps 1-3)."""
from __future__ import annotations

from . import shapes as S
from .diagnostics import Sink
from .model import Entity, Line, Row, SourceFile


def parse(lines: list[Line], path: str, sink: Sink) -> SourceFile:
    """Group rows into entities. An entity starts at its `is` row and its rows
    follow without interruption (LR-42 A22): a row whose subject is not the
    current entity is an error, not a silent re-open."""
    entities: list[Entity] = []
    current: Entity | None = None
    pending: list[str] = []
    for line in lines:
        if not line.tokens:
            if line.comment is not None:
                pending.append(line.comment)
            continue
        row = Row(line.number, line.tokens, pending + ([line.comment] if line.comment is not None else []))
        pending = []
        toks = line.tokens
        if toks[0].kind != "word":
            sink.error("R205", row.line, "a row starts with its subject name, not a string")
            continue
        if len(toks) < 2:
            sink.error("R205", row.line, f"row `{toks[0].raw}` has no predicate")
            continue
        if toks[1].is_word("is"):
            if len(toks) != 3 or toks[2].kind != "word":
                sink.error("R205", row.line, "an `is` row is exactly `<name> is <kind>`")
                current = None
                continue
            kind = toks[2].raw
            if kind not in S.KINDS:
                sink.error("R202", row.line, f"unknown entity kind `{kind}`; kinds are: {', '.join(sorted(S.KINDS))}")
                current = Entity(toks[0].raw, None, row.line, [row], path)
                continue
            current = Entity(toks[0].raw, kind, row.line, [row], path)
            entities.append(current)
            continue
        if current is None or toks[0].raw != current.name:
            where = f"inside `{current.name}`" if current is not None else "before any `is` row"
            sink.error("R201", row.line, f"row for `{toks[0].raw}` appears {where}; an entity's rows come "
                       f"directly after its own `is` row, with no other entity's rows in between")
            continue
        current.rows.append(row)
    return SourceFile(path, entities, pending)


def check_entity(ent: Entity, sink: Sink) -> None:
    """Names, shapes, context rows, skeleton order, and cardinality for one entity."""
    _check_entity_name(ent, sink)
    spec = S.KINDS[ent.kind]
    shapes = spec["shapes"]
    rank: dict[str, int] = {}
    for i, c in enumerate(S.CONTEXT_ORDER):
        rank[c] = i
    base = len(S.CONTEXT_ORDER)
    for i, (group, _card) in enumerate(spec["skeleton"]):
        for p in group.split("|"):
            rank[p] = base + i

    good_rows: list[Row] = []
    for row in ent.rows[1:]:
        pred = row.predicate
        if pred in S.CONTEXT_SHAPES:
            if not _context_allowed(ent.kind, pred):
                sink.error("R204", row.line, _context_not_allowed(ent.kind, pred))
                continue
            if _match_any(S.CONTEXT_SHAPES[pred], row.args, row, ent, sink, pred):
                good_rows.append(row)
            continue
        if pred not in shapes:
            allowed = ", ".join(f"`{p}`" for g, _c in spec["skeleton"] for p in g.split("|"))
            sink.error("R204", row.line, f"`{pred}` is not a predicate of a {ent.kind}; "
                       f"a {ent.kind} takes {allowed} and the context rows")
            continue
        shape = shapes[pred]
        if shape == "LABEL":
            if _check_label_row(row, sink):
                good_rows.append(row)
            continue
        if shape == "STEP":
            if _check_step_row(row, sink):
                good_rows.append(row)
            continue
        if _match_any(shape, row.args, row, ent, sink, pred):
            good_rows.append(row)

    # skeleton order (LR-42 A22: context first, then the kind's skeleton)
    last = -1
    for row in good_rows:
        r = rank[row.predicate]
        if r < last:
            sink.error("R301", row.line, f"`{row.predicate}` is out of order; a {ent.kind}'s rows are: "
                       f"`is`, context rows, then " + ", ".join(f"`{g}`" for g, _c in spec["skeleton"]))
        last = max(last, r)

    # cardinality
    for group, card in spec["skeleton"]:
        preds = group.split("|")
        rows = [r for r in good_rows if r.predicate in preds]
        shown = " or ".join(f"`{p}`" for p in preds)
        if card == "one" and len(rows) != 1:
            if rows:
                sink.error("R302", rows[1].line, f"a {ent.kind} has exactly one {shown} row; this is another")
            else:
                sink.error("R302", ent.line, f"{ent.kind} `{ent.name}` has no {shown} row")
        if card == "some":
            if not rows:
                sink.error("R302", ent.line, f"{ent.kind} `{ent.name}` has no {shown} row; "
                           f"write `{ent.name} {preds[0]} none` if there are none")
            elif any(_is_none_row(r) for r in rows) and len(rows) > 1:
                sink.error("R303", rows[0].line, f"`{preds[0]} none` must be the only {shown} row")
            _no_duplicate_rows(rows, sink)
    _check_context_cardinality(ent, good_rows, sink)
    # Rows that broke their shape are reported above and dropped here, so later passes only ever see
    # well-formed rows (a malformed row must produce a diagnostic, never a crash).
    ent.rows = ent.rows[:1] + good_rows


# ---------------------------------------------------------------- helpers

def _is_none_row(row: Row) -> bool:
    return len(row.args) == 1 and row.args[0].is_word("none")


def _no_duplicate_rows(rows: list[Row], sink: Sink) -> None:
    seen: dict[tuple, int] = {}
    for r in rows:
        key = tuple(t.raw for t in r.tokens)
        if key in seen:
            sink.error("R302", r.line, f"this row repeats line {seen[key]}")
        else:
            seen[key] = r.line


def _match_any(alternatives, tokens, row: Row, ent: Entity, sink: Sink, what: str) -> bool:
    if any(S.match_pattern(alt, tokens) for alt in alternatives):
        return True
    reserved = [t.raw for t in tokens if t.kind == "word" and t.raw in S.RESERVED and t.raw not in _allowed_words(alternatives)]
    if reserved:
        sink.error("R206", row.line, f"`{reserved[0]}` is a reserved word and cannot be a name here")
        return False
    problem = _name_slot_problem(alternatives, tokens)
    if problem is not None:
        sink.error(problem[0], row.line, problem[1])
        return False
    forms = " | ".join(f"`{ent.name} {what} {S.render(a)}`" for a in alternatives)
    sink.error("R205", row.line, f"`{what}` row does not match its shape; expected {forms}")
    return False


def _name_slot_problem(alternatives, tokens) -> tuple[str, str] | None:
    """When the only thing wrong with a row is one name, say so precisely: a reserved word where a name
    goes is R206, and a name with the wrong case is R207 (values and labels start lower-case)."""
    found = None
    for alt in alternatives:
        fixed = [s for s in alt if not (isinstance(s, str) and s.endswith("+"))]
        if len(fixed) != len(alt) or len(alt) != len(tokens):
            continue
        bad = [(s, t) for s, t in zip(alt, tokens) if not S._slot_ok(s, t)]
        if len(bad) != 1:
            continue
        slot, tok = bad[0]
        if slot in ("name", "label") and tok.kind == "word":
            if tok.raw in S.RESERVED:
                found = ("R206", f"`{tok.raw}` is a reserved word and cannot be a {slot} here")
            elif S.UPPER.match(tok.raw):
                found = ("R207", f"`{tok.raw}` is a {slot}, so it starts with a lower-case letter "
                         f"(`{tok.raw[0].lower() + tok.raw[1:]}`); upper-case names are types")
        if found:
            return found
    return None


def _allowed_words(alternatives) -> set[str]:
    out: set[str] = set()
    for alt in alternatives:
        for s in alt:
            if isinstance(s, frozenset):
                out |= s
            elif s in ("label",):
                out.add("begin")
            elif s == "letValue":
                out |= {"true", "false", "unset"}
            elif s == "cellValue":
                out |= {"true", "false"}
    return out


def _check_label_row(row: Row, sink: Sink) -> bool:
    a = row.args
    if len(a) < 2 or not S.SLOT_CHECKS["label"](a[0]) or a[1].raw not in S.LABEL_FACTS:
        sink.error("R205", row.line, "label row must be `<op> label <label> <fact> ...` with a fact from: "
                   + ", ".join(S.LABEL_ORDER))
        return False
    fact = a[1].raw
    if any(S.match_pattern(alt, a[2:]) for alt in S.LABEL_FACTS[fact]):
        return True
    forms = " | ".join(f"`label <label> {fact} {S.render(alt)}`" for alt in S.LABEL_FACTS[fact])
    sink.error("R205", row.line, f"`label ... {fact}` row does not match its shape; expected {forms}")
    return False


def _check_step_row(row: Row, sink: Sink) -> bool:
    a = row.args
    if len(a) < 2 or not S.SLOT_CHECKS["label"](a[0]) or a[1].raw not in S.STEPS:
        sink.error("R205", row.line, "step row must be `<op> at <label> <step> ...` with a step from: "
                   + ", ".join(S.STEPS))
        return False
    verb = a[1].raw
    if any(S.match_pattern(alt, a[2:]) for alt in S.STEPS[verb]):
        return True
    forms = " | ".join(f"`at <label> {verb} {S.render(alt)}`" for alt in S.STEPS[verb])
    sink.error("R205", row.line, f"`{verb}` step does not match its shape; expected {forms}")
    return False


def _context_allowed(kind: str, pred: str) -> bool:
    if pred == "invariant":
        return kind in S.INVARIANT_KINDS
    if pred == "verifies":
        return kind in S.VERIFIES_KINDS
    return True


def _context_not_allowed(kind: str, pred: str) -> str:
    if pred == "invariant":
        return (f"`invariant` belongs only on operations, because only an operation can be named by a test's "
                f"`verifies` row; describe a {kind} with `purpose`, `rationale`, or `note`")
    return "`verifies` belongs only on a test"


def _check_context_cardinality(ent: Entity, rows: list[Row], sink: Sink) -> None:
    purposes = [r for r in rows if r.predicate == "purpose"]
    if ent.kind in S.PURPOSE_REQUIRED and not purposes:
        sink.error("R304", ent.line, f"{ent.kind} `{ent.name}` needs a `purpose` row")
    if len(purposes) > 1:
        sink.error("R302", purposes[1].line, "an entity has at most one `purpose` row")
    if ent.kind == "operation":
        inv = [r for r in rows if r.predicate == "invariant"]
        if not inv:
            sink.error("R304", ent.line, f"operation `{ent.name}` needs an `invariant` row "
                       "(`invariant none` if it is not exported and has no tested claim)")
        elif any(_is_none_row(r) for r in inv) and len(inv) > 1:
            sink.error("R303", inv[0].line, "`invariant none` must be the only invariant row")
        ids = {}
        for r in inv:
            if not _is_none_row(r):
                if r.args[0].raw in ids:
                    sink.error("R304", r.line, f"invariant id `{r.args[0].raw}` is already used on line {ids[r.args[0].raw]}")
                ids[r.args[0].raw] = r.line
    if ent.kind == "test" and not [r for r in rows if r.predicate == "verifies"]:
        sink.error("R604", ent.line, f"test `{ent.name}` has no `verifies` row")
    for r in rows:
        if r.predicate in S.CONTEXT_SHAPES and r.args and r.args[-1].kind == "string":
            _filler(ent, r, r.args[-1].value, sink)


def _filler(ent: Entity, row: Row, text: str, sink: Sink) -> None:
    """LR-42 A17: empty, under ten characters, or just the entity's name."""
    norm = "".join(text.split()).lower()
    if len(text.strip()) < 10 or norm == ent.name.lower():
        sink.error("R304", row.line, f"`{row.predicate}` text is filler (under ten characters or the entity's "
                   "own name); say something a reader could not get from the name")


def _check_entity_name(ent: Entity, sink: Sink) -> None:
    name = ent.name
    if name in S.RESERVED:
        sink.error("R206", ent.line, f"`{name}` is a reserved word and cannot name an entity")
        return
    if ent.kind in S.TYPE_KINDS:
        if not S.UPPER.match(name):
            sink.error("R207", ent.line, f"a {ent.kind} is a type, so its name starts with an upper-case letter "
                       f"and has only letters and digits (`{name[:1].upper() + name[1:]}`)")
    elif not S.LOWER.match(name):
        sink.error("R207", ent.line, f"a {ent.kind} name starts with a lower-case letter and has only letters "
                   f"and digits (`{name[:1].lower() + name[1:]}`)")
