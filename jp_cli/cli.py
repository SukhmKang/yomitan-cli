from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

from fugashi import Tagger
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .deinflect import Deinflection, deinflect, entry_matches_conditions


POLL_INTERVAL_SECONDS = 0.5
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_DB_PATH = Path.home() / ".jp_data" / "jp.sqlite3"
DEFAULT_ENV_PATH = Path.home() / ".jp_data" / ".env"


def _resolve_db_path(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("JP_DB_PATH")
    if env:
        return Path(env).expanduser()
    return DEFAULT_DB_PATH


_db_path: Path = _resolve_db_path()


def get_db_path() -> Path:
    return _db_path


def set_db_path(override: Optional[str] = None) -> None:
    global _db_path
    _db_path = _resolve_db_path(override)


def load_environment() -> None:
    load_dotenv(DEFAULT_ENV_PATH)
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

console = Console()
tagger: Optional[Tagger] = None
openai_client: Optional[OpenAI] = None


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


def main(argv: Optional[List[str]] = None) -> None:
    configure_standard_streams()
    load_environment()

    parser = argparse.ArgumentParser(
        prog="jp",
        description="Japanese study helper for the terminal.",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path to the SQLite dictionary DB. Overrides $JP_DB_PATH. "
            "Default: ~/.jp_data/jp.sqlite3"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    watch_parser = subparsers.add_parser(
        "watch",
        parents=[common],
        help="Watch the system clipboard for copied Japanese text.",
    )
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=POLL_INTERVAL_SECONDS,
        help=f"Clipboard polling interval in seconds. Default: {POLL_INTERVAL_SECONDS}",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        parents=[common],
        help="Show how text would be detected and classified.",
    )
    inspect_parser.add_argument("text", help="Text to inspect.")

    import_parser = subparsers.add_parser(
        "import-jmdict",
        parents=[common],
        help="Import a JMdict JSON file into the local SQLite dictionary.",
    )
    import_parser.add_argument("path", help="Path to jmdict-eng JSON.")

    lookup_parser = subparsers.add_parser(
        "lookup",
        parents=[common],
        help="Look up a word in the imported local dictionary.",
    )
    lookup_parser.add_argument("term", help="Japanese term to look up.")
    lookup_parser.add_argument("--limit", type=int, default=5, help="Maximum entries to show.")

    explain_parser = subparsers.add_parser(
        "explain",
        parents=[common],
        help="Generate an N2-friendly explanation for a Japanese sentence.",
    )
    explain_parser.add_argument("text", help="Sentence to explain.")

    show_parser = subparsers.add_parser(
        "show",
        parents=[common],
        help="Open the word pager for a specific Japanese text.",
    )
    show_parser.add_argument("text", help="Text to show in the pager.")

    subparsers.add_parser(
        "debug-keys",
        parents=[common],
        help="Print raw terminal key bytes for debugging arrow keys.",
    )
    subparsers.add_parser(
        "desktop",
        parents=[common],
        help="Open the persistent clipboard-driven desktop companion.",
    )

    args = parser.parse_args(argv)
    set_db_path(args.db_path)

    if args.command == "watch":
        watch_clipboard(args.interval)
    elif args.command == "inspect":
        inspect_text(args.text)
    elif args.command == "import-jmdict":
        import_jmdict(Path(args.path))
    elif args.command == "lookup":
        print(format_dictionary_entries(lookup_dictionary(args.term, limit=args.limit)))
    elif args.command == "explain":
        explain_text(args.text)
    elif args.command == "show":
        show_text(args.text)
    elif args.command == "debug-keys":
        debug_keys()
    elif args.command == "desktop":
        from .desktop import main as desktop_main

        desktop_main()


def configure_standard_streams() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def inspect_text(text: str) -> None:
    normalized = normalize_clipboard_text(text)
    print(f"text: {normalized}")
    print(f"contains Japanese: {contains_japanese(normalized)}")
    if contains_japanese(normalized):
        print(f"kind: {classify_text(normalized)}")
        print()
        for index, token in enumerate(tokenize_japanese(normalized), start=1):
            print(
                f"{index:>2}. {token.surface}\t"
                f"lemma={token.lemma}\treading={token.reading}\tpos={token.part_of_speech}"
            )


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
        return f"No dictionary results found. Import JMdict first with:\npython -m jp_cli import-jmdict jmdict-eng-3.6.2.json"

    chunks = []
    for entry in entries:
        common = " common" if entry.common else ""
        readings = "、".join(entry.readings[:4])
        lines = [f"{entry.primary_spelling} 【{readings}】{common}"]
        lines.extend(entry.senses[:6])
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def explain_text(text: str) -> None:
    normalized = normalize_clipboard_text(text)
    if not contains_japanese(normalized):
        raise SystemExit("No Japanese text found.")
    print(format_explanation(explain_sentence(normalized)))


def show_text(text: str) -> None:
    normalized = normalize_clipboard_text(text)
    if not contains_japanese(normalized):
        raise SystemExit("No Japanese text found.")

    entry = ClipboardEntry(
        text=normalized,
        kind=classify_text(normalized),
        captured_at=time.strftime("%H:%M:%S"),
        tokens=tokenize_japanese(normalized),
        lookup_items=[],
    )
    entry = with_lookup_items(entry)
    original_terminal_settings = enable_single_keypress_input()
    selected_token_index = 0
    detail_view = "word"

    hide_cursor()
    try:
        render(entry, status="Showing provided text.", selected_token_index=selected_token_index, detail_view=detail_view)
        if entry.kind == "sentence":
            entry = with_sentence_explanation(entry)
            render(entry, status="Generated sentence explanation.", selected_token_index=selected_token_index, detail_view=detail_view)
        while True:
            key = read_keypress()
            if key == "quit":
                break
            if key == "toggle" and entry.kind == "sentence":
                detail_view = "explanation" if detail_view == "word" else "word"
                render(entry, status=f"Showing {detail_view}.", selected_token_index=selected_token_index, detail_view=detail_view)
            if key == "left" and detail_view == "word":
                selected_token_index = max(0, selected_token_index - 1)
                render(entry, status="Moved to previous lookup.", selected_token_index=selected_token_index, detail_view=detail_view)
            elif key == "right" and detail_view == "word":
                selected_token_index = min(len(entry.lookup_items) - 1, selected_token_index + 1)
                render(entry, status="Moved to next lookup.", selected_token_index=selected_token_index, detail_view=detail_view)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        restore_terminal(original_terminal_settings)
        show_cursor()
        console.clear()
        print("jp show stopped.")


def debug_keys() -> None:
    original_terminal_settings = enable_single_keypress_input()
    print("Press keys to inspect them. Press q to quit.")
    try:
        while True:
            data = read_key_bytes()
            if not data:
                time.sleep(0.05)
                continue
            print(f"bytes={list(data)!r} repr={data!r}")
            if data == b"q":
                break
    except KeyboardInterrupt:
        pass
    finally:
        restore_terminal(original_terminal_settings)


def watch_clipboard(interval: float) -> None:
    original_terminal_settings = enable_single_keypress_input()
    last_seen: Optional[str] = None
    current: Optional[ClipboardEntry] = None
    selected_token_index = 0
    detail_view = "word"

    hide_cursor()
    try:
        render(current, status="Waiting for Japanese text on the clipboard...")
        while True:
            key = read_keypress()
            if key == "quit":
                break
            if current is not None and current.tokens:
                if key == "toggle" and current.kind == "sentence":
                    detail_view = "explanation" if detail_view == "word" else "word"
                    render(current, status=f"Showing {detail_view}.", selected_token_index=selected_token_index, detail_view=detail_view)
                if key == "left" and detail_view == "word":
                    selected_token_index = max(0, selected_token_index - 1)
                    render(current, status="Moved to previous lookup.", selected_token_index=selected_token_index, detail_view=detail_view)
                elif key == "right" and detail_view == "word":
                    selected_token_index = min(len(current.lookup_items) - 1, selected_token_index + 1)
                    render(current, status="Moved to next lookup.", selected_token_index=selected_token_index, detail_view=detail_view)

            text = normalize_clipboard_text(read_clipboard())
            if text and text != last_seen:
                last_seen = text
                if contains_japanese(text):
                    selected_token_index = 0
                    detail_view = "word"
                    current = ClipboardEntry(
                        text=text,
                        kind=classify_text(text),
                        captured_at=time.strftime("%H:%M:%S"),
                        tokens=tokenize_japanese(text),
                        lookup_items=[],
                    )
                    current = with_lookup_items(current)
                    render(current, status="Copied Japanese text detected.", selected_token_index=selected_token_index, detail_view=detail_view)
                    if current.kind == "sentence":
                        current = with_sentence_explanation(current)
                        render(current, status="Generated sentence explanation.", selected_token_index=selected_token_index, detail_view=detail_view)
                else:
                    render(current, status="Clipboard changed, but no Japanese text was found.", selected_token_index=selected_token_index, detail_view=detail_view)

            time.sleep(max(interval, 0.1))
    except KeyboardInterrupt:
        pass
    finally:
        restore_terminal(original_terminal_settings)
        show_cursor()
        console.clear()
        print("jp watch stopped.")


def read_clipboard() -> str:
    if sys.platform == "darwin":
        return read_clipboard_with_command(["pbpaste"])
    if os.name == "nt":
        return read_clipboard_with_command(
            ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"]
        )

    if command_exists("wl-paste"):
        return read_clipboard_with_command(["wl-paste", "--no-newline"])
    if command_exists("xclip"):
        return read_clipboard_with_command(["xclip", "-selection", "clipboard", "-out"])
    if command_exists("xsel"):
        return read_clipboard_with_command(["xsel", "--clipboard", "--output"])
    return ""


def read_clipboard_with_command(command: List[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1,
        )
    except subprocess.SubprocessError:
        return ""

    if completed.returncode != 0:
        return ""
    return completed.stdout or ""


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


def explain_sentence(sentence: str) -> SentenceExplanation:
    model = os.environ.get("JP_LLM_MODEL", DEFAULT_LLM_MODEL)
    cached = get_cached_explanation(sentence, model)
    if cached is not None:
        return cached

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return SentenceExplanation(
            meaning="",
            yasashiku="",
            grammar_points=[],
            nuance="",
            raw=(
                "OPENAI_API_KEY is not configured.\n\n"
                "Create a .env file with:\n"
                "OPENAI_API_KEY=your_api_key_here\n"
                f"JP_LLM_MODEL={DEFAULT_LLM_MODEL}"
            ),
        )

    prompt = build_explanation_prompt(sentence)

    try:
        response = get_openai_client().responses.create(
            model=model,
            input=prompt,
            temperature=0.4,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "japanese_sentence_explanation",
                    "description": "N2-friendly explanation of a Japanese sentence.",
                    "strict": True,
                    "schema": explanation_schema(),
                },
                "verbosity": "medium",
            },
        )
    except OpenAIError as error:
        return SentenceExplanation(
            meaning="",
            yasashiku="",
            grammar_points=[],
            nuance="",
            raw=f"Could not generate explanation with {model}:\n{error}",
        )

    output_text = getattr(response, "output_text", "")
    explanation = parse_explanation(output_text.strip())
    if explanation.raw is None:
        save_cached_explanation(sentence, model, explanation)
    return explanation


