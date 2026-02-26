"""Help / About page – quick-start guide, troubleshooting, and diagnostics."""

from __future__ import annotations

import platform
import sys

from PySide6.QtCore import __version__ as qt_version
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import ptcg_art_scraper

_HELP_HTML = """\
<h2>PTCG Art Scraper v{version}</h2>

<h3>Quick Start</h3>
<ol>
  <li>Go to <b>New Job</b> and select your source (search, import file, or
      paste URLs).</li>
  <li>Choose an output folder and image format.</li>
  <li>Click <b>Build Queue</b> to resolve cards and start downloading.</li>
  <li>Monitor progress on the <b>Queue &amp; Progress</b> page.</li>
  <li>Browse results in the <b>Library</b> page.</li>
</ol>

<h3>Troubleshooting</h3>
<ul>
  <li><b>Rate limiting / 429 errors:</b> Lower the rate-limit slider in
      Advanced settings (1&ndash;2 req/s is usually safe).</li>
  <li><b>Blocked requests / 403 errors:</b> The provider may be blocking
      automated access. Try again later or use a different provider.</li>
  <li><b>Timeouts:</b> Increase the timeout value in Advanced settings or
      check your internet connection.</li>
  <li><b>Missing images:</b> Some cards may not have high-resolution art
      available yet. Check the provider website directly.</li>
</ul>

<h3>Legal</h3>
<p>Pok&eacute;mon and Pok&eacute;mon TCG are trademarks of Nintendo /
Creatures Inc. / GAME FREAK inc. This tool is an unofficial fan project
and is not affiliated with or endorsed by The Pok&eacute;mon Company.
Card images are &copy; their respective rights holders. Please respect
copyright and use downloaded images only for personal, non-commercial
purposes.</p>

<h3>Links</h3>
<p><a href="https://github.com/pokemon-tcg/ptcg-art-scraper">
GitHub Repository</a></p>
"""


class HelpPage(QWidget):
    """Displays help content, version info, and a diagnostics button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setHtml(
            _HELP_HTML.format(version=ptcg_art_scraper.__version__)
        )
        root.addWidget(self._browser, stretch=1)

        btn_row = QHBoxLayout()
        self._copy_diag_btn = QPushButton("Copy Diagnostics")
        self._copy_diag_btn.clicked.connect(self._copy_diagnostics)
        btn_row.addWidget(self._copy_diag_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @staticmethod
    def _copy_diagnostics() -> None:
        info = (
            f"App version: {ptcg_art_scraper.__version__}\n"
            f"Python: {sys.version}\n"
            f"Qt (PySide6): {qt_version}\n"
            f"OS: {platform.platform()}\n"
        )
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(info)
