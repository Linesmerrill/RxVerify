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
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
    """
    Return all valid dashed NDC11 forms a `packaging.package_ndc` field might hold.

    openFDA preserves whichever 10-digit grouping (4-4-2, 5-3-2, 5-4-1) the labeler
    originally registered, so a 5-4-2 input must fan out to every form that could
    have been zero-padded into it.
    """
    if not normalized or normalized.count("-") != 2:
        return [normalized] if normalized else []
    a, b, c = normalized.split("-")
    if (len(a), len(b), len(c)) != (5, 4, 2):
        return [normalized]
    candidates = {f"{a}-{b}-{c}"}
    a_strip = a[1:] if a.startswith("0") else None
    b_strip = b[1:] if b.startswith("0") else None
    c_strip = c[1:] if c.startswith("0") else None
    if a_strip:
        candidates.add(f"{a_strip}-{b}-{c}")
    if b_strip:
        candidates.add(f"{a}-{b_strip}-{c}")
    if c_strip:
        candidates.add(f"{a}-{b}-{c_strip}")
    return list(candidates)


def _candidate_product_ndcs(normalized: str) -> List[str]:
    """Return labeler-product (NDC9/10) candidates for openFDA `product_ndc` searches."""
    if not normalized or normalized.count("-") != 2:
        return []
    a, b, _ = normalized.split("-")
    if (len(a), len(b)) != (5, 4):
        return [f"{a}-{b}"]
    candidates = {f"{a}-{b}"}
    if a.startswith("0"):
        candidates.add(f"{a[1:]}-{b}")
    if b.startswith("0"):
        candidates.add(f"{a}-{b[1:]}")
    return list(candidates)


def _shape_local_result(
    doc: Dict[str, Any],
    ndc: str,
    matched_dosage: Optional[Tuple[str, str]] = None,
) -> Dict[str, Any]:
    """Convert a local Mongo drug doc into the same shape /drugs/search returns.

    When `matched_dosage` is provided, narrow `dosages` to just that form/strength
    so an NDC-driven response surfaces the specific package dose instead of every
    strength the drug ships in.
    """
    if matched_dosage:
        form, strength = matched_dosage
        dosages: Any = {form: [strength]}
    else:
        dosages = doc.get("dosages", {}) or {}
    return {
        "drug_id": doc.get("drug_id") or str(doc.get("_id", "")),
        "name": doc.get("name") or doc.get("generic_name") or "",
        "generic_name": doc.get("generic_name", ""),
        "brand_names": doc.get("brand_names", []) or [],
        "common_uses": doc.get("common_uses", []) or [],
        "dosages": dosages,
        "drug_class": doc.get("drug_class", ""),
        "source": "local_database",
        "rxcui": doc.get("rxnorm_id") or doc.get("rxcui"),
        "url": "",
        "manufacturer": doc.get("manufacturer", ""),
        "ndc": ndc,
        "match_type": "ndc_exact",
        "relevance_score": 1.0,
    }


