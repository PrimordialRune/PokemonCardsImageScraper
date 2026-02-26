"""New Job page – wizard-like flow for configuring and starting a scrape job."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

from ptcg_art_scraper.core.models import JobConfig, QueueItem

# ---------------------------------------------------------------------------
# Async search worker
# ---------------------------------------------------------------------------


class _SearchWorker(QThread):
    """Run ``resolve_search`` in a background thread."""

    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        provider: str,
        query: str,
        set_filter: str,
        limit: int,
        rate: float,
        timeout: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._query = query
        self._set_filter = set_filter
        self._limit = limit
        self._rate = rate
        self._timeout = timeout

    def run(self) -> None:  # noqa: D401
        from ptcg_art_scraper.core.engine import resolve_search

        try:
            items = asyncio.run(
                resolve_search(
                    self._provider,
                    self._query,
                    set_filter=self._set_filter,
                    limit=self._limit,
                    rate=self._rate,
                    timeout=self._timeout,
                )
            )
            self.finished.emit(items)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class _FileImportWorker(QThread):
    """Parse a CSV / JSON / TXT file into queue items."""

    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self, path: str, provider: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._provider = provider

    def run(self) -> None:  # noqa: D401
        try:
            items = _parse_import_file(self._path, self._provider)
            self.finished.emit(items)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


def _parse_import_file(path: str, provider: str) -> list[QueueItem]:
    """Return queue items from a CSV, JSON or plain-text file."""
    p = Path(path)
    suffix = p.suffix.lower()
    items: list[QueueItem] = []

    if suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        entries: Sequence[str | dict[str, str]] = (
            data if isinstance(data, list) else data.get("urls", [])
        )
        for entry in entries:
            url = entry if isinstance(entry, str) else entry.get("url", "")
            if url:
                items.append(
                    QueueItem(identifier=url, source_url=url, provider=provider)
                )
    elif suffix == ".csv":
        with p.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                url = row.get("url", "") or row.get("URL", "")
                if url:
                    items.append(
                        QueueItem(
                            identifier=url,
                            source_url=url,
                            name=row.get("name", ""),
                            provider=provider,
                        )
                    )
    else:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(
                    QueueItem(
                        identifier=line, source_url=line, provider=provider
                    )
                )
    return items


# ---------------------------------------------------------------------------
# New-job page widget
# ---------------------------------------------------------------------------


class NewJobPage(QWidget):
    """Wizard-like page for configuring a new scrape job."""

    job_requested = Signal(JobConfig, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings("ptcg_art_scraper", "gui")
        self._worker: _SearchWorker | _FileImportWorker | None = None
        self._build_ui()
        self._restore_prefs()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        # --- Source section ---
        src_group = QGroupBox("Source")
        src_layout = QVBoxLayout(src_group)

        prov_row = QHBoxLayout()
        prov_row.addWidget(QLabel("Provider:"))
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["pkmncards"])
        prov_row.addWidget(self._provider_combo, stretch=1)
        src_layout.addLayout(prov_row)

        self._input_tabs = QTabWidget()

        # Search tab
        search_tab = QWidget()
        sl = QVBoxLayout(search_tab)
        self._search_query = QLineEdit()
        self._search_query.setPlaceholderText("e.g. Charizard")
        sl.addWidget(QLabel("Search query:"))
        sl.addWidget(self._search_query)
        self._set_filter_edit = QLineEdit()
        self._set_filter_edit.setPlaceholderText("Optional set filter")
        sl.addWidget(QLabel("Set filter:"))
        sl.addWidget(self._set_filter_edit)
        sl.addStretch()
        self._input_tabs.addTab(search_tab, "Search")

        # Import File tab
        import_tab = QWidget()
        il = QVBoxLayout(import_tab)
        file_row = QHBoxLayout()
        self._import_path = QLineEdit()
        self._import_path.setPlaceholderText("Path to CSV / JSON / TXT")
        self._import_browse_btn = QPushButton("Browse…")
        self._import_browse_btn.clicked.connect(self._browse_import_file)
        file_row.addWidget(self._import_path, stretch=1)
        file_row.addWidget(self._import_browse_btn)
        il.addLayout(file_row)
        sample_label = QLabel(
            '<a href="#sample">Download sample CSV</a>'
        )
        sample_label.linkActivated.connect(self._save_sample_file)
        il.addWidget(sample_label)
        il.addStretch()
        self._input_tabs.addTab(import_tab, "Import File")

        # Direct URLs tab
        urls_tab = QWidget()
        ul = QVBoxLayout(urls_tab)
        self._urls_edit = QPlainTextEdit()
        self._urls_edit.setPlaceholderText("Paste URLs, one per line")
        ul.addWidget(self._urls_edit)
        self._input_tabs.addTab(urls_tab, "Direct URLs")

        src_layout.addWidget(self._input_tabs)

        self._validate_btn = QPushButton("Validate")
        self._validate_btn.clicked.connect(self._validate_input)
        self._validate_label = QLabel("")
        val_row = QHBoxLayout()
        val_row.addWidget(self._validate_btn)
        val_row.addWidget(self._validate_label, stretch=1)
        src_layout.addLayout(val_row)

        root.addWidget(src_group)

        # --- Output section ---
        out_group = QGroupBox("Output")
        out_layout = QFormLayout(out_group)

        out_row = QHBoxLayout()
        self._output_dir = QLineEdit()
        self._output_dir.setPlaceholderText("Select output folder…")
        self._output_browse_btn = QPushButton("Browse…")
        self._output_browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self._output_dir, stretch=1)
        out_row.addWidget(self._output_browse_btn)
        out_layout.addRow("Folder:", out_row)

        self._naming_preview = QLabel("…/SetName/001_CardName.png")
        self._naming_preview.setStyleSheet("color: #888;")
        out_layout.addRow("Preview:", self._naming_preview)

        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["png", "jpeg"])
        self._fmt_combo.currentTextChanged.connect(self._update_preview)
        out_layout.addRow("Format:", self._fmt_combo)

        self._overwrite_cb = QCheckBox("Overwrite existing files")
        out_layout.addRow(self._overwrite_cb)

        self._resume_cb = QCheckBox("Resume (skip already downloaded)")
        self._resume_cb.setChecked(True)
        out_layout.addRow(self._resume_cb)

        root.addWidget(out_group)

        # --- Advanced section (collapsible) ---
        self._adv_group = QGroupBox("Advanced")
        self._adv_group.setCheckable(True)
        self._adv_group.setChecked(False)
        adv_layout = QFormLayout(self._adv_group)

        # Concurrency slider
        conc_row = QHBoxLayout()
        self._conc_slider = QSlider()
        self._conc_slider.setOrientation(Qt.Orientation.Horizontal)
        self._conc_slider.setRange(1, 16)
        self._conc_slider.setValue(8)
        self._conc_label = QLabel("8")
        self._conc_slider.valueChanged.connect(
            lambda v: self._conc_label.setText(str(v))
        )
        conc_row.addWidget(self._conc_slider, stretch=1)
        conc_row.addWidget(self._conc_label)
        adv_layout.addRow("Concurrency:", conc_row)

        # Rate-limit slider (stored as int × 10 for 0.5 step)
        rate_row = QHBoxLayout()
        self._rate_slider = QSlider()
        self._rate_slider.setOrientation(Qt.Orientation.Horizontal)
        self._rate_slider.setRange(5, 100)
        self._rate_slider.setValue(20)
        self._rate_label = QLabel("2.0 req/s")
        self._rate_slider.valueChanged.connect(self._rate_changed)
        rate_row.addWidget(self._rate_slider, stretch=1)
        rate_row.addWidget(self._rate_label)
        adv_layout.addRow("Rate limit:", rate_row)

        self._retries_spin = QSpinBox()
        self._retries_spin.setRange(0, 10)
        self._retries_spin.setValue(3)
        adv_layout.addRow("Retries:", self._retries_spin)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(5, 120)
        self._timeout_spin.setValue(20)
        self._timeout_spin.setSuffix(" s")
        adv_layout.addRow("Timeout:", self._timeout_spin)

        root.addWidget(self._adv_group)

        # --- Progress indicator ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setVisible(False)
        root.addWidget(self._progress_bar)

        # --- Bottom action ---
        self._build_btn = QPushButton("Build Queue")
        self._build_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "padding: 10px 24px; font-size: 14px; font-weight: bold; "
            "border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
        )
        self._build_btn.clicked.connect(self._build_queue)
        root.addWidget(self._build_btn)

        root.addStretch()

    # ------------------------------------------------------------------
    # Slot helpers
    # ------------------------------------------------------------------

    def _rate_changed(self, value: int) -> None:
        self._rate_label.setText(f"{value / 10:.1f} req/s")

    def _update_preview(self) -> None:
        fmt = self._fmt_combo.currentText()
        self._naming_preview.setText(f"…/SetName/001_CardName.{fmt}")

    def _browse_import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select import file",
            "",
            "Supported Files (*.csv *.json *.txt);;All Files (*)",
        )
        if path:
            self._import_path.setText(path)

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder"
        )
        if folder:
            self._output_dir.setText(folder)
            self._settings.setValue("output_dir", folder)

    def _save_sample_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save sample CSV", "sample.csv", "CSV (*.csv)"
        )
        if path:
            Path(path).write_text(
                "url,name\n"
                "https://pkmncards.com/card/charizard-ex-sv-obsidian-flames-ovp/"
                ",Charizard ex\n",
                encoding="utf-8",
            )

    def _validate_input(self) -> None:
        tab = self._input_tabs.currentIndex()
        if tab == 0:
            q = self._search_query.text().strip()
            self._validate_label.setText(
                f"Query: '{q}'" if q else "Enter a search query"
            )
        elif tab == 1:
            p = self._import_path.text().strip()
            if p and Path(p).is_file():
                items = _parse_import_file(
                    p, self._provider_combo.currentText()
                )
                self._validate_label.setText(
                    f"{len(items)} item(s) recognized"
                )
            else:
                self._validate_label.setText("Select a valid file")
        else:
            lines = [
                ln.strip()
                for ln in self._urls_edit.toPlainText().splitlines()
                if ln.strip()
            ]
            self._validate_label.setText(f"{len(lines)} URL(s) entered")

    # ------------------------------------------------------------------
    # Build queue
    # ------------------------------------------------------------------

    def _current_config(self) -> JobConfig:
        return JobConfig(
            provider=self._provider_combo.currentText(),
            output_dir=self._output_dir.text().strip(),
            fmt=self._fmt_combo.currentText(),
            concurrency=self._conc_slider.value(),
            rate=self._rate_slider.value() / 10.0,
            retries=self._retries_spin.value(),
            timeout=float(self._timeout_spin.value()),
            resume=self._resume_cb.isChecked(),
            overwrite=self._overwrite_cb.isChecked(),
            set_filter=self._set_filter_edit.text().strip(),
            limit=0,
        )

    def _build_queue(self) -> None:
        config = self._current_config()
        if not config.output_dir:
            self._validate_label.setText("⚠️ Select an output folder first")
            return

        tab = self._input_tabs.currentIndex()
        self._build_btn.setEnabled(False)
        self._progress_bar.setVisible(True)

        if tab == 0:
            query = self._search_query.text().strip()
            if not query:
                self._validate_label.setText("⚠️ Enter a search query")
                self._build_btn.setEnabled(True)
                self._progress_bar.setVisible(False)
                return
            worker = _SearchWorker(
                provider=config.provider,
                query=query,
                set_filter=config.set_filter,
                limit=config.limit,
                rate=config.rate,
                timeout=config.timeout,
                parent=self,
            )
            worker.finished.connect(
                lambda items: self._on_items_ready(config, items)
            )
            worker.error.connect(self._on_worker_error)
            self._worker = worker
            worker.start()
        elif tab == 1:
            path = self._import_path.text().strip()
            if not path or not Path(path).is_file():
                self._validate_label.setText("⚠️ Select a valid file")
                self._build_btn.setEnabled(True)
                self._progress_bar.setVisible(False)
                return
            worker = _FileImportWorker(
                path=path,
                provider=config.provider,
                parent=self,
            )
            worker.finished.connect(
                lambda items: self._on_items_ready(config, items)
            )
            worker.error.connect(self._on_worker_error)
            self._worker = worker
            worker.start()
        else:
            lines = [
                ln.strip()
                for ln in self._urls_edit.toPlainText().splitlines()
                if ln.strip()
            ]
            items = [
                QueueItem(
                    identifier=url,
                    source_url=url,
                    provider=config.provider,
                )
                for url in lines
            ]
            self._on_items_ready(config, items)

    def _on_items_ready(
        self, config: JobConfig, items: list[QueueItem]
    ) -> None:
        self._build_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        if not items:
            self._validate_label.setText("⚠️ No items found")
            return
        self._validate_label.setText(f"✅ {len(items)} item(s) queued")
        self.job_requested.emit(config, items)

    def _on_worker_error(self, message: str) -> None:
        self._build_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._validate_label.setText(f"❌ {message}")

    # ------------------------------------------------------------------
    # Preference persistence
    # ------------------------------------------------------------------

    def _restore_prefs(self) -> None:
        out = self._settings.value("output_dir", "")
        if out:
            self._output_dir.setText(str(out))
        fmt = self._settings.value("default_format", "png")
        idx = self._fmt_combo.findText(str(fmt))
        if idx >= 0:
            self._fmt_combo.setCurrentIndex(idx)
