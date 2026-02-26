"""Tests for Set Completion Mode: models, detection logic, CLI command, and provider parsing."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from ptcg_art_scraper.cli import app
from ptcg_art_scraper.models import CardAssetStub, SetRef
from ptcg_art_scraper.providers.pkmncards import _parse_set_card_list, _parse_set_list
from ptcg_art_scraper.storage.completion import (
    CardStatus,
    _match_key,
    _scan_filenames,
    _scan_sidecars,
    detect_completion,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestSetRef:
    def test_basic(self) -> None:
        ref = SetRef(id="sv4", name="Paldea Evolved", year="2023", series="Scarlet & Violet")
        assert ref.id == "sv4"
        assert ref.name == "Paldea Evolved"
        assert ref.year == "2023"

    def test_defaults(self) -> None:
        ref = SetRef(id="sv4", name="Paldea Evolved")
        assert ref.year == ""
        assert ref.series == ""


class TestCardAssetStub:
    def test_basic(self) -> None:
        stub = CardAssetStub(
            provider="pkmncards",
            set_id="sv4",
            number="100",
            name="Charizard ex",
            rarity="Double Rare",
            url="https://pkmncards.com/card/charizard-ex-sv4-100/",
        )
        assert stub.provider == "pkmncards"
        assert stub.set_id == "sv4"
        assert stub.number == "100"
        assert stub.name == "Charizard ex"
        assert stub.url.startswith("https://")

    def test_defaults(self) -> None:
        stub = CardAssetStub(provider="pkmncards", set_id="sv4")
        assert stub.number == ""
        assert stub.name == ""
        assert stub.rarity == ""
        assert stub.url == ""


# ---------------------------------------------------------------------------
# Match key tests
# ---------------------------------------------------------------------------


class TestMatchKey:
    def test_with_number(self) -> None:
        key = _match_key("pkmncards", "sv4", "100", "Charizard")
        assert key == "pkmncards|sv4|100"

    def test_without_number_uses_name_slug(self) -> None:
        key = _match_key("pkmncards", "sv4", "", "Charizard ex")
        assert key == "pkmncards|sv4|charizard-ex"

    def test_both_empty(self) -> None:
        key = _match_key("pkmncards", "sv4", "", "")
        # slugify("") returns "card"
        assert key == "pkmncards|sv4|card"


# ---------------------------------------------------------------------------
# Sidecar scanning tests
# ---------------------------------------------------------------------------


class TestScanSidecars:
    def test_reads_sidecar(self, tmp_path: Path) -> None:
        sidecar = {
            "provider": "pkmncards",
            "setId": "sv4",
            "number": "100",
            "name": "Charizard ex",
            "normalized_output_path": str(tmp_path / "sv4" / "100_charizard-ex.png"),
        }
        (tmp_path / "sv4").mkdir()
        (tmp_path / "sv4" / "100_charizard-ex.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
        index = _scan_sidecars(tmp_path)
        assert "pkmncards|sv4|100" in index

    def test_ignores_bad_json(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
        index = _scan_sidecars(tmp_path)
        assert len(index) == 0

    def test_empty_folder(self, tmp_path: Path) -> None:
        index = _scan_sidecars(tmp_path)
        assert len(index) == 0

    def test_nonexistent_folder(self) -> None:
        index = _scan_sidecars(Path("/nonexistent"))
        assert len(index) == 0


# ---------------------------------------------------------------------------
# Filename scanning tests
# ---------------------------------------------------------------------------


class TestScanFilenames:
    def test_matches_numbered_file(self, tmp_path: Path) -> None:
        (tmp_path / "sv4").mkdir()
        (tmp_path / "sv4" / "100_charizard-ex.png").write_text("img", encoding="utf-8")
        index = _scan_filenames(tmp_path, "sv4", "pkmncards")
        assert "pkmncards|sv4|100" in index

    def test_no_number_uses_name(self, tmp_path: Path) -> None:
        (tmp_path / "sv4").mkdir()
        (tmp_path / "sv4" / "charizard-ex.png").write_text("img", encoding="utf-8")
        index = _scan_filenames(tmp_path, "sv4", "pkmncards")
        assert "pkmncards|sv4|charizard-ex" in index

    def test_ignores_other_sets(self, tmp_path: Path) -> None:
        (tmp_path / "other-set").mkdir()
        (tmp_path / "other-set" / "100_pikachu.png").write_text("img", encoding="utf-8")
        index = _scan_filenames(tmp_path, "sv4", "pkmncards")
        assert len(index) == 0

    def test_nonexistent_folder(self) -> None:
        index = _scan_filenames(Path("/nonexistent"), "sv4", "pkmncards")
        assert len(index) == 0


# ---------------------------------------------------------------------------
# Detection logic tests
# ---------------------------------------------------------------------------


class TestDetectCompletion:
    def _stubs(self) -> list[CardAssetStub]:
        return [
            CardAssetStub(
                provider="pkmncards", set_id="sv4", number="1",
                name="Card One", url="https://pkmncards.com/card/card-one-1/",
            ),
            CardAssetStub(
                provider="pkmncards", set_id="sv4", number="2",
                name="Card Two", url="https://pkmncards.com/card/card-two-2/",
            ),
            CardAssetStub(
                provider="pkmncards", set_id="sv4", number="3",
                name="Card Three", url="https://pkmncards.com/card/card-three-3/",
            ),
        ]

    def test_all_missing(self, tmp_path: Path) -> None:
        entries = detect_completion(self._stubs(), tmp_path, scan_local=True)
        assert len(entries) == 3
        assert all(e.status == CardStatus.MISSING for e in entries)

    def test_some_downloaded_via_sidecar(self, tmp_path: Path) -> None:
        (tmp_path / "sv4").mkdir()
        sidecar = {
            "provider": "pkmncards",
            "setId": "sv4",
            "number": "1",
            "name": "Card One",
            "normalized_output_path": str(tmp_path / "sv4" / "1_card-one.png"),
        }
        (tmp_path / "sv4" / "1_card-one.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
        entries = detect_completion(self._stubs(), tmp_path, scan_local=True)
        statuses = {e.stub.number: e.status for e in entries}
        assert statuses["1"] == CardStatus.DOWNLOADED
        assert statuses["2"] == CardStatus.MISSING
        assert statuses["3"] == CardStatus.MISSING

    def test_all_downloaded_via_filenames(self, tmp_path: Path) -> None:
        (tmp_path / "sv4").mkdir()
        for i in range(1, 4):
            (tmp_path / "sv4" / f"{i}_card.png").write_text("img", encoding="utf-8")
        entries = detect_completion(self._stubs(), tmp_path, scan_local=True)
        assert all(e.status == CardStatus.DOWNLOADED for e in entries)

    def test_scan_local_off(self, tmp_path: Path) -> None:
        (tmp_path / "sv4").mkdir()
        sidecar = {
            "provider": "pkmncards",
            "setId": "sv4",
            "number": "1",
            "name": "Card One",
        }
        (tmp_path / "sv4" / "1_card-one.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
        entries = detect_completion(self._stubs(), tmp_path, scan_local=False)
        assert all(e.status == CardStatus.MISSING for e in entries)

    def test_empty_stubs(self, tmp_path: Path) -> None:
        entries = detect_completion([], tmp_path, scan_local=True)
        assert entries == []


# ---------------------------------------------------------------------------
# Provider HTML parsing tests for sets
# ---------------------------------------------------------------------------


SET_LIST_HTML = """\
<html><body>
<div class="set-list">
  <a href="https://pkmncards.com/set/paldea-evolved/">Paldea Evolved</a>
  <a href="https://pkmncards.com/set/obsidian-flames/">Obsidian Flames</a>
  <a href="https://pkmncards.com/set/paldea-evolved/">Paldea Evolved</a>
