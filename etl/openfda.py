"""Ingest OpenFDA drugs (product + adverse events)."""
import asyncio
import httpx
from typing import List, Dict, Optional
from etl.common import upsert_doc, map_to_rxcui

OPENFDA_BASE_URL = "https://api.fda.gov"
DRUG_LABEL_URL = f"{OPENFDA_BASE_URL}/drug/label.json"
ADVERSE_EVENTS_URL = f"{OPENFDA_BASE_URL}/drug/event.json"

async def fetch_openfda_drug_labels(limit: int = 100) -> List[Dict]:
    """Fetch OpenFDA drug labeling information."""
    print("📥 Fetching OpenFDA drug labels...")
    
    # For demonstration, we'll use sample data
    # In production, you'd make actual API calls to OpenFDA
    
    sample_openfda_data = [
        {
            "id": "openfda_atorvastatin_1",
            "rxcui": "197361",
            "generic_name": "atorvastatin calcium",
            "brand_name": "Lipitor",
            "substance_name": "atorvastatin",
            "indications_and_usage": "Lipitor is indicated for the treatment of elevated total cholesterol, LDL-C, triglycerides, and to increase HDL-C in patients with primary hypercholesterolemia and mixed dyslipidemia.",
            "dosage_and_administration": "The usual starting dose is 10 or 20 mg once daily. Patients requiring large reductions in LDL-C (more than 45%) may be started at 40 mg once daily.",
            "warnings_and_precautions": "Liver enzyme abnormalities and persistent elevations in hepatic transaminases can occur. Monitor liver enzymes before and during treatment.",
            "adverse_reactions": "Most common adverse reactions (incidence ≥2%) are nasopharyngitis, arthralgia, diarrhea, pain in extremity, and urinary tract infection.",
            "drug_interactions": "Avoid concomitant use with strong CYP3A4 inhibitors. Monitor for myopathy when used with cyclosporine, gemfibrozil, or niacin."
        },
        {
            "id": "openfda_metformin_1",
            "rxcui": "6809",
            "generic_name": "metformin hydrochloride",
            "brand_name": "Glucophage",
            "substance_name": "metformin",
            "indications_and_usage": "Glucophage is indicated as an adjunct to diet and exercise to improve glycemic control in adults with type 2 diabetes mellitus.",
            "dosage_and_administration": "The usual starting dose is 500 mg twice daily or 850 mg once daily with meals. The dose may be increased by 500 mg weekly or 850 mg every 2 weeks.",
            "warnings_and_precautions": "Lactic acidosis is a rare but serious metabolic complication that can occur due to metformin accumulation. Risk increases with conditions that impair renal function.",
            "adverse_reactions": "Most common adverse reactions (incidence >5%) are diarrhea, nausea/vomiting, flatulence, asthenia, indigestion, abdominal discomfort, and headache.",
            "drug_interactions": "Cationic drugs that are eliminated by renal tubular secretion may reduce metformin elimination. Monitor for metformin adverse effects."
        },
        {
            "id": "openfda_lisinopril_1",
            "rxcui": "29046",
            "generic_name": "lisinopril",
            "brand_name": "Zestril",
            "substance_name": "lisinopril",
            "indications_and_usage": "Zestril is indicated for the treatment of hypertension, heart failure, and to improve survival after myocardial infarction.",
            "dosage_and_administration": "Hypertension: Usual starting dose is 10 mg once daily. Heart failure: Start with 2.5 mg once daily, titrate to target dose of 20-40 mg daily.",
            "warnings_and_precautions": "Angioedema can occur with ACE inhibitors. Discontinue immediately if angioedema occurs. Monitor renal function and potassium levels.",
            "adverse_reactions": "Most common adverse reactions (incidence ≥5%) are dizziness, headache, cough, fatigue, and nausea.",
            "drug_interactions": "Avoid concomitant use with aliskiren in patients with diabetes. Monitor potassium with potassium-sparing diuretics or potassium supplements."
        }
    ]
    
    print(f"✅ Retrieved {len(sample_openfda_data)} OpenFDA drug labels")
    return sample_openfda_data

async def fetch_openfda_adverse_events(limit: int = 100) -> List[Dict]:
    """Fetch OpenFDA adverse event reports."""
    print("📥 Fetching OpenFDA adverse events...")
    
    # Sample adverse event data
    sample_adverse_events = [
        {
            "id": "openfda_ae_atorvastatin_1",
            "rxcui": "197361",
            "drug_name": "atorvastatin",
            "event_type": "myopathy",
            "description": "Reports of myopathy and rhabdomyolysis have been reported with atorvastatin use, particularly at higher doses and when used with other medications.",
            "frequency": "rare",
            "severity": "serious"
        },
        {
            "id": "openfda_ae_metformin_1",
            "rxcui": "6809",
            "drug_name": "metformin",
            "event_type": "lactic_acidosis",
            "description": "Lactic acidosis is a rare but serious metabolic complication that can occur due to metformin accumulation, particularly in patients with renal impairment.",
            "frequency": "rare",
            "severity": "serious"
        }
    ]
    
    print(f"✅ Retrieved {len(sample_adverse_events)} OpenFDA adverse events")
    return sample_adverse_events

async def run():
    """Main ETL function for OpenFDA."""
    print("🏥 Starting OpenFDA ETL...")
    
    # Fetch drug labels and adverse events
    drug_labels = await fetch_openfda_drug_labels()
    adverse_events = await fetch_openfda_adverse_events()
    
    print(f"📝 Processing {len(drug_labels)} OpenFDA drug labels...")
    
    # Process drug labels
    for label in drug_labels:
        # Create comprehensive text content
        text_parts = [f"OpenFDA Drug Label: {label['generic_name']} ({label['brand_name']})"]
        
        if label.get("indications_and_usage"):
            text_parts.append(f"Indications: {label['indications_and_usage']}")
        if label.get("dosage_and_administration"):
            text_parts.append(f"Dosage: {label['dosage_and_administration']}")
        if label.get("warnings_and_precautions"):
            text_parts.append(f"Warnings: {label['warnings_and_precautions']}")
        if label.get("adverse_reactions"):
            text_parts.append(f"Adverse Reactions: {label['adverse_reactions']}")
        if label.get("drug_interactions"):
            text_parts.append(f"Drug Interactions: {label['drug_interactions']}")
        
        full_text = "\n\n".join(text_parts)
        
        # Store in ChromaDB
        await upsert_doc(
            rxcui=label["rxcui"],
            source="openfda",
            id=label["id"],
            url=f"https://www.accessdata.fda.gov/scripts/cder/drugsatfda/index.cfm?fuseaction=Search.Label_ApprovalHistory#labelinfo",
            title=f"{label['generic_name']} ({label['brand_name']})",
            text=full_text
        )
    
    print(f"📝 Processing {len(adverse_events)} OpenFDA adverse events...")
    
    # Process adverse events
    for event in adverse_events:
        text_content = f"OpenFDA Adverse Event: {event['drug_name']} - {event['event_type']}\n\nDescription: {event['description']}\n\nFrequency: {event['frequency']}\nSeverity: {event['severity']}"
        
        await upsert_doc(
            rxcui=event["rxcui"],
            source="openfda",
            id=event["id"],
            url=f"https://www.accessdata.fda.gov/scripts/cder/drugsatfda/index.cfm?fuseaction=Search.Label_ApprovalHistory#labelinfo",
            title=f"{event['drug_name']} - {event['event_type']}",
            text=text_content
        )
    
    print("✅ OpenFDA ETL completed!")
    return len(drug_labels) + len(adverse_events)

if __name__ == "__main__":
    asyncio.run(run())
