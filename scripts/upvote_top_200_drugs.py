#!/usr/bin/env python3
"""
Script to scrape top 200 drugs from PTCB Test Prep and upvote them via API.

This script:
1. Scrapes the top 200 brand and generic drugs from ptcbtestprep.com
2. Searches for each drug using the /drugs/search API endpoint
3. Upvotes each found drug a random number of times (7-12) using the /drugs/vote endpoint

Usage:
    python3 scripts/upvote_top_200_drugs.py [--api-url http://localhost:8000]
"""

import argparse
import json
import random
import re
import sys
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# PTCB Test Prep URL
PTCB_URL = "https://ptcbtestprep.com/top-200-brand-and-generic-drugs/"

# Default API URL (can be overridden with --api-url flag)
DEFAULT_API_URL = "http://localhost:8000"


def get_hardcoded_drug_list():
    """Get the top 200 drugs list (hardcoded from PTCB Test Prep page)."""
    # Format: (brand, generic, drug_class)
    drugs_data = [
        ("Lexapro", "Escitalopram", "SSRI"),
        ("Oxycodone Hydrochloride Immediate Release", "Oxycodone", "Opioid analgesic"),
        ("Prinivil", "Lisinopril", "ACE inhibitor"), ("Qbrelis", "Lisinopril", "ACE inhibitor"), ("Zestril", "Lisinopril", "ACE inhibitor"),
        ("Zocor", "Simvastatin", "Statin"),
        ("Synthroid", "Levothyroxine", "Thyroid hormone"),
        ("Amoxil", "Amoxicillin", "Antibacterial drug"), ("Trimox", "Amoxicillin", "Antibacterial drug"),
        ("Zithromax", "Azithromycin", "Macrolide antibacterial"),
        ("Microzide", "Hydrochlorothiazide", "Thiazide diuretic"), ("Aquazide H", "Hydrochlorothiazide", "Thiazide diuretic"),
        ("Norvasc", "Amlodipine", "Calcium channel blocker"),
        ("Xanax", "Alprazolam", "Benzodiazepine"),
        ("Glucophage", "Metformin", "Oral antidiabetic drug"), ("Fortamet", "Metformin", "Oral antidiabetic drug"),
        ("Lipitor", "Atorvastatin", "Statin"),
        ("Prilosec", "Omeprazole", "Proton-pump inhibitor"),
        ("Cipro", "Ciprofloxacin", "Fluoroquinolone"), ("Proquin", "Ciprofloxacin", "Fluoroquinolone"),
        ("Zofran", "Ondansetron", "Antiemetic drug"),
        ("Clozaril", "Clozapine", "Antipsychotic drug"),
        ("Lasix", "Furosemide", "Loop diuretic"),
        ("Levitra", "Vardenafil", "PDE5 inhibitor"),
        ("Sumycin", "Tetracycline", "Antibacterial drug"), ("Ala-Tet", "Tetracycline", "Antibacterial drug"), ("Brodspec", "Tetracycline", "Antibacterial drug"),
        ("Heparin Sodium", "Heparin", "Anticoagulant drug"),
        ("Valcyte", "Valganciclovir", "Antiviral drug"),
        ("Lamictal", "Lamotrigine", "Anticonvulsant drug"),
        ("Diflucan", "Fluconazole", "Antifungal drug"),
        ("Tenormin", "Atenolol", "Beta-blocker"),
        ("Singulair", "Montelukast", "Leukotriene inhibitor"),
        ("Flonase Nasal Spray", "Fluticasone propionate", "Corticosteroid"),
        ("Ceftin", "Cefuroxime", "Cephalosporin"),
        ("Nizoral Topical", "Ketoconazole", "Antifungal drug"),
        ("Lyrica", "Pregabalin", "Anticonvulsant drug"),
        ("Nexium", "Esomeprazole", "Proton-pump inhibitor"),
        ("Combivent Respimat", "Albuterol", "Beta-2 agonist"), ("Combivent Respimat", "Ipratropium", "Anticholinergic drug"),
        ("Niaspan", "Niacin", "Form of vitamin B3"),
        ("Uroxatral", "Alfuzosin", "Alpha-1 blocker"),
        ("Biaxin", "Clarithromycin", "Macrolide antibacterial"),
        ("Zomig", "Zolmitriptan", "Anti-migraine drug"),
        ("Invokana", "Canagliflozin", "SGLT-2 inhibitor"),
        ("Saxenda", "Liraglutide", "GLP-1 agonist"), ("Victoza", "Liraglutide", "GLP-1 agonist"),
        ("Alimta", "Pemetrexed", "Anticancer drug"),
        ("Lotrimin", "Clotrimazole", "Antifungal drug"), ("FungiCURE Pump Spray", "Clotrimazole", "Antifungal drug"),
        ("Avastin", "Bevacizumab", "Anticancer drug"),
        ("Sovaldi", "Sofosbuvir", "Hepatitis C drug"),
        ("Gilenya", "Fingolimod", "Immunomodulator"),
        ("Epogen", "Epoetin alfa", "Human erythropoietin"),
        ("Seroquel", "Quetiapine", "Antipsychotic drug"),
        ("Amaryl", "Glimepiride", "Antidiabetic medicine"),
        ("Percocet", "Acetaminophen", "Analgesic / antipyretic"), ("Percocet", "Oxycodone", "Opioid"),
        ("SandIMMUNE", "Cyclosporin", "Immunosuppressant"), ("Neoral", "Cyclosporin", "Immunosuppressant"),
        ("Lantus", "Insulin glargine", "Long-acting insulin"),
        ("Cialis", "Tadalafil", "PDE5 inhibitor"),
        ("Endep", "Amitriptyline", "Tricyclic antidepressant"), ("Elavil", "Amitriptyline", "Tricyclic antidepressant"), ("Vanatrip", "Amitriptyline", "Tricyclic antidepressant"),
        ("Lopid", "Gemfibrozil", "Fibrate"),
        ("Orapred", "Prednisolone", "Corticosteroid"),
        ("Advil", "Ibuprofen", "NSAID"),
        ("Aceon", "Perindopril", "ACE inhibitor"),
        ("Desyrel", "Trazodone", "Antidepressant"),
        ("Actos", "Pioglitazone", "Thiazolidinedione"),
        ("Proscar", "Finasteride", "5-alpha reductase inhibitor"),
        ("Inbrija", "Levodopa", "Antiparkinsonian drug"), ("Dopar", "Levodopa", "Antiparkinsonian drug"), ("Larodopa", "Levodopa", "Antiparkinsonian drug"),
        ("Actonel", "Risedronate", "Bisphosphonate"),
        ("Ventolin", "Albuterol", "Beta-2 agonist"), ("ProAir", "Albuterol", "Beta-2 agonist"), ("Proventil", "Albuterol", "Beta-2 agonist"),
        ("Ultram", "Tramadol", "Opiate narcotic"),
        ("Sonata", "Zaleplon", "Z-drug / hypnotic"),
        ("Zebeta", "Bisoprolol", "Beta-blocker"),
        ("Zovirax", "Acyclovir", "Antiviral drug"),
        ("Coumadin", "Warfarin", "Anticoagulant drug"),
        ("Luvox", "Fluvoxamine", "SSRI"),
        ("Plavix", "Clopidogrel", "Antiplatelet drug"),
        ("Vibramycin", "Doxycycline", "Tetracycline antibiotic"), ("Adoxa", "Doxycycline", "Tetracycline antibiotic"),
        ("Hyzaar", "Hydrochlorothiazide", "Thiazide diuretic"), ("Hyzaar", "Losartan", "Angiotensin II blocker"),
        ("Kytril", "Granisetron", "Antiemetic drug"), ("Sancuso", "Granisetron", "Antiemetic drug"),
        ("Restoril", "Temazepam", "Benzodiazepine"),
        ("Prevacid", "Lansoprazole", "Proton-pump inhibitor"),
        ("Augmentin", "Amoxicillin", "Penicillin antibiotic"), ("Augmentin", "Clavulanic acid", "Beta-lactamase inhibitor"),
        ("Mevacor", "Lovastatin", "Statin"), ("Altoprev", "Lovastatin", "Statin"),
    ]
    
    drugs = []
    for entry in drugs_data:
        if len(entry) == 3:
            brand, generic, drug_class = entry
        else:
            brand, generic = entry
            drug_class = None
        
        if brand and generic:
            drugs.append({
                'brand': brand,
                'generic': generic,
                'drug_class': drug_class
            })
    
    return drugs


