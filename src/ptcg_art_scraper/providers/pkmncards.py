"""pkmncards.com provider."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup, Tag

from ptcg_art_scraper.models import CardAsset, CardRef, FetchedImage
from ptcg_art_scraper.net.http import RateLimiter, fetch_bytes, fetch_text
from ptcg_art_scraper.providers.base import BaseProvider

logger = logging.getLogger(__name__)

BASE_URL = "https://pkmncards.com"


def _parse_search_results(html: str) -> list[str]:
    """Extract card-page URLs from a pkmncards.com search-results page."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a_tag in soup.select("a.card-image-otherwise-text"):
        href = a_tag.get("href")
        if href:
            urls.append(str(href))
    if not urls:
        # Fallback: look for entry links inside card list items
        for a_tag in soup.select(".entry-title a, article a"):
            href = a_tag.get("href")
            if href and "/card/" in str(href):
                urls.append(str(href))
    return urls


def _next_page_url(html: str) -> str | None:
    """Return the next-page URL from pagination, or *None*."""
    soup = BeautifulSoup(html, "html.parser")
    nxt = soup.select_one("a.next.page-numbers")
    if nxt:
        return str(nxt["href"])
    return None


def _text_of(soup: BeautifulSoup | Tag, selector: str) -> str:
    """Return stripped text of the first element matching *selector*, or ''."""
    el = soup.select_one(selector)
    return el.get_text(strip=True) if el else ""


def _extract_info_field(rows: list[Tag], label: str) -> str:
    """Search table rows / info divs for a labelled value."""
    label_lower = label.lower()
    for row in rows:
        text = row.get_text(" ", strip=True)
        if label_lower in text.lower():
            parts = text.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return ""


def _classify_basic_type(raw_type: str, name: str) -> str:
    """Determine basicType as 'Pokemon', 'Trainer', or 'Energy'."""
    combined = f"{raw_type} {name}".lower()
    if "energy" in combined:
        return "Energy"
    trainer_keywords = ("trainer", "supporter", "item", "stadium", "tool")
    for kw in trainer_keywords:
        if kw in combined:
            return "Trainer"
    return "Pokemon"


def _parse_attacks(soup: BeautifulSoup | Tag) -> list[dict]:
    """Extract attack info from the card page."""
    attacks: list[dict] = []
    for section in soup.select(".pokemon-attack, .card-attack, .attack"):
        name = _text_of(section, ".attack-name, .name")
        damage = _text_of(section, ".attack-damage, .damage")
        text = _text_of(section, ".attack-text, .text")
        cost_els = section.select(".attack-cost img, .cost img, .energy-icon")
        cost = [str(el.get("alt", el.get("title", ""))) for el in cost_els]
        if name:
            attacks.append({"name": name, "damage": damage, "text": text, "cost": cost})
    return attacks


def _parse_abilities(soup: BeautifulSoup | Tag) -> list[dict]:
    """Extract ability/poke-power/poke-body info."""
    abilities: list[dict] = []
    for section in soup.select(".pokemon-ability, .card-ability, .ability"):
        name = _text_of(section, ".ability-name, .name")
        kind = _text_of(section, ".ability-type, .type")
        text = _text_of(section, ".ability-text, .text")
        if name:
            abilities.append({"name": name, "type": kind, "text": text})
    return abilities


def _parse_weakness_resistance(
    rows: list[Tag], label: str
) -> dict[str, str]:
    """Return {type, value} for weakness or resistance."""
    raw = _extract_info_field(rows, label)
    if not raw:
        return {}
    # Common patterns: "Fire ×2", "Grass -30"
    m = re.match(r"([A-Za-z]+)\s*([×x+\-]\s*\d+)?", raw)
    if m:
        return {"type": m.group(1), "value": (m.group(2) or "").strip()}
    return {"type": raw, "value": ""}