def get_cached_explanation(sentence: str, model: str) -> Optional[SentenceExplanation]:
    if not get_db_path().exists():
        return None

    ensure_cache_schema()
    connection = sqlite3.connect(get_db_path())
    try:
        row = connection.execute(
            """
            select explanation_json
            from explanation_cache
            where sentence = ? and model = ?
            """,
            (sentence, model),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None
    return explanation_from_json(row[0])


def save_cached_explanation(sentence: str, model: str, explanation: SentenceExplanation) -> None:
    ensure_cache_schema()
    connection = sqlite3.connect(get_db_path())
    try:
        connection.execute(
            """
            insert or replace into explanation_cache(sentence, model, explanation_json, created_at)
            values (?, ?, ?, ?)
            """,
            (
                sentence,
                model,
                explanation_to_json(explanation),
                time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def explanation_to_json(explanation: SentenceExplanation) -> str:
    return json.dumps(
        {
            "meaning": explanation.meaning,
            "yasashiku": explanation.yasashiku,
            "grammar_points": [
                {"title": point.title, "explanation": point.explanation}
                for point in explanation.grammar_points
            ],
            "nuance": explanation.nuance,
        },
        ensure_ascii=False,
    )


def explanation_from_json(payload: str) -> SentenceExplanation:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return SentenceExplanation("", "", [], "", raw=payload)

    return SentenceExplanation(
        meaning=str(data.get("meaning", "")).strip(),
        yasashiku=str(data.get("yasashiku", "")).strip(),
        grammar_points=[
            GrammarPoint(
                title=str(point.get("title", "")).strip(),
                explanation=str(point.get("explanation", "")).strip(),
            )
            for point in data.get("grammar_points", [])
            if isinstance(point, dict)
        ],
        nuance=str(data.get("nuance", "")).strip(),
    )


def explanation_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "meaning": {
                "type": "string",
                "description": "A natural English translation of the sentence.",
            },
            "yasashiku": {
                "type": "string",
                "description": "Simple Japanese explanation suitable for a JLPT N2 learner.",
            },
            "grammar_points": {
                "type": "array",
                "description": "Important grammar points in the sentence.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["title", "explanation"],
                },
            },
            "nuance": {
                "type": "string",
                "description": "Useful nuance, implication, or naturalness note.",
            },
        },
        "required": ["meaning", "yasashiku", "grammar_points", "nuance"],
    }


