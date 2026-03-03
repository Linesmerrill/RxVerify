#!/usr/bin/env python3
"""
Script to scrape top 200 drugs from PTCB Test Prep and upvote them via API.

This script:
1. Scrapes the top 200 brand and generic drugs from ptcbtestprep.com
2. Searches for each drug using the /drugs/search API endpoint
3. Upvotes each found drug a random number of times (7-12) using the /drugs/vote endpoint

Usage:
    python3 scripts/upvote_top_200_drugs.py [--api-url http://localhost:8000]
"""

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# PTCB Test Prep URL
PTCB_URL = "https://ptcbtestprep.com/top-200-brand-and-generic-drugs/"

# Default API URL (can be overridden with --api-url flag)
DEFAULT_API_URL = "http://localhost:8000"

# Authoritative reference map for individual drug component classifications.
# Used to correctly classify individual components of combination drugs
# (e.g., Hyzaar = Hydrochlorothiazide + Losartan should NOT both be "Thiazide diuretic").
# Keys must be lowercase for case-insensitive lookup.
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


def get_hardcoded_drug_list():
    """Get the top 200 drugs list (hardcoded from PTCB Test Prep page).
    
    Returns a list where each entry is a dict with:
    - 'brand': single brand name (one entry per brand-generic pair)
    - 'generic': generic name
    - 'drug_class': drug class
    """
    # Format: (brand_names (can be multiple separated by |), generic, drug_class)
    # Each brand name will be split and create separate entries
    drugs_data = [
        ("Lexapro", "Escitalopram", "SSRI"),
        ("Oxycodone Hydrochloride Immediate Release", "Oxycodone", "Opioid analgesic"),
        ("Prinivil|Qbrelis|Zestril", "Lisinopril", "ACE inhibitor"),
        ("Zocor", "Simvastatin", "Statin"),
        ("Synthroid", "Levothyroxine", "Thyroid hormone"),
        ("Amoxil|Trimox", "Amoxicillin", "Antibacterial drug"),
        ("Zithromax", "Azithromycin", "Macrolide antibacterial"),
        ("Microzide|Aquazide H", "Hydrochlorothiazide", "Thiazide diuretic"),
        ("Norvasc", "Amlodipine", "Calcium channel blocker"),
        ("Xanax", "Alprazolam", "Benzodiazepine"),
        ("Glucophage|Fortamet", "Metformin", "Oral antidiabetic drug"),
        ("Lipitor", "Atorvastatin", "Statin"),
        ("Prilosec", "Omeprazole", "Proton-pump inhibitor"),
        ("Cipro|Proquin", "Ciprofloxacin", "Fluoroquinolone"),
        ("Zofran", "Ondansetron", "Antiemetic drug"),
        ("Clozaril", "Clozapine", "Antipsychotic drug"),
        ("Lasix", "Furosemide", "Loop diuretic"),
        ("Levitra", "Vardenafil", "PDE5 inhibitor"),
        ("Sumycin|Ala-Tet|Brodspec", "Tetracycline", "Antibacterial drug"),
        ("Heparin Sodium", "Heparin", "Anticoagulant drug"),
        ("Valcyte", "Valganciclovir", "Antiviral drug"),
        ("Lamictal", "Lamotrigine", "Anticonvulsant drug"),
        ("Diflucan", "Fluconazole", "Antifungal drug"),
        ("Tenormin", "Atenolol", "Beta-blocker"),
        ("Singulair", "Montelukast", "Leukotriene inhibitor"),
        ("Flonase Nasal Spray", "Fluticasone propionate", "Corticosteroid"),
        ("Zyloprim", "Allopurinol", "Anti-gout drug"),
        ("Fosamax", "Alendronate", "Bisphosphonate"),
        ("Pepcid", "Famotidine", "H2 antagonist"),
        ("Omnicef", "Cefdinir", "Cephalosporin"),
        ("Yaz", "Ethinyl estradiol|Drospirenone", "Birth control medicine"),
        ("Apresoline", "Hydralazine", "Antihypertensive drug"),
        ("Cogentin", "Benztropine", "Antiparkinsonian drug"),
        ("Aller-Chlor", "Chlorpheniramine", "Antihistamine"),
        ("Paxil", "Paroxetine", "SSRI"),
        ("Ativan", "Lorazepam", "Benzodiazepine"),
        ("Pyridium", "Phenazopyridine", "Analgesic"),
        ("Plaquenil", "Hydroxychloroquine", "Anti-malarial drug"),
        ("Lidoderm", "Lidocaine", "Local anesthetic"),
        ("Cataflam|Voltaren", "Diclofenac", "NSAID"),
        ("Rayos|Deltasone", "Prednisone", "Corticosteroid"),
        ("Zetia", "Ezetimibe", "Antihyperlipidemic"),
        ("Evista", "Raloxifene", "Estrogen modulator"),
        ("Dilantin", "Phenytoin", "Anticonvulsant drug"),
        ("Lovaza", "Omega-3 fatty acids", "Anti-triglyceride drug"),
        ("Zanaflex", "Tizanidine", "Muscle relaxant"),
        ("Tezruly|Hytrin", "Terazosin", "Alpha-1 blocker"),
        ("Dyrenium", "Triamterene", "Potassium-sparing diuretic"),
        ("Altace", "Ramipril", "ACE inhibitor"),
        ("Pravachol", "Pravastatin", "Statin"),
        ("Risperdal", "Risperidone", "Antipsychotic drug"),
        ("Lunesta", "Eszopiclone", "Z-drug / hypnotic"),
        ("Celebrex", "Celecoxib", "COX-inhibitor / NSAID"),
        ("Premarin", "Conjugated estrogens", "Estrogen replacement"),
        ("Avelox|Vigamox", "Moxifloxacin", "Fluoroquinolone"),
        ("Aricept", "Donepezil", "Acetylcholinesterase inhibitor"),
        ("Macrobid|Macrodantin", "Nitrofurantoin", "Antibacterial drug"),
        ("Duragesic Skin Patch", "Fentanyl", "Opioid narcotic"),
        ("Imdur", "Isosorbide mononitrate", "Nitrate"),
        ("Prozac|Sarafem", "Fluoxetine", "SSRI"),
        ("Aristocort", "Triamcinolone", "Corticosteroid"),
        ("Suboxone", "Buprenorphine|Naloxone", "Narcotic"),
        ("Vyvanse", "Lisdexamfetamine", "CNS Stimulant"),
        ("Pamelor", "Nortriptyline", "Tricyclic antidepressant"),
        ("HumaLOG", "Insulin lispro", "Rapid-acting insulin"),
        ("Depacon|Depakote", "Valproate sodium", "Anticonvulsant drug"),
        ("BetaSept|ChloraPrep", "Chlorhexidine", "Disinfectant/antiseptic"),
        ("Dibent|Bentyl", "Dicyclomine", "Anti-spasmodic drug"),
        ("Imitrex", "Sumatriptan", "Anti-migraine drug"),
        ("Protonix", "Pantoprazole", "Proton-pump inhibitor"),
        ("Lopressor", "Metoprolol", "Beta-blocker"),
        ("Robitussen", "Dextromethorphan|Guaifenesin", "Antitussive"),
        ("Valium", "Diazepam", "Benzodiazepine"),
        ("Viagra", "Sildenafil", "PDE5 inhibitor"),
        ("Bactroban", "Mupirocin", "Antibacterial drug"),
        ("Januvia", "Sitagliptin", "Antidiabetic drug"),
        ("Reglan", "Metoclopramide", "Dopamine antagonist"),
        ("Relafen", "Nabumetone", "NSAID"),
        ("Keflex", "Cefalexin", "Cephalosporin"),
        ("Effexor", "Venlafaxine", "SNRI"),
        ("Boniva", "Ibandronate", "Bisphosphonate"),
        ("Axid", "Nizatidine", "H2 antagonist"),
        ("Ex-Lax|Senna Lax", "Senna", "Laxative"),
        ("NovoLog", "Insulin aspart", "Rapid-acting insulin"),
        ("Bayer|Ecotrin|Bufferin", "Aspirin", "Antipyretic"),
        ("Gablofen|Lioresal", "Baclofen", "Muscle relaxant"),
        ("Flagyl", "Metronidazole", "Antibacterial drug"),
        ("Keppra", "Levetiracetam", "Anticonvulsant drug"),
        ("Colcrys|Mitigare", "Colchicine", "Anti-gout drug"),
        ("Zyprexa", "Olanzapine", "Antipsychotic drug"),
        ("Avodart", "Dutasteride", "5-alpha reductase inhibitor"),
        ("TriCor|Antara", "Fenofibrate", "Fibrate"),
        ("Cardura", "Doxazosin", "Alpha-1 blocker"),
        ("Aleve", "Naproxen", "NSAID"),
        ("Aldactone", "Spironolactone", "Potassium-sparing diuretic"),
        ("Namenda", "Memantine", "NMDA antagonist"),
        ("Methadose", "Methadone", "Opioid analgesic"),
        ("Vasotec|Epaned", "Enalapril", "ACE inhibitor"),
        ("Tamiflu", "Oseltamivir", "Antiviral drug"),
        ("Requip", "Ropinirole", "Antiparkinsonian drug"),
        ("Penicillin V potassium", "Penicillin V potassium", "Beta-lactam antibacterial"),
        ("Strattera", "Atomoxetine", "Norepinephrine reuptake inhibitor"),
        ("Ambien", "Zolpidem", "Z-drug / hypnotic"),
        ("Advair", "Salmeterol|Fluticasone", "Bronchodilators"),
        ("Levaquin", "Levofloxacin", "Fluoroquinolone"),
        ("Tofranil", "Imipramine", "Tricyclic antidepressant"),
        ("Reclast|Zometa", "Zoledronic acid", "Bisphosphonate"),
        ("Glucotrol", "Glipizide", "Antidiabetic drug"),
        ("Generlac|Constulose", "Lactulose", "Laxative"),
        ("AcipHex", "Rabeprazole", "Proton-pump inhibitor"),
        ("Otrexup", "Methotrexate", "DMARD"),
        ("Cleocin", "Clindamycin", "Antibacterial drug"),
        ("Tylenol", "Acetaminophen", "Analgesic / antipyretic"),
        ("Feosol", "Ferrous sulfate", "Iron supplement"),
        ("Relpax", "Eletriptan", "Antimigraine drug"),
        ("Carbacot|Robaxin", "Methocarbamol", "Muscle relaxant"),
        ("DiaBeta", "Glyburide", "Antidiabetic drug"),
        ("Celexa", "Citalopram", "SSRI"),
        ("Benicar", "Olmesartan", "Angiotensin II blocker"),
        ("Coreg", "Carvedilol", "Beta-blocker"),
        ("Spiriva", "Tiotropium", "Anticholinergic"),
        ("Xolair", "Omalizumab", "Monoclonal antibody"),
        ("NitroStat Sublingual", "Nitroglycerin", "Nitrate"),
        ("Eliquis", "Apixaban", "Anticoagulant"),
        ("Neurontin", "Gabapentin", "Anticonvulsant drug"),
        ("Enbrel", "Etanercept", "DMARD"),
        ("Herceptin", "Trastuzumab", "Monoclonal antibody"),
        ("Atripla", "Emtricitabine|Tenofovir|Efavirenz", "Antiretroviral drugs"),
        ("Xarelto", "Rivaroxaban", "Anticoagulant drug"),
        ("Stalevo 50", "Levodopa|Carbidopa|Entacapone", "Antiparkinsonian medicine"),
        ("Fioricet", "Acetaminophen|Butalbital|Caffeine", "Analgesic / antipyretic"),
        ("Levemir", "Insulin detemir", "Long-acting insulin"),
        ("Lovenox", "Enoxaparin", "Low-molecule weight heparin (LMWH)"),
        ("Ritalin|Concerta", "Methylphenidate", "CNS Stimulant"),
        ("Crestor", "Rosuvastatin", "Statin"),
        ("Xgeva|Prolia", "Denosumab", "Monoclonal antibody"),
        ("Pradaxa", "Dabigatran", "Anticoagulant drug"),
        ("Sensipar", "Cinacalcet", "Calcimimetic"),
        ("Vesicare", "Solifenacin", "Antimuscarinic drug"),
        ("Haldol", "Haloperidol", "Antipsychotic drug"),
        ("Ala-Cort", "Hydrocortisone", "Corticosteroid"),
        ("HumuLIN", "Insulin isophane", "Intermediate-acting insulin"),
        ("Isentress", "Raltegravir", "Integrase inhibitor"),
        ("Stelara", "Ustekinumab", "Monoclonal antibody"),
        ("Mobic", "Meloxicam", "NSAID"),
        ("Remicade", "Infliximab", "Monoclonal antibody"),
        ("Night Time Cold and Flu", "Acetaminophen|Dextromethorphan|Doxylamine", "Analgesic /antipyretic"),
        ("Renvela", "Sevelamer", "Phosphate binder"),
        ("Fragmin", "Dalteparin", "Low-molecular weight Heparin (LMWH)"),
        ("Zoloft", "Sertraline", "SSRI"),
        ("Klonopin", "Clonazepam", "Benzodiazepine"),
        ("Avalide", "Hydrochlorothiazide|Irbesartan", "Thiazide diuretic"),
        ("Ceftin", "Cefuroxime", "Cephalosporin"),
        ("Nizoral Topical", "Ketoconazole", "Antifungal drug"),
        ("Lyrica", "Pregabalin", "Anticonvulsant drug"),
        ("Nexium", "Esomeprazole", "Proton-pump inhibitor"),
        ("Combivent Respimat", "Albuterol|Ipratropium", "Beta-2 agonist"),
        ("Niaspan", "Niacin", "Form of vitamin B3"),
        ("Uroxatral", "Alfuzosin", "Alpha-1 blocker"),
        ("Biaxin", "Clarithromycin", "Macrolide antibacterial"),
        ("Zomig", "Zolmitriptan", "Anti-migraine drug"),
        ("Invokana", "Canagliflozin", "SGLT-2 inhibitor"),
        ("Saxenda|Victoza", "Liraglutide", "GLP-1 agonist"),
        ("Alimta", "Pemetrexed", "Anticancer drug"),
        ("Lotrimin|FungiCURE Pump Spray", "Clotrimazole", "Antifungal drug"),
        ("Avastin", "Bevacizumab", "Anticancer drug"),
        ("Sovaldi", "Sofosbuvir", "Hepatitis C drug"),
        ("Gilenya", "Fingolimod", "Immunomodulator"),
        ("Epogen", "Epoetin alfa", "Human erythropoietin"),
        ("Seroquel", "Quetiapine", "Antipsychotic drug"),
        ("Amaryl", "Glimepiride", "Antidiabetic medicine"),
        ("Percocet", "Acetaminophen|Oxycodone", "Analgesic / antipyretic"),
        ("SandIMMUNE|Neoral", "Cyclosporin", "Immunosuppressant"),
        ("Lantus", "Insulin glargine", "Long-acting insulin"),
        ("Cialis", "Tadalafil", "PDE5 inhibitor"),
        ("Endep|Elavil|Vanatrip", "Amitriptyline", "Tricyclic antidepressant"),
        ("Lopid", "Gemfibrozil", "Fibrate"),
        ("Orapred", "Prednisolone", "Corticosteroid"),
        ("Advil", "Ibuprofen", "NSAID"),
        ("Aceon", "Perindopril", "ACE inhibitor"),
        ("Desyrel", "Trazodone", "Antidepressant"),
        ("Actos", "Pioglitazone", "Thiazolidinedione"),
        ("Proscar", "Finasteride", "5-alpha reductase inhibitor"),
        ("Inbrija|Dopar|Larodopa", "Levodopa", "Antiparkinsonian drug"),
        ("Actonel", "Risedronate", "Bisphosphonate"),
        ("Ventolin|ProAir|Proventil", "Albuterol", "Beta-2 agonist"),
        ("Ultram", "Tramadol", "Opiate narcotic"),
        ("Sonata", "Zaleplon", "Z-drug / hypnotic"),
        ("Zebeta", "Bisoprolol", "Beta-blocker"),
        ("Zovirax", "Acyclovir", "Antiviral drug"),
        ("Coumadin", "Warfarin", "Anticoagulant drug"),
        ("Luvox", "Fluvoxamine", "SSRI"),
        ("Plavix", "Clopidogrel", "Antiplatelet drug"),
        ("Vibramycin|Adoxa", "Doxycycline", "Tetracycline antibiotic"),
        ("Hyzaar", "Hydrochlorothiazide|Losartan", "Thiazide diuretic"),
        ("Kytril|Sancuso", "Granisetron", "Antiemetic drug"),
        ("Restoril", "Temazepam", "Benzodiazepine"),
        ("Prevacid", "Lansoprazole", "Proton-pump inhibitor"),
        ("Augmentin", "Amoxicillin|Clavulanic acid", "Penicillin antibiotic"),
        ("Mevacor|Altoprev", "Lovastatin", "Statin"),
    ]
    
    drugs = []
    for entry in drugs_data:
        if len(entry) == 3:
            brand_names_str, generic, drug_class = entry
        else:
            brand_names_str, generic = entry
            drug_class = None
        
        if brand_names_str and generic:
            # Split multiple brand names (separated by | or comma)
            brand_names = []
            for separator in ['|', ',']:
                if separator in brand_names_str:
                    brand_names = [b.strip() for b in brand_names_str.split(separator) if b.strip()]
                    break
            else:
                # No separator found, treat as single brand name
                brand_names = [brand_names_str.strip()]
            
            # Split multiple generic names (separated by | or comma)
            generic_names = []
            for separator in ['|', ',']:
                if separator in generic:
                    generic_names = [g.strip() for g in generic.split(separator) if g.strip()]
                    break
            else:
                # No separator found, treat as single generic name
                generic_names = [generic.strip()]
            
            # Create separate entry for each brand-generic pair
            # For combination drugs, look up each component's correct class
            # from DRUG_CLASS_REFERENCE instead of using the combo-level class
            is_combo = len(generic_names) > 1
            for brand in brand_names:
                for generic_name in generic_names:
                    if brand and generic_name:
                        if is_combo:
                            component_class = DRUG_CLASS_REFERENCE.get(
                                generic_name.lower().strip(), drug_class
                            )
                        else:
                            component_class = drug_class
                        drugs.append({
                            'brand': brand,
                            'generic': generic_name,
                            'drug_class': component_class
                        })
    
    return drugs


