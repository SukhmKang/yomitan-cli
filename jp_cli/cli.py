from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from .clipboard import command_exists, read_clipboard, read_clipboard_with_command
from .commands import debug_keys, explain_text, inspect_text, show_text, watch_clipboard
from .config import (
    DEFAULT_DB_PATH,
    DEFAULT_ENV_PATH,
    DEFAULT_LLM_MODEL,
    POLL_INTERVAL_SECONDS,
    configure_standard_streams,
    get_db_path,
    load_environment,
    set_db_path,
)
from .dictionary import (
    create_dictionary_schema,
    create_explanation_cache_schema,
    dictionary_rank,
    ensure_cache_schema,
    format_dictionary_entries,
    has_rare_marker,
    has_suru_verb_pos,
    import_jmdict,
    jmdict_word_to_entry,
    lookup_dictionary,
    lookup_dictionary_terms,
    rank_dictionary_entries,
    search_terms_for_word,
)
from .enrich import with_lookup_items, with_sentence_explanation
from .explain import (
    build_explanation_prompt,
    explain_sentence,
    explanation_from_json,
    explanation_schema,
    explanation_to_json,
    format_explanation,
    get_cached_explanation,
    get_openai_client,
    parse_explanation,
    save_cached_explanation,
)
from .lookup import (
    build_lookup_items,
    dictionary_matches_for_deinflections,
    dictionary_pos_affinity,
    dictionary_terms_for_candidate,
    is_lookup_boundary,
    is_useful_lookup_entry,
    japanese_prefixes,
    lookup_longest_span,
    lookup_particle,
)
from .models import (
    ClipboardEntry,
    DictionaryEntry,
    GrammarPoint,
    LookupItem,
    SentenceExplanation,
    Token,
)
from .rendering import (
    first_sense,
    format_lookup_matches,
    render,
    render_current_entry,
    render_explanation_panel,
    render_lookup_detail,
    render_lookup_table,
    render_selected_source,
)
from .terminal import (
    enable_single_keypress_input,
    hide_cursor,
    read_key_bytes,
    read_keypress,
    read_windows_key_bytes,
    restore_terminal,
    show_cursor,
)
from .text import (
    classify_text,
    contains_japanese,
    count_japanese_runs,
    feature_value,
    has_particle_like_char,
    is_japanese_char,
    is_kana_char,
    is_kana_text,
    kata_to_hira,
    normalize_clipboard_text,
    token_note,
    tokenize_japanese,
)


__all__ = [
    "ClipboardEntry",
    "DEFAULT_DB_PATH",
    "DEFAULT_ENV_PATH",
    "DEFAULT_LLM_MODEL",
    "DictionaryEntry",
    "GrammarPoint",
    "LookupItem",
    "POLL_INTERVAL_SECONDS",
    "SentenceExplanation",
    "Token",
    "build_explanation_prompt",
    "build_lookup_items",
    "classify_text",
    "command_exists",
    "configure_standard_streams",
    "contains_japanese",
    "count_japanese_runs",
    "create_dictionary_schema",
    "create_explanation_cache_schema",
    "debug_keys",
    "dictionary_matches_for_deinflections",
    "dictionary_pos_affinity",
    "dictionary_rank",
    "dictionary_terms_for_candidate",
    "enable_single_keypress_input",
    "ensure_cache_schema",
    "explain_sentence",
    "explain_text",
    "explanation_from_json",
    "explanation_schema",
    "explanation_to_json",
    "feature_value",
    "first_sense",
    "format_dictionary_entries",
    "format_explanation",
    "format_lookup_matches",
    "get_cached_explanation",
    "get_db_path",
    "get_openai_client",
    "has_particle_like_char",
    "has_rare_marker",
    "has_suru_verb_pos",
    "hide_cursor",
    "import_jmdict",
    "inspect_text",
    "is_japanese_char",
    "is_kana_char",
    "is_kana_text",
    "is_lookup_boundary",
    "is_useful_lookup_entry",
    "japanese_prefixes",
    "jmdict_word_to_entry",
    "kata_to_hira",
    "load_environment",
    "lookup_dictionary",
    "lookup_dictionary_terms",
    "lookup_longest_span",
    "lookup_particle",
    "main",
    "normalize_clipboard_text",
    "parse_explanation",
    "rank_dictionary_entries",
    "read_clipboard",
    "read_clipboard_with_command",
    "read_key_bytes",
    "read_keypress",
    "read_windows_key_bytes",
    "render",
    "render_current_entry",
    "render_explanation_panel",
    "render_lookup_detail",
    "render_lookup_table",
    "render_selected_source",
    "restore_terminal",
    "save_cached_explanation",
    "search_terms_for_word",
    "set_db_path",
    "show_cursor",
    "show_text",
    "token_note",
    "tokenize_japanese",
    "watch_clipboard",
    "with_lookup_items",
    "with_sentence_explanation",
]


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
