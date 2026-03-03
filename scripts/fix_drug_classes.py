#!/usr/bin/env python3
"""
One-time script to fix incorrect drug class assignments in the database.

This corrects drug classes for individual components of combination drugs
that were incorrectly assigned the combo-level class (e.g., Losartan was
labeled "Thiazide diuretic" from the Hyzaar combo instead of "ARB").

Usage:
    python3 scripts/fix_drug_classes.py [--api-url http://localhost:8000] [--dry-run]
"""

import argparse
import json
import sys
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_API_URL = "http://localhost:8000"

# Authoritative reference for individual drug component classifications.
# Same map used in upvote_top_200_drugs.py to prevent future misclassification.
DRUG_CLASS_REFERENCE = {
    # Suboxone components
    "buprenorphine": "Partial opioid agonist",
    "naloxone": "Opioid antagonist",
    # Robitussin components
    "dextromethorphan": "Antitussive",
    "guaifenesin": "Expectorant",
    # Advair components
    "salmeterol": "Long-acting beta-2 agonist (LABA)",
    "fluticasone": "Corticosteroid",
    "fluticasone propionate": "Corticosteroid",
    # Fioricet / Percocet / Night Time Cold and Flu components
    "acetaminophen": "Analgesic / antipyretic",
    "butalbital": "Barbiturate",
    "caffeine": "CNS stimulant",
    "doxylamine": "Antihistamine",
    "oxycodone": "Opioid analgesic",
    # Avalide / Hyzaar components
    "hydrochlorothiazide": "Thiazide diuretic",
    "irbesartan": "Angiotensin II receptor blocker (ARB)",
    "losartan": "Angiotensin II receptor blocker (ARB)",
    # Combivent components
    "albuterol": "Beta-2 agonist",
    "ipratropium": "Anticholinergic bronchodilator",
    # Augmentin components
    "amoxicillin": "Penicillin antibiotic",
    "clavulanic acid": "Beta-lactamase inhibitor",
    # Atripla components
    "emtricitabine": "NRTI",
    "tenofovir": "NtRTI",
    "efavirenz": "NNRTI",
    # Stalevo 50 components
    "levodopa": "Dopamine precursor",
    "carbidopa": "Decarboxylase inhibitor",
    "entacapone": "COMT inhibitor",
    # Yaz components
    "ethinyl estradiol": "Estrogen",
    "drospirenone": "Progestin",
}


def search_drug(api_url, query):
    """Search for a drug by name using the API."""
    try:
        search_url = f"{api_url}/drugs/search?{urlencode({'query': query, 'limit': 10})}"
        req = Request(search_url)
        req.add_header('User-Agent', 'DrugClassFixer/1.0')
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('results', [])
    except Exception as e:
        print(f"    Error searching for '{query}': {e}")
        return []


def update_drug_class(api_url, drug_id, new_class):
    """Update a drug's class via the PUT endpoint."""
    try:
        url = f"{api_url}/drugs/{drug_id}"
        data = json.dumps({"drug_class": new_class}).encode('utf-8')
        req = Request(url, data=data, method='PUT')
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'DrugClassFixer/1.0')
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"    Error updating {drug_id}: {e}")
        return None


def find_drug_match(results, generic_name):
    """Find an exact match for a generic drug name in search results."""
    generic_lower = generic_name.lower().strip()
    for r in results:
        result_name = r.get('name', '').lower().strip()
        result_generic = (r.get('generic_name') or '').lower().strip()
        if generic_lower == result_name or generic_lower == result_generic:
            return r
    return None


def main():
    parser = argparse.ArgumentParser(
        description='Fix incorrect drug class assignments in the database'
    )
    parser.add_argument('--api-url', default=DEFAULT_API_URL,
                        help=f'API base URL (default: {DEFAULT_API_URL})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would change without making updates')
    args = parser.parse_args()

    api_url = args.api_url.rstrip('/')

    if args.dry_run:
        print("=== DRY RUN MODE - No changes will be made ===\n")

    fixed = 0
    already_correct = 0
    not_found = 0
    errors = 0

    print(f"Checking {len(DRUG_CLASS_REFERENCE)} drug class assignments...\n")

    for generic_name, correct_class in sorted(DRUG_CLASS_REFERENCE.items()):
        results = search_drug(api_url, generic_name)

        drug = find_drug_match(results, generic_name)

        if not drug:
            print(f"  NOT FOUND: {generic_name}")
            not_found += 1
            continue

        drug_id = drug.get('drug_id')
        current_class = drug.get('drug_class') or '(none)'

        if current_class == correct_class:
            print(f"  OK: {generic_name} - '{correct_class}'")
            already_correct += 1
            continue

        if args.dry_run:
            print(f"  WOULD FIX: {generic_name}: '{current_class}' -> '{correct_class}'")
            fixed += 1
        else:
            result = update_drug_class(api_url, drug_id, correct_class)
            if result:
                print(f"  FIXED: {generic_name}: '{current_class}' -> '{correct_class}'")
                fixed += 1
            else:
                print(f"  ERROR: Failed to update {generic_name}")
                errors += 1

    print(f"\n{'=' * 50}")
    print(f"Summary:")
    print(f"  Fixed:           {fixed}")
    print(f"  Already correct: {already_correct}")
    print(f"  Not found:       {not_found}")
    print(f"  Errors:          {errors}")

    if args.dry_run and fixed > 0:
        print(f"\nRun without --dry-run to apply {fixed} fix(es).")


if __name__ == "__main__":
    main()
