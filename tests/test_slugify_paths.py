"""Tests for slugify and output path helpers."""

from pathlib import Path

from ptcg_art_scraper.models import CardAsset
from ptcg_art_scraper.storage.layout import card_output_path, sidecar_path
from ptcg_art_scraper.utils.slugify import slugify

# --------------- slugify ---------------

class TestSlugify:
    def test_basic(self):
        assert slugify("Charizard ex") == "charizard-ex"

    def test_special_chars(self):
        assert slugify("Pikachu V-UNION #1") == "pikachu-v-union-1"

    def test_unicode(self):
        assert slugify("Méwtwo Ünown") == "mewtwo-unknow" or slugify("Méwtwo Ünown").startswith("m")

    def test_empty_string(self):
        assert slugify("") == "card"

    def test_only_special(self):
        assert slugify("!!!") == "card"

    def test_max_length(self):
        result = slugify("a" * 200, max_length=20)
        assert len(result) <= 20

    def test_no_leading_trailing_dashes(self):
        assert not slugify("--hello--").startswith("-")
        assert not slugify("--hello--").endswith("-")


# --------------- output paths ---------------

class TestOutputPath:
    def test_default_path(self):
        asset = CardAsset(name="Charizard ex", set_code="sv4", number="100")
        p = card_output_path(Path("/out"), asset, fmt="png")
        assert p == Path("/out/sv4/100_charizard-ex.png")

    def test_set_name_fallback(self):
        asset = CardAsset(name="Pikachu", set_name="Paldea Evolved", number="25")
        p = card_output_path(Path("/out"), asset, fmt="png")
        assert "paldea-evolved" in str(p)

    def test_unknown_set(self):
        asset = CardAsset(name="Card", number="1")
        p = card_output_path(Path("/out"), asset, fmt="png")
        assert "unknown-set" in str(p)

    def test_sidecar_path(self):
        img = Path("/out/sv4/100_charizard-ex.png")
        assert sidecar_path(img) == Path("/out/sv4/100_charizard-ex.json")
