from __future__ import annotations

import sys
from typing import List, Optional

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .dictionary import format_dictionary_entries
from .models import ClipboardEntry, DictionaryEntry, LookupItem, SentenceExplanation


console = Console()


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
