"""Data models for the scraper."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class CardRef:
    """Lightweight reference to a card – a URL or provider-specific ID."""

    provider: str
    url: str
    card_id: str = ""


@dataclass
class CardAsset:
    """Structured metadata about a card plus its image URL."""

    name: str
    set_name: str = ""
    set_code: str = ""
    number: str = ""
    rarity: str = ""
    artist: str = ""
    year: str = ""
    source_page_url: str = ""
    image_url: str = ""
    provider: str = ""


@dataclass
class FetchedImage:
    """Raw image data returned by a provider."""

    data: bytes
    mime_type: str = "image/png"
    source_url: str = ""

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass
class NormalizedResult:
    """Result of normalizing an image."""

    output_path: str
    width: int = 750
    height: int = 1050
    dpi: int = 300
    original_width: int = 0
    original_height: int = 0
    sha256_original: str = ""
    sha256_normalized: str = ""
    format: str = "png"


@dataclass
class SidecarMetadata:
    """JSON sidecar saved next to each normalized image."""

    provider: str = ""
    source_page_url: str = ""
    source_image_url: str = ""
    fetched_at_utc: str = ""
    normalized_size: list[int] = field(default_factory=lambda: [750, 1050])
    dpi: int = 300
    original_size: list[int] = field(default_factory=list)
    sha256_original: str = ""
    sha256_normalized: str = ""

    @staticmethod
    def now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()
