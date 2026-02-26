"""New Job page – wizard-like flow for configuring and starting a scrape job."""

from __future__ import annotations

import asyncio
import csv
import json
import re
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


_SERIES_PRESETS: list[tuple[str, str]] = [
    ("Any series", ""),
    ("EX era (2003-2007)", "ex"),
    ("Diamond & Pearl", "diamond-pearl"),
    ("Platinum", "platinum"),
    ("HeartGold & SoulSilver", "heartgold-soulsilver"),
    ("Black & White", "black-white"),
    ("XY", "xy"),
    ("Sun & Moon", "sun-moon"),
    ("Sword & Shield", "sword-shield"),
    ("Scarlet & Violet", "scarlet-violet"),
]

_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("Any type", ""),
    ("Pokemon", "pokemon"),
    ("Basic Pokemon", "basic-pokemon"),
    ("Trainer", "trainer"),
    ("Supporter", "supporter"),
    ("Item", "item"),
    ("Stadium", "stadium"),
    ("Pokemon Tool", "pokemon-tool"),
    ("Energy", "energy"),
    ("Special Energy", "special-energy"),
]

_COLOR_OPTIONS: list[tuple[str, str]] = [
    ("Any color", ""),
    ("Grass", "grass"),
    ("Fire", "fire"),
    ("Water", "water"),
    ("Lightning", "lightning"),
    ("Psychic", "psychic"),
    ("Fighting", "fighting"),
    ("Darkness", "darkness"),
    ("Metal", "metal"),
    ("Dragon", "dragon"),
    ("Fairy", "fairy"),
    ("Colorless", "colorless"),
]

_STAGE_OPTIONS: list[tuple[str, str]] = [
    ("Any stage", ""),
    ("Basic", "basic"),
    ("Stage 1", "stage-1"),
    ("Stage 2", "stage-2"),
    ("VMAX", "vmax"),
    ("VSTAR", "vstar"),
    ("LEGEND", "legend"),
    ("BREAK", "break"),
    ("Restored", "restored"),
]

_RARITY_OPTIONS: list[tuple[str, str]] = [
    ("Any rarity", ""),
    ("Common", "common"),
    ("Uncommon", "uncommon"),
    ("Rare", "rare"),
    ("Rare Holo", "rare-holo"),
    ("Rare Holo EX", "rare-holo-ex"),
    ("Rare Holo GX", "rare-holo-gx"),
    ("Rare Holo LV.X", "rare-holo-lv-x"),
    ("Rare Holo Star", "rare-holo-star"),
    ("Rare Prime", "rare-prime"),
    ("Rare Prism Star", "rare-prism-star"),
    ("Rare ACE", "rare-ace"),
    ("Rare BREAK", "rare-break"),
    ("Rare Rainbow", "rare-rainbow"),
    ("Rare Secret", "rare-secret"),
    ("Rare Ultra", "rare-ultra"),
    ("Illustration Rare", "illustration-rare"),
    ("Special Illustration Rare", "special-illustration-rare"),
    ("Promo", "promo"),
]

_COLLECTION_OPTIONS: list[tuple[str, str]] = [
    ("Any collection", ""),
    ("Shiny Vault", "shiny-vault"),
]

_FORMAT_OPTIONS: list[tuple[str, str]] = [
    ("Any format", ""),
    ("Standard", "standard"),
    ("Expanded", "expanded"),
    ("Unlimited", "unlimited"),
]

_MARK_OPTIONS: list[tuple[str, str]] = [
    ("Any mark", ""),
    ("D", "d"),
    ("E", "e"),
    ("F", "f"),
    ("G", "g"),
    ("H", "h"),
    ("I", "i"),
]

_HAS_OPTIONS: list[tuple[str, str]] = [
    ("Any has-value", ""),
    ("Ability", "ability"),
    ("Ancient Trait", "ancient-trait"),
    ("Poke-Body", "poke-body"),
    ("Poke-Power", "poke-power"),
    ("Pokemon Power", "pokemon-power"),
    ("Rule Box", "rule-box"),
]

