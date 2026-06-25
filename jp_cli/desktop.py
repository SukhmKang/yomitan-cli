from __future__ import annotations

import sys
import time
from typing import List, Optional

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .cli import (
    ClipboardEntry,
    DictionaryEntry,
    LookupItem,
    SentenceExplanation,
    build_lookup_items,
    classify_text,
    contains_japanese,
    explain_sentence,
    load_environment,
    normalize_clipboard_text,
    tokenize_japanese,
)


APP_STYLESHEET = """
QWidget {
    background: #151719;
    color: #e7e7e4;
    font-family: "Avenir Next", "Hiragino Sans", sans-serif;
    font-size: 14px;
}
QMainWindow {
    background: #151719;
}
QLabel#eyebrow {
    color: #8c9794;
    font-size: 11px;
    font-weight: 700;
}
QLabel#status {
    color: #a6b2ae;
    font-size: 12px;
}
QTextEdit#source {
    background: #1b1e20;
    border: 1px solid #33383a;
    border-radius: 6px;
    padding: 13px;
    selection-background-color: #d6a94e;
    selection-color: #171717;
    font-family: "Hiragino Sans", sans-serif;
    font-size: 20px;
}
QListWidget {
    background: #181b1d;
    border: 1px solid #33383a;
    border-radius: 6px;
    outline: 0;
    padding: 4px;
}
QListWidget::item {
    border-bottom: 1px solid #292d2f;
    padding: 9px 10px;
}
QListWidget::item:selected {
    background: #d6a94e;
    color: #171717;
}
QTextBrowser {
    background: #181b1d;
    border: 1px solid #33383a;
    border-radius: 6px;
    padding: 14px;
    selection-background-color: #d6a94e;
    selection-color: #171717;
}
QPushButton {
    background: transparent;
    border: 1px solid #3a4042;
    border-radius: 5px;
    padding: 7px 12px;
    color: #bfc5c2;
}
QPushButton:hover {
    border-color: #737c79;
}
QPushButton:checked {
    background: #e7e7e4;
    color: #171717;
    border-color: #e7e7e4;
}
QSplitter::handle {
    background: #2b2f31;
    width: 1px;
}
QScrollBar:vertical {
    background: #181b1d;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: #454b4d;
    border-radius: 4px;
    min-height: 28px;
}
"""


class ExplanationSignals(QObject):
    complete = pyqtSignal(str, object)


class ExplanationTask(QRunnable):
    def __init__(self, sentence: str) -> None:
        super().__init__()
        self.sentence = sentence
        self.signals = ExplanationSignals()

    def run(self) -> None:
        explanation = explain_sentence(self.sentence)
        self.signals.complete.emit(self.sentence, explanation)


class JapaneseDesktopWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.current: Optional[ClipboardEntry] = None
        self.selected_index = 0
        self.last_clipboard_text = ""
        self.thread_pool = QThreadPool.globalInstance()
        self.explanation_tasks: List[ExplanationTask] = []

        self.setWindowTitle("JP Companion")
        self.resize(760, 860)
        self.setMinimumSize(560, 620)
        self.setCentralWidget(self._build_ui())
        self._install_shortcuts()

        clipboard = app.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._show_waiting_state()
        self._process_clipboard_text(clipboard.text())

    def _build_ui(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.setSpacing(1)
        eyebrow = QLabel("JP COMPANION")
        eyebrow.setObjectName("eyebrow")
        self.status_label = QLabel("Watching clipboard")
        self.status_label.setObjectName("status")
        title_group.addWidget(eyebrow)
        title_group.addWidget(self.status_label)
        heading.addLayout(title_group)
        heading.addStretch()

        self.dictionary_button = QPushButton("Dictionary")
        self.dictionary_button.setCheckable(True)
        self.dictionary_button.setChecked(True)
        self.explanation_button = QPushButton("やさしく説明")
        self.explanation_button.setCheckable(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.dictionary_button, 0)
        mode_group.addButton(self.explanation_button, 1)
        self.mode_group = mode_group
        self.dictionary_button.clicked.connect(lambda: self.mode_stack.setCurrentIndex(0))
        self.explanation_button.clicked.connect(lambda: self.mode_stack.setCurrentIndex(1))
        heading.addWidget(self.dictionary_button)
        heading.addWidget(self.explanation_button)
        layout.addLayout(heading)

        self.source_view = QTextEdit()
        self.source_view.setObjectName("source")
        self.source_view.setReadOnly(True)
        self.source_view.setAcceptRichText(False)
        self.source_view.setMinimumHeight(82)
        self.source_view.setMaximumHeight(170)
        layout.addWidget(self.source_view)

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_dictionary_view())
        self.mode_stack.addWidget(self._build_explanation_view())
        layout.addWidget(self.mode_stack, 1)
        return root

    def _build_dictionary_view(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        self.match_list = QListWidget()
        self.match_list.setMinimumHeight(170)
        self.match_list.setWordWrap(True)
        self.match_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.match_list.currentRowChanged.connect(self._select_lookup)

        self.definition_view = QTextBrowser()
        self.definition_view.setOpenExternalLinks(False)
        self.definition_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.match_list)
        splitter.addWidget(self.definition_view)
        splitter.setSizes([240, 430])
        layout.addWidget(splitter)
        return pane

    def _build_explanation_view(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        self.explanation_view = QTextBrowser()
        layout.addWidget(self.explanation_view)
        return pane

    def _on_clipboard_changed(self) -> None:
        self._process_clipboard_text(self.app.clipboard().text())

    def _process_clipboard_text(self, raw_text: str) -> None:
        text = normalize_clipboard_text(raw_text)
        if not text or text == self.last_clipboard_text:
            return
        self.last_clipboard_text = text
        if not contains_japanese(text):
            self.status_label.setText("Clipboard changed · no Japanese detected")
            return

        tokens = tokenize_japanese(text)
        lookup_items = build_lookup_items(text, tokens)
        self.current = ClipboardEntry(
            text=text,
            kind=classify_text(text),
            captured_at=time.strftime("%H:%M:%S"),
            tokens=tokens,
            lookup_items=lookup_items,
        )
        self.selected_index = 0
        self._render_current()
        if self.current.kind == "sentence":
            self._start_explanation(text)
        else:
            self.explanation_view.setHtml(
                self._message_html("Copy a sentence to generate an explanation.")
            )

    def _render_current(self) -> None:
        if self.current is None:
            return
        self.status_label.setText(
            f"Updated {self.current.captured_at} · {len(self.current.lookup_items)} matches"
        )
        self.source_view.setPlainText(self.current.text)
        line_count = min(4, max(1, self.current.text.count("\n") + 1))
        self.source_view.setFixedHeight(58 + line_count * 30)
        self.match_list.blockSignals(True)
        self.match_list.clear()
        for item in self.current.lookup_items:
            entry = item.entries[0] if item.entries else None
            reading = "、".join(entry.readings[:2]) if entry else ""
            meaning = first_clean_sense(entry) if entry else ""
            row = QListWidgetItem(f"{item.term}    {reading}\n{meaning}")
            row.setData(Qt.ItemDataRole.UserRole, item)
            self.match_list.addItem(row)
        self.match_list.blockSignals(False)

        if self.current.lookup_items:
            self.match_list.setCurrentRow(0)
            self._select_lookup(0)
        else:
            self.definition_view.setHtml(self._message_html("No dictionary matches found."))
            self._highlight_selected_source()

    def _select_lookup(self, index: int) -> None:
        if self.current is None or not self.current.lookup_items:
            return
        self.selected_index = min(max(index, 0), len(self.current.lookup_items) - 1)
        item = self.current.lookup_items[self.selected_index]
        self.definition_view.setHtml(format_lookup_html(item))
        self._highlight_selected_source()

    def _highlight_selected_source(self) -> None:
        selections = []
        if self.current is not None and self.current.lookup_items:
            item = self.current.lookup_items[self.selected_index]
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor("#d6a94e"))
            selection.format.setForeground(QColor("#171717"))
            selection.format.setFontWeight(QFont.Weight.Bold)
            cursor = self.source_view.textCursor()
            cursor.setPosition(item.start)
            cursor.setPosition(item.end, QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            selections.append(selection)
        self.source_view.setExtraSelections(selections)

    def _start_explanation(self, sentence: str) -> None:
        self.explanation_view.setHtml(self._message_html("Generating explanation..."))
        task = ExplanationTask(sentence)
        task.signals.complete.connect(self._on_explanation_complete)
        self.explanation_tasks.append(task)
        self.thread_pool.start(task)

    def _on_explanation_complete(
        self,
        sentence: str,
        explanation: SentenceExplanation,
    ) -> None:
        self.explanation_tasks = [
            task for task in self.explanation_tasks if task.sentence != sentence
        ]
        if self.current is None or self.current.text != sentence:
            return
        self.explanation_view.setHtml(format_explanation_html(explanation))

    def _show_waiting_state(self) -> None:
        self.source_view.setPlaceholderText("Copy Japanese text to begin.")
        self.definition_view.setHtml(self._message_html("Watching the clipboard."))
        self.explanation_view.setHtml(
            self._message_html("Sentence explanations will appear here.")
        )

    @staticmethod
    def _message_html(message: str) -> str:
        return f'<p style="color:#9aa39f">{escape_html(message)}</p>'

    def _install_shortcuts(self) -> None:
        for key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda: self._move_selection(-1))
        for key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda: self._move_selection(1))
        toggle = QShortcut(QKeySequence(Qt.Key.Key_Tab), self)
        toggle.activated.connect(self._toggle_mode)

    def _move_selection(self, delta: int) -> None:
        if (
            self.mode_stack.currentIndex() != 0
            or self.current is None
            or not self.current.lookup_items
        ):
            return
        maximum = len(self.current.lookup_items) - 1
        self.match_list.setCurrentRow(
            min(maximum, max(0, self.selected_index + delta))
        )

    def _toggle_mode(self) -> None:
        if self.current is None:
            return
        next_index = 1 - self.mode_stack.currentIndex()
        self.mode_stack.setCurrentIndex(next_index)
        self.dictionary_button.setChecked(next_index == 0)
        self.explanation_button.setChecked(next_index == 1)


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def clean_sense(sense: str) -> str:
    if ") " in sense:
        return sense.split(") ", 1)[1]
    if ". " in sense:
        return sense.split(". ", 1)[1]
    return sense


