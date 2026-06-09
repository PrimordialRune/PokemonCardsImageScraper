"""Tests for the layered resolver and batch input parsing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

from ptcg_art_scraper.cli import app
from ptcg_art_scraper.core.config import ResolverConfig
from ptcg_art_scraper.core.models import CardIdentifier
from ptcg_art_scraper.core.services import (
    ImageResolutionService,
    load_cards_from_file,
    parse_card_list,
)

runner = CliRunner()


class TestImageResolutionService:
    def test_default_priority_returns_official_url_without_verification(self):
        service = ImageResolutionService(ResolverConfig(verify_urls=False))
        resolved = asyncio.run(service.resolve_card(CardIdentifier("EX6", "10")))

        assert resolved is not None
        assert resolved.provider == "pokemon_official"
        assert resolved.resolved_url.endswith("/EX6/EX6_EN_10.png")
        assert service.last_attempts[-1].provider == "pokemon_official"
        assert service.last_attempts[-1].status == "ok"

    def test_custom_priority_can_prefer_tcgio(self):
        service = ImageResolutionService(
            ResolverConfig(
                provider_priority=("pokemontcgio_images", "pokemon_official"),
                verify_urls=False,
            )
        )
        resolved = asyncio.run(service.resolve_card(CardIdentifier("sv4", "100")))

        assert resolved is not None
        assert resolved.provider == "pokemontcgio_images"
        assert resolved.resolved_url == "https://images.pokemontcg.io/sv4/100_hires.png"


class TestInputLoader:
    def test_parse_card_list_uses_default_set(self):
        cards = parse_card_list("10, 11", default_set="EX6")
        assert cards == [CardIdentifier("EX6", "10"), CardIdentifier("EX6", "11")]

    def test_load_json_file(self, tmp_path: Path):
        path = tmp_path / "cards.json"
        path.write_text(json.dumps([{"set_code": "sv4", "card_number": "100"}, "EX6#10"]))

        cards = load_cards_from_file(path)

        assert cards == [CardIdentifier("sv4", "100"), CardIdentifier("EX6", "10")]


class TestResolveCommand:
    def test_resolve_command_shows_provider_output(self):
        result = runner.invoke(
            app,
            ["resolve", "--set", "EX6", "--number", "10", "--no-verify"],
        )

        assert result.exit_code == 0
        assert "Resolving EX6 #10" in result.output
        assert "Provider: pokemon_official" in result.output
