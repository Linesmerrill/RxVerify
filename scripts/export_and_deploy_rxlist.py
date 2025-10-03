#!/usr/bin/env python3
"""
Script to export RxList drug data and deploy it to Heroku.
This allows us to populate the deployed app with our scraped data
without having to re-scrape from the website.
"""

import asyncio
import json
import sqlite3
import time
import logging
from typing import List, Dict
import httpx
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
LOCAL_DB_PATH = "rxlist_database.db"
HEROKU_BACKEND_URL = "https://rx-verify-api-e68bdd74c056.herokuapp.com"
BATCH_SIZE = 100  # Process drugs in batches to avoid memory issues

def export_drugs_from_local_db() -> List[Dict]:
    """Export all drugs from the local SQLite database."""
    logger.info(f"Exporting drugs from local database: {LOCAL_DB_PATH}")
    
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.cursor()
    
    # Get all drugs
    cursor.execute("""
        SELECT name, generic_name, brand_names, drug_class, common_uses, description, search_terms
        FROM drugs
        ORDER BY name
    """)
    
    drugs = []
    for row in cursor.fetchall():
        name, generic_name, brand_names_json, drug_class, common_uses_json, description, search_terms_json = row
        
        # Parse JSON fields
        brand_names = json.loads(brand_names_json) if brand_names_json else []
        common_uses = json.loads(common_uses_json) if common_uses_json else []
        search_terms = json.loads(search_terms_json) if search_terms_json else []
        
        drug_data = {
            "name": name,
            "generic_name": generic_name,
            "brand_names": brand_names,
            "drug_class": drug_class,
            "common_uses": common_uses,
            "description": description,
            "search_terms": search_terms
        }
        drugs.append(drug_data)
    
    conn.close()
    logger.info(f"Exported {len(drugs)} drugs from local database")
    return drugs

async def deploy_drugs_to_heroku(drugs: List[Dict]) -> bool:
    """Deploy drugs to Heroku backend in batches."""
    logger.info(f"Deploying {len(drugs)} drugs to Heroku backend...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # First, clear the existing database
        try:
            logger.info("Clearing existing RxList database on Heroku...")
            response = await client.post(f"{HEROKU_BACKEND_URL}/rxlist/clear")
            if response.status_code == 200:
                logger.info("Successfully cleared Heroku RxList database")
            else:
                logger.warning(f"Failed to clear database: {response.status_code}")
        except Exception as e:
            logger.error(f"Error clearing database: {str(e)}")
            return False
        
        # Deploy drugs in batches
        total_inserted = 0
        total_skipped = 0
        
        for i in range(0, len(drugs), BATCH_SIZE):
            batch = drugs[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (len(drugs) + BATCH_SIZE - 1) // BATCH_SIZE
            
            logger.info(f"Deploying batch {batch_num}/{total_batches} ({len(batch)} drugs)...")
            
            try:
                response = await client.post(
                    f"{HEROKU_BACKEND_URL}/rxlist/ingest",
                    json=batch,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    batch_inserted = result.get("total_drugs", 0) - total_inserted
                    total_inserted = result.get("total_drugs", 0)
                    logger.info(f"Batch {batch_num} deployed successfully. Total drugs: {total_inserted}")
                else:
                    logger.error(f"Failed to deploy batch {batch_num}: {response.status_code} - {response.text}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error deploying batch {batch_num}: {str(e)}")
                return False
            
            # Small delay between batches to be respectful
            await asyncio.sleep(1)
        
        logger.info(f"Successfully deployed {total_inserted} drugs to Heroku!")
        return True

async def verify_deployment() -> bool:
    """Verify that the deployment was successful."""
    logger.info("Verifying deployment...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{HEROKU_BACKEND_URL}/rxlist/stats")
            if response.status_code == 200:
                stats = response.json()
                total_drugs = stats.get("rxlist_stats", {}).get("total_drugs", 0)
                logger.info(f"Verification successful! Heroku database has {total_drugs} drugs")
                return True
            else:
                logger.error(f"Failed to verify deployment: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error verifying deployment: {str(e)}")
            return False

async def main():
    """Main function to export and deploy RxList data."""
    logger.info("Starting RxList data export and deployment...")
    
    # Check if local database exists
    if not os.path.exists(LOCAL_DB_PATH):
        logger.error(f"Local database not found: {LOCAL_DB_PATH}")
        return
    
    # Export drugs from local database
    drugs = export_drugs_from_local_db()
    if not drugs:
        logger.error("No drugs found in local database")
        return
    
    # Save exported data to JSON file for backup
    export_file = f"rxlist_export_{int(time.time())}.json"
    with open(export_file, 'w') as f:
        json.dump(drugs, f, indent=2)
    logger.info(f"Exported data saved to: {export_file}")
    
    # Deploy to Heroku
    success = await deploy_drugs_to_heroku(drugs)
    if not success:
        logger.error("Failed to deploy drugs to Heroku")
        return
    
    # Verify deployment
    if await verify_deployment():
        logger.info("✅ RxList data successfully deployed to Heroku!")
    else:
        logger.error("❌ Deployment verification failed")

if __name__ == "__main__":
    asyncio.run(main())
