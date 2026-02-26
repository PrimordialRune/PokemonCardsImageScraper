"""CLI entry-point built with Typer."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ptcg_art_scraper.image.normalize import normalize_image, verify_image
from ptcg_art_scraper.models import SidecarMetadata
from ptcg_art_scraper.storage.layout import card_output_path, sidecar_path
from ptcg_art_scraper.storage.metadata import save_sidecar

app = typer.Typer(name="ptcg_art_scraper", help="Pokémon TCG card image scraper & normalizer.")
console = Console()

logger = logging.getLogger("ptcg_art_scraper")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )


def _get_provider(name: str):
    """Resolve provider by name."""
    if name == "pkmncards":
        from ptcg_art_scraper.providers.pkmncards import PkmnCardsProvider

        return PkmnCardsProvider()
    raise typer.BadParameter(f"Unknown provider: {name!r}")


def _load_input_file(path: Path) -> list[str]:
    """Read card identifiers/URLs from a text, CSV, or JSON file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            return [str(item) for item in data]
        return []
    # Text / CSV – one entry per line, ignore blanks and comments
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            # For CSV take the first column
            lines.append(line.split(",")[0].strip())
    return lines


# ---------------------------------------------------------------------------
# scrape
# ---------------------------------------------------------------------------
@app.command()
def scrape(
    out: Path = typer.Option(..., help="Output directory for normalized images."),
    provider: str = typer.Option("pkmncards", help="Card image provider to use."),
    query: Optional[str] = typer.Option(None, help="Search query (provider-specific)."),
    input: Optional[Path] = typer.Option(None, help="File with card identifiers/URLs."),
    card_set: Optional[str] = typer.Option(None, "--set", help="Set code/name filter."),
    limit: int = typer.Option(0, help="Max cards to download (0 = unlimited)."),
    concurrency: int = typer.Option(8, help="Max concurrent downloads."),
    rate: float = typer.Option(2.0, help="Max requests per second."),
    retries: int = typer.Option(3, help="Retry count on transient failures."),
    timeout: float = typer.Option(20.0, help="HTTP timeout in seconds."),
    resume: bool = typer.Option(True, help="Skip already-downloaded items."),
    format: str = typer.Option("png", help="Output format: png or jpg."),
    overwrite: bool = typer.Option(False, help="Re-download and overwrite existing files."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Scrape card images from a provider and save normalized images."""
    _setup_logging(verbose)
    fmt = format.lower()
    if fmt not in ("png", "jpg", "jpeg"):
        raise typer.BadParameter("--format must be png or jpg")
    if fmt == "jpeg":
        fmt = "jpg"

    prov = _get_provider(provider)

    # Gather card identifiers
    identifiers: list[str] = []
    if query:
        identifiers.append(query)
    if input and input.is_file():
        identifiers.extend(_load_input_file(input))
    if not identifiers:
        console.print("[red]Provide --query and/or --input with card identifiers.[/red]")
        raise typer.Exit(1)

    asyncio.run(
        _run_scrape(
            prov=prov,
            identifiers=identifiers,
            out=out,
            fmt=fmt,
            concurrency=concurrency,
            rate=rate,
            retries=retries,
            timeout=timeout,
            resume=resume,
            overwrite=overwrite,
            set_filter=card_set or "",
            limit=limit,
        )
    )


async def _run_scrape(
    *,
    prov,
    identifiers: list[str],
    out: Path,
    fmt: str,
    concurrency: int,
    rate: float,
    retries: int,
    timeout: float,
    resume: bool,
    overwrite: bool,
    set_filter: str,
    limit: int,
) -> None:
    import httpx

    from ptcg_art_scraper.models import CardRef
    from ptcg_art_scraper.net.http import RateLimiter

    rl = RateLimiter(rate)
    sem = asyncio.Semaphore(concurrency)
    errors: list[dict] = []
    succeeded = 0
    skipped = 0
    failed = 0

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        # 1. Resolve identifiers → CardRefs
        all_refs: list[CardRef] = []
        for ident in identifiers:
            if ident.startswith("http://") or ident.startswith("https://"):
                all_refs.append(CardRef(provider=prov.name, url=ident))
            else:
                refs = await prov.search(
                    client, ident, set_filter=set_filter, limit=limit, rate_limiter=rl
                )
                all_refs.extend(refs)
        if limit > 0:
            all_refs = all_refs[:limit]

        console.print(f"[bold]Found {len(all_refs)} card(s) to process.[/bold]")

        # 2. Process each card
        async def _process(ref: CardRef) -> None:
            nonlocal succeeded, skipped, failed
            async with sem:
                try:
                    asset = await prov.resolve(client, ref, rate_limiter=rl)
                    dest = card_output_path(out, asset, fmt=fmt)
                    json_dest = sidecar_path(dest)

                    if resume and not overwrite and dest.exists() and json_dest.exists():
                        skipped += 1
                        return

                    fetched = await prov.fetch_image(client, asset, rate_limiter=rl)
                    meta_info = normalize_image(fetched.data, dest, fmt=fmt)

                    sidecar = SidecarMetadata(
                        provider=prov.name,
                        source_page_url=asset.source_page_url,
                        source_image_url=asset.image_url,
                        fetched_at_utc=SidecarMetadata.now_utc(),
                        normalized_size=[meta_info["width"], meta_info["height"]],
                        dpi=meta_info["dpi"],
                        original_size=[meta_info["original_width"], meta_info["original_height"]],
                        sha256_original=meta_info["sha256_original"],
                        sha256_normalized=meta_info["sha256_normalized"],
                    )
                    save_sidecar(sidecar, json_dest)
                    succeeded += 1
                except Exception as exc:
                    failed += 1
                    errors.append({"ref": ref.url, "error": str(exc)})
                    logger.error("Failed %s: %s", ref.url, exc)

        tasks = [asyncio.create_task(_process(r)) for r in all_refs]

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            tid = progress.add_task("Downloading…", total=len(tasks))
            for coro in asyncio.as_completed(tasks):
                await coro
                progress.advance(tid)

    # Summary
    console.print(f"\n[green]Succeeded:[/green] {succeeded}")
    console.print(f"[yellow]Skipped:[/yellow]  {skipped}")
    console.print(f"[red]Failed:[/red]    {failed}")

    if errors:
        err_path = out / "errors.jsonl"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        with err_path.open("a", encoding="utf-8") as fh:
            for err in errors:
                fh.write(json.dumps(err) + "\n")
        console.print(f"[red]Error details written to {err_path}[/red]")


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------
@app.command()
def normalize(
    input: Path = typer.Option(..., "--input", help="Folder of images to normalize."),
    out: Path = typer.Option(..., help="Output directory for normalized images."),
    format: str = typer.Option("png", help="Output format: png or jpg."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Normalize existing card images to 750×1050 @ 300 DPI."""
    _setup_logging(verbose)
    fmt = format.lower()
    if fmt == "jpeg":
        fmt = "jpg"

    if not input.is_dir():
        console.print(f"[red]{input} is not a directory.[/red]")
        raise typer.Exit(1)

    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for img_file in sorted(input.iterdir()):
        if img_file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        raw = img_file.read_bytes()
        dest = out / f"{img_file.stem}.{fmt}"
        try:
            normalize_image(raw, dest, fmt=fmt)
            count += 1
        except Exception as exc:
            console.print(f"[red]Error normalizing {img_file.name}: {exc}[/red]")

    console.print(f"[green]Normalized {count} image(s) → {out}[/green]")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------
@app.command()
def verify(
    input: Path = typer.Option(..., "--input", help="Folder of images to verify."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Verify that images are 750×1050 @ 300 DPI and not corrupted."""
    _setup_logging(verbose)

    if not input.is_dir():
        console.print(f"[red]{input} is not a directory.[/red]")
        raise typer.Exit(1)

    total = 0
    bad = 0
    for img_file in sorted(input.rglob("*")):
        if img_file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        total += 1
        problems = verify_image(img_file)
        if problems:
            bad += 1
            console.print(f"[red]FAIL[/red] {img_file}: {'; '.join(problems)}")
        elif verbose:
            console.print(f"[green]OK[/green]   {img_file}")

    console.print(f"\nChecked {total} image(s): {total - bad} OK, {bad} failed.")
    if bad:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# gui
# ---------------------------------------------------------------------------
@app.command()
def gui() -> None:
    """Launch the graphical user interface."""
    try:
        from ptcg_art_scraper.gui.app import launch
    except ImportError as exc:
        console.print(
            f"[red]GUI dependencies are not installed: {exc}[/red]\n"
            "Install with: pip install ptcg-art-scraper[gui]"
        )
        raise typer.Exit(1) from None
    raise SystemExit(launch())
