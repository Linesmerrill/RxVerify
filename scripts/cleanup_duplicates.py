#!/usr/bin/env python3
"""
Script to clean up duplicate entries in the RxList database.
This will remove exact duplicates and keep only one entry per unique drug.
"""

import sqlite3
import logging
from typing import List, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_duplicates():
    """Remove duplicate entries from the RxList database."""
    db_path = "rxlist_database.db"
    
    logger.info("Starting duplicate cleanup...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get initial count
    cursor.execute("SELECT COUNT(*) FROM drugs")
    initial_count = cursor.fetchone()[0]
    logger.info(f"Initial drug count: {initial_count}")
    
    # Find duplicates by name, generic_name, and brand_names
    cursor.execute("""
        SELECT name, generic_name, brand_names, COUNT(*) as count
        FROM drugs 
        GROUP BY name, generic_name, brand_names 
        HAVING COUNT(*) > 1
        ORDER BY count DESC
    """)
    
    duplicates = cursor.fetchall()
    logger.info(f"Found {len(duplicates)} groups of duplicates")
    
    total_removed = 0
    
    for name, generic_name, brand_names, count in duplicates:
        logger.info(f"Removing {count-1} duplicates for: {name}")
        
        # Keep the first entry, remove the rest
        cursor.execute("""
            DELETE FROM drugs 
            WHERE name = ? AND generic_name = ? AND brand_names = ?
            AND rowid NOT IN (
                SELECT MIN(rowid) 
                FROM drugs 
                WHERE name = ? AND generic_name = ? AND brand_names = ?
            )
        """, (name, generic_name, brand_names, name, generic_name, brand_names))
        
        removed_count = cursor.rowcount
        total_removed += removed_count
        logger.info(f"Removed {removed_count} duplicates for {name}")
    
    # Commit changes
    conn.commit()
    
    # Get final count
    cursor.execute("SELECT COUNT(*) FROM drugs")
    final_count = cursor.fetchone()[0]
    
    logger.info(f"Cleanup complete!")
    logger.info(f"Initial count: {initial_count}")
    logger.info(f"Final count: {final_count}")
    logger.info(f"Total duplicates removed: {total_removed}")
    
    conn.close()
    
    return total_removed

if __name__ == "__main__":
    cleanup_duplicates()
