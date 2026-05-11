"""Backfill pill images for every drug in the collection.

Resolution order, per NDC, via app.pill_image_service:
  1. NLM Pillbox  (in-memory manifest lookup; no network per NDC)
  2. DailyMed SPL Principal Display Panel (LOINC 51945-4) as fallback

Persisted fields:
  pill_image_url, pill_image_source ('pillbox' | 'dailymed_pdp'),
  pill_image_source_ndc, label_images, label_images_source_setid,
  label_images_last_fetched.

Usage:
    python -m etl.dailymed_images                # incremental
    python -m etl.dailymed_images --force        # refetch all
    python -m etl.dailymed_images --ndc 0006-0078
    python -m etl.dailymed_images --drug-id <id>
    python -m etl.dailymed_images --limit 50
"""
import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.drug_database_manager import drug_db_manager
from app.pill_image_service import pill_image_service

logger = logging.getLogger(__name__)

REFRESH_AFTER = timedelta(days=30)


async def update_one(client: httpx.AsyncClient, drug: dict) -> str:
    """Resolve and persist a pill image for one drug. Returns a status string."""
    ndcs = drug.get("ndc_codes") or []
    if not ndcs:
        return "skip:no-ndc"

    hit = await pill_image_service.resolve(ndcs, client=client)
    if hit is None:
        await drug_db_manager.update_drug(drug["drug_id"], {
            "pill_image_url": None,
            "pill_image_source": None,
            "pill_image_source_ndc": None,
            "label_images": [],
            "label_images_source_setid": None,
            "label_images_last_fetched": datetime.now(timezone.utc),
        })
        return "no-image"

    await drug_db_manager.update_drug(drug["drug_id"], {
        "pill_image_url": hit["url"],
        "pill_image_source": hit["source"],
        "pill_image_source_ndc": hit["ndc"],
        "label_images": hit["label_images"],
        "label_images_source_setid": hit["setid"],
        "label_images_last_fetched": datetime.now(timezone.utc),
    })
    return f"ok:{hit['source']}"


async def run(
    ndc: Optional[str] = None,
    drug_id: Optional[str] = None,
    limit: Optional[int] = None,
    force: bool = False,
):
    await drug_db_manager.initialize()

    query: dict = {"ndc_codes.0": {"$exists": True}}
    if drug_id:
        query = {"drug_id": drug_id}
    elif ndc:
        query = {"ndc_codes": ndc}
    elif not force:
        cutoff = datetime.now(timezone.utc) - REFRESH_AFTER
        query["$or"] = [
            {"label_images_last_fetched": {"$exists": False}},
            {"label_images_last_fetched": {"$lt": cutoff}},
        ]

    cursor = drug_db_manager.drugs_collection.find(
        query,
        {"drug_id": 1, "ndc_codes": 1, "name": 1},
    )
    if limit:
        cursor = cursor.limit(limit)

    drugs = await cursor.to_list(length=None)
    print(f"📥 Resolving pill images for {len(drugs)} drugs (Pillbox → DailyMed)...", flush=True)

    counts: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, drug in enumerate(drugs, 1):
            try:
                status = await update_one(client, drug)
            except httpx.HTTPError as e:
                logger.warning(f"Image fetch failed for {drug.get('name')} (ndcs={drug.get('ndc_codes', [])[:3]}): {e}")
                status = "error"
            counts[status] = counts.get(status, 0) + 1
            if i % 25 == 0:
                print(f"  {i}/{len(drugs)}  {counts}", flush=True)

    print(f"✅ Pill image ETL complete: {counts}")
    return counts


def main():
    p = argparse.ArgumentParser(description="Backfill pill images (Pillbox → DailyMed PDP).")
    p.add_argument("--ndc", help="Process all drugs whose ndc_codes contains this NDC.")
    p.add_argument("--drug-id", help="Process a single drug by drug_id.")
    p.add_argument("--limit", type=int, help="Cap the number of drugs processed.")
    p.add_argument("--force", action="store_true", help="Refetch even if recently updated.")
    args = p.parse_args()
    asyncio.run(run(ndc=args.ndc, drug_id=args.drug_id, limit=args.limit, force=args.force))


if __name__ == "__main__":
    main()
