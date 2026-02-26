"""Output path layout and naming conventions."""

from __future__ import annotations

from pathlib import Path

from ptcg_art_scraper.models import CardAsset
from ptcg_art_scraper.utils.slugify import slugify


def card_output_path(
    base_dir: Path,
    asset: CardAsset,
    fmt: str = "png",
) -> Path:
    """Build ``{set_slug}/{number}_{name_slug}.{fmt}`` under *base_dir*."""
    set_slug = slugify(asset.set_code or asset.set_name or "unknown-set")
    name_slug = slugify(asset.name or "card")
    number = slugify(asset.number) if asset.number else "000"
    filename = f"{number}_{name_slug}.{fmt}"
    return base_dir / set_slug / filename


def sidecar_path(image_path: Path) -> Path:
    """Return the JSON sidecar path for the given image."""
    return image_path.with_suffix(".json")
