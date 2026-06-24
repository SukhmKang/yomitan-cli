from __future__ import annotations

import unittest
from pathlib import Path

from jp_cli.cli import (
    ClipboardEntry,
    build_lookup_items,
    render_selected_source,
    set_db_path,
    tokenize_japanese,
)
from jp_cli.deinflect import deinflect, entry_matches_conditions


def setUpModule() -> None:
    # DB-dependent tests rely on the locally-built dictionary in the repo's
    # .jp_data/. Point at it explicitly so the suite is independent of the
    # current working directory.
    set_db_path(str(Path(__file__).resolve().parent.parent / ".jp_data" / "jp.sqlite3"))


class DeinflectionTests(unittest.TestCase):
    def assert_deinflects_to(self, source: str, expected: str) -> None:
        self.assertIn(expected, {candidate.term for candidate in deinflect(source)})

    def test_common_chained_conjugations(self) -> None:
        cases = [
            ("食べなかった", "食べる"),
            ("言われた", "言う"),
            ("読んでいる", "読む"),
            ("書きませんでした", "書く"),
            ("高くなかった", "高い"),
            ("勉強させられました", "勉強する"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assert_deinflects_to(source, expected)

    def test_word_class_validation(self) -> None:
        self.assertTrue(entry_matches_conditions(["v5m", "vt"], frozenset({"v5"})))
        self.assertFalse(entry_matches_conditions(["n"], frozenset({"v5"})))
        self.assertTrue(entry_matches_conditions(["adj-i"], frozenset({"adj-i"})))


class DictionaryScanningTests(unittest.TestCase):
    def test_sentence_uses_longest_grammar_valid_spans(self) -> None:
        items = build_lookup_items("先生に言われたことがまだ気になっている。")
        self.assertEqual(
            [item.term for item in items],
            ["先生", "に", "言われた", "こと", "が", "まだ", "気になっている"],
        )
        self.assertEqual(items[1].entries[0].word_classes, ["prt"])
        self.assertEqual(items[2].entries[0].primary_spelling, "言う")
        self.assertEqual(items[-1].entries[0].primary_spelling, "気になる")

    def test_suru_conjugation_attaches_to_verbal_noun(self) -> None:
        items = build_lookup_items("日本語を勉強させられました。")
        self.assertEqual(
            [item.term for item in items],
            ["日本語", "を", "勉強させられました"],
        )
        self.assertEqual(items[-1].entries[0].primary_spelling, "勉強")

    def test_tokenizer_lemma_ranks_deinflected_homophones(self) -> None:
        items = build_lookup_items("携帯みてしまいました。")
        self.assertEqual(
            [item.term for item in items],
            ["携帯", "みてしまいました"],
        )
        self.assertEqual(items[-1].entries[0].primary_spelling, "見る")

    def test_mixed_text_offsets_find_trailing_particle(self) -> None:
        text = "Adobe Stockで。"
        particle = [token for token in tokenize_japanese(text) if token.surface == "で"]
        self.assertEqual([(token.start, token.end) for token in particle], [(11, 12)])
        items = build_lookup_items(text)
        self.assertEqual([item.term for item in items], ["で"])
        self.assertIn("prt", items[0].entries[0].word_classes)

    def test_selected_lookup_is_highlighted_in_source_sentence(self) -> None:
        text = "先生に言われた。"
        items = build_lookup_items(text)
        entry = ClipboardEntry(
            text=text,
            kind="sentence",
            captured_at="00:00:00",
            tokens=[],
            lookup_items=items,
        )

        rendered = render_selected_source(entry, 1)

        self.assertEqual(rendered.plain, text)
        self.assertEqual(
            [(span.start, span.end, str(span.style)) for span in rendered.spans],
            [(2, 3, "bold reverse")],
        )


if __name__ == "__main__":
    unittest.main()
