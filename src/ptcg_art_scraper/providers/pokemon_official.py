"""Official Pokemon asset provider."""

from __future__ import annotations

import json
import logging

import httpx

from ptcg_art_scraper.models import CardAsset, CardRef, FetchedImage
from ptcg_art_scraper.net.http import RateLimiter, fetch_bytes
from ptcg_art_scraper.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_IMAGE_HOST = "https://assets.pokemon.com"
_IMAGE_PREFIX = f"{_IMAGE_HOST}/static-assets/content-assets/cms2/img/cards/web/"


def image_url(set_code: str, card_number: str) -> str:
    """Build an official Pokemon card asset URL."""
    cleaned_set = str(set_code).strip()
    cleaned_number = str(card_number).strip()
    return (
        f"{_IMAGE_PREFIX}{cleaned_set}/{cleaned_set}_EN_{cleaned_number}.png"
    )


def parse_image_url(url: str) -> tuple[str, str] | None:
    """Extract ``(set_code, card_number)`` from an official asset URL."""
    if not url.startswith(_IMAGE_PREFIX):
        return None
    path = url[len(_IMAGE_PREFIX) :]
    parts = path.split("/", 1)
    if len(parts) != 2:
        return None
    set_code, filename = parts
    prefix = f"{set_code}_EN_"
    if not set_code or not filename.startswith(prefix) or not filename.endswith(".png"):
        return None
    card_number = filename[len(prefix) : -4].strip()
    if not card_number:
        return None
    return set_code, card_number


class PokemonOfficialAssetProvider(BaseProvider):
    """Provider that deterministically builds official Pokemon asset URLs."""

    name = "pokemon_official"

    def get_image_url(self, set_code: str, card_number: str) -> str | None:
        cleaned_set = str(set_code).strip()
        cleaned_number = str(card_number).strip()
        if not cleaned_set:
            logger.info("%s failed deterministically: missing set code", self.name)
            return None
        if not cleaned_number:
            logger.info("%s failed deterministically: missing card number", self.name)
            return None
        return image_url(cleaned_set, cleaned_number)

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        set_filter: str = "",
        limit: int = 0,
        rate_limiter: RateLimiter | None = None,
    ) -> list[CardRef]:
        del client, limit, rate_limiter
        if query.startswith(_IMAGE_PREFIX):
            parsed = parse_image_url(query)
            if parsed is None:
                logger.info("%s failed deterministically: invalid official asset URL", self.name)
                return []
            set_code, number = parsed
            return [self._build_ref(set_code, number)]

        url = self.get_image_url(set_filter, query)
        if url is None:
            logger.info(
                "%s failed deterministically: requires --set plus card number query",
                self.name,
            )
            return []
        return [self._build_ref(str(set_filter).strip(), str(query).strip(), url=url)]

    async def resolve(
        self,
        client: httpx.AsyncClient,
        ref: CardRef,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> CardAsset:
        del client, rate_limiter
        meta: dict[str, str] = {}
        if ref.card_id:
            try:
                payload = json.loads(ref.card_id)
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                meta = {
                    str(key): str(value)
                    for key, value in payload.items()
                    if isinstance(key, str) and value is not None
                }

        set_code = meta.get("set_code", "")
        number = meta.get("number", "")
        if not set_code or not number:
            parsed = parse_image_url(ref.url)
            if parsed is None:
                raise ValueError(
                    "Official Pokemon asset references require "
                    "a valid set code and card number"
                )
            set_code, number = parsed

        url = self.get_image_url(set_code, number)
        if url is None:
            raise ValueError(
                "Official Pokemon asset references require "
                "a valid set code and card number"
            )

        return CardAsset(
            name=f"{set_code}-{number}",
            set_name=set_code,
            set_code=set_code,
            number=number,
            source_page_url=url,
            image_url=url,
            provider=self.name,
        )

    async def fetch_image(
        self,
        client: httpx.AsyncClient,
        asset: CardAsset,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> FetchedImage:
        if not asset.image_url:
            raise ValueError("Official Pokemon asset provider requires an image URL")
        data = await fetch_bytes(client, asset.image_url, rate_limiter=rate_limiter)
        return FetchedImage(data=data, mime_type="image/png", source_url=asset.image_url)

    def _build_ref(self, set_code: str, number: str, *, url: str | None = None) -> CardRef:
        resolved_url = url or image_url(set_code, number)
        meta = {"set_code": set_code, "number": number, "image_url": resolved_url}
        return CardRef(
            provider=self.name,
            url=resolved_url,
            card_id=json.dumps(meta),
        )
