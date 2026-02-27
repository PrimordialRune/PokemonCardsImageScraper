"""Index client interface and PokemonTcgData implementation."""

from __future__ import annotations

import abc
import json
import logging
import time
from pathlib import Path

from ptcg_art_scraper.index.models import CardIndexEntry, SetInfo

logger = logging.getLogger(__name__)

# Default disk cache directory.
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "ptcg_art_scraper" / "index"

# Cache time-to-live in seconds (24 hours).
_DEFAULT_TTL = 86400

# Schema version – bump when the cache format changes.
_SCHEMA_VERSION = 1

# Local folder expected to mirror PokemonTCG/pokemon-tcg-data.
_LOCAL_DATA_ROOT = Path(__file__).resolve().parents[3] / "pokemon-tcg-data"


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class IndexClient(abc.ABC):
    """Read-only index of sets and cards."""

    @abc.abstractmethod
    def list_sets(self) -> list[SetInfo]:
        """Return all known sets."""

    @abc.abstractmethod
    def get_set(self, set_id: str) -> SetInfo | None:
        """Return a single set by its id, or ``None``."""

    @abc.abstractmethod
    def list_cards_in_set(self, set_id: str) -> list[CardIndexEntry]:
        """Return all cards in the given set."""


# ---------------------------------------------------------------------------
# pokemon-tcg-data implementation
# ---------------------------------------------------------------------------


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.v{_SCHEMA_VERSION}.json"


def _read_cache(cache_dir: Path, key: str, ttl: int) -> object | None:
    path = _cache_path(cache_dir, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
        if time.time() - data.get("_ts", 0) > ttl:
            return None
        return data.get("payload")
    except Exception:
        return None


def _write_cache(cache_dir: Path, key: str, payload: object) -> None:
    path = _cache_path(cache_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_ts": time.time(), "payload": payload}),
        encoding="utf-8",
    )


class PokemonTcgDataIndexClient(IndexClient):
    """Reads set/card data from a local PokemonTCG/pokemon-tcg-data copy.

    Responses are cached on disk with a configurable TTL so subsequent calls
    are fast and offline-friendly.
    """

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        ttl: int = _DEFAULT_TTL,
        data_root: Path | None = None,
    ) -> None:
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._ttl = ttl
        root = data_root or _LOCAL_DATA_ROOT
        self._sets_path = root / "sets" / "en.json"
        self._cards_dir = root / "cards" / "en"

    # -- public interface ---------------------------------------------------

    def list_sets(self) -> list[SetInfo]:
        cached = _read_cache(self._cache_dir, "sets", self._ttl)
        if cached is not None:
            return _parse_sets(cached)

        try:
            raw = self._fetch_json(self._sets_path)
        except Exception:
            logger.warning("Could not read set index from %s", self._sets_path)
            return []
        _write_cache(self._cache_dir, "sets", raw)
        return _parse_sets(raw)

    def get_set(self, set_id: str) -> SetInfo | None:
        for s in self.list_sets():
            if s.id == set_id:
                return s
        return None

    def list_cards_in_set(self, set_id: str) -> list[CardIndexEntry]:
        cache_key = f"cards_{set_id}"
        cached = _read_cache(self._cache_dir, cache_key, self._ttl)
        if cached is not None:
            return _parse_cards(cached, set_id)

        path = self._cards_dir / f"{set_id}.json"
        try:
            raw = self._fetch_json(path)
        except Exception:
            logger.warning("Could not fetch card index for set %s", set_id)
            return []
        _write_cache(self._cache_dir, cache_key, raw)
        return _parse_cards(raw, set_id)

    # -- helpers ------------------------------------------------------------

    def _fetch_json(self, path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_IMAGE_HOST = "https://images.pokemontcg.io"


def _parse_sets(raw: object) -> list[SetInfo]:
    if not isinstance(raw, list):
        return []
    sets: list[SetInfo] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("id", "")
        sets.append(
            SetInfo(
                id=sid,
                name=entry.get("name", sid),
                series=entry.get("series", ""),
                printed_total=int(entry.get("printedTotal", 0)),
                total=int(entry.get("total", 0)),
                release_date=entry.get("releaseDate", ""),
                symbol_url=f"{_IMAGE_HOST}/{sid}/symbol.png",
                logo_url=f"{_IMAGE_HOST}/{sid}/logo.png",
            )
        )
    return sets


def _parse_cards(raw: object, set_id: str) -> list[CardIndexEntry]:
    if not isinstance(raw, list):
        return []
    cards: list[CardIndexEntry] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        cards.append(
            CardIndexEntry(
                set_id=set_id,
                number=entry.get("number", ""),
                name=entry.get("name", ""),
                supertype=entry.get("supertype", ""),
                rarity=entry.get("rarity", ""),
                subtypes=list(entry.get("subtypes") or []),
                hp=str(entry.get("hp", "")),
                types=list(entry.get("types") or []),
                evolves_from=entry.get("evolvesFrom", ""),
            )
        )
    return cards
