from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from Yomitan's language transformer and Japanese transform rules.
# Copyright (C) 2024-2026 Yomitan Authors.

from dataclasses import dataclass
from typing import FrozenSet, Iterable, List, Optional, Sequence, Tuple


ConditionSet = FrozenSet[str]


@dataclass(frozen=True)
class DeinflectionRule:
    inflected_suffix: str
    dictionary_suffix: str
    conditions_in: ConditionSet
    conditions_out: ConditionSet
    reason: str


@dataclass(frozen=True)
class Deinflection:
    term: str
    conditions: Optional[ConditionSet]
    reasons: Tuple[str, ...]


def rule(
    inflected_suffix: str,
    dictionary_suffix: str,
    conditions_in: Iterable[str],
    conditions_out: Iterable[str],
    reason: str,
) -> DeinflectionRule:
    return DeinflectionRule(
        inflected_suffix=inflected_suffix,
        dictionary_suffix=dictionary_suffix,
        conditions_in=frozenset(conditions_in),
        conditions_out=frozenset(conditions_out),
        reason=reason,
    )


def godan_rules(
    endings: Sequence[Tuple[str, str]],
    conditions_in: Iterable[str],
    reason: str,
) -> List[DeinflectionRule]:
    return [
        rule(inflected, dictionary, conditions_in, {"v5"}, reason)
        for inflected, dictionary in endings
    ]


GODAN_I = (
    ("い", "う"),
    ("き", "く"),
    ("ぎ", "ぐ"),
    ("し", "す"),
    ("ち", "つ"),
    ("に", "ぬ"),
    ("び", "ぶ"),
    ("み", "む"),
    ("り", "る"),
)
GODAN_A = (
    ("わ", "う"),
    ("か", "く"),
    ("が", "ぐ"),
    ("さ", "す"),
    ("た", "つ"),
    ("な", "ぬ"),
    ("ば", "ぶ"),
    ("ま", "む"),
    ("ら", "る"),
)
GODAN_E = (
    ("え", "う"),
    ("け", "く"),
    ("げ", "ぐ"),
    ("せ", "す"),
    ("て", "つ"),
    ("ね", "ぬ"),
    ("べ", "ぶ"),
    ("め", "む"),
    ("れ", "る"),
)
GODAN_O = (
    ("お", "う"),
    ("こ", "く"),
    ("ご", "ぐ"),
    ("そ", "す"),
    ("と", "つ"),
    ("の", "ぬ"),
    ("ぼ", "ぶ"),
    ("も", "む"),
    ("ろ", "る"),
)
GODAN_TE = (
    ("って", "う"),
    ("って", "つ"),
    ("って", "る"),
    ("いて", "く"),
    ("いで", "ぐ"),
    ("して", "す"),
    ("んで", "ぬ"),
    ("んで", "ぶ"),
    ("んで", "む"),
)
GODAN_TA = (
    ("った", "う"),
    ("った", "つ"),
    ("った", "る"),
    ("いた", "く"),
    ("いだ", "ぐ"),
    ("した", "す"),
    ("んだ", "ぬ"),
    ("んだ", "ぶ"),
    ("んだ", "む"),
)


