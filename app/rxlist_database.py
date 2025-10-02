"""
RxList Database Module
Creates and manages a local database of drug information from RxList
"""

import sqlite3
import json
import time
import re
from typing import List, Optional, Dict, Any
from app.models import DrugSearchResult, Source
import logging

logger = logging.getLogger(__name__)

class RxListDatabase:
    def __init__(self, db_path: str = "rxlist_database.db"):
        self.db_path = db_path
        self._init_db()
        self._populate_initial_data()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drugs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                generic_name TEXT,
                brand_names TEXT, -- JSON string
                drug_class TEXT,
                common_uses TEXT, -- JSON string
                description TEXT,
                search_terms TEXT, -- JSON string for partial matching
                created_at REAL,
                updated_at REAL
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs(name);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drugs_generic ON drugs(generic_name);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drugs_search_terms ON drugs(search_terms);
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"RxList database initialized at {self.db_path}")

    def _populate_initial_data(self):
        """Populate the database with initial drug data from RxList."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if data already exists
        cursor.execute("SELECT COUNT(*) FROM drugs")
        count = cursor.fetchone()[0]
        
        if count == 0:
            logger.info("Populating RxList database with initial drug data...")
            self._insert_initial_drugs(cursor)
            conn.commit()
            logger.info("Initial drug data populated successfully")
        else:
            logger.info(f"RxList database already contains {count} drugs")
        
        conn.close()

    def _insert_initial_drugs(self, cursor):
        """Insert initial drug data based on common medications."""
        now = time.time()
        
        # Common drugs with their information
        drugs_data = [
            {
                "name": "Acetaminophen",
                "generic_name": "Acetaminophen",
                "brand_names": ["Tylenol", "Panadol", "Excedrin"],
                "drug_class": "Analgesic, Antipyretic",
                "common_uses": ["Pain relief", "Fever reduction", "Headache", "Muscle aches"],
                "description": "Over-the-counter pain reliever and fever reducer",
                "search_terms": ["acetaminophen", "tylenol", "panadol", "excedrin", "paracetamol"]
            },
            {
                "name": "Ibuprofen",
                "generic_name": "Ibuprofen",
                "brand_names": ["Advil", "Motrin", "Nurofen"],
                "drug_class": "NSAID",
                "common_uses": ["Pain relief", "Inflammation", "Fever reduction", "Arthritis"],
                "description": "Nonsteroidal anti-inflammatory drug for pain and inflammation",
                "search_terms": ["ibuprofen", "advil", "motrin", "nurofen"]
            },
            {
                "name": "Aspirin",
                "generic_name": "Acetylsalicylic Acid",
                "brand_names": ["Bayer", "Ecotrin", "Bufferin"],
                "drug_class": "NSAID, Antiplatelet",
                "common_uses": ["Pain relief", "Fever reduction", "Heart attack prevention", "Stroke prevention"],
                "description": "NSAID with antiplatelet properties",
                "search_terms": ["aspirin", "bayer", "ecotrin", "bufferin", "asa"]
            },
            {
                "name": "Atorvastatin",
                "generic_name": "Atorvastatin",
                "brand_names": ["Lipitor"],
                "drug_class": "Statin",
                "common_uses": ["Cholesterol lowering", "Heart disease prevention", "Stroke prevention"],
                "description": "HMG-CoA reductase inhibitor for cholesterol management",
                "search_terms": ["atorvastatin", "lipitor"]
            },
            {
                "name": "Metformin",
                "generic_name": "Metformin",
                "brand_names": ["Glucophage", "Fortamet", "Glumetza"],
                "drug_class": "Biguanide",
                "common_uses": ["Type 2 diabetes", "Blood sugar control", "PCOS"],
                "description": "First-line medication for type 2 diabetes",
                "search_terms": ["metformin", "glucophage", "fortamet", "glumetza"]
            },
            {
                "name": "Lisinopril",
                "generic_name": "Lisinopril",
                "brand_names": ["Prinivil", "Zestril"],
                "drug_class": "ACE Inhibitor",
                "common_uses": ["High blood pressure", "Heart failure", "Heart attack prevention"],
                "description": "Angiotensin-converting enzyme inhibitor",
                "search_terms": ["lisinopril", "prinivil", "zestril"]
            },
            {
                "name": "Levothyroxine",
                "generic_name": "Levothyroxine",
                "brand_names": ["Synthroid", "Levoxyl", "Unithroid"],
                "drug_class": "Thyroid Hormone",
                "common_uses": ["Hypothyroidism", "Thyroid replacement", "Goiter"],
                "description": "Synthetic thyroid hormone replacement",
                "search_terms": ["levothyroxine", "synthroid", "levoxyl", "unithroid"]
            },
            {
                "name": "Amlodipine",
                "generic_name": "Amlodipine",
                "brand_names": ["Norvasc"],
                "drug_class": "Calcium Channel Blocker",
                "common_uses": ["High blood pressure", "Chest pain (angina)", "Coronary artery disease"],
                "description": "Calcium channel blocker for cardiovascular conditions",
                "search_terms": ["amlodipine", "norvasc"]
            },
            {
                "name": "Omeprazole",
                "generic_name": "Omeprazole",
                "brand_names": ["Prilosec", "Losec"],
                "drug_class": "Proton Pump Inhibitor",
                "common_uses": ["GERD", "Stomach ulcers", "Acid reflux", "Heartburn"],
                "description": "Proton pump inhibitor for acid-related conditions",
                "search_terms": ["omeprazole", "prilosec", "losec"]
            },
            {
                "name": "Ivermectin",
                "generic_name": "Ivermectin",
                "brand_names": ["Stromectol", "Soolantra"],
                "drug_class": "Antiparasitic",
                "common_uses": ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"],
                "description": "Antiparasitic medication for various parasitic infections",
                "search_terms": ["ivermectin", "stromectol", "soolantra"]
            },
            {
                "name": "Hydrochlorothiazide",
                "generic_name": "Hydrochlorothiazide",
                "brand_names": ["Microzide", "Esidrix"],
                "drug_class": "Thiazide Diuretic",
                "common_uses": ["High blood pressure", "Fluid retention", "Heart failure"],
                "description": "Thiazide diuretic for blood pressure and fluid management",
                "search_terms": ["hydrochlorothiazide", "hctz", "microzide", "esidrix"]
            },
            {
                "name": "Simvastatin",
                "generic_name": "Simvastatin",
                "brand_names": ["Zocor"],
                "drug_class": "Statin",
                "common_uses": ["Cholesterol lowering", "Heart disease prevention", "Stroke prevention"],
                "description": "HMG-CoA reductase inhibitor for cholesterol management",
                "search_terms": ["simvastatin", "zocor"]
            },
            {
                "name": "Losartan",
                "generic_name": "Losartan",
                "brand_names": ["Cozaar"],
                "drug_class": "ARB",
                "common_uses": ["High blood pressure", "Heart failure", "Kidney protection"],
                "description": "Angiotensin receptor blocker for cardiovascular conditions",
                "search_terms": ["losartan", "cozaar"]
            },
            {
                "name": "Albuterol",
                "generic_name": "Albuterol",
                "brand_names": ["Proventil", "Ventolin", "ProAir"],
                "drug_class": "Bronchodilator",
                "common_uses": ["Asthma", "COPD", "Bronchospasm", "Breathing problems"],
                "description": "Short-acting beta-2 agonist bronchodilator",
                "search_terms": ["albuterol", "proventil", "ventolin", "proair", "salbutamol"]
            },
            {
                "name": "Metoprolol",
                "generic_name": "Metoprolol",
                "brand_names": ["Lopressor", "Toprol XL"],
                "drug_class": "Beta Blocker",
                "common_uses": ["High blood pressure", "Heart failure", "Chest pain", "Heart attack prevention"],
                "description": "Beta-adrenergic blocker for cardiovascular conditions",
                "search_terms": ["metoprolol", "lopressor", "toprol"]
            },
            {
                "name": "Tramadol",
                "generic_name": "Tramadol",
                "brand_names": ["Ultram"],
                "drug_class": "Opioid Analgesic",
                "common_uses": ["Pain relief", "Chronic pain", "Post-surgical pain"],
                "description": "Synthetic opioid analgesic for moderate to severe pain",
                "search_terms": ["tramadol", "ultram"]
            },
            {
                "name": "Gabapentin",
                "generic_name": "Gabapentin",
                "brand_names": ["Neurontin"],
                "drug_class": "Anticonvulsant",
                "common_uses": ["Seizures", "Neuropathic pain", "Restless legs syndrome", "Anxiety"],
                "description": "Anticonvulsant and neuropathic pain medication",
                "search_terms": ["gabapentin", "neurontin"]
            },
            {
                "name": "Sertraline",
                "generic_name": "Sertraline",
                "brand_names": ["Zoloft"],
                "drug_class": "SSRI",
                "common_uses": ["Depression", "Anxiety", "Panic disorder", "OCD", "PTSD"],
                "description": "Selective serotonin reuptake inhibitor antidepressant",
                "search_terms": ["sertraline", "zoloft"]
            },
            {
                "name": "Fluoxetine",
                "generic_name": "Fluoxetine",
                "brand_names": ["Prozac"],
                "drug_class": "SSRI",
                "common_uses": ["Depression", "Anxiety", "Panic disorder", "OCD", "Bulimia"],
                "description": "Selective serotonin reuptake inhibitor antidepressant",
                "search_terms": ["fluoxetine", "prozac"]
            },
            {
                "name": "Ciprofloxacin",
                "generic_name": "Ciprofloxacin",
                "brand_names": ["Cipro"],
                "drug_class": "Fluoroquinolone Antibiotic",
                "common_uses": ["Bacterial infections", "UTI", "Respiratory infections", "Skin infections"],
                "description": "Broad-spectrum fluoroquinolone antibiotic",
                "search_terms": ["ciprofloxacin", "cipro"]
            }
        ]
        
        for drug in drugs_data:
            cursor.execute("""
                INSERT INTO drugs (name, generic_name, brand_names, drug_class, common_uses, description, search_terms, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                drug["name"],
                drug["generic_name"],
                json.dumps(drug["brand_names"]),
                drug["drug_class"],
                json.dumps(drug["common_uses"]),
                drug["description"],
                json.dumps(drug["search_terms"]),
                now,
                now
            ))

    def search_drugs(self, query: str, limit: int = 10) -> List[DrugSearchResult]:
        """Search for drugs matching the query."""
        if not query or len(query.strip()) < 2:
            return []
        
        query = query.strip().lower()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Search in multiple fields with relevance scoring
        cursor.execute("""
            SELECT name, generic_name, brand_names, drug_class, common_uses, description, search_terms
            FROM drugs
            WHERE 
                LOWER(name) LIKE ? OR
                LOWER(generic_name) LIKE ? OR
                LOWER(brand_names) LIKE ? OR
                LOWER(search_terms) LIKE ?
            ORDER BY 
                CASE 
                    WHEN LOWER(name) = ? THEN 1
                    WHEN LOWER(name) LIKE ? THEN 2
                    WHEN LOWER(generic_name) LIKE ? THEN 3
                    WHEN LOWER(brand_names) LIKE ? THEN 4
                    WHEN LOWER(search_terms) LIKE ? THEN 5
                    ELSE 6
                END,
                name
            LIMIT ?
        """, (
            f"%{query}%",  # name LIKE
            f"%{query}%",  # generic_name LIKE
            f"%{query}%",  # brand_names LIKE
            f"%{query}%",  # search_terms LIKE
            query,         # exact name match
            f"{query}%",   # name starts with
            f"%{query}%",  # generic_name LIKE
            f"%{query}%",  # brand_names LIKE
            f"%{query}%",  # search_terms LIKE
            limit
        ))
        
        results = []
        for row in cursor.fetchall():
            name, generic_name, brand_names_json, drug_class, common_uses_json, description, search_terms_json = row
            
            # Parse JSON fields
            brand_names = json.loads(brand_names_json) if brand_names_json else []
            common_uses = json.loads(common_uses_json) if common_uses_json else []
            search_terms = json.loads(search_terms_json) if search_terms_json else []
            
            # Create DrugSearchResult
            result = DrugSearchResult(
                rxcui=f"rxlist_{name.lower().replace(' ', '_')}",  # Generate unique ID
                name=name,
                generic_name=generic_name,
                brand_names=brand_names,
                common_uses=common_uses,
                drug_class=drug_class,
                source=Source.RXLIST
            )
            results.append(result)
        
        conn.close()
        logger.debug(f"RxList search found {len(results)} results for query: '{query}'")
        return results

    def add_drug(self, name: str, generic_name: str = None, brand_names: List[str] = None, 
                 drug_class: str = None, common_uses: List[str] = None, 
                 description: str = None, search_terms: List[str] = None):
        """Add a new drug to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = time.time()
        search_terms = search_terms or []
        
        # Add name and generic name to search terms if not already present
        if name.lower() not in [term.lower() for term in search_terms]:
            search_terms.append(name)
        if generic_name and generic_name.lower() not in [term.lower() for term in search_terms]:
            search_terms.append(generic_name)
        
        cursor.execute("""
            INSERT OR REPLACE INTO drugs (name, generic_name, brand_names, drug_class, common_uses, description, search_terms, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            generic_name,
            json.dumps(brand_names or []),
            drug_class,
            json.dumps(common_uses or []),
            description,
            json.dumps(search_terms),
            now,
            now
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Added drug to RxList database: {name}")

    def get_drug_stats(self) -> Dict[str, Any]:
        """Get statistics about the RxList database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM drugs")
        total_drugs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM drugs WHERE drug_class IS NOT NULL")
        drugs_with_class = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM drugs WHERE common_uses IS NOT NULL")
        drugs_with_uses = cursor.fetchone()[0]
        
        # Get most common drug classes
        cursor.execute("""
            SELECT drug_class, COUNT(*) as count
            FROM drugs
            WHERE drug_class IS NOT NULL
            GROUP BY drug_class
            ORDER BY count DESC
            LIMIT 5
        """)
        top_classes = [{"class": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "total_drugs": total_drugs,
            "drugs_with_class": drugs_with_class,
            "drugs_with_uses": drugs_with_uses,
            "top_drug_classes": top_classes
        }

    def clear_database(self) -> bool:
        """Clear all data from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM drugs")
            conn.commit()
            conn.close()
            logger.info("RxList database cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Error clearing RxList database: {e}")
            return False

# Global instance
_rxlist_database_instance: Optional[RxListDatabase] = None

def get_rxlist_database() -> RxListDatabase:
    """Get or create the global RxListDatabase instance."""
    global _rxlist_database_instance
    if _rxlist_database_instance is None:
        _rxlist_database_instance = RxListDatabase()
    return _rxlist_database_instance
