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
        return [r for r in self.rows[1:] if r.predicate == predicate]

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