# This is a Python adaptation of Yomitan's condition-aware transform graph.
# Rules output intermediate conditions so transformations can be chained safely.
RULES: Tuple[DeinflectionRule, ...] = tuple(
    [
        rule("ている", "て", {"v1"}, {"-te"}, "progressive"),
        rule("でいる", "で", {"v1"}, {"-te"}, "progressive"),
        rule("てる", "て", {"v1"}, {"-te"}, "progressive (contracted)"),
        rule("でる", "で", {"v1"}, {"-te"}, "progressive (contracted)"),
        rule("ておく", "て", {"v5"}, {"-te"}, "in advance"),
        rule("でおく", "で", {"v5"}, {"-te"}, "in advance"),
        rule("とく", "て", {"v5"}, {"-te"}, "in advance (contracted)"),
        rule("どく", "で", {"v5"}, {"-te"}, "in advance (contracted)"),
        rule("てしまう", "て", {"v5"}, {"-te"}, "completion/regret"),
        rule("でしまう", "で", {"v5"}, {"-te"}, "completion/regret"),
        rule("ちゃう", "て", {"v5"}, {"-te"}, "completion/regret (contracted)"),
        rule("じゃう", "で", {"v5"}, {"-te"}, "completion/regret (contracted)"),
        rule("なかった", "ない", {"adj-i"}, {"adj-i"}, "past"),
        rule("なくて", "ない", {"adj-i"}, {"adj-i"}, "te-form"),
        rule("なければ", "ない", {"adj-i"}, {"adj-i"}, "conditional"),
        rule("なかった", "る", {"-ta"}, {"v1"}, "negative"),
        rule("ない", "る", {"adj-i"}, {"v1"}, "negative"),
        rule("ない", "くる", {"adj-i"}, {"vk"}, "negative"),
        rule("ない", "する", {"adj-i"}, {"vs"}, "negative"),
        rule("ませんでした", "る", {"-ta"}, {"v1"}, "polite negative past"),
        rule("ませんでした", "くる", {"-ta"}, {"vk"}, "polite negative past"),
        rule("ませんでした", "する", {"-ta"}, {"vs"}, "polite negative past"),
        rule("ません", "る", {"v1"}, {"v1"}, "polite negative"),
        rule("ません", "くる", {"vk"}, {"vk"}, "polite negative"),
        rule("ません", "する", {"vs"}, {"vs"}, "polite negative"),
        rule("ました", "る", {"-ta"}, {"v1"}, "polite past"),
        rule("ました", "くる", {"-ta"}, {"vk"}, "polite past"),
        rule("ました", "する", {"-ta"}, {"vs"}, "polite past"),
        rule("ます", "る", {"v1"}, {"v1"}, "polite"),
        rule("ます", "くる", {"vk"}, {"vk"}, "polite"),
        rule("ます", "する", {"vs"}, {"vs"}, "polite"),
        rule("た", "る", {"-ta"}, {"v1"}, "past"),
        rule("て", "る", {"-te"}, {"v1"}, "te-form"),
        rule("れば", "る", {"v1"}, {"v1"}, "conditional"),
        rule("ろ", "る", {"v1"}, {"v1"}, "imperative"),
        rule("よ", "る", {"v1"}, {"v1"}, "imperative"),
        rule("よう", "る", set(), {"v1"}, "volitional"),
        rule("られる", "る", {"v1"}, {"v1"}, "potential/passive"),
        rule("させる", "る", {"v1"}, {"v1"}, "causative"),
        rule("させられる", "る", {"v1"}, {"v1"}, "causative passive"),
        rule("たい", "る", {"adj-i"}, {"v1"}, "desiderative"),
        rule("すぎる", "る", {"v1"}, {"v1"}, "excessive"),
        rule("かった", "い", {"-ta"}, {"adj-i"}, "past"),
        rule("くて", "い", {"-te"}, {"adj-i"}, "te-form"),
        rule("ければ", "い", set(), {"adj-i"}, "conditional"),
        rule("くない", "い", {"adj-i"}, {"adj-i"}, "negative"),
        rule("すぎる", "い", {"v1"}, {"adj-i"}, "excessive"),
        rule("そう", "い", set(), {"adj-i"}, "appearance"),
        rule("かった", "", {"-ta"}, {"adj-i"}, "past"),
        rule("くて", "", {"-te"}, {"adj-i"}, "te-form"),
        rule("した", "する", {"-ta"}, {"vs"}, "past"),
        rule("して", "する", {"-te"}, {"vs"}, "te-form"),
        rule("すれば", "する", set(), {"vs"}, "conditional"),
        rule("しろ", "する", set(), {"vs"}, "imperative"),
        rule("せよ", "する", set(), {"vs"}, "imperative"),
        rule("しよう", "する", set(), {"vs"}, "volitional"),
        rule("される", "する", {"v1"}, {"vs"}, "passive"),
        rule("させる", "する", {"v1"}, {"vs"}, "causative"),
        rule("させられる", "する", {"v1"}, {"vs"}, "causative passive"),
        rule("したい", "する", {"adj-i"}, {"vs"}, "desiderative"),
        rule("できる", "する", {"v1"}, {"vs"}, "potential"),
        rule("きた", "くる", {"-ta"}, {"vk"}, "past"),
        rule("きて", "くる", {"-te"}, {"vk"}, "te-form"),
        rule("くれば", "くる", set(), {"vk"}, "conditional"),
        rule("こい", "くる", set(), {"vk"}, "imperative"),
        rule("こよう", "くる", set(), {"vk"}, "volitional"),
        rule("こられる", "くる", {"v1"}, {"vk"}, "potential/passive"),
        rule("こさせる", "くる", {"v1"}, {"vk"}, "causative"),
        rule("きたい", "くる", {"adj-i"}, {"vk"}, "desiderative"),
        rule("行った", "行く", {"-ta"}, {"v5"}, "past"),
        rule("行って", "行く", {"-te"}, {"v5"}, "te-form"),
    ]
    + godan_rules(GODAN_I, {"v5"}, "continuative")
    + godan_rules(tuple((a + "ます", b) for a, b in GODAN_I), {"v5"}, "polite")
    + godan_rules(tuple((a + "ました", b) for a, b in GODAN_I), {"-ta"}, "polite past")
    + godan_rules(tuple((a + "ません", b) for a, b in GODAN_I), {"v5"}, "polite negative")
    + godan_rules(tuple((a + "ませんでした", b) for a, b in GODAN_I), {"-ta"}, "polite negative past")
    + godan_rules(GODAN_TE, {"-te"}, "te-form")
    + godan_rules(GODAN_TA, {"-ta"}, "past")
    + godan_rules(tuple((a + "ない", b) for a, b in GODAN_A), {"adj-i"}, "negative")
    + godan_rules(tuple((a + "なかった", b) for a, b in GODAN_A), {"-ta"}, "negative past")
    + godan_rules(tuple((a + "れる", b) for a, b in GODAN_A), {"v1"}, "passive")
    + godan_rules(tuple((a + "せる", b) for a, b in GODAN_A), {"v1"}, "causative")
    + godan_rules(tuple((a + "せられる", b) for a, b in GODAN_A), {"v1"}, "causative passive")
    + godan_rules(tuple((a + "ば", b) for a, b in GODAN_E), set(), "conditional")
    + godan_rules(tuple((a + "る", b) for a, b in GODAN_E), {"v1"}, "potential")
    + godan_rules(tuple((a + "よう", b) for a, b in GODAN_O), set(), "volitional")
    + godan_rules(tuple((a + "たい", b) for a, b in GODAN_I), {"adj-i"}, "desiderative")
)


