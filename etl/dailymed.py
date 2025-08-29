"""Fetch DailyMed SPL / labeling and normalize."""
import asyncio
import httpx
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from etl.common import upsert_doc, map_to_rxcui

DAILYMED_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
SPL_SEARCH_URL = f"{DAILYMED_BASE_URL}/spls"

async def fetch_dailymed_spls(limit: int = 100) -> List[Dict]:
    """Fetch DailyMed SPL documents for common drugs."""
    print("📥 Fetching DailyMed SPL documents...")
    
    # For demonstration, we'll use sample data
    # In production, you'd make actual API calls to DailyMed
    
    sample_dailymed_data = [
        {
            "set_id": "dailymed_atorvastatin_1",
            "title": "Atorvastatin Calcium Tablets, USP",
            "rxcui": "197361",
            "sections": {
                "indications": "Atorvastatin calcium tablets are indicated for the treatment of elevated total cholesterol, LDL-C, triglycerides, and to increase HDL-C in patients with primary hypercholesterolemia and mixed dyslipidemia.",
                "dosage": "The usual starting dose is 10 or 20 mg once daily. Patients requiring large reductions in LDL-C (more than 45%) may be started at 40 mg once daily.",
                "warnings": "Liver enzyme abnormalities and persistent elevations in hepatic transaminases can occur. Monitor liver enzymes before and during treatment.",
                "adverse_events": "Most common adverse reactions (incidence ≥2%) are nasopharyngitis, arthralgia, diarrhea, pain in extremity, and urinary tract infection.",
                "drug_interactions": "Avoid concomitant use with strong CYP3A4 inhibitors (e.g., itraconazole, clarithromycin). Monitor for myopathy when used with cyclosporine, gemfibrozil, or niacin."
            }
        },
        {
            "set_id": "dailymed_metformin_1", 
            "title": "Metformin Hydrochloride Tablets",
            "rxcui": "6809",
            "sections": {
                "indications": "Metformin hydrochloride tablets are indicated as an adjunct to diet and exercise to improve glycemic control in adults with type 2 diabetes mellitus.",
                "dosage": "The usual starting dose is 500 mg twice daily or 850 mg once daily with meals. The dose may be increased by 500 mg weekly or 850 mg every 2 weeks.",
                "warnings": "Lactic acidosis is a rare but serious metabolic complication that can occur due to metformin accumulation. Risk increases with conditions that impair renal function.",
                "adverse_events": "Most common adverse reactions (incidence >5%) are diarrhea, nausea/vomiting, flatulence, asthenia, indigestion, abdominal discomfort, and headache.",
                "drug_interactions": "Cationic drugs that are eliminated by renal tubular secretion may reduce metformin elimination. Monitor for metformin adverse effects."
            }
        },
        {
            "set_id": "dailymed_lisinopril_1",
            "title": "Lisinopril Tablets",
            "rxcui": "29046",
            "sections": {
                "indications": "Lisinopril tablets are indicated for the treatment of hypertension, heart failure, and to improve survival after myocardial infarction.",
                "dosage": "Hypertension: Usual starting dose is 10 mg once daily. Heart failure: Start with 2.5 mg once daily, titrate to target dose of 20-40 mg daily.",
                "warnings": "Angioedema can occur with ACE inhibitors. Discontinue immediately if angioedema occurs. Monitor renal function and potassium levels.",
                "adverse_events": "Most common adverse reactions (incidence ≥5%) are dizziness, headache, cough, fatigue, and nausea.",
                "drug_interactions": "Avoid concomitant use with aliskiren in patients with diabetes. Monitor potassium with potassium-sparing diuretics or potassium supplements."
            }
        }
    ]
    
    print(f"✅ Retrieved {len(sample_dailymed_data)} DailyMed documents")
    return sample_dailymed_data

def parse_spl_sections(spl_data: Dict) -> Dict[str, str]:
    """Parse SPL sections from DailyMed data."""
    return spl_data.get("sections", {})

async def run():
    """Main ETL function for DailyMed."""
    print("🏥 Starting DailyMed ETL...")
    
    # Fetch SPL documents
    spl_documents = await fetch_dailymed_spls()
    
    print(f"📝 Processing {len(spl_documents)} DailyMed SPL documents...")
    
    # Process each SPL document
    for spl in spl_documents:
        sections = parse_spl_sections(spl)
        
        # Create comprehensive text content
        text_parts = [f"DailyMed SPL: {spl['title']}"]
        
        for section_name, content in sections.items():
            if content:
                text_parts.append(f"{section_name.replace('_', ' ').title()}: {content}")
        
        full_text = "\n\n".join(text_parts)
        
        # Store in ChromaDB
        await upsert_doc(
            rxcui=spl["rxcui"],
            source="dailymed",
            id=spl["set_id"],
            url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={spl['set_id']}",
            title=spl["title"],
            text=full_text
        )
    
    print("✅ DailyMed ETL completed!")
    return len(spl_documents)

if __name__ == "__main__":
    asyncio.run(run())
