"""Batch scraping orchestration for the redesigned CLI."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable

import httpx

from ptcg_art_scraper.core.config import BatchScrapeConfig, ResolverConfig
from ptcg_art_scraper.core.exceptions import DownloadError, ResolutionError
from ptcg_art_scraper.core.models import (
    BatchItemResult,
    BatchSummary,
    CardIdentifier,
    FetchedImage,
    ResolvedImage,
    SidecarMetadata,
)
from ptcg_art_scraper.core.services.image_resolution import ImageResolutionService
from ptcg_art_scraper.core.services.image_pipeline import normalize_image
from ptcg_art_scraper.core.services.output import (
    card_output_path,
    save_sidecar,
    sidecar_path,
    template_output_path,
)
from ptcg_art_scraper.net.http import DEFAULT_HEADERS, RateLimiter, fetch_bytes

logger = logging.getLogger(__name__)

BatchCallback = Callable[[str, dict[str, str]], None]


class BatchScrapeService:
    """Single source of truth for batch processing."""

    def __init__(self, config: BatchScrapeConfig) -> None:
        self.config = config
        self.resolver = ImageResolutionService(
            ResolverConfig(
                provider_priority=config.provider_priority,
                verify_urls=config.verify_urls,
                timeout=config.timeout,
                rate=config.rate,
            )
        )

    async def run(
        self,
        cards: list[CardIdentifier],
        on_event: BatchCallback | None = None,
    ) -> BatchSummary:
        summary = BatchSummary(total=len(cards))
        event = on_event or (lambda *_args, **_kwargs: None)
        semaphore = asyncio.Semaphore(self.config.concurrency)
        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            limiter = RateLimiter(self.config.rate)
            tasks = [
                asyncio.create_task(self._process_card(card, client, limiter, semaphore, event))
                for card in cards
            ]
            for task in asyncio.as_completed(tasks):
                result = await task
                summary.results.append(result)
                if result.status == "saved":
                    summary.succeeded += 1
                elif result.status == "skipped":
                    summary.skipped += 1
                else:
                    summary.failed += 1
        return summary

    async def _process_card(
        self,
        card: CardIdentifier,
        client: httpx.AsyncClient,
        limiter: RateLimiter,
        semaphore: asyncio.Semaphore,
        on_event: BatchCallback,
    ) -> BatchItemResult:
        async with semaphore:
            on_event("item.started", {"card": card.label})
            resolved = await self.resolver.resolve_card(card)
            if resolved is None:
                message = "No provider could resolve an image URL."
                on_event("item.failed", {"card": card.label, "error": message})
                return BatchItemResult(
                    card=card,
                    status="failed",
                    error=message,
                    attempts=list(self.resolver.last_attempts),
                )

            on_event(
                "item.resolved",
                {
                    "card": card.label,
                    "provider": resolved.provider,
                    "url": resolved.resolved_url,
                },
            )
            try:
                output_path = self._output_path(resolved.asset)
                sidecar = sidecar_path(output_path)
                if not self.config.overwrite and output_path.exists() and sidecar.exists():
                    on_event(
                        "item.skipped",
                        {"card": card.label, "output_path": str(output_path)},
                    )
                    return BatchItemResult(
                        card=card,
                        status="skipped",
                        provider=resolved.provider,
                        resolved_url=resolved.resolved_url,
                        output_path=str(output_path),
                        sidecar_path=str(sidecar),
                        attempts=resolved.attempts,
                    )
                fetched = await self._download(client, resolved, limiter)
                meta = normalize_image(fetched.data, output_path, fmt=self.config.image_format)
                save_sidecar(
                    SidecarMetadata.from_asset(
                        resolved.asset,
                        fetched_at_utc=SidecarMetadata.now_utc(),
                        normalized_size=[meta["width"], meta["height"]],
                        dpi=meta["dpi"],
                        original_size=[meta["original_width"], meta["original_height"]],
                        sha256_original=meta["sha256_original"],
                        sha256_normalized=meta["sha256_normalized"],
                        normalized_output_path=str(output_path),
                        image_variant=(
                            "hires" if "_hires.png" in fetched.source_url else "standard"
                        ),
                    ),
                    sidecar,
                )
                on_event(
                    "item.saved",
                    {
                        "card": card.label,
                        "provider": resolved.provider,
                        "output_path": str(output_path),
                    },
                )
                return BatchItemResult(
                    card=card,
                    status="saved",
                    provider=resolved.provider,
                    resolved_url=resolved.resolved_url,
                    output_path=str(output_path),
                    sidecar_path=str(sidecar),
                    attempts=resolved.attempts,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed processing %s", card.label)
                message = str(exc)
                on_event("item.failed", {"card": card.label, "error": message})
                return BatchItemResult(
                    card=card,
                    status="failed",
                    provider=resolved.provider,
                    resolved_url=resolved.resolved_url,
                    error=message,
                    attempts=resolved.attempts,
                )

    async def _download(
        self,
        client: httpx.AsyncClient,
        resolved: ResolvedImage,
        limiter: RateLimiter,
    ) -> FetchedImage:
        try:
            data = await fetch_bytes(
                client,
                resolved.resolved_url,
                retries=self.config.retries,
                rate_limiter=limiter,
            )
        except Exception as exc:  # noqa: BLE001
            raise DownloadError("Failed to download the resolved image.", debug_message=str(exc)) from exc
        return FetchedImage(data=data, source_url=resolved.resolved_url)

    def _output_path(self, asset) -> Path:
        if self.config.folder_template:
            return template_output_path(
                self.config.output_dir,
                asset,
                fmt=self.config.image_format,
                template=self.config.folder_template,
            )
        return card_output_path(self.config.output_dir, asset, fmt=self.config.image_format)
