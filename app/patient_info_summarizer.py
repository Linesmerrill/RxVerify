"""Plain-language bullet summaries of FDA-label sections, derived strictly
from the source text and tuned to the reader's medical-literacy level.

Single LLM call per drug+tier: takes a dict of {section_key -> verbatim FDA
text} and returns {section_key -> [bullet, ...]}. The model is instructed to
use only the provided text — no outside medical knowledge — so the bullets
stay faithful to the label, including the source's hedges ("may", "rarely",
"common"). Three reading-level tiers (beginner / intermediate / advanced) map
roughly to 4th-5th / 6th / 8th grade — chosen because the user's literacy
profile already buckets into these three values, and 6th grade is the
patient-comms baseline the team is targeting. Bump PROMPT_VERSION whenever
the prompt or tier rules change; the service layer treats older cached rows
as stale and regenerates them lazily on read.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Iterable, List, Optional

from openai import AsyncOpenAI

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

_async_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _async_client
    if not app_settings.OPENAI_API_KEY:
        return None
    if _async_client is None:
        _async_client = AsyncOpenAI(api_key=app_settings.OPENAI_API_KEY)
    return _async_client


# Bump when the prompt structure or tier rules change so the service can
# treat older cache rows as stale without a manual DB sweep.
PROMPT_VERSION = "v2-literacy-2026-05"

LITERACY_LEVELS = ("beginner", "intermediate", "advanced")
DEFAULT_LITERACY_LEVEL = "intermediate"


def normalize_literacy_level(value: Optional[str]) -> str:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in LITERACY_LEVELS:
            return v
    return DEFAULT_LITERACY_LEVEL


_TIER_RULES = {
    "beginner": {
        "grade_level": "4th-5th grade",
        "max_words": 15,
        "extra_rules": [
            "Translate EVERY clinical term into everyday words ('duodenal ulcer' -> 'sore in the upper gut', 'hypertension' -> 'high blood pressure', 'tubulointerstitial nephritis' -> 'kidney inflammation', 'Clostridium difficile diarrhea' -> 'a serious gut infection that causes diarrhea').",
            "Expand every acronym on first use, then drop the acronym entirely ('GERD' -> 'acid reflux'; do not keep '(GERD)').",
            "Use you / your when it reads naturally ('this medicine may make you sleepy') instead of 'patients may experience drowsiness'.",
            "Prefer short Anglo-Saxon words over Latin/Greek ones ('use' not 'utilize', 'help' not 'facilitate', 'show up' not 'manifest').",
            "If a fact cannot be stated accurately without a medical term, drop that bullet rather than blur the meaning.",
        ],
    },
    "intermediate": {
        "grade_level": "6th grade (the baseline patient-comms target)",
        "max_words": 18,
        "extra_rules": [
            "Translate clinical terms inline with the everyday word in parentheses: 'acid reflux (GERD)', 'kidney inflammation (nephritis)', 'a serious gut infection (C. difficile diarrhea)'.",
            "Expand acronyms on first use; after that the acronym alone is fine.",
            "You / your is preferred, but third-person ('some people may...') is acceptable.",
        ],
    },
    "advanced": {
        "grade_level": "8th grade",
        "max_words": 25,
        "extra_rules": [
            "Clinical terms are OK when defined once parenthetically (e.g., 'tubulointerstitial nephritis (kidney inflammation)'); after that first definition you may reuse the clinical term.",
            "This reader is still a patient, not a clinician — assume no medical training even at this tier.",
        ],
    },
}


def _build_system_prompt(
    literacy_level: str,
    focus_areas: Optional[Iterable[str]],
) -> str:
    tier = _TIER_RULES[literacy_level]
    extras = "\n".join(f"- {r}" for r in tier["extra_rules"])
    focus_clause = ""
    cleaned_focus = [f for f in (focus_areas or []) if isinstance(f, str) and f.strip()]
    if cleaned_focus:
        focus_clause = (
            "\nFOCUS-AREA HINTS (the reader has signaled interest in these "
            "topics from their learning profile — when a section addresses "
            "them, lead with those bullets and spend your clearest writing "
            "there; do not invent content outside the source): "
            + ", ".join(cleaned_focus)
        )
    return f"""You convert FDA drug-label sections into plain-language bullet points for a patient.

