"""Configuration models used by the resolver and batch scraper."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ptcg_art_scraper.core.providers.registry import DEFAULT_PROVIDER_PRIORITY


@dataclass(slots=True)
class ResolverConfig:
    """Controls provider ordering and URL validation."""

    provider_priority: tuple[str, ...] = DEFAULT_PROVIDER_PRIORITY
    verify_urls: bool = True
    timeout: float = 20.0
    rate: float = 2.0


@dataclass(slots=True)
class BatchScrapeConfig:
    """Configuration for a batch scrape run."""

    output_dir: Path
    image_format: str = "png"
    concurrency: int = 8
    rate: float = 2.0
    timeout: float = 20.0
    retries: int = 3
    overwrite: bool = False
    folder_template: str = ""
    provider_priority: tuple[str, ...] = field(default_factory=lambda: DEFAULT_PROVIDER_PRIORITY)
    verify_urls: bool = True
