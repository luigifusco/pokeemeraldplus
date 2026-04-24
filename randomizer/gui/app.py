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

    from PySide6.QtGui import QColor, QPalette
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
    _apply_theme(app)

    window = QMainWindow()
    window.setWindowTitle("pokeemeraldplus — Randomizer & Build")
    window.resize(1080, 760)

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


def _apply_theme(app) -> None:
    """Apply a dark palette + QSS stylesheet for a modern look."""
    from PySide6.QtGui import QColor, QPalette

    pal = QPalette()
    bg = QColor("#1e1f22")
    base = QColor("#17181a")
    alt = QColor("#26272b")
    text = QColor("#e6e6e6")
    dim = QColor("#9aa0a6")
    accent = QColor("#7a5cff")

    pal.setColor(QPalette.Window, bg)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, alt)
    pal.setColor(QPalette.ToolTipBase, bg)
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, QColor("#2d2f34"))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.BrightText, QColor("#ff5d5d"))
    pal.setColor(QPalette.Highlight, accent)
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.PlaceholderText, dim)
    pal.setColor(QPalette.Link, accent)
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#6a6c70"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6a6c70"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#6a6c70"))
    app.setPalette(pal)

    qss_path = Path(__file__).resolve().parent / "theme.qss"
    try:
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    except OSError:
        pass


def _install_placeholder_tabs(tabs) -> None:
    from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

    from .widgets.log_view import LogView
    from .backend.runner import CommandRunner

    for name in ("Randomizer", "Evolutions", "Gameplay", "Speed & Skips"):
        w = QWidget()
        layout = QVBoxLayout(w)
        lbl = QLabel(f"{name} — coming soon")
        lbl.setStyleSheet("color: #888; font-style: italic; padding: 24px;")
        layout.addWidget(lbl)
        layout.addStretch(1)
        tabs.addTab(w, name)

    # Build & Run tab gets an early preview of the LogView + runner
    # so phases 2-4 can be exercised before the full tab arrives.
    build_tab = QWidget()
    build_layout = QVBoxLayout(build_tab)

    log = LogView()
    runner = CommandRunner(build_tab)
    runner.started.connect(lambda argv: log.info("$ " + " ".join(argv)))
    runner.line.connect(log.append_line)
    runner.finished.connect(
        lambda code: (log.success if code == 0 else log.error)(f"exit {code}")
    )
    runner.failed.connect(log.error)

    demo_btn = QPushButton("Run demo: echo + small make dry-run")
    demo_btn.clicked.connect(
        lambda: runner.run(
            [
                "/bin/sh",
                "-c",
                "echo '\\033[32mgreen demo line\\033[0m'; echo plain; sleep 0.2; echo done",
            ]
        )
    )
    build_layout.addWidget(demo_btn)
    build_layout.addWidget(log, 1)

    # Keep references alive on the window.
    build_tab._runner = runner  # noqa: SLF001
    build_tab._log = log  # noqa: SLF001

    tabs.addTab(build_tab, "Build & Run")
    tabs.setCurrentIndex(tabs.count() - 1)
