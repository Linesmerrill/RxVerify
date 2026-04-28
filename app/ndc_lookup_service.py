"""
NDC lookup service.

Accepts NDC codes in any common format (10-digit dashed, 11-digit dashed, or
undashed digits, including UPC-A barcodes that prepend a leading "3"), normalizes
them to the 11-digit (5-4-2) form used by openFDA, and looks up the matching
product. Tries the local Mongo `drugs` collection first, then falls back to the
live openFDA NDC directory.
"""

import asyncio
import logging
import re
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

import httpx

from app.config import settings as app_settings
from app.drug_database_manager import drug_db_manager

logger = logging.getLogger(__name__)

OPENFDA_NDC_URL = "https://api.fda.gov/drug/ndc.json"


class _OpenFDARateLimiter:
    """Sliding-window limiter that keeps us safely under openFDA's published
    caps (240 requests/minute and 120,000/day per API key).

    Tracks request timestamps in two deques. Before issuing a request, evicts
    timestamps older than the window, then either lets the call through or
    sleeps until the oldest in-window timestamp ages out. An asyncio.Lock
    serializes the check so concurrent callers don't all squeak through on a
    single available slot.
    """

    def __init__(self, max_per_minute: int, max_per_day: int) -> None:
        self.max_per_minute = max_per_minute
        self.max_per_day = max_per_day
        self._minute: Deque[float] = deque()
        self._day: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._minute and now - self._minute[0] >= 60:
                    self._minute.popleft()
                while self._day and now - self._day[0] >= 86_400:
                    self._day.popleft()
                if (
                    len(self._minute) < self.max_per_minute
                    and len(self._day) < self.max_per_day
                ):
                    self._minute.append(now)
                    self._day.append(now)
                    return
                # Decide how long to wait for the most-binding window.
                wait_minute = 60 - (now - self._minute[0]) if len(self._minute) >= self.max_per_minute else 0
                wait_day = 86_400 - (now - self._day[0]) if len(self._day) >= self.max_per_day else 0
                wait = max(wait_minute, wait_day, 0.05)
            logger.warning(
                "openFDA rate limit hit (minute=%d/%d, day=%d/%d); sleeping %.2fs",
                len(self._minute), self.max_per_minute,
                len(self._day), self.max_per_day,
                wait,
            )
            await asyncio.sleep(wait)

    async def usage(self) -> Dict[str, Any]:
        """Snapshot current usage. Evicts stale timestamps so the counts
        reflect just what's still inside the rolling minute/day windows."""
        async with self._lock:
            now = time.monotonic()
            while self._minute and now - self._minute[0] >= 60:
                self._minute.popleft()
            while self._day and now - self._day[0] >= 86_400:
                self._day.popleft()
            minute_used = len(self._minute)
            day_used = len(self._day)
            oldest_minute = self._minute[0] if self._minute else None
            oldest_day = self._day[0] if self._day else None
            return {
                "minute": {
                    "used": minute_used,
                    "limit": self.max_per_minute,
                    "remaining": max(self.max_per_minute - minute_used, 0),
                    # Seconds until the oldest in-window request ages out and
                    # frees a slot. None when the window is empty.
                    "reset_in_seconds": (
                        round(60 - (now - oldest_minute), 2)
                        if oldest_minute is not None else None
                    ),
                },
                "day": {
                    "used": day_used,
                    "limit": self.max_per_day,
                    "remaining": max(self.max_per_day - day_used, 0),
                    "reset_in_seconds": (
                        round(86_400 - (now - oldest_day), 2)
                        if oldest_day is not None else None
                    ),
                },
            }


async def get_openfda_usage() -> Dict[str, Any]:
    """Public accessor so other modules don't need to reach into the limiter."""
    snap = await _rate_limiter.usage()
    snap["api_key_configured"] = bool(app_settings.OPENFDA_API_KEY)
    return snap


