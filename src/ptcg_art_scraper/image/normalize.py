"""Image normalization pipeline.

Every card image is standardized to **750 × 1050 px @ 300 DPI**
(print size 2.5 × 3.5 in).
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

NORM_WIDTH = 750
NORM_HEIGHT = 1050
NORM_DPI = 300
JPEG_QUALITY = 95


def normalize_image(
    raw_bytes: bytes,
    output_path: Path,
    fmt: str = "png",
) -> dict:
    """Normalize *raw_bytes* → 750×1050 @ 300 DPI and save to *output_path*.

    Uses **cover** behaviour: scale to fill then centre-crop.

    Returns a dict with sizing / hash metadata.
    """
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    orig_w, orig_h = img.size

    sha256_original = hashlib.sha256(raw_bytes).hexdigest()

    # --- cover-fit: scale so both dimensions are >= target, then centre-crop ---
    target_ratio = NORM_WIDTH / NORM_HEIGHT
    source_ratio = orig_w / orig_h

    if source_ratio > target_ratio:
        # Source is wider → scale by height, crop width
        new_h = NORM_HEIGHT
        new_w = round(orig_w * (NORM_HEIGHT / orig_h))
    else:
        # Source is taller → scale by width, crop height
        new_w = NORM_WIDTH
        new_h = round(orig_h * (NORM_WIDTH / orig_w))

    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - NORM_WIDTH) // 2
    top = (new_h - NORM_HEIGHT) // 2
    img = img.crop((left, top, left + NORM_WIDTH, top + NORM_HEIGHT))

    # --- save with DPI metadata ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict = {"dpi": (NORM_DPI, NORM_DPI)}
    if fmt.lower() in ("jpg", "jpeg"):
        save_kwargs["quality"] = JPEG_QUALITY
        save_kwargs["subsampling"] = 0
        pil_fmt = "JPEG"
    else:
        pil_fmt = "PNG"

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
        "format": fmt.lower(),
    }


def verify_image(path: Path) -> list[str]:
    """Return a list of problems found with *path*.  Empty = OK."""
    problems: list[str] = []
    try:
        img = Image.open(path)
    except Exception as exc:
        problems.append(f"cannot open: {exc}")
        return problems

    w, h = img.size
    if (w, h) != (NORM_WIDTH, NORM_HEIGHT):
        problems.append(f"size {w}x{h}, expected {NORM_WIDTH}x{NORM_HEIGHT}")

    dpi = img.info.get("dpi")
    if dpi is None:
        problems.append("missing DPI metadata")
    else:
        rx, ry = dpi
        if round(rx) != NORM_DPI or round(ry) != NORM_DPI:
            problems.append(f"DPI {rx}x{ry}, expected {NORM_DPI}x{NORM_DPI}")

    return problems