def first_clean_sense(entry: Optional[DictionaryEntry]) -> str:
    if entry is None or not entry.senses:
        return ""
    return clean_sense(entry.senses[0])


def format_lookup_html(item: LookupItem) -> str:
    chunks = []
    for entry in item.entries:
        readings = "、".join(entry.readings[:4])
        common = " · common" if entry.common else ""
        senses = "".join(
            f"<li style='margin-bottom:7px'>{escape_html(clean_sense(sense))}</li>"
            for sense in entry.senses[:6]
        )
        chunks.append(
            f'<section style="margin-bottom:20px">'
            f'<div style="font-size:18px;font-weight:700">'
            f"{escape_html(entry.primary_spelling)}</div>"
            f'<div style="color:#aab2af;margin:2px 0 8px">'
            f"{escape_html(readings)}{common}</div>"
            f'<ol style="margin-top:0;padding-left:24px">{senses}</ol>'
            f"</section>"
        )
    return "".join(chunks)


def format_explanation_html(explanation: SentenceExplanation) -> str:
    if explanation.raw:
        return f"<p>{escape_html(explanation.raw).replace(chr(10), '<br>')}</p>"

    grammar = "".join(
        f'<section style="margin-bottom:14px">'
        f'<div style="font-weight:700">{escape_html(point.title)}</div>'
        f'<div>{escape_html(point.explanation).replace(chr(10), "<br>")}</div>'
        f"</section>"
        for point in explanation.grammar_points
    )
    return (
        explanation_section("意味", explanation.meaning)
        + explanation_section("やさしく説明", explanation.yasashiku)
        + f'<div style="color:#8c9794;font-size:11px;font-weight:700;'
        f'margin:18px 0 9px">文法ポイント</div>{grammar}'
        + explanation_section("ニュアンス", explanation.nuance)
    )


def explanation_section(title: str, body: str) -> str:
    return (
        f'<div style="color:#8c9794;font-size:11px;font-weight:700;'
        f'margin:4px 0 7px">{escape_html(title)}</div>'
        f'<div style="line-height:1.55;margin-bottom:18px">'
        f'{escape_html(body).replace(chr(10), "<br>")}</div>'
    )


def main() -> None:
    load_environment()
    app = QApplication(sys.argv)
    app.setApplicationName("JP Companion")
    app.setStyleSheet(APP_STYLESHEET)
    window = JapaneseDesktopWindow(app)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
