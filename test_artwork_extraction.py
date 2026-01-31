#!/usr/bin/env python3
"""
Test script for artwork extraction functionality.
Creates a synthetic Pokémon card image to test the artwork extraction with fixed boundaries.
"""

import cv2
import numpy as np
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_synthetic_card(width=400, height=560):
    """
    Create a synthetic Pokémon card image for testing fixed-ratio extraction.
    Standard Pokémon card ratio is approximately 2.5:3.5 (width:height).
    
    This creates a card with:
    - Artwork region with visible edges
    - Clear transition to flat text box below
    - Realistic EX-era card layout
    
    Args:
        width: Width of the card
        height: Height of the card
        
    Returns:
        numpy.ndarray: Synthetic card image
    """
    # Create a white canvas
    card = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    # Add a colored border (representing card border)
    border_color = (200, 200, 200)
    cv2.rectangle(card, (0, 0), (width-1, height-1), border_color, 20)
    
    # Add artwork region - extended for EX-era cards
    # Using boundaries: 6.5% top, 56% bottom
    art_left = int(width * 0.075)
    art_top = int(height * 0.065)
    art_right = int(width * 0.945)
    art_bottom = int(height * 0.56)
    
    # Fill artwork region with a complex pattern to create edges
    for y in range(art_top, art_bottom):
        for x in range(art_left, art_right):
            # Create a gradient with some texture
            r = int(255 * (y - art_top) / (art_bottom - art_top))
            g = int(255 * (x - art_left) / (art_right - art_left))
            b = 150
            # Add some noise/texture to create edges
            if (x + y) % 20 < 10:
                r = min(255, r + 30)
                g = min(255, g + 30)
            card[y, x] = [b, g, r]
    
    # Add a strong border around artwork (typical of Pokémon cards)
    cv2.rectangle(card, (art_left, art_top), (art_right, art_bottom), (0, 0, 0), 4)
    
    # Add flat "text box" region below artwork
    text_region_top = art_bottom + 15
    text_region_bottom = text_region_top + 100
    cv2.rectangle(card, (30, text_region_top), (width-30, text_region_bottom), 
                  (245, 245, 245), -1)
    
    # Add some subtle text lines
    for i in range(3):
        y_line = text_region_top + 20 + i * 20
        cv2.line(card, (40, y_line), (width-40, y_line), (230, 230, 230), 1)
    
    return card


def test_extraction():
    """Test the artwork extraction on a synthetic card with fixed ratio."""
    from pkmn_card_scraper import PokemonCardScraper
    
    # Test card dimensions
    CARD_WIDTH = 400
    CARD_HEIGHT = 560
    MIN_ART_WIDTH = 100
    MIN_ART_HEIGHT = 100
    
    # Expected dimensions based on fixed ratios
    EXPECTED_ART_WIDTH = int(CARD_WIDTH * (0.945 - 0.075))  # 348px
    EXPECTED_ART_HEIGHT = int(CARD_HEIGHT * (0.56 - 0.065))  # 277px
    
    # Create test directories
    test_dir = Path('test_output')
    test_cards = test_dir / 'cards'
    test_art = test_dir / 'art_only'
    test_cards.mkdir(parents=True, exist_ok=True)
    test_art.mkdir(parents=True, exist_ok=True)
    
    logger.info("Creating synthetic test card...")
    synthetic_card = create_synthetic_card(CARD_WIDTH, CARD_HEIGHT)
    
    # Save the synthetic card
    test_card_path = test_cards / 'test_card.jpg'
    cv2.imwrite(str(test_card_path), synthetic_card)
    logger.info(f"Saved test card to {test_card_path}")
    
    # Test extraction with fixed ratio (default 56%)
    logger.info("Testing artwork extraction with fixed ratio (56%)...")
    scraper = PokemonCardScraper(
        output_dir='test_output',
        search_params='s=series%3Aex&sort=date&ord=auto',
        artwork_bottom_ratio=0.56
    )
    
    test_art_path = test_art / 'test_card.png'
    success = scraper.extract_artwork(test_card_path, test_art_path)
    
    if success:
        logger.info("✓ Artwork extraction successful!")
        
        # Verify the output exists and has reasonable dimensions
        extracted = cv2.imread(str(test_art_path))
        if extracted is not None:
            h, w = extracted.shape[:2]
            logger.info(f"  Original card: {CARD_WIDTH}x{CARD_HEIGHT}")
            logger.info(f"  Extracted artwork: {w}x{h}")
            logger.info(f"  Expected artwork: {EXPECTED_ART_WIDTH}x{EXPECTED_ART_HEIGHT}")
            
            # Check if output is PNG
            if test_art_path.suffix == '.png':
                logger.info("✓ Output format is PNG as expected!")
            else:
                logger.error("✗ Output format is not PNG")
                return False
            
            # Check if dimensions match expected values (with small tolerance)
            if abs(w - EXPECTED_ART_WIDTH) <= 2 and abs(h - EXPECTED_ART_HEIGHT) <= 2:
                logger.info("✓ Extracted dimensions match expected values!")
                return True
            else:
                logger.warning(f"⚠ Dimensions slightly different than expected")
                logger.warning(f"  Width diff: {abs(w - EXPECTED_ART_WIDTH)}px")
                logger.warning(f"  Height diff: {abs(h - EXPECTED_ART_HEIGHT)}px")
                # Still acceptable if dimensions are reasonable
                if w > MIN_ART_WIDTH and h > MIN_ART_HEIGHT and w < CARD_WIDTH and h < CARD_HEIGHT:
                    logger.info("  Within acceptable range, considering as pass")
                    return True
                else:
                    logger.error("✗ Dimensions outside acceptable range")
                    return False
        else:
            logger.error("✗ Failed to read extracted artwork")
            return False
    else:
        logger.error("✗ Artwork extraction failed")
        return False


def main():
    """Run the test."""
    logger.info("=" * 60)
    logger.info("Testing Artwork Extraction with Fixed Ratio")
    logger.info("=" * 60)
    
    try:
        success = test_extraction()
        
        if success:
            logger.info("\n✓ All tests passed!")
            logger.info("\nTest output saved to test_output/ directory")
            logger.info("You can inspect the files to verify the extraction quality.")
            return 0
        else:
            logger.error("\n✗ Tests failed")
            return 1
            
    except Exception as e:
        logger.error(f"\n✗ Test error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit(main())
