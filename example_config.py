#!/usr/bin/env python3
"""
Example configuration file for the Pokémon Card Scraper.

This demonstrates how to customize the scraper's behavior.
"""

from pkmn_card_scraper import PokemonCardScraper
import logging

# Configure more verbose logging if needed
logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG for more detailed output
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_detailed.log'),
        logging.StreamHandler()
    ]
)

# Create scraper with custom settings
scraper = PokemonCardScraper(
    base_url='https://pkmncards.com',
    output_dir='my_cards'  # Custom output directory
)

# Customize scraper settings
scraper.timeout = 60  # Increase timeout to 60 seconds
scraper.retry_count = 5  # Try 5 times before giving up
scraper.delay_between_requests = 2  # 2 second delay between requests

# Run the scraper
# Adjust max_pages based on how many cards you want to download
scraper.run(max_pages=10)  # Download from 10 pages
