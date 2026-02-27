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
    ("\u2728", "New Job"),
    ("\u23F3", "Queue & Progress"),
    ("\U0001F4DA", "Library"),
    ("\u2699", "Settings"),
    ("\u2753", "Help / About"),
]

_THEME_PALETTES = {
    "light": {
        "window_bg": "#e8eef5",
        "text_primary": "#12263a",
        "sidebar_bg": "#162131",
        "sidebar_fg": "#dbe8f8",
        "sidebar_hover": "#223449",
        "sidebar_active": "#2f80ed",
        "page_bg": "#f3f6fa",
        "page_border": "#c8d3df",
        "card_bg": "#fbfdff",
        "card_border": "#ced7e2",
        "group_title_fg": "#1f3650",
        "input_bg": "#ffffff",
        "input_fg": "#102030",
        "input_border": "#c3cfdb",
        "input_focus": "#4f91e8",
        "selection_bg": "#b8d8ff",
        "selection_fg": "#0f2338",
        "tab_bg": "#e3ebf4",
        "tab_fg": "#2e4258",
        "button_bg": "#e2e9f1",
        "button_fg": "#102030",
        "button_border": "#c4cfdb",
        "button_hover": "#d7e1ec",
        "button_pressed": "#cbd7e4",
        "button_disabled_bg": "#edf2f7",
        "button_disabled_fg": "#7d8c9c",
        "button_disabled_border": "#d7dee6",
        "primary_btn_bg": "#2f80ed",
        "primary_btn_border": "#266ecb",
        "primary_btn_fg": "#f7fbff",
        "primary_btn_hover": "#3c8ef8",
        "primary_btn_pressed": "#2a76d8",
        "header_bg": "#dee8f2",
        "header_fg": "#1d3248",
        "header_border": "#c4d0dd",
        "grid_color": "#d4dde7",
        "alt_bg": "#f7fafd",
        "progress_bg": "#edf2f8",
        "status_bg": "#162131",
        "status_fg": "#dbe8f8",
        "muted_fg": "#6b7c8f",
        "link_fg": "#2f80ed",
        "tooltip_bg": "#253547",
        "tooltip_fg": "#eaf2ff",
    },
    "dark": {
        "window_bg": "#0f1622",
        "text_primary": "#e6edf6",
        "sidebar_bg": "#0a111a",
        "sidebar_fg": "#d6e1ee",
        "sidebar_hover": "#182537",
        "sidebar_active": "#3b87f0",
        "page_bg": "#131d2a",
        "page_border": "#2b3a4c",
        "card_bg": "#172334",
        "card_border": "#2d3c4f",
        "group_title_fg": "#d8e4f4",
        "input_bg": "#0f1824",
        "input_fg": "#e6edf6",
        "input_border": "#3a4d63",
        "input_focus": "#5ea2ff",
        "selection_bg": "#2d5e92",
        "selection_fg": "#f4f8ff",
        "tab_bg": "#1f3045",
        "tab_fg": "#c9d8ea",
        "button_bg": "#213043",
        "button_fg": "#dde8f6",
        "button_border": "#3a4d63",
        "button_hover": "#2a3b50",
        "button_pressed": "#1c2a3b",
        "button_disabled_bg": "#1a2533",
        "button_disabled_fg": "#75879b",
        "button_disabled_border": "#2d3e52",
        "primary_btn_bg": "#3b87f0",
        "primary_btn_border": "#2d73d4",
        "primary_btn_fg": "#f4f9ff",
        "primary_btn_hover": "#4c96fb",
        "primary_btn_pressed": "#357de1",
        "header_bg": "#223246",
        "header_fg": "#d9e6f6",
        "header_border": "#34485f",
        "grid_color": "#2b3c50",
        "alt_bg": "#162334",
        "progress_bg": "#1f2d3d",
        "status_bg": "#0a111a",
        "status_fg": "#d6e1ee",
        "muted_fg": "#8fa2b6",
        "link_fg": "#66acff",
        "tooltip_bg": "#233548",
        "tooltip_fg": "#f4f8ff",
    },
}

