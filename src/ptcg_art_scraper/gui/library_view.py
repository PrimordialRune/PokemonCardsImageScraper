"""Library page – browse and inspect previously downloaded card images."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Image extensions recognised by the library scanner.
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class LibraryPage(QWidget):
    """Browse downloaded card artwork on disk."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._root_path: Path | None = None
        self._files: list[Path] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        # --- Folder picker ---
        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select a library folder…")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse_folder)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        folder_row.addWidget(self._folder_edit, stretch=1)
        folder_row.addWidget(self._browse_btn)
        folder_row.addWidget(self._refresh_btn)
        root.addLayout(folder_row)

        # --- Splitter: tree + table ---
        splitter = QSplitter()

        # Left: folder tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Folders")
        self._tree.itemClicked.connect(self._on_tree_click)
        splitter.addWidget(self._tree)

        # Right: file table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Filename", "Size", "Set", "Status"]
        )
        header = self._table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.currentCellChanged.connect(self._on_selection)
        splitter.addWidget(self._table)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

        # --- Detail panel ---
        detail_group = QGroupBox("Details")
        detail_layout = QVBoxLayout(detail_group)
        self._detail_label = QLabel("Select an image to see details.")
        self._detail_label.setWordWrap(True)
        detail_layout.addWidget(self._detail_label)

        btn_row = QHBoxLayout()
        self._open_image_btn = QPushButton("Open Image")
        self._open_image_btn.setEnabled(False)
        self._open_image_btn.clicked.connect(self._open_image)
        btn_row.addWidget(self._open_image_btn)

        self._open_folder_btn = QPushButton("Open Folder")
        self._open_folder_btn.setEnabled(False)
        self._open_folder_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(self._open_folder_btn)
        btn_row.addStretch()
        detail_layout.addLayout(btn_row)

        root.addWidget(detail_group)

    # ------------------------------------------------------------------
    # Folder browsing
    # ------------------------------------------------------------------

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select library folder"
        )
        if folder:
            self._folder_edit.setText(folder)
            self._root_path = Path(folder)
            self._refresh()

    def _refresh(self) -> None:
        path_text = self._folder_edit.text().strip()
        if not path_text:
            return
        self._root_path = Path(path_text)
        if not self._root_path.is_dir():
            return
        self._build_tree()
        self._load_folder(self._root_path)

    def _build_tree(self) -> None:
        self._tree.clear()
        if self._root_path is None:
            return
        root_item = QTreeWidgetItem(
            self._tree, [self._root_path.name]
        )
        root_item.setData(0, 256, str(self._root_path))
        self._add_subdirs(root_item, self._root_path, depth=0)
        self._tree.expandAll()

    def _add_subdirs(
        self,
        parent: QTreeWidgetItem,
        folder: Path,
        depth: int,
    ) -> None:
        if depth > 3:
            return
        try:
            dirs = sorted(
                d for d in folder.iterdir() if d.is_dir()
            )
        except PermissionError:
            return
        for d in dirs:
            child = QTreeWidgetItem(parent, [d.name])
            child.setData(0, 256, str(d))
            self._add_subdirs(child, d, depth + 1)

    def _on_tree_click(self, item: QTreeWidgetItem, _col: int) -> None:
        path_str = item.data(0, 256)
        if path_str:
            self._load_folder(Path(str(path_str)))

    # ------------------------------------------------------------------
    # File table
    # ------------------------------------------------------------------

    def _load_folder(self, folder: Path) -> None:
        self._files = sorted(
            f
            for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTS
        )
        self._table.setRowCount(len(self._files))
        for row, fp in enumerate(self._files):
            self._table.setItem(
                row, 0, QTableWidgetItem(fp.name)
            )
            size_kb = fp.stat().st_size / 1024
            self._table.setItem(
                row, 1, QTableWidgetItem(f"{size_kb:.1f} KB")
            )
            meta = self._load_sidecar(fp)
            set_name = meta.get("set_name", fp.parent.name)
            status = "✅" if meta else "—"
            self._table.setItem(
                row, 2, QTableWidgetItem(str(set_name))
            )
            self._table.setItem(
                row, 3, QTableWidgetItem(status)
            )
        self._detail_label.setText(
            f"{len(self._files)} image(s) in {folder.name}"
        )

    @staticmethod
    def _load_sidecar(image_path: Path) -> dict[str, object]:
        """Load sidecar JSON if it exists next to the image."""
        sidecar = image_path.with_suffix(".json")
        if sidecar.is_file():
            try:
                return json.loads(  # type: ignore[return-value]
                    sidecar.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _on_selection(
        self, row: int, _col: int, _prev_row: int, _prev_col: int
    ) -> None:
        if row < 0 or row >= len(self._files):
            self._open_image_btn.setEnabled(False)
            self._open_folder_btn.setEnabled(False)
            return
        fp = self._files[row]
        meta = self._load_sidecar(fp)
        dims = meta.get("normalized_size", "unknown")
        info = f"Path: {fp}\nSize: {fp.stat().st_size / 1024:.1f} KB"
        if isinstance(dims, list) and len(dims) == 2:
            info += f"\nDimensions: {dims[0]}×{dims[1]}"
        self._detail_label.setText(info)
        self._open_image_btn.setEnabled(True)
        self._open_folder_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_image(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._files):
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._files[row]))
            )

    def _open_folder(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._files):
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._files[row].parent))
            )