def extract_drug_names_from_html(html_content: str):
    """Extract drug names from the PTCB Test Prep HTML page."""
    drugs = []
    
    def clean_html(text):
        """Remove HTML tags and clean up text."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Remove HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    # Try multiple patterns to find the table
    # Pattern 1: Look for table rows with <td> elements
    table_patterns = [
        r'<table[^>]*>(.*?)</table>',
        r'<tbody[^>]*>(.*?)</tbody>',
    ]
    
    table_html = None
    for pattern in table_patterns:
        match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
        if match:
            table_html = match.group(1)
            break
    
    if not table_html:
        # Try to find rows directly
        table_html = html_content
    
    # Find all table rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    
    print(f"Found {len(rows)} table rows")
    
    # If no rows found, try a different approach - look for the data directly in the content
    if len(rows) == 0:
        print("No table rows found, trying alternative parsing method...")
        # Look for patterns like "Brand Name | Generic Name" in the content
        # Based on the web search results, entries look like:
        # "Lexapro | Escitalopram | SSRI"
        # "Prinivil* Qbrelis Zestril | Lisinopril | ACE inhibitor"
        
        # Try to find lines that look like drug entries
        lines = html_content.split('\n')
        for line in lines:
            # Look for patterns with pipe separators or table-like structures
            if '|' in line and len(line.split('|')) >= 2:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2:
                    medicine_text = clean_html(parts[0])
                    generic_text = clean_html(parts[1])
                    
                    # Skip headers
                    if medicine_text.lower() in ['medicine', 'brand name', 'brand']:
                        continue
                    if generic_text.lower() in ['active ingredient', 'generic name', 'generic']:
                        continue
                    
                    if medicine_text and generic_text and len(medicine_text) > 2 and len(generic_text) > 2:
                        # Remove asterisks
                        medicine_text = re.sub(r'\*', '', medicine_text)
                        generic_text = re.sub(r'\*', '', generic_text)
                        
                        # Split brands
                        brand_names = [name.strip() for name in re.split(r'[\s,]+', medicine_text) if name.strip() and len(name.strip()) > 2]
                        generic_names = [generic_text.strip()]
                        
                        for brand in brand_names:
                            drugs.append({
                                'brand': brand,
                                'generic': generic_text.strip()
                            })
    
    for row_idx, row_html in enumerate(rows):
        # Extract all table cells
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)
        
        if len(cells) >= 2:
            medicine_cell = cells[0]
            active_ingredient_cell = cells[1]
            drug_class_cell = cells[2] if len(cells) >= 3 else None
            
            medicine_text = clean_html(medicine_cell)
            generic_text = clean_html(active_ingredient_cell)
            drug_class_text = clean_html(drug_class_cell) if drug_class_cell else None
            
            # Skip header rows
            if medicine_text.lower() in ['medicine', 'brand name', 'brand', '']:
                continue
            if generic_text.lower() in ['active ingredient', 'generic name', 'generic', 'active ingredient(s)', '']:
                continue
            if drug_class_text and drug_class_text.lower() in ['drug class', 'class', '']:
                drug_class_text = None
            
            # Skip if either is empty
            if not medicine_text or not generic_text:
                continue
            
            # Remove asterisks and italic markers (discontinued brands)
            medicine_text = re.sub(r'\*', '', medicine_text)
            medicine_text = re.sub(r'<em>|</em>', '', medicine_text)
            generic_text = re.sub(r'\*', '', generic_text)
            
            # Split multiple brands (can be separated by spaces, commas, or newlines)
            # Handle cases like "Prinivil* Qbrelis Zestril" or "Amoxil Trimox*"
            brand_names = []
            # First try splitting by common separators
            for separator in [',', '\n', '  ']:  # comma, newline, double space
                if separator in medicine_text:
                    brand_names.extend([name.strip() for name in medicine_text.split(separator)])
                    break
            else:
                # If no separator, try splitting by single spaces but be smart about it
                # Look for patterns like "Brand1 Brand2 Brand3" where each might be a brand
                parts = medicine_text.split()
                # If we have multiple words, they might be separate brands
                if len(parts) > 1:
                    # Check if any part looks like a brand (starts with capital, reasonable length)
                    for part in parts:
                        if part and len(part) > 2 and part[0].isupper():
                            brand_names.append(part)
                else:
                    brand_names = [medicine_text]
            
            # Clean up brand names
            brand_names = [name.strip() for name in brand_names if name.strip() and len(name.strip()) > 2]
            
            # Split generic names (usually just one, but handle multiple)
            generic_names = []
            for separator in [',', '\n', '  ']:
                if separator in generic_text:
                    generic_names.extend([name.strip() for name in generic_text.split(separator)])
                    break
            else:
                generic_names = [generic_text]
            
            generic_names = [name.strip() for name in generic_names if name.strip() and len(name.strip()) > 2]
            
            # Create entries for each brand-generic combination
            for brand in brand_names:
                for generic in generic_names:
                    if brand and generic:
                        drugs.append({
                            'brand': brand,
                            'generic': generic,
                            'drug_class': drug_class_text
                        })
    
    # Remove duplicates
    seen = set()
    unique_drugs = []
    for drug in drugs:
        key = (drug['brand'].lower().strip(), drug['generic'].lower().strip())
        if key not in seen and key[0] and key[1]:
            seen.add(key)
            unique_drugs.append(drug)
    
    print(f"Extracted {len(unique_drugs)} unique drug entries from page")
    
    # Debug: print first few entries
    if unique_drugs:
        print("Sample entries:")
        for drug in unique_drugs[:5]:
            print(f"  Brand: {drug['brand']}, Generic: {drug['generic']}")
    
    return unique_drugs


def search_drug(api_url: str, query: str):
    """Search for a drug using the API - exact match only."""
    try:
        clean_query = query.strip()
        if len(clean_query) < 2:
            return []
        
        search_url = f"{api_url}/drugs/search?{urlencode({'query': clean_query, 'limit': 10})}"
        req = Request(search_url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get('results', [])
            return results
    except Exception as e:
        return []


def update_drug_info(api_url: str, drug_id: str, updates: dict):
    """Update drug information using the API."""
    try:
        update_url = f"{api_url}/drugs/{drug_id}"
        data = json.dumps(updates).encode('utf-8')
        req = Request(update_url, data=data, method='PUT')
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=30) as response:
            response_data = response.read().decode('utf-8')
            data = json.loads(response_data)
            return data.get('success', False)
    except HTTPError as e:
        error_body = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"    HTTP error updating drug info: {e.code} {e.reason}")
        print(f"    Response: {error_body}")
        return False
    except Exception as e:
        print(f"    Error updating drug info: {str(e)}")
        return False


def upvote_drug(api_url: str, drug_id: str, ip_address: str = None, user_agent: str = None):
    """Upvote a drug using the API."""
    try:
        vote_url = f"{api_url}/drugs/vote?drug_id={drug_id}&vote_type=upvote"
        req = Request(vote_url, method='POST')
        req.add_header('Content-Type', 'application/json')
        if user_agent:
            req.add_header('User-Agent', user_agent)
        if ip_address:
            req.add_header('X-Forwarded-For', ip_address)
        
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('success', False)
    except Exception as e:
        return False


def generate_random_ip():
    """Generate a random IP address for voting simulation."""
    return f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"


def generate_random_user_agent():
    """Generate a random user agent string."""
    browsers = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    return random.choice(browsers)


def test_api_connection(api_url: str):
    """Test if the API is accessible."""
    try:
        test_url = f"{api_url}/status"
        req = Request(test_url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=5) as response:
            return True
    except Exception as e:
        print(f"WARNING: Could not connect to API at {api_url}: {str(e)}")
        return False


def process_generic_drug(api_url, generic_name, drug_class, processed_drug_ids, stats_lock):
    """Process a single generic drug - can be run in parallel."""
    result = {
        'generic_name': generic_name,
        'drug_id': None,
        'current_upvotes': 0,
        'success': False,
        'skipped_voting': False,
        'not_found': False,
        'upvotes_added': 0,
        'upvotes_failed': 0,
        'class_updated': False,
        'error': None
    }
    
    try:
        results = search_drug(api_url, generic_name)
        if results:
            generic_lower = generic_name.lower().strip()
            drug_id = None
            current_upvotes = 0
            
            for res in results:
                result_name = res.get('name', '').lower().strip()
                result_generic = res.get('generic_name', '').lower().strip() if res.get('generic_name') else ''
                
                if (generic_lower == result_name or generic_lower == result_generic):
                    drug_id = res.get('drug_id')
                    current_upvotes = res.get('upvotes', 0)
                    break
            
            if drug_id:
                with stats_lock:
                    if drug_id in processed_drug_ids:
                        result['skipped_voting'] = True
                        return result
                    processed_drug_ids.add(drug_id)
                
                result['drug_id'] = drug_id
                result['current_upvotes'] = current_upvotes
                
                # Always update drug class if available
                if drug_class:
                    if update_drug_info(api_url, drug_id, {'drug_class': drug_class}):
                        result['class_updated'] = True
                
                # Only upvote if under 30 votes
                if current_upvotes >= 30:
                    result['skipped_voting'] = True
                    result['success'] = True  # Still successful, just didn't vote
                    return result
                
                # Upvote the drug
                num_votes = random.randint(7, 12)
                success_count = 0
                failed_count = 0
                
                for i in range(num_votes):
                    ip_address = generate_random_ip()
                    user_agent = generate_random_user_agent()
                    
                    if upvote_drug(api_url, drug_id, ip_address, user_agent):
                        success_count += 1
                    else:
                        failed_count += 1
                    
                    time.sleep(0.05)  # Reduced delay for parallel execution
                
                result['success'] = True
                result['upvotes_added'] = success_count
                result['upvotes_failed'] = failed_count
            else:
                result['not_found'] = True
        else:
            result['not_found'] = True
    except Exception as e:
        result['error'] = str(e)
    
    return result


def process_brand_drug(api_url, drug, processed_drug_ids, stats_lock):
    """Process a single brand-generic pair - can be run in parallel."""
    brand_name = drug.get('brand')
    generic_name = drug.get('generic')
    drug_class = drug.get('drug_class')
    
    result = {
        'brand_name': brand_name,
        'generic_name': generic_name,
        'drug_id': None,
        'current_upvotes': 0,
        'success': False,
        'skipped_voting': False,
        'not_found': False,
        'upvotes_added': 0,
        'upvotes_failed': 0,
        'class_updated': False,
        'error': None
    }
    
    try:
        if brand_name:
            results = search_drug(api_url, brand_name)
            if results:
                brand_lower = brand_name.lower().strip()
                generic_lower = generic_name.lower().strip() if generic_name else ''
                drug_id = None
                current_upvotes = 0
                
                for res in results:
                    result_name = res.get('name', '').lower().strip()
                    result_generic = res.get('generic_name', '').lower().strip() if res.get('generic_name') else ''
                    result_brands = [b.lower().strip() for b in res.get('brand_names', [])]
                    
                    if (brand_lower == result_name or 
                        brand_lower in result_brands or
                        (generic_lower and generic_lower == result_generic and brand_lower in result_brands)):
                        drug_id = res.get('drug_id')
                        current_upvotes = res.get('upvotes', 0)
                        break
                
                if drug_id:
                    with stats_lock:
                        if drug_id in processed_drug_ids:
                            result['skipped_voting'] = True
                            return result
                        processed_drug_ids.add(drug_id)
                    
                    result['drug_id'] = drug_id
                    result['current_upvotes'] = current_upvotes
                    
                    # Always update drug class if available (regardless of vote count)
                    if drug_class:
                        if update_drug_info(api_url, drug_id, {'drug_class': drug_class}):
                            result['class_updated'] = True
                    
                    # Only upvote if under 30 votes
                    if current_upvotes >= 30:
                        result['skipped_voting'] = True
                        result['success'] = True  # Still successful, just didn't vote
                        return result
                    
                    # Upvote the drug
                    num_votes = random.randint(7, 12)
                    success_count = 0
                    failed_count = 0
                    
                    for i in range(num_votes):
                        ip_address = generate_random_ip()
                        user_agent = generate_random_user_agent()
                        
                        if upvote_drug(api_url, drug_id, ip_address, user_agent):
                            success_count += 1
                        else:
                            failed_count += 1
                        
                        time.sleep(0.05)  # Reduced delay for parallel execution
                    
                    result['success'] = True
                    result['upvotes_added'] = success_count
                    result['upvotes_failed'] = failed_count
                else:
                    result['not_found'] = True
            else:
                result['not_found'] = True
        else:
            result['not_found'] = True
    except Exception as e:
        result['error'] = str(e)
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Upvote top 200 drugs from PTCB Test Prep')
    parser.add_argument('--api-url', default=DEFAULT_API_URL, help=f'API base URL (default: {DEFAULT_API_URL})')
    parser.add_argument('--max-workers', type=int, default=10, help='Maximum number of parallel workers (default: 10)')
    args = parser.parse_args()
    
    api_url = args.api_url.rstrip('/')
    
    print("="*60)
    print("Top 200 Drugs Upvoter")
    print("="*60)
    print(f"API URL: {api_url}")
    print()
    
    # Test API connection
    print("Testing API connection...")
    if not test_api_connection(api_url):
        print("ERROR: Cannot connect to API. Make sure the server is running.")
        return 1
    print("✓ API connection successful\n")
    
    try:
        # Fetch the PTCB page
        print(f"Fetching top 200 drugs from {PTCB_URL}...")
        req = Request(PTCB_URL)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urlopen(req, timeout=30) as response:
            html_content = response.read().decode('utf-8')
        
        print("Page fetched successfully, extracting drug names...")
        
        # Try to extract from HTML first
        drugs = extract_drug_names_from_html(html_content)
        
        # If HTML parsing fails, use hardcoded list
        if not drugs or len(drugs) < 50:
            print("HTML parsing yielded few results, using hardcoded drug list...")
            drugs = get_hardcoded_drug_list()
        
        if not drugs:
            print("ERROR: No drugs found. Using fallback hardcoded list...")
            drugs = get_hardcoded_drug_list()
        
        if not drugs:
            print("ERROR: Could not get drug list.")
            return 1
        
        print(f"\nFound {len(drugs)} drug entries to process\n")
        
        # Track statistics (thread-safe)
        import threading
        stats_lock = threading.Lock()
        processed_drug_ids = set()  # Track which drugs we've already processed
        
        # First, collect all unique generic names with their drug classes
        generic_to_class = {}
        for drug in drugs:
            generic_name = drug.get('generic')
            drug_class = drug.get('drug_class')
            if generic_name and drug_class:
                # Use first drug_class found for each generic (they should be the same)
                if generic_name not in generic_to_class:
                    generic_to_class[generic_name] = drug_class
        
        unique_generics = sorted(generic_to_class.keys())
        
        print(f"Found {len(unique_generics)} unique generic names to process")
        print(f"Found {len(drugs)} brand-generic pairs to process")
        print(f"Using {args.max_workers} parallel workers")
        print()
        
        # Track statistics
        found_count = 0
        not_found_count = 0
        skipped_count = 0
        total_upvotes = 0
        total_failed_upvotes = 0
        
        # Process generic drugs in parallel
        print("="*60)
        print("PROCESSING GENERIC DRUGS (PARALLEL)")
        print("="*60)
        
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_to_generic = {
                executor.submit(process_generic_drug, api_url, generic_name, generic_to_class.get(generic_name), processed_drug_ids, stats_lock): generic_name
                for generic_name in unique_generics
            }
            
            completed = 0
            for future in as_completed(future_to_generic):
                completed += 1
                generic_name = future_to_generic[future]
                try:
                    result = future.result()
                    
                    if result['skipped_voting']:
                        class_msg = " (class updated)" if result['class_updated'] else ""
                        print(f"[{completed}/{len(unique_generics)}] {generic_name}: ⊙ Skipped voting ({result['current_upvotes']} upvotes >= 30){class_msg}")
                        skipped_count += 1
                        if result['class_updated']:
                            found_count += 1
                    elif result['not_found']:
                        print(f"[{completed}/{len(unique_generics)}] {generic_name}: ✗ Not found")
                        not_found_count += 1
                    elif result['success']:
                        class_msg = " (class updated)" if result['class_updated'] else ""
                        print(f"[{completed}/{len(unique_generics)}] {generic_name}: ✓ Upvoted {result['upvotes_added']} times (had {result['current_upvotes']} upvotes){class_msg}")
                        found_count += 1
                        total_upvotes += result['upvotes_added']
                        total_failed_upvotes += result['upvotes_failed']
                    elif result['error']:
                        print(f"[{completed}/{len(unique_generics)}] {generic_name}: ✗ Error: {result['error']}")
                        not_found_count += 1
                except Exception as e:
                    print(f"[{completed}/{len(unique_generics)}] {generic_name}: ✗ Exception: {str(e)}")
                    not_found_count += 1
        
        print()
        
        # Process brand-generic pairs in parallel
        print("="*60)
        print("PROCESSING BRAND-GENERIC PAIRS (PARALLEL)")
        print("="*60)
        
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_to_drug = {
                executor.submit(process_brand_drug, api_url, drug, processed_drug_ids, stats_lock): drug
                for drug in drugs
            }
            
            completed = 0
            for future in as_completed(future_to_drug):
                completed += 1
                drug = future_to_drug[future]
                brand_name = drug.get('brand', 'Unknown')
                
                try:
                    result = future.result()
                    
                    if result['skipped_voting']:
                        class_msg = " (class updated)" if result['class_updated'] else ""
                        print(f"[{completed}/{len(drugs)}] {brand_name}: ⊙ Skipped voting ({result['current_upvotes']} upvotes >= 30){class_msg}")
                        skipped_count += 1
                        if result['class_updated']:
                            found_count += 1
                    elif result['not_found']:
                        print(f"[{completed}/{len(drugs)}] {brand_name}: ✗ Not found")
                        not_found_count += 1
                    elif result['success']:
                        class_msg = " (class updated)" if result['class_updated'] else ""
                        vote_msg = f"Upvoted {result['upvotes_added']} times" if result['upvotes_added'] > 0 else "Class updated only"
                        print(f"[{completed}/{len(drugs)}] {brand_name}: ✓ {vote_msg} (had {result['current_upvotes']} upvotes){class_msg}")
                        found_count += 1
                        total_upvotes += result['upvotes_added']
                        total_failed_upvotes += result['upvotes_failed']
                    elif result['error']:
                        print(f"[{completed}/{len(drugs)}] {brand_name}: ✗ Error: {result['error']}")
                        not_found_count += 1
                except Exception as e:
                    print(f"[{completed}/{len(drugs)}] {brand_name}: ✗ Exception: {str(e)}")
                    not_found_count += 1
        
        # Print summary
        print()
        print("="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Total generic drugs processed: {len(unique_generics)}")
        print(f"Total brand-generic pairs processed: {len(drugs)}")
        print(f"Found in database: {found_count}")
        print(f"Skipped (already 30+ upvotes): {skipped_count}")
        print(f"Not found in database: {not_found_count}")
        print(f"Total successful upvotes: {total_upvotes}")
        print(f"Total failed upvotes: {total_failed_upvotes}")
        print("="*60)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\nERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
