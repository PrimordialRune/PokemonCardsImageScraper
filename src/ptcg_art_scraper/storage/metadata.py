"""Sidecar JSON metadata for downloaded cards."""

from __future__ import annotations

import json
from typing import Any


def write_metadata(json_path: str, data: dict[str, Any]) -> None:
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def read_metadata(json_path: str) -> dict[str, Any]:
    with open(json_path, encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def build_metadata(
    *,
    provider: str,
    source_page_url: str,
    source_image_url: str,
    fetched_at_utc: str,
    normalized_size: tuple[int, int],
    dpi: int,
    original_size: tuple[int, int],
    sha256_original: str,
    sha256_normalized: str,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "source_page_url": source_page_url,
        "source_image_url": source_image_url,
        "fetched_at_utc": fetched_at_utc,
        "normalized_size": list(normalized_size),
        "dpi": dpi,
        "original_size": list(original_size),
        "sha256_original": sha256_original,
        "sha256_normalized": sha256_normalized,
    }