class _NdcStats:
    """Thin shim that delegates outcome counters to the analytics DB so
    metrics survive dyno restarts. Keeps a small in-memory mirror of the
    most recent event for fast last-event display when the DB is slow."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_event: Optional[Dict[str, Any]] = None

    async def record(self, outcome: str, *, raw: Optional[str] = None,
                     ndc: Optional[str] = None) -> None:
        async with self._lock:
            self._last_event = {
                "outcome": outcome,
                "raw": raw,
                "ndc": ndc,
                "at": datetime.utcnow().isoformat() + "Z",
            }
        try:
            from app.analytics_database import analytics_db_manager
            if analytics_db_manager is not None:
                await analytics_db_manager.record_ndc_lookup(outcome)
        except Exception as e:
            logger.warning(f"Failed to persist NDC lookup metric: {e}")

    async def last_event(self) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return dict(self._last_event) if self._last_event else None


_ndc_stats = _NdcStats()


async def get_ndc_stats(days: int = 30) -> Dict[str, Any]:
    """Return persisted NDC analytics + the most recent in-memory event."""
    from app.analytics_database import analytics_db_manager
    metrics: Dict[str, Any]
    if analytics_db_manager is not None:
        try:
            metrics = await analytics_db_manager.get_ndc_metrics(days=days)
        except Exception as e:
            logger.warning(f"Failed to read NDC metrics: {e}")
            metrics = {"all_time": {}, "daily": [], "ready": False}
    else:
        metrics = {"all_time": {}, "daily": [], "ready": False}
    metrics["last_event"] = await _ndc_stats.last_event()
    return metrics


_rate_limiter = _OpenFDARateLimiter(
    max_per_minute=app_settings.OPENFDA_MAX_PER_MINUTE,
    max_per_day=app_settings.OPENFDA_MAX_PER_DAY,
)

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


def _ten_digit_groupings(d: str) -> List[str]:
    """Return every 5-4-2 normalization of a 10-digit undashed NDC.

    A bare 10-digit NDC could have been registered in any of the three valid
    groupings (4-4-2, 5-3-2, 5-4-1). Return one normalization per grouping so
    a downstream openFDA query has a chance to hit the right one.
    """
    if len(d) != 10 or not d.isdigit():
        return []
    return [
        f"0{d[0:4]}-{d[4:8]}-{d[8:10]}",     # 4-4-2 → pad labeler
        f"{d[0:5]}-0{d[5:8]}-{d[8:10]}",     # 5-3-2 → pad product
        f"{d[0:5]}-{d[5:9]}-0{d[9:10]}",     # 5-4-1 → pad package
    ]


def normalize_ndc_candidates(raw: str) -> List[str]:
    """Return every plausible 5-4-2 normalization of `raw`.

    Dashed input is unambiguous → one candidate. Undashed digits are
    ambiguous because the labeler-product-package boundary depends on which
    grouping the FDA labeler originally registered, so we expand:

    - 10 digits → three candidates (one per valid grouping).
    - 11 digits → the literal 5-4-2 split, plus, for any `0` sitting at
      positions 0 / 5 / 9 (the three valid padding-insertion points), the
      three groupings of the un-padded 10-digit body. This recovers inputs
      where the padding zero is misaligned with the segment boundary the
      literal 5-4-2 split implies (e.g. `76282418300` → `76282-0418-30`).
    """
    if not raw:
        return []
    s = raw.strip()

    if "-" in s:
        single = normalize_ndc(s)
        return [single] if single else []

    if not s.isdigit():
        return []

    digits = s

    # Unwrap UPC-A / GTIN-14 / EAN-13 down to a 10-or-11-digit core.
    if len(digits) == 12 and digits[0] == "3":
        digits = digits[1:11]
    elif len(digits) == 14 and digits[:3] == "003":
        digits = digits[3:13]
    elif len(digits) == 13 and digits[0] == "0" and digits[1] == "3":
        digits = digits[2:12]

    out: List[str] = []
    if len(digits) == 10:
        out.extend(_ten_digit_groupings(digits))
    elif len(digits) == 11:
        out.append(f"{digits[0:5]}-{digits[5:9]}-{digits[9:11]}")
        if digits[0] == "0":
            out.extend(_ten_digit_groupings(digits[1:]))
        if digits[5] == "0":
            out.extend(_ten_digit_groupings(digits[:5] + digits[6:]))
        if digits[9] == "0":
            out.extend(_ten_digit_groupings(digits[:9] + digits[10:]))

    # Dedup, preserving order.
    seen = set()
    deduped: List[str] = []
    for n in out:
        if n and n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped


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
    params: Dict[str, Any] = {"search": search_expr, "limit": 1}
    if app_settings.OPENFDA_API_KEY:
        params["api_key"] = app_settings.OPENFDA_API_KEY
    try:
        await _rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(OPENFDA_NDC_URL, params=params)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                # openFDA itself rejected us — log loud and back off so the
                # next call doesn't burn another quota slot immediately.
                logger.error("openFDA returned 429; pausing to back off.")
                await asyncio.sleep(2.0)
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


def _title_ingredient(name: str) -> str:
    """Convert openFDA's UPPERCASE ingredient names to title case."""
    return (name or "").strip().title()


def _clean_strength(s: str) -> str:
    s = (s or "").strip()
    # openFDA encodes per-unit denominators ("40 mg/1") that we don't display.
    if s.endswith("/1"):
        s = s[:-2].strip()
    return s


