from __future__ import annotations

import sys
import time
from typing import List, Optional

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QTimer,
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
    read_clipboard,
    tokenize_japanese,
)

CLIPBOARD_POLL_INTERVAL_MS = 500


APP_STYLESHEET = """
QWidget {
    background: #fbfbfa;
    color: #25282b;
    font-family: -apple-system, "Hiragino Sans", sans-serif;
    font-size: 13px;
}
QMainWindow {
    background: #fbfbfa;
}
QLabel#eyebrow {
    color: #737b83;
    font-size: 10px;
    font-weight: 600;
}
QLabel#status {
    color: #90979e;
    font-size: 11px;
}
QTextEdit#source {
    background: #ffffff;
    border: 1px solid #dfe2e5;
    border-radius: 4px;
    padding: 8px 10px;
    selection-background-color: #dbeafe;
    selection-color: #172033;
    font-family: "Hiragino Sans", sans-serif;
    font-size: 17px;
}
QListWidget {
    background: #ffffff;
    border: 1px solid #dfe2e5;
    border-radius: 4px;
    outline: 0;
    padding: 0;
}
QListWidget::item {
    border-bottom: 1px solid #eceef0;
    padding: 6px 9px;
}
QListWidget::item:selected {
    background: #edf4ff;
    color: #1f2937;
    border-left: 3px solid #4f7cac;
    padding-left: 6px;
}
QTextBrowser {
    background: #ffffff;
    border: 1px solid #dfe2e5;
    border-radius: 4px;
    padding: 10px 12px;
    selection-background-color: #dbeafe;
    selection-color: #172033;
}
QPushButton {
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 5px 8px 4px;
    color: #737b83;
    font-size: 12px;
}
QPushButton:hover {
    color: #25282b;
    background: #f2f3f4;
}
QPushButton:checked {
    color: #315f8f;
    border-bottom-color: #4f7cac;
    font-weight: 600;
}
QSplitter::handle {
    background: transparent;
    height: 5px;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c9ced3;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
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
        self.resize(620, 500)
        self.setMinimumSize(460, 380)
        self.setCentralWidget(self._build_ui())
        self._install_shortcuts()

        clipboard = app.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_changed)
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.setInterval(CLIPBOARD_POLL_INTERVAL_MS)
        self.clipboard_timer.timeout.connect(self._check_clipboard)
        self.clipboard_timer.start()
        self._show_waiting_state()
        self._check_clipboard()

    def _build_ui(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(9, 7, 9, 9)
        layout.setSpacing(5)

        heading = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.setSpacing(0)
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
        self.source_view.setMinimumHeight(46)
        self.source_view.setMaximumHeight(94)
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
        layout.setSpacing(3)

        self.match_list = QListWidget()
        self.match_list.setMinimumHeight(82)
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
        splitter.setSizes([125, 260])
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
        self._check_clipboard()

    def _check_clipboard(self) -> None:
        self._process_clipboard_text(read_clipboard())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.current is not None:
            self._resize_source_view()

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
        self._resize_source_view()
        self.match_list.blockSignals(True)
        self.match_list.clear()
        for item in self.current.lookup_items:
            entry = item.entries[0] if item.entries else None
            reading = "、".join(entry.readings[:2]) if entry else ""
            meaning = first_clean_sense(entry) if entry else ""
            row = QListWidgetItem(f"{item.term}  {reading}\n{meaning}")
            row.setData(Qt.ItemDataRole.UserRole, item)
            self.match_list.addItem(row)
        self.match_list.blockSignals(False)

        if self.current.lookup_items:
            self.match_list.setCurrentRow(0)
            self._select_lookup(0)
        else:
            self.definition_view.setHtml(self._message_html("No dictionary matches found."))
            self._highlight_selected_source()

    def _resize_source_view(self) -> None:
        if self.current is None:
            return
        document = self.source_view.document()
        text_width = max(120, self.source_view.viewport().width() - 4)
        document.setTextWidth(text_width)
        content_height = int(document.documentLayout().documentSize().height())
        self.source_view.setFixedHeight(min(180, max(48, content_height + 18)))

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
            selection.format.setBackground(QColor("#dbeafe"))
            selection.format.setForeground(QColor("#172033"))
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
        return f'<p style="color:#8b9299">{escape_html(message)}</p>'

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
        common = (
            '<span style="color:#4472a1;background:#edf4ff;'
            'font-size:10px;padding:1px 4px">common</span>'
            if entry.common
            else ""
        )
        senses = "".join(
            f"<li style='margin-bottom:4px'>{escape_html(clean_sense(sense))}</li>"
            for sense in entry.senses[:6]
        )
        chunks.append(
            f'<section style="margin-bottom:14px">'
            f'<div style="font-size:17px;font-weight:600;color:#202428">'
            f"{escape_html(entry.primary_spelling)}</div>"
            f'<div style="color:#7d858c;margin:1px 0 6px">'
            f"{escape_html(readings)}&nbsp;&nbsp;{common}</div>"
            f'<ol style="margin-top:0;padding-left:21px;line-height:1.35">{senses}</ol>'
            f"</section>"
        )
    return "".join(chunks)


def format_explanation_html(explanation: SentenceExplanation) -> str:
    if explanation.raw:
        return f"<p>{escape_html(explanation.raw).replace(chr(10), '<br>')}</p>"

    grammar = "".join(
        f'<section style="margin-bottom:11px">'
        f'<div style="font-weight:600;color:#30353a">{escape_html(point.title)}</div>'
        f'<div style="line-height:1.4">{escape_html(point.explanation).replace(chr(10), "<br>")}</div>'
        f"</section>"
        for point in explanation.grammar_points
    )
    return (
        explanation_section("意味", explanation.meaning)
        + explanation_section("やさしく説明", explanation.yasashiku)
        + f'<div style="color:#7d858c;font-size:10px;font-weight:600;'
        f'margin:14px 0 7px">文法ポイント</div>{grammar}'
        + explanation_section("ニュアンス", explanation.nuance)
    )


def explanation_section(title: str, body: str) -> str:
    return (
        f'<div style="color:#7d858c;font-size:10px;font-weight:600;'
        f'margin:3px 0 5px">{escape_html(title)}</div>'
        f'<div style="line-height:1.4;margin-bottom:13px">'
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
