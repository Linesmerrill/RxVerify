#!/usr/bin/env python3
"""Populate MongoDB drugs with clean data from OpenFDA NDC dataset.

Updates dosages, drug_class, manufacturer, ndc_codes, rxnorm_id, and
active_ingredients for all matched drugs.

Usage:
    python scripts/populate_dosages_mongo.py            # Dry-run (preview changes)
    python scripts/populate_dosages_mongo.py --apply     # Actually update MongoDB
"""

import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path so we can import app modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DOSAGES_FILE = PROJECT_ROOT / "data" / "drug_dosages.json"


def _sort_strength(s: str) -> float:
    match = re.match(r"([\d.]+)", s)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 0.0


def build_lookup(drugs_dosages: dict) -> dict:
    """Build a name -> full drug data lookup from the drug_dosages.json data."""
    lookup = {}
    for key, data in drugs_dosages.items():
        dosage_forms = data.get("dosage_forms", {})
        formatted_dosages = {}
        for form, strengths in sorted(dosage_forms.items()):
            sorted_s = sorted(strengths, key=_sort_strength)
            formatted_dosages[form.lower()] = sorted_s

        if not formatted_dosages:
            continue

        entry = {
            "dosages": formatted_dosages,
            "drug_class": data.get("drug_class", ""),
            "pharm_classes": data.get("pharm_classes", []),
            "manufacturers": data.get("manufacturers", []),
            "ndc_codes": data.get("ndc_codes", []),
            "rxcuis": data.get("rxcuis", []),
            "active_ingredients": data.get("active_ingredients", []),
            "routes": data.get("routes", []),
        }

        lookup[key.lower().strip()] = entry
        gn = data.get("generic_name", "").lower().strip()
        if gn:
            lookup[gn] = entry
        for bn in data.get("brand_names", []):
            bn_lower = bn.lower().strip()
            if bn_lower:
                lookup[bn_lower] = entry

    return lookup


def find_drug_data(lookup: dict, doc: dict) -> dict | None:
    """Find clean NDC data for a MongoDB drug document."""
    for try_name in [doc.get("name", ""), doc.get("generic_name", "")] + (doc.get("brand_names") or []):
        if try_name:
            key = try_name.lower().strip()
            if key in lookup:
                return lookup[key]
    return None


