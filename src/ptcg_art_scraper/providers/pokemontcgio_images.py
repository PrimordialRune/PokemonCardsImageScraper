"""Provider that downloads card images from images.pokemontcg.io.

Uses the PokemonTCG/pokemon-tcg-data index for set/card metadata so it
works without any paid API calls.
"""

from __future__ import annotations

import json
import logging

import httpx

from ptcg_art_scraper.index.client import IndexClient, PokemonTcgDataIndexClient
from ptcg_art_scraper.index.models import CardIndexEntry, SetInfo
from ptcg_art_scraper.models import CardAsset, CardRef, FetchedImage
from ptcg_art_scraper.net.http import RateLimiter, fetch_bytes
from ptcg_art_scraper.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_IMAGE_HOST = "https://images.pokemontcg.io"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def image_url(set_id: str, number: str, *, hires: bool = False) -> str:
    """Build a card image URL on images.pokemontcg.io."""
    suffix = "_hires.png" if hires else ".png"
    return f"{_IMAGE_HOST}/{set_id}/{number}{suffix}"


def parse_image_url(url: str) -> tuple[str, str] | None:
    """Extract ``(set_id, number)`` from an images.pokemontcg.io URL.

    Returns ``None`` when the URL doesn't match the expected pattern.
    """
    prefix = _IMAGE_HOST + "/"
    if not url.startswith(prefix):
        return None
    path = url[len(prefix):]
    parts = path.split("/", 1)
    if len(parts) != 2:
        return None
    set_id = parts[0]
    filename = parts[1]
    if not filename:
        return None
    # Strip known suffixes
    for ext in ("_hires.png", ".png", ".jpg", ".jpeg", ".webp"):
        if filename.endswith(ext):
            number = filename[: -len(ext)]
            return set_id, number
    return set_id, filename


def _basic_type_from_supertype(supertype: str) -> str:
    st = supertype.strip().lower()
    if st == "pokémon" or st == "pokemon":
        return "Pokemon"
    if st == "trainer":
        return "Trainer"
    if st == "energy":
        return "Energy"
    return supertype