def extract_drug_names_from_html(html_content: str):
    """Extract drug names from the PTCB Test Prep HTML page."""
    drugs = []
    
    def clean_html(text):
        """Remove HTML tags and clean up text."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Remove HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    # Try multiple patterns to find the table
    # Pattern 1: Look for table rows with <td> elements
    table_patterns = [
        r'<table[^>]*>(.*?)</table>',
        r'<tbody[^>]*>(.*?)</tbody>',
    ]
    
    table_html = None
    for pattern in table_patterns:
        match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
        if match:
            table_html = match.group(1)
            break
    
    if not table_html:
        # Try to find rows directly
        table_html = html_content
    
    # Find all table rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    
    print(f"Found {len(rows)} table rows")
    
    # If no rows found, try a different approach - look for the data directly in the content
    if len(rows) == 0:
        print("No table rows found, trying alternative parsing method...")
        # Look for patterns like "Brand Name | Generic Name" in the content
        # Based on the web search results, entries look like:
        # "Lexapro | Escitalopram | SSRI"
        # "Prinivil* Qbrelis Zestril | Lisinopril | ACE inhibitor"
        
        # Try to find lines that look like drug entries
        lines = html_content.split('\n')
        for line in lines:
            # Look for patterns with pipe separators or table-like structures
            if '|' in line and len(line.split('|')) >= 2:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2:
                    medicine_text = clean_html(parts[0])
                    generic_text = clean_html(parts[1])
                    
                    # Skip headers
                    if medicine_text.lower() in ['medicine', 'brand name', 'brand']:
                        continue
                    if generic_text.lower() in ['active ingredient', 'generic name', 'generic']:
                        continue
                    
                    if medicine_text and generic_text and len(medicine_text) > 2 and len(generic_text) > 2:
                        # Remove asterisks
                        medicine_text = re.sub(r'\*', '', medicine_text)
                        generic_text = re.sub(r'\*', '', generic_text)
                        
                        # Split brands
                        brand_names = [name.strip() for name in re.split(r'[\s,]+', medicine_text) if name.strip() and len(name.strip()) > 2]
                        generic_names = [generic_text.strip()]
                        
                        for brand in brand_names:
                            drugs.append({
                                'brand': brand,
                                'generic': generic_text.strip()
                            })
    
    for row_idx, row_html in enumerate(rows):
        # Extract all table cells
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)
        
        if len(cells) >= 2:
            medicine_cell = cells[0]
            active_ingredient_cell = cells[1]
            drug_class_cell = cells[2] if len(cells) >= 3 else None
            
            medicine_text = clean_html(medicine_cell)
            generic_text = clean_html(active_ingredient_cell)
            drug_class_text = clean_html(drug_class_cell) if drug_class_cell else None
            
            # Skip header rows
            if medicine_text.lower() in ['medicine', 'brand name', 'brand', '']:
                continue
            if generic_text.lower() in ['active ingredient', 'generic name', 'generic', 'active ingredient(s)', '']:
                continue
            if drug_class_text and drug_class_text.lower() in ['drug class', 'class', '']:
                drug_class_text = None
            
            # Skip if either is empty
            if not medicine_text or not generic_text:
                continue
            
            # Remove asterisks and italic markers (discontinued brands)
            medicine_text = re.sub(r'\*', '', medicine_text)
            medicine_text = re.sub(r'<em>|</em>', '', medicine_text)
            generic_text = re.sub(r'\*', '', generic_text)
            
            # Split multiple brands (can be separated by spaces, commas, or newlines)
            # Handle cases like "Prinivil* Qbrelis Zestril" or "Amoxil Trimox*"
            brand_names = []
            # First try splitting by common separators
            for separator in [',', '\n', '  ']:  # comma, newline, double space
                if separator in medicine_text:
                    brand_names.extend([name.strip() for name in medicine_text.split(separator)])
                    break
            else:
                # If no separator, try splitting by single spaces but be smart about it
                # Look for patterns like "Brand1 Brand2 Brand3" where each might be a brand
                parts = medicine_text.split()
                # If we have multiple words, they might be separate brands
                if len(parts) > 1:
                    # Check if any part looks like a brand (starts with capital, reasonable length)
                    for part in parts:
                        if part and len(part) > 2 and part[0].isupper():
                            brand_names.append(part)
                else:
                    brand_names = [medicine_text]
            
            # Clean up brand names
            brand_names = [name.strip() for name in brand_names if name.strip() and len(name.strip()) > 2]
            
            # Split generic names (usually just one, but handle multiple)
            generic_names = []
            for separator in [',', '\n', '  ']:
                if separator in generic_text:
                    generic_names.extend([name.strip() for name in generic_text.split(separator)])
                    break
            else:
                generic_names = [generic_text]
            
            generic_names = [name.strip() for name in generic_names if name.strip() and len(name.strip()) > 2]
            
            # Create entries for each brand-generic combination
            for brand in brand_names:
                for generic in generic_names:
                    if brand and generic:
                        drugs.append({
                            'brand': brand,
                            'generic': generic,
                            'drug_class': drug_class_text
                        })
    
    # Remove duplicates
    seen = set()
    unique_drugs = []
    for drug in drugs:
        key = (drug['brand'].lower().strip(), drug['generic'].lower().strip())
        if key not in seen and key[0] and key[1]:
            seen.add(key)
            unique_drugs.append(drug)
    
    print(f"Extracted {len(unique_drugs)} unique drug entries from page")
    
    # Debug: print first few entries
    if unique_drugs:
        print("Sample entries:")
        for drug in unique_drugs[:5]:
            print(f"  Brand: {drug['brand']}, Generic: {drug['generic']}")
    
    return unique_drugs


def search_drug(api_url: str, query: str):
    """Search for a drug using the API - exact match only."""
    try:
        clean_query = query.strip()
        if len(clean_query) < 2:
            return []
        
        search_url = f"{api_url}/drugs/search?{urlencode({'query': clean_query, 'limit': 10})}"
        req = Request(search_url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get('results', [])
            return results
    except Exception as e:
        return []


def update_drug_info(api_url: str, drug_id: str, updates: dict):
    """Update drug information using the API."""
    try:
        update_url = f"{api_url}/drugs/{drug_id}"
        data = json.dumps(updates).encode('utf-8')
        req = Request(update_url, data=data, method='PUT')
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=30) as response:
            response_data = response.read().decode('utf-8')
            data = json.loads(response_data)
            return data.get('success', False)
    except HTTPError as e:
        error_body = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"    HTTP error updating drug info: {e.code} {e.reason}")
        print(f"    Response: {error_body}")
        return False
    except Exception as e:
        print(f"    Error updating drug info: {str(e)}")
        return False


def upvote_drug(api_url: str, drug_id: str, ip_address: str = None, user_agent: str = None):
    """Upvote a drug using the API."""
    try:
        vote_url = f"{api_url}/drugs/vote?drug_id={drug_id}&vote_type=upvote"
        req = Request(vote_url, method='POST')
        req.add_header('Content-Type', 'application/json')
        if user_agent:
            req.add_header('User-Agent', user_agent)
        if ip_address:
            req.add_header('X-Forwarded-For', ip_address)
        
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('success', False)
    except Exception as e:
        return False


def generate_random_ip():
    """Generate a random IP address for voting simulation."""
    return f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"


def generate_random_user_agent():
    """Generate a random user agent string."""
    browsers = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    return random.choice(browsers)


def test_api_connection(api_url: str):
    """Test if the API is accessible."""
    try:
        test_url = f"{api_url}/status"
        req = Request(test_url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=5) as response:
            return True
    except Exception as e:
        print(f"WARNING: Could not connect to API at {api_url}: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Upvote top 200 drugs from PTCB Test Prep')
    parser.add_argument('--api-url', default=DEFAULT_API_URL, help=f'API base URL (default: {DEFAULT_API_URL})')
    args = parser.parse_args()
    
    api_url = args.api_url.rstrip('/')
    
    print("="*60)
    print("Top 200 Drugs Upvoter")
    print("="*60)
    print(f"API URL: {api_url}")
    print()
    
    # Test API connection
    print("Testing API connection...")
    if not test_api_connection(api_url):
        print("ERROR: Cannot connect to API. Make sure the server is running.")
        return 1
    print("✓ API connection successful\n")
    
    try:
        # Fetch the PTCB page
        print(f"Fetching top 200 drugs from {PTCB_URL}...")
        req = Request(PTCB_URL)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=30) as response:
            html_content = response.read().decode('utf-8')
        
        print("Page fetched successfully, extracting drug names...")
        
        # Try to extract from HTML first
        drugs = extract_drug_names_from_html(html_content)
        
        # If HTML parsing fails, use hardcoded list
        if not drugs or len(drugs) < 50:
            print("HTML parsing yielded few results, using hardcoded drug list...")
            drugs = get_hardcoded_drug_list()
        
        if not drugs:
            print("ERROR: No drugs found. Using fallback hardcoded list...")
            drugs = get_hardcoded_drug_list()
        
        if not drugs:
            print("ERROR: Could not get drug list.")
            return 1
        
        print(f"\nFound {len(drugs)} drug entries to process\n")
        
        # Track statistics
        found_count = 0
        not_found_count = 0
        total_upvotes = 0
        total_failed_upvotes = 0
        processed_drug_ids = set()  # Track which drugs we've already processed
        
        # Process each drug
        for idx, drug in enumerate(drugs, 1):
            brand_name = drug.get('brand')
            generic_name = drug.get('generic')
            
            print(f"[{idx}/{len(drugs)}] Searching for: Brand={brand_name}, Generic={generic_name}")
            
            # Try exact match searches - brand name first, then generic
            search_queries = []
            if brand_name:
                search_queries.append(brand_name)
            if generic_name:
                search_queries.append(generic_name)
            
            drug_id = None
            for query in search_queries:
                if not query or len(query.strip()) < 2:
                    continue
                try:
                    results = search_drug(api_url, query)
                    if results:
                        # Look for exact match in the results
                        query_lower = query.lower().strip()
                        brand_lower = brand_name.lower().strip() if brand_name else ''
                        generic_lower = generic_name.lower().strip() if generic_name else ''
                        
                        for result in results:
                            result_name = result.get('name', '').lower().strip()
                            result_generic = result.get('generic_name', '').lower().strip() if result.get('generic_name') else ''
                            result_brands = [b.lower().strip() for b in result.get('brand_names', [])]
                            
                            # Exact match only
                            if (query_lower == result_name or 
                                query_lower == result_generic or
                                query_lower in result_brands or
                                (brand_lower and brand_lower == result_name) or
                                (brand_lower and brand_lower in result_brands) or
                                (generic_lower and generic_lower == result_name) or
                                (generic_lower and generic_lower == result_generic)):
                                drug_id = result.get('drug_id')
                                if drug_id:
                                    break
                        if drug_id:
                            break
                except Exception as e:
                    # Continue to next query if this one fails
                    continue
            
            if drug_id and drug_id not in processed_drug_ids:
                processed_drug_ids.add(drug_id)
                found_count += 1
                print(f"  ✓ Found drug_id: {drug_id}")
                
                # Update drug class if available
                drug_class = drug.get('drug_class')
                if drug_class:
                    print(f"  Updating drug_class: {drug_class}")
                    if update_drug_info(api_url, drug_id, {'drug_class': drug_class}):
                        print(f"  ✓ Successfully updated drug_class")
                    else:
                        print(f"  ✗ Failed to update drug_class")
                
                # Generate random number of votes (7-12)
                num_votes = random.randint(7, 12)
                print(f"  Upvoting {num_votes} times...")
                
                # Upvote the drug multiple times
                success_count = 0
                failed_count = 0
                
                for i in range(num_votes):
                    ip_address = generate_random_ip()
                    user_agent = generate_random_user_agent()
                    
                    if upvote_drug(api_url, drug_id, ip_address, user_agent):
                        success_count += 1
                    else:
                        failed_count += 1
                    
                    # Small delay
                    import time
                    time.sleep(0.1)
                
                total_upvotes += success_count
                total_failed_upvotes += failed_count
                print(f"  ✓ Upvoted {success_count} times (failed: {failed_count})")
            elif drug_id in processed_drug_ids:
                print(f"  ⊙ Already processed this drug")
            else:
                not_found_count += 1
                print(f"  ✗ Not found in database")
            
            print()
        
        # Print summary
        print("="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Total drugs processed: {len(drugs)}")
        print(f"Found in database: {found_count}")
        print(f"Not found in database: {not_found_count}")
        print(f"Total successful upvotes: {total_upvotes}")
        print(f"Total failed upvotes: {total_failed_upvotes}")
        print("="*60)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\nERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
