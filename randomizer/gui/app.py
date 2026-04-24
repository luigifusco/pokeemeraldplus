"""QApplication + MainWindow scaffold.

Subsequent phases add tabs under ``randomizer/gui/tabs/`` and wire
them into :class:`MainWindow` here.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _require_pyside() -> None:
    try:
        import PySide6  # noqa: F401
    except ImportError as exc:  # pragma: no cover - import guard
        sys.stderr.write(
            "PySide6 is required for the randomizer GUI.\n"
            "Install it with:\n\n"
            "    pip install -r randomizer/requirements.txt\n\n"
            f"(original error: {exc})\n"
        )
        raise SystemExit(2) from exc


def run(argv: list[str] | None = None) -> int:
    _require_pyside()

    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QStatusBar,
        QTabWidget,
    )

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("pokeemeraldplus-randomizer")
    app.setOrganizationName("pokeemeraldplus")
    app.setStyle("Fusion")

    window = QMainWindow()
    window.setWindowTitle("pokeemeraldplus — Randomizer & Build")
    window.resize(980, 720)

    tabs = QTabWidget(window)
    tabs.setDocumentMode(True)
    window.setCentralWidget(tabs)

    # Tabs are wired up in later phases. Right now the window opens
    # empty so the scaffold is visibly end-to-end runnable.
    _install_placeholder_tabs(tabs)

    status = QStatusBar(window)
    status.showMessage("Ready")
    window.setStatusBar(status)

    window.show()
    return app.exec()


def _install_placeholder_tabs(tabs) -> None:
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    for name in ("Randomizer", "Evolutions", "Gameplay", "Speed & Skips", "Build & Run"):
        w = QWidget()
        layout = QVBoxLayout(w)
        lbl = QLabel(f"{name} — coming soon")
        lbl.setStyleSheet("color: #888; font-style: italic; padding: 24px;")
        layout.addWidget(lbl)
        layout.addStretch(1)
        tabs.addTab(w, name)
    tabs.setCurrentIndex(tabs.count() - 1)
