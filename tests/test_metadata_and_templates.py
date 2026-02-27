"""Tests for rich metadata extraction, template engine, and sidecar correctness."""

import json
from dataclasses import asdict
from pathlib import Path

from ptcg_art_scraper.models import CardAsset, SidecarMetadata
from ptcg_art_scraper.providers.pkmncards import (
    _classify_basic_type,
    parse_card_page,
)
from ptcg_art_scraper.storage.layout import (
    DEFAULT_TEMPLATE,
    expand_template,
    template_output_path,
)
from ptcg_art_scraper.storage.metadata import load_sidecar, save_sidecar

# ---------------------------------------------------------------------------
# Fixtures – HTML fragments for rich metadata parsing
# ---------------------------------------------------------------------------

POKEMON_HTML = """\
<html><body>
<h1 class="entry-title">Charizard ex – 100/197</h1>
<div class="entry-content">
  <img src="https://pkmncards.com/wp-content/uploads/en_US-SV4-100-charizard_ex.png" />
</div>
<table>
  <tr><td>Set: Paldea Evolved</td></tr>
  <tr><td>Number: #100</td></tr>
  <tr><td>Type: Fire</td></tr>
  <tr><td>Stage: Stage 2</td></tr>
  <tr><td>HP: 330</td></tr>
  <tr><td>Rarity: Double Rare</td></tr>
  <tr><td>Weakness: Water ×2</td></tr>
  <tr><td>Resistance: </td></tr>
  <tr><td>Retreat: 3</td></tr>
  <tr><td>Evolves From: Charmeleon</td></tr>
  <tr><td>Artist: PLANETA Mochizuki</td></tr>
</table>
</body></html>
"""

TRAINER_HTML = """\
<html><body>
<h1 class="entry-title">Boss's Orders</h1>
<div class="entry-content">
  <img src="https://pkmncards.com/wp-content/uploads/boss-orders.png" />
</div>
<table>
  <tr><td>Set: Paldea Evolved</td></tr>
  <tr><td>Number: #172</td></tr>
  <tr><td>Type: Trainer - Supporter</td></tr>
  <tr><td>Rarity: Uncommon</td></tr>
</table>
</body></html>
"""

