from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Token:
    surface: str
    lemma: str
    reading: str
    part_of_speech: str
    note: str
    start: int
    end: int


@dataclass(frozen=True)
class GrammarPoint:
    title: str
    explanation: str


@dataclass(frozen=True)
class SentenceExplanation:
    meaning: str
    yasashiku: str
    grammar_points: List[GrammarPoint]
    nuance: str
    raw: Optional[str] = None


@dataclass(frozen=True)
class DictionaryEntry:
    entry_id: str
    primary_spelling: str
    readings: List[str]
    common: bool
    senses: List[str]
    word_classes: List[str]


@dataclass(frozen=True)
class LookupItem:
    term: str
    entries: List[DictionaryEntry]
    start: int
    end: int


@dataclass(frozen=True)
class ClipboardEntry:
    text: str
    kind: str
    captured_at: str
    tokens: List[Token]
    lookup_items: List[LookupItem]
    explanation: Optional[SentenceExplanation] = None
