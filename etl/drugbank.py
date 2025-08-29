"""Process DrugBank open data (not the commercial set)."""
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from etl.common import upsert_doc, map_to_rxcui

DRUGBANK_OPEN_URL = "https://go.drugbank.com/releases/latest/downloads/open-data"

async def fetch_drugbank_open_data():
    """Fetch DrugBank open data for drug interactions and mechanisms."""
    print("📥 Fetching DrugBank open data...")
    
    # For demonstration, we'll use sample data
    # In production, you'd download and parse the actual DrugBank XML files
    
    sample_drugbank_data = [
        {
            "id": "drugbank_atorvastatin_1",
            "rxcui": "197361",
            "drug_name": "atorvastatin",
            "mechanism_of_action": "Atorvastatin is a competitive inhibitor of HMG-CoA reductase, the rate-limiting enzyme that converts 3-hydroxy-3-methylglutaryl-coenzyme A to mevalonate, a precursor of sterols, including cholesterol.",
            "pharmacodynamics": "Atorvastatin reduces total cholesterol, LDL-C, and triglycerides, and increases HDL-C. It has a long half-life and is metabolized by CYP3A4.",
            "drug_interactions": [
                {
                    "drug": "itraconazole",
                    "interaction": "Strong CYP3A4 inhibitor that increases atorvastatin exposure and risk of myopathy",
                    "severity": "major"
                },
                {
                    "drug": "cyclosporine",
                    "interaction": "Increases atorvastatin exposure and risk of myopathy",
                    "severity": "major"
                },
                {
                    "drug": "gemfibrozil",
                    "interaction": "Increases atorvastatin exposure and risk of myopathy",
                    "severity": "major"
                }
            ],
            "targets": [
                "HMG-CoA reductase (primary target)",
                "CYP3A4 (metabolism)",
                "OATP1B1 (transport)"
            ]
        },
        {
            "id": "drugbank_metformin_1",
            "rxcui": "6809",
            "drug_name": "metformin",
            "mechanism_of_action": "Metformin decreases hepatic glucose production, decreases intestinal absorption of glucose, and increases insulin sensitivity by increasing peripheral glucose uptake and utilization.",
            "pharmacodynamics": "Metformin is not metabolized and is eliminated unchanged in the urine. It has a half-life of 6.2 hours and is actively transported by organic cation transporters.",
            "drug_interactions": [
                {
                    "drug": "furosemide",
                    "interaction": "May reduce metformin elimination and increase risk of lactic acidosis",
                    "severity": "moderate"
                },
                {
                    "drug": "cimetidine",
                    "interaction": "May increase metformin exposure by reducing renal elimination",
                    "severity": "moderate"
                }
            ],
            "targets": [
                "AMP-activated protein kinase (AMPK)",
                "Mitochondrial complex I",
                "Organic cation transporters (OCT1, OCT2)"
            ]
        },
        {
            "id": "drugbank_lisinopril_1",
            "rxcui": "29046",
            "drug_name": "lisinopril",
            "mechanism_of_action": "Lisinopril is a competitive inhibitor of angiotensin-converting enzyme (ACE), preventing the conversion of angiotensin I to angiotensin II, a potent vasoconstrictor.",
            "pharmacodynamics": "Lisinopril is not metabolized and is eliminated unchanged in the urine. It has a long half-life (12 hours) and provides 24-hour blood pressure control.",
            "drug_interactions": [
                {
                    "drug": "aliskiren",
                    "interaction": "Avoid concomitant use in patients with diabetes due to increased risk of renal impairment",
                    "severity": "major"
                },
                {
                    "drug": "potassium supplements",
                    "interaction": "May increase risk of hyperkalemia",
                    "severity": "moderate"
                }
            ],
            "targets": [
                "Angiotensin-converting enzyme (ACE)",
                "Bradykinin metabolism",
                "Renin-angiotensin-aldosterone system"
            ]
        }
    ]
    
    print(f"✅ Retrieved {len(sample_drugbank_data)} DrugBank records")
    return sample_drugbank_data

async def run():
    """Main ETL function for DrugBank."""
    print("🏥 Starting DrugBank ETL...")
    
    # Fetch DrugBank data
    drugbank_records = await fetch_drugbank_open_data()
    
    print(f"📝 Processing {len(drugbank_records)} DrugBank records...")
    
    # Process each DrugBank record
    for record in drugbank_records:
        # Create comprehensive text content
        text_parts = [f"DrugBank: {record['drug_name']}"]
        
        if record.get("mechanism_of_action"):
            text_parts.append(f"Mechanism of Action: {record['mechanism_of_action']}")
        
        if record.get("pharmacodynamics"):
            text_parts.append(f"Pharmacodynamics: {record['pharmacodynamics']}")
        
        if record.get("targets"):
            targets_text = "Targets: " + "; ".join(record["targets"])
            text_parts.append(targets_text)
        
        if record.get("drug_interactions"):
            interactions_text = "Drug Interactions:"
            for interaction in record["drug_interactions"]:
                interactions_text += f"\n- {interaction['drug']}: {interaction['interaction']} (Severity: {interaction['severity']})"
            text_parts.append(interactions_text)
        
        full_text = "\n\n".join(text_parts)
        
        # Store in ChromaDB
        await upsert_doc(
            rxcui=record["rxcui"],
            source="drugbank",
            id=record["id"],
            url=f"https://go.drugbank.com/drugs/{record['drug_name'].replace(' ', '-').lower()}",
            title=f"DrugBank: {record['drug_name']}",
            text=full_text
        )
    
    print("✅ DrugBank ETL completed!")
    return len(drugbank_records)

if __name__ == "__main__":
    asyncio.run(run())