READING-LEVEL TARGET: {tier['grade_level']}. Every bullet should be readable, in one pass, by someone at this level. If a bullet would force them to re-read or look something up, simplify it.

STRICT RULES (these never bend, regardless of tier):
- Use ONLY the provided text. No outside medical knowledge. No additions. No fabrication of numbers, frequencies, or risk levels.
- If a section's text is empty, missing, or under ~30 characters, return an empty list for that key.
- Preserve hedges and qualifiers from the source ("may", "rarely", "common", "in some patients", "generally"). Never tighten a hedged claim into a definite one.
- Do NOT add medical advice the source does not contain. Do NOT say "talk to your doctor" unless the source says it.
- Do NOT bullet headers, footers, dosage tables, NDC codes, manufacturer info, "Inactive Ingredients", or boilerplate.
- Drug names: use Title Case once at the start of the section's first bullet ("Lansoprazole..."), not SHOUTING ALL CAPS.

PHRASING (tuned for this reader):
- Each bullet: one sentence, no more than {tier['max_words']} words, plain English, active voice when natural.
- 3-6 bullets per non-empty section, ordered most-important first.
- Concrete everyday words wherever possible ('drowsiness' not 'somnolence', 'rash' not 'cutaneous reaction', 'gut' not 'gastrointestinal tract').
{extras}
{focus_clause}

OUTPUT: strict JSON of the shape {{"sections": {{"<key>": ["bullet 1", "bullet 2", ...]}}}}, with one entry per input key (empty list if nothing summarizable).
"""


async def summarize_sections(
    section_texts: Dict[str, str],
    drug_name: str,
    literacy_level: str = DEFAULT_LITERACY_LEVEL,
    focus_areas: Optional[Iterable[str]] = None,
) -> Dict[str, List[str]]:
    """Summarize FDA section text into plain-language bullet lists for a
    specific reading-level tier.

    `section_texts` maps section key -> verbatim source text. Returns the same
    keys mapping to bullet-string lists (possibly empty). On any failure,
    returns empty lists for every key — the caller still has the verbatim
    text and the UI degrades gracefully.
    """
    client = _get_client()
    if client is None:
        logger.info("OPENAI_API_KEY not set; skipping bullet summarization")
        return {key: [] for key in section_texts}

    # Strip empty entries from the input so we don't waste tokens.
    non_empty = {k: v for k, v in section_texts.items() if v and len(v.strip()) >= 30}
    if not non_empty:
        return {key: [] for key in section_texts}

    tier = normalize_literacy_level(literacy_level)
    system_prompt = _build_system_prompt(tier, focus_areas)

    user_payload = {
        "drug_name": drug_name,
        "sections": non_empty,
    }

    try:
        response = await client.chat.completions.create(
            model=app_settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1500,
            # Keep this tight: we sit behind Heroku's 30s H12 hard limit, and
            # an unbounded LLM stall would burn the whole request budget. If
            # the model can't summarize in 12s, the caller falls back to
            # verbatim text — a degraded but still-correct response.
            timeout=12,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        out_sections = parsed.get("sections") or {}
    except json.JSONDecodeError as e:
        logger.warning(f"Summarizer returned invalid JSON: {e}")
        return {key: [] for key in section_texts}
    except Exception as e:
        logger.warning(f"Summarizer call failed for {drug_name}: {e}")
        return {key: [] for key in section_texts}

    result: Dict[str, List[str]] = {}
    for key in section_texts:
        bullets = out_sections.get(key)
        if isinstance(bullets, list):
            cleaned: List[str] = []
            for b in bullets:
                if not isinstance(b, str):
                    continue
                b = b.strip().lstrip("-•*").strip()
                if b:
                    cleaned.append(b)
            result[key] = cleaned[:6]
        else:
            result[key] = []
    return result
