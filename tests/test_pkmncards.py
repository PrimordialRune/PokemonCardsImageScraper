"""Tests for pkmncards.com HTML parsing using saved fixtures."""

import os

from ptcg_art_scraper.providers.pkmncards import _parse_card_page, _parse_search_results

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


class TestSearchResultsParsing:
    def test_parses_card_links(self):
        html = _load_fixture("pkmncards_search.html")
        urls = _parse_search_results(html)
        assert len(urls) == 2
        assert "charizard-ex-obsidian-flames" in urls[0]

    def test_empty_results(self):
        html = "<html><body><div class='search-results'></div></body></html>"
        urls = _parse_search_results(html)
        assert urls == []


class TestCardPageParsing:
    def test_extracts_metadata(self):
        html = _load_fixture("pkmncards_card.html")
        asset = _parse_card_page(html, "https://pkmncards.com/card/charizard-ex/")
        assert asset.name == "Charizard ex 125/197"
        assert asset.image_url.endswith(".png")
        from urllib.parse import urlparse

        assert urlparse(asset.image_url).hostname == "pkmncards.com"
        assert asset.source_page_url == "https://pkmncards.com/card/charizard-ex/"

    def test_extracts_number(self):
        html = _load_fixture("pkmncards_card.html")
        asset = _parse_card_page(html, "https://example.com")
        assert asset.number == "125/197"

    def test_extracts_set_name_from_breadcrumb(self):
        html = _load_fixture("pkmncards_card.html")
        asset = _parse_card_page(html, "https://example.com")
        assert asset.set_name == "Obsidian Flames"

    def test_missing_image(self):
        html = "<html><body><h1 class='entry-title'>Test</h1></body></html>"
        asset = _parse_card_page(html, "https://example.com")
        assert asset.image_url == ""
        assert asset.name == "Test"
