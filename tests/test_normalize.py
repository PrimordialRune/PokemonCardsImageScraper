"""Tests for image normalization pipeline."""

import os
import tempfile

from PIL import Image

from ptcg_art_scraper.image.normalize import (
    TARGET_DPI,
    TARGET_HEIGHT,
    TARGET_WIDTH,
    normalize_image,
    verify_image,
)


def _make_image(width: int, height: int, color: str = "red", fmt: str = "PNG") -> bytes:
    """Create a synthetic in-memory image."""
    import io

    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestNormalize:
    def test_exact_ratio(self):
        raw = _make_image(750, 1050)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            orig_size, sha_o, sha_n = normalize_image(raw, path, fmt="png")
            assert orig_size == (750, 1050)
            img = Image.open(path)
            assert img.size == (TARGET_WIDTH, TARGET_HEIGHT)
        finally:
            os.unlink(path)

    def test_wider_image_center_cropped(self):
        # 1500x1050 → wider than 750:1050 ratio → crop width
        raw = _make_image(1500, 1050)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            normalize_image(raw, path, fmt="png")
            img = Image.open(path)
            assert img.size == (TARGET_WIDTH, TARGET_HEIGHT)
        finally:
            os.unlink(path)

    def test_taller_image_center_cropped(self):
        # 750x2100 → taller than standard → crop height
        raw = _make_image(750, 2100)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            normalize_image(raw, path, fmt="png")
            img = Image.open(path)
            assert img.size == (TARGET_WIDTH, TARGET_HEIGHT)
        finally:
            os.unlink(path)

    def test_small_image_upscaled(self):
        raw = _make_image(375, 525)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            normalize_image(raw, path, fmt="png")
            img = Image.open(path)
            assert img.size == (TARGET_WIDTH, TARGET_HEIGHT)
        finally:
            os.unlink(path)

    def test_odd_ratio(self):
        # Square image → very different ratio
        raw = _make_image(500, 500)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            normalize_image(raw, path, fmt="png")
            img = Image.open(path)
            assert img.size == (TARGET_WIDTH, TARGET_HEIGHT)
        finally:
            os.unlink(path)

    def test_dpi_png(self):
        raw = _make_image(750, 1050)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            normalize_image(raw, path, fmt="png")
            img = Image.open(path)
            dpi = img.info.get("dpi")
            assert dpi is not None
            # PNG DPI round-trips through pHYs (pixels/meter) causing rounding
            assert abs(dpi[0] - TARGET_DPI) < 0.5
            assert abs(dpi[1] - TARGET_DPI) < 0.5
        finally:
            os.unlink(path)

    def test_dpi_jpg(self):
        raw = _make_image(750, 1050)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name
        try:
            normalize_image(raw, path, fmt="jpg")
            img = Image.open(path)
            dpi = img.info.get("dpi")
            assert dpi is not None
            # JPEG DPI may be stored as integer tuple
            assert (int(dpi[0]), int(dpi[1])) == (TARGET_DPI, TARGET_DPI)
        finally:
            os.unlink(path)

    def test_sha256_hashes_differ(self):
        raw = _make_image(800, 1100)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            _, sha_o, sha_n = normalize_image(raw, path, fmt="png")
            assert sha_o  # non-empty
            assert sha_n  # non-empty
            # original and normalized should differ (different sizes)
            assert sha_o != sha_n
        finally:
            os.unlink(path)


class TestVerify:
    def test_good_image(self):
        raw = _make_image(750, 1050)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            normalize_image(raw, path, fmt="png")
            problems = verify_image(path)
            assert problems == []
        finally:
            os.unlink(path)

    def test_wrong_size(self):

        img = Image.new("RGB", (500, 500))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        img.save(path, dpi=(300, 300))
        try:
            problems = verify_image(path)
            assert any("size" in p for p in problems)
        finally:
            os.unlink(path)

    def test_missing_dpi(self):

        img = Image.new("RGB", (750, 1050))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        # Save without DPI
        img.save(path, format="PNG")
        try:
            problems = verify_image(path)
            assert any("DPI" in p or "dpi" in p.lower() for p in problems)
        finally:
            os.unlink(path)

    def test_corrupt_file(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"not an image")
            path = f.name
        try:
            problems = verify_image(path)
            assert any("corrupt" in p or "unreadable" in p for p in problems)
        finally:
            os.unlink(path)