async def main():
    from pymongo import UpdateOne

    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("DRY RUN - no changes will be made. Pass --apply to update MongoDB.\n")

    # Load clean dosage data
    if not DOSAGES_FILE.exists():
        print(f"ERROR: {DOSAGES_FILE} not found. Run scripts/fetch_dosages.py first.")
        sys.exit(1)

    print(f"Loading clean dosage data from {DOSAGES_FILE}...")
    with open(DOSAGES_FILE) as f:
        dosage_data = json.load(f)
    drugs_dosages = dosage_data.get("drugs", {})
    print(f"  Loaded dosages for {len(drugs_dosages)} drugs")

    lookup = build_lookup(drugs_dosages)
    print(f"  Built lookup with {len(lookup)} name variants")

    # Connect to MongoDB
    from app.mongodb_config import MongoDBConfig

    config = MongoDBConfig()
    db = await config.connect()
    drugs_collection = db.drugs

    total = await drugs_collection.count_documents({})
    print(f"\nMongoDB drugs collection: {total} documents")

    # Load ALL docs into memory first to avoid cursor timeout
    print("Loading all drug documents...")
    docs = await drugs_collection.find(
        {},
        {
            "drug_id": 1, "name": 1, "generic_name": 1, "brand_names": 1,
            "dosages": 1, "drug_class": 1, "manufacturer": 1,
            "ndc_codes": 1, "rxnorm_id": 1, "active_ingredients": 1,
        },
    ).to_list(length=None)
    print(f"  Loaded {len(docs)} documents")

    # Build bulk write operations
    stats = {"total": 0, "updated": 0, "cleared": 0, "unchanged": 0, "enriched_fields": defaultdict(int)}
    operations = []
    samples_shown = 0

    for doc in docs:
        stats["total"] += 1
        drug_id = doc.get("drug_id", "")
        name = doc.get("name", "")

        ndc_data = find_drug_data(lookup, doc)

        if ndc_data:
            update_fields = {}

            # Dosages
            new_dosages = ndc_data["dosages"]
            old_dosages = doc.get("dosages", {})
            if new_dosages != old_dosages:
                update_fields["dosages"] = new_dosages

            # Drug class - use FDA pharm_class if existing is empty or generic "Medication"
            old_class = doc.get("drug_class", "")
            fda_class = ndc_data.get("drug_class", "")
            if fda_class and (not old_class or old_class == "Medication"):
                update_fields["drug_class"] = fda_class
                stats["enriched_fields"]["drug_class"] += 1

            # Manufacturer - set if empty
            old_mfr = doc.get("manufacturer", "")
            manufacturers = ndc_data.get("manufacturers", [])
            if not old_mfr and manufacturers:
                update_fields["manufacturer"] = manufacturers[0]
                stats["enriched_fields"]["manufacturer"] += 1

            # NDC codes - set if empty
            old_ndc = doc.get("ndc_codes", [])
            ndc_codes = ndc_data.get("ndc_codes", [])
            if not old_ndc and ndc_codes:
                update_fields["ndc_codes"] = ndc_codes[:20]  # Cap at 20 to avoid bloat
                stats["enriched_fields"]["ndc_codes"] += 1

            # RxNorm ID - set if empty
            old_rxnorm = doc.get("rxnorm_id", "")
            rxcuis = ndc_data.get("rxcuis", [])
            if not old_rxnorm and rxcuis:
                update_fields["rxnorm_id"] = rxcuis[0]
                stats["enriched_fields"]["rxnorm_id"] += 1

            # Active ingredients - set if empty
            old_ingredients = doc.get("active_ingredients", [])
            ingredients = ndc_data.get("active_ingredients", [])
            if not old_ingredients and ingredients:
                update_fields["active_ingredients"] = ingredients
                stats["enriched_fields"]["active_ingredients"] += 1

            if update_fields:
                operations.append(
                    UpdateOne({"drug_id": drug_id}, {"$set": update_fields})
                )
                stats["updated"] += 1
                if samples_shown < 5:
                    print(f"\n  UPDATING: {name}")
                    for field, val in update_fields.items():
                        if field == "dosages":
                            preview = list(val.items())[:2]
                            print(f"    dosages: {preview}...")
                        else:
                            print(f"    {field}: {val}")
                    samples_shown += 1
            else:
                stats["unchanged"] += 1
        else:
            old_dosages = doc.get("dosages", {})
            if old_dosages:
                operations.append(
                    UpdateOne({"drug_id": drug_id}, {"$set": {"dosages": {}}})
                )
                stats["cleared"] += 1
            else:
                stats["unchanged"] += 1

    # Execute bulk write
    if operations and not dry_run:
        print(f"\nWriting {len(operations)} updates to MongoDB...")
        # Process in batches of 500
        batch_size = 500
        for i in range(0, len(operations), batch_size):
            batch = operations[i:i + batch_size]
            result = await drugs_collection.bulk_write(batch, ordered=False)
            print(f"  Batch {i // batch_size + 1}: {result.modified_count} modified")

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")
    print(f"Total drugs in MongoDB:   {stats['total']}")
    print(f"Updated with clean data:  {stats['updated']}")
    print(f"Cleared (no NDC match):   {stats['cleared']}")
    print(f"Already correct:          {stats['unchanged']}")
    if stats["enriched_fields"]:
        print(f"\nEnriched fields:")
        for field, count in sorted(stats["enriched_fields"].items()):
            print(f"  {field}: {count} drugs")

    if dry_run:
        print(f"\nRun with --apply to commit these changes to MongoDB.")

    if hasattr(config, 'client') and config.client:
        config.client.close()


if __name__ == "__main__":
    asyncio.run(main())
