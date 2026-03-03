#!/usr/bin/env python3
"""Fetch dosage information for all drugs using OpenFDA NDC bulk data.

Downloads and matches the OpenFDA NDC dataset against our drug database
to extract structured dosage forms, strengths, and routes of administration.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NDC_FILE = PROJECT_ROOT / "data" / "openfda" / "drug-ndc-0001-of-0001.json"
DRUG_FILE = PROJECT_ROOT / "rxlist_export_1759512548.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "drug_dosages.json"

# Only include actual patient-facing drug products
VALID_PRODUCT_TYPES = {
    "HUMAN PRESCRIPTION DRUG",
    "HUMAN OTC DRUG",
}

# Filter out raw material / bulk forms
EXCLUDED_DOSAGE_FORMS = {
    "POWDER",  # Bulk API powders (raw material, not patient dosage forms)
}

# Strength patterns that indicate raw material, not patient products
RAW_MATERIAL_PATTERNS = re.compile(r"\d+\s*kg/", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """Normalize a drug name for matching."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [
        " hydrochloride", " hcl", " sodium", " potassium", " calcium",
        " mesylate", " maleate", " fumarate", " succinate", " tartrate",
        " besylate", " acetate", " phosphate", " sulfate", " citrate",
        " trihydrate", " dihydrate", " monohydrate",
    ]:
        name = name.replace(suffix, "")
    # Remove parenthetical content
    name = re.sub(r"\s*\(.*?\)\s*", " ", name)
    # Remove extra whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def extract_drug_names(drug_entry: dict) -> set:
    """Extract all searchable names from a drug entry."""
    names = set()

    raw_name = drug_entry.get("name", "")
    generic = drug_entry.get("generic_name", "")
    brands = drug_entry.get("brand_names", [])

    # "BrandName (GenericName)" format - extract both parts
    if "(" in raw_name:
        parts = re.split(r"\s*[\(\)]\s*", raw_name)
        for p in parts:
            p = p.strip()
            if p:
                names.add(normalize_name(p))

    if raw_name:
        names.add(normalize_name(raw_name))
    if generic:
        names.add(normalize_name(generic))
    for b in brands:
        if b:
            names.add(normalize_name(b))

    # Split "Drug A and Drug B" or "Drug A, Drug B" combinations
    all_names = list(names)
    for name in all_names:
        if " and " in name:
            for part in name.split(" and "):
                part = part.strip()
                if len(part) > 2:
                    names.add(normalize_name(part))
        if ", " in name:
            for part in name.split(", "):
                part = part.strip()
                if len(part) > 2:
                    names.add(normalize_name(part))

    # Also try just the first word (brand name alone, e.g. "abilify" from "abilify maintena")
    for name in list(names):
        words = name.split()
        if len(words) >= 2 and len(words[0]) > 2:
            names.add(words[0])

    names.discard("")
    return names


def parse_strength(strength_str: str) -> dict:
    """Parse a strength string like '40 mg/1' into structured data."""
    match = re.match(r"([\d.]+)\s*(\w+)(?:/([\d.]+\s*\w+|\d+))?", strength_str)
    if not match:
        return {"raw": strength_str}

    value = match.group(1)
    unit = match.group(2)
    denominator = match.group(3)

    # Clean up common denominator patterns
    if denominator == "1":
        display = f"{value} {unit}"
    elif denominator:
        display = f"{value} {unit}/{denominator}"
    else:
        display = f"{value} {unit}"

    try:
        float_value = float(value)
    except ValueError:
        float_value = None

    return {
        "value": float_value,
        "unit": unit,
        "display": display,
        "raw": strength_str,
    }


def is_raw_material(record: dict) -> bool:
    """Check if an NDC record is raw material, not a patient product."""
    product_type = record.get("product_type", "")
    if product_type not in VALID_PRODUCT_TYPES:
        return True

    dosage_form = record.get("dosage_form", "")
    if dosage_form in EXCLUDED_DOSAGE_FORMS:
        return True

    for ai in record.get("active_ingredients", []):
        strength = ai.get("strength", "")
        if RAW_MATERIAL_PATTERNS.search(strength):
            return True

    return False


