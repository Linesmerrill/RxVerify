#!/usr/bin/env python3
"""
RxList Drug Scraper
Scrapes all drug information from RxList A-Z pages and populates the database
"""

import asyncio
import aiohttp
import re
import time
import json
import logging
import sys
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import os
from asyncio import Lock

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rxlist_database import get_rxlist_database
from app.models import Source

class ProgressBar:
    """Simple progress bar for terminal output"""
    
    def __init__(self, total: int, width: int = 50):
        self.total = total
        self.width = width
        self.current = 0
        self.start_time = time.time()
    
    def update(self, current: int, inserted: int = 0, skipped: int = 0):
        """Update progress bar with current progress"""
        self.current = current
        percentage = (current / self.total) * 100
        
        # Calculate progress bar
        filled = int((current / self.total) * self.width)
        bar = '█' * filled + '░' * (self.width - filled)
        
        # Calculate elapsed time and ETA
        elapsed = time.time() - self.start_time
        if current > 0:
            eta = (elapsed / current) * (self.total - current)
            eta_str = f"ETA: {int(eta//60)}m {int(eta%60)}s"
        else:
            eta_str = "ETA: --:--"
        
        # Format the progress bar
        progress_str = f"\r[{bar}] {current}/{self.total} ({percentage:.1f}%) | Inserted: {inserted} | Skipped: {skipped} | {eta_str}"
        
        # Write to stdout and flush
        sys.stdout.write(progress_str)
        sys.stdout.flush()
    
    def finish(self, inserted: int, skipped: int):
        """Finish the progress bar"""
        elapsed = time.time() - self.start_time
        print(f"\n✅ Completed! Inserted: {inserted} | Skipped: {skipped} | Time: {int(elapsed//60)}m {int(elapsed%60)}s")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RxListScraper:
    def __init__(self, max_concurrent: int = 10):
        self.base_url = "https://www.rxlist.com"
        self.session = None
        self.scraped_drugs = set()
        self.drug_data = []
        self.max_concurrent = max_concurrent  # Maximum concurrent operations
        self.db_lock = Lock()  # Mutex for database operations
        self.stats_lock = Lock()  # Mutex for statistics updates
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def get_alphabet_urls(self) -> List[str]:
        """Get all A-Z page URLs from RxList"""
        alphabet_urls = []
        
        # Generate A-Z URLs
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            url = f"{self.base_url}/drugs/alpha_{letter.lower()}.htm"
            alphabet_urls.append(url)
            
        return alphabet_urls
    
    async def scrape_alphabet_page(self, url: str) -> List[Dict]:
        """Scrape a single A-Z page for drug links"""
        try:
            logger.info(f"Scraping alphabet page: {url}")
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {url}: {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find drug links - they typically have specific patterns
                drug_links = []
                
                # Look for links that point to drug pages
                links = soup.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    # Skip empty or very short text
                    if not text or len(text) < 2:
                        continue
                    
                    # Check if it's a drug page link
                    if self.is_drug_link(href, text):
                        full_url = urljoin(self.base_url, href)
                        drug_links.append({
                            'name': text,
                            'url': full_url
                        })
                
                logger.info(f"Found {len(drug_links)} drug links on {url}")
                return drug_links
                
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return []
    
    def is_drug_link(self, href: str, text: str) -> bool:
        """Determine if a link is likely a drug page"""
        # Skip certain patterns
        skip_patterns = [
            'javascript:', 'mailto:', '#', 'tel:',
            'drugs/alpha_', 'drugs/', 'tools/', 'dictionary/',
            'slideshows/', 'images/', 'quizzes/', 'generic_drugs/',
            'drug_classification/', 'drugs_comparison/', 'supplements/',
            'drug-interaction-checker', 'pill-identification', 'drug-medical-dictionary',
            'drug-slideshows', 'image_gallery', 'quizzes_a-z', 'about_us',
            'contact_us', 'terms_and_conditions', 'privacy_policy', 'advertising'
        ]
        
        for pattern in skip_patterns:
            if pattern in href.lower():
                return False
        
        # Skip very short or common words
        if len(text) < 3 or text.lower() in ['a', 'an', 'the', 'and', 'or', 'but']:
            return False
        
        # Skip navigation elements
        nav_words = ['home', 'about', 'contact', 'privacy', 'terms', 'advertising', 'drugs a-z']
        if text.lower() in nav_words:
            return False
        
        # Skip single letter links (A, B, C, etc.)
        if len(text) == 1 and text.isalpha():
            return False
        
        # Look for drug-like patterns in the URL
        drug_patterns = [
            '/drugs/', '/medications/', '/prescription/',
            'drug', 'medication', 'prescription'
        ]
        
        for pattern in drug_patterns:
            if pattern in href.lower():
                return True
        
        # If it's a relative link and has reasonable text, consider it
        if href.startswith('/') and len(text) > 3 and not any(char.isdigit() for char in text[:3]):
            return True
            
        return False
    
    async def scrape_drug_page(self, drug_info: Dict) -> Optional[Dict]:
        """Scrape individual drug page for detailed information"""
        try:
            url = drug_info['url']
            name = drug_info['name']
            
            # Skip if already scraped
            if url in self.scraped_drugs:
                return None
            
            self.scraped_drugs.add(url)
            
            logger.info(f"Scraping drug page: {name}")
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {url}: {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract drug information
                drug_data = self.extract_drug_data(soup, name, url)
                
                if drug_data:
                    logger.info(f"Extracted data for: {name}")
                    return drug_data
                else:
                    logger.warning(f"No data extracted for: {name}")
                    return None
                
        except Exception as e:
            logger.error(f"Error scraping drug page {drug_info.get('name', 'unknown')}: {str(e)}")
            return None
    
    def extract_drug_data(self, soup: BeautifulSoup, name: str, url: str) -> Optional[Dict]:
        """Extract drug information from a drug page"""
        try:
            # Initialize drug data
            drug_data = {
                'name': name,
                'generic_name': None,
                'brand_names': [],
                'drug_class': None,
                'common_uses': [],
                'description': None,
                'search_terms': [name.lower()]
            }
            
            # Extract generic name (often in the title or first paragraph)
            title = soup.find('title')
            if title:
                title_text = title.get_text().strip()
                # Look for patterns like "Generic Name (Brand Name)"
                if '(' in title_text and ')' in title_text:
                    parts = title_text.split('(')
                    if len(parts) >= 2:
                        generic = parts[0].strip()
                        brand_part = parts[1].split(')')[0].strip()
                        drug_data['generic_name'] = generic
                        drug_data['brand_names'].append(brand_part)
            
            # Look for drug class information
            class_patterns = [
                'drug class:', 'medication class:', 'therapeutic class:',
                'pharmacological class:', 'class:', 'type:'
            ]
            
            text_content = soup.get_text().lower()
            for pattern in class_patterns:
                if pattern in text_content:
                    # Try to extract the class information
                    class_info = self.extract_after_pattern(text_content, pattern)
                    if class_info:
                        # Clean up the extracted class info
                        class_info = class_info.strip()
                        # Remove leading colons, commas, and extra whitespace
                        while class_info.startswith((':', ',', ' ')):
                            class_info = class_info[1:].strip()
                        # Remove trailing colons and commas
                        while class_info.endswith((':', ',')):
                            class_info = class_info[:-1].strip()
                        if class_info:
                            drug_data['drug_class'] = class_info.title()
                            break
            
            # Look for common uses/indications
            use_patterns = [
                'uses', 'indications', 'what is', 'treats', 'used for',
                'purpose', 'benefits', 'conditions'
            ]
            
            for pattern in use_patterns:
                if pattern in text_content:
                    uses = self.extract_uses_from_text(text_content, pattern)
                    if uses:
                        drug_data['common_uses'] = uses
                        break
            
            # Extract description from first paragraph
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 50 and any(word in text.lower() for word in ['drug', 'medication', 'treatment', 'prescription']):
                    drug_data['description'] = text[:500]  # Limit description length
                    break
            
            # Add brand names to search terms
            for brand in drug_data['brand_names']:
                if brand.lower() not in drug_data['search_terms']:
                    drug_data['search_terms'].append(brand.lower())
            
            # Add generic name to search terms
            if drug_data['generic_name'] and drug_data['generic_name'].lower() not in drug_data['search_terms']:
                drug_data['search_terms'].append(drug_data['generic_name'].lower())
            
            # Ensure we have at least some useful data
            if drug_data['name'] and (drug_data['generic_name'] or drug_data['brand_names'] or drug_data['common_uses']):
                return drug_data
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error extracting drug data for {name}: {str(e)}")
            return None
    
    def extract_after_pattern(self, text: str, pattern: str) -> Optional[str]:
        """Extract text after a pattern"""
        try:
            index = text.find(pattern)
            if index != -1:
                after_pattern = text[index + len(pattern):].strip()
                # Take the first sentence or up to 100 characters
                sentence_end = min(after_pattern.find('.'), after_pattern.find('\n'), 100)
                if sentence_end > 0:
                    return after_pattern[:sentence_end].strip()
                return after_pattern[:100].strip()
        except:
            pass
        return None
    
    def extract_uses_from_text(self, text: str, pattern: str) -> List[str]:
        """Extract common uses from text"""
        try:
            uses = []
            index = text.find(pattern)
            if index != -1:
                after_pattern = text[index + len(pattern):].strip()
                # Look for common medical conditions
                common_conditions = [
                    'pain', 'inflammation', 'fever', 'infection', 'bacterial',
                    'viral', 'fungal', 'allergy', 'asthma', 'copd', 'diabetes',
                    'hypertension', 'high blood pressure', 'cholesterol',
                    'depression', 'anxiety', 'seizures', 'epilepsy', 'migraine',
                    'arthritis', 'ulcer', 'gerd', 'acid reflux', 'nausea',
                    'vomiting', 'diarrhea', 'constipation', 'insomnia', 'sleep'
                ]
                
                for condition in common_conditions:
                    if condition in after_pattern:
                        uses.append(condition.title())
                
                # Limit to 5 uses
                return uses[:5]
        except:
            pass
        return []

    async def process_single_drug(self, drug_link: Dict, progress_bar: ProgressBar, stats: Dict) -> bool:
        """Process a single drug with thread-safe database operations"""
        try:
            # Skip if already scraped (idempotent)
            if drug_link['url'] in self.scraped_drugs:
                async with self.stats_lock:
                    stats['skipped'] += 1
                return False
                
            drug_data = await self.scrape_drug_page(drug_link)
            if drug_data:
                # Thread-safe database insertion
                async with self.db_lock:
                    db = get_rxlist_database()
                    success = db.add_drug(
                        name=drug_data['name'],
                        generic_name=drug_data.get('generic_name'),
                        brand_names=drug_data.get('brand_names', []),
                        drug_class=drug_data.get('drug_class'),
                        common_uses=drug_data.get('common_uses', []),
                        description=drug_data.get('description'),
                        search_terms=drug_data.get('search_terms', [])
                    )
                    
                    if success:
                        async with self.stats_lock:
                            stats['inserted'] += 1
                        logger.info(f"Added drug to RxList database: {drug_data['name']}")
                        return True
                    else:
                        async with self.stats_lock:
                            stats['skipped'] += 1
                        return False
            else:
                async with self.stats_lock:
                    stats['skipped'] += 1
                return False
                
        except Exception as e:
            logger.error(f"Error processing drug {drug_link.get('name', 'unknown')}: {str(e)}")
            async with self.stats_lock:
                stats['skipped'] += 1
            return False
    
    async def scrape_all_drugs(self) -> int:
        """Scrape all drugs from RxList"""
        logger.info("Starting comprehensive RxList scraping...")
        
        # Get all alphabet page URLs
        alphabet_urls = self.get_alphabet_urls()
        logger.info(f"Found {len(alphabet_urls)} alphabet pages to scrape")
        
        all_drug_links = []
        
        # Scrape all alphabet pages
        for url in alphabet_urls:
            drug_links = await self.scrape_alphabet_page(url)
            all_drug_links.extend(drug_links)
            
            # Small delay to be respectful
            await asyncio.sleep(1)
        
        logger.info(f"Total drug links found: {len(all_drug_links)}")
        
        # Initialize progress bar and statistics
        progress_bar = ProgressBar(len(all_drug_links))
        print(f"\n🚀 Starting to scrape {len(all_drug_links)} drugs with {self.max_concurrent} parallel workers...")
        
        # Shared statistics dictionary
        stats = {'inserted': 0, 'skipped': 0, 'processed': 0}
        
        # Create semaphore to limit concurrent operations
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def process_drug_with_semaphore(drug_link: Dict, index: int):
            """Process a single drug with semaphore limiting"""
            async with semaphore:
                success = await self.process_single_drug(drug_link, progress_bar, stats)
                stats['processed'] = index + 1
                
                # Update progress bar (thread-safe)
                async with self.stats_lock:
                    progress_bar.update(stats['processed'], stats['inserted'], stats['skipped'])
                
                # Small delay to be respectful
                await asyncio.sleep(0.05)
                return success
        
        # Create tasks for parallel processing
        tasks = [
            process_drug_with_semaphore(drug_link, i) 
            for i, drug_link in enumerate(all_drug_links)
        ]
        
        # Process all drugs in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful results
        scraped_count = sum(1 for result in results if result is True)
        skipped_count = stats['skipped']
        
        # Finish progress bar
        progress_bar.finish(scraped_count, skipped_count)
        logger.info(f"Successfully scraped and inserted {scraped_count} drugs, skipped {skipped_count} already processed")
        return scraped_count

async def main():
    """Main function to run the scraper"""
    logger.info("Starting RxList drug scraper...")
    
    # Get database instance (don't clear - make it idempotent)
    db = get_rxlist_database()
    stats = db.get_drug_stats()
    logger.info(f"Starting with {stats['total_drugs']} existing drugs in database")
    
    async with RxListScraper(max_concurrent=15) as scraper:
        # Scrape all drugs and insert immediately
        scraped_count = await scraper.scrape_all_drugs()
        
        # Get final stats
        stats = db.get_drug_stats()
        logger.info(f"Database populated with {stats['total_drugs']} drugs")

if __name__ == "__main__":
    asyncio.run(main())
