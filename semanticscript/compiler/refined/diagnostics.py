"""Diagnostics for the refined front end.

Every diagnostic is an error: the refined language has no warning tier (P-2,
docs/language-refinement.md). Codes are grouped by the pass that emits them.
"""
from __future__ import annotations

from dataclasses import dataclass

CODES: dict[str, str] = {
    # R1xx lexical (LR-11)
    "R101": "Whitespace other than space or tab outside a string",
    "R102": "Control character in source",
    "R104": "Misplaced quote or `#`",
    "R105": "Unsupported string escape",
    "R106": "Unterminated string",
    # R2xx rows and entities
    "R201": "Row outside its entity",
    "R202": "Unknown entity kind",
    "R203": "Duplicate entity name",
    "R204": "Predicate not allowed on this entity kind",
    "R205": "Row does not match its shape",
    "R206": "Reserved word used as a name",
    "R207": "Name has the wrong case for its kind",
    # R3xx skeleton
    "R301": "Row out of skeleton order",
    "R302": "Wrong number of rows for a predicate",
    "R303": "`none` row beside other rows of the same predicate",
    "R304": "Context row rule broken",
    "R305": "Block label declaration missing or wrong",
    "R306": "Table rule broken",
    # R4xx names, types, signatures
    "R401": "Unresolved name",
    "R402": "Name refers to the wrong kind of thing",
    "R403": "Type mismatch",
    "R404": "Import rule broken",
    "R405": "Arguments do not match the target's parameters",
    "R406": "Passing mode mismatch",
    "R407": "Declared effects differ from performed effects",
    "R408": "Capability rule broken",
    "R409": "Ownership row disagrees with the target",
    "R410": "Declared fact differs from the program (async, memory heap, maxRecursion)",
    "R411": "Duplicate name in an operation's scope",
    # R5xx control flow
    "R501": "Block structure",
    "R502": "Jump to an unknown label",
    "R503": "Loop declaration rule broken",
    "R504": "Loop entry or cycle rule broken",
    "R505": "Counted loop does not advance its counter exactly once",
    "R506": "Fallible activation not followed by its error branch",
    "R507": "Value used where it may not be set",
    "R508": "Return rule broken",
    "R509": "Match does not cover the enum exactly",
    "R510": "Entity activated the wrong number of times",
    "R511": "Unreachable block",
    "R512": "Task or task group not settled on every path",
    "R513": "Owned value not released, given, or returned exactly once on a path",
    "R514": "Borrowed value escapes its loan",
    "R515": "Exclusive loan of a value that is shared or only read-borrowed",
    # R6xx project
    "R601": "build.sem rule broken",
    "R602": "Module name or file location rule broken",
    "R603": "Import cycle",
    "R604": "Test verification rule broken",
    "R605": "Structure changed but its context rows did not",
    # R9xx backend
    "R901": "Not yet supported by the backend",
}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    file: str
    line: int

    def format(self) -> str:
        return f"{self.file}:{self.line}: {self.code} {self.message}"

    def to_json(self) -> dict:
        return {
            "code": self.code,
            "summary": CODES.get(self.code, ""),
            "message": self.message,
            "file": self.file,
            "line": self.line,
        }


class Sink:
    """Collects diagnostics for one file."""

    def __init__(self, file: str):
        self.file = file
        self.items: list[Diagnostic] = []

    def error(self, code: str, line: int, message: str) -> None:
        assert code in CODES, code
        self.items.append(Diagnostic(code, message, self.file, line))
