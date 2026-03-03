"""
Dosage Service for RxVerify

Provides clean, structured dosage information from the pre-processed
OpenFDA NDC bulk dataset (data/drug_dosages.json).

The NDC dataset contains structured active_ingredients with exact strengths
and dosage forms, unlike the old label-scraping approach which extracted
random numbers from free-text paragraphs.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOSAGES_FILE = PROJECT_ROOT / "data" / "drug_dosages.json"

# Module-level cache so we only load the file once per process
_dosage_cache: Optional[Dict] = None


def _load_dosage_data() -> Dict:
    """Load the pre-processed dosage data from disk (cached)."""
    global _dosage_cache
    if _dosage_cache is not None:
        return _dosage_cache

    if not DOSAGES_FILE.exists():
        logger.warning(
            f"Dosage data file not found at {DOSAGES_FILE}. "
            "Run scripts/fetch_dosages.py to generate it."
        )
        _dosage_cache = {}
        return _dosage_cache

    with open(DOSAGES_FILE) as f:
        data = json.load(f)

    _dosage_cache = data.get("drugs", {})
    logger.info(f"Loaded dosage data for {len(_dosage_cache)} drugs")
    return _dosage_cache


def _normalize(name: str) -> str:
    """Lowercase and strip a name for comparison."""
    if not name:
        return ""
    return name.lower().strip()


def _sort_strength(s: str) -> float:
    """Extract numeric value from strength string for sorting."""
    match = re.match(r"([\d.]+)", s)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 0.0


def lookup_dosages(drug_name: str) -> Dict[str, List[str]]:
    """Look up dosages for a drug by name.

    Returns a dict keyed by lowercase dosage form, e.g.:
        {"tablet": ["10 mg", "20 mg"], "solution": ["5 mg/5mL"]}
    """
    cache = _load_dosage_data()
    if not cache:
        return {}

    name_lower = _normalize(drug_name)

    # Try exact key match first
    for key, data in cache.items():
        if _normalize(key) == name_lower:
            return _format_dosages(data)

    # Try matching on generic_name or brand_names
    for key, data in cache.items():
        if _normalize(data.get("generic_name", "")) == name_lower:
            return _format_dosages(data)
        for bn in data.get("brand_names", []):
            if _normalize(bn) == name_lower:
                return _format_dosages(data)

    # Try partial/contains match
    for key, data in cache.items():
        if name_lower in _normalize(key):
            return _format_dosages(data)

    return {}


def _format_dosages(drug_data: dict) -> Dict[str, List[str]]:
    """Format the simplified dosage data into a dict keyed by form.

    Returns e.g.: {"tablet": ["2.5 mg", "5 mg", "10 mg"], "solution": ["1 mg"]}
    """
    dosage_forms = drug_data.get("dosage_forms", {})
    result = {}
    for form, strengths in sorted(dosage_forms.items()):
        sorted_strengths = sorted(strengths, key=_sort_strength)
        result[form.lower()] = sorted_strengths
    return result


async def populate_dosages_for_all_drugs(
    drugs_collection,
) -> dict:
    """Replace dosages for ALL drugs in MongoDB using clean NDC data.

    This wipes any existing (potentially bad) dosage data and replaces
    it with structured data from the OpenFDA NDC bulk dataset.
    """
    cache = _load_dosage_data()
    if not cache:
        return {
            "error": f"No dosage data found. Run scripts/fetch_dosages.py first.",
            "total": 0,
            "updated": 0,
            "cleared": 0,
        }

    stats = {"total": 0, "updated": 0, "cleared": 0, "skipped": 0}

    # Iterate over every drug in the database
    cursor = drugs_collection.find(
        {},
        {"drug_id": 1, "name": 1, "generic_name": 1, "brand_names": 1},
    )

    async for doc in cursor:
        stats["total"] += 1
        drug_id = doc.get("drug_id", "")
        drug_name = doc.get("name", "")
        generic_name = doc.get("generic_name", "")

        # Try multiple name variants to find a match
        dosages: Dict[str, List[str]] = {}
        for try_name in [drug_name, generic_name]:
            if try_name:
                dosages = lookup_dosages(try_name)
                if dosages:
                    break

        # Also try brand names
        if not dosages:
            for bn in doc.get("brand_names", []):
                dosages = lookup_dosages(bn)
                if dosages:
                    break

        if dosages:
            await drugs_collection.update_one(
                {"drug_id": drug_id},
                {"$set": {"dosages": dosages}},
            )
            stats["updated"] += 1
        else:
            # Clear out any bad data that was there before
            await drugs_collection.update_one(
                {"drug_id": drug_id},
                {"$set": {"dosages": {}}},
            )
            stats["cleared"] += 1

    logger.info(
        f"Dosage population complete: {stats['updated']} updated, "
        f"{stats['cleared']} cleared, {stats['total']} total"
    )
    return stats