def _specific_type_from_subtypes(subtypes: list[str]) -> str:
    return ", ".join(subtypes) if subtypes else ""


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class PokemonTcgioImagesProvider(BaseProvider):
    """Card image provider backed by images.pokemontcg.io + index data."""

    name: str = "pokemontcgio_images"

    def __init__(
        self,
        *,
        index: IndexClient | None = None,
        prefer_hires: bool = True,
    ) -> None:
        self._index = index or PokemonTcgDataIndexClient()
        self._prefer_hires = prefer_hires

    def get_image_url(self, set_code: str, card_number: str) -> str | None:
        cleaned_set = str(set_code).strip()
        cleaned_number = str(card_number).strip()
        if not cleaned_set:
            logger.info("%s failed deterministically: missing set code", self.name)
            return None
        if not cleaned_number:
            logger.info("%s failed deterministically: missing card number", self.name)
            return None
        return image_url(cleaned_set, cleaned_number, hires=self._prefer_hires)

    # -- BaseProvider interface ---------------------------------------------

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        set_filter: str = "",
        limit: int = 0,
        rate_limiter: RateLimiter | None = None,
    ) -> list[CardRef]:
        """Search for cards.

        *query* is interpreted as a set id when it matches a known set,
        otherwise cards are matched by name substring across all sets (if
        a set_filter is provided, only that set is searched).
        """
        refs: list[CardRef] = []

        # Direct URL paste
        if query.startswith("https://images.pokemontcg.io/"):
            parsed = parse_image_url(query)
            if parsed:
                sid, num = parsed
                meta = {"set_code": sid, "number": num}
                refs.append(
                    CardRef(
                        provider=self.name,
                        url=image_url(sid, num),
                        card_id=json.dumps(meta),
                    )
                )
                return refs

        # Try treating query as a set id
        set_info = self._index.get_set(query)
        if set_info is not None:
            cards = self._index.list_cards_in_set(set_info.id)
            for c in cards:
                refs.append(self._card_entry_to_ref(c, set_info))
            if limit > 0:
                refs = refs[:limit]
            return refs

        # Otherwise search by name within a set or across all sets
        target_set_id = set_filter or ""
        if target_set_id:
            cards = self._index.list_cards_in_set(target_set_id)
            sets_info = {target_set_id: self._index.get_set(target_set_id)}
        else:
            all_sets = self._index.list_sets()
            sets_info = {s.id: s for s in all_sets}
            cards = []
            for s in all_sets:
                cards.extend(self._index.list_cards_in_set(s.id))

        q_lower = query.lower()
        for c in cards:
            if q_lower in c.name.lower():
                si = sets_info.get(c.set_id)
                refs.append(self._card_entry_to_ref(c, si))
        if limit > 0:
            refs = refs[:limit]
        return refs

    async def resolve(
        self,
        client: httpx.AsyncClient,
        ref: CardRef,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> CardAsset:
        """Resolve a :class:`CardRef` into a :class:`CardAsset`."""
        # Decode hints stored during search
        meta: dict[str, str] = {}
        if ref.card_id:
            try:
                meta = json.loads(ref.card_id)
            except (json.JSONDecodeError, TypeError):
                pass

        set_id = meta.get("set_code", "")
        number = meta.get("number", "")

        # Fallback: try parsing from URL
        if (not set_id or not number) and ref.url:
            parsed = parse_image_url(ref.url)
            if parsed:
                set_id, number = parsed

        # Attempt to enrich from index
        name = meta.get("name", "")
        set_name = meta.get("set_name", "")
        rarity = meta.get("rarity", "")
        basic_type = meta.get("basic_type", "")
        specific_type = meta.get("specific_type", "")
        evolves_from = ""
        hp = 0
        color = ""

        if set_id and number:
            cards = self._index.list_cards_in_set(set_id)
            for c in cards:
                if c.number == number:
                    name = name or c.name
                    rarity = rarity or c.rarity
                    basic_type = basic_type or _basic_type_from_supertype(c.supertype)
                    specific_type = specific_type or _specific_type_from_subtypes(c.subtypes)
                    evolves_from = c.evolves_from
                    hp = int(c.hp.strip()) if c.hp.strip().isdigit() else 0
                    color = c.types[0] if c.types else ""
                    break
            if not set_name:
                si = self._index.get_set(set_id)
                if si:
                    set_name = si.name

        img = image_url(set_id, number, hires=self._prefer_hires) if set_id and number else ref.url

        return CardAsset(
            name=name or f"{set_id}-{number}",
            set_name=set_name,
            set_code=set_id,
            number=number,
            rarity=rarity,
            image_url=img,
            provider=self.name,
            basic_type=basic_type,
            specific_type=specific_type,
            evolves_from=evolves_from,
            hp=hp,
            color=color,
        )

    async def fetch_image(
        self,
        client: httpx.AsyncClient,
        asset: CardAsset,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> FetchedImage:
        """Download the card image, falling back from hires to standard."""
        url = asset.image_url

        # Try hires first, fall back to standard on 404
        if "_hires.png" in url:
            try:
                data = await fetch_bytes(client, url, retries=1, rate_limiter=rate_limiter)
                return FetchedImage(data=data, mime_type="image/png", source_url=url)
            except Exception:
                fallback_url = url.replace("_hires.png", ".png")
                logger.info("Hires not available, falling back: %s", fallback_url)
                data = await fetch_bytes(client, fallback_url, rate_limiter=rate_limiter)
                # Update asset to reflect what was actually fetched
                asset.image_url = fallback_url
                return FetchedImage(data=data, mime_type="image/png", source_url=fallback_url)

        data = await fetch_bytes(client, url, rate_limiter=rate_limiter)
        return FetchedImage(data=data, mime_type="image/png", source_url=url)

    # -- helpers ------------------------------------------------------------

    def _card_entry_to_ref(
        self, card: CardIndexEntry, set_info: SetInfo | None
    ) -> CardRef:
        meta = {
            "set_code": card.set_id,
            "number": card.number,
            "name": card.name,
            "set_name": set_info.name if set_info else "",
            "rarity": card.rarity,
            "basic_type": _basic_type_from_supertype(card.supertype),
            "specific_type": _specific_type_from_subtypes(card.subtypes),
            "image_url": image_url(card.set_id, card.number),
        }
        return CardRef(
            provider=self.name,
            url=image_url(card.set_id, card.number),
            card_id=json.dumps(meta),
        )
