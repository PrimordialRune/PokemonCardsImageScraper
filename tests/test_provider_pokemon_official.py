"""Tests for the official Pokemon asset provider."""

from __future__ import annotations

import json

import httpx
import pytest

from ptcg_art_scraper.cli import _get_provider as cli_get_provider
from ptcg_art_scraper.core.engine import _get_provider as engine_get_provider
from ptcg_art_scraper.providers import PROVIDER_PRIORITY, resolve_image_url
from ptcg_art_scraper.providers.pokemon_official import (
    PokemonOfficialAssetProvider,
    image_url,
    parse_image_url,
)


class TestImageUrl:
    def test_builds_official_asset_url(self) -> None:
        assert image_url("EX6", "10") == (
            "https://assets.pokemon.com/static-assets/content-assets/"
            "cms2/img/cards/web/EX6/EX6_EN_10.png"
        )

    def test_preserves_string_card_numbers(self) -> None:
        assert image_url("EX15", "4a").endswith("/EX15/EX15_EN_4a.png")


class TestParseImageUrl:
    def test_parses_official_asset_url(self) -> None:
        parsed = parse_image_url(
            "https://assets.pokemon.com/static-assets/content-assets/"
            "cms2/img/cards/web/EX6/EX6_EN_10.png"
        )
        assert parsed == ("EX6", "10")

    def test_rejects_non_matching_url(self) -> None:
        assert parse_image_url("https://example.com/card.png") is None


class TestProvider:
    def test_get_image_url_returns_none_without_required_fields(self) -> None:
        provider = PokemonOfficialAssetProvider()

        assert provider.get_image_url("", "10") is None
        assert provider.get_image_url("EX6", "") is None

    @pytest.mark.asyncio
    async def test_search_requires_set_filter(self) -> None:
        provider = PokemonOfficialAssetProvider()

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, "10")

        assert refs == []

    @pytest.mark.asyncio
    async def test_search_builds_ref_from_set_and_number(self) -> None:
        provider = PokemonOfficialAssetProvider()

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, "10", set_filter="EX6")

        assert len(refs) == 1
        ref = refs[0]
        meta = json.loads(ref.card_id)
        assert ref.provider == "pokemon_official"
        assert ref.url.endswith("/EX6/EX6_EN_10.png")
        assert meta["set_code"] == "EX6"
        assert meta["number"] == "10"

    @pytest.mark.asyncio
    async def test_search_accepts_direct_asset_url(self) -> None:
        provider = PokemonOfficialAssetProvider()
        url = (
            "https://assets.pokemon.com/static-assets/content-assets/"
            "cms2/img/cards/web/EX6/EX6_EN_10.png"
        )

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, url)

        assert len(refs) == 1
        assert refs[0].url == url

    @pytest.mark.asyncio
    async def test_resolve_uses_metadata_hints(self) -> None:
        provider = PokemonOfficialAssetProvider()

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, "10", set_filter="EX6")
            asset = await provider.resolve(client, refs[0])

        assert asset.provider == "pokemon_official"
        assert asset.set_name == "EX6"
        assert asset.set_code == "EX6"
        assert asset.number == "10"
        assert asset.image_url.endswith("/EX6/EX6_EN_10.png")

    @pytest.mark.asyncio
    async def test_resolve_parses_direct_url(self) -> None:
        provider = PokemonOfficialAssetProvider()
        url = (
            "https://assets.pokemon.com/static-assets/content-assets/"
            "cms2/img/cards/web/EX6/EX6_EN_10.png"
        )

        async with httpx.AsyncClient() as client:
            asset = await provider.resolve(client, ref=provider._build_ref("EX6", "10", url=url))

        assert asset.set_code == "EX6"
        assert asset.number == "10"


class TestPriorityResolution:
    def test_default_priority_prefers_official_provider(self) -> None:
        assert PROVIDER_PRIORITY[0] == "pokemon_official"
        assert resolve_image_url("EX6", "10") == (
            "https://assets.pokemon.com/static-assets/content-assets/"
            "cms2/img/cards/web/EX6/EX6_EN_10.png"
        )

    def test_explicit_priority_can_choose_another_provider(self) -> None:
        assert resolve_image_url(
            "ex15",
            "4",
            provider_priority=["pokemontcgio_images", "pokemon_official"],
        ) == "https://images.pokemontcg.io/ex15/4_hires.png"

    def test_priority_returns_none_when_no_provider_can_construct_url(self) -> None:
        assert resolve_image_url("EX6", "10", provider_priority=["pkmncards"]) is None


class TestProviderRegistration:
    def test_engine_get_provider(self) -> None:
        assert engine_get_provider("pokemon_official").name == "pokemon_official"

    def test_cli_get_provider(self) -> None:
        assert cli_get_provider("pokemon_official").name == "pokemon_official"
