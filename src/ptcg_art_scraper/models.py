"""Compatibility exports for scraper data models."""

from ptcg_art_scraper.core.models import (
    CardAsset,
    CardIdentifier,
    CardRef,
    FetchedImage,
    NormalizedResult,
    SidecarMetadata,
)

__all__ = [
    "CardAsset",
    "CardIdentifier",
    "CardRef",
    "FetchedImage",
    "NormalizedResult",
    "SidecarMetadata",
]
