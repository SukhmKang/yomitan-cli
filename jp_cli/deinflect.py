from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-or-later
# Deinflection adapter. The transform rules and traversal engine are Yomitan's:
# the rule data lives in japanese_transforms.json (generated from Yomitan's
# japanese-transforms.js) and is driven by LanguageTransformer, a port of
# Yomitan's engine. This module is a thin shim exposing the same functions
# lookup.py already consumes, so the lookup pipeline is unchanged while the
# linguistics come straight from Yomitan.

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet, List, Optional, Sequence, Tuple, Union

from .language_transformer import LanguageTransformer

_DESCRIPTOR_PATH = Path(__file__).with_name("japanese_transforms.json")

# Condition value carried by a candidate: an int flag set from the transformer,
# or (for backwards compatibility with call sites that name conditions directly,
# e.g. the suru-verb noun stem) a set of Yomitan condition-type names.
ConditionSpec = Union[int, FrozenSet[str], None]


@dataclass(frozen=True)
class Deinflection:
    term: str
    conditions: ConditionSpec
    reasons: Tuple[str, ...]


@lru_cache(maxsize=1)
def _transformer() -> LanguageTransformer:
    descriptor = json.loads(_DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    transformer = LanguageTransformer()
    transformer.add_descriptor(descriptor)
    return transformer


def _jmdict_pos_to_condition(word_class: str) -> Optional[str]:
    """Map a JMdict part-of-speech code onto the Yomitan condition name the
    transform graph reasons about. Yomitan's own dictionaries store these names
    directly; JMdict uses finer codes (v5r, vs-i, adj-ix...), so collapse them."""
    if word_class == "v1" or word_class.startswith("v1-"):
        return "v1"
    if word_class.startswith("v5"):
        return "v5"
    if word_class.startswith("vs"):
        return "vs"
    if word_class == "vk":
        return "vk"
    if word_class == "vz":
        return "vz"
    if word_class in {"adj-i", "adj-ix"}:
        return "adj-i"
    return None


def deinflect(text: str) -> List[Deinflection]:
    """Every dictionary-form candidate reachable from ``text`` by undoing
    inflections. Each candidate's ``conditions`` is a Yomitan condition-flag
    bitset (0 = the uninflected source form, which matches any entry)."""
    return [
        Deinflection(term=result.text, conditions=result.conditions, reasons=result.trace)
        for result in _transformer().transform(text)
    ]


def _condition_flags(conditions: ConditionSpec) -> int:
    if conditions is None:
        return 0
    if isinstance(conditions, int):
        return conditions
    # An iterable of Yomitan condition-type names.
    return _transformer().get_condition_flags_from_condition_types(list(conditions))


def entry_matches_conditions(
    word_classes: Sequence[str], conditions: ConditionSpec
) -> bool:
    """True when a dictionary entry's word classes satisfy a candidate's
    inflection conditions. ``conditions`` may be a flag bitset (from
    :func:`deinflect`) or a set of condition-type names. A 0/empty/None
    condition always passes."""
    flags = _condition_flags(conditions)
    if flags == 0:
        return True
    condition_names = [
        name
        for name in (_jmdict_pos_to_condition(word_class) for word_class in word_classes)
        if name is not None
    ]
    entry_flags = _transformer().get_condition_flags_from_condition_types(condition_names)
    return LanguageTransformer.conditions_match(flags, entry_flags)
