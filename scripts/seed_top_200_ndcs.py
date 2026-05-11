#!/usr/bin/env python3
"""
Seed the deployed RxVerify backend with NDCs for the top-200 drugs.

For each unique generic name in the hardcoded top-200 list (reused from
`scripts/upvote_top_200_drugs.py`), this:

1. Pulls up to N distinct openFDA NDC records via `generic_name:"<name>"`.
2. Picks one `package_ndc` per record (different labelers/strengths → different
   pill images).
3. POSTs each NDC to the deployed `/drugs/lookup/ndc?ndc=<NDC>` endpoint so the
   backend can enrich its local drug docs and lazily resolve pill images.

Usage:
    python3 scripts/seed_top_200_ndcs.py
    python3 scripts/seed_top_200_ndcs.py --api-url https://rx-verify-api-...
    python3 scripts/seed_top_200_ndcs.py --per-drug 10 --max-workers 5
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

# Allow `from scripts.upvote_top_200_drugs import ...` when run from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.upvote_top_200_drugs import get_hardcoded_drug_list  # noqa: E402

DEFAULT_API_URL = "https://rx-verify-api-e68bdd74c056.herokuapp.com"
OPENFDA_NDC_URL = "https://api.fda.gov/drug/ndc.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 RxVerify-Seed/1.0"
)


def http_get_json(url: str, timeout: int = 30):
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_openfda_ndcs(generic: str, per_drug: int, api_key: str = "") -> list:
    """Return up to `per_drug` distinct package_ndcs across openFDA records
    matching `generic_name:"<generic>"`. Prefers one NDC per labeler so the
    sample spans manufacturers (and thus more potential pill images)."""
    params = {
        "search": f'generic_name:"{generic}"',
        "limit": max(per_drug, 1),
    }
    if api_key:
        params["api_key"] = api_key
    url = f"{OPENFDA_NDC_URL}?{urlencode(params, quote_via=quote)}"
    try:
        data = http_get_json(url, timeout=15)
    except HTTPError as e:
        if e.code == 404:
            return []
        print(f"  openFDA HTTP {e.code} for '{generic}': {e.reason}")
        return []
    except URLError as e:
        print(f"  openFDA URL error for '{generic}': {e}")
        return []
    except Exception as e:
        print(f"  openFDA error for '{generic}': {e}")
        return []

    out: list = []
    seen_labeler = set()
    leftovers: list = []
    for item in data.get("results", []):
        labeler = (item.get("labeler_name") or "").strip().lower()
        packagings = item.get("packaging") or []
        pkg = next(
            (p.get("package_ndc") for p in packagings if p.get("package_ndc")),
            None,
        )
        if not pkg:
            pkg = item.get("product_ndc")
        if not pkg:
            continue
        entry = {
            "ndc": pkg,
            "labeler": item.get("labeler_name") or "",
            "brand": item.get("brand_name") or "",
            "form": item.get("dosage_form") or "",
        }
        if labeler and labeler in seen_labeler:
            leftovers.append(entry)
            continue
        seen_labeler.add(labeler)
        out.append(entry)
        if len(out) >= per_drug:
            break
    # Pad with same-labeler results if we didn't reach per_drug.
    for entry in leftovers:
        if len(out) >= per_drug:
            break
        out.append(entry)
    return out


def post_ndc_lookup(api_url: str, ndc: str) -> dict:
    """Hit deployed /drugs/lookup/ndc and return a small outcome summary."""
    url = f"{api_url}/drugs/lookup/ndc?{urlencode({'ndc': ndc})}"
    try:
        data = http_get_json(url, timeout=30)
    except HTTPError as e:
        return {"ndc": ndc, "ok": False, "error": f"HTTP {e.code} {e.reason}"}
    except URLError as e:
        return {"ndc": ndc, "ok": False, "error": f"URL error: {e}"}
    except Exception as e:
        return {"ndc": ndc, "ok": False, "error": str(e)}

    result = data.get("result") or {}
    return {
        "ndc": ndc,
        "ok": data.get("found", False),
        "name": result.get("name"),
        "source": result.get("source"),
        "drug_id": result.get("drug_id"),
        "has_pill_image": bool(result.get("pill_image_url")),
        "pill_image_source": result.get("pill_image_source"),
    }


def test_api(api_url: str) -> bool:
    try:
        http_get_json(f"{api_url}/health", timeout=10)
        return True
    except Exception as e:
        print(f"WARNING: cannot reach {api_url}: {e}")
        return False


def unique_generics_with_brand() -> list:
    """Return [(generic_name, sample_brand_name_or_empty), ...] from top 200."""
    seen: dict = {}
    for drug in get_hardcoded_drug_list():
        g = (drug.get("generic") or "").strip()
        if not g:
            continue
        if g not in seen:
            seen[g] = drug.get("brand") or ""
    return [(g, b) for g, b in seen.items()]


def process_drug(api_url: str, generic: str, brand: str, per_drug: int,
                 api_key: str, stats_lock: Lock, stats: dict, throttle: float):
    discovered = fetch_openfda_ndcs(generic, per_drug, api_key=api_key)
    if not discovered:
        with stats_lock:
            stats["drugs_no_openfda"].append(generic)
        return {
            "generic": generic, "brand": brand, "discovered": 0,
            "lookups": [],
        }

    lookups = []
    for entry in discovered:
        res = post_ndc_lookup(api_url, entry["ndc"])
        res["openfda"] = entry
        lookups.append(res)
        with stats_lock:
            if res.get("ok"):
                stats["lookups_found"] += 1
                src = res.get("source") or "unknown"
                stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
                if res.get("has_pill_image"):
                    stats["with_pill_image"] += 1
            else:
                stats["lookups_missing"] += 1
        if throttle > 0:
            time.sleep(throttle)
    return {
        "generic": generic,
        "brand": brand,
        "discovered": len(discovered),
        "lookups": lookups,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help=f"Deployed RxVerify base URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--per-drug", type=int, default=10,
                        help="Max NDCs to seed per generic name (default: 10)")
    parser.add_argument("--max-workers", type=int, default=5,
                        help="Parallel drug workers (default: 5)")
    parser.add_argument("--throttle", type=float, default=0.05,
                        help="Per-NDC sleep within a worker, seconds (default: 0.05)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after this many generics (0 = all). Useful for dry-runs.")
    parser.add_argument("--openfda-api-key", default=os.getenv("OPENFDA_API_KEY", ""),
                        help="Optional openFDA API key (or set OPENFDA_API_KEY env)")
    parser.add_argument("--dump", default="",
                        help="Optional path to dump full per-drug results as JSON")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    print("=" * 60)
    print("Top 200 NDC Seeder")
    print("=" * 60)
    print(f"API URL:        {api_url}")
    print(f"NDCs per drug:  {args.per_drug}")
    print(f"Workers:        {args.max_workers}")
    print(f"openFDA key:    {'yes' if args.openfda_api_key else 'no'}")
    print()

    if not test_api(api_url):
        return 1
    print("OK: API reachable\n")

    drugs = unique_generics_with_brand()
    if args.limit > 0:
        drugs = drugs[:args.limit]
    print(f"Processing {len(drugs)} unique generic names\n")

    stats = {
        "lookups_found": 0,
        "lookups_missing": 0,
        "with_pill_image": 0,
        "by_source": {},
        "drugs_no_openfda": [],
    }
    stats_lock = Lock()
    all_results = []

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        fut_map = {
            ex.submit(
                process_drug, api_url, g, b, args.per_drug,
                args.openfda_api_key, stats_lock, stats, args.throttle,
            ): g
            for g, b in drugs
        }
        done = 0
        for fut in as_completed(fut_map):
            done += 1
            g = fut_map[fut]
            try:
                r = fut.result()
            except Exception as e:
                print(f"[{done}/{len(drugs)}] {g}: ERROR {e}")
                continue
            ok = sum(1 for x in r["lookups"] if x.get("ok"))
            img = sum(1 for x in r["lookups"] if x.get("has_pill_image"))
            msg = (
                f"discovered={r['discovered']:2d} "
                f"found={ok:2d} images={img:2d}"
            )
            if r["discovered"] == 0:
                msg = "no openFDA NDCs"
            print(f"[{done}/{len(drugs)}] {g}: {msg}")
            all_results.append(r)

    elapsed = time.time() - started
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Drugs processed:       {len(drugs)}")
    print(f"Drugs w/ no openFDA:   {len(stats['drugs_no_openfda'])}")
    total_calls = stats["lookups_found"] + stats["lookups_missing"]
    print(f"NDC lookups issued:    {total_calls}")
    print(f"  found:               {stats['lookups_found']}")
    print(f"  missing/errored:     {stats['lookups_missing']}")
    print(f"  with pill image:     {stats['with_pill_image']}")
    if stats["by_source"]:
        print("  by source:")
        for src, n in sorted(stats["by_source"].items(), key=lambda x: -x[1]):
            print(f"    {src}: {n}")
    if stats["drugs_no_openfda"]:
        sample = ", ".join(stats["drugs_no_openfda"][:10])
        more = f" (+{len(stats['drugs_no_openfda']) - 10} more)" if len(stats["drugs_no_openfda"]) > 10 else ""
        print(f"\n  Drugs with no openFDA matches: {sample}{more}")
    print(f"\nElapsed: {elapsed:.1f}s")

    if args.dump:
        with open(args.dump, "w") as f:
            json.dump(
                {"stats": stats, "results": all_results},
                f, indent=2, default=str,
            )
        print(f"\nFull per-drug results written to {args.dump}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
