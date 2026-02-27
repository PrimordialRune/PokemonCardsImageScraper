"""Data models for the index subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SetInfo:
    """Metadata about a Pokémon TCG set."""

    id: str
    name: str
    series: str = ""
    printed_total: int = 0
    total: int = 0
    release_date: str = ""
    symbol_url: str = ""
    logo_url: str = ""


@dataclass(frozen=True)
class CardIndexEntry:
    """Lightweight index entry for a card within a set."""

    set_id: str
    number: str
    name: str = ""
    supertype: str = ""
    rarity: str = ""
    subtypes: list[str] = field(default_factory=list)
    hp: str = ""
    types: list[str] = field(default_factory=list)
    evolves_from: str = ""
