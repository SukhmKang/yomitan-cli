from __future__ import annotations

from typing import List, Optional

from .deinflect import Deinflection, deinflect, entry_matches_conditions
from .dictionary import lookup_dictionary, lookup_dictionary_terms
from .models import DictionaryEntry, LookupItem, Token
from .text import contains_japanese, is_japanese_char, tokenize_japanese


def build_lookup_items(source_text: str, tokens: Optional[List[Token]] = None) -> List[LookupItem]:
    items: List[LookupItem] = []
    scan_tokens = tokens if tokens is not None else tokenize_japanese(source_text)
    token_by_start = {token.start: token for token in scan_tokens}
    skipped_until = {
        token.start: token.end
        for token in scan_tokens
        if token.part_of_speech in {"助動詞", "補助記号"}
    }
    offset = 0
    while offset < len(source_text):
        if offset in skipped_until:
            offset = skipped_until[offset]
            continue
        token = token_by_start.get(offset)
        if token is not None and token.part_of_speech == "助詞":
            item = lookup_particle(token)
            if item is not None:
                items.append(item)
            offset = token.end
            continue
        if not is_japanese_char(source_text[offset]):
            offset += 1
            continue

        item = lookup_longest_span(
            source_text,
            offset,
            preferred_pos=token.part_of_speech if token is not None else None,
            preferred_spelling=token.lemma if token is not None else None,
        )
        if item is None:
            offset += 1
            continue

        items.append(item)
        offset = item.end

    return items


def lookup_particle(token: Token) -> Optional[LookupItem]:
    entries = [
        entry
        for entry in lookup_dictionary(token.surface, limit=12)
        if "prt" in entry.word_classes
    ]
    if not entries:
        return None
    return LookupItem(
        term=token.surface,
        entries=entries[:5],
        start=token.start,
        end=token.end,
    )


def lookup_longest_span(
    source_text: str,
    char_offset: int,
    max_chars: int = 32,
    preferred_pos: Optional[str] = None,
    preferred_spelling: Optional[str] = None,
) -> Optional[LookupItem]:
    search_text = source_text[char_offset : char_offset + max_chars]
    prefixes = japanese_prefixes(search_text)
    candidates_by_source = []
    all_terms = []
    seen_terms = set()

    for source in prefixes:
        candidates = deinflect(source)
        candidates_by_source.append((source, candidates))
        for candidate in candidates:
            for term, _conditions in dictionary_terms_for_candidate(candidate):
                if term not in seen_terms:
                    seen_terms.add(term)
                    all_terms.append(term)

    dictionary_results = lookup_dictionary_terms(all_terms, limit_per_term=12)
    for source, candidates in candidates_by_source:
        matches = dictionary_matches_for_deinflections(
            candidates,
            dictionary_results,
            preferred_pos=preferred_pos,
            preferred_spelling=preferred_spelling,
        )
        if matches:
            return LookupItem(
                term=source,
                entries=matches[:5],
                start=char_offset,
                end=char_offset + len(source),
            )
    return None


def japanese_prefixes(text: str) -> List[str]:
    prefixes = []
    for length in range(len(text), 0, -1):
        prefix = text[:length]
        if not contains_japanese(prefix):
            continue
        if any(is_lookup_boundary(char) for char in prefix[:-1]):
            continue
        prefixes.append(prefix)
    return prefixes


def is_lookup_boundary(char: str) -> bool:
    return char.isspace() or char in "。、！？!?「」『』（）()［］[]【】・,;:"


def dictionary_matches_for_deinflections(
    candidates: List[Deinflection],
    dictionary_results: dict,
    preferred_pos: Optional[str] = None,
    preferred_spelling: Optional[str] = None,
) -> List[DictionaryEntry]:
    matches = []
    seen_entry_ids = set()

    for candidate in candidates:
        for term, conditions in dictionary_terms_for_candidate(candidate):
            for entry in dictionary_results.get(term, []):
                if entry.entry_id in seen_entry_ids:
                    continue
                if not entry_matches_conditions(entry.word_classes, conditions):
                    continue
                if not is_useful_lookup_entry(entry):
                    continue
                seen_entry_ids.add(entry.entry_id)
                matches.append(entry)

    return sorted(
        matches,
        key=lambda entry: (
            entry.primary_spelling == preferred_spelling,
            dictionary_pos_affinity(preferred_pos, entry.word_classes),
            entry.common,
        ),
        reverse=True,
    )


def dictionary_terms_for_candidate(candidate: Deinflection) -> List[tuple]:
    terms = [(candidate.term, candidate.conditions)]
    if candidate.term.endswith("する") and len(candidate.term) > 2:
        terms.append((candidate.term[:-2], frozenset({"vs"})))
    return terms


def dictionary_pos_affinity(
    tokenizer_pos: Optional[str],
    word_classes: List[str],
) -> int:
    preferred_classes = {
        "名詞": {"n", "n-adv", "n-pr", "n-pref", "n-suf", "vs"},
        "動詞": {"v1", "v5", "vk", "vs", "vz"},
        "形容詞": {"adj-i", "adj-ix"},
        "副詞": {"adv", "adv-to"},
        "連体詞": {"adj-pn"},
    }.get(tokenizer_pos)
    if not preferred_classes:
        return 0

    normalized = set()
    for word_class in word_classes:
        if word_class.startswith("v5"):
            normalized.add("v5")
        elif word_class.startswith("vs"):
            normalized.add("vs")
        else:
            normalized.add(word_class)
    return 1 if not normalized.isdisjoint(preferred_classes) else 0


def is_useful_lookup_entry(entry: DictionaryEntry) -> bool:
    functional_classes = {"prt", "aux", "aux-v", "aux-adj", "cop", "conj"}
    return not entry.word_classes or not set(entry.word_classes).issubset(functional_classes)
