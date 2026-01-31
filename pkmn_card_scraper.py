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
    
    def __init__(self, base_url='https://pkmncards.com', output_dir='output', search_params='s=series%3Aex&sort=date&ord=auto'):
        """
        Initialize the scraper.
        
        Args:
            base_url: The base URL of the website
            output_dir: Root directory for output files
            search_params: Query parameters for filtering (e.g., 's=series%3Aex&sort=date&ord=auto')
        """
        self.base_url = base_url
        self.search_params = search_params
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
            url = f"{self.base_url}/?{self.search_params}&display=images"
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
        
        Uses deterministic image processing with edge detection and
        relative bounding box heuristics specific to Pokémon cards.
        
        The heuristic uses:
        - x0 = 7.5% of width (left boundary)
        - y0 = 13% of height (top boundary)
        - x1 = 92.5% of width (right boundary)
        - y1 = 52% of height (bottom boundary)
        
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
            
            # Use precise bounding box heuristics for Pokémon card artwork
            # Based on standard card layout where artwork occupies a fixed region
            x0 = int(0.075 * width)   # 7.5% from left
            y0 = int(0.13 * height)   # 13% from top
            x1 = int(0.925 * width)   # 92.5% from left (right edge)
            y1 = int(0.52 * height)   # 52% from top (bottom edge)
            
            # Initial crop using deterministic heuristic
            art_top = y0
            art_bottom = y1
            art_left = x0
            art_right = x1
            
            # Optional: Validate using edge detection and expand if necessary
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Edge detection using Canny
            edges = cv2.Canny(blurred, 50, 150)
            
            # Check the crop region for significant edges
            crop_region = edges[art_top:art_bottom, art_left:art_right]
            
            # Find contours in the crop region
            # Note: Requires OpenCV >= 4.0 which returns (contours, hierarchy)
            contours, _ = cv2.findContours(
                crop_region, 
                cv2.RETR_EXTERNAL, 
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            # If we find significant contours, we can optionally refine the bounding box
            if contours:
                # Find the largest contour (likely the artwork region)
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)
                
                # Adjust coordinates back to full image space
                x += art_left
                y += art_top
                
                # Only expand the region if the contour suggests a larger area
                # This helps capture artwork that may extend slightly beyond the heuristic
                # Use 80% threshold to ensure we only expand for significant contours
                # that likely represent the actual artwork boundary
                if w > (art_right - art_left) * 0.8 and h > (art_bottom - art_top) * 0.8:
                    # Add minimal padding
                    padding = 5
                    art_left = max(x0, x - padding)
                    art_top = max(y0, y - padding)
                    art_right = min(x1, x + w + padding)
                    art_bottom = min(y1, y + h + padding)
            
            # Crop the artwork region
            artwork = img[art_top:art_bottom, art_left:art_right]
            
            # Ensure output path has .png extension
            output_path = Path(output_path)
            if output_path.suffix.lower() != '.png':
                output_path = output_path.with_suffix('.png')
            
            # Save the cropped artwork as PNG
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
    
    logger.info("=" * 80)
    logger.info("Pokémon Card Scraper - Ex Series with Artwork Extraction")
    logger.info("=" * 80)
    
    try:
        # Create and run scraper
        scraper = PokemonCardScraper(
            base_url=BASE_URL, 
            output_dir=OUTPUT_DIR,
            search_params=SEARCH_PARAMS
        )
        scraper.run(max_pages=MAX_PAGES)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
