"""Main GUI application window for the PTCG Art Scraper."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ptcg_art_scraper.gui.help_view import HelpPage
from ptcg_art_scraper.gui.library_view import LibraryPage
from ptcg_art_scraper.gui.new_job import NewJobPage
from ptcg_art_scraper.gui.queue_view import QueuePage
from ptcg_art_scraper.gui.settings_view import SettingsPage

if TYPE_CHECKING:
    from collections.abc import Sequence

_SIDEBAR_ITEMS: list[tuple[str, str]] = [
    ("📥", "New Job"),
    ("📋", "Queue & Progress"),
    ("📚", "Library"),
    ("⚙️", "Settings"),
    ("❓", "Help / About"),
]

_STYLE = """
QMainWindow {
    background-color: #f5f6fa;
}

#sidebar {
    background-color: #2c3e50;
    min-width: 200px;
    max-width: 200px;
}

#sidebar QPushButton {
    color: #ecf0f1;
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 12px 16px;
    font-size: 14px;
}

#sidebar QPushButton:hover {
    background-color: #34495e;
}

#sidebar QPushButton[active="true"] {
    background-color: #2980b9;
    font-weight: bold;
}

#page_stack {
    background-color: #ffffff;
    border-left: 1px solid #dcdde1;
}

QStatusBar {
    background-color: #2c3e50;
    color: #ecf0f1;
    font-size: 12px;
}
"""


class MainWindow(QMainWindow):
    """Primary application window with sidebar navigation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PTCG Art Scraper")
        self.resize(1100, 750)
        self.setStyleSheet(_STYLE)

        self._settings = QSettings("ptcg_art_scraper", "gui")
        self._nav_buttons: list[QPushButton] = []

        self._build_ui()
        self._restore_geometry()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QWidget(self)
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 8, 0, 8)
        sidebar_layout.setSpacing(0)

        for index, (icon, label) in enumerate(_SIDEBAR_ITEMS):
            btn = QPushButton(f"  {icon}  {label}")
            btn.setProperty("active", False)
            btn.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()
        root_layout.addWidget(sidebar)

        # --- Page stack ---
        self._stack = QStackedWidget(self)
        self._stack.setObjectName("page_stack")

        self._pages: list[QWidget] = [
            NewJobPage(self),
            QueuePage(self),
            LibraryPage(self),
            SettingsPage(self),
            HelpPage(self),
        ]
        for page in self._pages:
            self._stack.addWidget(page)

        root_layout.addWidget(self._stack, stretch=1)

        # --- Status bar ---
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)
        status_bar.showMessage("Ready")

        # Activate the first page by default
        self._switch_page(0)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _switch_page(self, index: int) -> None:
        """Activate the page at *index* and update sidebar highlights."""
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", i == index)
            # Force style refresh after dynamic property change
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)


def launch(argv: Sequence[str] | None = None) -> int:
    """Create the application, show the main window, and run the event loop."""
    app = QApplication(list(argv) if argv is not None else sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
