"""Output path layout and naming conventions."""

from __future__ import annotations

import re
from pathlib import Path

from ptcg_art_scraper.models import CardAsset
from ptcg_art_scraper.utils.slugify import slugify

# Default template used when no custom template is provided.
DEFAULT_TEMPLATE = "{setId}/{number}_{name}.{fmt}"

# Tokens recognised by the template engine.
_TOKEN_RE = re.compile(r"\{(\w+)\}")


def _token_map(asset: CardAsset, fmt: str = "png") -> dict[str, str]:
    """Build a mapping from token names to slugified values."""
    return {
        "set": slugify(asset.set_name or "unknown-set"),
        "setId": slugify(asset.set_code or asset.set_name or "unknown-set"),
        "number": slugify(asset.number) if asset.number else "000",
        "name": slugify(asset.name or "card"),
        "basicType": slugify(asset.basic_type or "unknown"),
        "specificType": slugify(asset.specific_type or "none"),
        "rarity": slugify(asset.rarity or "unknown"),
        "fmt": fmt,
    }


def expand_template(template: str, asset: CardAsset, fmt: str = "png") -> str:
    """Substitute ``{token}`` placeholders in *template* using *asset* metadata.

    Unknown tokens are left unchanged.
    """
    tokens = _token_map(asset, fmt)

    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        return tokens.get(key, m.group(0))

    return _TOKEN_RE.sub(_replace, template)


def template_output_path(
    base_dir: Path,
    asset: CardAsset,
    fmt: str = "png",
    template: str = "",
) -> Path:
    """Build an output path using a user-defined template.

    Falls back to :func:`card_output_path` behaviour when *template* is empty.
    """
    if not template:
        return card_output_path(base_dir, asset, fmt=fmt)
    expanded = expand_template(template, asset, fmt=fmt)
    return base_dir / expanded


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
