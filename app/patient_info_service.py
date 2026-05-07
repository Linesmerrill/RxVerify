"""Patient-friendly drug info pulled verbatim from openFDA SPL labels.

Accuracy is the product here. We surface only the FDA-label sections that are
actually populated for the requested drug; sections without content come back
as null so the UI hides them. The text is returned verbatim — no summarization,
no LLM rewriting, no keyword-scraped "food warnings" — because losing a hedge
or a qualifier in patient-facing copy is worse than showing nothing.

Lookup order: openFDA label by RxCUI (precise), then by generic name, then by
brand name. Results are cached in the `drug_patient_info` Mongo collection
keyed on rxcui (or lowercased name when no rxcui is available) for CACHE_TTL_DAYS.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from app.config import settings as app_settings
from app.drug_database_manager import drug_db_manager

logger = logging.getLogger(__name__)

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
DAILYMED_SETID_URL = "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}"
FDA_LABEL_FALLBACK_URL = "https://labels.fda.gov/"

CACHE_TTL_DAYS = 30
COLLECTION_NAME = "drug_patient_info"
MAX_SECTION_CHARS = 1500

# (openFDA field, ui key, display label). Order is the display order.
SECTION_SPEC = [
    ("indications_and_usage", "what_it_does", "What it's used for"),
    ("do_not_use", "do_not_use", "Don't use if"),
    ("adverse_reactions", "side_effects", "Possible side effects"),
    ("drug_interactions", "drug_interactions", "Drug interactions"),
    ("pregnancy", "pregnancy", "Pregnancy"),
]


def _trim_section(text: str) -> str:
    """Cap long FDA prose at MAX_SECTION_CHARS, snapping to the nearest
    sentence boundary so we don't end mid-thought."""
    if len(text) <= MAX_SECTION_CHARS:
        return text.strip()
    cut = text[:MAX_SECTION_CHARS]
    for sep in (". ", ".\n"):
        idx = cut.rfind(sep)
        if idx > MAX_SECTION_CHARS // 2:
            return cut[: idx + 1].strip()
    return cut.strip() + "…"


def _extract_section(label: Dict[str, Any], field: str) -> Optional[str]:
    val = label.get(field)
    if not val:
        return None
    text = val[0] if isinstance(val, list) else val
    if not isinstance(text, str):
        return None
    text = text.strip()
    # Below ~30 chars the field is almost always just a section header without
    # body content — skip rather than render an empty card.
    if len(text) < 30:
        return None
    return _trim_section(text)


def _resolve_drug_name(label: Dict[str, Any], fallback: Optional[str]) -> str:
    openfda = label.get("openfda") or {}
    for key in ("generic_name", "brand_name", "substance_name"):
        vals = openfda.get(key) or []
        if vals and vals[0]:
            return vals[0]
    return fallback or ""


def _resolve_source_url(label: Dict[str, Any]) -> tuple[str, str]:
    openfda = label.get("openfda") or {}
    spl_set_id = (openfda.get("spl_set_id") or [None])[0]
    set_id = spl_set_id or label.get("set_id")
    if set_id:
        return DAILYMED_SETID_URL.format(set_id=set_id), "DailyMed (FDA)"
    return FDA_LABEL_FALLBACK_URL, "FDA Drug Labels"


async def _shape_response(
    label: Dict[str, Any],
    rxcui: Optional[str],
    name: Optional[str],
) -> Dict[str, Any]:
    # Extract verbatim sections first — the source of truth.
    extracted: Dict[str, Optional[str]] = {}
    for fda_field, ui_key, _ in SECTION_SPEC:
        extracted[ui_key] = _extract_section(label, fda_field)

    drug_name = _resolve_drug_name(label, name)

    # One LLM call summarizes every populated section into plain-language
    # bullets. The verbatim text remains the source of truth and is always
    # included in the response so the UI can offer "Read FDA wording".
    from app.patient_info_summarizer import summarize_sections

    summary_input = {k: v for k, v in extracted.items() if v}
    bullets_by_key = (
        await summarize_sections(summary_input, drug_name) if summary_input else {}
    )

    sections: Dict[str, Any] = {}
    for _, ui_key, ui_label in SECTION_SPEC:
        text = extracted.get(ui_key)
        if not text:
            sections[ui_key] = None
            continue
        sections[ui_key] = {
            "label": ui_label,
            "text": text,
            "bullets": bullets_by_key.get(ui_key, []),
        }

    source_url, source_name = _resolve_source_url(label)

    return {
        "rxcui": rxcui,
        "drug_name": drug_name,
        "sections": sections,
        "source_url": source_url,
        "source_name": source_name,
        "last_verified_at": datetime.now(timezone.utc).isoformat(),
    }