</div>
</body></html>
"""

SET_CARD_LIST_HTML = """\
<html><body>
<div class="card-list">
  <a class="card-image-otherwise-text" href="https://pkmncards.com/card/charizard-ex-sv4-100/">
    <img src="https://pkmncards.com/wp-content/uploads/charizard.jpg" />
  </a>
  <a class="card-image-otherwise-text" href="https://pkmncards.com/card/pikachu-sv4-25/">
    <img src="https://pkmncards.com/wp-content/uploads/pikachu.jpg" />
  </a>
</div>
</body></html>
"""


class TestParseSetList:
    def test_extracts_sets(self) -> None:
        sets = _parse_set_list(SET_LIST_HTML)
        assert len(sets) == 2  # deduplication
        assert sets[0].id == "paldea-evolved"
        assert sets[0].name == "Paldea Evolved"
        assert sets[1].id == "obsidian-flames"
        assert sets[1].name == "Obsidian Flames"

    def test_empty_page(self) -> None:
        sets = _parse_set_list("<html><body></body></html>")
        assert sets == []


class TestParseSetCardList:
    def test_extracts_stubs(self) -> None:
        stubs = _parse_set_card_list(SET_CARD_LIST_HTML, "sv4")
        assert len(stubs) == 2
        assert stubs[0].number == "100"
        assert stubs[0].set_id == "sv4"
        assert stubs[0].provider == "pkmncards"
        assert stubs[1].number == "25"

    def test_empty_page(self) -> None:
        stubs = _parse_set_card_list("<html><body></body></html>", "sv4")
        assert stubs == []


# ---------------------------------------------------------------------------
# CLI complete-set command tests
# ---------------------------------------------------------------------------

runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class TestCompleteSetCLI:
    def test_help(self) -> None:
        result = runner.invoke(app, ["complete-set", "--help"])
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "--set-id" in plain
        assert "--out" in plain

    def test_shows_in_main_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "complete-set" in result.output
