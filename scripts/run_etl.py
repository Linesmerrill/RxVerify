#!/usr/bin/env python3
"""Master ETL script to run all data source ingestion processes."""

import asyncio
import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.rxnorm import run as run_rxnorm
from etl.dailymed import run as run_dailymed
from etl.openfda import run as run_openfda
from etl.drugbank import run as run_drugbank

async def run_all_etl():
    """Run all ETL processes in sequence."""
    print("🚀 Starting Complete MedRAG ETL Pipeline")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    total_records = 0
    results = {}
    
    try:
        # 1. RxNorm (drug nomenclature and relationships)
        print("\n🏥 Step 1: RxNorm ETL")
        print("-" * 40)
        rxnorm_count = await run_rxnorm()
        results["rxnorm"] = rxnorm_count
        total_records += rxnorm_count
        print(f"✅ RxNorm: {rxnorm_count} records processed")
        
        # 2. DailyMed (FDA-approved drug labeling)
        print("\n🏥 Step 2: DailyMed ETL")
        print("-" * 40)
        dailymed_count = await run_dailymed()
        results["dailymed"] = dailymed_count
        total_records += dailymed_count
        print(f"✅ DailyMed: {dailymed_count} records processed")
        
        # 3. OpenFDA (drug safety and adverse events)
        print("\n🏥 Step 3: OpenFDA ETL")
        print("-" * 40)
        openfda_count = await run_openfda()
        results["openfda"] = openfda_count
        total_records += openfda_count
        print(f"✅ OpenFDA: {openfda_count} records processed")
        
        # 4. DrugBank (drug interactions and mechanisms)
        print("\n🏥 Step 4: DrugBank ETL")
        print("-" * 40)
        drugbank_count = await run_drugbank()
        results["drugbank"] = drugbank_count
        total_records += drugbank_count
        print(f"✅ DrugBank: {drugbank_count} records processed")
        
        # Summary
        print("\n" + "=" * 60)
        print("🎉 ETL PIPELINE COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"Total records processed: {total_records}")
        print("\nBreakdown by source:")
        for source, count in results.items():
            print(f"  {source.upper()}: {count} records")
        
        print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("\nYour MedRAG system now has a comprehensive drug knowledge base!")
        print("You can now ask questions about drugs and get intelligent, cited responses.")
        
        return results
        
    except Exception as e:
        print(f"\n❌ ETL Pipeline failed: {str(e)}")
        print("Check the logs above for details.")
        raise

async def run_single_etl(source: str):
    """Run a single ETL source."""
    print(f"🏥 Running {source.upper()} ETL only...")
    
    if source == "rxnorm":
        count = await run_rxnorm()
    elif source == "dailymed":
        count = await run_dailymed()
    elif source == "openfda":
        count = await run_openfda()
    elif source == "drugbank":
        count = await run_drugbank()
    else:
        print(f"❌ Unknown source: {source}")
        return
    
    print(f"✅ {source.upper()}: {count} records processed")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run MedRAG ETL pipeline")
    parser.add_argument("--source", choices=["rxnorm", "dailymed", "openfda", "drugbank"], 
                       help="Run only a specific ETL source")
    
    args = parser.parse_args()
    
    if args.source:
        asyncio.run(run_single_etl(args.source))
    else:
        asyncio.run(run_all_etl())