def _extract_dosage(item: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Backwards-compatible (form, strength) pair. Combos return paired strengths
    joined by " / " (positionally aligned with active_ingredients)."""
    info = _extract_dosage_info(item)
    if info is None:
        return None
    return info["form"], info["strength"]


def _extract_dosage_info(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull form, paired strength, and per-ingredient breakdown from an openFDA
    NDC record.

    Returns:
        {
          "form":        "tablet",
          "strength":    "25 mg / 20 mg",
          "ingredients": [
              {"name": "Hydrochlorothiazide", "strength": "25 mg"},
              {"name": "Lisinopril",          "strength": "20 mg"},
          ],
        }
    """
    form_raw = (item.get("dosage_form") or "").strip()
    if not form_raw:
        return None
    form_key = form_raw.split(",")[0].strip().split()[0].lower()
    if not form_key:
        return None
    ingredients: List[Dict[str, str]] = []
    for ing in item.get("active_ingredients") or []:
        s = _clean_strength(ing.get("strength"))
        n = _title_ingredient(ing.get("name"))
        if not s:
            continue
        ingredients.append({"name": n, "strength": s})
    if not ingredients:
        return None
    return {
        "form": form_key,
        "strength": " / ".join(i["strength"] for i in ingredients),
        "ingredients": ingredients,
    }


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


async def _create_drug_from_openfda(
    item: Dict[str, Any], package_ndc: str
) -> Optional[Dict[str, Any]]:
    """Seed a new local drugs-collection entry from an openFDA NDC record.

    Keyed on rxcui (or a slug of generic_name when rxcui is missing) so that
    every future NDC scan for the same drug — different strengths, different
    labelers — accretes onto the same doc instead of producing orphans.
    Returns the inserted/refreshed doc, or None if the local store is unreachable.
    """
    if drug_db_manager is None or getattr(drug_db_manager, "drugs_collection", None) is None:
        return None
    coll = drug_db_manager.drugs_collection
    openfda = item.get("openfda") or {}
    rxcuis = [r for r in (openfda.get("rxcui") or []) if r]
    primary_rxcui = rxcuis[0] if rxcuis else None
    generic = (item.get("generic_name") or "").strip()
    brands_raw = item.get("brand_name") or openfda.get("brand_name") or []
    if isinstance(brands_raw, str):
        brands_raw = [brands_raw]
    generic_lower = generic.lower()
    brands = [b for b in brands_raw if b and b.strip().lower() != generic_lower]
    pharm_class = (
        item.get("pharm_class")
        or openfda.get("pharm_class_epc")
        or openfda.get("pharm_class_moa")
        or openfda.get("pharm_class_cs")
        or openfda.get("pharm_class_pe")
        or []
    )
    drug_class = pharm_class[0] if pharm_class else ""
    manufacturer = item.get("labeler_name", "") or (openfda.get("manufacturer_name") or [""])[0]
    name = generic or (brands[0] if brands else "")
    if not name:
        return None
    name_lower = name.lower()

    raw_ingredients = item.get("active_ingredients") or []
    ingredient_names = [_title_ingredient(i.get("name")) for i in raw_ingredients if i.get("name")]
    is_combination = len(ingredient_names) > 1

    drug_id = (
        f"openfda_rxcui_{primary_rxcui}" if primary_rxcui
        else f"openfda_{re.sub(r'[^a-z0-9]+', '_', name_lower).strip('_')}"
    )

    search_term_set = {name_lower, generic_lower, *(b.lower() for b in brands)}
    search_term_set.update(n.lower() for n in ingredient_names)
    search_term_set.discard("")

    set_on_insert: Dict[str, Any] = {
        "drug_id": drug_id,
        "name": name,
        "name_lower": name_lower,
        "status": "active",
        "data_source": "openFDA",
        "primary_search_term": name_lower,
        "search_terms": list(search_term_set),
        "search_terms_lower": list(search_term_set),
        "common_uses": [],
        "combination_drug_ids": [],
    }

    update_set: Dict[str, Any] = {"last_updated": datetime.utcnow()}
    # drug_type is split across operators to avoid a $set/$setOnInsert conflict:
    # combos always promote to "combination" (even if the doc was first seeded as
    # generic by a single-ingredient sibling NDC); non-combos only seed "generic"
    # on insert so an existing combo isn't accidentally demoted.
    if is_combination:
        update_set["drug_type"] = "combination"
    else:
        set_on_insert["drug_type"] = "generic"
    if generic:
        update_set["generic_name"] = generic
    if manufacturer:
        update_set["manufacturer"] = manufacturer
    if drug_class:
        update_set["drug_class"] = drug_class
    if primary_rxcui:
        update_set["rxnorm_id"] = primary_rxcui

    add_to_set: Dict[str, Any] = {}
    if package_ndc:
        add_to_set["ndc_codes"] = package_ndc
    if brands:
        add_to_set["brand_names"] = {"$each": brands}
    if ingredient_names:
        add_to_set["active_ingredients"] = {"$each": ingredient_names}

    dosage_info = _extract_dosage_info(item)
    if dosage_info:
        form_key = dosage_info["form"]
        add_to_set[f"dosages.{form_key}"] = dosage_info["strength"]
        if package_ndc:
            update_set[f"ndc_dosages.{package_ndc}"] = {
                "form": form_key,
                "strength": dosage_info["strength"],
                "ingredients": dosage_info["ingredients"],
            }

    update_ops: Dict[str, Any] = {
        "$setOnInsert": set_on_insert,
        "$set": update_set,
    }
    if add_to_set:
        update_ops["$addToSet"] = add_to_set

    try:
        await coll.update_one({"drug_id": drug_id}, update_ops, upsert=True)
        return await coll.find_one({"drug_id": drug_id})
    except Exception as e:
        logger.warning(f"Failed to seed local drug from openFDA NDC {package_ndc}: {e}")
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
        item.get("pharm_class")
        or openfda.get("pharm_class_epc")
        or openfda.get("pharm_class_moa")
        or openfda.get("pharm_class_cs")
        or openfda.get("pharm_class_pe")
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

    raw_ingredients = item.get("active_ingredients") or []
    ingredient_names = [_title_ingredient(i.get("name")) for i in raw_ingredients if i.get("name")]
    if len(ingredient_names) > 1 and doc.get("drug_type") != "combination":
        update_set["drug_type"] = "combination"
    if ingredient_names:
        add_to_set["active_ingredients"] = {"$each": ingredient_names}

    dosage_info = _extract_dosage_info(item)
    if dosage_info:
        form_key = dosage_info["form"]
        add_to_set[f"dosages.{form_key}"] = dosage_info["strength"]
        if package_ndc:
            update_set[f"ndc_dosages.{package_ndc}"] = {
                "form": form_key,
                "strength": dosage_info["strength"],
                "ingredients": dosage_info["ingredients"],
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


async def _lookup_one(normalized: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Resolve a single normalized 5-4-2 NDC, hitting local first then openFDA.

    Returns (result_or_None, outcome) where outcome is one of:
    `local_hit`, `openfda_enrich`, `openfda_seed`, `openfda_only`, `not_found`.
    """
    local = await _lookup_local(normalized)
    if local:
        return local, "local_hit"

    item = await _lookup_openfda_raw(normalized)
    if item is None:
        return None, "not_found"

    package_ndc = next(
        (c for c in _candidate_ndcs(normalized)
         if any(c == p.get("package_ndc") for p in item.get("packaging") or [])),
        normalized,
    )
    matched_dosage = _extract_dosage(item)

    existing = await _match_existing_drug(item)
    if existing is not None:
        enriched = await _enrich_existing_drug(existing, item, package_ndc)
        return _shape_local_result(enriched, package_ndc, matched_dosage), "openfda_enrich"

    # No local match — seed a new entry so this NDC, its strength, and its
    # form get cached. Future scans of any NDC mapped to the same rxcui or
    # generic name will accrete onto the same doc.
    seeded = await _create_drug_from_openfda(item, package_ndc)
    if seeded is not None:
        return _shape_local_result(seeded, package_ndc, matched_dosage), "openfda_seed"

    return _shape_openfda_result(item, package_ndc, matched_dosage), "openfda_only"


async def lookup_by_ndc(raw: str) -> Optional[Dict[str, Any]]:
    """Look up a single NDC. Returns one search-result-shaped dict, or None.

    Iterates every plausible 5-4-2 normalization (dashed inputs are
    unambiguous; undashed inputs may map to several depending on which
    grouping the labeler originally registered) and returns the first hit.
    Records the outcome of the first non-`not_found` candidate (or the last
    candidate if every one missed) into the in-memory NDC stats counter.
    """
    candidates = normalize_ndc_candidates(raw)
    if not candidates:
        await _ndc_stats.record("parse_error", raw=raw)
        return None

    last_outcome = "not_found"
    last_normalized: Optional[str] = None
    for normalized in candidates:
        last_normalized = normalized
        result, outcome = await _lookup_one(normalized)
        # Stop on the first real resolution; "not_found" means try the next
        # candidate grouping before giving up.
        if outcome != "not_found":
            await _ndc_stats.record(outcome, raw=raw, ndc=normalized)
            return result
        last_outcome = outcome
    await _ndc_stats.record(last_outcome, raw=raw, ndc=last_normalized)
    return None