def build_ndc_index(ndc_records: list) -> dict:
    """Build a lookup index from normalized drug names to NDC records."""
    print("Building NDC name index...")
    index = defaultdict(list)

    for record in ndc_records:
        if is_raw_material(record):
            continue

        generic = normalize_name(record.get("generic_name", ""))
        brand = normalize_name(record.get("brand_name", ""))
        brand_base = normalize_name(record.get("brand_name_base", ""))

        names_to_index = {generic, brand, brand_base}

        # Also index individual ingredient names
        for ai in record.get("active_ingredients", []):
            ai_name = normalize_name(ai.get("name", ""))
            if ai_name:
                names_to_index.add(ai_name)

        for name in names_to_index:
            if name:
                index[name].append(record)

    print(f"  Indexed {len(index)} unique normalized names")
    return index


def extract_dosages(ndc_records: list, drug_name_hint: str = "") -> list:
    """Extract unique dosage forms from matched NDC records.

    Filters out combination products when matching a single-ingredient drug.
    """
    # Separate single-ingredient vs multi-ingredient NDC records
    single_ingredient_records = [
        r for r in ndc_records
        if len(r.get("active_ingredients", [])) == 1
    ]
    multi_ingredient_records = [
        r for r in ndc_records
        if len(r.get("active_ingredients", [])) > 1
    ]

    # Prefer single-ingredient records for cleaner dosage data.
    # Only include multi-ingredient if no single-ingredient matches found,
    # or if the drug itself is a combination drug.
    is_combination = " and " in drug_name_hint.lower() or ", " in drug_name_hint.lower()
    if single_ingredient_records and not is_combination:
        records_to_use = single_ingredient_records
    else:
        records_to_use = ndc_records

    seen = set()
    dosages = []

    for record in records_to_use:
        dosage_form = record.get("dosage_form", "Unknown")
        route = record.get("route", [])
        route_str = ", ".join(route) if isinstance(route, list) else str(route)

        for ai in record.get("active_ingredients", []):
            name = ai.get("name", "")
            strength_raw = ai.get("strength", "")
            parsed = parse_strength(strength_raw)

            # Deduplicate key: form + strength display + route
            key = (dosage_form, parsed.get("display", strength_raw), route_str)
            if key in seen:
                continue
            seen.add(key)

            dosages.append({
                "dosage_form": dosage_form,
                "strength": parsed.get("display", strength_raw),
                "strength_value": parsed.get("value"),
                "strength_unit": parsed.get("unit"),
                "route": route_str,
                "ingredient_name": name,
            })

    # Sort by strength value for clean output
    dosages.sort(key=lambda d: (d["dosage_form"], d.get("strength_value") or 0))
    return dosages


def _sort_strength(s: str) -> float:
    """Extract numeric value from strength string for sorting."""
    match = re.match(r"([\d.]+)", s)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 0.0


