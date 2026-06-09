"""Filesystem layout and sidecar persistence services."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from ptcg_art_scraper.core.models import CardAsset, SidecarMetadata
from ptcg_art_scraper.utils.slugify import slugify

DEFAULT_TEMPLATE = "{setId}/{number}_{name}.{fmt}"
_TOKEN_RE = re.compile(r"\{(\w+)\}")


def _token_map(asset: CardAsset, fmt: str = "png") -> dict[str, str]:
    return {
        "set": slugify(asset.set_name or asset.set_code or "unknown-set"),
        "setId": slugify(asset.set_code or asset.set_name or "unknown-set"),
        "number": slugify(asset.number) if asset.number else "000",
        "name": slugify(asset.name or "card"),
        "basicType": slugify(asset.basic_type or "unknown"),
        "specificType": slugify(asset.specific_type or "none"),
        "rarity": slugify(asset.rarity or "unknown"),
        "fmt": fmt,
    }


def expand_template(template: str, asset: CardAsset, fmt: str = "png") -> str:
    tokens = _token_map(asset, fmt)

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return tokens.get(key, match.group(0))

    return _TOKEN_RE.sub(_replace, template)


def card_output_path(base_dir: Path, asset: CardAsset, fmt: str = "png") -> Path:
    set_slug = slugify(asset.set_code or asset.set_name or "unknown-set")
    name_slug = slugify(asset.name or "card")
    number = slugify(asset.number) if asset.number else "000"
    return base_dir / set_slug / f"{number}_{name_slug}.{fmt}"


def template_output_path(base_dir: Path, asset: CardAsset, fmt: str = "png", template: str = "") -> Path:
    if not template:
        return card_output_path(base_dir, asset, fmt=fmt)
    return base_dir / expand_template(template, asset, fmt=fmt)


def sidecar_path(image_path: Path) -> Path:
    return image_path.with_suffix(".json")


def save_sidecar(meta: SidecarMetadata, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")


def load_sidecar(path: Path) -> SidecarMetadata | None:
    if not path.is_file():
        return None
    try:
        return SidecarMetadata(**json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None
