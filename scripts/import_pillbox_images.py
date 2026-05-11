"""Import NLM Pillbox pill images into the Med-Madness/pill-images GitHub repo.

Pipeline:
  1. Read NLM Pillbox CSV → build (normalized NDC9 → splimage) lookup
  2. Query the local drugs collection for every unique NDC currently stored
  3. For each NDC found in Pillbox, extract its image from the cached zip
     and write it to the image repo at images/{labeler5}/{ndc9}.jpg
  4. Update manifest.json keyed by normalized NDC9
  5. Optionally git add / commit / push (requires --push)

Run a dry run first to see coverage and what will change. Pillbox is frozen
2018, so this script is a one-time backfill (re-run only when you add many
new NDCs to the drugs collection).

Usage:
    # Dry run — count matches, show what would change, don't write anything
    python -m scripts.import_pillbox_images --dry-run

    # Actually extract images and update manifest (no git push yet)
    python -m scripts.import_pillbox_images

    # Same plus commit and push the new images
    python -m scripts.import_pillbox_images --push
"""
import argparse
import asyncio
import csv
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from app.drug_database_manager import drug_db_manager

CACHE_DIR = Path.home() / ".cache" / "med-madness" / "pillbox"
PILLBOX_ZIP = CACHE_DIR / "pillbox_production_images_full_202008.zip"
PILLBOX_CSV = CACHE_DIR / "pillbox_master.csv"
PILLBOX_CSV_URL = "https://datadiscovery.nlm.nih.gov/api/views/crzr-uvwg/rows.csv?accessType=DOWNLOAD"

REPO_URL = "https://github.com/Med-Madness/pill-images.git"
REPO_DIR = Path("/Users/merrill/workspace/med-madness-applications/pill-images")
IMAGES_SUBDIR = REPO_DIR / "images"
MANIFEST_PATH = REPO_DIR / "manifest.json"


def normalize_ndc9(ndc: str) -> Optional[str]:
    """Convert hyphenated NDC (e.g. '0006-0078' or '31722-557') to Pillbox's
    9-digit zero-padded form ('000060078' / '317220557'). Returns None if the
    input doesn't have exactly two segments."""
    if not ndc or "-" not in ndc:
        return None
    parts = ndc.split("-")
    if len(parts) != 2:
        return None
    labeler, product = parts
    return labeler.zfill(5) + product.zfill(4)


def labeler_shard(ndc9: str) -> str:
    """First 5 chars of normalized NDC9 = labeler code."""
    return ndc9[:5]


def ensure_pillbox_csv() -> None:
    if PILLBOX_CSV.exists() and PILLBOX_CSV.stat().st_size > 0:
        return
    print(f"📥 Downloading Pillbox CSV → {PILLBOX_CSV}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    import urllib.request
    urllib.request.urlretrieve(PILLBOX_CSV_URL, PILLBOX_CSV)


def ensure_pillbox_zip() -> None:
    if not PILLBOX_ZIP.exists():
        raise SystemExit(
            f"Pillbox zip not found at {PILLBOX_ZIP}. "
            f"Download it once with:\n  curl -L 'https://ftp.nlm.nih.gov/projects/pillbox/"
            f"pillbox_production_images_full_202008.zip' -o '{PILLBOX_ZIP}'"
        )


def ensure_repo_clone() -> None:
    if (REPO_DIR / ".git").exists():
        return
    if REPO_DIR.exists() and any(REPO_DIR.iterdir()):
        raise SystemExit(f"{REPO_DIR} exists and is not empty but isn't a git repo. Aborting.")
    REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
    print(f"📦 Cloning {REPO_URL} → {REPO_DIR}")
    subprocess.run(["git", "clone", REPO_URL, str(REPO_DIR)], check=True)


def load_pillbox_lookup() -> dict[str, str]:
    """Build {normalized_ndc9: splimage} for every Pillbox row that has an image."""
    lookup: dict[str, str] = {}
    with PILLBOX_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("has_image") != "True":
                continue
            ndc9 = (row.get("ndc9") or "").strip()
            splimage = (row.get("splimage") or "").strip()
            if not ndc9 or not splimage:
                continue
            # ndc9 in the CSV is already normalized (no hyphen, zero-padded).
            # Last-write-wins on duplicates is fine — same NDC tends to point
            # to the same splimage across rows.
            lookup[ndc9] = splimage
    return lookup


async def collect_db_ndcs() -> set[str]:
    """Return every distinct, hyphenated NDC currently stored across all drugs."""
    await drug_db_manager.initialize()
    ndcs: set[str] = set()
    cursor = drug_db_manager.drugs_collection.find(
        {"ndc_codes.0": {"$exists": True}},
        {"ndc_codes": 1, "_id": 0},
    )
    async for doc in cursor:
        for n in doc.get("ndc_codes") or []:
            if n:
                ndcs.add(n.strip())
    return ndcs


def write_manifest(manifest: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"  (dry-run) manifest would have {len(manifest)} entries")
        return
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"📝 Wrote manifest with {len(manifest)} entries → {MANIFEST_PATH}")


