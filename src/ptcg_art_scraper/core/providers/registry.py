"""Provider registry for the layered resolver."""

from __future__ import annotations

from collections.abc import Callable

from ptcg_art_scraper.core.providers.base import ImageProvider
from ptcg_art_scraper.core.providers.official import PokemonOfficialProvider
from ptcg_art_scraper.core.providers.pkmncards import PkmnCardsResolutionProvider
from ptcg_art_scraper.core.providers.pokemontcgio import PokemonTcgioProvider

DEFAULT_PROVIDER_PRIORITY = (
    "pokemon_official",
    "pokemontcgio_images",
    "pkmncards",
)

_PROVIDER_FACTORIES: dict[str, Callable[[], ImageProvider]] = {
    "pokemon_official": PokemonOfficialProvider,
    "pokemontcgio_images": PokemonTcgioProvider,
    "pkmncards": PkmnCardsResolutionProvider,
}


def provider_names() -> list[str]:
    return list(_PROVIDER_FACTORIES)


def create_provider(name: str) -> ImageProvider:
    try:
        return _PROVIDER_FACTORIES[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {name!r}") from exc
