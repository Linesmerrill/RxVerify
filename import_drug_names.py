#!/usr/bin/env python3
"""
Read drug names from text file and insert them into the database.
This script will:
1. Read drug names from drug_names_input.txt
2. Clean and format each drug name
3. Insert them into the database with proper structure
4. Ensure they are searchable and have proper metadata
"""

import asyncio
import uuid
import re
from datetime import datetime
from app.mongodb_config import MongoDBConfig
from app.drug_database_manager import DrugDatabaseManager
from app.drug_database_schema import DrugEntry, DrugType, DrugStatus
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DrugNameImporter:
    def __init__(self):
        self.mongodb_config = MongoDBConfig()
        self.db_manager = DrugDatabaseManager()
        
    async def initialize(self):
        """Initialize database connections."""
        await self.db_manager.initialize()
        
    def clean_drug_name(self, name):
        """Clean and format drug name."""
        # Remove extra whitespace
        name = name.strip()
        
        # Remove comments (lines starting with #)
        if name.startswith('#'):
            return None
            
        # Skip empty lines
        if not name:
            return None
            
        # Remove dosage information (e.g., "500mg", "2ml", etc.)
        # This ensures we only keep the base drug name
        dosage_patterns = [
            r'\s+\d+\s*(mg|mcg|ml|g|gram|grams)\s*$',
            r'\s+\d+\.\d+\s*(mg|mcg|ml|g|gram|grams)\s*$',
            r'\s+\d+\s*(mg|mcg|ml|g|gram|grams)\s*\(.*\)\s*$',
        ]
        
        for pattern in dosage_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        # Clean up any remaining extra spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Convert to proper title case (first letter of each word capitalized)
        name = name.title()
        
        return name if name else None
        
    async def import_drug_names(self, filename='drug_names_input.txt'):
        """Import drug names from text file."""
        logger.info(f"Reading drug names from {filename}...")
        
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                lines = file.readlines()
        except FileNotFoundError:
            logger.error(f"File {filename} not found!")
            return
            
        # Process each line
        drug_names = []
        for line_num, line in enumerate(lines, 1):
            cleaned_name = self.clean_drug_name(line)
            if cleaned_name:
                drug_names.append(cleaned_name)
                logger.info(f"Line {line_num}: '{line.strip()}' -> '{cleaned_name}'")
            else:
                logger.debug(f"Line {line_num}: Skipped '{line.strip()}'")
        
        # Remove duplicates while preserving order
        unique_drugs = []
        seen = set()
        for drug in drug_names:
            if drug not in seen:
                unique_drugs.append(drug)
                seen.add(drug)
        
        logger.info(f"Found {len(drug_names)} drug names, {len(unique_drugs)} unique")
        
        if not unique_drugs:
            logger.warning("No valid drug names found!")
            return
            
        # Insert drugs into database
        inserted_count = 0
        skipped_count = 0
        
        for drug_name in unique_drugs:
            # Check if drug already exists
            existing_drug = await self.db_manager.drugs_collection.find_one({
                "name": drug_name
            })
            
            if existing_drug:
                logger.info(f"Skipping '{drug_name}' - already exists")
                skipped_count += 1
                continue
                
            # Create drug entry
            drug_entry = DrugEntry(
                drug_id=f"{drug_name.lower().replace(' ', '_')}_DrugType.GENERIC_{uuid.uuid4().hex[:8]}",
                name=drug_name,
                drug_type=DrugType.GENERIC,
                generic_name=drug_name,  # Assume it's generic unless specified otherwise
                brand_names=[],  # Empty for now
                common_uses=[],  # Empty for now
                drug_class=None,  # Empty for now
                manufacturer=None,  # Empty for now
                rxnorm_id=None,  # Empty for now
                ndc_codes=[],  # Empty for now
                search_terms=[drug_name.lower()],
                primary_search_term=drug_name.lower(),
                status=DrugStatus.ACTIVE,
                data_source="Manual Import",
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                search_count=0,
                last_searched=None,
                # Rating fields
                rating_score=0.0,
                total_votes=0,
                upvotes=0,
                downvotes=0
            )
            
            # Insert into database
            await self.db_manager.drugs_collection.insert_one(drug_entry.dict())
            inserted_count += 1
            logger.info(f"Inserted: {drug_name}")
        
        logger.info(f"Import complete!")
        logger.info(f"Inserted: {inserted_count} drugs")
        logger.info(f"Skipped: {skipped_count} drugs (already existed)")
        
        # Get final count
        total_count = await self.db_manager.drugs_collection.count_documents({})
        logger.info(f"Total drugs in database: {total_count}")

async def main():
    """Main import function."""
    importer = DrugNameImporter()
    await importer.initialize()
    await importer.import_drug_names()

if __name__ == "__main__":
    asyncio.run(main())
