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
1. Visit pkmncards.com with EX series filter (`s=series%3Aex&sort=date&ord=auto&display=images`)
2. Download card images from up to 50 pages (configurable)
3. Use OpenCV with **combined frame boundary detection** to extract artwork:
   - Fixed bounds: 7.5%-92.5% width, 13% from top
   - **Dynamic bottom**: Analyzes both edge density and color histograms
   - Identifies the border between artwork and text box
   - Captures full holo backgrounds typical of EX-era cards
4. Save full cards and artwork separately
5. Prevent duplicate downloads using URL tracking

## Customization

Edit `pkmn_card_scraper.py` at the bottom:
```python
def main():
    BASE_URL = 'https://pkmncards.com'
    SEARCH_PARAMS = 's=series%3Aex&sort=date&ord=auto'  # Change series filter
    OUTPUT_DIR = 'output'                                # Change output folder
    MAX_PAGES = 50                                       # Adjust page limit (EX series ~1000 cards)
```

Or use `example_config.py` as a template for advanced customization.

## Testing

To verify artwork extraction works correctly:
```bash
python test_artwork_extraction.py
```

This creates a synthetic card and tests the combined edge density + histogram detection algorithm.

## Artwork Extraction Details

The algorithm uses **combined frame boundary detection**:

**Fixed Boundaries:**
- **x0 = 7.5%** of width (left boundary)
- **y0 = 9.5%** of height (top boundary)
- **x1 = 92.5%** of width (right boundary)

**Dynamic Bottom Boundary:**
Uses two methods simultaneously to identify the card frame:

1. **Edge Density Analysis**
   - Scans downward from ~25% of card height
   - Calculates edge density using Canny(50, 150) in 10-pixel windows
   - Finds peak edge density (artwork border)
   - Checks for sustained low edge density (<0.01)

2. **Color Histogram Analysis**
   - Calculates color histograms (32 bins per BGR channel)
   - Compares baseline (artwork) with current region
   - Detects color shift between artwork and text box
   - Uses correlation coefficient (<0.7 = significant change)

**Combined Detection:**
- Both conditions must be met for ≥10 consecutive rows:
  - Edge density drops sharply (flat region)
  - Color histogram shifts significantly (content change)
- Maximum expansion: +12% of card height

**Example on 400x560 card:**
- Old fixed approach: 340x219 pixels (bottom at 52% = 291px)
- New dynamic approach: 340x249 pixels (bottom at 57% = 321px)
- **Captures 30 more pixels** with more reliable boundary detection

## Troubleshooting

**No images downloaded?**
- Check your internet connection
- Verify the website URL is correct
- Check `scraper.log` for error messages
- Ensure the search parameters match available series

**Artwork extraction looks wrong?**
- The algorithm is tuned for standard Pokémon TCG EX-era card layouts
- Different card formats may need adjustment to the parameters
- Check debug logs for edge density information
- The dynamic detection adapts to each card's layout

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
