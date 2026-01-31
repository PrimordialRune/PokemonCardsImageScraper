# Pokémon Card Scraper with Artwork Extraction

A Python script that downloads Pokémon card images from pkmncards.com (specifically the **EX series**) and automatically extracts the artwork region using deterministic OpenCV image processing.

## Features

- **EX Series Targeted Scraping**: Downloads cards from the EX series using `s=series%3Aex` parameter
- **Paginated Scraping**: Handles pagination with `?display=images` parameter
- **Artwork Extraction**: Uses OpenCV with deterministic edge detection and precise bounding box heuristics to crop card artwork
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

### How It Works

1. **Scraping**: The script visits pkmncards.com with EX series filter (`s=series%3Aex&sort=date&ord=auto&display=images`) and extracts card image URLs from each page
2. **Downloading**: Each card image is downloaded with retry logic (3 attempts with exponential backoff)
3. **Deduplication**: URLs are tracked to prevent downloading the same card multiple times
4. **Artwork Detection**: For each card:
   - Applies precise bounding box heuristics (x: 7.5%-92.5%, y: 13%-52%)
   - Uses Canny edge detection to validate and optionally refine the crop area
   - Saves the cropped artwork region as PNG
5. **Organization**: 
   - Full cards are saved to `output/cards/` (original format)
   - Extracted artwork is saved to `output/art_only/` (PNG format)

### Artwork Detection Algorithm

The script uses a deterministic approach for artwork detection:

1. **Precise Bounding Box Heuristic**: Based on standard Pokémon card layout:
   - Left boundary: 7.5% from left edge (x0 = 0.075 * width)
   - Top boundary: 13% from top edge (y0 = 0.13 * height)
   - Right boundary: 92.5% from left edge (x1 = 0.925 * width)
   - Bottom boundary: 52% from top edge (y1 = 0.52 * height)

2. **Edge Detection Enhancement**:
   - Converts to grayscale
   - Applies Gaussian blur to reduce noise
   - Uses Canny edge detection
   - Finds contours in the expected artwork region
   - Optionally expands bounding box based on detected contours (if they indicate a larger artwork area)

## Output Structure

```
output/
├── cards/          # Full card images (original format)
│   ├── card_00000.jpg
│   ├── card_00001.jpg
│   └── ...
└── art_only/       # Cropped artwork only (PNG format)
    ├── card_00000.png
    ├── card_00001.png
    └── ...
```

## Logging

The script logs all activities to:
- Console (stdout)
- `scraper.log` file

Log levels:
- INFO: General progress and successful operations
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

## License

See repository license.