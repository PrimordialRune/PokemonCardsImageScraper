#!/usr/bin/env python3
"""
Pokémon Card Scraper with Artwork Extraction

This script downloads Pokémon card images from pkmncards.com and uses OpenCV
to automatically detect and crop the artwork region from each card.

Features:
- Paginated scraping with ?display=images parameter
- Error handling and retry logic
- Deterministic OpenCV-based artwork detection
- Organized folder structure (cards/ and art_only/)
- Comprehensive logging
"""

import os
import re
import time
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import cv2
import numpy as np


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PokemonCardScraper:
    """
    A scraper that downloads Pokémon card images and extracts artwork regions.
    """
    
    def __init__(self, base_url='https://pkmncards.com', output_dir='output', search_params='s=series%3Aex&sort=date&ord=auto', artwork_bottom_ratio=0.56):
        """
        Initialize the scraper.
        
        Args:
            base_url: The base URL of the website
            output_dir: Root directory for output files
            search_params: Query parameters for filtering (e.g., 's=series%3Aex&sort=date&ord=auto')
            artwork_bottom_ratio: Fixed percentage for bottom boundary of artwork (default: 0.56 = 56%)
        """
        self.base_url = base_url
        self.search_params = search_params
        self.output_dir = Path(output_dir)
        self.cards_dir = self.output_dir / 'cards'
        self.art_dir = self.output_dir / 'art_only'
        
        # Artwork extraction parameters
        self.artwork_bottom_ratio = artwork_bottom_ratio  # Fixed percentage for y1
        
        # Create output directories
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        self.art_dir.mkdir(parents=True, exist_ok=True)
        
        # Request settings
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.timeout = 30
        self.retry_count = 3
        self.delay_between_requests = 1  # seconds
        
        # Track downloaded URLs to prevent duplicates
        self.downloaded_urls = set()
        
    def download_image(self, url, filepath):
        """
        Download an image from a URL with retry logic.
        
        Args:
            url: URL of the image to download
            filepath: Local path to save the image
            
        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(self.retry_count):
            try:
                logger.info(f"Downloading {url} (attempt {attempt + 1}/{self.retry_count})")
                response = self.session.get(url, timeout=self.timeout, stream=True)
                response.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"Successfully downloaded to {filepath}")
                return True
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Download attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_count - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Failed to download {url} after {self.retry_count} attempts")
                    
        return False
    
    def scrape_page(self, page_num=1):
        """
        Scrape a single page to find card image URLs.
        
        Args:
            page_num: Page number to scrape
            
        Returns:
            list: List of image URLs found on the page
        """
        try:
            # Construct URL with search parameters and pagination
            # Format: https://pkmncards.com/page/2/?s=...&display=images
            if page_num == 1:
                url = f"{self.base_url}/?{self.search_params}&display=images"
            else:
                url = f"{self.base_url}/page/{page_num}/?{self.search_params}&display=images"
            
            logger.info(f"Scraping page {page_num}: {url}")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all image elements (adjust selectors based on actual site structure)
            # This is a generic approach - may need adjustment for actual site
            image_urls = []
            
            # Look for images in common card display patterns
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if src and ('card' in src.lower() or 'pokemon' in src.lower()):
                    full_url = urljoin(self.base_url, src)
                    # Skip if already downloaded
                    if full_url not in self.downloaded_urls:
                        image_urls.append(full_url)
            
            # Also check for links to card images
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png']):
                    full_url = urljoin(self.base_url, href)
                    # Skip if already downloaded
                    if full_url not in self.downloaded_urls:
                        image_urls.append(full_url)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in image_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            logger.info(f"Found {len(unique_urls)} new images on page {page_num}")
            return unique_urls
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error scraping page {page_num}: {e}")
            return []
    

    
    def extract_artwork(self, image_path, output_path):
        """
        Extract the artwork region from a Pokémon card using OpenCV.
        
        Uses deterministic image processing with fixed percentage-based boundaries
        specific to Pokémon TCG cards.
        
        The detection uses fixed ratios:
        - x0 = 7.5% of width (left boundary)
        - y0 = 6.5% of height (top boundary)
        - x1 = 94.5% of width (right boundary)
        - y1 = configurable percentage (default 56%, set via artwork_bottom_ratio)
        
        Args:
            image_path: Path to the full card image
            output_path: Path to save the cropped artwork (as PNG)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Read the image
            img = cv2.imread(str(image_path))
            if img is None:
                logger.error(f"Failed to read image: {image_path}")
                return False
            
            height, width = img.shape[:2]
            logger.debug(f"Processing image: {width}x{height}")
            
            # Use fixed bounding box ratios for Pokémon card artwork
            # All boundaries are ratio-based for consistency across card sizes
            x0 = int(0.075 * width)   # 7.5% from left
            y0 = int(0.065 * height)  # 6.5% from top
            x1 = int(0.945 * width)   # 94.5% from left (right edge)
            y1 = int(self.artwork_bottom_ratio * height)  # Configurable bottom boundary
            
            # Define crop boundaries
            art_top = y0
            art_left = x0
            art_right = x1
            art_bottom = y1
            
            logger.debug(f"Artwork bounds: x=[{art_left}, {art_right}], y=[{art_top}, {art_bottom}]")
            logger.debug(f"Using bottom ratio: {self.artwork_bottom_ratio:.1%}")
            
            # Crop the artwork region
            artwork = img[art_top:art_bottom, art_left:art_right]
            
            # Ensure output path has .png extension
            output_path = Path(output_path)
            if output_path.suffix.lower() != '.png':
                output_path = output_path.with_suffix('.png')
            
            # Save the cropped artwork as PNG
            cv2.imwrite(str(output_path), artwork)
            logger.info(f"Extracted artwork to {output_path} (size: {artwork.shape[1]}x{artwork.shape[0]})")
            return True
            
        except Exception as e:
            logger.error(f"Error extracting artwork from {image_path}: {e}")
            return False
    
    def process_card(self, image_url, card_index):
        """
        Download a card image and extract its artwork.
        
        Args:
            image_url: URL of the card image
            card_index: Index for naming the file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Generate filename from URL or use index
            parsed_url = urlparse(image_url)
            filename = os.path.basename(parsed_url.path)
            
            # Sanitize filename - collapse multiple underscores
            filename = re.sub(r'[^\w\-\.]+', '_', filename)
            if not filename or len(filename) < 4:
                filename = f"card_{card_index:05d}.jpg"
            
            # Ensure unique filename
            parts = filename.rsplit('.', 1)
            base_name = parts[0]
            extension = parts[1] if len(parts) > 1 else 'jpg'
            filename = f"{base_name}_{card_index:05d}.{extension}"
            
            card_path = self.cards_dir / filename
            
            # For artwork, always use PNG extension
            art_filename = f"{base_name}_{card_index:05d}.png"
            art_path = self.art_dir / art_filename
            
            # Download the card image
            if self.download_image(image_url, card_path):
                # Mark URL as downloaded
                self.downloaded_urls.add(image_url)
                
                # Extract artwork from the card
                self.extract_artwork(card_path, art_path)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error processing card {image_url}: {e}")
            return False
    
    def run(self, max_pages=5):
        """
        Run the scraper for multiple pages.
        
        Args:
            max_pages: Maximum number of pages to scrape
        """
        logger.info(f"Starting scraper for {max_pages} pages")
        logger.info(f"Output directory: {self.output_dir.absolute()}")
        
        total_downloaded = 0
        card_index = 0
        
        for page_num in range(1, max_pages + 1):
            try:
                # Scrape the page for image URLs
                image_urls = self.scrape_page(page_num)
                
                if not image_urls:
                    logger.warning(f"No images found on page {page_num}, stopping")
                    break
                
                # Process each image
                for url in image_urls:
                    if self.process_card(url, card_index):
                        total_downloaded += 1
                    
                    card_index += 1
                    
                    # Delay between requests to be polite
                    time.sleep(self.delay_between_requests)
                
                logger.info(f"Completed page {page_num}: {len(image_urls)} images processed")
                
                # Delay between pages
                time.sleep(self.delay_between_requests * 2)
                
            except KeyboardInterrupt:
                logger.info("Scraping interrupted by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error on page {page_num}: {e}")
                continue
        
        logger.info(f"Scraping complete! Downloaded {total_downloaded} cards")
        logger.info(f"Full cards saved to: {self.cards_dir.absolute()}")
        logger.info(f"Artwork only saved to: {self.art_dir.absolute()}")


def main():
    """
    Main entry point for the scraper.
    """
    # Configuration for EX series cards
    BASE_URL = 'https://pkmncards.com'
    SEARCH_PARAMS = 's=series%3Aex&sort=date&ord=auto'
    OUTPUT_DIR = 'output'
    MAX_PAGES = 50  # EX series has ~1000 cards; adjust based on cards per page (typically 20-30)
    
    # Artwork extraction configuration
    # Adjust this percentage to control where the bottom crop occurs
    # 0.56 = 56% of card height, typically captures full artwork without text
    ARTWORK_BOTTOM_RATIO = 0.56
    
    logger.info("=" * 80)
    logger.info("Pokémon Card Scraper - Ex Series with Artwork Extraction")
    logger.info("=" * 80)
    
    try:
        # Create and run scraper
        scraper = PokemonCardScraper(
            base_url=BASE_URL, 
            output_dir=OUTPUT_DIR,
            search_params=SEARCH_PARAMS,
            artwork_bottom_ratio=ARTWORK_BOTTOM_RATIO
        )
        scraper.run(max_pages=MAX_PAGES)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
