# Pokémon Card Scraper with Artwork Extraction

A Python script that downloads Pokémon card images from pkmncards.com (specifically the **EX series**) and automatically extracts the artwork region using deterministic OpenCV image processing with **dynamic bottom-edge detection**.

## Features

- **EX Series Targeted Scraping**: Downloads cards from the EX series using `s=series%3Aex` parameter
- **Paginated Scraping**: Handles pagination with `?display=images` parameter
- **Dynamic Artwork Extraction**: Uses OpenCV with combined edge detection and color histogram analysis
  - X bounds and top Y are ratio-based (7.5%-92.5% width, 13% from top)
  - **Bottom boundary is detected dynamically** by analyzing the card frame
  - Uses both horizontal edge density (Canny) and color histogram shifts
  - Identifies the precise border between artwork and text box
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
4. **Frame Boundary Detection**: For each card:
   - Applies ratio-based bounds for left, right, and top (7.5%, 92.5%, 13%)
   - **Dynamically detects the bottom boundary** by analyzing the card frame:
     - Scans downward from the artwork region
     - Computes horizontal edge density using Canny edge detection
     - Calculates color histogram for each region
     - Identifies where edge density drops sharply AND color histogram shifts
     - Confirms sustained boundary for ≥10 consecutive rows
   - Saves the cropped artwork region as PNG
5. **Organization**: 
   - Full cards are saved to `output/cards/` (original format)
   - Extracted artwork is saved to `output/art_only/` (PNG format)

### Artwork Detection Algorithm

The script uses a **hybrid deterministic approach** for artwork detection:

1. **Fixed Boundaries** (ratio-based):
   - Left boundary: 7.5% from left edge (x0 = 0.075 * width)
   - Top boundary: 9.5% from top edge (y0 = 0.095 * height)
   - Right boundary: 92.5% from left edge (x1 = 0.925 * width)

2. **Dynamic Bottom Boundary Detection** (frame analysis):
   
   **Phase 1: Edge Density Analysis**
   - Scans downward from ~25% of card height
   - Calculates edge density in 10-pixel windows using Canny(50, 150)
   - Finds peak edge density (typically the artwork bottom border)
   
   **Phase 2: Color Histogram Analysis**
   - Calculates color histogram baseline from artwork region
   - Uses 32 bins per BGR channel (96 bins total)
   - Compares histograms using correlation method
   - Detects significant color shift between artwork and text box
   
   **Combined Detection**
   - Both conditions must be met simultaneously:
     - Edge density < 0.01 (flat region)
     - Histogram similarity < 0.7 (color change)
   - Requires ≥10 consecutive rows meeting both criteria
   - Maximum expansion: +8% of card height (conservative to avoid text)
   
   **Key Parameters:**
   - Edge detector: Canny(50, 150)
   - Edge density window: 10 pixels
   - Histogram window: 15 pixels
   - Histogram bins: 32 per channel
   - Low density threshold: <0.01 (flat region indicator)
   - Histogram similarity threshold: <0.6 (correlation coefficient, strict)
   - Combined flat confirmation: ≥10 consecutive rows
   - Maximum downward expansion: +8% of card height (56% max)

This dual-method approach ensures reliable frame boundary detection by identifying both the physical border (edges) and the content transition (color), making it robust across different card designs and lighting conditions.

## Output Structure

Files are named using structured format: `{set_code}_{number}_{name}.png`

```
output/
├── cards/          # Full card images (PNG format)
│   ├── rs_1_aggron.png
│   ├── rs_2_blaziken.png
│   ├── rs_3_swampert.png
│   └── ...
└── art_only/       # Cropped artwork only (PNG format)
    ├── rs_1_aggron_board.png
    ├── rs_2_blaziken_board.png
    ├── rs_3_swampert_board.png
    └── ...
```

**Naming Convention:**
- Full card: `{set}_{number}_{name}.png` (e.g., `rs_1_aggron.png`)
- Cropped art: `{set}_{number}_{name}_board.png` (e.g., `rs_1_aggron_board.png`)

The script automatically extracts metadata from card filenames and transforms them:
- Input: `aggron-ruby-sapphire-rs-1_00001.jpg`
- Output: `rs_1_aggron.png` + `rs_1_aggron_board.png`

## Logging

The script logs all activities to:
- Console (stdout)
- `scraper.log` file

Log levels:
- INFO: General progress and successful operations
- DEBUG: Detailed edge detection and histogram information
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
- Frame boundary detection adapts to individual card layouts using both edge and color analysis

## License

See repository license.