def main():
    # Load NDC bulk data
    print(f"Loading NDC data from {NDC_FILE}...")
    with open(NDC_FILE) as f:
        ndc_data = json.load(f)
    ndc_records = ndc_data.get("results", [])
    print(f"  Loaded {len(ndc_records)} NDC records")

    # Build index
    ndc_index = build_ndc_index(ndc_records)

    # Load our drugs
    print(f"\nLoading drug database from {DRUG_FILE}...")
    with open(DRUG_FILE) as f:
        our_drugs = json.load(f)
    print(f"  Loaded {len(our_drugs)} drugs")

    # Match each drug
    print("\nMatching drugs against NDC data...")
    results = {}
    matched = 0
    unmatched = []

    for drug in our_drugs:
        drug_name = drug.get("name", "Unknown")
        search_names = extract_drug_names(drug)

        # Try exact/direct matches first (full name, generic, brand)
        primary_names = set()
        raw_name = drug.get("name", "")
        generic = drug.get("generic_name", "")
        brands = drug.get("brand_names", [])
        if "(" in raw_name:
            parts = re.split(r"\s*[\(\)]\s*", raw_name)
            for p in parts:
                if p.strip():
                    primary_names.add(normalize_name(p.strip()))
        if raw_name:
            primary_names.add(normalize_name(raw_name))
        if generic:
            primary_names.add(normalize_name(generic))
        for b in brands:
            if b:
                primary_names.add(normalize_name(b))
        primary_names.discard("")

        # Phase 1: Try primary (exact) names
        matched_records = []
        for name in primary_names:
            matched_records.extend(ndc_index.get(name, []))

        # Phase 2: If no primary match, try expanded names (splits, first-word)
        if not matched_records:
            for name in search_names - primary_names:
                matched_records.extend(ndc_index.get(name, []))

        if matched_records:
            dosages = extract_dosages(matched_records, drug_name_hint=drug_name)
            if dosages:
                matched += 1
                results[drug_name] = {
                    "generic_name": drug.get("generic_name", ""),
                    "brand_names": drug.get("brand_names", []),
                    "drug_class": drug.get("drug_class", ""),
                    "dosages": dosages,
                    "ndc_matches": len(matched_records),
                }
            else:
                unmatched.append(drug_name)
        else:
            unmatched.append(drug_name)

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Total drugs in database:  {len(our_drugs)}")
    print(f"Matched with dosages:     {matched}")
    print(f"Unmatched:                {len(unmatched)}")
    print(f"Match rate:               {matched/len(our_drugs)*100:.1f}%")

    # Build simplified view: collapse coating variants, unique strengths per form category
    simplified = {}
    for drug_name, data in results.items():
        form_strengths = defaultdict(set)
        routes = set()
        for d in data["dosages"]:
            # Collapse dosage form to base form
            form = d["dosage_form"]
            base_form = form.split(",")[0].strip()  # "TABLET, FILM COATED" → "TABLET"
            if base_form in ("FOR SUSPENSION", "POWDER"):
                base_form = "SUSPENSION"  # Normalize powder-for-suspension
            strength = d["strength"]
            route = d["route"]
            form_strengths[base_form].add(strength)
            if route:
                routes.add(route)

        simplified[drug_name] = {
            "generic_name": data["generic_name"],
            "brand_names": data["brand_names"],
            "drug_class": data["drug_class"],
            "routes": sorted(routes),
            "dosage_forms": {
                form: sorted(strengths, key=lambda s: _sort_strength(s))
                for form, strengths in sorted(form_strengths.items())
            },
        }

    # Save results
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "metadata": {
            "source": "OpenFDA NDC Bulk Download",
            "total_drugs": len(our_drugs),
            "matched": matched,
            "unmatched": len(unmatched),
            "match_rate": f"{matched/len(our_drugs)*100:.1f}%",
        },
        "drugs": simplified,
        "drugs_detailed": results,
        "unmatched_drugs": unmatched[:100],  # First 100 for review
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"File size: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.1f} MB")

    # Show a few examples (simplified format)
    print(f"\n{'='*60}")
    print("SAMPLE RESULTS (simplified)")
    print(f"{'='*60}")
    sample_drugs = ["lisinopril", "metformin", "amoxicillin", "atorvastatin",
                    "omeprazole", "sertraline", "albuterol"]
    for sample in sample_drugs:
        for name, data in simplified.items():
            if sample in name.lower() and "(" not in name:
                print(f"\n{name} ({', '.join(data['routes'])}):")
                for form, strengths in data["dosage_forms"].items():
                    print(f"  {form}: {', '.join(strengths)}")
                break

    # Show some unmatched for debugging
    if unmatched:
        print(f"\n{'='*60}")
        print(f"SAMPLE UNMATCHED DRUGS (first 20):")
        print(f"{'='*60}")
        for name in unmatched[:20]:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
