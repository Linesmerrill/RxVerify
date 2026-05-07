"""Plain-language bullet summaries of FDA-label sections, derived strictly
from the source text.

Single LLM call per drug: takes a dict of {section_key -> verbatim FDA text}
and returns {section_key -> [bullet, ...]}. The model is instructed to use
only the provided text — no outside medical knowledge — so the bullets stay
faithful to the label, including the source's hedges ("may", "rarely",
"common"). When the LLM is unavailable or the source is empty, returns an
empty list for that section. The verbatim text is always available alongside
the bullets in the API response, so a degraded LLM never blocks the feature.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List

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


SUMMARIZER_SYSTEM_PROMPT = """You convert FDA drug-label sections into plain-language bullet points for a patient.

STRICT RULES:
- Use ONLY the provided text. No outside medical knowledge. No additions.
- If a section's text is empty, missing, or under ~30 characters, return an empty list for that key.
- Preserve hedges and qualifiers from the source ("may", "rarely", "common", "in some patients", "generally").
- Each bullet: one sentence, ≤25 words, plain English, active voice when natural.
- Use concrete words a patient understands ("drowsiness" not "somnolence", "rash" not "cutaneous reaction").
- 3-6 bullets per non-empty section, ordered most-important first.
- Do NOT add medical advice the source does not contain. Do NOT say "talk to your doctor" unless the source says it.
- Do NOT bullet headers, footers, dosage tables, NDC codes, manufacturer info, "Inactive Ingredients", or boilerplate.
- Do NOT invent numbers, frequencies, or risk levels not stated in the source.

OUTPUT: strict JSON of the shape {"sections": {"<key>": ["bullet 1", "bullet 2", ...]}}, with one entry per input key (empty list if nothing summarizable).
"""


async def summarize_sections(
    section_texts: Dict[str, str],
    drug_name: str,
) -> Dict[str, List[str]]:
    """Summarize FDA section text into plain-language bullet lists.

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

    user_payload = {
        "drug_name": drug_name,
        "sections": non_empty,
    }

    try:
        response = await client.chat.completions.create(
            model=app_settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
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
