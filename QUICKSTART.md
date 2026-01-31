# Quick Start Guide

## Getting Started in 3 Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Scraper
```bash
python pkmn_card_scraper.py
```

### 3. Find Your Results
- Full card images: `output/cards/`
- Extracted artwork (PNG): `output/art_only/`
- Logs: `scraper.log`

## What It Does

The script will:
1. Visit pkmncards.com with ex series filter (`s=series%3Aex&sort=date&ord=auto&display=images`)
2. Download card images from up to 50 pages (configurable)
3. Use OpenCV with precise heuristics (7.5%-92.5% width, 13%-52% height) to detect and crop artwork
4. Save full cards and artwork separately
5. Prevent duplicate downloads using URL tracking

## Customization

Edit `pkmn_card_scraper.py` at the bottom:
```python
def main():
    BASE_URL = 'https://pkmncards.com'
    SEARCH_PARAMS = 's=series%3Aex&sort=date&ord=auto'  # Change series filter
    OUTPUT_DIR = 'output'                                # Change output folder
    MAX_PAGES = 50                                       # Adjust page limit
```

Or use `example_config.py` as a template for advanced customization.

## Testing

To verify artwork extraction works correctly:
```bash
python test_artwork_extraction.py
```

This creates a synthetic card and tests the extraction algorithm with the ex series heuristics.

## Artwork Extraction Details

The algorithm uses precise bounding box coordinates:
- **x0 = 7.5%** of width (left boundary)
- **y0 = 13%** of height (top boundary)
- **x1 = 92.5%** of width (right boundary)
- **y1 = 52%** of height (bottom boundary)

These are validated and optionally refined using Canny edge detection.

## Troubleshooting

**No images downloaded?**
- Check your internet connection
- Verify the website URL is correct
- Check `scraper.log` for error messages
- Ensure the search parameters match available series

**Artwork extraction looks wrong?**
- The algorithm is tuned for standard Pokémon TCG card layouts
- Different card formats may need adjustment to the heuristics
- Check the constants in `extract_artwork()` method

**Rate limiting or timeouts?**
- Increase `delay_between_requests` in the scraper
- Increase `timeout` value
- Reduce `MAX_PAGES` to scrape fewer pages

**Duplicates being downloaded?**
- The scraper tracks URLs automatically
- If you restart, previously downloaded URLs are lost
- Consider implementing persistent storage if needed

## Next Steps

- Adjust `MAX_PAGES` to scrape more/fewer pages
- Change `SEARCH_PARAMS` to target different series
- Modify artwork detection parameters if needed
- Process downloaded images further
- Integrate into your own workflow

For full documentation, see [README.md](README.md).
