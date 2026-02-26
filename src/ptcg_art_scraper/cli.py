"""CLI entry-point for ptcg_art_scraper (Typer)."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ptcg_art_scraper.image.normalize import (
    TARGET_DPI,
    TARGET_HEIGHT,
    TARGET_WIDTH,
    normalize_image,
    verify_image,
)
from ptcg_art_scraper.models import ScrapeStats, utcnow_iso
from ptcg_art_scraper.net.http import HttpClient
from ptcg_art_scraper.providers.base import BaseProvider
from ptcg_art_scraper.providers.pkmncards import PkmncardsProvider
from ptcg_art_scraper.storage.layout import output_paths
from ptcg_art_scraper.storage.metadata import build_metadata, write_metadata

app = typer.Typer(name="ptcg_art_scraper", add_completion=False)
console = Console()

PROVIDERS: dict[str, BaseProvider] = {
    "pkmncards": PkmncardsProvider(),
}


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _read_input_file(path: str) -> list[str]:
    """Read card identifiers from a text, CSV or JSON file."""
    ext = Path(path).suffix.lower()
    with open(path, encoding="utf-8") as fh:
        if ext == ".json":
            data = json.load(fh)
            if isinstance(data, list):
                return [str(x) for x in data]
            raise typer.BadParameter("JSON input must be a list of strings/URLs")
        if ext == ".csv":
            reader = csv.reader(fh)
            return [row[0] for row in reader if row]
        # plain text: one entry per line
        return [line.strip() for line in fh if line.strip()]


# ── scrape ─────────────────────────────────────────────────────────────────

async def _scrape_cards(
    provider: BaseProvider,
    queries: list[str],
    out: str,
    *,
    set_filter: Optional[str],
    limit: int,
    concurrency: int,
    rate: float,
    retries: int,
    timeout: float,
    resume: bool,
    fmt: str,
    overwrite: bool,
) -> ScrapeStats:
    stats = ScrapeStats()
    client = HttpClient(rate=rate, retries=retries, timeout=timeout)
    sem = asyncio.Semaphore(concurrency)
    ext = ".jpg" if fmt == "jpg" else ".png"

    async def _process_query(query: str) -> None:
        try:
            # If the query looks like a URL, treat it as a direct card page
            if query.startswith("http://") or query.startswith("https://"):
                from ptcg_art_scraper.models import CardRef

                refs = [CardRef(provider=provider.name, url=query)]
            else:
                refs = list(await provider.search(
                    client, query, set_filter=set_filter, limit=limit
                ))
            for ref in refs:
                async with sem:
                    await _process_ref(ref)
        except Exception as exc:  # noqa: BLE001
            stats.failed += 1
            stats.errors.append({"query": query, "error": str(exc)})
            console.print(f"[red]✗[/red] {query}: {exc}")

    async def _process_ref(ref) -> None:  # type: ignore[no-untyped-def]
        try:
            asset = await provider.resolve(client, ref)
            img_path, json_path = output_paths(
                out,
                asset.name,
                asset.number,
                asset.set_name,
                asset.set_code,
                ext=ext,
            )
            already_done = (
                os.path.exists(img_path) and os.path.exists(json_path)
            )
            if resume and not overwrite and already_done:
                stats.skipped += 1
                console.print(f"[yellow]⊘[/yellow] skip {asset.name}")
                return

            fetched = await provider.fetch_image(client, asset)
            original_size, sha_orig, sha_norm = normalize_image(
                fetched.data, img_path, fmt=fmt  # type: ignore[arg-type]
            )
            meta = build_metadata(
                provider=provider.name,
                source_page_url=asset.source_page_url,
                source_image_url=asset.image_url,
                fetched_at_utc=utcnow_iso(),
                normalized_size=(TARGET_WIDTH, TARGET_HEIGHT),
                dpi=TARGET_DPI,
                original_size=original_size,
                sha256_original=sha_orig,
                sha256_normalized=sha_norm,
            )
            write_metadata(json_path, meta)
            stats.succeeded += 1
            console.print(f"[green]✓[/green] {asset.name} → {img_path}")
        except Exception as exc:  # noqa: BLE001
            stats.failed += 1
            stats.errors.append({"url": ref.url, "error": str(exc)})
            console.print(f"[red]✗[/red] {ref.url}: {exc}")

    tasks = [_process_query(q) for q in queries]
    await asyncio.gather(*tasks)
    await client.close()
    return stats


@app.command()
def scrape(
    out: str = typer.Option(..., help="Output directory"),
    provider: str = typer.Option("pkmncards", help="Provider name"),
    query: Optional[str] = typer.Option(None, help="Search query"),
    input: Optional[str] = typer.Option(None, help="Input file (text/CSV/JSON)"),  # noqa: A002
    set: Optional[str] = typer.Option(None, help="Set code/name filter"),  # noqa: A002
    limit: int = typer.Option(50, help="Max cards per query"),
    concurrency: int = typer.Option(8, help="Max concurrent downloads"),
    rate: float = typer.Option(2.0, help="Requests per second"),
    retries: int = typer.Option(3, help="Retry count"),
    timeout: float = typer.Option(20.0, help="Request timeout (seconds)"),
    resume: bool = typer.Option(True, help="Skip already-downloaded items"),
    format: str = typer.Option("png", help="Output format (png or jpg)"),  # noqa: A002
    overwrite: bool = typer.Option(False, help="Overwrite existing files"),
) -> None:
    """Scrape Pokémon card images from a provider."""
    _setup_logging()
    prov = PROVIDERS.get(provider)
    if prov is None:
        console.print(f"[red]Unknown provider:[/red] {provider}")
        raise typer.Exit(1)

    queries: list[str] = []
    if query:
        queries.append(query)
    if input:
        queries.extend(_read_input_file(input))
    if not queries:
        console.print("[red]Provide --query and/or --input[/red]")
        raise typer.Exit(1)

    os.makedirs(out, exist_ok=True)

    stats = asyncio.run(
        _scrape_cards(
            prov,
            queries,
            out,
            set_filter=set,
            limit=limit,
            concurrency=concurrency,
            rate=rate,
            retries=retries,
            timeout=timeout,
            resume=resume,
            fmt=format,
            overwrite=overwrite,
        )
    )

    console.print(
        f"\n[bold]Done.[/bold] ✓ {stats.succeeded}  ✗ {stats.failed}  ⊘ {stats.skipped}"
    )

    if stats.errors:
        err_path = os.path.join(out, "errors.jsonl")
        with open(err_path, "a", encoding="utf-8") as fh:
            for err in stats.errors:
                fh.write(json.dumps(err) + "\n")
        console.print(f"Errors written to {err_path}")

    if stats.failed:
        raise typer.Exit(1)


# ── normalize ──────────────────────────────────────────────────────────────

@app.command()
def normalize(
    input: str = typer.Option(..., "--input", help="Folder of images to normalize"),  # noqa: A002
    out: str = typer.Option(..., help="Output directory"),
    format: str = typer.Option("png", help="Output format (png or jpg)"),  # noqa: A002
) -> None:
    """Normalize existing images to 750×1050 @ 300 DPI."""
    _setup_logging()
    os.makedirs(out, exist_ok=True)
    ext = ".jpg" if format == "jpg" else ".png"
    count = 0
    for root, _dirs, files in os.walk(input):
        for fname in files:
            if not fname.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            src = os.path.join(root, fname)
            with open(src, "rb") as fh:
                raw = fh.read()
            dest = os.path.join(out, Path(fname).stem + ext)
            normalize_image(raw, dest, fmt=format)  # type: ignore[arg-type]
            count += 1
            console.print(f"[green]✓[/green] {dest}")
    console.print(f"[bold]Normalized {count} images.[/bold]")


# ── verify ─────────────────────────────────────────────────────────────────

@app.command()
def verify(
    input: str = typer.Option(..., "--input", help="Folder to verify"),  # noqa: A002
) -> None:
    """Verify images in a folder are 750×1050 @ 300 DPI."""
    _setup_logging()
    ok = 0
    bad = 0
    for root, _dirs, files in os.walk(input):
        for fname in files:
            if not fname.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            path = os.path.join(root, fname)
            problems = verify_image(path)
            if problems:
                bad += 1
                console.print(f"[red]✗[/red] {path}: {'; '.join(problems)}")
            else:
                ok += 1
    console.print(f"\n[bold]Verified:[/bold] ✓ {ok}  ✗ {bad}")
    if bad:
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
