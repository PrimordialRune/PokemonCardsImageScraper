# Pokémon Card Scraper with Artwork Extraction

A Python script that downloads Pokémon card images from pkmncards.com (specifically the **EX series**) and automatically extracts the artwork region using deterministic OpenCV image processing with **fixed percentage-based boundaries**.

## Features

- **EX Series Targeted Scraping**: Downloads cards from the EX series using `s=series%3Aex` parameter
- **Paginated Scraping**: Handles pagination with `?display=images` parameter
- **Simple Artwork Extraction**: Uses OpenCV with fixed ratio-based boundaries
  - All boundaries are percentage-based for consistency across card sizes
  - Top: 6.5%, Bottom: 56% (configurable), Left: 7.5%, Right: 94.5%
  - Easy to adjust via `artwork_bottom_ratio` parameter
- **Organized Storage**: Saves full cards to `cards/` folder and extracted artwork (PNG) to `art_only/` folder
- **Deduplication**: Tracks downloaded URLs to prevent duplicate downloads
- **Error Handling**: Comprehensive error handling with retry logic for network requests
- **Logging**: Detailed logging to both console and file (`scraper.log`)
- **Rate Limiting**: Built-in delays between requests to be respectful to the server

## Installation

1. Clone the repository:
```bash
git clone https://github.com/PrimordialRune/pkmncardsPreviewScraper.git
cd pkmncardsPreviewScraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the scraper with default settings (EX series, 50 pages):
```bash
python pkmn_card_scraper.py
```

### Configuration

You can modify the following settings in the `main()` function:

- `BASE_URL`: The base URL of the website (default: 'https://pkmncards.com')
- `SEARCH_PARAMS`: Query parameters for filtering (default: 's=series%3Aex&sort=date&ord=auto')
- `OUTPUT_DIR`: Root directory for output files (default: 'output')
- `MAX_PAGES`: Number of pages to scrape (default: 50 for EX series)
- `ARTWORK_BOTTOM_RATIO`: Percentage for bottom crop boundary (default: 0.56 = 56%)

### Custom Artwork Boundary

You can easily adjust the bottom boundary percentage to match your needs:

```python
# More conservative (crops higher, excludes more)
scraper = PokemonCardScraper(artwork_bottom_ratio=0.50)

# Default (recommended for most EX cards)
scraper = PokemonCardScraper(artwork_bottom_ratio=0.56)

# More liberal (includes more, may include text)
scraper = PokemonCardScraper(artwork_bottom_ratio=0.60)
```

### How It Works

1. **Scraping**: The script visits pkmncards.com with EX series filter (`s=series%3Aex&sort=date&ord=auto&display=images`) and extracts card image URLs from each page
2. **Downloading**: Each card image is downloaded with retry logic (3 attempts with exponential backoff)
3. **Deduplication**: URLs are tracked to prevent downloading the same card multiple times
4. **Artwork Extraction**: For each card:
   - Applies fixed percentage-based boundaries to all edges
   - Left: 7.5%, Top: 6.5%, Right: 94.5%, Bottom: configurable (default 56%)
   - Crops the artwork region and saves as PNG
5. **Organization**: 
   - Full cards are saved to `output/cards/` (original format)
   - Extracted artwork is saved to `output/art_only/` (PNG format)

### Artwork Detection Algorithm

The script uses **fixed percentage-based boundaries** for artwork extraction:

- **Left boundary**: 7.5% from left edge (x0 = 0.075 * width)
- **Top boundary**: 6.5% from top edge (y0 = 0.065 * height)
- **Right boundary**: 94.5% from left edge (x1 = 0.945 * width)
- **Bottom boundary**: Configurable percentage (default: y1 = 0.56 * height)

This provides consistent results across all card sizes while allowing easy customization via the `artwork_bottom_ratio` parameter.

**Why Fixed Ratios?**
- Simple and predictable
- Fast (no image processing overhead)
- Easy to adjust for different card layouts
- Consistent results every time

## Output Structure

Files are named using the original filename from the website plus an index:

```
output/
├── cards/          # Full card images (original format)
│   ├── aggron-ruby-sapphire-rs-1_00001.jpg
│   ├── blaziken-ruby-sapphire-rs-2_00002.jpg
│   └── ...
└── art_only/       # Cropped artwork only (PNG format)
    ├── aggron-ruby-sapphire-rs-1_00001.png
    ├── blaziken-ruby-sapphire-rs-2_00002.png
    └── ...
```

**Naming Convention:**
- Full card: `{original-filename}_{index}.jpg`
- Cropped art: `{original-filename}_{index}.png`

## Logging

The script logs all activities to:
- Console (stdout)
- `scraper.log` file

Log levels:
- INFO: General progress and successful operations
- DEBUG: Detailed extraction information
- WARNING: Recoverable errors (e.g., failed download attempts)
- ERROR: Unrecoverable errors (e.g., failed after all retries)

## Error Handling

The script includes comprehensive error handling for:
- Network timeouts and connection errors
- Invalid or corrupted images
- Image processing failures
- File system errors
- Duplicate URL prevention

All errors are logged with detailed information for debugging.

## Dependencies

- `requests`: HTTP library for downloading images
- `beautifulsoup4`: HTML parsing for scraping
- `opencv-python`: Image processing for artwork extraction
- `numpy`: Numerical operations (required by OpenCV)

## Notes

- The script includes a 1-second delay between requests to be respectful to the server
- Failed downloads are retried up to 3 times with exponential backoff
- Image URLs are deduplicated automatically using a tracking set
- The scraper will stop if it encounters a page with no images
- Artwork is always saved as PNG format for quality preservation
- Adjust `artwork_bottom_ratio` parameter (0.50-0.60) to fine-tune the bottom crop boundary

## License

See repository license.