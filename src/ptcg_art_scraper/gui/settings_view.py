"""Settings page – persistent user preferences."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsPage(QWidget):
    """Persistent application settings backed by QSettings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings("ptcg_art_scraper", "gui")
        self._build_ui()
        self._load()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        form = QFormLayout()

        # Default output folder
        out_row = QHBoxLayout()
        self._output_dir = QLineEdit()
        self._output_dir.setPlaceholderText("Default output folder")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self._output_dir, stretch=1)
        out_row.addWidget(self._browse_btn)
        form.addRow("Output folder:", out_row)

        # Default provider
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["pkmncards"])
        form.addRow("Provider:", self._provider_combo)

        # Default format
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["png", "jpeg"])
        form.addRow("Format:", self._fmt_combo)

        # Folder template
        self._template_edit = QLineEdit()
        self._template_edit.setPlaceholderText(
            "e.g. {setId}/{number}_{name}.{fmt} or {basicType}/{set}/{rarity}/{number}_{name}.{fmt}"
        )
        form.addRow("Folder template:", self._template_edit)
        template_help = QLabel(
            "Tokens: {set}, {setId}, {number}, {name}, {basicType}, {specificType}, {rarity}, {fmt}"
        )
        template_help.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", template_help)

        # Normalization (read-only)
        norm_label = QLabel("750 × 1050 @ 300 DPI")
        norm_label.setStyleSheet("color: #666;")
        form.addRow("Normalization:", norm_label)

        # Network defaults
        self._conc_spin = QSpinBox()
        self._conc_spin.setRange(1, 16)
        self._conc_spin.setValue(8)
        form.addRow("Concurrency:", self._conc_spin)

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0.5, 10.0)
        self._rate_spin.setSingleStep(0.5)
        self._rate_spin.setValue(2.0)
        self._rate_spin.setSuffix(" req/s")
        form.addRow("Rate limit:", self._rate_spin)

        self._retries_spin = QSpinBox()
        self._retries_spin.setRange(0, 10)
        self._retries_spin.setValue(3)
        form.addRow("Retries:", self._retries_spin)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(5, 120)
        self._timeout_spin.setValue(20)
        self._timeout_spin.setSuffix(" s")
        form.addRow("Timeout:", self._timeout_spin)

        root.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.setProperty("role", "primary")
        self._save_btn.clicked.connect(self._save)
        btn_row.addWidget(self._save_btn)

        self._reset_btn = QPushButton("Reset Defaults")
        self._reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(self._reset_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        root.addStretch()

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select default output folder"
        )
        if folder:
            self._output_dir.setText(folder)

    # ------------------------------------------------------------------
    # Load / Save / Reset
    # ------------------------------------------------------------------

    def _load(self) -> None:
        s = self._settings
        self._output_dir.setText(str(s.value("output_dir", "")))
        idx = self._provider_combo.findText(
            str(s.value("default_provider", "pkmncards"))
        )
        if idx >= 0:
            self._provider_combo.setCurrentIndex(idx)
        fmt_idx = self._fmt_combo.findText(
            str(s.value("default_format", "png"))
        )
        if fmt_idx >= 0:
            self._fmt_combo.setCurrentIndex(fmt_idx)
        self._template_edit.setText(
            str(s.value("folder_template", ""))
        )
        self._conc_spin.setValue(
            int(s.value("concurrency", 8))  # type: ignore[arg-type]
        )
        self._rate_spin.setValue(
            float(s.value("rate", 2.0))  # type: ignore[arg-type]
        )
        self._retries_spin.setValue(
            int(s.value("retries", 3))  # type: ignore[arg-type]
        )
        self._timeout_spin.setValue(
            int(s.value("timeout", 20))  # type: ignore[arg-type]
        )

    def _save(self) -> None:
        s = self._settings
        s.setValue("output_dir", self._output_dir.text().strip())
        s.setValue(
            "default_provider", self._provider_combo.currentText()
        )
        s.setValue("default_format", self._fmt_combo.currentText())
        s.setValue(
            "folder_template", self._template_edit.text().strip()
        )
        s.setValue("concurrency", self._conc_spin.value())
        s.setValue("rate", self._rate_spin.value())
        s.setValue("retries", self._retries_spin.value())
        s.setValue("timeout", self._timeout_spin.value())
        QMessageBox.information(self, "Settings", "Settings saved.")

    def _reset_defaults(self) -> None:
        self._output_dir.clear()
        self._provider_combo.setCurrentIndex(0)
        self._fmt_combo.setCurrentIndex(0)
        self._template_edit.clear()
        self._conc_spin.setValue(8)
        self._rate_spin.setValue(2.0)
        self._retries_spin.setValue(3)
        self._timeout_spin.setValue(20)
