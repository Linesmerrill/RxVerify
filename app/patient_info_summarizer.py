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
from typing import Any, Dict, Iterable, List, Optional

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
PROMPT_VERSION = "v6-retry-empty-sections-2026-05"

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
            "Clinical terms are OK to use directly — this reader can handle 'myopathy' or 'hepatic dysfunction' without translation. A parenthetical gloss is optional, not required.",
            "Even at this tier, the reader is a patient, not a clinician — keep bullets actionable and concrete.",
            "This permission to use clinical terms is NOT permission to refuse to bullet a section. You still MUST bullet every section that has real content — see CRITICAL OUTPUT REQUIREMENT above.",
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

CRITICAL OUTPUT REQUIREMENT (this is the #1 rule — read it first):
For EVERY input section whose `text` is 30+ characters of real content, you MUST produce at least one bullet. Returning an empty list for a section that has content is a FAILURE of this task. When in doubt, BULLET IT. The acceptable cases for returning `[]` are limited to: text under 30 chars, text that is purely NDC codes / manufacturer info / "Inactive Ingredients" / packaging boilerplate. Anything else — including lists of named risks with cross-references, narrative prose about clinical studies, drug-interaction tables, pregnancy directives — MUST be bulleted, even if you have to use clinical terms or be brief.

READING-LEVEL TARGET: {tier['grade_level']}. Every bullet should be readable, in one pass, by someone at this level. If a bullet would force them to re-read or look something up, simplify it. But an imperfect bullet is ALWAYS better than no bullet.

TRANSLATING VS FABRICATING (the most important distinction):
- You MAY use general English vocabulary to translate medical jargon into plain language. That is a LINGUISTIC task, not a medical one. Examples that are FINE: "myopathy" -> "muscle damage", "rhabdomyolysis" -> "severe muscle breakdown", "hepatic dysfunction" -> "liver problems", "nasopharyngitis" -> "a cold", "arthralgia" -> "joint pain", "HbA1c" -> "long-term blood sugar", "concomitant use" -> "using at the same time".
- What you MUST NOT do is invent new FACTS: do not add risks, frequencies, drug names, conditions, mechanisms, dosages, or causal claims that are not in the source text. Translating "myopathy" to "muscle damage" is fine; adding "occurs in 5% of patients" when the source does not state that is fabrication.
- If you can name the risk, drug, or event from the source, you can bullet it — even if you have to translate the term to plain English.

STRICT RULES (these never bend, regardless of tier):
- Use ONLY the FACTS in the provided text. Linguistic translation (above) is allowed; new facts are not.
- Preserve hedges and qualifiers from the source ("may", "rarely", "common", "in some patients", "generally"). Never tighten a hedged claim into a definite one.
- Do NOT add medical advice the source does not contain. Do NOT say "talk to your doctor" unless the source says it.
- Drug names: use Title Case once at the start of the section's first bullet ("Lansoprazole..."), not SHOUTING ALL CAPS.
- If a section text genuinely contains content but you find yourself wanting to return [], stop — that is the failure mode the CRITICAL OUTPUT REQUIREMENT exists to prevent. Bullet whatever named items, claims, or directives are present.

HANDLING THE INPUT (FDA label text has structural quirks):
- The text often STARTS with the FDA section number and heading inline (e.g. "6 ADVERSE REACTIONS The following important adverse reactions are...", "7 DRUG INTERACTIONS See full prescribing information...", "8.1 Pregnancy Risk Summary Discontinue..."). Skip that opening section-number prefix and bullet the body that follows. The body is real content even when the leading label is repetitive.
- Cross-references like "[see Warnings and Precautions (5.1)]", "[see Use in Specific Populations (8.1)]", or "(2.5, 7.1)" are navigation pointers, NOT facts. Drop them and keep the surrounding fact. Do NOT skip a bullet just because it carried a cross-reference — the *named item* is still a fact.
- Lists shaped as `Name: short claim. Name: short claim.` (common in DRUG INTERACTIONS) -> one bullet per Name, preserving the claim's hedge.
- Lists shaped as `Named Risk [see ...] Named Risk [see ...]` (common in ADVERSE REACTIONS) -> one bullet per named risk, translated to plain English.
- Things that ARE boilerplate to skip: NDC codes, manufacturer addresses, "Inactive Ingredients" lists, dosage-form tables, "How Supplied" packaging info, footer text like "Distributed by...", and reporting addresses like "To report SUSPECTED ADVERSE REACTIONS, contact...".

PHRASING (tuned for this reader):
- Each bullet: one sentence, no more than {tier['max_words']} words, plain English, active voice when natural.
- 3-6 bullets per non-empty section, ordered most-important first.
- Concrete everyday words wherever possible ('drowsiness' not 'somnolence', 'rash' not 'cutaneous reaction', 'gut' not 'gastrointestinal tract').
{extras}
{focus_clause}

OUTPUT: strict JSON of the shape {{"sections": {{"<key>": ["bullet 1", "bullet 2", ...]}}}}, with one entry per input key (empty list if nothing summarizable).
"""


RETRY_NUDGE = """The previous response returned an empty bullet list for one or more sections that DO contain real content. That is the failure mode you were told to prevent. For the sections below, you MUST produce at least one bullet each. The text contains named risks, drugs, events, or directives — bullet them. If you have to be brief or use a clinical term, do that. Empty lists are not acceptable here. Apply the same source-locking, hedge-preservation, and reading-level rules from the original system prompt."""


async def _call_llm(
    client: AsyncOpenAI,
    system_prompt: str,
    user_payload: Dict[str, Any],
    drug_name: str,
) -> Dict[str, List[str]]:
    """One LLM round-trip. Returns {section_key -> bullets} for the keys in
    user_payload['sections']. Empty dict on any failure — caller decides
    whether to fall back or retry."""
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
            # Keep this tight: we sit behind Heroku's 30s H12 hard limit. If
            # the model can't summarize in 12s the caller falls back. Retry
            # call uses the same budget — bounded to 1 retry so worst-case
            # total is ~24s for the LLM stage, leaving room for openFDA.
            timeout=12,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return parsed.get("sections") or {}
    except json.JSONDecodeError as e:
        logger.warning(f"Summarizer returned invalid JSON: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Summarizer call failed for {drug_name}: {e}")
        return {}


def _clean_bullets(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned: List[str] = []
    for b in raw:
        if not isinstance(b, str):
            continue
        b = b.strip().lstrip("-•*").strip()
        if b:
            cleaned.append(b)
    return cleaned[:6]


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

    If the first LLM call returns empty bullets for any section that DID
    have real content in the input (>=30 chars), retries those sections
    once with an explicit nudge. Bounded to a single retry so a stubborn
    drug doesn't burn unbounded LLM budget.
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

    first_out = await _call_llm(
        client,
        system_prompt,
        {"drug_name": drug_name, "sections": non_empty},
        drug_name,
    )

    result: Dict[str, List[str]] = {}
    for key in section_texts:
        result[key] = _clean_bullets(first_out.get(key)) if key in non_empty else []

    # Find sections that had real content but came back empty. Retry just
    # those with an emphatic nudge — captures cases like metformin where
    # the model bails on certain FDA section structures even at v5.
    missing = {k: non_empty[k] for k in non_empty if not result.get(k)}
    if missing:
        logger.info(
            f"Retrying {list(missing.keys())} for {drug_name} ({tier}) — "
            f"first call returned empty bullets"
        )
        retry_out = await _call_llm(
            client,
            system_prompt + "\n\n" + RETRY_NUDGE,
            {"drug_name": drug_name, "sections": missing},
            drug_name,
        )
        for k in missing:
            bullets = _clean_bullets(retry_out.get(k))
            if bullets:
                result[k] = bullets

    return result
