# Pokémon TCG Card Image Scraper

A batch-first CLI for resolving, downloading, and normalizing Pokémon card images into
**750 × 1050 px** artwork files with **300 DPI** metadata and JSON sidecars.

## Features

- **Layered architecture** with dedicated `core/config`, `core/models`, `core/providers`, and `core/services` packages.
- **Central image resolution service** that applies provider priority, fallback, and trace logging in one place.
- **Standardized providers** for `pokemon_official`, `pokemontcgio_images`, and `pkmncards`.
- **Rich CLI output** with explicit resolution visibility, batch progress, and concise summaries.
- **Deterministic batch workflows** for set-based scraping from flags, TXT, CSV, or JSON input files.
- **Print-ready normalization** with sidecar metadata and output templating.

## Installation

```bash
# From repository root
pip install -e ".[dev]"
```

Dependencies: Python ≥ 3.11, httpx, typer, beautifulsoup4, Pillow, rich.

## CLI usage

### Resolve a single card

```bash
ptcg_art_scraper resolve --set EX6 --number 10
ptcg_art_scraper resolve --set sv4 --number 100 --providers pokemontcgio_images,pkmncards
```

Example output:

```text
[INFO] Resolving EX6 #10
[OK]  Provider: pokemon_official
      URL: https://assets.pokemon.com/...
[OK] Provider: pokemon_official
URL: https://assets.pokemon.com/...
```

### Scrape a batch

```bash
# One set with inline numbers
ptcg_art_scraper scrape --set EX6 --numbers 10,11,12 --out ./cards

# Mixed-set input file
ptcg_art_scraper scrape --input ./cards.json --out ./cards --providers pokemon_official,pokemontcgio_images,pkmncards

# Custom layout template
ptcg_art_scraper scrape \
  --set sv4 \
  --numbers 25,100 \
  --out ./cards \
  --folder-template "{setId}/{rarity}/{number}_{name}.{fmt}"
```

Supported input formats:

- **TXT**: one `SET#NUMBER` or `SET,NUMBER` entry per line, or plain numbers when `--set` is supplied.
- **CSV**: `set`/`set_code` plus `number`/`card_number` columns.
- **JSON**: a list of `"SET#NUMBER"` strings or objects with `set`/`set_code` and `number`/`card_number`.

### Normalize existing images

```bash
ptcg_art_scraper normalize --input ./raw_images --out ./normalized
```

### Verify normalized images

```bash
ptcg_art_scraper verify --input ./normalized
```

Exit code is non-zero if any verification or batch item fails.

## GUI quick start

A graphical interface is still available for users who prefer not to use the terminal.

```bash
pip install -e ".[gui]"
ptcg_art_scraper gui
```

## Provider notes

### `pokemon_official`

Builds official asset URLs directly from the supplied set code and card number.

### `pokemontcgio_images`

Uses the `PokemonTCG/pokemon-tcg-data` layout when local set metadata is available at:

```text
<this-project>/pokemon-tcg-data/
  sets/en.json
  cards/en/*.json
```

### `pkmncards`

Acts as the retrieval-oriented fallback when deterministic providers are insufficient.

## Output structure

```text
cards/
└── sv4/
    ├── 100_charizard-ex.png
    └── 100_charizard-ex.json
```

Each sidecar includes the provider, resolved source URL, timestamps, hashes, and normalized sizing data.

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

```text
src/ptcg_art_scraper/
├── cli.py                    # Compatibility entrypoint to the redesigned CLI
├── core/
│   ├── config/               # Resolver and batch configuration models
│   ├── models/               # Card, batch, and legacy GUI bridge models
│   ├── providers/            # Standardized provider adapters
│   ├── services/             # Resolution, batch scraping, I/O, normalization
│   ├── engine.py             # Legacy GUI bridge
│   └── exceptions.py         # Typed user-safe exceptions
├── ui/
│   └── cli/                  # Typer + rich command surface
├── providers/                # Legacy parser-heavy provider implementations
├── storage/                  # Compatibility wrappers around output services
├── image/                    # Compatibility wrappers around image services
├── gui/                      # Existing graphical interface
└── utils/
    └── slugify.py
```

## Troubleshooting

- **Blocked or slow requests?** Reduce `--rate` (for example `0.5`).
- **Unexpected provider choice?** Use `resolve` first to inspect the resolution chain.
- **Timeouts?** Increase `--timeout`.

## Legal / ethical note

This tool is provided for personal, non-commercial use only. Users are responsible for complying with the terms of service of any website they scrape. Pokémon card images are © The Pokémon Company / Nintendo.

## License

See repository license.
