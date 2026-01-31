#!/usr/bin/env python3
"""
Example configuration file for the Pokémon Card Scraper.

This demonstrates how to customize the scraper's behavior for EX series cards.
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

# Create scraper with custom settings for EX series
scraper = PokemonCardScraper(
    base_url='https://pkmncards.com',
    output_dir='my_ex_cards',  # Custom output directory
    search_params='s=series%3Aex&sort=date&ord=auto'  # EX series filter
)

# Customize scraper settings
scraper.timeout = 60  # Increase timeout to 60 seconds
scraper.retry_count = 5  # Try 5 times before giving up
scraper.delay_between_requests = 2  # 2 second delay between requests

# Run the scraper
# Adjust max_pages based on how many cards you want to download
# EX series has ~1000 cards, so you may need many pages
scraper.run(max_pages=50)  # Download from 50 pages
