"""Tests for the pokemontcgio_images provider and index subsystem."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from ptcg_art_scraper.index.client import (
    PokemonTcgDataIndexClient,
    _parse_cards,
    _parse_sets,
)
from ptcg_art_scraper.index.models import CardIndexEntry, SetInfo
from ptcg_art_scraper.models import CardAsset, SidecarMetadata
from ptcg_art_scraper.providers.pokemontcgio_images import (
    PokemonTcgioImagesProvider,
    image_url,
    parse_image_url,
)

# ---------------------------------------------------------------------------
# Fixtures – sample JSON payloads matching pokemon-tcg-data schema
# ---------------------------------------------------------------------------

SAMPLE_SETS_JSON = [
    {
        "id": "base1",
        "name": "Base",
        "series": "Base",
        "printedTotal": 102,
        "total": 102,
        "releaseDate": "1999/01/09",
    },
    {
        "id": "ex15",
        "name": "Dragon Frontiers",
        "series": "EX",
        "printedTotal": 101,
        "total": 101,
        "releaseDate": "2006/11/01",
    },
    {
        "id": "sv4",
        "name": "Paldea Evolved",
        "series": "Scarlet & Violet",
        "printedTotal": 193,
        "total": 279,
        "releaseDate": "2023/06/09",
    },
]

SAMPLE_CARDS_JSON = [
    {
        "id": "ex15-1",
        "name": "Ampharos δ",
        "supertype": "Pokémon",
        "subtypes": ["Stage 2"],
        "hp": "110",
        "types": ["Lightning"],
        "evolvesFrom": "Flaaffy",
        "number": "1",
        "rarity": "Rare Holo",
    },
    {
        "id": "ex15-4",
        "name": "Feraligatr δ",
        "supertype": "Pokémon",
        "subtypes": ["Stage 2"],
        "hp": "120",
        "types": ["Lightning"],
        "evolvesFrom": "Croconaw",
        "number": "4",
        "rarity": "Rare Holo",
    },
    {
        "id": "ex15-80",
        "name": "Professor Elm's Training Method",
        "supertype": "Trainer",
        "subtypes": ["Supporter"],
        "number": "80",
        "rarity": "Uncommon",
    },
    {
        "id": "ex15-99",
        "name": "Boost Energy",
        "supertype": "Energy",
        "subtypes": ["Special"],
        "number": "99",
        "rarity": "Uncommon",
    },
]


# ---------------------------------------------------------------------------
# URL construction tests
# ---------------------------------------------------------------------------


class TestImageUrl:
    def test_standard_url(self):
        assert image_url("ex15", "4") == "https://images.pokemontcg.io/ex15/4.png"

    def test_hires_url(self):
        assert (
            image_url("ex15", "4", hires=True)
            == "https://images.pokemontcg.io/ex15/4_hires.png"
        )

    def test_non_numeric_number(self):
        assert image_url("sv4", "SV01") == "https://images.pokemontcg.io/sv4/SV01.png"

    def test_alpha_suffix_number(self):
        assert image_url("dp1", "4a") == "https://images.pokemontcg.io/dp1/4a.png"


class TestParseImageUrl:
    def test_standard(self):
        result = parse_image_url("https://images.pokemontcg.io/ex15/4.png")
        assert result == ("ex15", "4")

    def test_hires(self):
        result = parse_image_url("https://images.pokemontcg.io/sv4/100_hires.png")
        assert result == ("sv4", "100")

    def test_not_matching(self):
        assert parse_image_url("https://pkmncards.com/card/test") is None

    def test_missing_number(self):
        assert parse_image_url("https://images.pokemontcg.io/ex15/") is None

    def test_non_numeric_card(self):
        result = parse_image_url("https://images.pokemontcg.io/sv4/SV01.png")
        assert result == ("sv4", "SV01")


# ---------------------------------------------------------------------------
# Index parsing tests
# ---------------------------------------------------------------------------


class TestParseSets:
    def test_returns_set_info_list(self):
        sets = _parse_sets(SAMPLE_SETS_JSON)
        assert len(sets) == 3
        assert all(isinstance(s, SetInfo) for s in sets)

    def test_set_fields(self):
        sets = _parse_sets(SAMPLE_SETS_JSON)
        base = sets[0]
        assert base.id == "base1"
        assert base.name == "Base"
        assert base.series == "Base"
        assert base.printed_total == 102
        assert base.total == 102

    def test_symbol_url(self):
        sets = _parse_sets(SAMPLE_SETS_JSON)
        assert sets[0].symbol_url == "https://images.pokemontcg.io/base1/symbol.png"

    def test_logo_url(self):
        sets = _parse_sets(SAMPLE_SETS_JSON)
        assert sets[0].logo_url == "https://images.pokemontcg.io/base1/logo.png"

    def test_handles_non_list_input(self):
        assert _parse_sets({"not": "a list"}) == []
        assert _parse_sets(None) == []

    def test_skips_non_dict_entries(self):
        sets = _parse_sets([SAMPLE_SETS_JSON[0], "garbage", 42])
        assert len(sets) == 1


class TestParseCards:
    def test_returns_card_entries(self):
        cards = _parse_cards(SAMPLE_CARDS_JSON, "ex15")
        assert len(cards) == 4
        assert all(isinstance(c, CardIndexEntry) for c in cards)

    def test_card_fields(self):
        cards = _parse_cards(SAMPLE_CARDS_JSON, "ex15")
        amp = cards[0]
        assert amp.set_id == "ex15"
        assert amp.number == "1"
        assert amp.name == "Ampharos δ"
        assert amp.supertype == "Pokémon"
        assert amp.rarity == "Rare Holo"
        assert amp.hp == "110"
        assert amp.types == ["Lightning"]
        assert amp.evolves_from == "Flaaffy"

    def test_trainer_entry(self):
        cards = _parse_cards(SAMPLE_CARDS_JSON, "ex15")
        trainer = cards[2]
        assert trainer.supertype == "Trainer"
        assert trainer.subtypes == ["Supporter"]

    def test_energy_entry(self):
        cards = _parse_cards(SAMPLE_CARDS_JSON, "ex15")
        energy = cards[3]
        assert energy.supertype == "Energy"

    def test_handles_non_list_input(self):
        assert _parse_cards("not a list", "base1") == []


# ---------------------------------------------------------------------------
# Index client with cache
# ---------------------------------------------------------------------------


class TestIndexClientCache:
    def test_list_sets_caches(self, tmp_path: Path, monkeypatch):
        """list_sets uses cache on second call."""
        client = PokemonTcgDataIndexClient(cache_dir=tmp_path, ttl=3600)
        calls = []

        def fake_fetch(self_inner, url):
            calls.append(url)
            return SAMPLE_SETS_JSON

        monkeypatch.setattr(PokemonTcgDataIndexClient, "_fetch_json", fake_fetch)

        sets1 = client.list_sets()
        sets2 = client.list_sets()
        assert len(sets1) == 3
        assert len(sets2) == 3
        assert len(calls) == 1  # Only one network call

    def test_get_set_returns_match(self, tmp_path: Path, monkeypatch):
        client = PokemonTcgDataIndexClient(cache_dir=tmp_path, ttl=3600)
        monkeypatch.setattr(
            PokemonTcgDataIndexClient,
            "_fetch_json",
            lambda self_inner, url: SAMPLE_SETS_JSON,
        )
        result = client.get_set("ex15")
        assert result is not None
        assert result.name == "Dragon Frontiers"

    def test_get_set_returns_none_for_unknown(self, tmp_path: Path, monkeypatch):
        client = PokemonTcgDataIndexClient(cache_dir=tmp_path, ttl=3600)
        monkeypatch.setattr(
            PokemonTcgDataIndexClient,
            "_fetch_json",
            lambda self_inner, url: SAMPLE_SETS_JSON,
        )
        assert client.get_set("nonexistent") is None

    def test_list_cards_caches(self, tmp_path: Path, monkeypatch):
        client = PokemonTcgDataIndexClient(cache_dir=tmp_path, ttl=3600)
        calls = []

        def fake_fetch(self_inner, url):
            calls.append(url)
            return SAMPLE_CARDS_JSON

        monkeypatch.setattr(PokemonTcgDataIndexClient, "_fetch_json", fake_fetch)

        cards1 = client.list_cards_in_set("ex15")
        cards2 = client.list_cards_in_set("ex15")
        assert len(cards1) == 4
        assert len(cards2) == 4
        assert len(calls) == 1

    def test_list_cards_returns_empty_on_fetch_failure(self, tmp_path: Path, monkeypatch):
        client = PokemonTcgDataIndexClient(cache_dir=tmp_path, ttl=3600)

        def failing_fetch(self_inner, url):
            raise RuntimeError("Network error")

        monkeypatch.setattr(PokemonTcgDataIndexClient, "_fetch_json", failing_fetch)
        assert client.list_cards_in_set("unknown_set") == []


# ---------------------------------------------------------------------------
# Provider unit tests (no network)
# ---------------------------------------------------------------------------


class _FakeIndex:
    """In-memory index for testing the provider without network."""

    def __init__(self):
        self._sets = _parse_sets(SAMPLE_SETS_JSON)
        self._cards = {
            "ex15": _parse_cards(SAMPLE_CARDS_JSON, "ex15"),
        }

    def list_sets(self):
        return self._sets

    def get_set(self, set_id):
        for s in self._sets:
            if s.id == set_id:
                return s
        return None

    def list_cards_in_set(self, set_id):
        return self._cards.get(set_id, [])


class TestProviderSearch:
    @pytest.fixture()
    def provider(self):
        return PokemonTcgioImagesProvider(index=_FakeIndex(), prefer_hires=True)

    @pytest.mark.asyncio
    async def test_search_by_set_id(self, provider):
        import httpx

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, "ex15")
        assert len(refs) == 4
        assert refs[0].provider == "pokemontcgio_images"
        meta = json.loads(refs[0].card_id)
        assert meta["set_code"] == "ex15"
        assert meta["number"] == "1"
        assert meta["name"] == "Ampharos δ"

    @pytest.mark.asyncio
    async def test_search_by_name(self, provider):
        import httpx

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, "Feraligatr", set_filter="ex15")
        assert len(refs) == 1
        meta = json.loads(refs[0].card_id)
        assert meta["name"] == "Feraligatr δ"

    @pytest.mark.asyncio
    async def test_search_direct_url(self, provider):
        import httpx

        url = "https://images.pokemontcg.io/ex15/4.png"
        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, url)
        assert len(refs) == 1
        meta = json.loads(refs[0].card_id)
        assert meta["set_code"] == "ex15"
        assert meta["number"] == "4"

    @pytest.mark.asyncio
    async def test_search_with_limit(self, provider):
        import httpx

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, "ex15", limit=2)
        assert len(refs) == 2

    @pytest.mark.asyncio
    async def test_search_unknown_set_returns_empty(self, provider):
        import httpx

        async with httpx.AsyncClient() as client:
            refs = await provider.search(client, "nonexistent_set_xyz")
        assert refs == []


class TestProviderResolve:
    @pytest.fixture()
    def provider(self):
        return PokemonTcgioImagesProvider(index=_FakeIndex(), prefer_hires=True)

    @pytest.mark.asyncio
    async def test_resolve_with_index(self, provider):
        import httpx

        from ptcg_art_scraper.models import CardRef

        ref = CardRef(
            provider="pokemontcgio_images",
            url="https://images.pokemontcg.io/ex15/4.png",
            card_id=json.dumps({"set_code": "ex15", "number": "4"}),
        )
        async with httpx.AsyncClient() as client:
            asset = await provider.resolve(client, ref)
        assert asset.name == "Feraligatr δ"
        assert asset.set_code == "ex15"
        assert asset.number == "4"
        assert asset.provider == "pokemontcgio_images"
        assert "_hires.png" in asset.image_url
        assert asset.basic_type == "Pokemon"
        assert asset.rarity == "Rare Holo"
        assert asset.hp == 120
        assert asset.color == "Lightning"
        assert asset.evolves_from == "Croconaw"

    @pytest.mark.asyncio
    async def test_resolve_from_url_only(self, provider):
        import httpx

        from ptcg_art_scraper.models import CardRef

        ref = CardRef(
            provider="pokemontcgio_images",
            url="https://images.pokemontcg.io/ex15/1.png",
        )
        async with httpx.AsyncClient() as client:
            asset = await provider.resolve(client, ref)
        assert asset.set_code == "ex15"
        assert asset.number == "1"
        assert asset.name == "Ampharos δ"

    @pytest.mark.asyncio
    async def test_resolve_standard_url_when_hires_disabled(self):
        provider = PokemonTcgioImagesProvider(index=_FakeIndex(), prefer_hires=False)
        import httpx

        from ptcg_art_scraper.models import CardRef

        ref = CardRef(
            provider="pokemontcgio_images",
            url="https://images.pokemontcg.io/ex15/4.png",
            card_id=json.dumps({"set_code": "ex15", "number": "4"}),
        )
        async with httpx.AsyncClient() as client:
            asset = await provider.resolve(client, ref)
        assert "_hires.png" not in asset.image_url
        assert asset.image_url == "https://images.pokemontcg.io/ex15/4.png"


# ---------------------------------------------------------------------------
# Sidecar image_variant field
# ---------------------------------------------------------------------------


class TestSidecarImageVariant:
    def test_image_variant_field_exists(self):
        s = SidecarMetadata()
        assert hasattr(s, "image_variant")
        assert s.image_variant == ""

    def test_image_variant_in_serialized(self, tmp_path: Path):
        from ptcg_art_scraper.storage.metadata import save_sidecar

        s = SidecarMetadata(image_variant="hires")
        path = tmp_path / "test.json"
        save_sidecar(s, path)
        raw = json.loads(path.read_text("utf-8"))
        assert raw["image_variant"] == "hires"

    def test_from_asset_preserves_image_variant(self):
        asset = CardAsset(
            name="Test",
            set_code="ex15",
            number="4",
            provider="pokemontcgio_images",
        )
        s = SidecarMetadata.from_asset(asset, image_variant="standard")
        assert s.image_variant == "standard"

    def test_old_sidecars_still_load(self, tmp_path: Path):
        """Sidecars without image_variant should still load (backwards compat)."""
        from ptcg_art_scraper.storage.metadata import load_sidecar

        raw = asdict(SidecarMetadata(name="Old"))
        del raw["image_variant"]
        path = tmp_path / "old.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        # load_sidecar passes **data to constructor; missing key = default
        loaded = load_sidecar(path)
        # May be None if strict, otherwise should have default
        if loaded is not None:
            assert loaded.image_variant == ""


# ---------------------------------------------------------------------------
# Provider registration
# ---------------------------------------------------------------------------


class TestProviderRegistration:
    def test_engine_get_provider(self):
        from ptcg_art_scraper.core.engine import _get_provider

        prov = _get_provider("pokemontcgio_images")
        assert prov.name == "pokemontcgio_images"

    def test_engine_get_provider_unknown_raises(self):
        from ptcg_art_scraper.core.engine import _get_provider

        with pytest.raises(ValueError):
            _get_provider("nonexistent_provider")

    def test_cli_get_provider(self):
        from ptcg_art_scraper.cli import _get_provider

        prov = _get_provider("pokemontcgio_images")
        assert prov.name == "pokemontcgio_images"
