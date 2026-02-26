"""Data models used across the scraper."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CardRef:
    """Lightweight reference to a card – a URL or provider-specific id."""

    provider: str
    url: str
    id: Optional[str] = None  # noqa: A003


@dataclass
class CardAsset:
    """Structured metadata for a resolved card."""

    name: str
    set_name: str
    set_code: Optional[str]
    number: Optional[str]
    rarity: Optional[str] = None
    artist: Optional[str] = None
    year: Optional[str] = None
    source_page_url: str = ""
    image_url: str = ""
    provider: str = ""


@dataclass
class FetchedImage:
    """Raw downloaded image bytes with metadata."""

    data: bytes
    mime_type: str
    source_url: str
    card_asset: CardAsset


@dataclass
class NormalizedResult:
    """Result of normalization."""

    image_path: str
    json_path: str
    original_size: tuple[int, int]
    normalized_size: tuple[int, int] = (750, 1050)
    dpi: int = 300
    sha256_original: str = ""
    sha256_normalized: str = ""


@dataclass
class ScrapeStats:
    """Aggregate statistics for a scrape run."""

    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
