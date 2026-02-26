"""Tests for pkmncards.com HTML parsing using fixtures."""

from pathlib import Path

from ptcg_art_scraper.providers.pkmncards import (
    _next_page_url,
    _parse_search_results,
    parse_card_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---- Inline fixtures for unit testing without live network ----

SEARCH_HTML = """\
<html><body>
<div class="card-list">
  <a class="card-image-otherwise-text" href="https://pkmncards.com/card/charizard-ex-sv4-100/">
    <img src="https://pkmncards.com/wp-content/uploads/charizard.jpg" />
  </a>
  <a class="card-image-otherwise-text" href="https://pkmncards.com/card/pikachu-sv4-25/">
    <img src="https://pkmncards.com/wp-content/uploads/pikachu.jpg" />
  </a>
</div>
<a class="next page-numbers" href="https://pkmncards.com/?s=charizard&page=2">Next</a>
</body></html>
"""

CARD_HTML = """\
<html><body>
<h1 class="entry-title">Charizard ex – 100/197</h1>
<div class="entry-content">
  <img src="https://pkmncards.com/wp-content/uploads/en_US-SV4-100-charizard_ex.png" />
</div>
<table>
  <tr><td>Set: Paldea Evolved</td></tr>
  <tr><td>Number: #100</td></tr>
</table>
</body></html>
"""

NO_IMAGE_HTML = """\
<html><body>
<h1 class="entry-title">Unknown Card</h1>
<div class="entry-content"><p>No image available</p></div>
</body></html>
"""


class TestParseSearchResults:
    def test_finds_card_urls(self):
        urls = _parse_search_results(SEARCH_HTML)
        assert len(urls) == 2
        assert "charizard-ex-sv4-100" in urls[0]
        assert "pikachu-sv4-25" in urls[1]

    def test_empty_page(self):
        urls = _parse_search_results("<html><body></body></html>")
        assert urls == []


class TestNextPageUrl:
    def test_finds_next(self):
        url = _next_page_url(SEARCH_HTML)
        assert url is not None
        assert "page=2" in url

    def test_finds_rel_next_link_and_normalizes(self):
        html = """\
        <html><head>
        <link rel="next" href="/page/2/?s=charizard&display=full#content" />
        </head><body></body></html>
        """
        url = _next_page_url(
            html,
            current_url="https://pkmncards.com/?s=charizard&display=full",
        )
        assert url == "https://pkmncards.com/page/2/?s=charizard&display=full"

    def test_no_next(self):
        assert _next_page_url("<html><body></body></html>") is None


class TestParseCardPage:
    def test_extracts_metadata(self):
        asset = parse_card_page(
            CARD_HTML,
            page_url="https://pkmncards.com/card/charizard-ex-sv4-100/",
        )
        assert asset.name == "Charizard ex – 100/197"
        assert "charizard" in asset.image_url.lower()
        assert asset.number == "100"
        assert asset.provider == "pkmncards"

    def test_no_image(self):
        asset = parse_card_page(NO_IMAGE_HTML, page_url="https://pkmncards.com/card/unknown/")
        assert asset.image_url == ""
        assert asset.name == "Unknown Card"

    def test_set_code_from_url(self):
        asset = parse_card_page(
            CARD_HTML,
            page_url="https://pkmncards.com/card/charizard-ex-sv4-100/",
        )
        # set_code is derived from URL path segments
        assert asset.set_code == "charizard-ex-sv4-100"
