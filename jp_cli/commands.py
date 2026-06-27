from __future__ import annotations

import time
from typing import Optional

from .clipboard import read_clipboard
from .enrich import with_lookup_items, with_sentence_explanation
from .explain import explain_sentence, format_explanation
from .models import ClipboardEntry
from .rendering import console, render
from .terminal import (
    enable_single_keypress_input,
    hide_cursor,
    read_key_bytes,
    read_keypress,
    restore_terminal,
    show_cursor,
)
from .text import classify_text, contains_japanese, normalize_clipboard_text, tokenize_japanese


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