_IS_OPTIONS: list[tuple[str, str]] = [
    ("Any is-value", ""),
    ("ex", "ex"),
    ("GX", "gx"),
    ("V", "v"),
    ("VMAX", "vmax"),
    ("VSTAR", "vstar"),
    ("TAG TEAM", "tag-team"),
    ("Delta Species", "delta-species"),
    ("Radiant", "radiant"),
    ("Prime", "prime"),
    ("LEGEND", "legend"),
    ("Baby Pokemon", "baby"),
]

_PRINT_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("Any print type", ""),
    ("Holo", "holo"),
    ("Reverse Holo", "reverse-holo"),
    ("Non Holo", "non-holo"),
    ("Full Art", "full-art"),
    ("Secret", "secret"),
]

_NUMERIC_OPERATORS: list[tuple[str, str]] = [
    ("=", "="),
    (">=", ">="),
    ("<=", "<="),
    (">", ">"),
    ("<", "<"),
]


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

        self._guided_mode_cb = QCheckBox("Use guided filters (recommended)")
        self._guided_mode_cb.setChecked(True)
        self._guided_mode_cb.toggled.connect(self._sync_search_mode)
        sl.addWidget(self._guided_mode_cb)

        sl.addWidget(QLabel("Manual query syntax:"))
        self._search_query = QLineEdit()
        self._search_query.setPlaceholderText(
            'e.g. Charizard, series:ex, rarity:"Rare Holo"'
        )
        sl.addWidget(self._search_query)

        syntax_help = QLabel(
            '<a href="https://pkmncards.com/advanced/">'
            "Query syntax reference (pkmncards advanced search)"
            "</a>"
        )
        syntax_help.setOpenExternalLinks(True)
        sl.addWidget(syntax_help)

        self._guided_group = QGroupBox("Guided filters")
        guided_layout = QFormLayout(self._guided_group)

        self._guided_name_edit = QLineEdit()
        self._guided_name_edit.setPlaceholderText("e.g. Charizard ex 100/197")
        self._guided_name_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Card Name, Set, or #:", self._guided_name_edit)

        self._guided_text_edit = QLineEdit()
        self._guided_text_edit.setPlaceholderText(
            "Search card text (uses text: token)"
        )
        self._guided_text_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Card Text:", self._guided_text_edit)

        text_opts = QWidget()
        text_opts_layout = QHBoxLayout(text_opts)
        text_opts_layout.setContentsMargins(0, 0, 0, 0)
        self._guided_text_exact_cb = QCheckBox("Match exact phrase")
        self._guided_text_exact_cb.toggled.connect(
            self._update_guided_query_preview
        )
        text_opts_layout.addWidget(self._guided_text_exact_cb)
        self._guided_exclude_edit = QLineEdit()
        self._guided_exclude_edit.setPlaceholderText(
            "Exclude words (space separated)"
        )
        self._guided_exclude_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        text_opts_layout.addWidget(self._guided_exclude_edit, stretch=1)
        guided_layout.addRow("", text_opts)

        self._guided_set_edit = QLineEdit()
        self._guided_set_edit.setPlaceholderText("e.g. ex-unseen-forces")
        self._guided_set_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Set:", self._guided_set_edit)

        self._guided_series_combo = QComboBox()
        for label, value in _SERIES_PRESETS:
            self._guided_series_combo.addItem(label, value)
        self._guided_series_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Series:", self._guided_series_combo)

        self._guided_collection_combo = QComboBox()
        for label, value in _COLLECTION_OPTIONS:
            self._guided_collection_combo.addItem(label, value)
        self._guided_collection_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Collection:", self._guided_collection_combo)

        self._guided_artist_edit = QLineEdit()
        self._guided_artist_edit.setPlaceholderText("e.g. Ken Sugimori")
        self._guided_artist_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Artist:", self._guided_artist_edit)

        self._guided_rarity_combo = QComboBox()
        self._guided_rarity_combo.setEditable(True)
        for label, value in _RARITY_OPTIONS:
            self._guided_rarity_combo.addItem(label, value)
        self._guided_rarity_combo.currentTextChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Rarity:", self._guided_rarity_combo)

        self._guided_type_combo = QComboBox()
        for label, value in _TYPE_OPTIONS:
            self._guided_type_combo.addItem(label, value)
        self._guided_type_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Card Type:", self._guided_type_combo)

        self._guided_color_combo = QComboBox()
        for label, value in _COLOR_OPTIONS:
            self._guided_color_combo.addItem(label, value)
        self._guided_color_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Color:", self._guided_color_combo)

        self._guided_stage_combo = QComboBox()
        for label, value in _STAGE_OPTIONS:
            self._guided_stage_combo.addItem(label, value)
        self._guided_stage_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Stage:", self._guided_stage_combo)

        hp_wrap = QWidget()
        hp_row = QHBoxLayout(hp_wrap)
        hp_row.setContentsMargins(0, 0, 0, 0)
        self._guided_hp_op_combo = QComboBox()
        for label, value in _NUMERIC_OPERATORS:
            self._guided_hp_op_combo.addItem(label, value)
        self._guided_hp_op_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        hp_row.addWidget(self._guided_hp_op_combo)
        self._guided_hp_value_edit = QLineEdit()
        self._guided_hp_value_edit.setPlaceholderText("e.g. 120")
        self._guided_hp_value_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        hp_row.addWidget(self._guided_hp_value_edit, stretch=1)
        guided_layout.addRow("HP:", hp_wrap)

        self._guided_weak_combo = QComboBox()
        for label, value in _COLOR_OPTIONS:
            self._guided_weak_combo.addItem(label, value)
        self._guided_weak_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Weakness:", self._guided_weak_combo)

        self._guided_resist_combo = QComboBox()
        for label, value in _COLOR_OPTIONS:
            self._guided_resist_combo.addItem(label, value)
        self._guided_resist_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Resistance:", self._guided_resist_combo)

        retreat_wrap = QWidget()
        retreat_row = QHBoxLayout(retreat_wrap)
        retreat_row.setContentsMargins(0, 0, 0, 0)
        self._guided_retreat_op_combo = QComboBox()
        for label, value in _NUMERIC_OPERATORS:
            self._guided_retreat_op_combo.addItem(label, value)
        self._guided_retreat_op_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        retreat_row.addWidget(self._guided_retreat_op_combo)
        self._guided_retreat_value_edit = QLineEdit()
        self._guided_retreat_value_edit.setPlaceholderText("e.g. 2")
        self._guided_retreat_value_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        retreat_row.addWidget(self._guided_retreat_value_edit, stretch=1)
        guided_layout.addRow("Retreat Cost:", retreat_wrap)

        self._guided_is_combo = QComboBox()
        self._guided_is_combo.setEditable(True)
        for label, value in _IS_OPTIONS:
            self._guided_is_combo.addItem(label, value)
        self._guided_is_combo.currentTextChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("is:", self._guided_is_combo)

        self._guided_has_combo = QComboBox()
        self._guided_has_combo.setEditable(True)
        for label, value in _HAS_OPTIONS:
            self._guided_has_combo.addItem(label, value)
        self._guided_has_combo.currentTextChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("has:", self._guided_has_combo)

        self._guided_format_combo = QComboBox()
        self._guided_format_combo.setEditable(True)
        for label, value in _FORMAT_OPTIONS:
            self._guided_format_combo.addItem(label, value)
        self._guided_format_combo.currentTextChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Format:", self._guided_format_combo)

        self._guided_mark_combo = QComboBox()
        for label, value in _MARK_OPTIONS:
            self._guided_mark_combo.addItem(label, value)
        self._guided_mark_combo.currentIndexChanged.connect(
            lambda _idx: self._update_guided_query_preview()
        )
        guided_layout.addRow("Regulation Mark:", self._guided_mark_combo)

        self._guided_print_type_combo = QComboBox()
        self._guided_print_type_combo.setEditable(True)
        for label, value in _PRINT_TYPE_OPTIONS:
            self._guided_print_type_combo.addItem(label, value)
        self._guided_print_type_combo.currentTextChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Print Type:", self._guided_print_type_combo)

        self._guided_number_edit = QLineEdit()
        self._guided_number_edit.setPlaceholderText("e.g. 95")
        self._guided_number_edit.textChanged.connect(
            self._update_guided_query_preview
        )
        guided_layout.addRow("Card number:", self._guided_number_edit)

        self._guided_query_preview = QLineEdit()
        self._guided_query_preview.setReadOnly(True)
        self._guided_query_preview.setPlaceholderText(
            "Generated query"
        )
        guided_layout.addRow("Generated query:", self._guided_query_preview)

        guided_btn_wrap = QWidget()
        guided_btn_row = QHBoxLayout(guided_btn_wrap)
        guided_btn_row.setContentsMargins(0, 0, 0, 0)
        self._ex_preset_btn = QPushButton("Preset: EX era")
        self._ex_preset_btn.clicked.connect(self._apply_ex_era_preset)
        guided_btn_row.addWidget(self._ex_preset_btn)
        self._copy_query_btn = QPushButton("Copy to manual query")
        self._copy_query_btn.clicked.connect(self._copy_guided_query_to_manual)
        guided_btn_row.addWidget(self._copy_query_btn)
        guided_btn_row.addStretch()
        guided_layout.addRow("", guided_btn_wrap)

        sl.addWidget(self._guided_group)

        self._set_filter_edit = QLineEdit()
        self._set_filter_edit.setPlaceholderText("Optional provider set filter")
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
        self._validate_label.setWordWrap(True)
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

        tmpl_row = QHBoxLayout()
        self._template_edit = QLineEdit()
        self._template_edit.setPlaceholderText(
            "e.g. {setId}/{number}_{name}.{fmt}"
        )
        self._template_edit.textChanged.connect(self._update_preview)
        tmpl_row.addWidget(self._template_edit, stretch=1)
        out_layout.addRow("Folder template:", tmpl_row)
        tmpl_help = QLabel(
            "Tokens: {set}, {setId}, {number}, {name}, {basicType}, {specificType}, {rarity}, {fmt}"
        )
        tmpl_help.setStyleSheet("color: #888; font-size: 11px;")
        out_layout.addRow("", tmpl_help)

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
        self._build_btn.setProperty("role", "primary")
        self._build_btn.setMinimumHeight(40)
        self._build_btn.clicked.connect(self._build_queue)
        root.addWidget(self._build_btn)

        self._update_guided_query_preview()
        self._sync_search_mode(self._guided_mode_cb.isChecked())

        root.addStretch()

    # ------------------------------------------------------------------
    # Slot helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_query_part(value: str) -> str:
        return " ".join(value.strip().split())

    @classmethod
    def _format_query_token(cls, field: str, value: str) -> str:
        cleaned = cls._normalize_query_part(value)
        if not cleaned:
            return ""
        if any(ch.isspace() for ch in cleaned):
            cleaned = f'"{cleaned}"'
        return f"{field}:{cleaned}"

    @staticmethod
    def _slug_query_value(value: str) -> str:
        lowered = value.strip().lower()
        if not lowered:
            return ""
        return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        data = combo.currentData()
        if isinstance(data, str) and data:
            return data
        text = combo.currentText().strip()
        if not text:
            return ""
        if text.lower().startswith("any "):
            return ""
        return text

    @staticmethod
    def _split_filter_values(value: str) -> list[str]:
        return [v for v in re.split(r"[,\s]+", value.strip()) if v]

    def _build_guided_query(self) -> str:
        parts: list[str] = []

        name_term = self._normalize_query_part(self._guided_name_edit.text())
        if name_term:
            parts.append(name_term)

        text_term = self._normalize_query_part(self._guided_text_edit.text())
        if text_term:
            if self._guided_text_exact_cb.isChecked():
                safe_text = text_term.replace('"', "")
                parts.append(f'text:"{safe_text}"')
            else:
                parts.append(self._format_query_token("text", text_term))

        exclude_words = self._split_filter_values(self._guided_exclude_edit.text())
        parts.extend(f"-{word}" for word in exclude_words)

        set_slug = self._slug_query_value(self._guided_set_edit.text())
        if set_slug:
            parts.append(self._format_query_token("set", set_slug))

        series_slug = self._slug_query_value(
            self._combo_value(self._guided_series_combo)
        )
        if series_slug:
            parts.append(self._format_query_token("series", series_slug))

        collection_slug = self._slug_query_value(
            self._combo_value(self._guided_collection_combo)
        )
        if collection_slug:
            parts.append(self._format_query_token("collection", collection_slug))

        artist_slug = self._slug_query_value(self._guided_artist_edit.text())
        if artist_slug:
            parts.append(self._format_query_token("@", artist_slug))

        rarity_slug = self._slug_query_value(
            self._combo_value(self._guided_rarity_combo)
        )
        if rarity_slug:
            parts.append(self._format_query_token("rarity", rarity_slug))

        card_type = self._slug_query_value(self._combo_value(self._guided_type_combo))
        if card_type:
            parts.append(self._format_query_token("type", card_type))

        color = self._slug_query_value(self._combo_value(self._guided_color_combo))
        if color:
            parts.append(self._format_query_token("color", color))

        stage = self._slug_query_value(self._combo_value(self._guided_stage_combo))
        if stage:
            parts.append(self._format_query_token("stage", stage))

        hp_value = self._normalize_query_part(self._guided_hp_value_edit.text())
        if hp_value:
            hp_op = self._guided_hp_op_combo.currentData() or "="
            parts.append(f"hp{hp_op}{hp_value}")

        weakness = self._slug_query_value(self._combo_value(self._guided_weak_combo))
        if weakness:
            parts.append(self._format_query_token("weak", weakness))

        resistance = self._slug_query_value(
            self._combo_value(self._guided_resist_combo)
        )
        if resistance:
            parts.append(self._format_query_token("resist", resistance))

        retreat_value = self._normalize_query_part(
            self._guided_retreat_value_edit.text()
        )
        if retreat_value:
            retreat_op = self._guided_retreat_op_combo.currentData() or "="
            parts.append(f"rc{retreat_op}{retreat_value}")

        is_values = self._split_filter_values(self._combo_value(self._guided_is_combo))
        for value in is_values:
            slug = self._slug_query_value(value)
            if slug:
                parts.append(self._format_query_token("is", slug))

        has_values = self._split_filter_values(
            self._combo_value(self._guided_has_combo)
        )
        for value in has_values:
            slug = self._slug_query_value(value)
            if slug:
                parts.append(self._format_query_token("has", slug))

        format_slug = self._slug_query_value(
            self._combo_value(self._guided_format_combo)
        )
        if format_slug:
            parts.append(self._format_query_token("format", format_slug))

        mark_slug = self._slug_query_value(self._combo_value(self._guided_mark_combo))
        if mark_slug:
            parts.append(self._format_query_token("mark", mark_slug))

        print_type_slug = self._slug_query_value(
            self._combo_value(self._guided_print_type_combo)
        )
        if print_type_slug:
            parts.append(self._format_query_token("print-type", print_type_slug))

        number = self._normalize_query_part(self._guided_number_edit.text())
        if number:
            parts.append(self._format_query_token("number", number))

        return " ".join(parts)

    def _update_guided_query_preview(self) -> None:
        query = self._build_guided_query()
        self._guided_query_preview.setText(query)
        if self._guided_mode_cb.isChecked():
            self._search_query.setText(query)

    def _sync_search_mode(self, checked: bool) -> None:
        self._guided_group.setEnabled(checked)
        self._search_query.setEnabled(not checked)
        if checked:
            self._update_guided_query_preview()

    def _copy_guided_query_to_manual(self) -> None:
        query = self._build_guided_query()
        if query:
            self._search_query.setText(query)
            self._guided_mode_cb.setChecked(False)
            self._validate_label.setText(
                "Guided query copied to manual query field."
            )

    def _apply_ex_era_preset(self) -> None:
        self._guided_mode_cb.setChecked(True)
        self._guided_name_edit.clear()
        self._guided_text_edit.clear()
        self._guided_text_exact_cb.setChecked(False)
        self._guided_exclude_edit.clear()
        self._guided_set_edit.clear()
        self._guided_collection_combo.setCurrentIndex(0)
        self._guided_artist_edit.clear()
        self._guided_rarity_combo.setCurrentIndex(0)
        self._guided_type_combo.setCurrentIndex(0)
        self._guided_color_combo.setCurrentIndex(0)
        self._guided_stage_combo.setCurrentIndex(0)
        self._guided_hp_op_combo.setCurrentIndex(0)
        self._guided_hp_value_edit.clear()
        self._guided_weak_combo.setCurrentIndex(0)
        self._guided_resist_combo.setCurrentIndex(0)
        self._guided_retreat_op_combo.setCurrentIndex(0)
        self._guided_retreat_value_edit.clear()
        self._guided_is_combo.setCurrentIndex(0)
        self._guided_has_combo.setCurrentIndex(0)
        self._guided_format_combo.setCurrentIndex(0)
        self._guided_mark_combo.setCurrentIndex(0)
        self._guided_print_type_combo.setCurrentIndex(0)
        self._guided_number_edit.clear()
        index = self._guided_series_combo.findData("ex")
        if index >= 0:
            self._guided_series_combo.setCurrentIndex(index)
        self._update_guided_query_preview()
        self._validate_label.setText(
            "Preset applied: EX era (series:ex)."
        )

    def _effective_search_query(self) -> str:
        if self._guided_mode_cb.isChecked():
            return self._build_guided_query().strip()
        return self._search_query.text().strip()

    def _rate_changed(self, value: int) -> None:
        self._rate_label.setText(f"{value / 10:.1f} req/s")

    def _update_preview(self) -> None:
        fmt = self._fmt_combo.currentText()
        tmpl = self._template_edit.text().strip()
        if tmpl:
            preview = tmpl.replace("{set}", "SetName").replace("{setId}", "sv4")
            preview = preview.replace("{number}", "001").replace("{name}", "CardName")
            preview = preview.replace("{basicType}", "Pokemon").replace("{specificType}", "stage-1")
            preview = preview.replace("{rarity}", "rare").replace("{fmt}", fmt)
            self._naming_preview.setText(f"…/{preview}")
        else:
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
            q = self._effective_search_query()
            if not q:
                self._validate_label.setText(
                    "Add at least one guided filter or enter a manual query."
                )
                return
            hint = ""
            q_lower = q.lower()
            if "serie:" in q_lower and "series:" not in q_lower:
                hint = " Tip: use `series:` (with s)."
            mode = "Guided" if self._guided_mode_cb.isChecked() else "Manual"
            self._validate_label.setText(f"{mode} query: '{q}'.{hint}")
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
            folder_template=self._template_edit.text().strip(),
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
            query = self._effective_search_query()
            if not query:
                self._validate_label.setText(
                    "⚠️ Add guided filters or enter a manual search query"
                )
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
        hint = ""
        lowered = message.lower()
        if "all 3 attempts" in lowered and "pkmncards.com" in lowered:
            hint = (
                " Tip: this is usually timeout or provider blocking. "
                "Try rate limit 1.0 req/s and timeout 60s."
            )
        elif "429" in lowered:
            hint = " Tip: lower rate limit to 0.5-1.0 req/s."
        self._validate_label.setText(f"❌ {message}{hint}")

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
