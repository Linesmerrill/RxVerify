#!/usr/bin/env python3
"""Wipe bad dosage data from MongoDB and repopulate with clean NDC data.

Usage:
    python scripts/populate_dosages_mongo.py            # Dry-run (preview changes)
    python scripts/populate_dosages_mongo.py --apply     # Actually update MongoDB
"""

import asyncio
import json
import re
import sys
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
    """Build a name -> dosages lookup from the drug_dosages.json data."""
    lookup = {}
    for key, data in drugs_dosages.items():
        dosage_forms = data.get("dosage_forms", {})
        formatted = {}
        for form, strengths in sorted(dosage_forms.items()):
            sorted_s = sorted(strengths, key=_sort_strength)
            formatted[form.lower()] = sorted_s

        if not formatted:
            continue

        lookup[key.lower().strip()] = formatted
        gn = data.get("generic_name", "").lower().strip()
        if gn:
            lookup[gn] = formatted
        for bn in data.get("brand_names", []):
            bn_lower = bn.lower().strip()
            if bn_lower:
                lookup[bn_lower] = formatted

    return lookup


def find_dosages(lookup: dict, doc: dict) -> dict | None:
    """Find clean dosages for a MongoDB drug document."""
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
        {"drug_id": 1, "name": 1, "generic_name": 1, "brand_names": 1, "dosages": 1},
    ).to_list(length=None)
    print(f"  Loaded {len(docs)} documents")

    # Build bulk write operations
    stats = {"total": 0, "updated": 0, "cleared": 0, "unchanged": 0}
    operations = []
    samples_shown = 0

    for doc in docs:
        stats["total"] += 1
        drug_id = doc.get("drug_id", "")
        name = doc.get("name", "")
        old_dosages = doc.get("dosages", {})

        new_dosages = find_dosages(lookup, doc)

        if new_dosages:
            if new_dosages != old_dosages:
                operations.append(
                    UpdateOne({"drug_id": drug_id}, {"$set": {"dosages": new_dosages}})
                )
                stats["updated"] += 1
                if samples_shown < 5:
                    old_preview = list(old_dosages.items())[:3] if isinstance(old_dosages, dict) else old_dosages[:3]
                    new_preview = list(new_dosages.items())[:3]
                    print(f"\n  UPDATING: {name}")
                    print(f"    Old: {old_preview}{'...' if len(old_dosages) > 3 else ''}")
                    print(f"    New: {new_preview}{'...' if len(new_dosages) > 3 else ''}")
                    samples_shown += 1
            else:
                stats["unchanged"] += 1
        else:
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

    if dry_run:
        print(f"\nRun with --apply to commit these changes to MongoDB.")

    if hasattr(config, 'client') and config.client:
        config.client.close()


if __name__ == "__main__":
    asyncio.run(main())