_STYLE_TEMPLATE = """
QMainWindow {{
    background-color: {window_bg};
    color: {text_primary};
}}

QWidget {{
    color: {text_primary};
    font-size: 13px;
}}

QToolTip {{
    background-color: {tooltip_bg};
    color: {tooltip_fg};
    border: 1px solid {input_border};
    padding: 4px 6px;
}}

QLabel[muted="true"] {{
    color: {muted_fg};
    font-size: 11px;
}}

#sidebar {{
    background-color: {sidebar_bg};
    min-width: 220px;
    max-width: 220px;
}}

#sidebar QPushButton {{
    color: {sidebar_fg};
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: 600;
}}

#sidebar QPushButton:hover {{
    background-color: {sidebar_hover};
}}

#sidebar QPushButton[active="true"] {{
    background-color: {sidebar_active};
    font-weight: bold;
}}

#page_stack {{
    background-color: {page_bg};
    border-left: 1px solid {page_border};
}}

#page_stack QWidget {{
    color: {text_primary};
}}

#page_stack QScrollArea {{
    border: none;
    background-color: transparent;
}}

#page_stack QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

#page_stack QGroupBox {{
    border: 1px solid {card_border};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    background-color: {card_bg};
}}

#page_stack QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {group_title_fg};
    font-weight: 600;
}}

#page_stack QLineEdit,
#page_stack QPlainTextEdit,
#page_stack QComboBox,
#page_stack QSpinBox,
#page_stack QDoubleSpinBox,
#page_stack QTextBrowser,
#page_stack QTableWidget,
#page_stack QTreeWidget {{
    background-color: {input_bg};
    color: {input_fg};
    border: 1px solid {input_border};
    border-radius: 6px;
    selection-background-color: {selection_bg};
    selection-color: {selection_fg};
}}

#page_stack QComboBox QLineEdit {{
    background-color: transparent;
    color: {input_fg};
}}

#page_stack QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid {input_border};
    background-color: {button_bg};
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
}}

#page_stack QComboBox::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {input_fg};
}}

QComboBox QAbstractItemView,
QListView,
QTreeView {{
    background-color: {input_bg};
    color: {input_fg};
    border: 1px solid {input_border};
    selection-background-color: {selection_bg};
    selection-color: {selection_fg};
}}

#page_stack QLineEdit,
#page_stack QComboBox,
#page_stack QSpinBox,
#page_stack QDoubleSpinBox {{
    min-height: 30px;
    padding: 2px 8px;
}}

#page_stack QPlainTextEdit,
#page_stack QTextBrowser {{
    padding: 6px 8px;
}}

#page_stack QLineEdit:focus,
#page_stack QPlainTextEdit:focus,
#page_stack QComboBox:focus,
#page_stack QSpinBox:focus,
#page_stack QDoubleSpinBox:focus,
#page_stack QTextBrowser:focus,
#page_stack QTableWidget:focus,
#page_stack QTreeWidget:focus {{
    border: 1px solid {input_focus};
}}

#page_stack QTabWidget::pane {{
    border: 1px solid {card_border};
    border-radius: 8px;
    top: -1px;
    background-color: {input_bg};
}}

#page_stack QTabBar::tab {{
    background-color: {tab_bg};
    color: {tab_fg};
    border: 1px solid {card_border};
    border-bottom: none;
    padding: 7px 12px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

#page_stack QTabBar::tab:selected {{
    background-color: {input_bg};
    color: {input_fg};
}}

#page_stack QPushButton {{
    background-color: {button_bg};
    color: {button_fg};
    border: 1px solid {button_border};
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}}

#page_stack QPushButton:hover {{
    background-color: {button_hover};
}}

#page_stack QPushButton:pressed {{
    background-color: {button_pressed};
}}

#page_stack QPushButton:disabled {{
    background-color: {button_disabled_bg};
    color: {button_disabled_fg};
    border-color: {button_disabled_border};
}}

#page_stack QPushButton[role="primary"] {{
    background-color: {primary_btn_bg};
    border-color: {primary_btn_border};
    color: {primary_btn_fg};
}}

#page_stack QPushButton[role="primary"]:hover {{
    background-color: {primary_btn_hover};
}}

#page_stack QPushButton[role="primary"]:pressed {{
    background-color: {primary_btn_pressed};
}}

#page_stack QHeaderView::section {{
    background-color: {header_bg};
    color: {header_fg};
    border: 1px solid {header_border};
    padding: 6px;
    font-weight: 600;
}}

#page_stack QTableWidget {{
    gridline-color: {grid_color};
    alternate-background-color: {alt_bg};
}}

#page_stack QTreeWidget {{
    alternate-background-color: {alt_bg};
}}

#page_stack QCheckBox {{
    color: {text_primary};
    spacing: 6px;
}}

#page_stack QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {input_border};
    background: {input_bg};
    border-radius: 3px;
}}

#page_stack QCheckBox::indicator:checked {{
    background: {primary_btn_bg};
    border-color: {primary_btn_border};
}}

#page_stack QProgressBar {{
    border: 1px solid {input_border};
    border-radius: 6px;
    background-color: {progress_bg};
    color: {text_primary};
    text-align: center;
}}

#page_stack QProgressBar::chunk {{
    background-color: {primary_btn_bg};
    border-radius: 5px;
}}

#page_stack QScrollBar:vertical,
#page_stack QScrollBar:horizontal {{
    background: {page_bg};
    border: 1px solid {page_border};
    border-radius: 6px;
}}

QStatusBar {{
    background-color: {status_bg};
    color: {status_fg};
    font-size: 12px;
}}

QStatusBar::item {{
    border: none;
}}
"""


def _style_for_theme(theme_name: str) -> str:
    """Build the application stylesheet for the requested theme."""
    normalized = str(theme_name).lower().strip()
    palette = _THEME_PALETTES["dark" if normalized == "dark" else "light"]
    return _STYLE_TEMPLATE.format(**palette)


class MainWindow(QMainWindow):
    """Primary application window with sidebar navigation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PTCG Art Scraper")
        self.resize(1100, 750)

        self._settings = QSettings("ptcg_art_scraper", "gui")
        self._nav_buttons: list[QPushButton] = []
        self._theme = str(self._settings.value("theme", "light"))

        self._apply_theme(self._theme)
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

        # Connect New Job -> Queue
        new_job_page: NewJobPage = self._pages[0]  # type: ignore[assignment]
        queue_page: QueuePage = self._pages[1]  # type: ignore[assignment]
        new_job_page.job_requested.connect(
            lambda config, items: self._start_job(queue_page, config, items)
        )

        # Connect settings theme updates
        settings_page: SettingsPage = self._pages[3]  # type: ignore[assignment]
        settings_page.theme_changed.connect(self._apply_theme)

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

    def _apply_theme(self, theme_name: str) -> None:
        """Apply and persist the selected theme."""
        normalized = "dark" if str(theme_name).lower() == "dark" else "light"
        self._theme = normalized
        self._settings.setValue("theme", normalized)
        self.setStyleSheet(_style_for_theme(normalized))

        if hasattr(self, "_stack") and self._nav_buttons:
            self._switch_page(self._stack.currentIndex())

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
