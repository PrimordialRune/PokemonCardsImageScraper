"""Abstract base provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from ptcg_art_scraper.models import CardAsset, CardRef, FetchedImage
from ptcg_art_scraper.net.http import HttpClient


class BaseProvider(ABC):
    """Interface that every scraping provider must implement."""

    name: str = ""

    @abstractmethod
    async def search(
        self,
        client: HttpClient,
        query: str,
        *,
        set_filter: Optional[str] = None,
        limit: int = 50,
    ) -> Sequence[CardRef]:
        """Return lightweight references matching *query*."""

    @abstractmethod
    async def resolve(
        self, client: HttpClient, ref: CardRef
    ) -> CardAsset:
        """Resolve a :class:`CardRef` into a full :class:`CardAsset`."""

    @abstractmethod
    async def fetch_image(
        self, client: HttpClient, asset: CardAsset
    ) -> FetchedImage:
        """Download the image bytes for *asset*."""
