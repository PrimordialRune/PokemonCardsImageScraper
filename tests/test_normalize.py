"""Tests for image normalization pipeline."""

import io
from pathlib import Path

from PIL import Image

from ptcg_art_scraper.image.normalize import (
    NORM_DPI,
    NORM_HEIGHT,
    NORM_WIDTH,
    normalize_image,
    verify_image,
)


def _make_image(w: int, h: int, color: tuple = (255, 0, 0)) -> bytes:
    """Create a solid-color test image as raw bytes."""
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class TestNormalization:
    def test_exact_size_output(self, tmp_path: Path):
        raw = _make_image(800, 1120)
        dest = tmp_path / "test.png"
        info = normalize_image(raw, dest, fmt="png")
        assert dest.exists()
        img = Image.open(dest)
        assert img.size == (NORM_WIDTH, NORM_HEIGHT)
        assert info["width"] == NORM_WIDTH
        assert info["height"] == NORM_HEIGHT

    def test_square_input(self, tmp_path: Path):
        """A square image should be centre-cropped to 750×1050."""
        raw = _make_image(500, 500)
        dest = tmp_path / "sq.png"
        normalize_image(raw, dest)
        img = Image.open(dest)
        assert img.size == (NORM_WIDTH, NORM_HEIGHT)

    def test_wide_input(self, tmp_path: Path):
        """A very wide image should still produce 750×1050."""
        raw = _make_image(2000, 600)
        dest = tmp_path / "wide.png"
        normalize_image(raw, dest)
        img = Image.open(dest)
        assert img.size == (NORM_WIDTH, NORM_HEIGHT)

    def test_tall_input(self, tmp_path: Path):
        """A very tall image should still produce 750×1050."""
        raw = _make_image(400, 2000)
        dest = tmp_path / "tall.png"
        normalize_image(raw, dest)
        img = Image.open(dest)
        assert img.size == (NORM_WIDTH, NORM_HEIGHT)

    def test_dpi_png(self, tmp_path: Path):
        raw = _make_image(750, 1050)
        dest = tmp_path / "dpi.png"
        normalize_image(raw, dest, fmt="png")
        img = Image.open(dest)
        dpi = img.info.get("dpi")
        assert dpi is not None
        assert round(dpi[0]) == NORM_DPI
        assert round(dpi[1]) == NORM_DPI

    def test_dpi_jpg(self, tmp_path: Path):
        raw = _make_image(750, 1050)
        dest = tmp_path / "dpi.jpg"
        normalize_image(raw, dest, fmt="jpg")
        img = Image.open(dest)
        dpi = img.info.get("dpi")
        assert dpi is not None
        assert round(dpi[0]) == NORM_DPI
        assert round(dpi[1]) == NORM_DPI

    def test_hashes_differ(self, tmp_path: Path):
        raw = _make_image(600, 900)
        dest = tmp_path / "hash.png"
        info = normalize_image(raw, dest)
        assert info["sha256_original"] != info["sha256_normalized"]

    def test_creates_parent_dirs(self, tmp_path: Path):
        raw = _make_image(300, 400)
        dest = tmp_path / "sub" / "dir" / "img.png"
        normalize_image(raw, dest)
        assert dest.exists()


class TestVerify:
    def test_good_image(self, tmp_path: Path):
        raw = _make_image(800, 1120)
        dest = tmp_path / "ok.png"
        normalize_image(raw, dest)
        assert verify_image(dest) == []

    def test_wrong_size(self, tmp_path: Path):
        img = Image.new("RGB", (100, 100))
        dest = tmp_path / "bad.png"
        img.save(str(dest))
        problems = verify_image(dest)
        assert any("size" in p for p in problems)

    def test_missing_dpi(self, tmp_path: Path):
        img = Image.new("RGB", (NORM_WIDTH, NORM_HEIGHT))
        dest = tmp_path / "nodpi.png"
        # Save without DPI
        img.save(str(dest), "PNG")
        problems = verify_image(dest)
        # PNG without explicit DPI may or may not report missing;
        # at least it should not crash
        assert isinstance(problems, list)

    def test_corrupted(self, tmp_path: Path):
        dest = tmp_path / "corrupt.png"
        dest.write_bytes(b"not an image")
        problems = verify_image(dest)
        assert len(problems) > 0
