"""Provider registry and priority helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from ptcg_art_scraper.providers.base import BaseProvider
from ptcg_art_scraper.providers.pkmncards import PkmnCardsProvider
from ptcg_art_scraper.providers.pokemon_official import PokemonOfficialAssetProvider
from ptcg_art_scraper.providers.pokemontcgio_images import PokemonTcgioImagesProvider

logger = logging.getLogger(__name__)

PROVIDER_PRIORITY = [
    "pokemon_official",
    "pokemontcgio_images",
    "pkmncards",
]

_PROVIDER_FACTORIES: dict[str, Callable[[], BaseProvider]] = {
    "pkmncards": PkmnCardsProvider,
    "pokemontcgio_images": PokemonTcgioImagesProvider,
    "pokemon_official": PokemonOfficialAssetProvider,
}


def provider_names() -> list[str]:
    """Return the known provider names."""
    return list(_PROVIDER_FACTORIES)


def get_provider(name: str) -> BaseProvider:
    """Resolve a provider by name."""
    try:
        return _PROVIDER_FACTORIES[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {name!r}") from exc


def resolve_image_url(
    set_code: str,
    card_number: str,
    *,
    provider_priority: Sequence[str] | None = None,
) -> str | None:
    """Resolve a card image URL by provider priority."""
    cleaned_set = str(set_code).strip()
    cleaned_number = str(card_number).strip()
    if not cleaned_set or not cleaned_number:
        logger.info(
            "Provider priority resolution failed deterministically: missing set code or card number"
        )
        return None

    for provider_name in provider_priority or PROVIDER_PRIORITY:
        logger.info(
            "Attempting provider %s for set_code=%s card_number=%s",
            provider_name,
            cleaned_set,
            cleaned_number,
        )
        provider = get_provider(provider_name)
        url = provider.get_image_url(cleaned_set, cleaned_number)
        if url:
            logger.info(
                "Provider %s succeeded for set_code=%s card_number=%s",
                provider_name,
                cleaned_set,
                cleaned_number,
            )
            return url
        logger.info(
            "Provider %s failed for set_code=%s card_number=%s",
            provider_name,
            cleaned_set,
            cleaned_number,
        )

    logger.info(
        "No provider resolved set_code=%s card_number=%s",
        cleaned_set,
        cleaned_number,
    )
    return None