def _shape_openfda_result(
    item: Dict[str, Any],
    ndc: str,
    matched_dosage: Optional[Tuple[str, str]] = None,
) -> Dict[str, Any]:
    """Convert an openFDA /drug/ndc.json record into our standard search-result shape."""
    openfda = item.get("openfda") or {}
    brand_names = item.get("brand_name") or openfda.get("brand_name") or []
    if isinstance(brand_names, str):
        brand_names = [brand_names]
    # Unbranded generics list brand_name == generic_name in openFDA — drop those
    # so the UI doesn't show "Brands: Lisinopril" for plain Lisinopril.
    generic_lower = (item.get("generic_name") or "").strip().lower()
    brand_names = [
        b for b in brand_names
        if b and b.strip().lower() != generic_lower
    ]
    rxcuis = openfda.get("rxcui") or []
    primary_rxcui = rxcuis[0] if rxcuis else None

    pharm_class = (
        openfda.get("pharm_class_epc")
        or openfda.get("pharm_class_moa")
        or openfda.get("pharm_class_cs")
        or openfda.get("pharm_class_pe")
        or []
    )
    drug_class = pharm_class[0] if pharm_class else ""

    if matched_dosage:
        form, strength = matched_dosage
        dosages: Any = {form: [strength]}
    elif item.get("dosage_form"):
        form_key = item["dosage_form"].split(",")[0].strip().split()[0].lower()
        dosages = {form_key: []}
    else:
        dosages = {}

    return {
        "drug_id": f"openfda:{item.get('product_ndc', ndc)}",
        "name": (brand_names[0] if brand_names else None) or item.get("generic_name") or "",
        "generic_name": item.get("generic_name", ""),
        "brand_names": brand_names,
        "common_uses": [],
        "dosages": dosages,
        "drug_class": drug_class,
        "source": "openfda",
        "rxcui": primary_rxcui,
        "all_rxcuis": rxcuis,
        "url": "",
        "manufacturer": item.get("labeler_name", ""),
        "ndc": ndc or item.get("product_ndc"),
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
                {"ndc_codes": {"$in": candidates}},
                {"product_ndcs": {"$in": candidates}},
                {"package_ndcs": {"$in": candidates}},
            ]}
        )
        if doc:
            matched_ndc = next(
                (c for c in candidates if c in (doc.get("ndc_codes") or [])
                 or c in (doc.get("product_ndcs") or [])
                 or c in (doc.get("package_ndcs") or [])
                 or c == doc.get("ndc")),
                ndc,
            )
            ndc_dosages = doc.get("ndc_dosages") or {}
            entry = ndc_dosages.get(matched_ndc) or {}
            matched_dosage = None
            if entry.get("form") and entry.get("strength"):
                matched_dosage = (entry["form"], entry["strength"])
            return _shape_local_result(doc, matched_ndc, matched_dosage)
    except Exception as e:
        logger.warning(f"Local NDC lookup failed for {ndc}: {e}")
    return None


async def _query_openfda(search_expr: str) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                OPENFDA_NDC_URL,
                params={"search": search_expr, "limit": 1},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"openFDA NDC lookup HTTP error: {e}")
        return None
    except Exception as e:
        logger.warning(f"openFDA NDC lookup failed: {e}")
        return None
    results = data.get("results") or []
    return results[0] if results else None


async def _lookup_openfda_raw(ndc: str) -> Optional[Dict[str, Any]]:
    """Return the raw openFDA NDC record for a normalized NDC, or None."""
    pkg_candidates = _candidate_ndcs(ndc)
    # openFDA stores package_ndc in its original 10-digit grouping with the
    # package code appended — match that field directly.
    pkg_expr = " OR ".join(f'packaging.package_ndc:"{c}"' for c in pkg_candidates)
    item = await _query_openfda(pkg_expr)

    # Fall back to product_ndc (labeler-product only) for inputs that don't
    # disambiguate to a package row.
    if item is None:
        prod_candidates = _candidate_product_ndcs(ndc)
        if prod_candidates:
            prod_expr = " OR ".join(f'product_ndc:"{c}"' for c in prod_candidates)
            item = await _query_openfda(prod_expr)
    return item


async def _lookup_openfda(ndc: str) -> Optional[Dict[str, Any]]:
    item = await _lookup_openfda_raw(ndc)
    if item is None:
        return None
    return _shape_openfda_result(item, ndc)


