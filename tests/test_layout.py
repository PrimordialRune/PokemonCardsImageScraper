"""Tests for output path layout."""

import os
import tempfile

from ptcg_art_scraper.storage.layout import card_stem, output_paths


def test_card_stem_with_set_code():
    dir_name, stem = card_stem("Charizard ex", "100/197", "Obsidian Flames", "sv3")
    assert dir_name == "sv3"
    assert stem == "100-197_charizard-ex"


def test_card_stem_without_set_code():
    dir_name, stem = card_stem("Pikachu", "25", "Base Set", None)
    assert dir_name == "base-set"
    assert stem == "25_pikachu"


def test_card_stem_no_number():
    dir_name, stem = card_stem("Energy", None, "Base Set", None)
    assert dir_name == "base-set"
    assert stem == "energy"


def test_output_paths_creates_dirs():
    with tempfile.TemporaryDirectory() as td:
        img, js = output_paths(td, "Charizard", "100", "Obsidian Flames", "sv3", ".png")
        assert img.endswith(".png")
        assert js.endswith(".json")
        assert os.path.isdir(os.path.join(td, "sv3"))
