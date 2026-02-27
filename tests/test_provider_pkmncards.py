"""Tests for pkmncards.com HTML parsing using fixtures."""

from pathlib import Path

from ptcg_art_scraper.providers.pkmncards import (
    _next_page_url,
    _parse_search_rows,
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

SEARCH_HTML_IMAGE_LINKS = """\
<html><body>
<div class="card-list">
  <a class="card-image-otherwise-text"
     href="https://pkmncards.com/wp-content/uploads/aggron-ruby-sapphire-rs-1.jpg">
    Image
  </a>
  <a class="card-image-otherwise-text"
     href="https://pkmncards.com/wp-content/uploads/azurill-ruby-sapphire-rs-31.jpg">
    Image
  </a>
</div>
</body></html>
"""

SEARCH_HTML_TABLE_ROWS = """\
<html><body>
<div class="entry-content">
  <div class="entry-inner">
    <table>
      <tbody>
        <tr>
          <td>
            <a class="card-image-otherwise-text" href="/card/lunatone-sandstorm-ss-8/">
              <img src="/wp-content/uploads/lunatone-sandstorm-ss-8.jpg" />
            </a>
          </td>
          <td><a href="/card/lunatone-sandstorm-ss-8/">Lunatone</a></td>
          <td>Pokemon</td>
          <td>8/100</td>
          <td>Uncommon</td>
          <td><a href="/set/sandstorm/">Sandstorm</a></td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
</body></html>
"""

SEARCH_HTML_ARTICLE_ROWS = """\
<html><body>
<article class="type-pkmn_card entry">
  <div class="entry-content">
    <div class="card-image-area">
      <a class="card-image-link" href="https://pkmncards.com/wp-content/uploads/me2-5_en_294_std.jpg">
        <img src="https://pkmncards.com/wp-content/uploads/me2-5_en_294_std.jpg" />
      </a>
    </div>
    <div class="card-text-area">
      <h2 class="card-title">
        <a href="https://pkmncards.com/card/mega-charizard-y-ex-ascended-heroes-asc-294/">
          <span>Mega Charizard Y ex · Ascended Heroes (ASC) #294</span>
        </a>
      </h2>
      <div class="release-meta">
        <span title="Set"><a href="/set/ascended-heroes/">Ascended Heroes</a></span>
        (<span title="Set Abbreviation">ASC</span>)
        #<span class="number"><a href="/number/294/">294</a></span>
      </div>
    </div>
  </div>
</article>
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

CARD_HTML_TITLE_SET = """\
<html><body>
<h1 class="entry-title">Aggron · Ruby & Sapphire (RS) #1</h1>
<div class="entry-content">
  <img src="https://pkmncards.com/wp-content/uploads/aggron-ruby-sapphire-rs-1.jpg" />
</div>
</body></html>
"""

CARD_HTML_TABLE_HEADERS = """\
<html><body>
<h1 class="entry-title">Gardevoir ex</h1>
<div class="entry-content">
  <img src="https://pkmncards.com/wp-content/uploads/en_US-SV4-086-gardevoir_ex.png" />
</div>
<table class="vitals">
  <tr><th>Set</th><td>Paldea Evolved</td></tr>
  <tr><th>Number</th><td>086/197</td></tr>
</table>
</body></html>
"""

NO_IMAGE_HTML = """\
<html><body>
<h1 class="entry-title">Unknown Card</h1>
<div class="entry-content"><p>No image available</p></div>
</body></html>
"""

OG_ONLY_HTML = """\
<html><head>
  <meta property="og:title" content="Lunatone · Sandstorm (SS) #8" />
  <meta property="og:image" content="https://pkmncards.com/wp-content/uploads/lunatone-sandstorm-ss-8.jpg" />
</head><body></body></html>
"""

OG_TITLE_WITH_SITE_SUFFIX_HTML = """\
<html><head>
  <meta property="og:title" content="Aggron · Ruby &amp; Sapphire (RS) #1 ‹ PkmnCards" />
  <meta property="og:image" content="https://pkmncards.com/wp-content/uploads/aggron-ruby-sapphire-rs-1.jpg" />
</head><body></body></html>
"""

CARD_HTML_LIVE_LAYOUT = """\
<html><body>
<article class="type-pkmn_card entry">
  <div class="entry-content">
    <div class="card-image-area">
      <a class="card-image-link" href="https://pkmncards.com/wp-content/uploads/aggron-ruby-sapphire-rs-1.jpg">
        <img class="card-image" src="https://pkmncards.com/wp-content/uploads/aggron-ruby-sapphire-rs-1.jpg" />
      </a>
    </div>
    <div class="card-text-area">
      <h1 class="card-title">Aggron · Ruby &amp; Sapphire (RS) #1</h1>
      <div class="card-tabs">
        <div class="tab text">
          <div class="name-hp-color">
            <span class="name"><a href="/name/aggron/">Aggron</a></span>
            · <span class="hp"><a href="/hp/110/">110 HP</a></span>
            · <span class="color"><a href="/color/metal/"><abbr title="Metal">{M}</abbr></a></span>
          </div>
          <div class="type-evolves-is">
            <span class="type"><a href="/type/pokemon/">Pokémon</a></span>
            › <span class="stage"><a href="/stage/stage-2/">Stage 2</a></span>
            : <span class="evolves">Evolves from <a href="/name/lairon/">Lairon</a></span>
          </div>
          <div class="text">
            <p><abbr title="Colorless">{C}</abbr> → <span>Retaliate</span> : 10× Flip a coin.</p>
            <p><abbr title="Colorless">{C}</abbr><abbr title="Colorless">{C}</abbr><abbr title="Colorless">{C}</abbr> → <span>Mega Punch</span> : 40</p>
          </div>
          <div class="weak-resist-retreat">
            <span class="weak">weak: <abbr title="Fire">{R}</abbr><span title="Weakness Modifier">×2</span></span>
            |
            <span class="resist">resist: <abbr title="Grass">{G}</abbr><span title="Resistance Modifier">-30</span></span>
            |
            <span class="retreat">retreat: <a href="/retreat-cost/4/"><abbr title="{C}{C}{C}{C}">4</abbr></a></span>
          </div>
          <div class="illus minor-text"><span title="Illustrator">illus. <a href="/artist/mitsuhiro-arita/">Mitsuhiro Arita</a></span></div>
          <div class="release-meta minor-text">
            <span title="Series"><a href="/series/ex/">EX</a></span>
            › <span title="Set"><a href="/set/ruby-sapphire/">Ruby &amp; Sapphire</a></span>
            (<span title="Set Abbreviation">RS</span>, <span title="Set Series Code">EX1</span>)
            › <span class="number-out-of">#<span class="number"><a href="/number/1/">1</a></span></span>
            : <span class="rarity"><a href="/rarity/rare-holo/">Rare Holo</a></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</article>
</body></html>
"""

CARD_HTML_LIVE_TRAINER = """\
<html><body>
<article class="type-pkmn_card entry">
  <div class="entry-content">
    <div class="card-text-area">
      <h1 class="card-title">Switch · Ruby &amp; Sapphire (RS) #92</h1>
      <div class="card-tabs">
        <div class="tab text">
          <div class="name-hp-color"><span class="name">Switch</span></div>
          <div class="type-evolves-is">
            <span class="type"><a href="/type/trainer/">Trainer</a></span>
            › <span class="sub-type"><a href="/type/item/">Item</a></span>
          </div>
          <div class="text">
            <p>Switch 1 of your Active Pokémon with 1 of your Benched Pokémon.</p>
          </div>
          <div class="release-meta">
            <span title="Set"><a href="/set/ruby-sapphire/">Ruby &amp; Sapphire</a></span>
            (<span title="Set Abbreviation">RS</span>)
            › <span class="number">92</span>
            : <span class="rarity"><a href="/rarity/common/">Common</a></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</article>
</body></html>
"""


class TestParseSearchResults:
    def test_finds_card_urls(self):
        urls = _parse_search_results(SEARCH_HTML)
        assert len(urls) == 2
        assert "charizard-ex-sv4-100" in urls[0]
        assert "pikachu-sv4-25" in urls[1]

    def test_converts_image_urls_to_card_pages(self):
        urls = _parse_search_results(SEARCH_HTML_IMAGE_LINKS)
        assert urls == [
            "https://pkmncards.com/card/aggron-ruby-sapphire-rs-1/",
            "https://pkmncards.com/card/azurill-ruby-sapphire-rs-31/",
        ]

    def test_empty_page(self):
        urls = _parse_search_results("<html><body></body></html>")
        assert urls == []

    def test_extracts_metadata_from_full_display_rows(self):
        rows = _parse_search_rows(
            SEARCH_HTML_TABLE_ROWS, base_url="https://pkmncards.com"
        )
        assert len(rows) == 1
        url, meta = rows[0]
        assert url == "https://pkmncards.com/card/lunatone-sandstorm-ss-8/"
        assert meta["name"] == "Lunatone"
        assert meta["set_name"] == "Sandstorm"
        assert meta["set_code"] == "ss"
        assert meta["number"] == "8"
        assert (
            meta["image_url"]
            == "https://pkmncards.com/wp-content/uploads/lunatone-sandstorm-ss-8.jpg"
        )

    def test_extracts_metadata_from_article_cards(self):
        rows = _parse_search_rows(
            SEARCH_HTML_ARTICLE_ROWS, base_url="https://pkmncards.com"
        )
        assert len(rows) == 1
        url, meta = rows[0]
        assert (
            url
            == "https://pkmncards.com/card/mega-charizard-y-ex-ascended-heroes-asc-294/"
        )
        assert meta["name"] == "Mega Charizard Y ex"
        assert meta["set_name"] == "Ascended Heroes"
        assert meta["set_code"] == "ASC"
        assert meta["number"] == "294"


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

    def test_fallback_detects_next_by_aria_label(self):
        html = """\
        <html><body>
        <a href="/page/3/?s=series%3Aex" aria-label="Next page">Older</a>
        </body></html>
        """
        url = _next_page_url(
            html,
            current_url="https://pkmncards.com/?s=series%3Aex&display=full",
        )
        assert url == "https://pkmncards.com/page/3/?s=series%3Aex"


class TestParseCardPage:
    def test_extracts_metadata(self):
        asset = parse_card_page(
            CARD_HTML,
            page_url="https://pkmncards.com/card/charizard-ex-sv4-100/",
        )
        assert asset.name == "Charizard ex – 100/197"
        assert "charizard" in asset.image_url.lower()
        assert asset.number == "100"
        assert asset.set_code == "sv4"
        assert asset.provider == "pkmncards"

    def test_extracts_set_info_from_title(self):
        asset = parse_card_page(
            CARD_HTML_TITLE_SET,
            page_url="https://pkmncards.com/card/aggron-ruby-sapphire-rs-1/",
        )
        assert asset.name == "Aggron"
        assert asset.set_name == "Ruby & Sapphire"
        assert asset.set_code == "rs"
        assert asset.number == "1"

    def test_extracts_set_and_number_from_th_td_rows(self):
        asset = parse_card_page(
            CARD_HTML_TABLE_HEADERS,
            page_url="https://pkmncards.com/card/gardevoir-ex-sv4-86/",
        )
        assert asset.set_name == "Paldea Evolved"
        assert asset.set_code == "sv4"
        assert asset.number == "086"

    def test_set_name_falls_back_to_set_code(self):
        asset = parse_card_page(
            NO_IMAGE_HTML,
            page_url="https://pkmncards.com/card/unknown-sv4-12/",
        )
        assert asset.set_code == "sv4"
        assert asset.set_name == "sv4"

    def test_uses_og_metadata_when_entry_elements_missing(self):
        asset = parse_card_page(
            OG_ONLY_HTML,
            page_url="https://pkmncards.com/card/lunatone-sandstorm-ss-8/",
        )
        assert asset.name == "Lunatone"
        assert asset.set_name == "Sandstorm"
        assert asset.set_code == "ss"
        assert asset.number == "8"
        assert "lunatone-sandstorm-ss-8.jpg" in asset.image_url

    def test_strips_site_suffix_from_og_title(self):
        asset = parse_card_page(
            OG_TITLE_WITH_SITE_SUFFIX_HTML,
            page_url="https://pkmncards.com/card/aggron-ruby-sapphire-rs-1/",
        )
        assert asset.name == "Aggron"
        assert asset.set_name == "Ruby & Sapphire"
        assert asset.set_code == "rs"
        assert asset.number == "1"

    def test_no_image(self):
        asset = parse_card_page(NO_IMAGE_HTML, page_url="https://pkmncards.com/card/unknown/")
        assert asset.image_url == ""
        assert asset.name == "Unknown Card"

    def test_set_code_from_url(self):
        asset = parse_card_page(
            CARD_HTML,
            page_url="https://pkmncards.com/card/charizard-ex-sv4-100/",
        )
        # set_code is derived from URL slug when missing in page metadata
        assert asset.set_code == "sv4"

    def test_extracts_live_layout_rich_metadata(self):
        asset = parse_card_page(
            CARD_HTML_LIVE_LAYOUT,
            page_url="https://pkmncards.com/card/aggron-ruby-sapphire-rs-1/",
        )
        assert asset.name == "Aggron"
        assert asset.set_name == "Ruby & Sapphire"
        assert asset.set_code == "RS"
        assert asset.number == "1"
        assert asset.basic_type == "Pokemon"
        assert asset.specific_type == "Stage 2"
        assert asset.evolves_from == "Lairon"
        assert asset.hp == 110
        assert asset.color == "Metal"
        assert asset.rarity == "Rare Holo"
        assert asset.artist == "Mitsuhiro Arita"
        assert asset.retreat_cost == 4
        assert asset.weaknesses == {"type": "Fire", "value": "×2"}
        assert asset.resistances == {"type": "Grass", "value": "-30"}
        assert len(asset.attacks) == 2
        assert asset.attacks[0]["name"] == "Retaliate"
        assert asset.attacks[1]["name"] == "Mega Punch"

    def test_extracts_live_layout_trainer_metadata(self):
        asset = parse_card_page(
            CARD_HTML_LIVE_TRAINER,
            page_url="https://pkmncards.com/card/switch-ruby-sapphire-rs-92/",
        )
        assert asset.name == "Switch"
        assert asset.set_name == "Ruby & Sapphire"
        assert asset.set_code == "RS"
        assert asset.number == "92"
        assert asset.basic_type == "Trainer"
        assert asset.specific_type == "Item"
        assert asset.hp == 0
        assert asset.weaknesses == {}
        assert asset.resistances == {}
        assert asset.retreat_cost == 0
