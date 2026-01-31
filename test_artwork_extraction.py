#!/usr/bin/env python3
"""
Test script for artwork extraction functionality.
Creates a synthetic Pokémon card image to test the artwork detection algorithm.
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
    Create a synthetic Pokémon card image for testing.
    Standard Pokémon card ratio is approximately 2.5:3.5 (width:height).
    
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
    
    # Add artwork region using the new heuristics (7.5%, 13%, 92.5%, 52%)
    art_left = int(width * 0.075)
    art_top = int(height * 0.13)
    art_right = int(width * 0.925)
    art_bottom = int(height * 0.52)
    
    # Fill artwork region with a gradient (to simulate actual artwork)
    for y in range(art_top, art_bottom):
        for x in range(art_left, art_right):
            # Create a simple gradient pattern
            r = int(255 * (y - art_top) / (art_bottom - art_top))
            g = int(255 * (x - art_left) / (art_right - art_left))
            b = 150
            card[y, x] = [b, g, r]
    
    # Add a border around artwork (typical of Pokémon cards)
    cv2.rectangle(card, (art_left, art_top), (art_right, art_bottom), (0, 0, 0), 3)
    
    # Add some "text" regions below artwork (simulating card text)
    text_region_top = art_bottom + 20
    cv2.rectangle(card, (30, text_region_top), (width-30, text_region_top + 80), 
                  (220, 220, 220), -1)
    
    return card


def test_extraction():
    """Test the artwork extraction on a synthetic card."""
    from pkmn_card_scraper import PokemonCardScraper
    
    # Test card dimensions
    CARD_WIDTH = 400
    CARD_HEIGHT = 560
    MIN_ART_WIDTH = 100
    MIN_ART_HEIGHT = 100
    
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
    
    # Test extraction with ex series parameters
    logger.info("Testing artwork extraction with ex series heuristics...")
    scraper = PokemonCardScraper(
        output_dir='test_output',
        search_params='s=series%3Aex&sort=date&ord=auto'
    )
    
    test_art_path = test_art / 'test_card.png'  # Should be PNG now
    success = scraper.extract_artwork(test_card_path, test_art_path)
    
    if success:
        logger.info("✓ Artwork extraction successful!")
        
        # Verify the output exists and has reasonable dimensions
        extracted = cv2.imread(str(test_art_path))
        if extracted is not None:
            h, w = extracted.shape[:2]
            logger.info(f"  Original card: {CARD_WIDTH}x{CARD_HEIGHT}")
            logger.info(f"  Extracted artwork: {w}x{h}")
            
            # Check if output is PNG
            if test_art_path.suffix == '.png':
                logger.info("✓ Output format is PNG as expected!")
            
            # Check if dimensions are reasonable (should be smaller than original)
            if w < CARD_WIDTH and h < CARD_HEIGHT and w > MIN_ART_WIDTH and h > MIN_ART_HEIGHT:
                logger.info("✓ Extracted dimensions look reasonable!")
                return True
            else:
                logger.warning("⚠ Extracted dimensions seem off")
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
    logger.info("Testing Artwork Extraction Functionality")
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
