#!/usr/bin/env python3
"""Tests for the CV-first EX card pipeline."""

import csv
import unittest
from pathlib import Path
import shutil
from uuid import uuid4

import cv2
import numpy as np

from pkmn_card_scraper import CardMetadata, OCRCandidate, PokemonCardScraper, SetSymbolMatcher


def create_synthetic_card(
    width: int = 400,
    height: int = 550,
    frame: tuple[int, int, int, int] = (30, 52, 372, 258),
    seed: int = 123,
) -> np.ndarray:
    """Build a card-like synthetic image with known artwork frame bounds."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = frame

    card = np.full((height, width, 3), 240, dtype=np.uint8)

    # Outer border.
    cv2.rectangle(card, (2, 2), (width - 3, height - 3), (120, 120, 120), 4)

    # Artwork texture.
    texture = rng.integers(0, 255, size=(y1 - y0 - 2, x1 - x0 - 2, 3), dtype=np.uint8)
    card[y0 + 1 : y1 - 1, x0 + 1 : x1 - 1] = texture

    # Artwork frame line.
    cv2.rectangle(card, (x0, y0), (x1, y1), (15, 15, 15), 3)

    # Flat text box region below art.
    text_top = y1 + 8
    text_bottom = min(height - 20, text_top + 125)
    cv2.rectangle(card, (28, text_top), (width - 28, text_bottom), (230, 230, 230), -1)

    for line in range(4):
        y = text_top + 18 + (line * 22)
        cv2.line(card, (40, y), (width - 40, y), (210, 210, 210), 1)

    return card


def alpha_blend_symbol(card: np.ndarray, symbol_path: Path, x: int, y: int, h: int) -> None:
    """Blend a symbol PNG with alpha into card image."""
    symbol = cv2.imread(str(symbol_path), cv2.IMREAD_UNCHANGED)
    if symbol is None:
        raise RuntimeError(f"Missing symbol image: {symbol_path}")

    if symbol.shape[2] == 4:
        alpha = symbol[:, :, 3]
        rgb = symbol[:, :, :3]
        ys, xs = np.where(alpha > 10)
        rgb = rgb[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        alpha = alpha[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    else:
        rgb = symbol[:, :, :3]
        alpha = np.full(rgb.shape[:2], 255, dtype=np.uint8)

    w = max(8, int(rgb.shape[1] * h / max(rgb.shape[0], 1)))
    rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
    alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_AREA)

    y1 = min(card.shape[0], y + h)
    x1 = min(card.shape[1], x + w)
    roi = card[y:y1, x:x1]

    rgb = rgb[: roi.shape[0], : roi.shape[1]]
    alpha = alpha[: roi.shape[0], : roi.shape[1]]

    blend = alpha[:, :, None] / 255.0
    roi[:] = (rgb * blend + roi * (1.0 - blend)).astype(np.uint8)


class TestCVPipeline(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = Path("test_tmp")
        base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp_path = base_tmp / f"cv_pipeline_case_{uuid4().hex}"
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path, ignore_errors=True)
        self.tmp_path.mkdir(parents=True, exist_ok=True)
        self.scraper = PokemonCardScraper(
            output_dir=str(self.tmp_path / "output"),
            sets_dir="Sets",
            enable_ocr=False,
            min_symbol_conf=0.42,
        )

    def tearDown(self) -> None:
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path, ignore_errors=True)

    def test_bounds_detection_regression(self) -> None:
        expected = (30, 52, 372, 258)
        card = create_synthetic_card(frame=expected)
        bounds = self.scraper.detect_art_bounds(card)

        self.assertFalse(bounds.used_fallback)
        self.assertGreater(bounds.confidence, 0.55)

        self.assertLessEqual(abs(bounds.x0 - expected[0]), 3)
        self.assertLessEqual(abs(bounds.y0 - expected[1]), 3)
        self.assertLessEqual(abs(bounds.x1 - expected[2]), 3)
        self.assertLessEqual(abs(bounds.y1 - expected[3]), 3)

    def test_bounds_detection_fallback_trigger(self) -> None:
        flat = np.full((550, 400, 3), 255, dtype=np.uint8)
        bounds = self.scraper.detect_art_bounds(flat)

        self.assertTrue(bounds.used_fallback)
        self.assertIn(bounds.fallback_reason, {"low_confidence", "invalid_geometry"})

    def test_filename_builder_and_collisions(self) -> None:
        metadata = CardMetadata(
            set_code="rs",
            collector_no="15",
            card_name="blaziken",
        )

        art_1, board_1, base_1 = self.scraper.build_output_paths(metadata)
        self.assertEqual(base_1, "rs_15_blaziken")

        art_1.write_bytes(b"x")
        board_1.write_bytes(b"x")

        art_2, board_2, base_2 = self.scraper.build_output_paths(metadata)
        self.assertEqual(base_2, "rs_15_blaziken_dup2")
        self.assertEqual(art_2.name, "rs_15_blaziken_dup2.png")
        self.assertEqual(board_2.name, "rs_15_blaziken_dup2_board.png")

    def test_metadata_parser_patterns(self) -> None:
        sample_1 = PokemonCardScraper.parse_metadata_from_source(
            "blaziken-ruby-sapphire-rs-15_00015.jpg"
        )
        self.assertEqual(sample_1.get("set_code"), "rs")
        self.assertEqual(sample_1.get("collector_no"), "15")
        self.assertEqual(sample_1.get("card_name"), "blaziken")

        sample_2 = PokemonCardScraper.parse_metadata_from_source(
            "rs093-darkness_energy-1.jpg"
        )
        self.assertEqual(sample_2.get("set_code"), "rs")
        self.assertEqual(sample_2.get("collector_no"), "93")
        self.assertEqual(sample_2.get("card_name"), "darkness_energy")

        sample_3 = PokemonCardScraper.parse_metadata_from_source(
            "en_US-EX1-015-blaziken_00015.jpg"
        )
        self.assertEqual(sample_3.get("set_code"), "rs")
        self.assertEqual(sample_3.get("collector_no"), "15")
        self.assertEqual(sample_3.get("card_name"), "blaziken")

    def test_collector_prefers_fallback_when_ocr_mismatches(self) -> None:
        metadata = self.scraper.resolve_metadata(
            cv_set_code="rs",
            set_score=0.10,
            cv_number=OCRCandidate(value="j0", confidence=0.95),
            cv_name=None,
            fallback_metadata={
                "set_code": "rs",
                "collector_no": "30",
                "card_name": "electrike",
            },
        )

        self.assertEqual(metadata.collector_no, "30")
        self.assertEqual(metadata.field_source.get("collector_no"), "fallback")

    def test_set_symbol_matcher_and_unknown(self) -> None:
        matcher = SetSymbolMatcher(Path("Sets"), min_symbol_conf=0.30)

        card = np.full((550, 400, 3), 255, dtype=np.uint8)
        alpha_blend_symbol(
            card,
            Path("Sets") / "ex-team-rocket-returns.png",
            x=300,
            y=460,
            h=26,
        )

        set_code, score, _, _ = matcher.match(card)
        self.assertEqual(set_code, "trr")
        self.assertGreaterEqual(score, 0.30)

        strict_matcher = SetSymbolMatcher(Path("Sets"), min_symbol_conf=0.95)
        blank = np.full((550, 400, 3), 255, dtype=np.uint8)
        set_code_2, _, _, _ = strict_matcher.match(blank)
        self.assertEqual(set_code_2, "unk")

    def test_batch_integration_smoke(self) -> None:
        in_dir = self.tmp_path / "input"
        in_dir.mkdir(parents=True, exist_ok=True)

        card_1 = create_synthetic_card(seed=1)
        card_2 = create_synthetic_card(seed=2)

        path_1 = in_dir / "en_US-EX1-015-blaziken.jpg"
        path_2 = in_dir / "en_US-EX2-001-cacturne.jpg"

        cv2.imwrite(str(path_1), card_1)
        cv2.imwrite(str(path_2), card_2)

        runner = PokemonCardScraper(
            output_dir=str(self.tmp_path / "batch_output"),
            sets_dir="Sets",
            enable_ocr=False,
            min_symbol_conf=0.99,
        )

        runner.run_batch(in_dir)

        art_1 = runner.art_dir / "rs_15_blaziken.png"
        board_1 = runner.cards_dir / "rs_15_blaziken_board.png"
        art_2 = runner.art_dir / "ss_1_cacturne.png"
        board_2 = runner.cards_dir / "ss_1_cacturne_board.png"

        self.assertTrue(art_1.exists())
        self.assertTrue(board_1.exists())
        self.assertTrue(art_2.exists())
        self.assertTrue(board_2.exists())

        board_img = cv2.imread(str(board_1))
        self.assertIsNotNone(board_img)
        self.assertEqual(board_img.shape[0], 1024)

        manifest = runner.output_dir / "manifest.csv"
        self.assertTrue(manifest.exists())

        with manifest.open("r", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        saved_rows = [row for row in rows if row.get("status") == "saved"]
        self.assertGreaterEqual(len(saved_rows), 2)


if __name__ == "__main__":
    unittest.main()
