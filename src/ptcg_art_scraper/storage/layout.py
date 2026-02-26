"""Output path layout and naming conventions."""

from __future__ import annotations

import os
from typing import Optional

from ptcg_art_scraper.utils.slugify import slugify


def card_stem(
    name: str,
    number: Optional[str],
    set_name: str,
    set_code: Optional[str],
) -> tuple[str, str]:
    """Return ``(directory_name, file_stem)`` for a card.

    ``directory_name`` – set-level directory (e.g. ``sv4-obsidian-flames``).
    ``file_stem``      – ``{number}_{name_slug}`` (e.g. ``100_charizard-ex``).
    """
    dir_part = slugify(set_code) if set_code else slugify(set_name)
    name_slug = slugify(name)
    if number:
        num_slug = slugify(number)
        stem = f"{num_slug}_{name_slug}"
    else:
        stem = name_slug
    return dir_part, stem


def output_paths(
    out_dir: str,
    name: str,
    number: Optional[str],
    set_name: str,
    set_code: Optional[str],
    ext: str = ".png",
) -> tuple[str, str]:
    """Return ``(image_path, json_path)`` under *out_dir*."""
    dir_part, stem = card_stem(name, number, set_name, set_code)
    folder = os.path.join(out_dir, dir_part)
    os.makedirs(folder, exist_ok=True)
    img_path = os.path.join(folder, stem + ext)
    json_path = os.path.join(folder, stem + ".json")
    return img_path, json_path
