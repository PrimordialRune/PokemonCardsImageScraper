"""Async HTTP client with rate limiting and retries."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_UA = (
    "ptcg-art-scraper/0.1 "
    "(+https://github.com/PrimordialRune/pkmncardsPreviewScraper)"
)


class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, rate: float = 2.0) -> None:
        self._min_interval = 1.0 / rate if rate > 0 else 0.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class HttpClient:
    """Thin wrapper around ``httpx.AsyncClient`` with retry + rate limiting."""

    def __init__(
        self,
        rate: float = 2.0,
        retries: int = 3,
        timeout: float = 20.0,
        user_agent: Optional[str] = None,
    ) -> None:
        self.rate_limiter = RateLimiter(rate)
        self.retries = retries
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": user_agent or _DEFAULT_UA},
            follow_redirects=True,
        )

    async def get(self, url: str) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            await self.rate_limiter.acquire()
            try:
                resp = await self._client.get(url)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"Server returned {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                backoff = 2 ** (attempt - 1)
                logger.warning(
                    "Attempt %d/%d for %s failed: %s – retrying in %ss",
                    attempt,
                    self.retries,
                    url,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
        raise last_exc  # type: ignore[misc]

    async def close(self) -> None:
        await self._client.aclose()
