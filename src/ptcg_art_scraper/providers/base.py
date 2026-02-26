"""Abstract provider interface."""

from __future__ import annotations

import abc

import httpx

from ptcg_art_scraper.models import CardAsset, CardAssetStub, CardRef, FetchedImage, SetRef
from ptcg_art_scraper.net.http import RateLimiter


class BaseProvider(abc.ABC):
    """All card-image providers implement this interface."""

    name: str = "base"

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

    # -- Optional set-completion capabilities -------------------------------

    supports_set_completion: bool = False

    async def list_sets(
        self,
        client: httpx.AsyncClient,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> list[SetRef]:
        """Return all sets known to this provider.

        Override when :attr:`supports_set_completion` is ``True``.
        """
        return []

    async def get_set_cards(
        self,
        client: httpx.AsyncClient,
        set_id: str,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> list[CardAssetStub]:
        """Return stub info for every card in *set_id*.

        Override when :attr:`supports_set_completion` is ``True``.
        """
        return []
