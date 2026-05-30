"""Patient-friendly drug info pulled verbatim from openFDA SPL labels, with
plain-language bullets summarized for the reader's medical-literacy tier.

Verbatim FDA text is the source of truth and is always returned alongside the
bullets so the UI can offer a "Read the original FDA text" toggle. The
summarizer is source-locked (no outside medical knowledge, hedges preserved),
and on any LLM failure the bullets come back empty while the verbatim text
remains — a degraded but still-correct response.

Lookup order: openFDA label by RxCUI (precise), then by generic name, then by
brand name. Results are cached in the `drug_patient_info` Mongo collection
keyed on (rxcui-or-name, literacy_level). Two entry-points:

* `get_patient_info(...)` — used by the on-demand GET path. Serves the cache
  when fresh; otherwise fetches openFDA + summarizes + caches. Designed to
  fit inside the 30s HTTP budget.
* `regenerate_patient_info(...)` — used by the weekly batch. Fetches the
  openFDA label, hashes the verbatim text, and skips the LLM entirely when
  the hash and prompt_version are both unchanged from the cached entry.
  Steady-state batches spend zero LLM tokens.
"""

import hashlib
import logging
import re
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

# Hash-based invalidation is the primary freshness signal now (verbatim text
# unchanged AND prompt version unchanged -> skip LLM). TTL is kept as a
# safety net in case the weekly batch script fails for several weeks in a
# row, so users don't see indefinitely-stale bullets.
CACHE_TTL_DAYS = 90
COLLECTION_NAME = "drug_patient_info"
# Effectively no truncation for typical FDA labels — lovastatin's longest
# section is ~7100 chars, clozapine/atorvastatin similar. We previously
# trimmed to 1500 and were cutting off the actual list of named adverse
# reactions, sending the LLM only clinical-study methodology prose. With
# gpt-4o-mini the larger input is well under the model's context limit
# and adds negligible per-call cost.
MAX_SECTION_CHARS = 12000

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


def _extract_all_sections(label: Dict[str, Any]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for fda_field, ui_key, _ in SECTION_SPEC:
        out[ui_key] = _extract_section(label, fda_field)
    return out


def _text_hash(sections_by_key: Dict[str, Optional[str]]) -> str:
    """Stable hash of the verbatim text for change-detection.

    Sorts keys so the hash is order-independent, and includes a section
    delimiter so a section that moved between fields doesn't accidentally
    collide. Used by the batch path to decide whether the label has actually
    changed since the last LLM run; if the hash matches, we skip regen.
    """
    h = hashlib.sha256()
    for key in sorted(sections_by_key.keys()):
        text = sections_by_key.get(key) or ""
        h.update(key.encode("utf-8"))
        h.update(b"\x1e")  # ASCII record separator — won't appear in label text
        h.update(text.encode("utf-8"))
        h.update(b"\x1f")  # ASCII unit separator
    return h.hexdigest()


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
    extracted: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    # Extract verbatim sections first — the source of truth. Caller may pass
    # `extracted` if they already computed it (e.g. for hashing); avoids
    # parsing the openFDA payload twice.
    if extracted is None:
        extracted = _extract_all_sections(label)

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
        # Normalized names from the resolved label, persisted so a cached entry
        # can be re-validated against the requested name on read (see
        # _payload_matches_name) without re-hitting openFDA. Internal field.
        "_match_keys": {
            "brand_name": _openfda_values(label, "brand_name"),
            "generic_name": _openfda_values(label, "generic_name"),
            "substance_name": _openfda_values(label, "substance_name"),
        },
        "literacy_level": literacy_level,
        "prompt_version": PROMPT_VERSION,
        "sections": sections,
        "source_url": source_url,
        "source_name": source_name,
        "last_verified_at": datetime.now(timezone.utc).isoformat(),
    }