def parse_explanation(output_text: str) -> SentenceExplanation:
    if not output_text:
        return SentenceExplanation("", "", [], "", raw="The model returned an empty explanation.")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return SentenceExplanation("", "", [], "", raw=output_text)

    grammar_points = [
        GrammarPoint(
            title=str(item.get("title", "")).strip(),
            explanation=str(item.get("explanation", "")).strip(),
        )
        for item in payload.get("grammar_points", [])
        if isinstance(item, dict)
    ]

    return SentenceExplanation(
        meaning=str(payload.get("meaning", "")).strip(),
        yasashiku=str(payload.get("yasashiku", "")).strip(),
        grammar_points=grammar_points,
        nuance=str(payload.get("nuance", "")).strip(),
    )


def format_explanation(explanation: SentenceExplanation) -> str:
    if explanation.raw:
        return explanation.raw

    lines = [
        "意味:",
        explanation.meaning,
        "",
        "やさしく説明:",
        explanation.yasashiku,
        "",
        "文法ポイント:",
    ]
    for point in explanation.grammar_points:
        lines.append(f"- {point.title}")
        lines.append(f"  {point.explanation}")
    lines.extend(["", "ニュアンス:", explanation.nuance])
    return "\n".join(lines).strip()


def get_openai_client() -> OpenAI:
    global openai_client
    if openai_client is None:
        openai_client = OpenAI()
    return openai_client


