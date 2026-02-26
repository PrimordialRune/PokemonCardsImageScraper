# ptcg_art_scraper

A CLI tool that scrapes Pokémon card images (initially from [pkmncards.com](https://pkmncards.com)) and saves them as standardized, print-ready images.

**Default output:** 750 × 1050 px · 300 DPI · 2.5 × 3.5 in

## Installation

```bash
# Clone and install
git clone https://github.com/PrimordialRune/pkmncardsPreviewScraper.git
cd pkmncardsPreviewScraper
pip install -e ".[dev]"
```

## Usage

### `scrape` – Download card images

```bash
# Single card by search query
ptcg_art_scraper scrape --out ./cards --query "Charizard ex 100/197"

# Batch from a file (text/CSV/JSON list of card names or URLs)
ptcg_art_scraper scrape --out ./cards --input cards_to_fetch.csv --concurrency 6 --rate 1.5

# Filter by set
ptcg_art_scraper scrape --out ./cards --query "Pikachu" --set "Obsidian Flames"

# Direct URL
ptcg_art_scraper scrape --out ./cards --query "https://pkmncards.com/card/charizard-ex-obsidian-flames-sv3-125/"
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--out` | *(required)* | Output directory |
| `--provider` | `pkmncards` | Scraping provider |
| `--query` | | Search query |
| `--input` | | Input file (text/CSV/JSON) |
| `--set` | | Set code/name filter |
| `--limit` | `50` | Max cards per query |
| `--concurrency` | `8` | Parallel downloads |
| `--rate` | `2.0` | Requests per second |
| `--retries` | `3` | Retry count per request |
| `--timeout` | `20.0` | Request timeout (seconds) |
| `--resume` | `true` | Skip already-downloaded items |
| `--format` | `png` | Output format (`png` or `jpg`) |
| `--overwrite` | `false` | Overwrite existing files |

### `normalize` – Standardize existing images

```bash
ptcg_art_scraper normalize --input ./raw_images --out ./normalized
ptcg_art_scraper normalize --input ./raw_images --out ./normalized --format jpg
```

### `verify` – Check image compliance

```bash
ptcg_art_scraper verify --input ./normalized
```

Exits non-zero if any image fails (wrong size, missing DPI, corrupt). Useful in CI pipelines.

## Output Structure

```
cards/
  sv3/
    125-197_charizard-ex.png
    125-197_charizard-ex.json    ← sidecar metadata
  base-set/
    25_pikachu.png
    25_pikachu.json
  errors.jsonl                   ← error log (if any failures)
```

Each sidecar JSON contains:

```json
{
  "provider": "pkmncards",
  "source_page_url": "https://pkmncards.com/card/...",
  "source_image_url": "https://pkmncards.com/wp-content/uploads/...",
  "fetched_at_utc": "2025-01-15T12:00:00+00:00",
  "normalized_size": [750, 1050],
  "dpi": 300,
  "original_size": [734, 1024],
  "sha256_original": "abc123...",
  "sha256_normalized": "def456..."
}
```

## Architecture

```
src/ptcg_art_scraper/
├── cli.py                  # Typer CLI (scrape, normalize, verify)
├── models.py               # Data models (CardRef, CardAsset, etc.)
├── providers/
│   ├── base.py             # Abstract provider interface
│   └── pkmncards.py        # pkmncards.com implementation
├── image/
│   └── normalize.py        # 750×1050 @ 300 DPI pipeline
├── storage/
│   ├── layout.py           # Output path naming conventions
│   └── metadata.py         # Sidecar JSON read/write
├── net/
│   └── http.py             # Async HTTP client, rate limiting, retries
└── utils/
    └── slugify.py          # Filesystem-safe slug generation
```

### Adding a new provider

1. Create `src/ptcg_art_scraper/providers/my_provider.py`
2. Implement `BaseProvider` (search → resolve → fetch_image)
3. Register it in `cli.py`'s `PROVIDERS` dict

## Development

```bash
pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Type check
mypy src/ --ignore-missing-imports

# Test
pytest tests/ -v
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Requests blocked / 403** | Reduce `--rate` (e.g. `0.5`), check if site has changed layout |
| **Timeouts** | Increase `--timeout`, reduce `--concurrency` |
| **Missing images** | Some cards may lack high-res images; check `errors.jsonl` |
| **Wrong DPI readback** | PNG stores DPI as pixels-per-meter (pHYs); slight rounding (299.999…) is normal |

## Legal / Ethical Note

This tool is provided for **personal, non-commercial use**. Users are responsible for complying with the terms of service and copyright policies of any website they scrape. The default rate limit is conservative (2 req/s). Please be respectful of site resources.

## License

MIT