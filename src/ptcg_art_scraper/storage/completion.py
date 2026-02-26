"""Set-completion detection: scan a local folder and determine which cards are present."""

from __future__ import annotations

import enum
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ptcg_art_scraper.models import CardAssetStub
from ptcg_art_scraper.utils.slugify import slugify

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class CardStatus(enum.Enum):
    DOWNLOADED = "Downloaded"
    MISSING = "Missing"
    UNKNOWN = "Unknown"


@dataclass
class SetCardEntry:
    """One row in the set-completion table."""

    stub: CardAssetStub
    status: CardStatus = CardStatus.MISSING
    output_path: str = ""


def _match_key(provider: str, set_id: str, number: str, name: str) -> str:
    """Build a stable match key.

    Primary key: ``(provider, set_id, number)`` when *number* is available.
    Fallback: ``(provider, set_id, slug(name))``.
    """
    if number:
        return f"{provider}|{set_id}|{number}"
    return f"{provider}|{set_id}|{slugify(name)}"


def _scan_sidecars(folder: Path) -> dict[str, str]:
    """Read all sidecar JSON files in *folder* (recursively) and return
    a mapping from match-key → image path.
    """
    index: dict[str, str] = {}
    if not folder.is_dir():
        return index
    for json_path in folder.rglob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        provider = data.get("provider", "")
        set_id = data.get("setId", "")
        number = data.get("number", "")
        name = data.get("name", "")
        if not provider or not set_id:
            continue
        key = _match_key(provider, set_id, number, name)
        # Image path is typically the JSON path with a different extension
        img_path = data.get("normalized_output_path", "")
        if not img_path:
            for ext in (".png", ".jpg"):
                candidate = json_path.with_suffix(ext)
                if candidate.exists():
                    img_path = str(candidate)
                    break
        index[key] = img_path
    return index


def _scan_filenames(folder: Path, set_id: str, provider: str) -> dict[str, str]:
    """Infer downloaded cards from filenames when sidecars are missing.

    Expected pattern: ``{number}_{name_slug}.{ext}`` inside a set folder.
    """
    index: dict[str, str] = {}
    if not folder.is_dir():
        return index
    set_slug = slugify(set_id)
    for img in folder.rglob("*"):
        if img.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        # Check if this image is in the set's subfolder
        relative = img.relative_to(folder)
        parts = relative.parts
        if len(parts) >= 2 and slugify(parts[-2]) == set_slug:
            stem = img.stem
            m = re.match(r"^(\d+)_(.+)$", stem)
            if m:
                number = m.group(1)
                key = _match_key(provider, set_id, number, "")
                index[key] = str(img)
            else:
                # No number prefix – use the whole stem as name
                key = _match_key(provider, set_id, "", stem)
                index[key] = str(img)
    return index


def detect_completion(
    stubs: list[CardAssetStub],
    output_folder: Path,
    *,
    scan_local: bool = True,
) -> list[SetCardEntry]:
    """Compare *stubs* (all cards in the set) against what's on disk.

    Returns one :class:`SetCardEntry` per stub with status filled in.
    """
    entries: list[SetCardEntry] = []
    if not stubs:
        return entries

    provider = stubs[0].provider
    set_id = stubs[0].set_id

    if scan_local and output_folder.is_dir():
        sidecar_idx = _scan_sidecars(output_folder)
        filename_idx = _scan_filenames(output_folder, set_id, provider)
    else:
        sidecar_idx = {}
        filename_idx = {}

    name_fallback_used = False
    for stub in stubs:
        key = _match_key(stub.provider, stub.set_id, stub.number, stub.name)
        if key in sidecar_idx:
            entries.append(
                SetCardEntry(stub=stub, status=CardStatus.DOWNLOADED, output_path=sidecar_idx[key])
            )
        elif key in filename_idx:
            entries.append(
                SetCardEntry(
                    stub=stub, status=CardStatus.DOWNLOADED, output_path=filename_idx[key]
                )
            )
            if not stub.number:
                name_fallback_used = True
        else:
            entries.append(SetCardEntry(stub=stub, status=CardStatus.MISSING))

    if name_fallback_used:
        logger.warning(
            "Some cards in set %r matched by name slug only (no number available). "
            "Results may be less accurate.",
            set_id,
        )

    return entries