def build_explanation_prompt(sentence: str) -> str:
    return f"""
You are helping an intermediate Japanese learner around JLPT N2 level.

Explain this sentence:
{sentence}

Return only the requested structured data.

Keep each field compact and readable in a terminal.
""".strip()


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


def render(
    current: Optional[ClipboardEntry],
    status: str,
    selected_token_index: int = 0,
    detail_view: str = "word",
) -> None:
    console.clear()
    console.print(
        Panel(
            Group(
                Text(status, style="bold cyan"),
                Text("Copy Japanese to the clipboard. Use ←/→ to page dictionary matches. Tab toggles detail. Press q to quit.", style="dim"),
            ),
            title="jp watch",
            box=box.ROUNDED,
        )
    )

    if current is None:
        console.print(Panel("Waiting for Japanese text on the clipboard.", title="Current", box=box.ROUNDED))
    else:
        console.print(render_current_entry(current, selected_token_index, detail_view))

    sys.stdout.flush()


def render_current_entry(entry: ClipboardEntry, selected_token_index: int, detail_view: str) -> Panel:
    if entry.kind == "sentence":
        if detail_view == "explanation":
            body = Group(
                Text(entry.text),
                render_explanation_panel(entry.explanation),
            )
        else:
            body = Group(
                render_selected_source(entry, selected_token_index),
                render_lookup_table(entry.lookup_items, selected_token_index),
                render_lookup_detail(entry.lookup_items, selected_token_index),
            )
    else:
        body = Group(
            render_selected_source(entry, selected_token_index),
            render_lookup_detail(entry.lookup_items, selected_token_index),
        )

    return Panel(body, title=f"Current {entry.kind} · {entry.captured_at}", box=box.ROUNDED)


def render_selected_source(entry: ClipboardEntry, selected_index: int) -> Text:
    text = Text(entry.text)
    if not entry.lookup_items:
        return text

    index = min(max(selected_index, 0), len(entry.lookup_items) - 1)
    item = entry.lookup_items[index]
    text.stylize("bold reverse", item.start, item.end)
    return text


