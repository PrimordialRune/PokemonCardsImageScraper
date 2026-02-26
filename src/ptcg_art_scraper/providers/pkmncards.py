"""pkmncards.com provider."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

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

    # --- set / number from breadcrumbs or page text ---
    set_name = ""
    set_code = ""
    number = ""

    # Try the card detail table / info area
    for row in soup.select("table tr, .card-tab-otherwise-text div"):
        text = row.get_text(" ", strip=True).lower()
        if "set" in text:
            parts = text.split(":", 1)
            if len(parts) == 2:
                set_name = parts[1].strip()
        if "number" in text:
            parts = text.split(":", 1)
            if len(parts) == 2:
                number = parts[1].strip().lstrip("#")

    # Try parsing name like "Charizard ex – 100/197"
    if not number and name:
        m = re.search(r"(\d+)\s*/\s*\d+", name)
        if m:
            number = m.group(1)

    # Attempt set code from URL segments (e.g. /card/{slug}/)
    if not set_code and page_url:
        parts = [p for p in page_url.rstrip("/").split("/") if p]
        # pkmncards URLs: …/card/{card-slug}/
        if len(parts) >= 2 and parts[-2] == "card":
            set_code = parts[-1]

    return CardAsset(
        name=name,
        set_name=set_name,
        set_code=set_code,
        number=number,
        image_url=image_url,
        source_page_url=page_url,
        provider="pkmncards",
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
