"""Download & normalize RxNorm releases (RRF files)."""
import pathlib
import gzip
import urllib.request
import csv
import asyncio
from typing import List, Dict, Optional
from etl.common import upsert_doc

DATA_DIR = pathlib.Path("data/rxnorm")
RXNORM_BASE_URL = "https://download.nlm.nih.gov/rxnorm/RxNorm_full/rrf/"
LATEST_RELEASE_URL = "https://download.nlm.nih.gov/rxnorm/RxNorm_full/rrf/RxNorm_full_01012024_pgd.zip"

def download_rxnorm_release():
    """Download the latest RxNorm release."""
    print("📥 Downloading RxNorm release...")
    
    # Create data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download the release
    zip_path = DATA_DIR / "rxnorm_latest.zip"
    urllib.request.urlretrieve(LATEST_RELEASE_URL, zip_path)
    
    # Extract (you'll need to implement zip extraction)
    print(f"✅ Downloaded to {zip_path}")
    return zip_path

def parse_rxnsat_rrf(file_path: pathlib.Path) -> List[Dict]:
    """Parse RXNSAT.RRF for drug attributes and descriptions."""
    records = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='|')
        for row in reader:
            if len(row) >= 7:
                rxcui = row[0]
                lat = row[1]  # Language
                ts = row[2]   # Term status
                lui = row[3]  # Lexical unique identifier
                lui_ts = row[4]  # LUI term status
                lui_norm = row[5]  # LUI normalized
                string = row[6]  # String
                
                if lat == "ENG" and ts == "P":  # English, Preferred term
                    records.append({
                        "rxcui": rxcui,
                        "attribute": "description",
                        "value": string,
                        "source": "rxnorm"
                    })
    
    return records

def parse_rxnconso_rrf(file_path: pathlib.Path) -> List[Dict]:
    """Parse RXNCONSO.RRF for drug names and synonyms."""
    records = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='|')
        for row in reader:
            if len(row) >= 16:
                rxcui = row[0]
                lat = row[1]  # Language
                ts = row[2]   # Term status
                lui = row[3]  # Lexical unique identifier
                lui_ts = row[4]  # LUI term status
                lui_norm = row[5]  # LUI normalized
                string = row[6]  # String
                sdu = row[7]  # Source of drug name
                sab = row[8]  # Source abbreviation
                tty = row[9]  # Term type
                code = row[10]  # Source code
                string_in = row[11]  # String input
                string_out = row[12]  # String output
                string_clean = row[13]  # Clean string
                string_clean_ts = row[14]  # Clean string term status
                string_clean_lui = row[15]  # Clean string LUI
                
                # Focus on drug names and synonyms
                if lat == "ENG" and sab == "RXNORM":
                    records.append({
                        "rxcui": rxcui,
                        "name": string,
                        "term_type": tty,
                        "source": "rxnorm",
                        "source_code": code
                    })
    
    return records

async def run():
    """Main ETL function for RxNorm."""
    print("🏥 Starting RxNorm ETL...")
    
    # For now, we'll work with sample data since downloading requires large files
    # In production, you'd call download_rxnorm_release() here
    
    # Create sample RxNorm data for demonstration
    sample_rxnorm_data = [
        {
            "rxcui": "197361",
            "name": "atorvastatin 10 MG Oral Tablet",
            "term_type": "BN",
            "source": "rxnorm",
            "source_code": "197361"
        },
        {
            "rxcui": "197361",
            "name": "Lipitor 10 MG Oral Tablet",
            "term_type": "BN",
            "source": "rxnorm", 
            "source_code": "197361"
        },
        {
            "rxcui": "197361",
            "name": "atorvastatin calcium 10 MG Oral Tablet",
            "term_type": "BN",
            "source": "rxnorm",
            "source_code": "197361"
        },
        {
            "rxcui": "197361",
            "name": "atorvastatin",
            "term_type": "IN",
            "source": "rxnorm",
            "source_code": "197361"
        }
    ]
    
    print(f"📝 Processing {len(sample_rxnorm_data)} RxNorm records...")
    
    # Process each record
    for record in sample_rxnorm_data:
        # Create text content for the document
        text_content = f"RxNorm Drug: {record['name']} (RxCUI: {record['rxcui']}, Type: {record['term_type']})"
        
        # Store in ChromaDB
        await upsert_doc(
            rxcui=record["rxcui"],
            source="rxnorm",
            id=f"rxnorm_{record['source_code']}_{record['term_type']}",
            url=f"https://rxnav.nlm.nih.gov/REST/rxcui/{record['rxcui']}",
            title=record["name"],
            text=text_content
        )
    
    print("✅ RxNorm ETL completed!")
    return len(sample_rxnorm_data)

if __name__ == "__main__":
    asyncio.run(run())