ENERGY_HTML = """\
<html><body>
<h1 class="entry-title">Basic Fire Energy</h1>
<div class="entry-content">
  <img src="https://pkmncards.com/wp-content/uploads/fire-energy.png" />
</div>
<table>
  <tr><td>Set: Base Set</td></tr>
  <tr><td>Number: #98</td></tr>
  <tr><td>Type: Energy</td></tr>
  <tr><td>Rarity: Common</td></tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# Rich metadata extraction tests
# ---------------------------------------------------------------------------


class TestRichMetadataExtraction:
    def test_pokemon_metadata(self):
        asset = parse_card_page(
            POKEMON_HTML,
            page_url="https://pkmncards.com/card/charizard-ex-sv4-100/",
        )
        assert asset.name == "Charizard ex – 100/197"
        assert asset.set_name == "Paldea Evolved"
        assert asset.number == "100"
        assert asset.basic_type == "Pokemon"
        assert asset.specific_type == "Stage 2"
        assert asset.hp == 330
        assert asset.color == "Fire"
        assert asset.rarity == "Double Rare"
        assert asset.evolves_from == "Charmeleon"
        assert asset.weaknesses == {"type": "Water", "value": "×2"}
        assert asset.retreat_cost == 3
        assert asset.provider == "pkmncards"
        assert "charizard" in asset.image_url.lower()

    def test_trainer_metadata(self):
        asset = parse_card_page(
            TRAINER_HTML,
            page_url="https://pkmncards.com/card/boss-orders-sv4-172/",
        )
        assert asset.basic_type == "Trainer"
        assert asset.name == "Boss's Orders"
        assert asset.rarity == "Uncommon"
        assert asset.hp == 0

    def test_energy_metadata(self):
        asset = parse_card_page(
            ENERGY_HTML,
            page_url="https://pkmncards.com/card/fire-energy-base-98/",
        )
        assert asset.basic_type == "Energy"
        assert asset.name == "Basic Fire Energy"
        assert asset.rarity == "Common"
        assert asset.hp == 0


class TestClassifyBasicType:
    def test_pokemon(self):
        assert _classify_basic_type("Fire", "Charizard") == "Pokemon"

    def test_trainer(self):
        assert _classify_basic_type("Trainer - Supporter", "Boss's Orders") == "Trainer"
        assert _classify_basic_type("Item", "Ultra Ball") == "Trainer"
        assert _classify_basic_type("Stadium", "Path to the Peak") == "Trainer"

    def test_energy(self):
        assert _classify_basic_type("Energy", "Basic Fire Energy") == "Energy"
        assert _classify_basic_type("", "Double Colorless Energy") == "Energy"


# ---------------------------------------------------------------------------
# Template engine tests
# ---------------------------------------------------------------------------


class TestExpandTemplate:
    def _asset(self, **kwargs) -> CardAsset:
        defaults = dict(
            name="Charizard ex",
            set_name="Paldea Evolved",
            set_code="sv4",
            number="100",
            basic_type="Pokemon",
            specific_type="Stage 2",
            rarity="Double Rare",
        )
        defaults.update(kwargs)
        return CardAsset(**defaults)

    def test_default_template(self):
        result = expand_template(DEFAULT_TEMPLATE, self._asset(), fmt="png")
        assert result == "sv4/100_charizard-ex.png"

    def test_basic_type_template(self):
        tmpl = "{basicType}/{set}/{rarity}/{number}_{name}.{fmt}"
        result = expand_template(tmpl, self._asset(), fmt="png")
        assert result == "pokemon/paldea-evolved/double-rare/100_charizard-ex.png"

    def test_set_id_template(self):
        tmpl = "{setId}/{number}_{name}.{fmt}"
        result = expand_template(tmpl, self._asset(), fmt="jpg")
        assert result == "sv4/100_charizard-ex.jpg"

    def test_unknown_token_preserved(self):
        tmpl = "{unknown}/{name}.{fmt}"
        result = expand_template(tmpl, self._asset(), fmt="png")
        assert result == "{unknown}/charizard-ex.png"

    def test_specific_type_token(self):
        tmpl = "{specificType}/{name}.{fmt}"
        result = expand_template(tmpl, self._asset(), fmt="png")
        assert result == "stage-2/charizard-ex.png"

    def test_set_token_falls_back_to_set_id(self):
        tmpl = "{set}/{number}_{name}.{fmt}"
        asset = self._asset(set_name="", set_code="sv4")
        result = expand_template(tmpl, asset, fmt="png")
        assert result == "sv4/100_charizard-ex.png"


class TestTemplateOutputPath:
    def test_with_template(self):
        asset = CardAsset(name="Pikachu", set_code="sv1", number="25", basic_type="Pokemon")
        p = template_output_path(Path("/out"), asset, fmt="png", template="{setId}/{name}.{fmt}")
        assert p == Path("/out/sv1/pikachu.png")

    def test_without_template_falls_back(self):
        asset = CardAsset(name="Pikachu", set_code="sv1", number="25")
        p = template_output_path(Path("/out"), asset, fmt="png", template="")
        expected = Path("/out/sv1/25_pikachu.png")
        assert p == expected


# ---------------------------------------------------------------------------
# Sidecar metadata tests
# ---------------------------------------------------------------------------


class TestSidecarMetadata:
    def test_from_asset(self):
        asset = CardAsset(
            name="Charizard ex",
            set_name="Paldea Evolved",
            set_code="sv4",
            number="100",
            basic_type="Pokemon",
            specific_type="Stage 2",
            rarity="Double Rare",
            hp=330,
            color="Fire",
            evolves_from="Charmeleon",
            provider="pkmncards",
            source_page_url="https://pkmncards.com/card/charizard-ex-sv4-100/",
            image_url="https://pkmncards.com/wp-content/uploads/charizard.png",
            attacks=[{"name": "Burn", "damage": "100", "cost": ["Fire", "Fire"], "text": ""}],
            weaknesses={"type": "Water", "value": "×2"},
            retreat_cost=3,
        )
        sidecar = SidecarMetadata.from_asset(
            asset,
            fetched_at_utc="2025-01-01T00:00:00+00:00",
            dpi=300,
            normalized_size=[750, 1050],
            normalized_output_path="/out/sv4/100_charizard-ex.png",
        )
        assert sidecar.name == "Charizard ex"
        assert sidecar.set == "Paldea Evolved"
        assert sidecar.setId == "sv4"
        assert sidecar.basicType == "Pokemon"
        assert sidecar.specificType == "Stage 2"
        assert sidecar.hp == 330
        assert sidecar.rarity == "Double Rare"
        assert sidecar.evolvesFrom == "Charmeleon"
        assert sidecar.weaknesses == {"type": "Water", "value": "×2"}
        assert sidecar.retreatCost == 3
        assert len(sidecar.attacks) == 1
        assert sidecar.attacks[0]["name"] == "Burn"
        assert sidecar.normalized_output_path == "/out/sv4/100_charizard-ex.png"
        assert sidecar.provider == "pkmncards"

    def test_sidecar_roundtrip(self, tmp_path: Path):
        asset = CardAsset(
            name="Pikachu",
            set_name="Base Set",
            set_code="BS",
            number="25",
            basic_type="Pokemon",
            rarity="Common",
            hp=60,
            provider="pkmncards",
        )
        sidecar = SidecarMetadata.from_asset(
            asset,
            fetched_at_utc=SidecarMetadata.now_utc(),
            dpi=300,
        )
        path = tmp_path / "pikachu.json"
        save_sidecar(sidecar, path)

        loaded = load_sidecar(path)
        assert loaded is not None
        assert loaded.name == "Pikachu"
        assert loaded.setId == "BS"
        assert loaded.basicType == "Pokemon"
        assert loaded.hp == 60

    def test_sidecar_json_contains_metadata(self, tmp_path: Path):
        asset = CardAsset(
            name="Test Card",
            set_code="TC",
            number="1",
            basic_type="Trainer",
            rarity="Rare",
            provider="pkmncards",
        )
        sidecar = SidecarMetadata.from_asset(asset, fetched_at_utc="2025-01-01T00:00:00+00:00")
        path = tmp_path / "test.json"
        save_sidecar(sidecar, path)

        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["name"] == "Test Card"
        assert raw["setId"] == "TC"
        assert raw["basicType"] == "Trainer"
        assert raw["rarity"] == "Rare"
        assert "warnings" in raw
        assert "normalized_output_path" in raw

    def test_sidecar_warnings(self):
        sidecar = SidecarMetadata(
            name="Test",
            warnings=["low resolution", "no DPI metadata"],
        )
        d = asdict(sidecar)
        assert len(d["warnings"]) == 2
        assert "low resolution" in d["warnings"]


# ---------------------------------------------------------------------------
# CardAsset new fields defaults
# ---------------------------------------------------------------------------


class TestCardAssetFields:
    def test_defaults(self):
        asset = CardAsset(name="Test")
        assert asset.basic_type == ""
        assert asset.specific_type == ""
        assert asset.evolves_from == ""
        assert asset.hp == 0
        assert asset.color == ""
        assert asset.attacks == []
        assert asset.abilities == []
        assert asset.traits == []
        assert asset.weaknesses == {}
        assert asset.resistances == {}
        assert asset.retreat_cost == 0

    def test_all_fields_set(self):
        asset = CardAsset(
            name="Test",
            basic_type="Pokemon",
            specific_type="Stage 1",
            evolves_from="Charmander",
            hp=120,
            color="Fire",
            attacks=[{"name": "Slash", "damage": "30"}],
            abilities=[{"name": "Blaze"}],
            traits=[{"name": "Ancient Trait"}],
            weaknesses={"type": "Water", "value": "×2"},
            resistances={"type": "Grass", "value": "-30"},
            retreat_cost=2,
        )
        assert asset.basic_type == "Pokemon"
        assert asset.hp == 120
        assert len(asset.attacks) == 1
        assert len(asset.abilities) == 1
        assert asset.retreat_cost == 2
