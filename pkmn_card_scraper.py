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
    
    def __init__(self, base_url='https://pkmncards.com', output_dir='output'):
        """
        Initialize the scraper.
        
        Args:
            base_url: The base URL of the website
            output_dir: Root directory for output files
        """
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.cards_dir = self.output_dir / 'cards'
        self.art_dir = self.output_dir / 'art_only'
        
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
            # Construct URL with pagination
            url = f"{self.base_url}/?display=images"
            if page_num > 1:
                url += f"&page={page_num}"
            
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
                    image_urls.append(full_url)
            
            # Also check for links to card images
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png']):
                    full_url = urljoin(self.base_url, href)
                    image_urls.append(full_url)
            
            logger.info(f"Found {len(image_urls)} images on page {page_num}")
            return list(set(image_urls))  # Remove duplicates
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error scraping page {page_num}: {e}")
            return []
    
    def extract_artwork(self, image_path, output_path):
        """
        Extract the artwork region from a Pokémon card using OpenCV.
        
        Uses deterministic image processing with edge detection and
        relative bounding box heuristics specific to Pokémon cards.
        
        Args:
            image_path: Path to the full card image
            output_path: Path to save the cropped artwork
            
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
            
            # Pokémon card artwork is typically in the upper portion of the card
            # Using relative bounding box heuristics based on standard card layout
            # Standard Pokémon card proportions: artwork is roughly in the top 40-60% of card
            
            # Method 1: Use relative positioning (deterministic approach)
            # Artwork typically starts at ~8-12% from top and ~8-12% from sides
            # and extends to ~55-65% height and ~88-92% width
            
            art_top = int(height * 0.10)      # 10% from top
            art_bottom = int(height * 0.60)   # 60% from top
            art_left = int(width * 0.10)      # 10% from left
            art_right = int(width * 0.90)     # 90% from left
            
            # Method 2: Enhance with edge detection for fine-tuning
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Edge detection using Canny
            edges = cv2.Canny(blurred, 50, 150)
            
            # Find contours in the upper region where artwork typically is
            upper_region = edges[art_top:art_bottom, art_left:art_right]
            contours, _ = cv2.findContours(
                upper_region, 
                cv2.RETR_EXTERNAL, 
                cv2.CONTOUR_APPROX_SIMPLE
            )
            
            # If we find significant contours, use them to refine the bounding box
            if contours:
                # Find the largest contour (likely the artwork region)
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)
                
                # Adjust coordinates back to full image space
                x += art_left
                y += art_top
                
                # Apply some padding and sanity checks
                padding = 10
                x = max(art_left, x - padding)
                y = max(art_top, y - padding)
                w = min(art_right - x, w + 2 * padding)
                h = min(art_bottom - y, h + 2 * padding)
                
                # Only use contour-based crop if it's reasonable
                if w > width * 0.3 and h > height * 0.2:
                    art_top = y
                    art_bottom = y + h
                    art_left = x
                    art_right = x + w
            
            # Crop the artwork region
            artwork = img[art_top:art_bottom, art_left:art_right]
            
            # Save the cropped artwork
            cv2.imwrite(str(output_path), artwork)
            logger.info(f"Extracted artwork to {output_path}")
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
            
            # Sanitize filename
            filename = re.sub(r'[^\w\-.]', '_', filename)
            if not filename or len(filename) < 4:
                filename = f"card_{card_index:05d}.jpg"
            
            # Ensure unique filename
            base_name = filename.rsplit('.', 1)[0]
            extension = filename.rsplit('.', 1)[1] if '.' in filename else 'jpg'
            filename = f"{base_name}_{card_index:05d}.{extension}"
            
            card_path = self.cards_dir / filename
            art_path = self.art_dir / filename
            
            # Download the card image
            if self.download_image(image_url, card_path):
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
    # Configuration
    BASE_URL = 'https://pkmncards.com'
    OUTPUT_DIR = 'output'
    MAX_PAGES = 5  # Adjust as needed
    
    logger.info("=" * 80)
    logger.info("Pokémon Card Scraper with Artwork Extraction")
    logger.info("=" * 80)
    
    try:
        # Create and run scraper
        scraper = PokemonCardScraper(base_url=BASE_URL, output_dir=OUTPUT_DIR)
        scraper.run(max_pages=MAX_PAGES)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
