
#!/usr/bin/env python3
"""
Pokemon Card Scraper with CV-first artwork extraction and deterministic naming.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup

try:
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    easyocr = None

try:
    from rapidfuzz import fuzz  # type: ignore
except ImportError:  # pragma: no cover - optional enhancement
    fuzz = None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


TARGET_WIDTH = 400
TARGET_HEIGHT = 550
TARGET_RATIO = TARGET_WIDTH / TARGET_HEIGHT
DEFAULT_OUTPUT_CARD_HEIGHT = 1024

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

EX_SET_SYMBOL_FILES: Dict[str, str] = {
    "rs": "ex-ruby-and-sapphire.png",
    "ss": "ex-sandstorm.png",
    "dr": "ex-dragon.png",
    "ma": "ex-team-magma-vs-team-aqua.png",
    "hl": "ex-hidden-legendsl.png",  # file in repository includes trailing l
    "fl": "ex-fire-red-and-leaf-green.png",
    "trr": "ex-team-rocket-returns.png",
    "dx": "ex-deoxys-pokemon.png",
    "em": "ex-emerald-pokemon.png",
    "uf": "ex-unseen-forces.png",
    "ds": "ex-delta-species.png",
    "lm": "ex-legend-maker.png",
    "hp": "ex-holon-phantoms.png",
    "cg": "ex-crystal-guardians.png",
    "df": "ex-dragon-frontiers.png",
    "pk": "ex-power-keepers.png",
}

EX_INDEX_TO_SET_CODE: Dict[int, str] = {
    1: "rs",
    2: "ss",
    3: "dr",
    4: "ma",
    5: "hl",
    6: "fl",
    7: "trr",
    8: "dx",
    9: "em",
    10: "uf",
    11: "ds",
    12: "lm",
    13: "hp",
    14: "cg",
    15: "df",
    16: "pk",
}

FALLBACK_NAME_STOPWORDS = {
    "pokemon",
    "ex",
    "ruby",
    "sapphire",
    "sandstorm",
    "dragon",
    "team",
    "magma",
    "vs",
    "aqua",
    "hidden",
    "legends",
    "fire",
    "red",
    "leaf",
    "green",
    "rocket",
    "returns",
    "deoxys",
    "emerald",
    "unseen",
    "forces",
    "delta",
    "species",
    "legend",
    "maker",
    "holon",
    "phantoms",
    "crystal",
    "guardians",
    "frontiers",
    "power",
    "keepers",
    "and",
}

OCR_DIGIT_CONFUSION_MAP = {
    "o": "0",
    "d": "0",
    "q": "0",
    "i": "1",
    "l": "1",
    "z": "2",
    "j": "3",
    "y": "4",
    "s": "5",
    "g": "6",
    "t": "7",
    "b": "8",
}


@dataclass
class ArtBounds:
    x0: int
    y0: int
    x1: int
    y1: int
    confidence: float
    used_fallback: bool = False
    fallback_reason: str = ""


@dataclass
class CardMetadata:
    set_code: str
    collector_no: str
    card_name: str
    field_source: Dict[str, str] = field(default_factory=dict)
    field_confidence: Dict[str, float] = field(default_factory=dict)
    fallback_reason: Dict[str, str] = field(default_factory=dict)


@dataclass
class OCRCandidate:
    value: str
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]] = None
    raw_text: str = ""


@dataclass
class NormalizationResult:
    image: np.ndarray
    method: str
    confidence: float
    reason: str = ""


def clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def slugify_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unk"


def normalize_collector_token(value: str) -> str:
    token = (value or "").strip()
    if "/" in token:
        token = token.split("/", 1)[0]

    token = re.sub(r"[^A-Za-z0-9]+", "", token)
    if not token:
        return "unk"

    if token.isdigit():
        return str(int(token))

    return token.lower()


class SetSymbolMatcher:
    """Template matcher for EX-era set symbols."""

    def __init__(self, sets_dir: Path, min_symbol_conf: float = 0.42) -> None:
        self.sets_dir = sets_dir
        self.min_symbol_conf = min_symbol_conf
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict[str, List[Tuple[np.ndarray, np.ndarray]]]:
        template_cache: Dict[str, List[Tuple[np.ndarray, np.ndarray]]] = {}

        for set_code, filename in EX_SET_SYMBOL_FILES.items():
            symbol_path = self.sets_dir / filename
            symbol = cv2.imread(str(symbol_path), cv2.IMREAD_UNCHANGED)

            if symbol is None:
                logger.warning("Missing set symbol template: %s", symbol_path)
                continue

            prepared = self._prepare_symbol(symbol)
            if prepared is None:
                logger.warning("Unable to prepare set symbol template: %s", symbol_path)
                continue

            gray, edge = prepared
            template_cache[set_code] = self._build_multiscale_variants(gray, edge)

        if not template_cache:
            logger.warning("No EX set symbol templates loaded from %s", self.sets_dir)
        else:
            logger.info("Loaded %d EX set symbol templates", len(template_cache))

        return template_cache

    @staticmethod
    def _prepare_symbol(symbol: np.ndarray) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        if symbol.ndim != 3:
            return None

        if symbol.shape[2] == 4:
            alpha = symbol[:, :, 3]
            rgb = symbol[:, :, :3]
            ys, xs = np.where(alpha > 10)
            if len(xs) == 0:
                return None

            x0, x1 = int(xs.min()), int(xs.max()) + 1
            y0, y1 = int(ys.min()), int(ys.max()) + 1

            rgb = rgb[y0:y1, x0:x1]
            alpha = alpha[y0:y1, x0:x1]

            bg = np.full_like(rgb, 255)
            blend = alpha[:, :, None] / 255.0
            composed = (rgb * blend + bg * (1.0 - blend)).astype(np.uint8)
        else:
            composed = symbol[:, :, :3].copy()

        gray = cv2.cvtColor(composed, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        edge = cv2.Canny(gray, 60, 180)
        return gray, edge

    @staticmethod
    def _build_multiscale_variants(
        gray: np.ndarray, edge: np.ndarray
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        variants: List[Tuple[np.ndarray, np.ndarray]] = []
        for height in range(12, 52, 2):
            width = max(8, int(gray.shape[1] * height / max(gray.shape[0], 1)))
            scaled_gray = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
            scaled_edge = cv2.resize(edge, (width, height), interpolation=cv2.INTER_AREA)
            variants.append((scaled_gray, scaled_edge))
        return variants

    @staticmethod
    def _extract_roi(
        card_image: np.ndarray, number_bbox: Optional[Tuple[int, int, int, int]]
    ) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
        h, w = card_image.shape[:2]

        if number_bbox:
            bx0, by0, bx1, by1 = number_bbox
            x0 = clamp(bx1 + 2, 0, w - 1)
            x1 = clamp(x0 + int(0.22 * w), x0 + 10, w)
            y0 = clamp(by0 - int(0.03 * h), 0, h - 1)
            y1 = clamp(by1 + int(0.06 * h), y0 + 10, h)

            if x1 - x0 >= 16 and y1 - y0 >= 16:
                return card_image[y0:y1, x0:x1], (x0, y0, x1, y1)

        x0 = int(0.62 * w)
        x1 = int(0.95 * w)
        y0 = int(0.80 * h)
        y1 = int(0.97 * h)
        return card_image[y0:y1, x0:x1], (x0, y0, x1, y1)

    def match(
        self,
        card_image: np.ndarray,
        number_bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> Tuple[str, float, float, Tuple[int, int, int, int]]:
        if not self.templates:
            return "unk", 0.0, 0.0, (0, 0, 0, 0)

        roi, roi_bounds = self._extract_roi(card_image, number_bbox)
        if roi.size == 0:
            return "unk", 0.0, 0.0, roi_bounds

        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        roi_gray = cv2.equalizeHist(roi_gray)
        roi_edge = cv2.Canny(roi_gray, 60, 180)

        scores: Dict[str, float] = {}

        for set_code, variants in self.templates.items():
            best_score = -1.0

            for template_gray, template_edge in variants:
                th, tw = template_gray.shape[:2]
                if th >= roi_gray.shape[0] or tw >= roi_gray.shape[1]:
                    continue

                gray_result = cv2.matchTemplate(
                    roi_gray, template_gray, cv2.TM_CCOEFF_NORMED
                )
                edge_result = cv2.matchTemplate(
                    roi_edge, template_edge, cv2.TM_CCOEFF_NORMED
                )

                _, gray_score, _, _ = cv2.minMaxLoc(gray_result)
                _, edge_score, _, _ = cv2.minMaxLoc(edge_result)

                combined = (0.45 * float(gray_score)) + (0.55 * float(edge_score))
                if np.isfinite(combined) and combined > best_score:
                    best_score = combined

            if best_score >= 0.0:
                scores[set_code] = best_score

        if not scores:
            return "unk", 0.0, 0.0, roi_bounds

        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_code, best_score = ordered[0]
        second_score = ordered[1][1] if len(ordered) > 1 else 0.0

        if best_score >= self.min_symbol_conf and (best_score - second_score) >= 0.05:
            return best_code, best_score, second_score, roi_bounds

        return "unk", best_score, second_score, roi_bounds


class PokemonCardScraper:
    """Scrape and process Pokemon cards with CV and OCR."""

    def __init__(
        self,
        base_url: str = "https://pkmncards.com",
        output_dir: str = "output",
        search_params: str = "s=series%3Aex&sort=date&ord=auto",
        sets_dir: str = "Sets",
        min_ocr_conf: float = 0.45,
        min_symbol_conf: float = 0.42,
        output_card_height: int = DEFAULT_OUTPUT_CARD_HEIGHT,
        enhance_text_mode: str = "mild",
        enable_ocr: bool = True,
    ) -> None:
        self.base_url = base_url
        self.search_params = search_params

        self.output_dir = Path(output_dir)
        self.cards_dir = self.output_dir / "cards"
        self.art_dir = self.output_dir / "art_only"
        self.raw_dir = self.output_dir / "raw_downloads"

        self.cards_dir.mkdir(parents=True, exist_ok=True)
        self.art_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        self.min_ocr_conf = min_ocr_conf
        self.min_symbol_conf = min_symbol_conf
        self.output_card_height = max(TARGET_HEIGHT, int(output_card_height))
        self.enhance_text_mode = enhance_text_mode.lower().strip()
        if self.enhance_text_mode not in {"none", "mild"}:
            raise ValueError("enhance_text_mode must be one of: none, mild")

        self.manifest_path = self.output_dir / "manifest.csv"
        self.manifest_columns = [
            "timestamp",
            "status",
            "input_source",
            "input_path",
            "normalized_method",
            "normalized_confidence",
            "art_bounds_x0",
            "art_bounds_y0",
            "art_bounds_x1",
            "art_bounds_y1",
            "art_bounds_confidence",
            "art_bounds_fallback",
            "set_code",
            "collector_no",
            "card_name",
            "set_source",
            "collector_source",
            "name_source",
            "set_confidence",
            "collector_confidence",
            "name_confidence",
            "symbol_score",
            "symbol_second_score",
            "fallback_reason",
            "art_file",
            "board_file",
            "message",
        ]
        self._ensure_manifest_header()

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0 Safari/537.36"
                )
            }
        )
        self.timeout = 30
        self.retry_count = 3
        self.delay_between_requests = 1.0
        self.downloaded_urls: set[str] = set()
        self.last_collector_by_set: Dict[str, int] = {}

        self.output_card_width = int(round(self.output_card_height * TARGET_RATIO))
        logger.info(
            "Board output size configured to %dx%d (enhance_text_mode=%s)",
            self.output_card_width,
            self.output_card_height,
            self.enhance_text_mode,
        )

        self.symbol_matcher = SetSymbolMatcher(
            sets_dir=Path(sets_dir), min_symbol_conf=self.min_symbol_conf
        )

        self.reader = None
        if enable_ocr:
            if easyocr is None:
                raise RuntimeError(
                    "easyocr is not installed. Install dependencies with: pip install -r requirements.txt"
                )
            logger.info("Initializing EasyOCR reader (single instance)")
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    def _ensure_manifest_header(self) -> None:
        if self.manifest_path.exists():
            return

        with self.manifest_path.open("w", newline="", encoding="utf-8") as manifest_file:
            writer = csv.DictWriter(manifest_file, fieldnames=self.manifest_columns)
            writer.writeheader()

    def _append_manifest(self, row: Dict[str, object]) -> None:
        payload = {column: row.get(column, "") for column in self.manifest_columns}
        with self.manifest_path.open("a", newline="", encoding="utf-8") as manifest_file:
            writer = csv.DictWriter(manifest_file, fieldnames=self.manifest_columns)
            writer.writerow(payload)

    def scrape_page(self, page_num: int = 1) -> List[str]:
        if page_num == 1:
            url = f"{self.base_url}/?{self.search_params}&display=images"
        else:
            url = f"{self.base_url}/page/{page_num}/?{self.search_params}&display=images"

        logger.info("Scraping page %d: %s", page_num, url)

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to scrape page %d: %s", page_num, exc)
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        candidates: List[str] = []

        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src")
            if not src:
                continue
            full_url = urljoin(self.base_url, src)
            lower = full_url.lower()
            if any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                candidates.append(full_url)

        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue
            full_url = urljoin(self.base_url, href)
            lower = full_url.lower()
            if any(lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                candidates.append(full_url)

        deduped: List[str] = []
        seen = set()
        for item in candidates:
            if item in self.downloaded_urls or item in seen:
                continue
            seen.add(item)
            deduped.append(item)

        logger.info("Found %d candidate images on page %d", len(deduped), page_num)
        return deduped

    def download_image(self, url: str, filepath: Path) -> bool:
        for attempt in range(1, self.retry_count + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, stream=True)
                response.raise_for_status()

                with filepath.open("wb") as out_file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            out_file.write(chunk)

                return True
            except requests.RequestException as exc:
                logger.warning(
                    "Download attempt %d/%d failed for %s: %s",
                    attempt,
                    self.retry_count,
                    url,
                    exc,
                )
                if attempt < self.retry_count:
                    time.sleep(2 ** (attempt - 1))

        return False

    @staticmethod
    def _is_valid_card_candidate(image: np.ndarray) -> Tuple[bool, str]:
        if image is None:
            return False, "image_load_failed"

        h, w = image.shape[:2]
        ratio = w / max(h, 1)

        if w < 240 or h < 320:
            return False, f"too_small_{w}x{h}"

        if ratio < 0.58 or ratio > 0.79:
            return False, f"invalid_ratio_{ratio:.3f}"

        return True, "ok"

    @staticmethod
    def _order_points(points: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype=np.float32)
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1)

        rect[0] = points[np.argmin(sums)]
        rect[2] = points[np.argmax(sums)]
        rect[1] = points[np.argmin(diffs)]
        rect[3] = points[np.argmax(diffs)]
        return rect

    def _normalize_card_image(self, image: np.ndarray) -> NormalizationResult:
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 60, 160)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:40]

        best_quad = None
        best_score = -1.0
        best_fill_ratio = 0.0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 0.35 * w * h:
                continue

            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) != 4:
                continue

            quad = approx.reshape(4, 2).astype(np.float32)
            ordered = self._order_points(quad)

            top_width = np.linalg.norm(ordered[1] - ordered[0])
            bottom_width = np.linalg.norm(ordered[2] - ordered[3])
            left_height = np.linalg.norm(ordered[3] - ordered[0])
            right_height = np.linalg.norm(ordered[2] - ordered[1])

            quad_width = max(top_width, bottom_width)
            quad_height = max(left_height, right_height)
            if quad_height < 1:
                continue

            ratio = quad_width / quad_height
            if ratio < 0.58 or ratio > 0.79:
                continue

            fill_ratio = area / float(w * h)
            score = fill_ratio - abs(ratio - TARGET_RATIO)

            if score > best_score:
                best_score = score
                best_quad = ordered
                best_fill_ratio = fill_ratio

        if best_quad is not None:
            destination = np.array(
                [
                    [0, 0],
                    [TARGET_WIDTH - 1, 0],
                    [TARGET_WIDTH - 1, TARGET_HEIGHT - 1],
                    [0, TARGET_HEIGHT - 1],
                ],
                dtype=np.float32,
            )
            matrix = cv2.getPerspectiveTransform(best_quad, destination)
            warped = cv2.warpPerspective(
                image,
                matrix,
                (TARGET_WIDTH, TARGET_HEIGHT),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )
            confidence = min(1.0, 0.5 + (best_fill_ratio * 0.7))
            return NormalizationResult(
                image=warped,
                method="perspective_warp",
                confidence=confidence,
                reason="",
            )

        scale = min(TARGET_WIDTH / w, TARGET_HEIGHT / h)
        resized_w = max(1, int(round(w * scale)))
        resized_h = max(1, int(round(h * scale)))

        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        resized = cv2.resize(image, (resized_w, resized_h), interpolation=interpolation)

        canvas = np.full((TARGET_HEIGHT, TARGET_WIDTH, 3), 255, dtype=np.uint8)
        offset_x = (TARGET_WIDTH - resized_w) // 2
        offset_y = (TARGET_HEIGHT - resized_h) // 2
        canvas[offset_y : offset_y + resized_h, offset_x : offset_x + resized_w] = resized

        ratio_error = abs((w / max(h, 1)) - TARGET_RATIO)
        confidence = 0.62 if ratio_error <= 0.035 else 0.45

        return NormalizationResult(
            image=canvas,
            method="pad_resize",
            confidence=confidence,
            reason="contour_not_found",
        )

    @staticmethod
    def _find_peak(
        profile: np.ndarray,
        start: int,
        end: int,
        guess: int,
        smooth: int = 7,
        distance_penalty: float = 0.20,
    ) -> Tuple[int, float]:
        start = clamp(start, 0, len(profile) - 1)
        end = clamp(end, start + 1, len(profile))
        segment = profile[start:end].astype(np.float32)

        if smooth > 1:
            kernel = np.ones(smooth, dtype=np.float32) / smooth
            segment = np.convolve(segment, kernel, mode="same")

        indexes = np.arange(start, end)
        penalized = segment - (distance_penalty * np.abs(indexes - guess))
        local_index = int(np.argmax(penalized))
        best_index = start + local_index

        raw_peak = float(segment[local_index])
        mean = float(np.mean(segment))
        std = float(np.std(segment)) + 1e-6
        z_score = max(0.0, (raw_peak - mean) / std)
        normalized_score = min(1.0, z_score / 6.0)

        return best_index, normalized_score

    def detect_art_bounds(
        self, card_image: np.ndarray, force_low_confidence: bool = False
    ) -> ArtBounds:
        h, w = card_image.shape[:2]

        gray = cv2.cvtColor(card_image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        grad_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
        grad_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))

        guess_x0 = int(0.075 * w)
        guess_x1 = int(0.93 * w)
        guess_y0 = int(0.095 * h)
        guess_y1 = int(0.47 * h)

        row_start = int(0.08 * h)
        row_end = int(0.57 * h)

        col_profile = grad_x[row_start:row_end, :].mean(axis=0)
        x0, score_x0 = self._find_peak(
            col_profile,
            int(guess_x0 - (0.035 * w)),
            int(guess_x0 + (0.035 * w)),
            guess_x0,
        )
        x1, score_x1 = self._find_peak(
            col_profile,
            int(guess_x1 - (0.040 * w)),
            int(guess_x1 + (0.040 * w)),
            guess_x1,
        )

        inner_x0 = clamp(x0 + 4, 0, w - 1)
        inner_x1 = clamp(x1 - 4, inner_x0 + 1, w)
        row_profile = grad_y[:, inner_x0:inner_x1].mean(axis=1)

        y0, score_y0 = self._find_peak(
            row_profile,
            int(guess_y0 - (0.050 * h)),
            int(guess_y0 + (0.050 * h)),
            guess_y0,
        )
        y1, score_y1 = self._find_peak(
            row_profile,
            int(guess_y1 - (0.070 * h)),
            int(guess_y1 + (0.060 * h)),
            guess_y1,
            smooth=9,
            distance_penalty=0.45,
        )

        # Bottom refinement: find sustained texture drop below artwork area.
        variance_band = gray[:, inner_x0:inner_x1].astype(np.float32).var(axis=1)
        variance_smooth = np.convolve(
            variance_band,
            np.ones(7, dtype=np.float32) / 7.0,
            mode="same",
        )

        baseline_start = clamp(y0 + 12, 0, h - 1)
        baseline_end = clamp(y1 - 6, baseline_start + 1, h)
        baseline = float(np.mean(variance_smooth[baseline_start:baseline_end]))
        threshold = baseline * 0.67

        search_start = clamp(y1, 0, h - 1)
        search_end = clamp(y1 + int(0.12 * h), search_start + 1, int(0.62 * h))

        run_length = 0
        transition_row = None

        for row in range(search_start, search_end):
            if variance_smooth[row] < threshold:
                run_length += 1
                if run_length >= 6:
                    transition_row = row - run_length + 1
                    break
            else:
                run_length = 0

        refine_bonus = 0.0
        if transition_row is not None:
            y1 = clamp(transition_row - 1, y0 + 20, h - 1)
            refine_bonus = 0.05

        # Keep bottom frame near known EX-era layout to avoid text bleed.
        y1 = clamp(
            y1,
            max(y0 + 80, int(0.43 * h)),
            int(0.48 * h),
        )

        width_ratio = (x1 - x0) / float(w)
        height_ratio = (y1 - y0) / float(h)

        width_score = max(0.0, 1.0 - abs(width_ratio - 0.855) / 0.18)
        height_score = max(0.0, 1.0 - abs(height_ratio - 0.375) / 0.20)
        geometry_score = (0.5 * width_score) + (0.5 * height_score)

        edge_score = (score_x0 + score_x1 + score_y0 + score_y1) / 4.0
        confidence = (0.25 * edge_score) + (0.70 * geometry_score) + refine_bonus
        confidence = float(np.clip(confidence, 0.0, 1.0))

        invalid_geometry = (
            x1 <= x0 + 60
            or y1 <= y0 + 60
            or width_ratio < 0.60
            or width_ratio > 0.94
            or height_ratio < 0.25
            or height_ratio > 0.40
            or edge_score < 0.10
        )

        if force_low_confidence:
            confidence = 0.0

        if invalid_geometry or confidence < 0.55:
            return ArtBounds(
                x0=int(0.075 * w),
                y0=int(0.095 * h),
                x1=int(0.93 * w),
                y1=int(0.47 * h),
                confidence=confidence,
                used_fallback=True,
                fallback_reason="low_confidence" if not invalid_geometry else "invalid_geometry",
            )

        return ArtBounds(
            x0=clamp(x0, 0, w - 2),
            y0=clamp(y0, 0, h - 2),
            x1=clamp(x1, 1, w - 1),
            y1=clamp(y1, 1, h - 1),
            confidence=confidence,
            used_fallback=False,
            fallback_reason="",
        )

    @staticmethod
    def crop_artwork(card_image: np.ndarray, bounds: ArtBounds) -> np.ndarray:
        h, w = card_image.shape[:2]
        inset_x = max(2, int(round(0.008 * w)))
        inset_y = max(2, int(round(0.008 * h)))

        x0 = clamp(bounds.x0 + inset_x, 0, w - 1)
        y0 = clamp(bounds.y0 + inset_y, 0, h - 1)
        x1 = clamp(bounds.x1 - inset_x, x0 + 1, w)
        y1 = clamp(bounds.y1 - inset_y, y0 + 1, h)
        return card_image[y0:y1, x0:x1].copy()

    @staticmethod
    def _enhance_text_readability_mild(image: np.ndarray) -> np.ndarray:
        """
        Apply very mild, fidelity-first readability enhancement.
        This intentionally avoids aggressive denoise/contrast boosts.
        """
        ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
        y, cr, cb = cv2.split(ycrcb)

        blurred = cv2.GaussianBlur(y, (0, 0), sigmaX=0.8, sigmaY=0.8)
        y_sharp = cv2.addWeighted(y, 1.03, blurred, -0.03, 0)

        merged = cv2.merge([y_sharp, cr, cb])
        return cv2.cvtColor(merged, cv2.COLOR_YCrCb2BGR)

    def build_board_output(self, normalized_card: np.ndarray) -> np.ndarray:
        target_w = self.output_card_width
        target_h = self.output_card_height

        if normalized_card.shape[1] == target_w and normalized_card.shape[0] == target_h:
            board = normalized_card.copy()
        else:
            board = cv2.resize(
                normalized_card,
                (target_w, target_h),
                interpolation=cv2.INTER_LANCZOS4,
            )

        if self.enhance_text_mode == "mild":
            board = self._enhance_text_readability_mild(board)

        return board

    def _run_ocr(
        self, roi: np.ndarray, allowlist: Optional[str] = None
    ) -> List[Tuple[np.ndarray, str, float]]:
        if self.reader is None:
            return []

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        thresholded = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]

        variants = [
            roi,
            cv2.cvtColor(thresholded, cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(255 - thresholded, cv2.COLOR_GRAY2BGR),
        ]

        all_results: List[Tuple[np.ndarray, str, float]] = []

        for variant in variants:
            upscaled = cv2.resize(
                variant,
                None,
                fx=2.0,
                fy=2.0,
                interpolation=cv2.INTER_CUBIC,
            )

            try:
                results = self.reader.readtext(
                    upscaled,
                    detail=1,
                    paragraph=False,
                    allowlist=allowlist,
                )
            except Exception as exc:  # pragma: no cover - OCR runtime dependent
                logger.warning("EasyOCR read failed: %s", exc)
                continue

            for box, text, confidence in results:
                box_array = np.array(box, dtype=np.float32) / 2.0
                all_results.append((box_array, text, float(confidence)))

        return all_results

    @staticmethod
    def _bbox_from_quad(quad: np.ndarray) -> Tuple[int, int, int, int]:
        x0 = int(np.floor(np.min(quad[:, 0])))
        y0 = int(np.floor(np.min(quad[:, 1])))
        x1 = int(np.ceil(np.max(quad[:, 0])))
        y1 = int(np.ceil(np.max(quad[:, 1])))
        return x0, y0, x1, y1

    def _extract_name_candidate(self, card_image: np.ndarray) -> Optional[OCRCandidate]:
        h, w = card_image.shape[:2]
        rx0, rx1 = int(0.06 * w), int(0.79 * w)
        ry0, ry1 = int(0.025 * h), int(0.14 * h)

        roi = card_image[ry0:ry1, rx0:rx1]
        ocr_results = self._run_ocr(roi)

        best: Optional[OCRCandidate] = None
        best_score = -1.0

        for box, text, confidence in ocr_results:
            cleaned = re.sub(r"\bHP\d*\b", "", text, flags=re.IGNORECASE)
            cleaned = re.sub(r"[^A-Za-z0-9 '\-]", "", cleaned).strip()
            if len(cleaned) < 2 or not re.search(r"[A-Za-z]", cleaned):
                continue

            global_box = box.copy()
            global_box[:, 0] += rx0
            global_box[:, 1] += ry0
            bbox = self._bbox_from_quad(global_box)

            score = confidence + min(0.15, len(cleaned) * 0.01)
            if score > best_score:
                best_score = score
                best = OCRCandidate(
                    value=slugify_name(cleaned),
                    confidence=float(confidence),
                    bbox=bbox,
                    raw_text=cleaned,
                )

        return best

    def _extract_collector_candidate(self, card_image: np.ndarray) -> Optional[OCRCandidate]:
        h, w = card_image.shape[:2]
        rx0, rx1 = int(0.56 * w), int(0.92 * w)
        ry0, ry1 = int(0.82 * h), int(0.97 * h)

        roi = card_image[ry0:ry1, rx0:rx1]
        allowlist = "0123456789/SHsh"
        ocr_results = self._run_ocr(roi, allowlist=allowlist)

        best: Optional[OCRCandidate] = None
        best_conf = -1.0

        numeric_pattern = re.compile(r"(\d{1,3})(?:/\d{1,3})?", re.IGNORECASE)
        secret_pattern = re.compile(r"(SH\d{1,3})", re.IGNORECASE)

        for box, text, confidence in ocr_results:
            compact = re.sub(r"\s+", "", text.upper())
            token_match = numeric_pattern.search(compact) or secret_pattern.search(compact)
            if not token_match:
                continue

            collector = normalize_collector_token(token_match.group(1))
            if collector == "unk":
                continue

            global_box = box.copy()
            global_box[:, 0] += rx0
            global_box[:, 1] += ry0
            bbox = self._bbox_from_quad(global_box)

            if confidence > best_conf:
                best_conf = float(confidence)
                best = OCRCandidate(
                    value=collector,
                    confidence=float(confidence),
                    bbox=bbox,
                    raw_text=compact,
                )

        return best

    @staticmethod
    def _extract_name_from_prefix(prefix: str) -> str:
        tokens = [token for token in re.split(r"[-_]+", prefix.lower()) if token]
        tokens = [token for token in tokens if not re.fullmatch(r"\d+", token)]

        if not tokens:
            return "unk"

        filtered = [token for token in tokens if token not in FALLBACK_NAME_STOPWORDS]

        if not filtered:
            filtered = tokens[:]

        if len(filtered) > 3:
            filtered = filtered[:3]

        return slugify_name("_".join(filtered))

    @staticmethod
    def parse_metadata_from_source(source_ref: str) -> Dict[str, str]:
        source = unquote(source_ref)
        parsed = urlparse(source)
        raw_name = Path(parsed.path if parsed.scheme else source).name
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", raw_name)
        stem = re.sub(r"[_-]\d{4,}$", "", stem)
        lower = stem.lower()

        result: Dict[str, str] = {}

        ex_match = re.search(
            r"ex(?:_|-)?(\d{1,2})[-_](\d{1,3}[a-z]?)[-_]([a-z0-9][a-z0-9_-]*)",
            lower,
        )
        if ex_match:
            ex_index = int(ex_match.group(1))
            set_code = EX_INDEX_TO_SET_CODE.get(ex_index)
            if set_code:
                result["set_code"] = set_code
            result["collector_no"] = normalize_collector_token(ex_match.group(2))
            result["card_name"] = slugify_name(ex_match.group(3))
            return result

        compact_match = re.match(
            r"^(rs|ss|dr|ma|hl|fl|trr|dx|em|uf|ds|lm|hp|cg|df|pk)(\d{2,3}[a-z]?)[-_]([a-z0-9][a-z0-9_-]*)$",
            lower,
        )
        if compact_match:
            result["set_code"] = compact_match.group(1)
            result["collector_no"] = normalize_collector_token(compact_match.group(2))
            name_part = re.sub(r"[-_]\d+$", "", compact_match.group(3))
            result["card_name"] = slugify_name(name_part)
            return result

        hyphen_match = re.search(
            r"(?P<prefix>.+?)[-_](?P<set>rs|ss|dr|ma|hl|fl|trr|dx|em|uf|ds|lm|hp|cg|df|pk)[-_](?P<num>[a-z0-9]{1,4})(?:[_-]|$)",
            lower,
        )
        if hyphen_match:
            result["set_code"] = hyphen_match.group("set")
            result["collector_no"] = normalize_collector_token(hyphen_match.group("num"))
            result["card_name"] = PokemonCardScraper._extract_name_from_prefix(
                hyphen_match.group("prefix")
            )
            return result

        return result

    def _resolve_name_choice(
        self,
        cv_name: Optional[OCRCandidate],
        fallback_name: Optional[str],
        fallback_reason: Dict[str, str],
    ) -> Tuple[str, str, float]:
        if cv_name and cv_name.value != "unk" and cv_name.confidence >= self.min_ocr_conf:
            return cv_name.value, "cv", cv_name.confidence

        if cv_name and fallback_name and fuzz is not None:
            similarity = fuzz.ratio(cv_name.value, fallback_name)
            if cv_name.confidence >= (self.min_ocr_conf * 0.65) and similarity >= 85:
                return cv_name.value, "cv", cv_name.confidence

        if fallback_name:
            fallback_reason["card_name"] = (
                "cv_low_confidence" if cv_name else "cv_missing"
            )
            return fallback_name, "fallback", 0.35

        return "unk", "unknown", 0.0

    @staticmethod
    def _coerce_ambiguous_collector(token: str) -> str:
        mapped: List[str] = []
        for ch in token.lower():
            if ch.isdigit():
                mapped.append(ch)
            elif ch in OCR_DIGIT_CONFUSION_MAP:
                mapped.append(OCR_DIGIT_CONFUSION_MAP[ch])

        if not mapped:
            return "unk"

        digits = "".join(mapped)
        if digits.isdigit():
            return str(int(digits))

        return "unk"

    def _resolve_collector_choice(
        self,
        cv_number: Optional[OCRCandidate],
        fallback_number: str,
        fallback_reason: Dict[str, str],
    ) -> Tuple[str, str, float]:
        fallback_available = fallback_number != "unk"

        if cv_number:
            cv_token = normalize_collector_token(cv_number.value)
            cv_conf = cv_number.confidence
        else:
            cv_token = "unk"
            cv_conf = 0.0

        coerced = self._coerce_ambiguous_collector(cv_token)

        if fallback_available:
            if cv_token == fallback_number and cv_conf >= self.min_ocr_conf:
                return cv_token, "cv", cv_conf

            if coerced == fallback_number and cv_conf >= (self.min_ocr_conf * 0.75):
                fallback_reason["collector_no"] = "cv_ambiguous_corrected"
                return fallback_number, "fallback", 0.35

            fallback_reason["collector_no"] = (
                "cv_mismatch" if cv_number and cv_token != "unk" else "cv_missing"
            )
            return fallback_number, "fallback", 0.35

        if cv_token != "unk" and cv_conf >= self.min_ocr_conf and cv_token.isdigit():
            return cv_token, "cv", cv_conf

        if (
            coerced != "unk"
            and cv_conf >= (self.min_ocr_conf * 0.80)
            and len(coerced) <= 3
        ):
            fallback_reason["collector_no"] = "cv_ambiguous_coerced"
            return coerced, "cv", cv_conf

        return "unk", "unknown", 0.0

    def _apply_sequence_inference(self, metadata: CardMetadata) -> None:
        set_code = metadata.set_code
        if set_code not in EX_SET_SYMBOL_FILES:
            return

        collector = metadata.collector_no
        if collector.isdigit():
            self.last_collector_by_set[set_code] = int(collector)
            return

        previous = self.last_collector_by_set.get(set_code)
        if previous is None:
            return

        inferred = str(previous + 1)
        metadata.collector_no = inferred
        metadata.field_source["collector_no"] = "sequence"
        metadata.field_confidence["collector_no"] = 0.20
        metadata.fallback_reason["collector_no"] = "sequence_inference"
        self.last_collector_by_set[set_code] = int(inferred)

    def resolve_metadata(
        self,
        cv_set_code: str,
        set_score: float,
        cv_number: Optional[OCRCandidate],
        cv_name: Optional[OCRCandidate],
        fallback_metadata: Dict[str, str],
    ) -> CardMetadata:
        fallback_reason: Dict[str, str] = {}
        field_source: Dict[str, str] = {}
        field_conf: Dict[str, float] = {}

        fallback_set = fallback_metadata.get("set_code")
        if cv_set_code in EX_SET_SYMBOL_FILES and set_score >= self.min_symbol_conf:
            set_code = cv_set_code
            field_source["set_code"] = "cv"
            field_conf["set_code"] = set_score
        elif fallback_set in EX_SET_SYMBOL_FILES:
            set_code = fallback_set
            field_source["set_code"] = "fallback"
            field_conf["set_code"] = 0.35
            fallback_reason["set_code"] = "cv_low_confidence"
        else:
            set_code = "unk"
            field_source["set_code"] = "unknown"
            field_conf["set_code"] = 0.0

        fallback_number = normalize_collector_token(fallback_metadata.get("collector_no", ""))
        collector_no, collector_source, collector_conf = self._resolve_collector_choice(
            cv_number=cv_number,
            fallback_number=fallback_number,
            fallback_reason=fallback_reason,
        )
        field_source["collector_no"] = collector_source
        field_conf["collector_no"] = collector_conf

        fallback_name = fallback_metadata.get("card_name")
        card_name, name_source, name_conf = self._resolve_name_choice(
            cv_name,
            fallback_name,
            fallback_reason,
        )
        field_source["card_name"] = name_source
        field_conf["card_name"] = name_conf

        return CardMetadata(
            set_code=slugify_name(set_code),
            collector_no=normalize_collector_token(collector_no),
            card_name=slugify_name(card_name),
            field_source=field_source,
            field_confidence=field_conf,
            fallback_reason=fallback_reason,
        )

    def build_output_paths(self, metadata: CardMetadata) -> Tuple[Path, Path, str]:
        base = f"{metadata.set_code}_{metadata.collector_no}_{metadata.card_name}"
        base = re.sub(r"_+", "_", base).strip("_") or "unk_unk_unk"

        candidate = base
        duplicate_index = 2

        while True:
            art_path = self.art_dir / f"{candidate}.png"
            board_path = self.cards_dir / f"{candidate}_board.png"
            if not art_path.exists() and not board_path.exists():
                return art_path, board_path, candidate

            candidate = f"{base}_dup{duplicate_index}"
            duplicate_index += 1

    def process_image_array(
        self,
        image: np.ndarray,
        source_ref: str,
        input_path: str = "",
    ) -> bool:
        valid, reason = self._is_valid_card_candidate(image)
        if not valid:
            self._append_manifest(
                {
                    "timestamp": int(time.time()),
                    "status": "skipped",
                    "input_source": source_ref,
                    "input_path": input_path,
                    "message": reason,
                }
            )
            logger.warning("Skipping non-card candidate %s (%s)", source_ref, reason)
            return False

        normalized = self._normalize_card_image(image)
        art_bounds = self.detect_art_bounds(normalized.image)
        artwork = self.crop_artwork(normalized.image, art_bounds)

        number_candidate = self._extract_collector_candidate(normalized.image)
        name_candidate = self._extract_name_candidate(normalized.image)

        number_bbox = number_candidate.bbox if number_candidate else None
        set_code_cv, symbol_score, second_score, _ = self.symbol_matcher.match(
            normalized.image,
            number_bbox=number_bbox,
        )

        fallback = self.parse_metadata_from_source(source_ref)
        metadata = self.resolve_metadata(
            cv_set_code=set_code_cv,
            set_score=symbol_score,
            cv_number=number_candidate,
            cv_name=name_candidate,
            fallback_metadata=fallback,
        )
        self._apply_sequence_inference(metadata)

        art_path, board_path, final_base = self.build_output_paths(metadata)
        board_image = self.build_board_output(normalized.image)

        saved_art = cv2.imwrite(str(art_path), artwork)
        saved_board = cv2.imwrite(str(board_path), board_image)

        if not saved_art or not saved_board:
            self._append_manifest(
                {
                    "timestamp": int(time.time()),
                    "status": "error",
                    "input_source": source_ref,
                    "input_path": input_path,
                    "set_code": metadata.set_code,
                    "collector_no": metadata.collector_no,
                    "card_name": metadata.card_name,
                    "message": "write_failed",
                }
            )
            logger.error("Failed writing outputs for %s", source_ref)
            return False

        self._append_manifest(
            {
                "timestamp": int(time.time()),
                "status": "saved",
                "input_source": source_ref,
                "input_path": input_path,
                "normalized_method": normalized.method,
                "normalized_confidence": f"{normalized.confidence:.4f}",
                "art_bounds_x0": art_bounds.x0,
                "art_bounds_y0": art_bounds.y0,
                "art_bounds_x1": art_bounds.x1,
                "art_bounds_y1": art_bounds.y1,
                "art_bounds_confidence": f"{art_bounds.confidence:.4f}",
                "art_bounds_fallback": int(art_bounds.used_fallback),
                "set_code": metadata.set_code,
                "collector_no": metadata.collector_no,
                "card_name": metadata.card_name,
                "set_source": metadata.field_source.get("set_code", "unknown"),
                "collector_source": metadata.field_source.get("collector_no", "unknown"),
                "name_source": metadata.field_source.get("card_name", "unknown"),
                "set_confidence": f"{metadata.field_confidence.get('set_code', 0.0):.4f}",
                "collector_confidence": f"{metadata.field_confidence.get('collector_no', 0.0):.4f}",
                "name_confidence": f"{metadata.field_confidence.get('card_name', 0.0):.4f}",
                "symbol_score": f"{symbol_score:.4f}",
                "symbol_second_score": f"{second_score:.4f}",
                "fallback_reason": repr(metadata.fallback_reason),
                "art_file": art_path.name,
                "board_file": board_path.name,
                "message": final_base,
            }
        )

        logger.info(
            "Saved %s -> %s and %s",
            source_ref,
            art_path.name,
            board_path.name,
        )
        return True

    def process_local_file(self, file_path: Path) -> bool:
        image = cv2.imread(str(file_path))
        if image is None:
            self._append_manifest(
                {
                    "timestamp": int(time.time()),
                    "status": "error",
                    "input_source": str(file_path),
                    "input_path": str(file_path),
                    "message": "image_read_failed",
                }
            )
            logger.error("Unable to read local image: %s", file_path)
            return False

        return self.process_image_array(image, source_ref=str(file_path.name), input_path=str(file_path))

    def run_batch(self, input_dir: Path) -> None:
        logger.info("Running in batch mode from %s", input_dir)

        files = sorted(
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        )

        processed = 0
        saved = 0
        generated_roots: List[Path] = []

        for generated_dir in (self.cards_dir, self.art_dir, self.raw_dir):
            try:
                generated_roots.append(generated_dir.resolve())
            except OSError:
                continue

        try:
            manifest_resolved = self.manifest_path.resolve()
        except OSError:
            manifest_resolved = None

        for file_path in files:
            try:
                resolved_file = file_path.resolve()
                if manifest_resolved is not None and resolved_file == manifest_resolved:
                    continue
                if any(
                    resolved_file == generated_root
                    or generated_root in resolved_file.parents
                    for generated_root in generated_roots
                ):
                    continue
            except OSError:
                pass

            processed += 1
            if self.process_local_file(file_path):
                saved += 1

        logger.info("Batch run complete: %d processed, %d saved", processed, saved)

    def run_scrape(self, max_pages: int = 5) -> None:
        logger.info("Running in scrape mode for up to %d pages", max_pages)

        saved = 0
        processed = 0

        for page_num in range(1, max_pages + 1):
            image_urls = self.scrape_page(page_num)
            if not image_urls:
                logger.info("No image URLs found on page %d; stopping", page_num)
                break

            for index, image_url in enumerate(image_urls):
                if image_url in self.downloaded_urls:
                    continue

                parsed = urlparse(image_url)
                extension = Path(parsed.path).suffix.lower()
                if extension not in SUPPORTED_IMAGE_EXTENSIONS:
                    extension = ".jpg"

                raw_file = self.raw_dir / f"raw_{page_num:03d}_{index:04d}{extension}"

                ok = self.download_image(image_url, raw_file)
                if not ok:
                    self._append_manifest(
                        {
                            "timestamp": int(time.time()),
                            "status": "error",
                            "input_source": image_url,
                            "input_path": str(raw_file),
                            "message": "download_failed",
                        }
                    )
                    continue

                self.downloaded_urls.add(image_url)
                image = cv2.imread(str(raw_file))
                if image is None:
                    self._append_manifest(
                        {
                            "timestamp": int(time.time()),
                            "status": "error",
                            "input_source": image_url,
                            "input_path": str(raw_file),
                            "message": "image_read_failed",
                        }
                    )
                    continue

                valid, reason = self._is_valid_card_candidate(image)
                if not valid:
                    self._append_manifest(
                        {
                            "timestamp": int(time.time()),
                            "status": "skipped",
                            "input_source": image_url,
                            "input_path": str(raw_file),
                            "message": reason,
                        }
                    )
                    logger.info("Skipping %s (%s)", image_url, reason)
                    processed += 1
                    continue

                if self.process_image_array(image, source_ref=image_url, input_path=str(raw_file)):
                    saved += 1

                processed += 1
                time.sleep(self.delay_between_requests)

            time.sleep(self.delay_between_requests * 2)

        logger.info("Scrape run complete: %d processed, %d saved", processed, saved)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CV-first Pokemon card scraper for EX-era artwork extraction and naming"
    )
    parser.add_argument("--mode", choices=["scrape", "batch"], default="scrape")
    parser.add_argument("--input-dir", default="", help="Input directory for batch mode")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--search-params", default="s=series%3Aex&sort=date&ord=auto")
    parser.add_argument("--min-ocr-conf", type=float, default=0.45)
    parser.add_argument("--min-symbol-conf", type=float, default=0.42)
    parser.add_argument(
        "--board-height",
        type=int,
        default=DEFAULT_OUTPUT_CARD_HEIGHT,
        help="Output height for full-card board PNGs (default: 1024)",
    )
    parser.add_argument(
        "--enhance-text",
        choices=["none", "mild"],
        default="mild",
        help="Readability enhancement strength for board PNGs",
    )
    parser.add_argument("--base-url", default="https://pkmncards.com")
    parser.add_argument("--sets-dir", default="Sets")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)

    logger.info("=" * 80)
    logger.info("Pokemon Card Scraper - CV First EX Pipeline")
    logger.info("=" * 80)

    try:
        scraper = PokemonCardScraper(
            base_url=args.base_url,
            output_dir=args.output_dir,
            search_params=args.search_params,
            sets_dir=args.sets_dir,
            min_ocr_conf=args.min_ocr_conf,
            min_symbol_conf=args.min_symbol_conf,
            output_card_height=args.board_height,
            enhance_text_mode=args.enhance_text,
            enable_ocr=True,
        )
    except Exception as exc:
        logger.error("Failed to initialize scraper: %s", exc)
        return 1

    try:
        if args.mode == "batch":
            if not args.input_dir:
                logger.error("--input-dir is required when --mode batch")
                return 1

            input_dir = Path(args.input_dir)
            if not input_dir.exists() or not input_dir.is_dir():
                logger.error("Invalid batch input directory: %s", input_dir)
                return 1

            scraper.run_batch(input_dir)
        else:
            scraper.run_scrape(max_pages=args.max_pages)

    except KeyboardInterrupt:
        logger.info("Execution interrupted by user")
        return 130
    except Exception as exc:  # pragma: no cover - top-level guard
        logger.error("Fatal runtime error: %s", exc, exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
