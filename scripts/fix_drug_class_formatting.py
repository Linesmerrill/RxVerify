#!/usr/bin/env python3
"""
Script to fix drug class formatting issues in the RxList database.
Removes leading colons, commas, and extra whitespace from drug_class entries.
"""

import sqlite3
import logging
from typing import List, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_drug_class_formatting():
    """Fix drug class formatting issues in the RxList database."""
    db_path = "rxlist_database.db"
    
    logger.info("Starting drug class formatting cleanup...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all drug_class entries that need fixing
    cursor.execute("SELECT id, name, drug_class FROM drugs WHERE drug_class IS NOT NULL AND drug_class != ''")
    entries = cursor.fetchall()
    
    logger.info(f"Found {len(entries)} drug entries with drug_class data")
    
    fixed_count = 0
    for drug_id, name, drug_class in entries:
        if drug_class:
            original_class = drug_class
            cleaned_class = drug_class.strip()
            
            # Remove leading colons, commas, and extra whitespace
            while cleaned_class.startswith((':', ',', ' ')):
                cleaned_class = cleaned_class[1:].strip()
            
            # Remove trailing colons and commas
            while cleaned_class.endswith((':', ',')):
                cleaned_class = cleaned_class[:-1].strip()
            
            # Only update if the class was actually changed
            if cleaned_class != original_class and cleaned_class:
                cursor.execute("UPDATE drugs SET drug_class = ? WHERE id = ?", (cleaned_class, drug_id))
                logger.info(f"Fixed '{name}': '{original_class}' → '{cleaned_class}'")
                fixed_count += 1
            elif not cleaned_class:
                # If cleaning resulted in empty string, set to NULL
                cursor.execute("UPDATE drugs SET drug_class = NULL WHERE id = ?", (drug_id,))
                logger.info(f"Cleared empty drug_class for '{name}'")
                fixed_count += 1
    
    # Commit changes
    conn.commit()
    conn.close()
    
    logger.info(f"Fixed {fixed_count} drug class entries")
    logger.info("Drug class formatting cleanup completed!")

if __name__ == "__main__":
    fix_drug_class_formatting()