def render_explanation_panel(explanation: Optional[SentenceExplanation]) -> Panel:
    if explanation is None:
        return Panel("Generating explanation...", title="やさしく説明", box=box.ROUNDED)
    if explanation.raw:
        return Panel(explanation.raw, title="やさしく説明", box=box.ROUNDED)

    grammar = "\n".join(
        f"- {point.title}\n  {point.explanation}" for point in explanation.grammar_points
    )
    body = "\n\n".join(
        [
            f"意味:\n{explanation.meaning}",
            f"やさしく説明:\n{explanation.yasashiku}",
            f"文法ポイント:\n{grammar}",
            f"ニュアンス:\n{explanation.nuance}",
        ]
    )
    return Panel(body, title="やさしく説明", box=box.ROUNDED)


def render_lookup_table(items: List[LookupItem], selected_index: int) -> Table:
    table = Table(title="Dictionary Matches", box=box.SIMPLE, expand=True, show_lines=False)
    table.add_column("#", justify="right", width=4)
    table.add_column("Term")
    table.add_column("Reading")
    table.add_column("Meaning")

    if not items:
        table.add_row("-", "No dictionary matches found", "", "")
        return table

    for index, item in enumerate(items):
        style = "bold reverse" if index == selected_index else ""
        entry = item.entries[0] if item.entries else None
        table.add_row(
            str(index + 1),
            item.term,
            "、".join(entry.readings[:2]) if entry else "",
            first_sense(entry) if entry else "",
            style=style,
        )
    return table


def render_lookup_detail(items: List[LookupItem], selected_index: int) -> Panel:
    if not items:
        body = "No dictionary result found."
    else:
        index = min(max(selected_index, 0), len(items) - 1)
        item = items[index]
        body = format_lookup_matches([(item.term, item.entries)])
    return Panel(body, title="Dictionary", box=box.ROUNDED)


def format_lookup_matches(matches: List[tuple]) -> str:
    chunks = []
    for term, entries in matches[:4]:
        chunks.append(f"match: {term}\n{format_dictionary_entries(entries)}")
    return "\n\n".join(chunks)


def first_sense(entry: Optional[DictionaryEntry]) -> str:
    if entry is None or not entry.senses:
        return ""
    sense = entry.senses[0]
    if ") " in sense:
        return sense.split(") ", 1)[1]
    if ". " in sense:
        return sense.split(". ", 1)[1]
    return sense


def command_exists(command: str) -> bool:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    return any(os.path.exists(os.path.join(path, command)) for path in paths)


def hide_cursor() -> None:
    print("\033[?25l", end="")


def show_cursor() -> None:
    print("\033[?25h", end="")


def enable_single_keypress_input() -> Optional[Any]:
    if not sys.stdin.isatty():
        return None
    if os.name == "nt":
        return None

    settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin)
    return settings


def restore_terminal(settings: Optional[Any]) -> None:
    if settings is not None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)


def read_keypress() -> Optional[str]:
    if not sys.stdin.isatty():
        return None

    data = read_key_bytes()
    if not data:
        return None
    if data.lower() == b"q":
        return "quit"
    if data == b"\t":
        return "toggle"
    if data in {b"\x1b[D", b"\x1bOD"}:
        return "left"
    if data in {b"\x1b[C", b"\x1bOC"}:
        return "right"
    return None


def read_key_bytes() -> bytes:
    if not sys.stdin.isatty():
        return b""
    if os.name == "nt":
        return read_windows_key_bytes()

    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if not readable:
        return b""

    data = os.read(sys.stdin.fileno(), 32)
    if data != b"\x1b":
        return data

    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        timeout = max(0, deadline - time.monotonic())
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if not readable:
            break
        data += os.read(sys.stdin.fileno(), 32)
        if data in {b"\x1b[C", b"\x1b[D", b"\x1bOC", b"\x1bOD"}:
            break
    return data


def read_windows_key_bytes() -> bytes:
    if not msvcrt.kbhit():
        return b""

    data = msvcrt.getwch()
    if data in {"\x00", "\xe0"} and msvcrt.kbhit():
        code = msvcrt.getwch()
        if code == "K":
            return b"\x1b[D"
        if code == "M":
            return b"\x1b[C"
        return code.encode(errors="ignore")
    return data.encode(errors="ignore")
