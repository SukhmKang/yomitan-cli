from __future__ import annotations

from .explain import explain_sentence
from .lookup import build_lookup_items
from .models import ClipboardEntry


def with_sentence_explanation(entry: ClipboardEntry) -> ClipboardEntry:
    return ClipboardEntry(
        text=entry.text,
        kind=entry.kind,
        captured_at=entry.captured_at,
        tokens=entry.tokens,
        lookup_items=entry.lookup_items,
        explanation=explain_sentence(entry.text),
    )


def with_lookup_items(entry: ClipboardEntry) -> ClipboardEntry:
    return ClipboardEntry(
        text=entry.text,
        kind=entry.kind,
        captured_at=entry.captured_at,
        tokens=entry.tokens,
        lookup_items=build_lookup_items(entry.text, entry.tokens),
        explanation=entry.explanation,
    )
