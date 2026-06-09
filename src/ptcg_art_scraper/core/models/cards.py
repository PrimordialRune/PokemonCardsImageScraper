"""Card, resolution, and batch result models."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class CardIdentifier:
    """Unique card identity used by the new batch pipeline."""

    set_code: str
    card_number: str

    @property
    def label(self) -> str:
        return f"{self.set_code} #{self.card_number}"


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
    basic_type: str = ""
    specific_type: str = ""
    evolves_from: str = ""
    hp: int = 0
    color: str = ""
    attacks: list = field(default_factory=list)
    abilities: list = field(default_factory=list)
    traits: list = field(default_factory=list)
    weaknesses: dict = field(default_factory=dict)
    resistances: dict = field(default_factory=dict)
    retreat_cost: int = 0


@dataclass
class FetchedImage:
    """Raw image data returned by a provider or downloader."""

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
    name: str = ""
    set: str = ""
    setId: str = ""
    number: str = ""
    basicType: str = ""
    specificType: str = ""
    evolvesFrom: str = ""
    color: str = ""
    rarity: str = ""
    hp: int = 0
    attacks: list = field(default_factory=list)
    abilities: list = field(default_factory=list)
    traits: list = field(default_factory=list)
    weaknesses: dict = field(default_factory=dict)
    resistances: dict = field(default_factory=dict)
    retreatCost: int = 0
    normalized_output_path: str = ""
    image_variant: str = ""
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def from_asset(cls, asset: CardAsset, **kwargs: object) -> "SidecarMetadata":
        return cls(
            provider=asset.provider,
            source_page_url=asset.source_page_url,
            source_image_url=asset.image_url,
            name=asset.name,
            set=asset.set_name,
            setId=asset.set_code,
            number=asset.number,
            basicType=asset.basic_type,
            specificType=asset.specific_type,
            evolvesFrom=asset.evolves_from,
            color=asset.color,
            rarity=asset.rarity,
            hp=asset.hp,
            attacks=list(asset.attacks),
            abilities=list(asset.abilities),
            traits=list(asset.traits),
            weaknesses=dict(asset.weaknesses),
            resistances=dict(asset.resistances),
            retreatCost=asset.retreat_cost,
            **kwargs,  # type: ignore[arg-type]
        )


@dataclass(slots=True)
class ProviderAttempt:
    """One provider attempt recorded by the resolver."""

    provider: str
    status: str
    detail: str = ""
    url: str = ""


@dataclass(slots=True)
class ProviderCandidate:
    """Provider-returned candidate data before final selection."""

    provider: str
    asset: CardAsset
    candidate_urls: tuple[str, ...]


@dataclass(slots=True)
class ResolvedImage:
    """Final resolver output including trace information."""

    card: CardIdentifier
    asset: CardAsset
    attempts: list[ProviderAttempt] = field(default_factory=list)

    @property
    def resolved_url(self) -> str:
        return self.asset.image_url

    @property
    def provider(self) -> str:
        return self.asset.provider


@dataclass(slots=True)
class BatchItemResult:
    """Final result for a single batch item."""

    card: CardIdentifier
    status: str
    provider: str = ""
    resolved_url: str = ""
    output_path: str = ""
    sidecar_path: str = ""
    error: str = ""
    attempts: list[ProviderAttempt] = field(default_factory=list)


@dataclass(slots=True)
class BatchSummary:
    """Aggregate summary for a scrape batch."""

    total: int
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[BatchItemResult] = field(default_factory=list)
