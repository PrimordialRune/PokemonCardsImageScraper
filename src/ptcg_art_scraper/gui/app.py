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
    background-color: #e8eef5;
    color: #12263a;
}

QWidget {
    color: #12263a;
    font-size: 13px;
}

#sidebar {
    background-color: #162131;
    min-width: 220px;
    max-width: 220px;
}

#sidebar QPushButton {
    color: #dbe8f8;
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: 600;
}

#sidebar QPushButton:hover {
    background-color: #223449;
}

#sidebar QPushButton[active="true"] {
    background-color: #2f80ed;
    font-weight: bold;
}

#page_stack {
    background-color: #f3f6fa;
    border-left: 1px solid #c8d3df;
}

#page_stack QWidget {
    color: #12263a;
}

#page_stack QGroupBox {
    border: 1px solid #ced7e2;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    background-color: #fbfdff;
}

#page_stack QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #1f3650;
    font-weight: 600;
}

#page_stack QLineEdit,
#page_stack QPlainTextEdit,
#page_stack QComboBox,
#page_stack QSpinBox,
#page_stack QDoubleSpinBox,
#page_stack QTextBrowser,
#page_stack QTableWidget,
#page_stack QTreeWidget {
    background-color: #ffffff;
    color: #102030;
    border: 1px solid #c3cfdb;
    border-radius: 6px;
    selection-background-color: #b8d8ff;
    selection-color: #0f2338;
}

#page_stack QLineEdit,
#page_stack QComboBox,
#page_stack QSpinBox,
#page_stack QDoubleSpinBox {
    min-height: 30px;
    padding: 2px 8px;
}

#page_stack QPlainTextEdit,
#page_stack QTextBrowser {
    padding: 6px 8px;
}

#page_stack QLineEdit:focus,
#page_stack QPlainTextEdit:focus,
#page_stack QComboBox:focus,
#page_stack QSpinBox:focus,
#page_stack QDoubleSpinBox:focus,
#page_stack QTextBrowser:focus,
#page_stack QTableWidget:focus,
#page_stack QTreeWidget:focus {
    border: 1px solid #4f91e8;
}

#page_stack QTabWidget::pane {
    border: 1px solid #ccd7e3;
    border-radius: 8px;
    top: -1px;
    background-color: #ffffff;
}

#page_stack QTabBar::tab {
    background-color: #e3ebf4;
    color: #2e4258;
    border: 1px solid #ccd7e3;
    border-bottom: none;
    padding: 7px 12px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

#page_stack QTabBar::tab:selected {
    background-color: #ffffff;
    color: #102030;
}

#page_stack QPushButton {
    background-color: #e2e9f1;
    color: #102030;
    border: 1px solid #c4cfdb;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}

#page_stack QPushButton:hover {
    background-color: #d7e1ec;
}

#page_stack QPushButton:pressed {
    background-color: #cbd7e4;
}

#page_stack QPushButton:disabled {
    background-color: #edf2f7;
    color: #7d8c9c;
    border-color: #d7dee6;
}

#page_stack QPushButton[role="primary"] {
    background-color: #2f80ed;
    border-color: #266ecb;
    color: #f7fbff;
}

#page_stack QPushButton[role="primary"]:hover {
    background-color: #3c8ef8;
}

#page_stack QPushButton[role="primary"]:pressed {
    background-color: #2a76d8;
}

#page_stack QHeaderView::section {
    background-color: #dee8f2;
    color: #1d3248;
    border: 1px solid #c4d0dd;
    padding: 6px;
    font-weight: 600;
}

#page_stack QTableWidget {
    gridline-color: #d4dde7;
    alternate-background-color: #f7fafd;
}

#page_stack QTreeWidget {
    alternate-background-color: #f7fafd;
}

#page_stack QProgressBar {
    border: 1px solid #c3cfdb;
    border-radius: 6px;
    background-color: #edf2f8;
    color: #1d3248;
    text-align: center;
}

#page_stack QProgressBar::chunk {
    background-color: #2f80ed;
    border-radius: 5px;
}

QStatusBar {
    background-color: #162131;
    color: #dbe8f8;
    font-size: 12px;
}

QStatusBar::item {
    border: none;
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
            btn.clicked.connect(lambda _checked=False, i=index: self._switch_page(i))
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

        # Connect New Job → Queue
        new_job_page: NewJobPage = self._pages[0]  # type: ignore[assignment]
        queue_page: QueuePage = self._pages[1]  # type: ignore[assignment]
        new_job_page.job_requested.connect(
            lambda config, items: self._start_job(queue_page, config, items)
        )

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

    def _start_job(
        self, queue_page: QueuePage, config: object, items: list[object]
    ) -> None:
        """Switch to Queue page and begin the scrape job."""
        self._switch_page(1)
        queue_page.set_queue(items, config)  # type: ignore[arg-type]

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
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return int(app.exec())
