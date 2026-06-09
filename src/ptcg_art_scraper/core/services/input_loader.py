"""Batch input parsing helpers for the CLI."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ptcg_art_scraper.core.exceptions import InputFormatError
from ptcg_art_scraper.core.models import CardIdentifier


def parse_card_list(numbers: str, default_set: str = "") -> list[CardIdentifier]:
    cards: list[CardIdentifier] = []
    for raw_entry in numbers.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        cards.append(_parse_identifier(entry, default_set=default_set))
    return cards


def load_cards_from_file(path: Path, default_set: str = "") -> list[CardIdentifier]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path, default_set=default_set)
    if suffix == ".csv":
        return _load_csv(path, default_set=default_set)
    return _load_text(path, default_set=default_set)


def _load_json(path: Path, default_set: str) -> list[CardIdentifier]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise InputFormatError("JSON input must be a list of cards or identifiers.")
    cards: list[CardIdentifier] = []
    for entry in data:
        cards.append(_parse_json_entry(entry, default_set=default_set))
    return cards


def _load_csv(path: Path, default_set: str) -> list[CardIdentifier]:
    cards: list[CardIdentifier] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            set_code = (row.get("set") or row.get("set_code") or default_set).strip()
            card_number = (row.get("number") or row.get("card_number") or "").strip()
            if not set_code or not card_number:
                raise InputFormatError(
                    "CSV rows must provide set/set_code and number/card_number values."
                )
            cards.append(CardIdentifier(set_code=set_code, card_number=card_number))
    return cards


def _load_text(path: Path, default_set: str) -> list[CardIdentifier]:
    cards: list[CardIdentifier] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cards.append(_parse_identifier(line, default_set=default_set))
    return cards


def _parse_json_entry(entry: Any, default_set: str) -> CardIdentifier:
    if isinstance(entry, str):
        return _parse_identifier(entry, default_set=default_set)
    if not isinstance(entry, dict):
        raise InputFormatError("JSON entries must be strings or objects.")
    set_code = str(entry.get("set") or entry.get("set_code") or default_set).strip()
    card_number = str(entry.get("number") or entry.get("card_number") or "").strip()
    if not set_code or not card_number:
        raise InputFormatError("JSON objects must include set/set_code and number/card_number.")
    return CardIdentifier(set_code=set_code, card_number=card_number)


def _parse_identifier(value: str, default_set: str) -> CardIdentifier:
    cleaned = value.strip()
    if "#" in cleaned:
        set_code, card_number = cleaned.split("#", 1)
        return CardIdentifier(set_code=set_code.strip(), card_number=card_number.strip())
    if "," in cleaned:
        set_code, card_number = cleaned.split(",", 1)
        return CardIdentifier(set_code=set_code.strip(), card_number=card_number.strip())
    if not default_set:
        raise InputFormatError(
            "Text entries must be in SET#NUMBER form unless --set is supplied."
        )
    return CardIdentifier(set_code=default_set.strip(), card_number=cleaned)