def _extract_dosage(item: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Pull (form_key, strength) from an openFDA NDC record.

    `dosage_form` like "CAPSULE, DELAYED RELEASE" is reduced to its first token
    ("capsule") to match the keys the local `dosages` dict already uses. Multi-
    ingredient strengths (combination products) are joined with " / ".
    """
    form_raw = (item.get("dosage_form") or "").strip()
    if not form_raw:
        return None
    form_key = form_raw.split(",")[0].strip().split()[0].lower()
    if not form_key:
        return None
    strengths: List[str] = []
    for ing in item.get("active_ingredients") or []:
        s = (ing.get("strength") or "").strip()
        if not s:
            continue
        # openFDA encodes per-unit denominators ("40 mg/1") that we don't display.
        if s.endswith("/1"):
            s = s[:-2].strip()
        strengths.append(s)
    if not strengths:
        return None
    return form_key, " / ".join(strengths)


async def _match_existing_drug(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find an existing drugs-collection doc that this openFDA record describes.

    Priority: rxnorm_id (most reliable), then generic_name, then any brand name.
    """
    if drug_db_manager is None or getattr(drug_db_manager, "drugs_collection", None) is None:
        return None
    coll = drug_db_manager.drugs_collection
    openfda = item.get("openfda") or {}
    rxcuis = [r for r in (openfda.get("rxcui") or []) if r]
    generic = (item.get("generic_name") or "").strip()
    brands_raw = item.get("brand_name") or openfda.get("brand_name") or []
    if isinstance(brands_raw, str):
        brands_raw = [brands_raw]
    brands = [b for b in brands_raw if b]

    if rxcuis:
        doc = await coll.find_one({"rxnorm_id": {"$in": rxcuis}})
        if doc:
            return doc
    if generic:
        pattern = re.compile(f"^{re.escape(generic)}$", re.IGNORECASE)
        doc = await coll.find_one({"$or": [
            {"name": pattern}, {"generic_name": pattern}
        ]})
        if doc:
            return doc
    for b in brands:
        pattern = re.compile(f"^{re.escape(b)}$", re.IGNORECASE)
        doc = await coll.find_one({"$or": [
            {"brand_names": pattern}, {"name": pattern}
        ]})
        if doc:
            return doc
    return None


async def _enrich_existing_drug(
    doc: Dict[str, Any], item: Dict[str, Any], package_ndc: str
) -> Dict[str, Any]:
    """Merge openFDA data into an existing drugs-collection doc and return it."""
    coll = drug_db_manager.drugs_collection
    openfda = item.get("openfda") or {}
    rxcuis = [r for r in (openfda.get("rxcui") or []) if r]
    brands_raw = item.get("brand_name") or openfda.get("brand_name") or []
    if isinstance(brands_raw, str):
        brands_raw = [brands_raw]
    brands = [b for b in brands_raw if b]
    pharm_class = (
        openfda.get("pharm_class_epc")
        or openfda.get("pharm_class_moa")
        or openfda.get("pharm_class_cs")
        or []
    )
    drug_class = pharm_class[0] if pharm_class else ""
    manufacturer = item.get("labeler_name", "")

    update_set: Dict[str, Any] = {"last_updated": datetime.utcnow()}
    if not doc.get("manufacturer") and manufacturer:
        update_set["manufacturer"] = manufacturer
    if not doc.get("drug_class") and drug_class:
        update_set["drug_class"] = drug_class
    if not doc.get("rxnorm_id") and rxcuis:
        update_set["rxnorm_id"] = rxcuis[0]

    add_to_set: Dict[str, Any] = {}
    if package_ndc:
        add_to_set["ndc_codes"] = package_ndc
    name_l = (doc.get("name") or "").lower()
    generic_l = (doc.get("generic_name") or "").lower()
    new_brands = [b for b in brands if b.lower() not in (name_l, generic_l)]
    if new_brands:
        add_to_set["brand_names"] = {"$each": new_brands}
    dosage_pair = _extract_dosage(item)
    if dosage_pair:
        form_key, strength = dosage_pair
        add_to_set[f"dosages.{form_key}"] = strength
        if package_ndc:
            update_set[f"ndc_dosages.{package_ndc}"] = {
                "form": form_key,
                "strength": strength,
            }

    update_ops: Dict[str, Any] = {"$set": update_set}
    if add_to_set:
        update_ops["$addToSet"] = add_to_set
    try:
        await coll.update_one({"_id": doc["_id"]}, update_ops)
        refreshed = await coll.find_one({"_id": doc["_id"]})
        return refreshed or doc
    except Exception as e:
        logger.warning(f"Failed to enrich drug {doc.get('drug_id')} from openFDA: {e}")
        return doc


async def lookup_by_ndc(raw: str) -> Optional[Dict[str, Any]]:
    """Look up a single NDC. Returns one search-result-shaped dict, or None."""
    normalized = normalize_ndc(raw)
    if not normalized:
        return None

    local = await _lookup_local(normalized)
    if local:
        return local

    item = await _lookup_openfda_raw(normalized)
    if item is None:
        return None

    package_ndc = next(
        (c for c in _candidate_ndcs(normalized)
         if any(c == p.get("package_ndc") for p in item.get("packaging") or [])),
        normalized,
    )
    matched_dosage = _extract_dosage(item)

    existing = await _match_existing_drug(item)
    if existing is not None:
        enriched = await _enrich_existing_drug(existing, item, package_ndc)
        return _shape_local_result(enriched, package_ndc, matched_dosage)

    return _shape_openfda_result(item, package_ndc, matched_dosage)
