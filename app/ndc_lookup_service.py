"""
NDC lookup service.

Accepts NDC codes in any common format (10-digit dashed, 11-digit dashed, or
undashed digits, including UPC-A barcodes that prepend a leading "3"), normalizes
them to the 11-digit (5-4-2) form used by openFDA, and looks up the matching
product. Tries the local Mongo `drugs` collection first, then falls back to the
live openFDA NDC directory.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.drug_database_manager import drug_db_manager

logger = logging.getLogger(__name__)

OPENFDA_NDC_URL = "https://api.fda.gov/drug/ndc.json"

# Recognizes common NDC shapes the user might type or paste.
# Examples: "0093-1024-01", "00093-1024-01", "00093102401", "0093102401"
_NDC_TYPED_RE = re.compile(r"^\s*\d{4,5}-?\d{3,4}-?\d{1,2}\s*$")

# A pure 10–14 digit run from a barcode (UPC-A=12, EAN-13=13, GTIN-14=14).
_BARCODE_RE = re.compile(r"^\s*\d{10,14}\s*$")


def looks_like_ndc(query: str) -> bool:
    """Return True if `query` plausibly identifies an NDC."""
    if not query:
        return False
    q = query.strip()
    return bool(_NDC_TYPED_RE.match(q) or _BARCODE_RE.match(q))


def normalize_ndc(raw: str) -> Optional[str]:
    """
    Normalize an NDC-ish string to the 11-digit dashed (5-4-2) form openFDA
    indexes on. Returns None if the input cannot be interpreted.

    Handles:
      - 10-digit dashed (4-4-2, 5-3-2, 5-4-1) — pads to 5-4-2 by inserting a
        leading 0 in the segment that is short by one
      - 11-digit dashed/undashed
      - UPC-A barcode (12 digits leading "3" + NDC10 + check digit)
      - GTIN-14 (14 digits, leading "0030" or "003" then NDC10 + check digit)
    """
    if not raw:
        return None
    s = raw.strip()

    # If dashed, preserve segment widths so we know which part to pad.
    if "-" in s:
        parts = s.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return None
        a, b, c = parts
        widths = (len(a), len(b), len(c))
        if widths == (5, 4, 2):
            return f"{a}-{b}-{c}"
        if widths == (4, 4, 2):
            return f"0{a}-{b}-{c}"
        if widths == (5, 3, 2):
            return f"{a}-0{b}-{c}"
        if widths == (5, 4, 1):
            return f"{a}-{b}-0{c}"
        return None

    # Undashed: digits only.
    if not s.isdigit():
        return None

    digits = s

    # UPC-A: 12 digits, leading "3" indicates Rx; strip leader and check digit.
    if len(digits) == 12 and digits[0] == "3":
        digits = digits[1:11]  # 10-digit NDC core
    # GTIN-14 packaged for Rx: leading "00" + 12-digit UPC-A.
    elif len(digits) == 14 and digits[:3] == "003":
        digits = digits[3:13]
    elif len(digits) == 13:
        # EAN-13 fallback: strip leading 0 + check digit if it fits the UPC-A pattern.
        if digits[0] == "0" and digits[1] == "3":
            digits = digits[2:12]

    # At this point digits should be 10 or 11 long.
    if len(digits) == 11:
        return f"{digits[0:5]}-{digits[5:9]}-{digits[9:11]}"
    if len(digits) == 10:
        # Try the three valid 10-digit groupings, padding the short segment.
        # 4-4-2: pad labeler
        return f"0{digits[0:4]}-{digits[4:8]}-{digits[8:10]}"

    return None


def _candidate_ndcs(normalized: str) -> List[str]:
    """Return search candidates for openFDA — both 11-digit dashed and bare 10-digit forms."""
    if not normalized:
        return []
    parts = normalized.split("-")
    candidates = {normalized}
    if len(parts) == 3 and parts[0].startswith("0") and len(parts[0]) == 5:
        # Also try the original 4-4-2 form
        candidates.add(f"{parts[0][1:]}-{parts[1]}-{parts[2]}")
    return list(candidates)


def _shape_local_result(doc: Dict[str, Any], ndc: str) -> Dict[str, Any]:
    """Convert a local Mongo drug doc into the same shape /drugs/search returns."""
    return {
        "drug_id": doc.get("drug_id") or str(doc.get("_id", "")),
        "name": doc.get("name") or doc.get("generic_name") or "",
        "generic_name": doc.get("generic_name", ""),
        "brand_names": doc.get("brand_names", []) or [],
        "common_uses": doc.get("common_uses", []) or [],
        "dosages": doc.get("dosages", []) or [],
        "drug_class": doc.get("drug_class", ""),
        "source": "local_database",
        "rxcui": doc.get("rxnorm_id") or doc.get("rxcui"),
        "url": "",
        "manufacturer": doc.get("manufacturer", ""),
        "ndc": ndc,
        "match_type": "ndc_exact",
        "relevance_score": 1.0,
    }


def _shape_openfda_result(item: Dict[str, Any], ndc: str) -> Dict[str, Any]:
    """Convert an openFDA /drug/ndc.json record into our standard search-result shape."""
    openfda = item.get("openfda") or {}
    brand_names = item.get("brand_name") or openfda.get("brand_name") or []
    if isinstance(brand_names, str):
        brand_names = [brand_names]
    rxcuis = openfda.get("rxcui") or []
    primary_rxcui = rxcuis[0] if rxcuis else None

    pharm_class = (
        openfda.get("pharm_class_epc")
        or openfda.get("pharm_class_moa")
        or openfda.get("pharm_class_cs")
        or []
    )
    drug_class = pharm_class[0] if pharm_class else ""

    return {
        "drug_id": f"openfda:{item.get('product_ndc', ndc)}",
        "name": (brand_names[0] if brand_names else None) or item.get("generic_name") or "",
        "generic_name": item.get("generic_name", ""),
        "brand_names": brand_names,
        "common_uses": [],
        "dosages": [item.get("dosage_form")] if item.get("dosage_form") else [],
        "drug_class": drug_class,
        "source": "openfda",
        "rxcui": primary_rxcui,
        "all_rxcuis": rxcuis,
        "url": "",
        "manufacturer": item.get("labeler_name", ""),
        "ndc": item.get("product_ndc") or ndc,
        "match_type": "ndc_exact",
        "relevance_score": 1.0,
    }


async def _lookup_local(ndc: str) -> Optional[Dict[str, Any]]:
    """Look up an NDC in the local Mongo drugs collection, if available."""
    try:
        if drug_db_manager is None or getattr(drug_db_manager, "drugs_collection", None) is None:
            return None
        candidates = _candidate_ndcs(ndc)
        doc = await drug_db_manager.drugs_collection.find_one(
            {"$or": [
                {"ndc": {"$in": candidates}},
                {"product_ndcs": {"$in": candidates}},
                {"package_ndcs": {"$in": candidates}},
            ]}
        )
        if doc:
            return _shape_local_result(doc, ndc)
    except Exception as e:
        logger.warning(f"Local NDC lookup failed for {ndc}: {e}")
    return None


async def _lookup_openfda(ndc: str) -> Optional[Dict[str, Any]]:
    """Look up an NDC against the live openFDA NDC directory."""
    candidates = _candidate_ndcs(ndc)
    # openFDA accepts product_ndc with the dashed 5-4-2 or 4-4-2 form.
    search_expr = " ".join(f'product_ndc:"{c}"' for c in candidates)
    if len(candidates) > 1:
        search_expr = "+OR+".join(f'product_ndc:"{c}"' for c in candidates)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                OPENFDA_NDC_URL,
                params={"search": search_expr, "limit": 1},
            )
            if resp.status_code == 404:
                return None  # No match, openFDA returns 404 for empty results
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"openFDA NDC lookup HTTP error for {ndc}: {e}")
        return None
    except Exception as e:
        logger.warning(f"openFDA NDC lookup failed for {ndc}: {e}")
        return None

    results = data.get("results") or []
    if not results:
        return None
    return _shape_openfda_result(results[0], ndc)


async def _persist_openfda_to_local(result: Dict[str, Any]) -> None:
    """Best-effort cache an openFDA hit into Mongo so future scans hit local first."""
    try:
        if drug_db_manager is None or getattr(drug_db_manager, "drugs_collection", None) is None:
            return
        ndc = result.get("ndc")
        if not ndc:
            return
        await drug_db_manager.drugs_collection.update_one(
            {"drug_id": result["drug_id"]},
            {"$setOnInsert": {
                "drug_id": result["drug_id"],
                "name": result["name"],
                "generic_name": result.get("generic_name", ""),
                "brand_names": result.get("brand_names", []),
                "drug_class": result.get("drug_class", ""),
                "rxnorm_id": result.get("rxcui"),
                "manufacturer": result.get("manufacturer", ""),
                "source": "openfda",
            },
             "$addToSet": {"product_ndcs": ndc}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"Skip caching openFDA NDC result: {e}")


async def lookup_by_ndc(raw: str) -> Optional[Dict[str, Any]]:
    """Look up a single NDC. Returns one search-result-shaped dict, or None."""
    normalized = normalize_ndc(raw)
    if not normalized:
        return None

    local = await _lookup_local(normalized)
    if local:
        return local

    remote = await _lookup_openfda(normalized)
    if remote:
        await _persist_openfda_to_local(remote)
    return remote
