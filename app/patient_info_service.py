"""Patient-friendly drug info pulled verbatim from openFDA SPL labels, with
plain-language bullets summarized for the reader's medical-literacy tier.

Verbatim FDA text is the source of truth and is always returned alongside the
bullets so the UI can offer a "Read the original FDA text" toggle. The
summarizer is source-locked (no outside medical knowledge, hedges preserved),
and on any LLM failure the bullets come back empty while the verbatim text
remains — a degraded but still-correct response.

Lookup order: openFDA label by RxCUI (precise), then by generic name, then by
brand name. Results are cached in the `drug_patient_info` Mongo collection
keyed on (rxcui-or-name, literacy_level) for CACHE_TTL_DAYS. Cached entries
carry a `prompt_version`; rows generated under an older prompt are treated as
stale and regenerated lazily on the next read.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

import httpx

from app.config import settings as app_settings
from app.drug_database_manager import drug_db_manager
from app.patient_info_summarizer import (
    DEFAULT_LITERACY_LEVEL,
    PROMPT_VERSION,
    normalize_literacy_level,
)

logger = logging.getLogger(__name__)

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
DAILYMED_SETID_URL = "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}"
FDA_LABEL_FALLBACK_URL = "https://labels.fda.gov/"

CACHE_TTL_DAYS = 30
COLLECTION_NAME = "drug_patient_info"
# Sized to fit the long-tail FDA adverse-reactions sections (lovastatin is
# ~7100 chars; clozapine, atorvastatin similar). At 1500 we were trimming
# off the actual list of named adverse reactions and only sending the
# clinical-study methodology prose to the LLM — which has nothing to
# bullet. The full payload across all 5 sections is still well under the
# model's context limit.
MAX_SECTION_CHARS = 8000

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


def _normalize_focus_areas(focus_areas: Optional[Iterable[str]]) -> list[str]:
    if not focus_areas:
        return []
    out: list[str] = []
    for f in focus_areas:
        if isinstance(f, str):
            f = f.strip()
            if f:
                out.append(f)
    return out


async def _shape_response(
    label: Dict[str, Any],
    rxcui: Optional[str],
    name: Optional[str],
    literacy_level: str,
    focus_areas: list[str],
) -> Dict[str, Any]:
    # Extract verbatim sections first — the source of truth.
    extracted: Dict[str, Optional[str]] = {}
    for fda_field, ui_key, _ in SECTION_SPEC:
        extracted[ui_key] = _extract_section(label, fda_field)

    drug_name = _resolve_drug_name(label, name)

    # One LLM call summarizes every populated section into plain-language
    # bullets at the reader's tier. The verbatim text remains the source of
    # truth and is always included so the UI can offer "Read FDA wording".
    from app.patient_info_summarizer import summarize_sections

    summary_input = {k: v for k, v in extracted.items() if v}
    bullets_by_key = (
        await summarize_sections(
            summary_input,
            drug_name,
            literacy_level=literacy_level,
            focus_areas=focus_areas,
        )
        if summary_input
        else {}
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
        "literacy_level": literacy_level,
        "prompt_version": PROMPT_VERSION,
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


def _cache_filter(
    rxcui: Optional[str], name: Optional[str], literacy_level: str
) -> Optional[Dict[str, Any]]:
    if rxcui:
        return {"rxcui": rxcui, "literacy_level": literacy_level}
    if name:
        return {
            "rxcui": None,
            "name_lower": name.strip().lower(),
            "literacy_level": literacy_level,
        }
    return None


def _is_cache_fresh(cached_at: Any, payload: Dict[str, Any]) -> bool:
    """A cache row is fresh only when it's within TTL AND was generated by
    the current prompt version. Stale-prompt rows are regenerated so a
    deployed prompt change reaches readers without a manual DB sweep.
    """
    if not isinstance(cached_at, datetime):
        return False
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - cached_at).days >= CACHE_TTL_DAYS:
        return False
    return payload.get("prompt_version") == PROMPT_VERSION


def _get_cache_collection():
    if drug_db_manager is None or getattr(drug_db_manager, "db", None) is None:
        return None
    return drug_db_manager.db[COLLECTION_NAME]


def _payload_missing_bullets(payload: Dict[str, Any]) -> bool:
    """True when a cached payload has populated verbatim text but every
    section's bullets list is empty — the signature of a cache entry written
    while the LLM was unavailable. Deliberately does NOT fire on partial-
    empty entries: if the LLM consistently can't bullet certain sections at
    the current prompt version, retrying on every read would burn 12s of
    LLM latency per request without changing the answer. Partial-empty rows
    are accepted until the next PROMPT_VERSION bump invalidates them.
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
    literacy_level: str,
    focus_areas: list[str],
) -> Dict[str, Any]:
    """Re-run the summarizer on the verbatim text already in the cached
    payload at the requested tier, then write the bullets back. Avoids
    re-fetching openFDA.
    """
    from app.patient_info_summarizer import summarize_sections

    sections = payload.get("sections") or {}
    section_texts = {k: v["text"] for k, v in sections.items() if v and v.get("text")}
    if not section_texts:
        return payload

    bullets_by_key = await summarize_sections(
        section_texts,
        payload.get("drug_name") or "",
        literacy_level=literacy_level,
        focus_areas=focus_areas,
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
    payload = {
        **payload,
        "sections": new_sections,
        "literacy_level": literacy_level,
        "prompt_version": PROMPT_VERSION,
    }

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
    rxcui: Optional[str],
    name: Optional[str],
    literacy_level: Optional[str] = None,
    focus_areas: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Return patient-friendly FDA label sections for a drug, with bullets
    tuned to the reader's medical-literacy tier. Returns None if no matching
    openFDA label exists.

    Sections inside the response payload may individually be None when the
    label exists but lacks that section — the UI is expected to hide nulls.
    `literacy_level` is one of beginner / intermediate / advanced; any other
    value (or omission) defaults to intermediate, the 6th-grade baseline.
    """
    if not rxcui and not name:
        return None

    tier = normalize_literacy_level(literacy_level)
    focus = _normalize_focus_areas(focus_areas)

    coll = _get_cache_collection()
    cache_filter = _cache_filter(rxcui, name, tier)
    if coll is not None and cache_filter is not None:
        try:
            cached = await coll.find_one(cache_filter)
            if cached:
                payload = cached.get("payload") or {}
                if _is_cache_fresh(cached.get("cached_at"), payload):
                    payload = dict(payload)
                    # Cache entries written while the LLM was unavailable are
                    # missing bullets. Backfill them in-place at the current
                    # tier so we don't have to wait for the 30-day TTL to
                    # recover.
                    if _payload_missing_bullets(payload):
                        payload = await _backfill_bullets(
                            payload, coll, cache_filter, tier, focus
                        )
                    payload["cache_hit"] = True
                    return payload
        except Exception as e:
            logger.warning(f"patient_info cache read failed: {e}")

    label = await _fetch_label(rxcui, name)
    if not label:
        return None

    payload = await _shape_response(label, rxcui, name, tier, focus)
    payload["cache_hit"] = False

    if coll is not None and cache_filter is not None:
        try:
            await coll.update_one(
                cache_filter,
                {
                    "$set": {
                        "rxcui": rxcui,
                        "name_lower": (name or "").strip().lower() or None,
                        "literacy_level": tier,
                        "payload": payload,
                        "cached_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"patient_info cache write failed: {e}")

    return payload
