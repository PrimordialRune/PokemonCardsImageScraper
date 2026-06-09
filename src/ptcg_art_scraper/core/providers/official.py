"""Official asset provider wrapper."""

from __future__ import annotations

import httpx

from ptcg_art_scraper.core.models import CardAsset, CardIdentifier, ProviderCandidate
from ptcg_art_scraper.core.providers.base import ImageProvider
from ptcg_art_scraper.net.http import RateLimiter
from ptcg_art_scraper.providers.pokemon_official import image_url


class PokemonOfficialProvider(ImageProvider):
    name = "pokemon_official"

    async def resolve(
        self,
        client: httpx.AsyncClient,
        card: CardIdentifier,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> ProviderCandidate | None:
        del client, rate_limiter
        if not card.set_code or not card.card_number:
            return None
        url = image_url(card.set_code, card.card_number)
        asset = CardAsset(
            name=f"{card.set_code}-{card.card_number}",
            set_name=card.set_code,
            set_code=card.set_code,
            number=card.card_number,
            provider=self.name,
            source_page_url=url,
            image_url=url,
        )
        return ProviderCandidate(provider=self.name, asset=asset, candidate_urls=(url,))
