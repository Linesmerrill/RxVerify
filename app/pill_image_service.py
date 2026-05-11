"""Resolve a pill image URL for an NDC.

Two sources, in priority order:

  1. NLM Pillbox  (public-domain pill-only photos mirrored to
     https://github.com/Med-Madness/pill-images). In-memory manifest lookup —
     no network per NDC after the manifest is loaded.
  2. DailyMed SPL Principal Display Panel (LOINC 51945-4). Fetches the SPL
     XML for the NDC, parses it, returns the first PDP image. Several
     hundred ms per NDC.

Used by:
  - The live `/drugs/lookup/ndc` route (scan-time resolution)
  - The batch `etl.dailymed_images` ETL (backfill)

The service caches the Pillbox manifest for 24 hours, refreshing lazily.
On the manifest fetch failing, we fall through to DailyMed-only resolution
rather than surfacing the failure — coverage degrades gracefully.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# --- Pillbox ----------------------------------------------------------------

PILLBOX_REPO_RAW = "https://raw.githubusercontent.com/Med-Madness/pill-images/main"
PILLBOX_MANIFEST_URL = f"{PILLBOX_REPO_RAW}/manifest.json"
MANIFEST_REFRESH_AFTER = timedelta(hours=24)

# --- DailyMed ---------------------------------------------------------------

DAILYMED_BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
SPLS_BY_NDC = f"{DAILYMED_BASE}/spls.json"
SPL_XML_BY_SETID = f"{DAILYMED_BASE}/spls/{{setid}}.xml"
DAILYMED_IMAGE_URL_TEMPLATE = "https://dailymed.nlm.nih.gov/dailymed/image.cfm?setid={setid}&name={name}"

HL7_NS = {"h": "urn:hl7-org:v3"}
PRINCIPAL_DISPLAY_PANEL_LOINC = "51945-4"

# Polite client-side throttle for DailyMed (rate limit ~240 req/min).
DAILYMED_REQUEST_INTERVAL_S = 0.3


def normalize_ndc9(ndc: str) -> Optional[str]:
    """Hyphenated NDC ('0006-0078') → 9-digit zero-padded ('000060078')."""
    if not ndc or "-" not in ndc:
        return None
    parts = ndc.split("-")
    if len(parts) != 2:
        return None
    return parts[0].zfill(5) + parts[1].zfill(4)


def _mime_by_name(name: str) -> str:
    n = name.lower()
    if n.endswith(".png"):
        return "image/png"
    if n.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def _parse_spl_images(xml_bytes: bytes, setid: str) -> list[dict]:
    """Walk the SPL, return every observationMedia annotated with section context."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning(f"SPL XML parse failed for setid={setid}: {e}")
        return []

    images: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for section in root.iter("{urn:hl7-org:v3}section"):
        code_el = section.find("h:code", HL7_NS)
        title_el = section.find("h:title", HL7_NS)
        section_loinc = code_el.get("code") if code_el is not None else None
        section_title = (title_el.text or "").strip() if title_el is not None and title_el.text else None

        for media in section.iter("{urn:hl7-org:v3}observationMedia"):
            ref = media.find(".//h:reference", HL7_NS)
            if ref is None:
                continue
            fname = ref.get("value")
            if not fname:
                continue
            key = (fname, section_loinc or "")
            if key in seen:
                continue
            seen.add(key)
            images.append({
                "name": fname,
                "url": DAILYMED_IMAGE_URL_TEMPLATE.format(setid=setid, name=fname),
                "mime_type": _mime_by_name(fname),
                "section_loinc": section_loinc,
                "section_title": section_title,
            })
    return images


def _pdp_image(images: list[dict]) -> Optional[str]:
    for img in images:
        if img.get("section_loinc") == PRINCIPAL_DISPLAY_PANEL_LOINC:
            return img["url"]
    return None