def _pick_best_label(
    results: list[Dict[str, Any]], name: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Choose the best candidate from a set of openFDA labels.

    Preference order: (1) labels that actually match the requested name —
    which excludes combination products for a single-ingredient request, so
    "metformin" picks plain metformin over the Saxagliptin/Metformin combo;
    then (2) an oral form over an injectable/IV one. Falls back to the first
    result when nothing matches, so the caller's name/combo gate still applies.
    """
    if not results:
        return None
    candidates = results
    if name:
        matched = [r for r in results if _label_matches_name(name, r)]
        if matched:
            candidates = matched
    return next((r for r in candidates if _is_oral_label(r)), candidates[0])


async def _query_openfda_label(
    query_expr: str, name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    # Fetch several candidates (not just 1) so we can prefer a name-matching,
    # single-ingredient, oral form over a combo/injectable openFDA ranks first.
    params: Dict[str, Any] = {"search": query_expr, "limit": 10}
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
    return _pick_best_label(data.get("results") or [], name)


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _norm(s: Optional[str]) -> str:
    """Lowercase a string and collapse runs of non-alphanumerics to single
    spaces, so 'Amlodipine Besylate' and 'amlodipine-besylate' compare equal."""
    if not s:
        return ""
    return _NON_ALNUM_RE.sub(" ", s.lower()).strip()


def _openfda_values(label: Dict[str, Any], key: str) -> list[str]:
    vals = (label.get("openfda") or {}).get(key) or []
    if isinstance(vals, str):
        vals = [vals]
    return [_norm(v) for v in vals if v]


def _label_is_combination(label: Dict[str, Any]) -> bool:
    """True when the label lists more than one distinct active substance
    (e.g. Tribenzor = olmesartan + amlodipine + hydrochlorothiazide)."""
    return len({s for s in _openfda_values(label, "substance_name") if s}) > 1


# Routes/forms taken by mouth. This app is about the pills people take at home,
# so an oral form should win over an injectable/IV version of the same drug.
_ORAL_ROUTES = {"ORAL", "SUBLINGUAL", "BUCCAL"}
_ORAL_FORM_HINTS = (
    "TABLET", "CAPSULE", "ORAL", "SUBLINGUAL", "BUCCAL",
    "LOZENGE", "CHEWABLE", "GRANULE", "FILM", "TROCHE",
)


def _is_oral_label(label: Dict[str, Any]) -> bool:
    """Best-effort check that a label describes an orally-administered form.
    Routes are the strong signal; dosage_form wording is a fallback for the
    labels that omit `route`. A label with neither is treated as non-oral so
    it never beats a label we can positively confirm as oral."""
    openfda = label.get("openfda") or {}
    routes = openfda.get("route") or []
    if isinstance(routes, str):
        routes = [routes]
    if any((r or "").strip().upper() in _ORAL_ROUTES for r in routes):
        return True
    forms = openfda.get("dosage_form") or []
    if isinstance(forms, str):
        forms = [forms]
    return any(any(h in (f or "").upper() for h in _ORAL_FORM_HINTS) for f in forms)


def _label_matches_name(name: str, label: Dict[str, Any]) -> bool:
    """Does this openFDA label actually correspond to the requested drug name?

    Guards against a synthetic or shared RxCUI resolving to the wrong product.
    The key rule: a single-ingredient request must never bind to a combination
    label (Norvasc/amlodipine -> Tribenzor) and vice versa. A combination label
    is therefore accepted ONLY on a brand-name match — being one of the combo's
    ingredients is not enough.
    """
    q = _norm(name)
    if not q:
        return False
    q_head = q.split()[0]
    brands = _openfda_values(label, "brand_name")

    # An EXACT brand match always wins — it uniquely identifies the product,
    # combo or not. This is the only way a combination label is accepted, so a
    # combo brand like "Tribenzor" still matches itself.
    if any(q == b for b in brands):
        return True

    # For a combination product, a loose/partial match is NOT enough. "Metformin"
    # must not bind to "Saxagliptin and Metformin Hydrochloride" just because
    # 'metformin' is one of its ingredients (or a token in its brand name), and
    # likewise "amlodipine" must not bind to Tribenzor. Only the exact brand
    # match above accepts a combo.
    if _label_is_combination(label):
        return False

    # Single-ingredient label: a partial brand-token or ingredient/generic match
    # is fine (handles "Norvasc" -> brand, "amlodipine" -> substance/generic).
    for b in brands:
        b_tokens = b.split()
        if q in b_tokens or (q_head and q_head in b_tokens):
            return True
    for s in _openfda_values(label, "substance_name") + _openfda_values(label, "generic_name"):
        s_tokens = s.split()
        if q == s or q_head in s_tokens or (s_tokens and s_tokens[0] == q_head):
            return True
    return False


def _payload_matches_name(name: Optional[str], payload: Dict[str, Any]) -> bool:
    """Self-heal check for cached entries: does a cached payload's resolved
    label still correspond to the requested name?

    Entries written after this change carry `_match_keys` (the resolved
    label's normalized openFDA names), so we re-run the exact same matcher
    used at fetch time — a combo brand like Tribenzor keeps matching while a
    single drug wrongly bound to a combo (Norvasc -> Tribenzor) is rejected.

    Legacy entries lack `_match_keys`; for those we fall back to a conservative
    drug_name heuristic that only evicts the exact bug shape (a single-product
    request, no '/', whose cache resolved to a combination 'A / B / C' name
    that doesn't name the request). Those get `_match_keys` on their next write.
    """
    if not name:
        return True
    match_keys = payload.get("_match_keys")
    if isinstance(match_keys, dict):
        return _label_matches_name(name, {"openfda": match_keys})

    raw_dn = payload.get("drug_name") or ""
    q = _norm(name)
    dn = _norm(raw_dn)
    if not q or not dn:
        return True
    q_head = q.split()[0]
    if q == dn or q in dn or q_head in dn.split():
        return True
    cached_is_combo = "/" in raw_dn
    requested_is_combo = "/" in name
    if cached_is_combo and not requested_is_combo:
        return False
    return True


async def _fetch_label(rxcui: Optional[str], name: Optional[str]) -> Optional[Dict[str, Any]]:
    # Non-oral but otherwise-correct label, kept only as a last resort so an
    # injectable-only drug still resolves when no oral form exists.
    fallback = None

    if rxcui:
        rxcui_label = await _query_openfda_label(f'openfda.rxcui:"{rxcui}"', name)
        # Trust the rxcui hit only when there's no name to cross-check, or when
        # it actually matches that name. A synthetic/shared rxcui can resolve to
        # the wrong product — e.g. Norvasc's local rxcui resolving to the
        # Tribenzor combo label — so on a name mismatch we prefer the
        # name-based lookup below and keep the rxcui hit only as a last resort.
        if rxcui_label and (not name or _label_matches_name(name, rxcui_label)):
            if _is_oral_label(rxcui_label) or not name:
                return rxcui_label
            # Matched but non-oral (e.g. an IV-only rxcui). Hold it and look for
            # the oral form by name before settling.
            fallback = rxcui_label

    if name:
        slug = name.strip().lower().replace(" ", "+")
        if slug:
            for field in ("generic_name", "brand_name"):
                label = await _query_openfda_label(f"openfda.{field}:{slug}", name)
                if label:
                    if _is_oral_label(label):
                        return label
                    if fallback is None:
                        fallback = label

    # No oral form found anywhere; degrade to the best non-oral match (if any)
    # rather than returning no label at all.
    return fallback


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


async def _write_cache(
    coll,
    cache_filter: Dict[str, Any],
    rxcui: Optional[str],
    name: Optional[str],
    tier: str,
    payload: Dict[str, Any],
    text_hash: Optional[str],
) -> None:
    if coll is None or cache_filter is None:
        return
    update: Dict[str, Any] = {
        "rxcui": rxcui,
        "name_lower": (name or "").strip().lower() or None,
        "literacy_level": tier,
        "payload": payload,
        "cached_at": datetime.now(timezone.utc),
    }
    if text_hash is not None:
        update["text_hash"] = text_hash
    try:
        await coll.update_one(cache_filter, {"$set": update}, upsert=True)
    except Exception as e:
        logger.warning(f"patient_info cache write failed: {e}")


async def get_patient_info(
    rxcui: Optional[str],
    name: Optional[str],
    literacy_level: Optional[str] = None,
    focus_areas: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Return patient-friendly FDA label sections for a drug, with bullets
    tuned to the reader's medical-literacy tier. Returns None if no matching
    openFDA label exists.

    On-demand path used by `GET /drugs/patient-info`. Serves cache when fresh
    (within TTL + matching prompt_version); otherwise fetches openFDA and
    summarizes inline so the user never sees an empty card. The batch
    regenerator below is responsible for keeping the cache populated with
    high-quality results so this on-demand path rarely needs to do real work.
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
                # Self-heal entries written before the combination-product guard:
                # if a single-product request cached a combo label (Norvasc ->
                # Tribenzor), drop through to a fresh, validated _fetch_label.
                if (
                    _is_cache_fresh(cached.get("cached_at"), payload)
                    and _payload_matches_name(name, payload)
                ):
                    payload = dict(payload)
                    # Cache entries written while the LLM was unavailable are
                    # missing bullets. Backfill them in-place at the current
                    # tier so we don't have to wait for the TTL to recover.
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

    extracted = _extract_all_sections(label)
    payload = await _shape_response(
        label, rxcui, name, tier, focus, extracted=extracted
    )
    payload["cache_hit"] = False

    await _write_cache(
        coll, cache_filter, rxcui, name, tier, payload, _text_hash(extracted)
    )
    return payload


async def regenerate_patient_info(
    rxcui: Optional[str],
    name: Optional[str],
    literacy_level: Optional[str] = None,
    focus_areas: Optional[Iterable[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Batch-path regenerator. Hash-checks the openFDA label against the
    cached entry; only runs the LLM when the verbatim text has actually
    changed or the prompt version has been bumped. Returns a status dict
    the batch script can log/aggregate over.

    Status values:
      * `not-found`  — openFDA returned no label for this drug.
      * `skipped`    — cached hash + prompt_version match; no LLM call made.
      * `regenerated`— LLM ran, cache updated.
      * `error`      — unexpected failure during regen (caller may retry).
    """
    if not rxcui and not name:
        return {"status": "error", "reason": "rxcui-or-name-required"}

    tier = normalize_literacy_level(literacy_level)
    focus = _normalize_focus_areas(focus_areas)

    label = await _fetch_label(rxcui, name)
    if not label:
        return {"status": "not-found", "rxcui": rxcui, "name": name, "tier": tier}

    extracted = _extract_all_sections(label)
    new_hash = _text_hash(extracted)

    coll = _get_cache_collection()
    cache_filter = _cache_filter(rxcui, name, tier)

    if coll is not None and cache_filter is not None and not force:
        try:
            cached = await coll.find_one(cache_filter)
            if cached:
                cached_payload = cached.get("payload") or {}
                hash_match = cached.get("text_hash") == new_hash
                version_match = cached_payload.get("prompt_version") == PROMPT_VERSION
                no_missing_bullets = not _payload_missing_bullets(cached_payload)
                if hash_match and version_match and no_missing_bullets:
                    return {
                        "status": "skipped",
                        "reason": "unchanged",
                        "rxcui": rxcui,
                        "name": name,
                        "tier": tier,
                        "text_hash": new_hash,
                    }
        except Exception as e:
            logger.warning(f"regenerate cache read failed: {e}")

    try:
        payload = await _shape_response(
            label, rxcui, name, tier, focus, extracted=extracted
        )
    except Exception as e:
        logger.warning(f"regenerate _shape_response failed: {e}")
        return {"status": "error", "reason": str(e)}

    payload["cache_hit"] = False
    await _write_cache(coll, cache_filter, rxcui, name, tier, payload, new_hash)
    return {
        "status": "regenerated",
        "rxcui": rxcui,
        "name": name,
        "tier": tier,
        "text_hash": new_hash,
        "drug_name": payload.get("drug_name"),
        "sections_with_bullets": sum(
            1
            for v in (payload.get("sections") or {}).values()
            if v and (v.get("bullets") or [])
        ),
    }