def parse_card_page(html: str, page_url: str = "") -> CardAsset:
    """Parse a pkmncards.com card detail page into a :class:`CardAsset`."""
    soup = BeautifulSoup(html, "html.parser")

    # --- image URL ---
    image_url = ""
    img_tag = soup.select_one("div.entry-content img")
    if img_tag is None:
        img_tag = soup.select_one("img.card-image")
    if img_tag is None:
        img_tag = soup.select_one("article img")
    if img_tag:
        image_url = str(img_tag.get("src", ""))

    # --- name ---
    name = ""
    title_el = soup.select_one("h1.entry-title") or soup.select_one("h2.entry-title")
    if title_el:
        name = title_el.get_text(strip=True)

    # --- Collect info rows once ---
    info_rows: list[Tag] = list(soup.select("table tr, .card-tab-otherwise-text div"))

    # --- set / number from breadcrumbs or page text ---
    set_name = _extract_info_field(info_rows, "set") or ""
    number = _extract_info_field(info_rows, "number").lstrip("#") or ""

    # Try parsing name like "Charizard ex – 100/197"
    if not number and name:
        m = re.search(r"(\d+)\s*/\s*\d+", name)
        if m:
            number = m.group(1)

    # Attempt set code from URL segments (e.g. /card/{slug}/)
    set_code = ""
    if page_url:
        parts = [p for p in page_url.rstrip("/").split("/") if p]
        # pkmncards URLs: …/card/{card-slug}/
        if len(parts) >= 2 and parts[-2] == "card":
            set_code = parts[-1]

    # --- Rich metadata ---
    raw_type = _extract_info_field(info_rows, "type")
    specific_type = _extract_info_field(info_rows, "stage") or _extract_info_field(
        info_rows, "sub"
    )
    basic_type = _classify_basic_type(raw_type or specific_type, name)

    evolves_from = _extract_info_field(info_rows, "evolves from")
    hp_raw = _extract_info_field(info_rows, "hp")
    hp = 0
    if hp_raw:
        hp_match = re.search(r"\d+", hp_raw)
        if hp_match:
            hp = int(hp_match.group())

    color = _extract_info_field(info_rows, "color") or _extract_info_field(info_rows, "type")
    rarity = _extract_info_field(info_rows, "rarity")
    artist = _extract_info_field(info_rows, "artist")

    retreat_raw = _extract_info_field(info_rows, "retreat")
    retreat_cost = 0
    if retreat_raw:
        rc_match = re.search(r"\d+", retreat_raw)
        if rc_match:
            retreat_cost = int(rc_match.group())

    attacks = _parse_attacks(soup)
    abilities = _parse_abilities(soup)
    weaknesses = _parse_weakness_resistance(info_rows, "weakness")
    resistances = _parse_weakness_resistance(info_rows, "resistance")

    return CardAsset(
        name=name,
        set_name=set_name,
        set_code=set_code,
        number=number,
        rarity=rarity,
        artist=artist,
        image_url=image_url,
        source_page_url=page_url,
        provider="pkmncards",
        basic_type=basic_type,
        specific_type=specific_type,
        evolves_from=evolves_from,
        hp=hp,
        color=color,
        attacks=attacks,
        abilities=abilities,
        weaknesses=weaknesses,
        resistances=resistances,
        retreat_cost=retreat_cost,
    )


class PkmnCardsProvider(BaseProvider):
    """Scraper for pkmncards.com."""

    name = "pkmncards"

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        set_filter: str = "",
        limit: int = 0,
        rate_limiter: RateLimiter | None = None,
    ) -> list[CardRef]:
        refs: list[CardRef] = []
        search_url = f"{BASE_URL}/?s={quote_plus(query)}&display=full"
        if set_filter:
            search_url += f"&set={quote_plus(set_filter)}"

        page_url: str | None = search_url
        while page_url:
            html = await fetch_text(client, page_url, rate_limiter=rate_limiter)
            card_urls = _parse_search_results(html)
            for u in card_urls:
                refs.append(CardRef(provider=self.name, url=u))
                if 0 < limit <= len(refs):
                    return refs
            page_url = _next_page_url(html)
        return refs

    async def resolve(
        self,
        client: httpx.AsyncClient,
        ref: CardRef,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> CardAsset:
        html = await fetch_text(client, ref.url, rate_limiter=rate_limiter)
        return parse_card_page(html, page_url=ref.url)

    async def fetch_image(
        self,
        client: httpx.AsyncClient,
        asset: CardAsset,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> FetchedImage:
        if not asset.image_url:
            raise ValueError(f"No image URL for card {asset.name!r}")
        data = await fetch_bytes(client, asset.image_url, rate_limiter=rate_limiter)
        ext = asset.image_url.rsplit(".", 1)[-1].lower()
        mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
        return FetchedImage(data=data, mime_type=mime, source_url=asset.image_url)
