"""
Dosage Service for RxVerify

Fetches and parses drug dosage information from OpenFDA drug labels.
Populates the `dosages` field on drug records in MongoDB.
"""

import re
import logging
import asyncio
import httpx
from typing import List, Optional

logger = logging.getLogger(__name__)

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"

# Pattern to extract dosage strengths like "500 mg", "10 mg/5 mL", "0.25 mg", "100 mcg"
DOSAGE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|meq|units?|iu|%)"
    r"(?:\s*/\s*(\d+(?:\.\d+)?)\s*(ml|g|mg|tablet|capsule|dose))?",
    re.IGNORECASE,
)


def parse_dosages_from_text(text: str) -> List[str]:
    """Extract unique dosage strengths from free-text dosage information.

    Parses strings like:
        "500 mg tablets", "10 mg/5 mL oral suspension", "0.25 mg"
    into a deduplicated, sorted list of dosage strings.
    """
    if not text:
        return []

    matches = DOSAGE_PATTERN.findall(text)
    seen = set()
    dosages: List[str] = []

    for match in matches:
        amount, unit, denom_amount, denom_unit = match
        unit = unit.lower()
        # Normalise common unit names
        if unit == "iu":
            unit = "IU"
        elif unit in ("unit", "units"):
            unit = "units"

        if denom_amount and denom_unit:
            dosage_str = f"{amount} {unit}/{denom_amount} {denom_unit.lower()}"
        else:
            dosage_str = f"{amount} {unit}"

        key = dosage_str.lower()
        if key not in seen:
            seen.add(key)
            dosages.append(dosage_str)

    return dosages


async def fetch_dosages_from_openfda(drug_name: str) -> List[str]:
    """Query OpenFDA drug/label endpoint and return parsed dosage strengths."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params = {
                "search": f'openfda.generic_name:"{drug_name}"',
                "limit": 3,
            }
            response = await client.get(OPENFDA_LABEL_URL, params=params)

            if response.status_code != 200:
                # Retry with a broader search (brand name field)
                params["search"] = f'openfda.brand_name:"{drug_name}"'
                response = await client.get(OPENFDA_LABEL_URL, params=params)

            if response.status_code != 200:
                logger.debug(f"OpenFDA returned {response.status_code} for '{drug_name}'")
                return []

            data = response.json()
            results = data.get("results", [])
            if not results:
                return []

            all_dosages: List[str] = []
            for result in results:
                # Primary source: dosage_and_administration section
                dosage_sections = result.get("dosage_and_administration", [])
                for section_text in dosage_sections:
                    all_dosages.extend(parse_dosages_from_text(section_text))

                # Secondary source: description section (often contains strength info)
                descriptions = result.get("description", [])
                for desc in descriptions:
                    all_dosages.extend(parse_dosages_from_text(desc))

                # Tertiary: spl_product_data_elements (contains active ingredient strengths)
                spl_data = result.get("spl_product_data_elements", [])
                for spl in spl_data:
                    all_dosages.extend(parse_dosages_from_text(spl))

            # Deduplicate while preserving order
            seen: set = set()
            unique: List[str] = []
            for d in all_dosages:
                key = d.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(d)

            return unique

    except Exception as e:
        logger.warning(f"Failed to fetch dosages from OpenFDA for '{drug_name}': {e}")
        return []


async def populate_dosages_for_all_drugs(
    drugs_collection,
    batch_size: int = 50,
    delay_between_batches: float = 1.0,
) -> dict:
    """Iterate over all drugs in the database and populate dosages from OpenFDA.

    Returns a summary dict with counts of updated / skipped / failed drugs.
    """
    stats = {"total": 0, "updated": 0, "skipped": 0, "failed": 0, "already_has_dosages": 0}

    # Find drugs that don't already have dosages populated
    cursor = drugs_collection.find(
        {"$or": [{"dosages": {"$exists": False}}, {"dosages": {"$size": 0}}]},
        {"drug_id": 1, "name": 1, "generic_name": 1},
    )

    batch: list = []
    async for doc in cursor:
        batch.append(doc)
        if len(batch) >= batch_size:
            await _process_batch(drugs_collection, batch, stats)
            batch = []
            await asyncio.sleep(delay_between_batches)

    # Process remaining
    if batch:
        await _process_batch(drugs_collection, batch, stats)

    # Count drugs that already had dosages
    already_count = await drugs_collection.count_documents(
        {"dosages": {"$exists": True, "$not": {"$size": 0}}}
    )
    stats["already_has_dosages"] = already_count

    logger.info(
        f"Dosage population complete: {stats['updated']} updated, "
        f"{stats['skipped']} skipped, {stats['failed']} failed, "
        f"{stats['already_has_dosages']} already had dosages"
    )
    return stats


async def _process_batch(drugs_collection, batch: list, stats: dict):
    """Process a batch of drugs concurrently."""
    tasks = []
    for doc in batch:
        tasks.append(_fetch_and_update_single(drugs_collection, doc, stats))
    await asyncio.gather(*tasks, return_exceptions=True)


async def _fetch_and_update_single(drugs_collection, doc: dict, stats: dict):
    """Fetch dosages for a single drug and update the database."""
    stats["total"] += 1
    drug_id = doc.get("drug_id", "")
    # Prefer generic_name for OpenFDA lookups since labels are indexed by generic name
    drug_name = doc.get("generic_name") or doc.get("name", "")

    if not drug_name:
        stats["skipped"] += 1
        return

    try:
        dosages = await fetch_dosages_from_openfda(drug_name)
        if dosages:
            await drugs_collection.update_one(
                {"drug_id": drug_id},
                {"$set": {"dosages": dosages}},
            )
            stats["updated"] += 1
            logger.debug(f"Updated dosages for '{drug_name}': {dosages}")
        else:
            stats["skipped"] += 1
    except Exception as e:
        stats["failed"] += 1
        logger.warning(f"Failed to update dosages for '{drug_name}': {e}")
