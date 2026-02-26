"""Image normalization pipeline.

Every card image is standardized to 750 × 1050 pixels, 300 DPI (2.5 × 3.5 in).
"""

from __future__ import annotations

import hashlib
import io
from typing import Literal

from PIL import Image

TARGET_WIDTH = 750
TARGET_HEIGHT = 1050
TARGET_DPI = 300
TARGET_RATIO = TARGET_WIDTH / TARGET_HEIGHT  # ≈ 0.7143


def _cover_crop(img: Image.Image) -> Image.Image:
    """Scale-to-fill then center-crop to TARGET_WIDTH × TARGET_HEIGHT."""
    src_w, src_h = img.size
    src_ratio = src_w / src_h

    if src_ratio > TARGET_RATIO:
        # Source is wider → scale height to fit, crop width
        new_h = TARGET_HEIGHT
        new_w = round(src_w * TARGET_HEIGHT / src_h)
    else:
        # Source is taller (or equal) → scale width to fit, crop height
        new_w = TARGET_WIDTH
        new_h = round(src_h * TARGET_WIDTH / src_w)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - TARGET_WIDTH) // 2
    top = (new_h - TARGET_HEIGHT) // 2
    img = img.crop((left, top, left + TARGET_WIDTH, top + TARGET_HEIGHT))
    return img


def normalize_image(
    raw_bytes: bytes,
    output_path: str,
    fmt: Literal["png", "jpg"] = "png",
) -> tuple[tuple[int, int], str, str]:
    """Normalize *raw_bytes* and save to *output_path*.

    Returns ``(original_size, sha256_original, sha256_normalized)``.
    """
    sha256_original = hashlib.sha256(raw_bytes).hexdigest()

    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    original_size = img.size

    img = _cover_crop(img)

    save_kwargs: dict[str, object] = {"dpi": (TARGET_DPI, TARGET_DPI)}
    if fmt == "jpg":
        save_kwargs["quality"] = 95
        save_kwargs["subsampling"] = 0  # 4:4:4
        img.save(output_path, format="JPEG", **save_kwargs)  # type: ignore[arg-type]
    else:
        img.save(output_path, format="PNG", **save_kwargs)  # type: ignore[arg-type]

    with open(output_path, "rb") as fh:
        sha256_normalized = hashlib.sha256(fh.read()).hexdigest()

    return original_size, sha256_original, sha256_normalized


def verify_image(path: str) -> list[str]:
    """Return a list of problems (empty == OK)."""
    problems: list[str] = []
    try:
        img = Image.open(path)
        img.load()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"corrupt or unreadable: {exc}")
        return problems

    if img.size != (TARGET_WIDTH, TARGET_HEIGHT):
        problems.append(f"size {img.size} != ({TARGET_WIDTH}, {TARGET_HEIGHT})")

    dpi = img.info.get("dpi")
    if dpi is None:
        problems.append("missing DPI metadata")
    elif not (
        abs(dpi[0] - TARGET_DPI) < 0.5 and abs(dpi[1] - TARGET_DPI) < 0.5
    ):
        problems.append(f"DPI {dpi} != ({TARGET_DPI}, {TARGET_DPI})")

    return problems