def deinflect(text: str, max_depth: int = 8) -> List[Deinflection]:
    results = [Deinflection(text, None, ())]
    seen = {(text, None)}

    for candidate in results:
        if len(candidate.reasons) >= max_depth:
            continue
        for transform in RULES:
            if candidate.conditions is not None and transform.conditions_in:
                if candidate.conditions.isdisjoint(transform.conditions_in):
                    continue
            if not candidate.term.endswith(transform.inflected_suffix):
                continue
            stem_length = len(candidate.term) - len(transform.inflected_suffix)
            transformed = candidate.term[:stem_length] + transform.dictionary_suffix
            if not transformed or transformed == candidate.term:
                continue
            state = (transformed, transform.conditions_out)
            if state in seen:
                continue
            seen.add(state)
            results.append(
                Deinflection(
                    term=transformed,
                    conditions=transform.conditions_out,
                    reasons=candidate.reasons + (transform.reason,),
                )
            )
    return results


def entry_matches_conditions(word_classes: Sequence[str], conditions: Optional[ConditionSet]) -> bool:
    if conditions is None or not conditions:
        return True

    entry_conditions = set()
    for word_class in word_classes:
        if word_class == "v1" or word_class.startswith("v1-"):
            entry_conditions.add("v1")
        elif word_class.startswith("v5"):
            entry_conditions.add("v5")
        elif word_class.startswith("vs"):
            entry_conditions.add("vs")
        elif word_class == "vk":
            entry_conditions.add("vk")
        elif word_class == "vz":
            entry_conditions.add("vz")
        elif word_class in {"adj-i", "adj-ix"}:
            entry_conditions.add("adj-i")

    return not conditions.isdisjoint(entry_conditions)
