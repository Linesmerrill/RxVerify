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
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rxlist_database import get_rxlist_database
from app.models import Source

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RxListScraper:
    def __init__(self):
        self.base_url = "https://www.rxlist.com"
        self.session = None
        self.scraped_drugs = set()
        self.drug_data = []
        
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
            'slideshows/', 'images/', 'quizzes/'
        ]
        
        for pattern in skip_patterns:
            if pattern in href.lower():
                return False
        
        # Skip very short or common words
        if len(text) < 3 or text.lower() in ['a', 'an', 'the', 'and', 'or', 'but']:
            return False
        
        # Skip navigation elements
        nav_words = ['home', 'about', 'contact', 'privacy', 'terms', 'advertising']
        if text.lower() in nav_words:
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
                'drug class', 'medication class', 'therapeutic class',
                'pharmacological class', 'class:', 'type:'
            ]
            
            text_content = soup.get_text().lower()
            for pattern in class_patterns:
                if pattern in text_content:
                    # Try to extract the class information
                    class_info = self.extract_after_pattern(text_content, pattern)
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
    
    async def scrape_all_drugs(self) -> List[Dict]:
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
        
        # Scrape individual drug pages (all drugs)
        scraped_drugs = []
        for i, drug_link in enumerate(all_drug_links):  # Process all drugs
            drug_data = await self.scrape_drug_page(drug_link)
            if drug_data:
                scraped_drugs.append(drug_data)
            
            # Progress update
            if (i + 1) % 50 == 0:
                logger.info(f"Scraped {i + 1}/{len(all_drug_links)} drugs")
            
            # Small delay to be respectful (reduced for faster processing)
            await asyncio.sleep(0.1)
        
        logger.info(f"Successfully scraped {len(scraped_drugs)} drugs")
        return scraped_drugs

async def main():
    """Main function to run the scraper"""
    logger.info("Starting RxList drug scraper...")
    
    # Clear existing database
    db = get_rxlist_database()
    db.clear_database()
    logger.info("Cleared existing database")
    
    async with RxListScraper() as scraper:
        # Scrape all drugs
        scraped_drugs = await scraper.scrape_all_drugs()
        
        # Add drugs to database
        logger.info(f"Adding {len(scraped_drugs)} drugs to database...")
        for drug in scraped_drugs:
            try:
                db.add_drug(
                    name=drug['name'],
                    generic_name=drug.get('generic_name'),
                    brand_names=drug.get('brand_names', []),
                    drug_class=drug.get('drug_class'),
                    common_uses=drug.get('common_uses', []),
                    description=drug.get('description'),
                    search_terms=drug.get('search_terms', [])
                )
            except Exception as e:
                logger.error(f"Error adding drug {drug.get('name', 'unknown')}: {str(e)}")
        
        # Get final stats
        stats = db.get_drug_stats()
        logger.info(f"Database populated with {stats['total_drugs']} drugs")
        
        # Save scraped data to JSON for backup
        with open('scraped_drugs.json', 'w') as f:
            json.dump(scraped_drugs, f, indent=2)
        logger.info("Saved scraped data to scraped_drugs.json")

if __name__ == "__main__":
    asyncio.run(main())
