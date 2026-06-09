"""Standardized provider contract for URL resolution."""

from __future__ import annotations

import abc

import httpx

from ptcg_art_scraper.core.models import CardIdentifier, ProviderCandidate
from ptcg_art_scraper.net.http import RateLimiter


class ImageProvider(abc.ABC):
    """Providers only return candidate URLs plus minimal metadata."""

    name: str

    @abc.abstractmethod
    async def resolve(
        self,
        client: httpx.AsyncClient,
        card: CardIdentifier,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> ProviderCandidate | None:
        """Return candidate URLs for *card*, or ``None`` when unsupported."""
