"""Central image resolution service with provider fallback tracing."""

from __future__ import annotations

import asyncio
import logging

import httpx

from ptcg_art_scraper.core.config import ResolverConfig
from ptcg_art_scraper.core.models import (
    CardIdentifier,
    ProviderAttempt,
    ProviderCandidate,
    ResolvedImage,
)
from ptcg_art_scraper.core.providers import create_provider
from ptcg_art_scraper.net.http import DEFAULT_HEADERS, RateLimiter

logger = logging.getLogger(__name__)


class ImageResolutionService:
    """Resolve a card image URL through ordered providers."""

    def __init__(self, config: ResolverConfig | None = None) -> None:
        self.config = config or ResolverConfig()
        self.last_attempts: list[ProviderAttempt] = []

    def resolve(self, set_code: str, card_number: str) -> str | None:
        resolved = asyncio.run(self._resolve(CardIdentifier(set_code=set_code, card_number=card_number)))
        return resolved.resolved_url if resolved else None

    async def resolve_card(self, card: CardIdentifier) -> ResolvedImage | None:
        return await self._resolve(card)

    async def _resolve(self, card: CardIdentifier) -> ResolvedImage | None:
        self.last_attempts = []
        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            limiter = RateLimiter(self.config.rate)
            for provider_name in self.config.provider_priority:
                provider = create_provider(provider_name)
                logger.info("Trying provider %s for %s", provider_name, card.label)
                try:
                    candidate = await provider.resolve(client, card, rate_limiter=limiter)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Provider %s failed for %s", provider_name, card.label)
                    self.last_attempts.append(
                        ProviderAttempt(provider=provider_name, status="error", detail=str(exc))
                    )
                    continue
                if candidate is None:
                    self.last_attempts.append(
                        ProviderAttempt(provider=provider_name, status="miss", detail="No candidate")
                    )
                    continue
                resolved_url = await self._select_url(client, candidate, limiter)
                if not resolved_url:
                    self.last_attempts.append(
                        ProviderAttempt(
                            provider=provider_name,
                            status="miss",
                            detail="Candidate URL check failed",
                        )
                    )
                    continue
                candidate.asset.provider = provider_name
                candidate.asset.image_url = resolved_url
                if not candidate.asset.source_page_url:
                    candidate.asset.source_page_url = resolved_url
                attempt = ProviderAttempt(
                    provider=provider_name,
                    status="ok",
                    detail="Resolved",
                    url=resolved_url,
                )
                self.last_attempts.append(attempt)
                return ResolvedImage(card=card, asset=candidate.asset, attempts=list(self.last_attempts))
        return None

    async def _select_url(
        self,
        client: httpx.AsyncClient,
        candidate: ProviderCandidate,
        limiter: RateLimiter,
    ) -> str | None:
        if not candidate.candidate_urls:
            return None
        if not self.config.verify_urls:
            return candidate.candidate_urls[0]
        for url in candidate.candidate_urls:
            if await self._probe_url(client, url, limiter):
                return url
        return None

    async def _probe_url(
        self,
        client: httpx.AsyncClient,
        url: str,
        limiter: RateLimiter,
    ) -> bool:
        await limiter.acquire()
        try:
            response = await client.head(url, follow_redirects=True)
            if response.status_code < 400:
                return True
            if response.status_code not in {403, 405}:
                return False
        except httpx.HTTPError:
            pass
        await limiter.acquire()
        try:
            response = await client.get(url, follow_redirects=True, headers={"Range": "bytes=0-0"})
            return response.status_code < 400
        except httpx.HTTPError:
            return False
