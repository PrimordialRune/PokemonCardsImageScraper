"""Image normalization and verification services."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from PIL import Image

NORM_WIDTH = 750
NORM_HEIGHT = 1050
NORM_DPI = 300
JPEG_QUALITY = 95


def normalize_image(raw_bytes: bytes, output_path: Path, fmt: str = "png") -> dict[str, Any]:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    orig_w, orig_h = img.size
    sha256_original = hashlib.sha256(raw_bytes).hexdigest()

    target_ratio = NORM_WIDTH / NORM_HEIGHT
    source_ratio = orig_w / orig_h
    if source_ratio > target_ratio:
        new_h = NORM_HEIGHT
        new_w = round(orig_w * (NORM_HEIGHT / orig_h))
    else:
        new_w = NORM_WIDTH
        new_h = round(orig_h * (NORM_WIDTH / orig_w))

    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - NORM_WIDTH) // 2
    top = (new_h - NORM_HEIGHT) // 2
    img = img.crop((left, top, left + NORM_WIDTH, top + NORM_HEIGHT))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict[str, Any] = {"dpi": (NORM_DPI, NORM_DPI)}
    normalized_fmt = fmt.lower()
    if normalized_fmt in ("jpg", "jpeg"):
        save_kwargs["quality"] = JPEG_QUALITY
        save_kwargs["subsampling"] = 0
        pil_fmt = "JPEG"
        normalized_fmt = "jpg"
    else:
        pil_fmt = "PNG"
        normalized_fmt = "png"
    img.save(str(output_path), pil_fmt, **save_kwargs)

    sha256_normalized = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "original_width": orig_w,
        "original_height": orig_h,
        "width": NORM_WIDTH,
        "height": NORM_HEIGHT,
        "dpi": NORM_DPI,
        "sha256_original": sha256_original,
        "sha256_normalized": sha256_normalized,
        "format": normalized_fmt,
    }


def verify_image(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        img = Image.open(path)
    except Exception as exc:
        return [f"cannot open: {exc}"]

    if img.size != (NORM_WIDTH, NORM_HEIGHT):
        problems.append(f"size {img.size[0]}x{img.size[1]}, expected {NORM_WIDTH}x{NORM_HEIGHT}")

    dpi = img.info.get("dpi")
    if dpi is None:
        problems.append("missing DPI metadata")
    else:
        rx, ry = dpi
        if round(rx) != NORM_DPI or round(ry) != NORM_DPI:
            problems.append(f"DPI {rx}x{ry}, expected {NORM_DPI}x{NORM_DPI}")
    return problems
