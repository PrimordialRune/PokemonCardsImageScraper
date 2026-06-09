"""Compatibility registry wrappers around the new layered providers."""

from __future__ import annotations

from collections.abc import Sequence

from ptcg_art_scraper.core.config import ResolverConfig
from ptcg_art_scraper.core.providers import DEFAULT_PROVIDER_PRIORITY, create_provider, provider_names
from ptcg_art_scraper.core.services import ImageResolutionService

PROVIDER_PRIORITY = list(DEFAULT_PROVIDER_PRIORITY)


def get_provider(name: str):
    return create_provider(name)


def resolve_image_url(
    set_code: str,
    card_number: str,
    *,
    provider_priority: Sequence[str] | None = None,
) -> str | None:
    service = ImageResolutionService(
        ResolverConfig(
            provider_priority=tuple(provider_priority or DEFAULT_PROVIDER_PRIORITY),
            verify_urls=False,
        )
    )
    return service.resolve(set_code, card_number)


__all__ = ["PROVIDER_PRIORITY", "get_provider", "provider_names", "resolve_image_url"]
