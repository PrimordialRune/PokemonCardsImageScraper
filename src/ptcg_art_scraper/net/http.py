"""Async HTTP helpers with retry, rate-limiting, and bounded concurrency."""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3
DEFAULT_CONCURRENCY = 8
DEFAULT_RATE = 2.0  # requests per second
DEFAULT_HEADERS = {
    "User-Agent": (
        "ptcg-art-scraper/1.0 "
        "(https://github.com/pokemon-tcg/ptcg-art-scraper)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Transient HTTP status codes that deserve a retry.
_TRANSIENT = {408, 429, 500, 502, 503, 504}


class RateLimiter:
    """Simple token-bucket style rate limiter."""

    def __init__(self, rate: float) -> None:
        self._interval = 1.0 / rate if rate > 0 else 0.0
        self._last = 0.0

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        now = asyncio.get_event_loop().time()
        wait = self._last + self._interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = asyncio.get_event_loop().time()


async def fetch_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = DEFAULT_RETRIES,
    rate_limiter: RateLimiter | None = None,
) -> bytes:
    """Download *url* with exponential back-off on transient errors."""
    last_exc: BaseException | None = None
    for attempt in range(1, retries + 1):
        if rate_limiter:
            await rate_limiter.acquire()
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code in _TRANSIENT:
                raise httpx.HTTPStatusError(
                    f"Transient {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
            resp.raise_for_status()
            return resp.content
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            delay = (2**attempt) + random.uniform(0, 1)
            logger.warning(
                "Attempt %d/%d for %s failed: %s - retrying in %.1fs",
                attempt,
                retries,
                url,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    detail = f": {last_exc}" if last_exc is not None else ""
    raise RuntimeError(
        f"All {retries} attempts for {url} failed{detail}"
    ) from last_exc


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = DEFAULT_RETRIES,
    rate_limiter: RateLimiter | None = None,
) -> str:
    """Download *url* and return text content."""
    raw = await fetch_bytes(client, url, retries=retries, rate_limiter=rate_limiter)
    return raw.decode("utf-8", errors="replace")
