"""Redesigned Typer CLI with structured rich output."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from ptcg_art_scraper.core.config import BatchScrapeConfig, ResolverConfig
from ptcg_art_scraper.core.exceptions import ConfigurationError, InputFormatError, ScraperError
from ptcg_art_scraper.core.models import CardIdentifier
from ptcg_art_scraper.core.providers import DEFAULT_PROVIDER_PRIORITY, provider_names
from ptcg_art_scraper.core.services import (
    BatchScrapeService,
    ImageResolutionService,
    load_cards_from_file,
    normalize_image,
    parse_card_list,
    verify_image,
)

app = typer.Typer(
    name="ptcg_art_scraper",
    help="Resolve, download, and normalize Pokémon card images with provider transparency.",
    no_args_is_help=True,
)
console = Console()
logger = logging.getLogger("ptcg_art_scraper")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _parse_provider_priority(raw: str) -> tuple[str, ...]:
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not names:
        raise typer.BadParameter("At least one provider must be supplied.")
    unknown = [name for name in names if name not in provider_names()]
    if unknown:
        raise typer.BadParameter(f"Unknown provider(s): {', '.join(unknown)}")
    return names


def _collect_cards(
    card_set: str,
    numbers: str | None,
    input_path: Path | None,
) -> list[CardIdentifier]:
    cards: list[CardIdentifier] = []
    if numbers:
        cards.extend(parse_card_list(numbers, default_set=card_set))
    if input_path:
        cards.extend(load_cards_from_file(input_path, default_set=card_set))
    if not cards:
        raise ConfigurationError("Provide --numbers and/or --input.")
    return cards


def _print_attempts(service: ImageResolutionService) -> None:
    for attempt in service.last_attempts:
        if attempt.status == "ok":
            style = "green"
            label = "OK"
        elif attempt.status == "miss":
            style = "yellow"
            label = "TRY"
        else:
            style = "red"
            label = "ERR"
        detail = f" {attempt.detail}" if attempt.detail else ""
        url = f"\n      URL: {attempt.url}" if attempt.url else ""
        console.print(
            f"[{style}][{label}][/{style}] {attempt.provider}{detail}{url}"
        )


@app.command()
def resolve(
    card_set: Annotated[str, typer.Option("--set", help="Card set code, e.g. EX6 or sv4.")],
    number: Annotated[str, typer.Option("--number", help="Card number within the set.")],
    providers: Annotated[
        str,
        typer.Option(
            "--providers",
            help="Comma-separated provider priority.",
        ),
    ] = ",".join(DEFAULT_PROVIDER_PRIORITY),
    timeout: Annotated[float, typer.Option(help="HTTP timeout in seconds.")] = 20.0,
    rate: Annotated[float, typer.Option(help="Maximum provider probe rate per second.")] = 2.0,
    no_verify: Annotated[
        bool,
        typer.Option("--no-verify", help="Skip URL probing and trust the first candidate.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging.")] = False,
) -> None:
    """Resolve a single card image URL and show the provider chain."""
    _setup_logging(verbose)
    console.print(f"[cyan][INFO][/cyan] Resolving {card_set} #{number}")
    service = ImageResolutionService(
        ResolverConfig(
            provider_priority=_parse_provider_priority(providers),
            verify_urls=not no_verify,
            timeout=timeout,
            rate=rate,
        )
    )
    card = CardIdentifier(set_code=card_set, card_number=number)
    resolved = asyncio.run(service.resolve_card(card))
    _print_attempts(service)
    if resolved is None:
        console.print("[red][FAIL][/red] No provider resolved a usable image URL.")
        raise typer.Exit(1)
    console.print(f"[green][OK][/green] Provider: {resolved.provider}")
    console.print(f"URL: {resolved.resolved_url}")


@app.command()
def scrape(
    out: Annotated[Path, typer.Option("--out", help="Output directory for normalized images.")],
    card_set: Annotated[
        str,
        typer.Option("--set", help="Default set code for --numbers and plain-text inputs."),
    ] = "",
    numbers: Annotated[
        str | None,
        typer.Option(
            "--numbers",
            help="Comma-separated card numbers or SET#NUMBER entries.",
        ),
    ] = None,
    input_path: Annotated[
        Path | None,
        typer.Option("--input", help="TXT, CSV, or JSON batch file."),
    ] = None,
    providers: Annotated[
        str,
        typer.Option(
            "--providers",
            help="Comma-separated provider priority.",
        ),
    ] = ",".join(DEFAULT_PROVIDER_PRIORITY),
    format: Annotated[str, typer.Option("--format", help="png or jpg output.")] = "png",
    concurrency: Annotated[int, typer.Option(help="Concurrent downloads.")] = 6,
    rate: Annotated[float, typer.Option(help="Shared provider/download rate.")] = 2.0,
    retries: Annotated[int, typer.Option(help="Download retry count.")] = 3,
    timeout: Annotated[float, typer.Option(help="HTTP timeout in seconds.")] = 20.0,
    overwrite: Annotated[bool, typer.Option(help="Overwrite existing outputs.")] = False,
    folder_template: Annotated[
        str,
        typer.Option(
            "--folder-template",
            help="Optional output template using set/name/number/type tokens.",
        ),
    ] = "",
    no_verify: Annotated[
        bool,
        typer.Option("--no-verify", help="Skip URL probing and trust the first candidate.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging.")] = False,
) -> None:
    """Batch resolve, download, and normalize card images."""
    _setup_logging(verbose)
    normalized_format = format.lower()
    if normalized_format == "jpeg":
        normalized_format = "jpg"
    if normalized_format not in {"png", "jpg"}:
        raise typer.BadParameter("--format must be png or jpg")

    try:
        cards = _collect_cards(card_set, numbers, input_path)
    except InputFormatError as exc:
        console.print(f"[red][FAIL][/red] {exc.user_message}")
        raise typer.Exit(1) from None
    except ScraperError as exc:
        console.print(f"[red][FAIL][/red] {exc.user_message}")
        raise typer.Exit(1) from None

    service = BatchScrapeService(
        BatchScrapeConfig(
            output_dir=out,
            image_format=normalized_format,
            concurrency=concurrency,
            rate=rate,
            timeout=timeout,
            retries=retries,
            overwrite=overwrite,
            folder_template=folder_template,
            provider_priority=_parse_provider_priority(providers),
            verify_urls=not no_verify,
        )
    )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )
    task_id = progress.add_task("Scraping cards", total=len(cards))

    def _on_event(event_name: str, payload: dict[str, str]) -> None:
        if event_name == "item.started":
            console.print(f"[cyan][INFO][/cyan] Resolving {payload['card']}")
        elif event_name == "item.resolved":
            console.print(
                f"[green][OK][/green]  Provider: {payload['provider']}\n"
                f"      URL: {payload['url']}"
            )
        elif event_name == "item.skipped":
            console.print(f"[yellow][SKIP][/yellow] {payload['card']} -> {payload['output_path']}")
            progress.advance(task_id)
        elif event_name == "item.saved":
            console.print(f"[green][SAVE][/green] {payload['card']} -> {payload['output_path']}")
            progress.advance(task_id)
        elif event_name == "item.failed":
            console.print(f"[red][FAIL][/red] {payload['card']}: {payload['error']}")
            progress.advance(task_id)

    with progress:
        summary = asyncio.run(service.run(cards, on_event=_on_event))

    table = Table(title="Batch summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total", str(summary.total))
    table.add_row("Saved", str(summary.succeeded))
    table.add_row("Skipped", str(summary.skipped))
    table.add_row("Failed", str(summary.failed))
    console.print(table)
    if summary.failed:
        raise typer.Exit(1)


@app.command()
def normalize(
    input_path: Annotated[Path, typer.Option("--input", help="Folder of images to normalize.")],
    out: Annotated[Path, typer.Option("--out", help="Output directory for normalized images.")],
    format: Annotated[str, typer.Option("--format", help="png or jpg output.")] = "png",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging.")] = False,
) -> None:
    """Normalize existing images to 750x1050 at 300 DPI."""
    _setup_logging(verbose)
    if not input_path.is_dir():
        console.print(f"[red][FAIL][/red] {input_path} is not a directory.")
        raise typer.Exit(1)
    fmt = "jpg" if format.lower() == "jpeg" else format.lower()
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for image_path in sorted(input_path.iterdir()):
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        normalize_image(image_path.read_bytes(), out / f"{image_path.stem}.{fmt}", fmt=fmt)
        count += 1
    console.print(f"[green][OK][/green] Normalized {count} image(s) -> {out}")


@app.command()
def verify(
    input_path: Annotated[Path, typer.Option("--input", help="Folder of images to verify.")],
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show passing files too.")
    ] = False,
) -> None:
    """Verify normalized image dimensions and DPI metadata."""
    _setup_logging(verbose)
    if not input_path.is_dir():
        console.print(f"[red][FAIL][/red] {input_path} is not a directory.")
        raise typer.Exit(1)
    total = 0
    bad = 0
    for image_path in sorted(input_path.rglob("*")):
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        total += 1
        problems = verify_image(image_path)
        if problems:
            bad += 1
            console.print(f"[red][FAIL][/red] {image_path}: {'; '.join(problems)}")
        elif verbose:
            console.print(f"[green][OK][/green] {image_path}")
    console.print(f"Checked {total} image(s): {total - bad} OK, {bad} failed.")
    if bad:
        raise typer.Exit(1)


@app.command()
def gui() -> None:
    """Launch the graphical interface when GUI dependencies are installed."""
    try:
        from ptcg_art_scraper.gui.app import launch
    except ImportError as exc:
        console.print(
            f"[red][FAIL][/red] GUI dependencies are not installed: {exc}\n"
            "Install with: pip install ptcg-art-scraper[gui]"
        )
        raise typer.Exit(1) from None
    raise SystemExit(launch())