class PillImageService:
    """Singleton-style service that lazily loads the Pillbox manifest and
    resolves NDCs to image URLs (Pillbox first, DailyMed fallback)."""

    def __init__(self) -> None:
        self._manifest: dict[str, str] = {}
        self._manifest_loaded_at: Optional[datetime] = None
        self._manifest_lock = asyncio.Lock()

    async def _ensure_manifest(self, client: httpx.AsyncClient) -> None:
        now = datetime.now(timezone.utc)
        if (
            self._manifest_loaded_at is not None
            and (now - self._manifest_loaded_at) < MANIFEST_REFRESH_AFTER
        ):
            return
        async with self._manifest_lock:
            # Re-check under lock — another coroutine may have refreshed it.
            if (
                self._manifest_loaded_at is not None
                and (now - self._manifest_loaded_at) < MANIFEST_REFRESH_AFTER
            ):
                return
            try:
                resp = await client.get(PILLBOX_MANIFEST_URL, timeout=10.0)
                resp.raise_for_status()
                self._manifest = resp.json()
                self._manifest_loaded_at = now
                logger.info(f"Pillbox manifest loaded: {len(self._manifest)} NDCs")
            except (httpx.HTTPError, ValueError) as e:
                logger.warning(f"Pillbox manifest fetch failed: {e}")
                # Stamp time even on failure so we don't hammer GitHub on every
                # call — try again after the refresh window elapses.
                self._manifest_loaded_at = now

    def _pillbox_url(self, ndc: str) -> Optional[str]:
        ndc9 = normalize_ndc9(ndc)
        if not ndc9:
            return None
        relpath = self._manifest.get(ndc9)
        if not relpath:
            return None
        return f"{PILLBOX_REPO_RAW}/{relpath}"

    async def _dailymed_setid_for_ndc(
        self, client: httpx.AsyncClient, ndc: str
    ) -> Optional[str]:
        try:
            resp = await client.get(SPLS_BY_NDC, params={"ndc": ndc}, timeout=10.0)
        except httpx.HTTPError as e:
            logger.warning(f"DailyMed setid lookup failed for {ndc}: {e}")
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        data = (resp.json() or {}).get("data", []) or []
        if not data:
            return None

        def _pub(d: dict) -> datetime:
            try:
                return datetime.strptime(d.get("published_date", ""), "%b %d, %Y")
            except ValueError:
                return datetime.min
        data.sort(key=_pub, reverse=True)
        return data[0].get("setid")

    async def _dailymed_for_ndc(
        self, client: httpx.AsyncClient, ndc: str
    ) -> Optional[dict]:
        """Return {url, label_images, setid} for an NDC, or None on miss."""
        setid = await self._dailymed_setid_for_ndc(client, ndc)
        await asyncio.sleep(DAILYMED_REQUEST_INTERVAL_S)
        if not setid:
            return None
        try:
            resp = await client.get(SPL_XML_BY_SETID.format(setid=setid), timeout=15.0)
        except httpx.HTTPError as e:
            logger.warning(f"DailyMed XML fetch failed for setid={setid}: {e}")
            return None
        await asyncio.sleep(DAILYMED_REQUEST_INTERVAL_S)
        if resp.status_code != 200:
            return None
        images = _parse_spl_images(resp.content, setid)
        url = _pdp_image(images)
        if not url:
            return None
        return {"url": url, "setid": setid, "label_images": images}

    async def resolve(
        self,
        ndcs: list[str],
        client: Optional[httpx.AsyncClient] = None,
        max_dailymed_attempts: int = 5,
    ) -> Optional[dict]:
        """Try Pillbox for each NDC; fall back to DailyMed for the first
        `max_dailymed_attempts` NDCs. Returns the first hit, or None if every
        candidate misses both sources.

        Result shape:
            {
              "url": str,
              "source": "pillbox" | "dailymed_pdp",
              "ndc": str,                     # the NDC that produced the hit
              "label_images": list[dict],     # populated only for dailymed_pdp
              "setid": Optional[str],         # populated only for dailymed_pdp
            }
        """
        if not ndcs:
            return None

        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=15.0)
        try:
            await self._ensure_manifest(client)

            # 1. Pillbox: instant in-memory lookup, no network per NDC.
            for ndc in ndcs:
                url = self._pillbox_url(ndc)
                if url:
                    return {
                        "url": url,
                        "source": "pillbox",
                        "ndc": ndc,
                        "label_images": [],
                        "setid": None,
                    }

            # 2. DailyMed PDP: capped to bound scan-time latency.
            for ndc in ndcs[:max_dailymed_attempts]:
                hit = await self._dailymed_for_ndc(client, ndc)
                if hit:
                    return {
                        "url": hit["url"],
                        "source": "dailymed_pdp",
                        "ndc": ndc,
                        "label_images": hit["label_images"],
                        "setid": hit["setid"],
                    }
            return None
        finally:
            if owns_client:
                await client.aclose()


pill_image_service = PillImageService()
