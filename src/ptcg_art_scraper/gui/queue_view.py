"""Queue & Progress page – displays scrape progress and controls."""

from __future__ import annotations

import asyncio
import csv
import time
from io import StringIO
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    pass

from ptcg_art_scraper.core.models import (
    EventType,
    ItemStatus,
    JobConfig,
    JobEvent,
    QueueItem,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATUS_ICONS: dict[ItemStatus, str] = {
    ItemStatus.QUEUED: "⏳",
    ItemStatus.RESOLVING: "🔍",
    ItemStatus.FETCHING: "⬇️",
    ItemStatus.NORMALIZING: "🔄",
    ItemStatus.SAVED: "✅",
    ItemStatus.SKIPPED: "⏭️",
    ItemStatus.FAILED: "❌",
}

_COL_STATUS = 0
_COL_CARD = 1
_COL_SET = 2
_COL_TYPE = 3
_COL_RARITY = 4
_COL_SOURCE = 5
_COL_OUTPUT = 6
_COL_PROGRESS = 7
_COL_MESSAGE = 8
_COL_HEADERS = ["Status", "Card", "Set", "Type", "Rarity", "Source", "Output", "Progress", "Message"]


# ---------------------------------------------------------------------------
# Scrape worker
# ---------------------------------------------------------------------------


class ScrapeWorker(QThread):
    """Run :class:`ScrapeEngine` in a background thread."""

    event_emitted = Signal(object)  # JobEvent
    finished_signal = Signal()

    def __init__(
        self,
        config: JobConfig,
        items: list[QueueItem],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._items = items
        self._engine: object | None = None

    def run(self) -> None:  # noqa: D401
        from ptcg_art_scraper.core.engine import ScrapeEngine

        engine = ScrapeEngine(
            self._config,
            self._items,
            on_event=lambda evt: self.event_emitted.emit(evt),
        )
        self._engine = engine
        asyncio.run(engine.run())
        self.finished_signal.emit()

    # Proxy controls to the engine (thread-safe) --------------------------

    def request_pause(self) -> None:
        if self._engine is not None:
            self._engine.request_pause()  # type: ignore[attr-defined]

    def request_resume(self) -> None:
        if self._engine is not None:
            self._engine.request_resume()  # type: ignore[attr-defined]

    def request_cancel(self) -> None:
        if self._engine is not None:
            self._engine.request_cancel()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Queue page
# ---------------------------------------------------------------------------


class QueuePage(QWidget):
    """Displays the queue table, progress, controls and log panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[QueueItem] = []
        self._item_row: dict[str, int] = {}
        self._config: JobConfig | None = None
        self._worker: ScrapeWorker | None = None
        self._paused = False
        self._start_time: float = 0.0
        self._completed_count = 0
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        # --- Filter row ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Search:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter by name, set…")
        self._filter_edit.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(self._filter_edit, stretch=1)

        filter_layout.addWidget(QLabel("Type:"))
        self._type_filter = QComboBox()
        self._type_filter.addItems(["All", "Pokemon", "Trainer", "Energy"])
        self._type_filter.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self._type_filter)

        filter_layout.addWidget(QLabel("Rarity:"))
        self._rarity_filter = QComboBox()
        self._rarity_filter.addItems(["All"])
        self._rarity_filter.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self._rarity_filter)
        root.addLayout(filter_layout)

        # --- Queue table ---
        self._table = QTableWidget(0, len(_COL_HEADERS))
        self._table.setHorizontalHeaderLabels(_COL_HEADERS)
        self._table.setSortingEnabled(True)
        header = self._table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(
                _COL_CARD, QHeaderView.ResizeMode.Stretch
            )
            header.setSectionResizeMode(
                _COL_MESSAGE, QHeaderView.ResizeMode.Stretch
            )
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        root.addWidget(self._table, stretch=3)

        # --- Global progress ---
        prog_layout = QVBoxLayout()
        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        prog_layout.addWidget(self._progress_bar)

        self._counters_label = QLabel(
            "✅ 0 saved | ⏭️ 0 skipped | ❌ 0 failed | ⏳ 0 remaining"
        )
        prog_layout.addWidget(self._counters_label)

        self._throughput_label = QLabel("0 cards/min")
        prog_layout.addWidget(self._throughput_label)
        root.addLayout(prog_layout)

        # --- Controls ---
        ctrl_layout = QHBoxLayout()
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._pause_btn.setEnabled(False)
        ctrl_layout.addWidget(self._pause_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._cancel)
        self._cancel_btn.setEnabled(False)
        ctrl_layout.addWidget(self._cancel_btn)

        self._retry_btn = QPushButton("Retry Failed")
        self._retry_btn.clicked.connect(self._retry_failed)
        self._retry_btn.setEnabled(False)
        ctrl_layout.addWidget(self._retry_btn)

        self._export_btn = QPushButton("Export Report")
        self._export_btn.clicked.connect(self._export_report)
        ctrl_layout.addWidget(self._export_btn)

        ctrl_layout.addStretch()
        root.addLayout(ctrl_layout)

        # --- Logs panel ---
        self._log_group = QGroupBox("Logs")
        self._log_group.setCheckable(True)
        self._log_group.setChecked(False)
        log_layout = QVBoxLayout(self._log_group)

        log_ctrl = QHBoxLayout()
        self._log_filter = QComboBox()
        self._log_filter.addItems(["All", "Info", "Warning", "Error"])
        log_ctrl.addWidget(QLabel("Level:"))
        log_ctrl.addWidget(self._log_filter)
        log_ctrl.addStretch()
        self._copy_diag_btn = QPushButton("Copy Diagnostics")
        self._copy_diag_btn.clicked.connect(self._copy_diagnostics)
        log_ctrl.addWidget(self._copy_diag_btn)
        log_layout.addLayout(log_ctrl)

        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumBlockCount(5000)
        log_layout.addWidget(self._log_edit)

        root.addWidget(self._log_group, stretch=1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_queue(
        self, items: list[QueueItem], config: JobConfig
    ) -> None:
        """Populate the table and start the scrape job."""
        self._items = list(items)
        self._config = config
        self._item_row.clear()
        self._completed_count = 0
        self._start_time = time.monotonic()

        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            self._item_row[item.id] = row
            self._set_row(row, item)

        self._progress_bar.setMaximum(len(self._items))
        self._progress_bar.setValue(0)
        self._update_counters()

        # Start engine
        self._worker = ScrapeWorker(config, self._items, parent=self)
        self._worker.event_emitted.connect(self.handle_event)
        self._worker.finished_signal.connect(self._on_job_finished)
        self._pause_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._retry_btn.setEnabled(False)
        self._paused = False
        self._pause_btn.setText("Pause")
        self._worker.start()

    def handle_event(self, event: JobEvent) -> None:
        """Update table and progress from an engine event."""
        etype = event.event_type

        if etype == EventType.LOG:
            self.append_log("info", event.message)
            return

        if etype in (
            EventType.JOB_STARTED,
            EventType.JOB_FINISHED,
            EventType.JOB_CANCELLED,
        ):
            self.append_log("info", event.message)
            return

        row = self._item_row.get(event.item_id)
        if row is None:
            return

        item = self._items[row]
        status_map: dict[EventType, ItemStatus] = {
            EventType.ITEM_QUEUED: ItemStatus.QUEUED,
            EventType.ITEM_RESOLVING: ItemStatus.RESOLVING,
            EventType.ITEM_FETCHING: ItemStatus.FETCHING,
            EventType.ITEM_NORMALIZING: ItemStatus.NORMALIZING,
            EventType.ITEM_SAVED: ItemStatus.SAVED,
            EventType.ITEM_SKIPPED: ItemStatus.SKIPPED,
            EventType.ITEM_FAILED: ItemStatus.FAILED,
        }
        new_status = status_map.get(etype)
        if new_status is not None:
            item.status = new_status
        item.progress = event.progress
        item.message = event.message
        self._set_row(row, item)

        if etype in (
            EventType.ITEM_SAVED,
            EventType.ITEM_SKIPPED,
            EventType.ITEM_FAILED,
        ):
            self._completed_count += 1
            self._progress_bar.setValue(self._completed_count)

        self._update_counters()

    def append_log(self, level: str, message: str) -> None:
        """Add a message to the log pane, respecting the level filter."""
        current_filter = self._log_filter.currentText().lower()
        if current_filter != "all" and level.lower() != current_filter:
            return
        prefix = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(
            level.lower(), "•"
        )
        self._log_edit.appendPlainText(f"{prefix} {message}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_row(self, row: int, item: QueueItem) -> None:
        icon = _STATUS_ICONS.get(item.status, "")
        self._table.setItem(
            row,
            _COL_STATUS,
            QTableWidgetItem(f"{icon} {item.status.value}"),
        )
        card_text = item.name or item.identifier
        if item.number:
            card_text += f" #{item.number}"
        self._table.setItem(row, _COL_CARD, QTableWidgetItem(card_text))
        set_text = item.set_name or item.set_code or ""
        self._table.setItem(row, _COL_SET, QTableWidgetItem(set_text))
        type_parts = [item.basic_type, item.specific_type]
        type_text = " / ".join(p for p in type_parts if p)
        self._table.setItem(row, _COL_TYPE, QTableWidgetItem(type_text))
        self._table.setItem(
            row, _COL_RARITY, QTableWidgetItem(item.rarity)
        )
        self._table.setItem(
            row, _COL_SOURCE, QTableWidgetItem(item.source_url)
        )
        self._table.setItem(
            row, _COL_OUTPUT, QTableWidgetItem(item.output_path)
        )
        pct = f"{item.progress * 100:.0f}%"
        self._table.setItem(row, _COL_PROGRESS, QTableWidgetItem(pct))
        self._table.setItem(
            row, _COL_MESSAGE, QTableWidgetItem(item.message)
        )

    def _update_counters(self) -> None:
        saved = sum(
            1 for i in self._items if i.status == ItemStatus.SAVED
        )
        skipped = sum(
            1 for i in self._items if i.status == ItemStatus.SKIPPED
        )
        failed = sum(
            1 for i in self._items if i.status == ItemStatus.FAILED
        )
        remaining = len(self._items) - saved - skipped - failed
        self._counters_label.setText(
            f"✅ {saved} saved | ⏭️ {skipped} skipped "
            f"| ❌ {failed} failed | ⏳ {remaining} remaining"
        )
        elapsed = time.monotonic() - self._start_time
        if elapsed > 0 and self._completed_count > 0:
            rate = self._completed_count / (elapsed / 60.0)
            self._throughput_label.setText(f"{rate:.1f} cards/min")

    def _apply_filter(self) -> None:
        """Show/hide table rows based on search text and filter combos."""
        text = self._filter_edit.text().strip().lower()
        type_filter = self._type_filter.currentText()
        rarity_filter = self._rarity_filter.currentText()
        for row, item in enumerate(self._items):
            visible = True
            if text:
                haystack = f"{item.name} {item.set_name} {item.set_code}".lower()
                if text not in haystack:
                    visible = False
            if visible and type_filter != "All":
                if item.basic_type != type_filter:
                    visible = False
            if visible and rarity_filter != "All":
                if item.rarity.lower() != rarity_filter.lower():
                    visible = False
            self._table.setRowHidden(row, not visible)

    # ------------------------------------------------------------------
    # Control slots
    # ------------------------------------------------------------------

    def _toggle_pause(self) -> None:
        if self._worker is None:
            return
        if self._paused:
            self._worker.request_resume()
            self._pause_btn.setText("Pause")
            self._paused = False
        else:
            self._worker.request_pause()
            self._pause_btn.setText("Resume")
            self._paused = True

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)

    def _on_job_finished(self) -> None:
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._retry_btn.setEnabled(
            any(i.status == ItemStatus.FAILED for i in self._items)
        )
        self.append_log("info", "Job finished.")

    def _retry_failed(self) -> None:
        if self._config is None:
            return
        failed = [
            QueueItem(
                identifier=i.identifier,
                source_url=i.source_url,
                provider=i.provider,
                name=i.name,
                set_name=i.set_name,
                number=i.number,
            )
            for i in self._items
            if i.status == ItemStatus.FAILED
        ]
        if failed:
            self.set_queue(failed, self._config)

    def _export_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Report", "report.csv", "CSV (*.csv)"
        )
        if not path:
            return
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["Status", "Card", "Source", "Output", "Message"]
        )
        for item in self._items:
            writer.writerow([
                item.status.value,
                item.name or item.identifier,
                item.source_url,
                item.output_path,
                item.message,
            ])
        from pathlib import Path as _P

        _P(path).write_text(buf.getvalue(), encoding="utf-8")

    def _copy_diagnostics(self) -> None:
        import platform
        import sys

        from PySide6.QtCore import __version__ as qt_ver
        from PySide6.QtWidgets import QApplication

        info = (
            f"Python: {sys.version}\n"
            f"Qt: {qt_ver}\n"
            f"OS: {platform.platform()}\n"
            f"Items: {len(self._items)}\n"
            f"Completed: {self._completed_count}\n"
        )
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(info)
