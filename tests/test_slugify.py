"""Tests for ptcg_art_scraper.utils.slugify."""

from ptcg_art_scraper.utils.slugify import slugify


def test_basic_slug():
    assert slugify("Charizard ex") == "charizard-ex"


def test_number_slash():
    assert slugify("100/197") == "100-197"


def test_unicode():
    assert slugify("Étoile étrange") == "etoile-etrange"


def test_special_chars():
    assert slugify("Pikachu (V-Max)!!!") == "pikachu-v-max"


def test_collapse_dashes():
    assert slugify("a -- b --- c") == "a-b-c"


def test_max_length():
    result = slugify("a" * 200, max_length=10)
    assert len(result) == 10


def test_empty():
    assert slugify("") == ""
