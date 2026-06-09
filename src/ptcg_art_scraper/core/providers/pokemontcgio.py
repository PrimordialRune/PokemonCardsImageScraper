"""PokemonTCG.io image provider wrapper."""

from __future__ import annotations

import logging

import httpx

from ptcg_art_scraper.core.models import CardAsset, CardIdentifier, ProviderCandidate
from ptcg_art_scraper.core.providers.base import ImageProvider
from ptcg_art_scraper.index.client import PokemonTcgDataIndexClient
from ptcg_art_scraper.net.http import RateLimiter
from ptcg_art_scraper.providers.pokemontcgio_images import (
    _basic_type_from_supertype,
    _specific_type_from_subtypes,
    image_url,
)

logger = logging.getLogger(__name__)


class PokemonTcgioProvider(ImageProvider):
    name = "pokemontcgio_images"

    def __init__(self, *, prefer_hires: bool = True) -> None:
        self._prefer_hires = prefer_hires
        self._index = PokemonTcgDataIndexClient()

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

        set_info = self._index.get_set(card.set_code)
        asset = CardAsset(
            name=f"{card.set_code}-{card.card_number}",
            set_name=set_info.name if set_info else card.set_code,
            set_code=card.set_code,
            number=card.card_number,
            provider=self.name,
        )

        for entry in self._index.list_cards_in_set(card.set_code):
            if entry.number != card.card_number:
                continue
            asset.name = entry.name
            asset.rarity = entry.rarity
            asset.basic_type = _basic_type_from_supertype(entry.supertype)
            asset.specific_type = _specific_type_from_subtypes(entry.subtypes)
            asset.evolves_from = entry.evolves_from
            if entry.hp.isdigit():
                asset.hp = int(entry.hp)
            elif entry.hp:
                logger.warning(
                    "Unexpected HP value %r for %s #%s",
                    entry.hp,
                    card.set_code,
                    card.card_number,
                )
                asset.hp = 0
            asset.color = entry.types[0] if entry.types else ""
            break

        preferred = image_url(card.set_code, card.card_number, hires=self._prefer_hires)
        fallback = image_url(card.set_code, card.card_number, hires=False)
        asset.image_url = preferred
        asset.source_page_url = preferred
        candidate_urls = (preferred, fallback) if preferred != fallback else (preferred,)
        return ProviderCandidate(provider=self.name, asset=asset, candidate_urls=candidate_urls)
