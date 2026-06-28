from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-or-later
# Python port of Yomitan's LanguageTransformer (ext/js/language/language-transformer.js).
# Copyright (C) 2024-2026 Yomitan Authors.
#
# Consumes the descriptor emitted by scripts/generate_transforms.mjs (which is
# generated from Yomitan's japanese-transforms.js, the single source of truth).
# Conditions are tracked as 32-bit flag sets exactly as upstream does, so a
# deinflected candidate only matches dictionary entries of a compatible word
# class.

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class _Rule:
    type: str
    inflected: str
    deinflected: str
    conditions_in: int
    conditions_out: int


@dataclass(frozen=True)
class _Transform:
    id: str
    rules: Tuple[_Rule, ...]


@dataclass(frozen=True)
class TransformedText:
    text: str
    conditions: int
    trace: Tuple[str, ...] = field(default=())


class LanguageTransformer:
    def __init__(self) -> None:
        self._next_flag_index = 0
        self._transforms: List[_Transform] = []
        self._condition_type_to_flags: Dict[str, int] = {}
        self._part_of_speech_to_flags: Dict[str, int] = {}

    def add_descriptor(self, descriptor: dict) -> None:
        conditions = descriptor["conditions"]
        transforms = descriptor["transforms"]
        condition_entries = list(conditions.items())
        flags_map, next_flag_index = self._build_condition_flags_map(
            condition_entries, self._next_flag_index
        )

        for transform in transforms:
            rules: List[_Rule] = []
            for index, raw in enumerate(transform["rules"]):
                conditions_in = self._flags_strict(flags_map, raw["conditionsIn"])
                if conditions_in is None:
                    raise ValueError(
                        f"Invalid conditionsIn for transform {transform['id']}.rules[{index}]"
                    )
                conditions_out = self._flags_strict(flags_map, raw["conditionsOut"])
                if conditions_out is None:
                    raise ValueError(
                        f"Invalid conditionsOut for transform {transform['id']}.rules[{index}]"
                    )
                rules.append(
                    _Rule(
                        type=raw["type"],
                        inflected=raw["inflected"],
                        deinflected=raw["deinflected"],
                        conditions_in=conditions_in,
                        conditions_out=conditions_out,
                    )
                )
            self._transforms.append(_Transform(id=transform["id"], rules=tuple(rules)))

        self._next_flag_index = next_flag_index
        for condition_type, condition in condition_entries:
            flags = flags_map.get(condition_type)
            if flags is None:
                continue
            self._condition_type_to_flags[condition_type] = flags
            if condition.get("isDictionaryForm"):
                self._part_of_speech_to_flags[condition_type] = flags

    def get_condition_flags_from_parts_of_speech(self, parts_of_speech: Sequence[str]) -> int:
        return self._flags(self._part_of_speech_to_flags, parts_of_speech)

    def get_condition_flags_from_condition_types(self, condition_types: Sequence[str]) -> int:
        return self._flags(self._condition_type_to_flags, condition_types)

    def get_condition_flags_from_condition_type(self, condition_type: str) -> int:
        return self._flags(self._condition_type_to_flags, [condition_type])

    def transform(self, source_text: str) -> List[TransformedText]:
        results = [TransformedText(source_text, 0, ())]
        seen = {(source_text, 0)}
        i = 0
        while i < len(results):
            current = results[i]
            i += 1
            for transform in self._transforms:
                for rule in transform.rules:
                    if not self.conditions_match(current.conditions, rule.conditions_in):
                        continue
                    deinflected = self._apply(rule, current.text)
                    if deinflected is None:
                        continue
                    state = (deinflected, rule.conditions_out)
                    if state in seen:
                        continue
                    seen.add(state)
                    results.append(
                        TransformedText(
                            deinflected,
                            rule.conditions_out,
                            current.trace + (transform.id,),
                        )
                    )
        return results

    @staticmethod
    def conditions_match(current_conditions: int, next_conditions: int) -> bool:
        return current_conditions == 0 or (current_conditions & next_conditions) != 0

    @staticmethod
    def _apply(rule: _Rule, text: str) -> Optional[str]:
        if rule.type == "suffix":
            if text.endswith(rule.inflected) and len(text) > len(rule.inflected) - 1:
                stem = text[: len(text) - len(rule.inflected)]
                transformed = stem + rule.deinflected
                return transformed if transformed and transformed != text else None
        elif rule.type == "wholeWord":
            if text == rule.inflected:
                return rule.deinflected if rule.deinflected != text else None
        return None

    def _build_condition_flags_map(
        self, condition_entries, next_flag_index: int
    ) -> Tuple[Dict[str, int], int]:
        flags_map: Dict[str, int] = {}
        targets = list(condition_entries)
        while targets:
            next_targets = []
            for condition_type, condition in targets:
                sub_conditions = condition.get("subConditions")
                if not sub_conditions:
                    if next_flag_index >= 32:
                        raise ValueError("Maximum number of conditions was exceeded")
                    flags = 1 << next_flag_index
                    next_flag_index += 1
                else:
                    multi = self._flags_strict(flags_map, sub_conditions)
                    if multi is None:
                        next_targets.append((condition_type, condition))
                        continue
                    flags = multi
                flags_map[condition_type] = flags
            if len(next_targets) == len(targets):
                raise ValueError("Cycle in subCondition declaration")
            targets = next_targets
        return flags_map, next_flag_index

    @staticmethod
    def _flags_strict(flags_map: Dict[str, int], condition_types: Sequence[str]) -> Optional[int]:
        flags = 0
        for condition_type in condition_types:
            value = flags_map.get(condition_type)
            if value is None:
                return None
            flags |= value
        return flags

    @staticmethod
    def _flags(flags_map: Dict[str, int], condition_types: Sequence[str]) -> int:
        flags = 0
        for condition_type in condition_types:
            flags |= flags_map.get(condition_type, 0)
        return flags
