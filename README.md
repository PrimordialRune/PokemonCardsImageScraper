# Pokémon Card Scraper with Artwork Extraction

A Python script that downloads Pokémon card images from pkmncards.com and automatically extracts the artwork region using deterministic OpenCV image processing.

## Features

- **Paginated Scraping**: Downloads card images using pagination with `?display=images` parameter
- **Artwork Extraction**: Uses OpenCV with deterministic edge detection and relative bounding box heuristics to crop card artwork
- **Organized Storage**: Saves full cards to `cards/` folder and extracted artwork to `art_only/` folder
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

Run the scraper with default settings (5 pages):
```bash
python pkmn_card_scraper.py
```

### Configuration

You can modify the following settings in the `main()` function:

- `BASE_URL`: The base URL of the website (default: 'https://pkmncards.com')
- `OUTPUT_DIR`: Root directory for output files (default: 'output')
- `MAX_PAGES`: Number of pages to scrape (default: 5)

### How It Works

1. **Scraping**: The script visits pkmncards.com with `?display=images` parameter and extracts card image URLs from each page
2. **Downloading**: Each card image is downloaded with retry logic (3 attempts with exponential backoff)
3. **Artwork Detection**: For each card:
   - Applies relative bounding box heuristics (artwork is typically in the top 10-60% of the card)
   - Uses Canny edge detection to find contours in the artwork region
   - Refines the crop area based on detected contours
   - Saves the cropped artwork region
4. **Organization**: 
   - Full cards are saved to `output/cards/`
   - Extracted artwork is saved to `output/art_only/`

### Artwork Detection Algorithm

The script uses a deterministic approach for artwork detection:

1. **Relative Positioning**: Based on standard Pokémon card layout, the artwork is typically:
   - Top: 10% from the top of the card
   - Bottom: 60% from the top
   - Left: 10% from the left edge
   - Right: 90% from the left edge

2. **Edge Detection Enhancement**:
   - Converts to grayscale
   - Applies Gaussian blur to reduce noise
   - Uses Canny edge detection
   - Finds contours in the expected artwork region
   - Refines bounding box based on largest contour

## Output Structure

```
output/
├── cards/          # Full card images
│   ├── card_00000.jpg
│   ├── card_00001.jpg
│   └── ...
└── art_only/       # Cropped artwork only
    ├── card_00000.jpg
    ├── card_00001.jpg
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

All errors are logged with detailed information for debugging.

## Dependencies

- `requests`: HTTP library for downloading images
- `beautifulsoup4`: HTML parsing for scraping
- `opencv-python`: Image processing for artwork extraction
- `numpy`: Numerical operations (required by OpenCV)

## Notes

- The script includes a 1-second delay between requests to be respectful to the server
- Failed downloads are retried up to 3 times with exponential backoff
- Image URLs are deduplicated automatically
- The scraper will stop if it encounters a page with no images

## License

See repository license.