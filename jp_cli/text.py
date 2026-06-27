from __future__ import annotations

from typing import Any, List, Optional

from fugashi import Tagger

from .models import Token


PARTICLE_HINTS = {
    "は": "topic marker",
    "が": "subject marker",
    "を": "direct object marker",
    "に": "time/place/target marker",
    "へ": "direction marker",
    "で": "place/means marker",
    "と": "and/with/quote marker",
    "も": "also/even marker",
    "の": "possessive/nominalizer",
    "から": "from/because",
    "まで": "until/to",
    "より": "than/from",
}


tagger: Optional[Tagger] = None


def tokenize_japanese(text: str) -> List[Token]:
    tokens: List[Token] = []
    offset = 0
    for word in get_tagger()(text):
        surface = word.surface
        start = text.find(surface, offset)
        if start < 0:
            start = offset
        end = start + len(surface)
        if not surface.strip():
            offset = end
            continue

        feature = word.feature
        pos = feature_value(feature, "pos1")
        if pos == "補助記号":
            offset = end
            continue

        lemma = feature_value(feature, "lemma") or surface
        reading = kata_to_hira(feature_value(feature, "kana")) or surface
        note = token_note(surface, pos)
        tokens.append(
            Token(
                surface=surface,
                lemma=lemma,
                reading=reading,
                part_of_speech=pos or "unknown",
                note=note,
                start=start,
                end=end,
            )
        )
        offset = end
    return tokens


def get_tagger() -> Tagger:
    global tagger
    if tagger is None:
        tagger = Tagger()
    return tagger


def feature_value(feature: Any, name: str) -> str:
    value = getattr(feature, name, "")
    if value is None or value == "*":
        return ""
    return str(value)


def token_note(surface: str, pos: str) -> str:
    if surface in PARTICLE_HINTS:
        return PARTICLE_HINTS[surface]
    if pos == "助詞":
        return "particle"
    if pos == "助動詞":
        return "auxiliary"
    if pos == "動詞":
        return "verb"
    if pos == "名詞":
        return "noun"
    if pos == "形容詞":
        return "i-adjective"
    if pos == "副詞":
        return "adverb"
    return ""


def kata_to_hira(text: str) -> str:
    result = []
    for char in text:
        codepoint = ord(char)
        if 0x30A1 <= codepoint <= 0x30F6:
            result.append(chr(codepoint - 0x60))
        else:
            result.append(char)
    return "".join(result)


def normalize_clipboard_text(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines()]
    return "\n".join(line for line in lines if line)


def contains_japanese(text: str) -> bool:
    return any(is_japanese_char(char) for char in text)


def is_japanese_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3040 <= codepoint <= 0x309F  # Hiragana
        or 0x30A0 <= codepoint <= 0x30FF  # Katakana
        or 0x3400 <= codepoint <= 0x4DBF  # CJK Extension A
        or 0x4E00 <= codepoint <= 0x9FFF  # CJK Unified Ideographs
        or 0xFF66 <= codepoint <= 0xFF9F  # Half-width Katakana
    )


def is_kana_text(text: str) -> bool:
    if not text:
        return False
    return all(is_kana_char(char) for char in text)


def is_kana_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3040 <= codepoint <= 0x309F
        or 0x30A0 <= codepoint <= 0x30FF
        or 0xFF66 <= codepoint <= 0xFF9F
    )


def classify_text(text: str) -> str:
    compact = "".join(char for char in text if not char.isspace())
    sentence_punctuation = "。！？!?…"

    if "\n" in text:
        return "sentence"
    if any(mark in compact for mark in sentence_punctuation):
        return "sentence"
    if len(compact) >= 18:
        return "sentence"
    if count_japanese_runs(compact) >= 2 and has_particle_like_char(compact):
        return "sentence"
    return "word/phrase"


def count_japanese_runs(text: str) -> int:
    runs = 0
    in_run = False
    for char in text:
        if is_japanese_char(char):
            if not in_run:
                runs += 1
                in_run = True
        else:
            in_run = False
    return runs


def has_particle_like_char(text: str) -> bool:
    return any(char in text for char in "はがをにへでとものからまでより")