async def _query_openfda_label(query_expr: str) -> Optional[Dict[str, Any]]:
    params: Dict[str, Any] = {"search": query_expr, "limit": 1}
    if app_settings.OPENFDA_API_KEY:
        params["api_key"] = app_settings.OPENFDA_API_KEY
    try:
        # Tight timeout: we may chain up to 3 of these (rxcui → generic_name →
        # brand_name). Heroku's hard 30s ceiling means we can't afford an
        # openFDA hang to eat the whole request budget.
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(OPENFDA_LABEL_URL, params=params)
            if resp.status_code in (404, 429):
                return None
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"openFDA label query failed ({query_expr}): {e}")
        return None
    except Exception as e:
        logger.warning(f"openFDA label query unexpected error ({query_expr}): {e}")
        return None
    results = data.get("results") or []
    return results[0] if results else None


async def _fetch_label(rxcui: Optional[str], name: Optional[str]) -> Optional[Dict[str, Any]]:
    if rxcui:
        label = await _query_openfda_label(f'openfda.rxcui:"{rxcui}"')
        if label:
            return label
    if name:
        slug = name.strip().lower().replace(" ", "+")
        if slug:
            label = await _query_openfda_label(f"openfda.generic_name:{slug}")
            if label:
                return label
            label = await _query_openfda_label(f"openfda.brand_name:{slug}")
            if label:
                return label
    return None


def _cache_filter(rxcui: Optional[str], name: Optional[str]) -> Optional[Dict[str, Any]]:
    if rxcui:
        return {"rxcui": rxcui}
    if name:
        return {"rxcui": None, "name_lower": name.strip().lower()}
    return None


def _is_cache_fresh(cached_at: Any) -> bool:
    if not isinstance(cached_at, datetime):
        return False
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - cached_at).days < CACHE_TTL_DAYS


def _get_cache_collection():
    if drug_db_manager is None or getattr(drug_db_manager, "db", None) is None:
        return None
    return drug_db_manager.db[COLLECTION_NAME]


def _payload_missing_bullets(payload: Dict[str, Any]) -> bool:
    """True when a cached payload has populated verbatim text but every
    section's bullets list is empty — the signature of a cache entry written
    before the summarizer was deployed (or while the LLM was unavailable).
    """
    sections = payload.get("sections") or {}
    has_text = False
    has_any_bullets = False
    for v in sections.values():
        if not v:
            continue
        if v.get("text"):
            has_text = True
        if v.get("bullets"):
            has_any_bullets = True
    return has_text and not has_any_bullets


async def _backfill_bullets(
    payload: Dict[str, Any],
    coll,
    cache_filter: Dict[str, Any],
) -> Dict[str, Any]:
    """Re-run the summarizer on the verbatim text already in the cached
    payload, then write the bullets back. Avoids re-fetching openFDA.
    """
    from app.patient_info_summarizer import summarize_sections

    sections = payload.get("sections") or {}
    section_texts = {k: v["text"] for k, v in sections.items() if v and v.get("text")}
    if not section_texts:
        return payload

    bullets_by_key = await summarize_sections(
        section_texts, payload.get("drug_name") or ""
    )

    # If the LLM still produced nothing (no API key, model error), don't
    # rewrite the cache — leave the existing entry alone so we'll try again
    # on the next request rather than refreshing the TTL on an empty result.
    if not any(bullets_by_key.values()):
        return payload

    new_sections: Dict[str, Any] = {}
    for k, v in sections.items():
        if v and v.get("text"):
            new_sections[k] = {**v, "bullets": bullets_by_key.get(k, [])}
        else:
            new_sections[k] = v
    payload = {**payload, "sections": new_sections}

    if coll is not None and cache_filter is not None:
        try:
            await coll.update_one(
                cache_filter,
                {"$set": {"payload": payload, "cached_at": datetime.now(timezone.utc)}},
            )
        except Exception as e:
            logger.warning(f"patient_info bullet-backfill write failed: {e}")
    return payload


async def get_patient_info(
    rxcui: Optional[str], name: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Return patient-friendly FDA label sections for a drug, or None if no
    matching openFDA label exists.

    Sections inside the response payload may individually be None when the
    label exists but lacks that section — the UI is expected to hide nulls.
    """
    if not rxcui and not name:
        return None

    coll = _get_cache_collection()
    cache_filter = _cache_filter(rxcui, name)
    if coll is not None and cache_filter is not None:
        try:
            cached = await coll.find_one(cache_filter)
            if cached and _is_cache_fresh(cached.get("cached_at")):
                payload = cached.get("payload")
                if payload:
                    payload = dict(payload)
                    # Cache entries written before the summarizer was deployed
                    # (or while the LLM was unavailable) are missing bullets.
                    # Backfill them in-place so we don't have to wait for the
                    # 30-day TTL to recover.
                    if _payload_missing_bullets(payload):
                        payload = await _backfill_bullets(payload, coll, cache_filter)
                    payload["cache_hit"] = True
                    return payload
        except Exception as e:
            logger.warning(f"patient_info cache read failed: {e}")

    label = await _fetch_label(rxcui, name)
    if not label:
        return None

    payload = await _shape_response(label, rxcui, name)
    payload["cache_hit"] = False

    if coll is not None and cache_filter is not None:
        try:
            await coll.update_one(
                cache_filter,
                {
                    "$set": {
                        "rxcui": rxcui,
                        "name_lower": (name or "").strip().lower() or None,
                        "payload": payload,
                        "cached_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"patient_info cache write failed: {e}")

    return payload
