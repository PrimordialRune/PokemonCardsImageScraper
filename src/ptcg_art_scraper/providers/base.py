"""Abstract provider interface."""

from __future__ import annotations

import abc

import httpx

from ptcg_art_scraper.models import CardAsset, CardRef, FetchedImage
from ptcg_art_scraper.net.http import RateLimiter


class BaseProvider(abc.ABC):
    """All card-image providers implement this interface."""

    name: str = "base"

    def get_image_url(self, set_code: str, card_number: str) -> str | None:
        """Deterministically resolve a card image URL when supported."""
        return None

    @abc.abstractmethod
    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        set_filter: str = "",
        limit: int = 0,
        rate_limiter: RateLimiter | None = None,
    ) -> list[CardRef]:
        """Return lightweight card references matching *query*."""

    @abc.abstractmethod
    async def resolve(
        self,
        client: httpx.AsyncClient,
        ref: CardRef,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> CardAsset:
        """Resolve a :class:`CardRef` into full :class:`CardAsset` metadata."""

    @abc.abstractmethod
    async def fetch_image(
        self,
        client: httpx.AsyncClient,
        asset: CardAsset,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> FetchedImage:
        """Download the card image bytes."""