def write_readme_if_missing(dry_run: bool) -> None:
    readme = REPO_DIR / "README.md"
    if readme.exists() or dry_run:
        return
    readme.write_text(
        "# pill-images\n\n"
        "Public-domain pill images mirrored from the NIH National Library of Medicine "
        "[Pillbox](https://datadiscovery.nlm.nih.gov/Chemicals-and-Drugs/Pillbox-Archived-Data/crzr-uvwg) "
        "dataset (frozen January 2021, retired program).\n\n"
        "## Layout\n\n"
        "Images are sharded by 5-digit FDA labeler code:\n\n"
        "```\n"
        "images/{labeler}/{ndc9}.jpg\n"
        "```\n\n"
        "where `ndc9` is the 9-digit National Drug Code zero-padded with no hyphen "
        "(e.g. `000060078` for NDC `0006-0078`). `manifest.json` maps every imported "
        "NDC to its relative image path.\n\n"
        "## URL pattern\n\n"
        "```\n"
        "https://raw.githubusercontent.com/Med-Madness/pill-images/main/images/{ndc9[:5]}/{ndc9}.jpg\n"
        "```\n\n"
        "## License\n\n"
        "Source data is U.S. federal government work and therefore in the public domain.\n"
    )


def git_commit_and_push(num_added: int, dry_run: bool) -> None:
    if dry_run:
        return
    subprocess.run(["git", "-C", str(REPO_DIR), "add", "-A"], check=True)
    status = subprocess.run(
        ["git", "-C", str(REPO_DIR), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    )
    if not status.stdout.strip():
        print("  No changes to commit.")
        return
    msg = f"Import {num_added} pill images from NLM Pillbox"
    subprocess.run(["git", "-C", str(REPO_DIR), "commit", "-m", msg], check=True)
    subprocess.run(["git", "-C", str(REPO_DIR), "push"], check=True)
    print("✅ Pushed to origin.")


async def main_async(dry_run: bool, push: bool, limit: Optional[int]) -> None:
    ensure_pillbox_csv()
    ensure_pillbox_zip()
    if not dry_run:
        ensure_repo_clone()
        IMAGES_SUBDIR.mkdir(parents=True, exist_ok=True)
        write_readme_if_missing(dry_run)

    print("🔎 Loading Pillbox manifest…", flush=True)
    pillbox = load_pillbox_lookup()
    print(f"  Pillbox has images for {len(pillbox)} NDCs.", flush=True)

    print("🔎 Collecting NDCs from drugs collection…", flush=True)
    db_ndcs = await collect_db_ndcs()
    print(f"  drugs collection references {len(db_ndcs)} distinct NDCs.", flush=True)

    # Match
    matched: dict[str, str] = {}  # ndc9 → splimage
    unmatched_count = 0
    for raw in db_ndcs:
        ndc9 = normalize_ndc9(raw)
        if not ndc9:
            unmatched_count += 1
            continue
        splimage = pillbox.get(ndc9)
        if splimage:
            matched[ndc9] = splimage
        else:
            unmatched_count += 1

    print(f"  ✅ {len(matched)} NDCs map to a Pillbox image  ({100*len(matched)//max(len(db_ndcs),1)}% coverage)")
    print(f"  ⚠ {unmatched_count} NDCs have no Pillbox match (will fall back to DailyMed PDP)")

    if limit and len(matched) > limit:
        keys = sorted(matched.keys())[:limit]
        matched = {k: matched[k] for k in keys}
        print(f"  Limiting to first {limit} for this run.")

    if not matched:
        print("Nothing to import.")
        return

    # Extract & write
    manifest: dict[str, str] = {}
    if MANIFEST_PATH.exists() and not dry_run:
        manifest = json.loads(MANIFEST_PATH.read_text())

    added = skipped = missing_in_zip = 0
    print(f"📂 Opening zip {PILLBOX_ZIP.name}…")
    with zipfile.ZipFile(PILLBOX_ZIP, "r") as zf:
        zip_names = set(zf.namelist())
        for ndc9, splimage in sorted(matched.items()):
            relpath = f"images/{labeler_shard(ndc9)}/{ndc9}.jpg"
            target = REPO_DIR / relpath
            if target.exists() and manifest.get(ndc9) == relpath:
                skipped += 1
                continue
            filename = f"{splimage}.jpg"
            if filename not in zip_names:
                missing_in_zip += 1
                continue
            data = zf.read(filename)
            if dry_run:
                added += 1
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                added += 1
            manifest[ndc9] = relpath

    print(f"  ➕ {added} images extracted  |  ↻ {skipped} unchanged  |  ❌ {missing_in_zip} missing in zip")

    write_manifest(manifest, dry_run)

    if push and not dry_run:
        git_commit_and_push(added, dry_run)
    elif not dry_run:
        print("ℹ Skipped git commit/push (use --push to commit and push).")


def main():
    p = argparse.ArgumentParser(description="Import NLM Pillbox pill images into the image repo.")
    p.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing.")
    p.add_argument("--push", action="store_true", help="After writing files, git commit and push.")
    p.add_argument("--limit", type=int, help="Cap how many images to extract (for testing).")
    args = p.parse_args()

    if args.push and args.dry_run:
        raise SystemExit("--push and --dry-run are mutually exclusive.")

    asyncio.run(main_async(dry_run=args.dry_run, push=args.push, limit=args.limit))


if __name__ == "__main__":
    main()
