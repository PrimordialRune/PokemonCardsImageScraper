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
- Extracted artwork: `output/art_only/`
- Logs: `scraper.log`

## What It Does

The script will:
1. Visit pkmncards.com with pagination (`?display=images`)
2. Download card images from 5 pages (configurable)
3. Use OpenCV to detect and crop artwork from each card
4. Save both full cards and artwork separately

## Customization

Edit `pkmn_card_scraper.py` at the bottom:
```python
def main():
    BASE_URL = 'https://pkmncards.com'  # Change if needed
    OUTPUT_DIR = 'output'                # Change output folder
    MAX_PAGES = 5                        # Increase to get more cards
```

Or use `example_config.py` as a template for advanced customization.

## Testing

To verify artwork extraction works correctly:
```bash
python test_artwork_extraction.py
```

This creates a synthetic card and tests the extraction algorithm.

## Troubleshooting

**No images downloaded?**
- Check your internet connection
- Verify the website URL is correct
- Check `scraper.log` for error messages

**Artwork extraction looks wrong?**
- The algorithm is tuned for standard Pokémon card layouts
- Different card formats may need adjustment to the heuristics
- Check the constants in `extract_artwork()` method (lines 178-183)

**Rate limiting or timeouts?**
- Increase `delay_between_requests` in the scraper
- Increase `timeout` value
- Reduce `MAX_PAGES` to scrape fewer pages

## Next Steps

- Adjust `MAX_PAGES` to scrape more/fewer pages
- Modify artwork detection parameters if needed
- Process downloaded images further
- Integrate into your own workflow

For full documentation, see [README.md](README.md).
