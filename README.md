# Pokémon TCG Card Image Scraper

A CLI tool that scrapes Pokémon card images (from [pkmncards.com](https://pkmncards.com) and other providers) and produces **standardised, print-ready** images:

* **750 × 1050 px** (2.5 × 3.5 in at 300 DPI)
* Embedded 300 DPI metadata
* Sidecar JSON with provenance, hashes, and sizing data

## Features

* **Provider architecture** – pluggable providers (`pkmncards` today; add more later).
* **Image normalization** – cover-fit → centre-crop → Lanczos resampling → DPI embed.
* **Batch processing** – async downloads, bounded concurrency, token-bucket rate limiting.
* **Retries with exponential back-off** on 429 / 5xx / timeouts.
* **Resume support** – skip already-downloaded images by checking output + sidecar JSON.
* **Verify command** – audit an output folder for size / DPI / corruption issues.
* **Structured output** – `{set_slug}/{number}_{name_slug}.png` + `.json` sidecar.

## Installation

```bash
# From repository root
pip install -e ".[dev]"
```

Dependencies: Python ≥ 3.11, httpx, typer, beautifulsoup4, Pillow, rich.

## Usage

### Scrape cards

```bash
# Single card search
ptcg_art_scraper scrape --out ./cards --query "Charizard ex 100/197"

# From a text/CSV/JSON list
ptcg_art_scraper scrape --out ./cards --input cards_to_fetch.csv --concurrency 6 --rate 1.5

# Limit results
ptcg_art_scraper scrape --out ./cards --query "Pikachu" --limit 5
```

### Normalize existing images

```bash
ptcg_art_scraper normalize --input ./raw_images --out ./normalized
```

### Verify output

```bash
ptcg_art_scraper verify --input ./normalized
```

Exit code is non-zero if any image fails (useful in CI).

## GUI Quick Start

A graphical interface is available for users who prefer not to use the terminal.

### Install

```bash
pip install -e ".[gui]"
```

### Launch

```bash
# Via CLI subcommand
ptcg_art_scraper gui

# Or directly
ptcg_art_scraper_gui
```

### Workflow

1. **New Job** – Select a source (search query, import file, or paste URLs), choose an output folder and format, then click **Build Queue**.
2. **Queue & Progress** – Watch per-card status (resolving → fetching → normalizing → saved), pause/resume, cancel, or retry failed items.
3. **Library** – Browse downloaded card images, view metadata from sidecar JSON files, and open images or folders.
4. **Settings** – Configure default output folder, provider, format, concurrency, rate limit, retries, and timeout.
5. **Help / About** – Quick-start guide, troubleshooting tips, legal note, and a **Copy Diagnostics** button for bug reports.

### Packaging (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --name "PTCG Art Scraper" \
    --windowed \
    --onefile \
    src/ptcg_art_scraper/gui/app.py
```

The resulting executable will be in `dist/`.

### Key options (`scrape`)

| Option | Default | Description |
|---|---|---|
| `--provider` | `pkmncards` | Image provider |
| `--out` | *(required)* | Output directory |
| `--query` | | Search query |
| `--input` | | File with card identifiers/URLs |
| `--set` | | Set code/name filter |
| `--limit` | 0 (all) | Max cards |
| `--concurrency` | 8 | Parallel downloads |
| `--rate` | 2.0 | Requests / second |
| `--retries` | 3 | Retry count |
| `--timeout` | 20 s | HTTP timeout |
| `--resume` / `--no-resume` | resume | Skip existing |
| `--format` | png | `png` or `jpg` |
| `--overwrite` | false | Re-download existing |

## Output structure

```
cards/
├── sv4/
│   ├── 100_charizard-ex.png
│   ├── 100_charizard-ex.json
│   ├── 25_pikachu.png
│   └── 25_pikachu.json
└── errors.jsonl          # only if failures occurred
```

Each `.json` sidecar contains:

```json
{
  "provider": "pkmncards",
  "source_page_url": "https://pkmncards.com/card/…",
  "source_image_url": "https://…/image.png",
  "fetched_at_utc": "2025-01-01T00:00:00+00:00",
  "normalized_size": [750, 1050],
  "dpi": 300,
  "original_size": [800, 1120],
  "sha256_original": "abc…",
  "sha256_normalized": "def…"
}
```

## Development

```bash
pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Type check
mypy src/ptcg_art_scraper/

# Tests (skip network tests)
pytest -m "not network" -v
```

## Project structure

```
src/ptcg_art_scraper/
├── cli.py                 # Typer CLI (scrape / normalize / verify / gui)
├── models.py              # CardRef, CardAsset, FetchedImage, etc.
├── core/
│   ├── models.py          # JobConfig, QueueItem, JobEvent (shared)
│   └── engine.py          # ScrapeEngine with event callbacks
├── gui/
│   ├── app.py             # MainWindow + sidebar navigation
│   ├── new_job.py         # New Job wizard page
│   ├── queue_view.py      # Queue & Progress page
│   ├── library_view.py    # Library browser page
│   ├── settings_view.py   # Settings page
│   └── help_view.py       # Help / About page
├── providers/
│   ├── base.py            # Abstract provider interface
│   └── pkmncards.py       # pkmncards.com provider
├── image/
│   └── normalize.py       # 750×1050 @ 300 DPI pipeline
├── storage/
│   ├── layout.py          # Output path / naming rules
│   └── metadata.py        # Sidecar JSON persistence
├── net/
│   └── http.py            # Async HTTP client, retry, rate limiting
└── utils/
    └── slugify.py         # Filesystem-safe slug generation
tests/
├── test_cli.py            # CLI smoke tests
├── test_core_models.py    # Job/event model tests
├── test_normalize.py      # Image pipeline + DPI golden tests
├── test_provider_pkmncards.py  # HTML parsing with fixtures
└── test_slugify_paths.py  # Slug + output path rules
```

## Troubleshooting

* **Blocked requests?** – Reduce `--rate` (e.g. `0.5`). The default (2 req/s) is conservative.
* **HTML layout changed?** – Provider parsing may need updating; file an issue.
* **Timeouts?** – Increase `--timeout` (e.g. `60`).

## Legal / ethical note

This tool is provided for personal, non-commercial use only. Users are responsible for complying with the terms of service of any website they scrape. Pokémon card images are © The Pokémon Company / Nintendo.

## Legacy scraper

The original `pkmn_card_scraper.py` (EX-series CV-based artwork extractor) is still available in the repository for reference.

## License

See repository license.