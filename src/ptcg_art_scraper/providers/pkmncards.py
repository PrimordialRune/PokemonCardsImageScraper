"""pkmncards.com provider."""

from __future__ import annotations

import logging
import re
from typing import Optional, Sequence
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ptcg_art_scraper.models import CardAsset, CardRef, FetchedImage
from ptcg_art_scraper.net.http import HttpClient
from ptcg_art_scraper.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_BASE = "https://pkmncards.com/"
_SEARCH_URL = _BASE + "?s={query}"


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _parse_search_results(html: str) -> list[str]:
    """Return card page URLs from a pkmncards.com search result page."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a_tag in soup.select("a.card-image-otherwise-text"):
        href = a_tag.get("href")
        if href:
            urls.append(str(href))
    if not urls:
        for entry in soup.select(".entry-title a"):
            href = entry.get("href")
            if href:
                urls.append(str(href))
    return urls


def _parse_card_page(html: str, page_url: str) -> CardAsset:
    """Extract card metadata and image URL from a card detail page."""
    soup = BeautifulSoup(html, "html.parser")

    # Image URL – look for the large card image
    image_url = ""
    img_tag = soup.select_one("div.card-image img")
    if img_tag:
        image_url = str(img_tag.get("src", ""))
    if not image_url:
        img_tag = soup.select_one("img.card-image")
        if img_tag:
            image_url = str(img_tag.get("src", ""))
    if not image_url:
        # broader fallback: img with pkmncards.com + wp-content path
        for img in soup.find_all("img"):
            src = str(img.get("src", ""))
            if "pkmncards.com" in src and "/wp-content/" in src:
                image_url = src
                break
    if image_url and image_url.startswith("//"):
        image_url = "https:" + image_url

    # Title / name
    name = ""
    title_tag = soup.select_one("h1.entry-title") or soup.select_one("h2.entry-title")
    if title_tag and hasattr(title_tag, "get_text"):
        name = title_tag.get_text(strip=True)
    if not name:
        fallback_title = soup.find("title")
        if fallback_title and hasattr(fallback_title, "get_text"):
            name = fallback_title.get_text(strip=True).split("|")[0].strip()

    # Try to extract set, number from page text or breadcrumbs
    set_name = ""
    set_code: str | None = None
    number: str | None = None
    rarity: str | None = None
    artist: str | None = None

    # Look for structured data in a detail table or text block
    detail_text = ""
    for el in soup.select(".pokemon-info li, .card-details li, .entry-content p"):
        detail_text += " " + el.get_text(" ", strip=True)

    # number: e.g. "100/197"
    m = re.search(r"(\d+)\s*/\s*(\d+)", detail_text)
    if m:
        number = f"{m.group(1)}/{m.group(2)}"
    if not number:
        m = re.search(r"(\d+)\s*/\s*(\d+)", name)
        if m:
            number = f"{m.group(1)}/{m.group(2)}"

    # set name from breadcrumb or detail
    for bc in soup.select("nav.breadcrumbs a, .breadcrumb a"):
        bc_text = bc.get_text(strip=True)
        if bc_text.lower() not in ("home", "cards", "pokémon", "pokemon", ""):
            set_name = bc_text

    return CardAsset(
        name=name or "Unknown",
        set_name=set_name or "Unknown",
        set_code=set_code,
        number=number,
        rarity=rarity,
        artist=artist,
        source_page_url=page_url,
        image_url=image_url,
        provider="pkmncards",
    )


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class PkmncardsProvider(BaseProvider):
    name = "pkmncards"

    async def search(
        self,
        client: HttpClient,
        query: str,
        *,
        set_filter: Optional[str] = None,
        limit: int = 50,
    ) -> Sequence[CardRef]:
        full_query = query
        if set_filter:
            full_query = f"{query} {set_filter}"
        url = _SEARCH_URL.format(query=quote_plus(full_query))
        resp = await client.get(url)
        urls = _parse_search_results(resp.text)
        refs = [CardRef(provider=self.name, url=u) for u in urls[:limit]]
        logger.info("pkmncards search for %r returned %d results", query, len(refs))
        return refs

    async def resolve(self, client: HttpClient, ref: CardRef) -> CardAsset:
        resp = await client.get(ref.url)
        return _parse_card_page(resp.text, ref.url)

    async def fetch_image(
        self, client: HttpClient, asset: CardAsset
    ) -> FetchedImage:
        if not asset.image_url:
            raise ValueError(f"No image URL for card: {asset.name}")
        resp = await client.get(asset.image_url)
        mime = resp.headers.get("content-type", "image/png")
        return FetchedImage(
            data=resp.content,
            mime_type=mime,
            source_url=asset.image_url,
            card_asset=asset,
        )
