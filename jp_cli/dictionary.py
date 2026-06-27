from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from .config import get_db_path
from .models import DictionaryEntry
from .text import is_kana_text


console = Console()


def import_jmdict(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Dictionary file not found: {path}")

    console.print(f"Loading [bold]{path}[/bold]...")
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    words = data.get("words")
    if not isinstance(words, list):
        raise SystemExit("Expected a JMdict JSON file with a top-level 'words' list.")

    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        create_dictionary_schema(connection)
        connection.execute("delete from search_terms")
        connection.execute("delete from entries")

        total = len(words)
        with console.status(f"Importing {total:,} entries..."):
            for index, word in enumerate(words, start=1):
                entry = jmdict_word_to_entry(word)
                if entry is None:
                    continue
                connection.execute(
                    """
                    insert into entries(entry_id, primary_spelling, readings, common, senses, word_classes)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.entry_id,
                        entry.primary_spelling,
                        json.dumps(entry.readings, ensure_ascii=False),
                        1 if entry.common else 0,
                        json.dumps(entry.senses, ensure_ascii=False),
                        json.dumps(entry.word_classes, ensure_ascii=False),
                    ),
                )
                for term in search_terms_for_word(word):
                    connection.execute(
                        "insert into search_terms(term, entry_id) values (?, ?)",
                        (term, entry.entry_id),
                    )
                if index % 5000 == 0:
                    connection.commit()
        connection.commit()
    finally:
        connection.close()

    console.print(f"Imported {total:,} JMdict entries into [bold]{db_path}[/bold].")


def create_dictionary_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists entries (
            entry_id text primary key,
            primary_spelling text not null,
            readings text not null,
            common integer not null,
            senses text not null,
            word_classes text not null default '[]'
        );

        create table if not exists search_terms (
            term text not null,
            entry_id text not null,
            foreign key(entry_id) references entries(entry_id)
        );

        create index if not exists idx_search_terms_term on search_terms(term);
        """
    )
    entry_columns = {
        row[1] for row in connection.execute("pragma table_info(entries)").fetchall()
    }
    if "word_classes" not in entry_columns:
        connection.execute(
            "alter table entries add column word_classes text not null default '[]'"
        )
    create_explanation_cache_schema(connection)


def create_explanation_cache_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists explanation_cache (
            sentence text not null,
            model text not null,
            explanation_json text not null,
            created_at text not null,
            primary key(sentence, model)
        );
        """
    )


def ensure_cache_schema() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        create_explanation_cache_schema(connection)
        connection.commit()
    finally:
        connection.close()


def jmdict_word_to_entry(word: dict) -> Optional[DictionaryEntry]:
    entry_id = str(word.get("id", "")).strip()
    if not entry_id:
        return None

    kanji = word.get("kanji", [])
    kana = word.get("kana", [])
    kanji_texts = [item.get("text", "") for item in kanji if item.get("text")]
    kana_texts = [item.get("text", "") for item in kana if item.get("text")]
    primary_spelling = kanji_texts[0] if kanji_texts else (kana_texts[0] if kana_texts else "")
    if not primary_spelling:
        return None

    common = any(item.get("common") for item in kanji) or any(item.get("common") for item in kana)
    senses = []
    word_classes = set()
    for index, sense in enumerate(word.get("sense", []), start=1):
        glosses = [
            gloss.get("text", "")
            for gloss in sense.get("gloss", [])
            if gloss.get("lang") == "eng" and gloss.get("text")
        ]
        if not glosses:
            continue
        pos = ", ".join(sense.get("partOfSpeech", []))
        word_classes.update(sense.get("partOfSpeech", []))
        label = f"{index}. "
        if pos:
            label += f"({pos}) "
        senses.append(label + "; ".join(glosses))

    return DictionaryEntry(
        entry_id=entry_id,
        primary_spelling=primary_spelling,
        readings=kana_texts,
        common=common,
        senses=senses,
        word_classes=sorted(word_classes),
    )


def search_terms_for_word(word: dict) -> List[str]:
    terms = []
    for section in ("kanji", "kana"):
        for item in word.get(section, []):
            text = item.get("text")
            if text:
                terms.append(text)
    return sorted(set(terms))


def lookup_dictionary(term: str, limit: int = 5) -> List[DictionaryEntry]:
    db_path = get_db_path()
    if not db_path.exists():
        return []

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            select e.entry_id, e.primary_spelling, e.readings, e.common, e.senses, e.word_classes
            from search_terms st
            join entries e on e.entry_id = st.entry_id
            where st.term = ?
            order by e.common desc, e.primary_spelling
            limit ?
            """,
            (term, limit * 8),
        ).fetchall()
    finally:
        connection.close()

    entries = [
        DictionaryEntry(
            entry_id=row[0],
            primary_spelling=row[1],
            readings=json.loads(row[2]),
            common=bool(row[3]),
            senses=json.loads(row[4]),
            word_classes=json.loads(row[5]),
        )
        for row in rows
    ]
    return rank_dictionary_entries(term, entries)[:limit]


def lookup_dictionary_terms(terms: List[str], limit_per_term: int = 3) -> dict:
    db_path = get_db_path()
    if not terms or not db_path.exists():
        return {}

    connection = sqlite3.connect(db_path)
    try:
        rows = []
        for offset in range(0, len(terms), 800):
            chunk = terms[offset : offset + 800]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                connection.execute(
                    f"""
                    select st.term, e.entry_id, e.primary_spelling, e.readings, e.common, e.senses, e.word_classes
                    from search_terms st
                    join entries e on e.entry_id = st.entry_id
                    where st.term in ({placeholders})
                    order by length(st.term) desc, e.common desc, e.primary_spelling
                    """,
                    chunk,
                ).fetchall()
            )
    finally:
        connection.close()

    results: dict = {}
    for row in rows:
        term = row[0]
        entries = results.setdefault(term, [])
        entries.append(
            DictionaryEntry(
                entry_id=row[1],
                primary_spelling=row[2],
                readings=json.loads(row[3]),
                common=bool(row[4]),
                senses=json.loads(row[5]),
                word_classes=json.loads(row[6]),
            )
        )
    return {
        term: rank_dictionary_entries(term, entries)[:limit_per_term]
        for term, entries in results.items()
    }


def rank_dictionary_entries(term: str, entries: List[DictionaryEntry]) -> List[DictionaryEntry]:
    return sorted(entries, key=lambda entry: dictionary_rank(term, entry), reverse=True)


def dictionary_rank(term: str, entry: DictionaryEntry) -> tuple:
    senses = " ".join(entry.senses)
    return (
        entry.primary_spelling == term,
        term in entry.readings,
        is_kana_text(term) and has_suru_verb_pos(senses),
        entry.common,
        not has_rare_marker(senses),
        -len(entry.primary_spelling),
    )


def has_suru_verb_pos(senses: str) -> bool:
    return "(vs" in senses


def has_rare_marker(senses: str) -> bool:
    return "rare" in senses or "arch" in senses or "obs" in senses


def format_dictionary_entries(entries: List[DictionaryEntry]) -> str:
    if not entries:
        return "No dictionary results found. Import JMdict first with:\npython -m jp_cli import-jmdict jmdict-eng-3.6.2.json"

    chunks = []
    for entry in entries:
        common = " common" if entry.common else ""
        readings = "、".join(entry.readings[:4])
        lines = [f"{entry.primary_spelling} 【{readings}】{common}"]
        lines.extend(entry.senses[:6])
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)
