"""Scrape engine that yields events – used by both CLI and GUI.

The engine wraps the existing provider/normalize/storage pipeline and
emits :class:`JobEvent` objects through a callback so the caller (GUI
worker thread or CLI progress bar) can update status in real time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable

import httpx

from ptcg_art_scraper.core.models import (
    EventType,
    ItemStatus,
    JobConfig,
    JobEvent,
    JobSummary,
    QueueItem,
)
from ptcg_art_scraper.image.normalize import normalize_image
from ptcg_art_scraper.models import CardRef, SidecarMetadata
from ptcg_art_scraper.net.http import DEFAULT_HEADERS, RateLimiter
from ptcg_art_scraper.storage.layout import card_output_path, sidecar_path, template_output_path
from ptcg_art_scraper.storage.metadata import save_sidecar

logger = logging.getLogger(__name__)

EventCallback = Callable[[JobEvent], None]


def _get_provider(name: str):
    """Resolve provider by name."""
    if name == "pkmncards":
        from ptcg_art_scraper.providers.pkmncards import PkmnCardsProvider

        return PkmnCardsProvider()
    if name == "pokemontcgio_images":
        from ptcg_art_scraper.providers.pokemontcgio_images import PokemonTcgioImagesProvider

        return PokemonTcgioImagesProvider()
    raise ValueError(f"Unknown provider: {name!r}")


def _decode_ref_metadata(card_id: str) -> dict[str, str]:
    """Decode optional metadata hints stored in ``CardRef.card_id``."""
    if not card_id:
        return {}
    try:
        payload = json.loads(card_id)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(key, str) and value is not None:
            out[key] = str(value)
    return out


class ScrapeEngine:
    """Run a scrape job and emit events for UI updates.

    Usage::

        engine = ScrapeEngine(config, items, on_event=callback)
        await engine.run()          # or: asyncio.run(engine.run())
        engine.request_pause()      # from another thread
        engine.request_cancel()     # from another thread
    """

    def __init__(
        self,
        config: JobConfig,
        items: list[QueueItem],
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config
        self.items = list(items)
        self._on_event = on_event or (lambda _e: None)
        self._paused = asyncio.Event()
        self._paused.set()  # not paused initially
        self._cancelled = False

    # -- thread-safe controls -----------------------------------------------

    def request_pause(self) -> None:
        self._paused.clear()

    def request_resume(self) -> None:
        self._paused.set()

    def request_cancel(self) -> None:
        self._cancelled = True
        self._paused.set()  # unblock if paused

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()

    # -- event helpers ------------------------------------------------------

    def _emit(self, event_type: EventType, item_id: str = "", **kwargs) -> None:
        evt = JobEvent(
            event_type=event_type,
            item_id=item_id,
            timestamp=JobEvent.now(),
            **kwargs,
        )
        self._on_event(evt)

    # -- main run -----------------------------------------------------------

    async def run(self) -> JobSummary:
        summary = JobSummary(total=len(self.items))
        self._emit(EventType.JOB_STARTED, message=f"Starting job with {len(self.items)} cards")

        prov = _get_provider(self.config.provider)
        rl = RateLimiter(self.config.rate)
        sem = asyncio.Semaphore(self.config.concurrency)
        out = Path(self.config.output_dir)
        fmt = self.config.fmt

        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            tasks = []
            for item in self.items:
                if not item.selected:
                    item.status = ItemStatus.SKIPPED
                    summary.skipped += 1
                    self._emit(
                        EventType.ITEM_SKIPPED,
                        item_id=item.id,
                        message="Deselected by user",
                    )
                    continue
                tasks.append(
                    asyncio.create_task(
                        self._process_item(item, prov, client, rl, sem, out, fmt, summary)
                    )
                )

            for coro in asyncio.as_completed(tasks):
                await coro
                if self._cancelled:
                    break

        if self._cancelled:
            # Cancel remaining tasks
            for t in tasks:
                if not t.done():
                    t.cancel()
            self._emit(EventType.JOB_CANCELLED, message="Job cancelled by user")
        else:
            self._emit(
                EventType.JOB_FINISHED,
                message=(
                    f"Done: {summary.succeeded} saved, "
                    f"{summary.skipped} skipped, {summary.failed} failed"
                ),
            )
        return summary

    async def _process_item(
        self,
        item: QueueItem,
        prov,
        client: httpx.AsyncClient,
        rl: RateLimiter,
        sem: asyncio.Semaphore,
        out: Path,
        fmt: str,
        summary: JobSummary,
    ) -> None:
        async with sem:
            # Check pause/cancel
            await self._paused.wait()
            if self._cancelled:
                return

            try:
                # Resolve
                item.status = ItemStatus.RESOLVING
                self._emit(
                    EventType.ITEM_RESOLVING,
                    item_id=item.id,
                    message="Resolving metadata…",
                    progress=0.1,
                )
                ref = CardRef(provider=self.config.provider, url=item.identifier)
                asset = await prov.resolve(client, ref, rate_limiter=rl)

                # Preserve metadata parsed during search if detail resolution is sparse.
                asset.name = asset.name or item.name
                asset.set_name = asset.set_name or item.set_name
                asset.set_code = asset.set_code or item.set_code
                asset.number = asset.number or item.number
                asset.image_url = asset.image_url or item.image_url

                # Update item metadata
                item.name = asset.name or item.name
                item.set_name = asset.set_name or item.set_name
                item.number = asset.number or item.number
                item.image_url = asset.image_url
                item.source_url = asset.source_page_url or item.identifier
                item.basic_type = asset.basic_type
                item.specific_type = asset.specific_type
                item.rarity = asset.rarity
                item.set_code = asset.set_code

                if self.config.folder_template:
                    dest = template_output_path(
                        out, asset, fmt=fmt, template=self.config.folder_template
                    )
                else:
                    dest = card_output_path(out, asset, fmt=fmt)
                json_dest = sidecar_path(dest)
                item.output_path = str(dest)

                # Skip if already exists
                if (
                    self.config.resume
                    and not self.config.overwrite
                    and dest.exists()
                    and json_dest.exists()
                ):
                    item.status = ItemStatus.SKIPPED
                    item.message = "Already downloaded"
                    summary.skipped += 1
                    self._emit(
                        EventType.ITEM_SKIPPED,
                        item_id=item.id,
                        message="Already downloaded",
                        progress=1.0,
                    )
                    return

                # Check pause/cancel
                await self._paused.wait()
                if self._cancelled:
                    return

                # Fetch image
                item.status = ItemStatus.FETCHING
                self._emit(
                    EventType.ITEM_FETCHING,
                    item_id=item.id,
                    message="Downloading image…",
                    progress=0.4,
                )
                fetched = await prov.fetch_image(client, asset, rate_limiter=rl)

                # Normalize
                item.status = ItemStatus.NORMALIZING
                self._emit(
                    EventType.ITEM_NORMALIZING,
                    item_id=item.id,
                    message="Normalizing…",
                    progress=0.7,
                )
                meta_info = normalize_image(fetched.data, dest, fmt=fmt)

                sidecar = SidecarMetadata.from_asset(
                    asset,
                    fetched_at_utc=SidecarMetadata.now_utc(),
                    normalized_size=[meta_info["width"], meta_info["height"]],
                    dpi=meta_info["dpi"],
                    original_size=[meta_info["original_width"], meta_info["original_height"]],
                    sha256_original=meta_info["sha256_original"],
                    sha256_normalized=meta_info["sha256_normalized"],
                    normalized_output_path=str(dest),
                    image_variant=(
                        "hires" if "_hires.png" in fetched.source_url
                        else "standard" if asset.provider == "pokemontcgio_images"
                        else ""
                    ),
                )
                save_sidecar(sidecar, json_dest)

                item.status = ItemStatus.SAVED
                item.progress = 1.0
                item.message = ""
                summary.succeeded += 1
                self._emit(
                    EventType.ITEM_SAVED,
                    item_id=item.id,
                    message=f"Saved → {dest.name}",
                    progress=1.0,
                )

            except Exception as exc:
                item.status = ItemStatus.FAILED
                item.message = str(exc)
                summary.failed += 1
                summary.errors.append({"ref": item.identifier, "error": str(exc)})
                self._emit(
                    EventType.ITEM_FAILED,
                    item_id=item.id,
                    message=str(exc),
                )
                logger.error("Failed %s: %s", item.identifier, exc)


async def resolve_search(
    provider_name: str,
    query: str,
    *,
    set_filter: str = "",
    limit: int = 0,
    rate: float = 2.0,
    timeout: float = 20.0,
) -> list[QueueItem]:
    """Search a provider and return :class:`QueueItem` objects for preview."""
    prov = _get_provider(provider_name)
    rl = RateLimiter(rate)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        refs = await prov.search(
            client, query, set_filter=set_filter, limit=limit, rate_limiter=rl
        )
        items: list[QueueItem] = []
        for ref in refs:
            meta = _decode_ref_metadata(ref.card_id)
            items.append(
                QueueItem(
                    identifier=ref.url,
                    source_url=ref.url,
                    provider=provider_name,
                    name=meta.get("name", ""),
                    set_name=meta.get("set_name", ""),
                    set_code=meta.get("set_code", ""),
                    number=meta.get("number", ""),
                    image_url=meta.get("image_url", ""),
                )
            )
        return items
