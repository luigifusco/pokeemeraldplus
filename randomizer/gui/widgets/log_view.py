"""ANSI-aware log panel used by the Build & Run tab.

Replaces the Tk ScrolledText panel from the old GUI with a
``QPlainTextEdit``-based widget that:

  * is read-only and uses a monospace font
  * parses a useful subset of ANSI escape sequences (colors 30-37,
    90-97, bright/bold, reset, and the common bright-fg 3-byte
    forms) into Qt character formats
  * auto-follows the tail unless the user scrolls away from the
    bottom; scrolling back to the bottom re-enables auto-follow
  * exposes ``append_line`` (one stripped line at a time, matches
    the CommandRunner.line signal) and ``append_chunk`` (raw text
    for status messages written by the GUI itself)
  * has a toolbar with Copy All, Save to file, Clear, and a Follow
    tail toggle.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QPlainTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


# Subset of SGR codes sufficient for make/gcc/python output. Mapped
# to QColor rather than palette lookup so they render the same
# regardless of system theme.
_ANSI_FG_COLORS: dict[int, QColor] = {
    30: QColor("#404040"),  # black (nudged up so it's visible on dark bg)
    31: QColor("#d14a5a"),
    32: QColor("#58a65c"),
    33: QColor("#c7a65a"),
    34: QColor("#5a88d1"),
    35: QColor("#b062c4"),
    36: QColor("#4aa4b0"),
    37: QColor("#c8c8c8"),
    90: QColor("#6a6a6a"),
    91: QColor("#ff6680"),
    92: QColor("#7ed38a"),
    93: QColor("#f2d57b"),
    94: QColor("#8fb6f0"),
    95: QColor("#d48ce6"),
    96: QColor("#7fd3dc"),
    97: QColor("#ffffff"),
}

_ANSI_RE = re.compile(r"\x1b\[([\d;]*)m")


class LogView(QWidget):
    """Read-only log panel with ANSI coloring and tail auto-follow."""

    cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toolbar = QToolBar(self)
        self._toolbar.setMovable(False)

        copy_act = QAction("Copy", self)
        copy_act.setShortcut(QKeySequence.Copy)
        copy_act.triggered.connect(self._copy_all)
        self._toolbar.addAction(copy_act)

        save_act = QAction("Save…", self)
        save_act.triggered.connect(self._save_to_file)
        self._toolbar.addAction(save_act)

        clear_act = QAction("Clear", self)
        clear_act.triggered.connect(self.clear)
        self._toolbar.addAction(clear_act)

        self._toolbar.addSeparator()

        self._follow_act = QAction("Follow tail", self)
        self._follow_act.setCheckable(True)
        self._follow_act.setChecked(True)
        self._follow_act.toggled.connect(self._on_follow_toggled)
        self._toolbar.addAction(self._follow_act)

        layout.addWidget(self._toolbar)

        self._edit = QPlainTextEdit(self)
        self._edit.setReadOnly(True)
        self._edit.setUndoRedoEnabled(False)
        self._edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._edit.setMaximumBlockCount(20000)  # hard cap on memory
        self._edit.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        layout.addWidget(self._edit, 1)

        self._follow_tail = True
        scroll = self._edit.verticalScrollBar()
        scroll.valueChanged.connect(self._on_scroll_changed)

        self._default_fmt = QTextCharFormat()
        self._default_fmt.setForeground(self._edit.palette().text())

    # ----- public API -----

    def append_line(self, text: str) -> None:
        """Append a single line of subprocess output."""
        self._append(text + "\n")

    def append_chunk(self, text: str) -> None:
        """Append a status/info message produced by the GUI itself.

        Unlike ``append_line``, ``text`` may contain internal newlines
        but is not auto-newline-terminated.
        """
        self._append(text)

    def info(self, message: str) -> None:
        """Append an italicized GUI-side status message."""
        self._append_formatted(f"[info] {message}\n", self._make_fmt(QColor("#6a8fd6")))

    def warn(self, message: str) -> None:
        self._append_formatted(f"[warn] {message}\n", self._make_fmt(QColor("#c7a65a")))

    def error(self, message: str) -> None:
        self._append_formatted(f"[error] {message}\n", self._make_fmt(QColor("#d14a5a")))

    def success(self, message: str) -> None:
        self._append_formatted(f"[success] {message}\n", self._make_fmt(QColor("#58a65c")))

    def clear(self) -> None:
        self._edit.clear()
        self.cleared.emit()

    def text(self) -> str:
        return self._edit.toPlainText()

    # ----- internals -----

    def _append(self, text: str) -> None:
        self._render_ansi(text)
        if self._follow_tail:
            self._scroll_to_end()

    def _render_ansi(self, text: str) -> None:
        fmt = QTextCharFormat(self._default_fmt)
        pos = 0
        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        for m in _ANSI_RE.finditer(text):
            if m.start() > pos:
                cursor.insertText(text[pos : m.start()], fmt)
            codes = m.group(1)
            fmt = self._update_fmt(fmt, codes)
            pos = m.end()
        if pos < len(text):
            cursor.insertText(text[pos:], fmt)

    def _update_fmt(self, fmt: QTextCharFormat, codes: str) -> QTextCharFormat:
        out = QTextCharFormat(fmt)
        if not codes:
            return QTextCharFormat(self._default_fmt)
        for raw in codes.split(";"):
            if raw == "" or raw == "0":
                out = QTextCharFormat(self._default_fmt)
                continue
            try:
                c = int(raw)
            except ValueError:
                continue
            if c == 1:
                f = out.font()
                f.setBold(True)
                out.setFont(f)
            elif c == 22:
                f = out.font()
                f.setBold(False)
                out.setFont(f)
            elif c in _ANSI_FG_COLORS:
                out.setForeground(_ANSI_FG_COLORS[c])
            elif c == 39:
                out.setForeground(self._default_fmt.foreground())
        return out

    def _append_formatted(self, text: str, fmt: QTextCharFormat) -> None:
        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text, fmt)
        if self._follow_tail:
            self._scroll_to_end()

    def _make_fmt(self, color: QColor) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        return fmt

    def _scroll_to_end(self) -> None:
        bar = self._edit.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_scroll_changed(self, value: int) -> None:
        bar = self._edit.verticalScrollBar()
        at_bottom = value >= bar.maximum() - 2
        # Reflect user-driven scroll into the toolbar toggle without
        # firing the toggled signal (which would re-scroll).
        if at_bottom != self._follow_tail:
            self._follow_tail = at_bottom
            block = self._follow_act.blockSignals(True)
            self._follow_act.setChecked(at_bottom)
            self._follow_act.blockSignals(block)

    def _on_follow_toggled(self, checked: bool) -> None:
        self._follow_tail = checked
        if checked:
            self._scroll_to_end()

    def _copy_all(self) -> None:
        self._edit.selectAll()
        self._edit.copy()
        # Deselect so the user isn't left with a huge selection.
        cur = self._edit.textCursor()
        cur.clearSelection()
        self._edit.setTextCursor(cur)

    def _save_to_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save log", "build.log", "Text files (*.log *.txt);;All files (*)"
        )
        if not path:
            return
        Path(path).write_text(self._edit.toPlainText(), encoding="utf-8")
