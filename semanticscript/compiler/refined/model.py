"""Source model for the refined front end: tokens, rows, entities, modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Token:
    kind: str  # "word" or "string"
    raw: str  # exactly as written
    value: str  # decoded text for strings, raw for words
    col: int

    def is_word(self, text: Optional[str] = None) -> bool:
        return self.kind == "word" and (text is None or self.raw == text)


@dataclass
class Line:
    number: int
    tokens: list[Token]
    comment: Optional[str]


@dataclass
class Row:
    line: int
    tokens: list[Token]
    comments: list[str] = field(default_factory=list)

    @property
    def subject(self) -> str:
        return self.tokens[0].raw

    @property
    def predicate(self) -> str:
        return self.tokens[1].raw if len(self.tokens) > 1 else ""

    @property
    def args(self) -> list[Token]:
        return self.tokens[2:]

    def text(self, i: int) -> Optional[str]:
        """Raw text of payload token i (0-based after the predicate), or None."""
        a = self.args
        return a[i].raw if i < len(a) else None


@dataclass
class Entity:
    name: str
    kind: Optional[str]
    line: int
    rows: list[Row] = field(default_factory=list)  # rows[0] is the `is` row
    file: str = ""

    def facts(self, predicate: str) -> list[Row]:
        """Rows of one predicate, in order. Indexed once per row list (D-106: a linear scan per question made
        checking quadratic in a module's size); the index is rebuilt if the rows are replaced or change in number."""
        key = (id(self.rows), len(self.rows))
        index = self.__dict__.get("_index")
        if index is None or index[0] != key:
            by: dict[str, list[Row]] = {}
            for r in self.rows[1:]:
                by.setdefault(r.predicate, []).append(r)
            index = (key, by)
            self.__dict__["_index"] = index
        return list(index[1].get(predicate, ()))

    def fact(self, predicate: str) -> Optional[Row]:
        f = self.facts(predicate)
        return f[0] if f else None

    def value(self, predicate: str, i: int = 0) -> Optional[str]:
        r = self.fact(predicate)
        return r.text(i) if r else None

    @property
    def owner(self) -> Optional[str]:
        return self.value("in")


@dataclass
class SourceFile:
    path: str
    entities: list[Entity]
    trailing_comments: list[str] = field(default_factory=list)
