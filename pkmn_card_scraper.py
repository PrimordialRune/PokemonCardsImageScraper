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
    
    def detect_bottom_edge(self, gray_img, color_img, x0, x1, y_start, max_y):
        """
        Detect the bottom edge of artwork by analyzing the card frame boundary.
        
        Uses a combination of:
        - Horizontal edge density (Canny edge detection)
        - Color histogram shift between artwork and uniform text box
        
        The artwork region ends where both:
        1. Edge density drops sharply for ≥10 consecutive rows
        2. Color histogram similarity falls below threshold
        
        Args:
            gray_img: Grayscale image for edge detection
            color_img: Full color image for histogram analysis
            x0: Left boundary of artwork region
            x1: Right boundary of artwork region
            y_start: Starting Y position to scan from
            max_y: Maximum Y position (limit of downward expansion)
            
        Returns:
            int: Detected bottom Y coordinate
        """
        height, width = gray_img.shape[:2]
        
        # ===== EDGE DETECTION PARAMETERS =====
        # Gaussian blur kernel size for noise reduction
        BLUR_KERNEL = (5, 5)
        
        # Canny edge detection thresholds
        CANNY_LOW = 50   # Lower threshold for edge detection
        CANNY_HIGH = 150  # Upper threshold for edge detection
        
        # Edge density window size (pixels)
        EDGE_WINDOW = 10  # Window size for calculating edge density
        
        # Edge density thresholds
        LOW_DENSITY_THRESHOLD = 0.01  # Threshold for "flat" region (very low edges)
        MIN_PEAK_DENSITY = 0.05  # Minimum density to consider a valid peak
        PEAK_UPDATE_THRESHOLD = 0.5  # Threshold (50%) for updating peak density
        MODERATE_DENSITY_MULTIPLIER = 2  # Multiplier for moderate density check
        
        # Consecutive flat rows required for confirmation
        FLAT_ROWS_REQUIRED = 10  # Number of consecutive flat rows to confirm boundary
        
        # ===== COLOR HISTOGRAM PARAMETERS =====
        # Histogram bins per channel (more bins = more sensitive to color changes)
        HISTOGRAM_BINS = 32  # Number of bins per color channel
        
        # Histogram comparison window size
        HISTOGRAM_WINDOW = 15  # Height of region for histogram comparison
        
        # Histogram similarity threshold (0-1, lower = more different)
        # Using correlation: 1.0 = identical, 0.0 = uncorrelated, -1.0 = opposite
        HISTOGRAM_SIMILARITY_THRESHOLD = 0.7  # Below this = significant color change
        
        # Combined detection parameters
        # Both edge density AND histogram conditions must be met
        COMBINED_FLAT_ROWS = 10  # Rows where both conditions are true
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray_img, BLUR_KERNEL, 0)
        
        # Edge detection using Canny
        edges = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)
        
        def calculate_edge_density(y_pos):
            """Calculate horizontal edge density in a window of rows."""
            if y_pos + EDGE_WINDOW > height:
                return 0.0
            
            # Extract the region
            region = edges[y_pos:y_pos + EDGE_WINDOW, x0:x1]
            
            # Count non-zero pixels (edges)
            edge_pixels = np.count_nonzero(region)
            total_pixels = region.size
            
            if total_pixels == 0:
                return 0.0
            
            return edge_pixels / total_pixels
        
        def calculate_color_histogram(y_pos):
            """
            Calculate color histogram for a region.
            
            Returns normalized histogram for BGR channels combined.
            """
            if y_pos + HISTOGRAM_WINDOW > height:
                return None
            
            # Extract color region
            region = color_img[y_pos:y_pos + HISTOGRAM_WINDOW, x0:x1]
            
            # Calculate histogram for each channel
            histograms = []
            for channel in range(3):  # BGR channels
                hist = cv2.calcHist([region], [channel], None, [HISTOGRAM_BINS], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()
                histograms.append(hist)
            
            # Combine histograms from all channels
            combined_hist = np.concatenate(histograms)
            
            return combined_hist
        
        def compare_histograms(hist1, hist2):
            """
            Compare two histograms using correlation method.
            
            Returns:
                float: Correlation coefficient (1.0 = identical, 0.0 = uncorrelated)
            """
            if hist1 is None or hist2 is None:
                return 1.0  # Assume similar if can't compare
            
            # Use correlation method (range: -1 to 1, where 1 = perfect match)
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            
            return similarity
        
        # ===== PHASE 1: Find peak edge density (artwork border) =====
        max_density = 0.0
        peak_y = y_start
        
        # Scan to find peak
        scan_range = min(max_y - y_start, int(height * 0.25))
        for y in range(y_start, y_start + scan_range):
            density = calculate_edge_density(y)
            if density > max_density:
                max_density = density
                peak_y = y
        
        logger.debug(f"Peak edge density: {max_density:.4f} at y={peak_y}")
        
        # If no significant peak found, use default
        if max_density < MIN_PEAK_DENSITY:
            logger.debug("No significant peak found, using max_y")
            return max_y
        
        # ===== PHASE 2: Combined detection using edge density + histogram =====
        # Calculate baseline histogram from artwork region (before peak)
        baseline_y = max(y_start, peak_y - 30)  # Sample from artwork region
        baseline_histogram = calculate_color_histogram(baseline_y)
        
        y_current = peak_y + EDGE_WINDOW
        combined_flat_count = 0
        detected_y = max_y  # Default to max if not detected
        
        # Scan downward looking for combined conditions
        while y_current < max_y:
            current_density = calculate_edge_density(y_current)
            current_histogram = calculate_color_histogram(y_current)
            
            # Check edge density condition
            edge_is_flat = current_density < LOW_DENSITY_THRESHOLD
            
            # Check histogram condition
            histogram_similarity = compare_histograms(baseline_histogram, current_histogram)
            histogram_is_different = histogram_similarity < HISTOGRAM_SIMILARITY_THRESHOLD
            
            # Both conditions must be met
            if edge_is_flat and histogram_is_different:
                combined_flat_count += 1
                
                # Found sustained region meeting both criteria
                if combined_flat_count >= COMBINED_FLAT_ROWS:
                    detected_y = peak_y + EDGE_WINDOW // 2
                    logger.debug(f"Frame boundary detected at y={detected_y}")
                    logger.debug(f"  Edge density: {current_density:.4f} (< {LOW_DENSITY_THRESHOLD})")
                    logger.debug(f"  Histogram similarity: {histogram_similarity:.4f} (< {HISTOGRAM_SIMILARITY_THRESHOLD})")
                    break
            else:
                # Reset counter if conditions not met
                # Update peak if we find higher edge density
                if current_density > max_density * PEAK_UPDATE_THRESHOLD:
                    peak_y = y_current
                    max_density = current_density
                    combined_flat_count = 0
                    # Update baseline from new peak
                    baseline_y = max(y_start, peak_y - 30)
                    baseline_histogram = calculate_color_histogram(baseline_y)
                elif current_density > LOW_DENSITY_THRESHOLD * MODERATE_DENSITY_MULTIPLIER:
                    # Reset for moderate density
                    combined_flat_count = 0
            
            y_current += 1
        
        # Ensure we don't go beyond max_y
        detected_y = min(detected_y, max_y)
        
        return detected_y
    
    def extract_artwork(self, image_path, output_path):
        """
        Extract the artwork region from a Pokémon card using OpenCV.
        
        Uses deterministic image processing with dynamic frame boundary detection
        for the bottom edge, specific to Pokémon TCG cards.
        
        The detection uses:
        - x0 = 7.5% of width (left boundary, ratio-based)
        - y0 = 9.5% of height (top boundary, ratio-based)
        - x1 = 92.5% of width (right boundary, ratio-based)
        - y1 = dynamically detected (bottom boundary)
        
        Dynamic bottom detection scans downward analyzing:
        1. Horizontal edge density (Canny edge detection)
        2. Color histogram shifts between artwork and text box
        
        The frame boundary is identified where both:
        - Edge density drops sharply for ≥10 consecutive rows
        - Color histogram similarity falls below threshold
        
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
            # X bounds and top Y bound are ratio-based
            x0 = int(0.075 * width)   # 7.5% from left
            y0 = int(0.095 * height)  # 9.5% from top (adjusted to capture top of artwork)
            x1 = int(0.925 * width)   # 92.5% from left (right edge)
            
            # Initial crop using deterministic heuristic for top and sides
            art_top = y0
            art_left = x0
            art_right = x1
            
            # Convert to grayscale for edge detection
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Dynamically detect bottom boundary using both edge density and color histogram
            # Start scanning from a reasonable position in the artwork
            y_start = int(0.25 * height)  # Start scanning from 25% down (earlier to catch artwork properly)
            
            # Maximum downward expansion: +12% of card height from initial y0
            max_y_expansion = int(0.12 * height)
            max_y = min(int(0.48 * height) + max_y_expansion, height - 10)  # Adjusted to stop before text box
            
            # Detect the bottom edge using combined edge density + histogram analysis
            art_bottom = self.detect_bottom_edge(gray, img, x0, x1, y_start, max_y)
            
            logger.debug(f"Detected artwork bounds: x=[{art_left}, {art_right}], y=[{art_top}, {art_bottom}]")
            
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
