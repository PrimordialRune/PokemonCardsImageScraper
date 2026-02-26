"""Sidecar metadata persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ptcg_art_scraper.models import SidecarMetadata


def save_sidecar(meta: SidecarMetadata, path: Path) -> None:
    """Write sidecar JSON to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")


def load_sidecar(path: Path) -> SidecarMetadata | None:
    """Load sidecar JSON from *path*, or ``None`` if missing/invalid."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SidecarMetadata(**data)
    except Exception:
        return None
