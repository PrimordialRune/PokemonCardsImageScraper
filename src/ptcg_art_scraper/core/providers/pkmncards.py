"""PkmnCards provider wrapper for the layered resolver."""

from __future__ import annotations

import httpx

from ptcg_art_scraper.core.models import CardIdentifier, ProviderCandidate
from ptcg_art_scraper.core.providers.base import ImageProvider
from ptcg_art_scraper.net.http import RateLimiter
from ptcg_art_scraper.providers.pkmncards import PkmnCardsProvider


class PkmnCardsResolutionProvider(ImageProvider):
    name = "pkmncards"

    def __init__(self) -> None:
        self._provider = PkmnCardsProvider()

    async def resolve(
        self,
        client: httpx.AsyncClient,
        card: CardIdentifier,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> ProviderCandidate | None:
        refs = await self._provider.search(
            client,
            card.card_number,
            set_filter=card.set_code,
            limit=1,
            rate_limiter=rate_limiter,
        )
        if not refs:
            return None
        asset = await self._provider.resolve(client, refs[0], rate_limiter=rate_limiter)
        return ProviderCandidate(
            provider=self.name,
            asset=asset,
            candidate_urls=(asset.image_url,) if asset.image_url else (),
        )
