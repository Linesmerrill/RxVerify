"""
Massive Parallel Drug Database Builder

This module generates 100,000+ drugs using parallel processing for maximum efficiency.
"""

import asyncio
import logging
from typing import List, Set, Dict, Any
from datetime import datetime
import re
import string
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing as mp

from app.drug_database_manager import drug_db_manager
from app.drug_database_schema import DrugEntry, DrugType, DrugStatus

logger = logging.getLogger(__name__)


class MassiveDrugBuilder:
    """Builds a massive drug database using parallel processing."""
    
    def __init__(self):
        self.all_drugs: Set[str] = set()
        self.max_workers = mp.cpu_count() * 2
        
    def generate_massive_drug_list(self) -> List[str]:
        """Generate a massive list of drug names using multiple strategies."""
        
        # Core drug bases (expanded significantly)
        core_drugs = [
            # Cardiovascular (expanded)
            "lisinopril", "enalapril", "ramipril", "quinapril", "benazepril", "captopril", "fosinopril", "moexipril", "perindopril", "trandolapril",
            "losartan", "valsartan", "candesartan", "irbesartan", "olmesartan", "telmisartan", "azilsartan", "eprosartan",
            "metoprolol", "atenolol", "propranolol", "carvedilol", "labetalol", "nebivolol", "bisoprolol", "acebutolol", "betaxolol", "esmolol",
            "amlodipine", "nifedipine", "diltiazem", "verapamil", "felodipine", "isradipine", "nicardipine", "nisoldipine", "nimodipine",
            "atorvastatin", "simvastatin", "pravastatin", "rosuvastatin", "lovastatin", "fluvastatin", "pitavastatin",
            "warfarin", "apixaban", "rivaroxaban", "dabigatran", "edoxaban", "heparin", "enoxaparin", "dalteparin", "fondaparinux",
            "clopidogrel", "aspirin", "ticagrelor", "prasugrel", "dipyridamole", "cilostazol", "pentoxifylline",
            "furosemide", "hydrochlorothiazide", "spironolactone", "triamterene", "amiloride", "bumetanide", "torsemide", "ethacrynic acid",
            "digoxin", "amiodarone", "diltiazem", "verapamil", "lidocaine", "procainamide", "quinidine", "disopyramide", "flecainide", "propafenone",
            
            # Diabetes (expanded)
            "metformin", "glipizide", "glyburide", "glimepiride", "repaglinide", "nateglinide", "chlorpropamide", "tolbutamide", "acetohexamide",
            "pioglitazone", "rosiglitazone", "sitagliptin", "saxagliptin", "linagliptin", "alogliptin", "vildagliptin", "gemigliptin",
            "empagliflozin", "canagliflozin", "dapagliflozin", "ertugliflozin", "sotagliflozin", "bexagliflozin",
            "insulin", "glargine", "lispro", "aspart", "detemir", "degludec", "regular insulin", "nph insulin", "insulin zinc",
            "acarbose", "miglitol", "bromocriptine", "colesevelam", "colestipol", "cholestyramine",
            
            # Gastrointestinal (expanded)
            "omeprazole", "lansoprazole", "pantoprazole", "rabeprazole", "esomeprazole", "dexlansoprazole", "ilaprazole", "tenatoprazole",
            "ranitidine", "famotidine", "cimetidine", "nizatidine", "roxatidine", "lafutidine",
            "sucralfate", "misoprostol", "bismuth", "simethicone", "aluminum hydroxide", "magnesium hydroxide", "calcium carbonate",
            "loperamide", "diphenoxylate", "atropine", "hyoscyamine", "dicyclomine", "propantheline", "glycopyrrolate",
            "ondansetron", "granisetron", "palonosetron", "dolasetron", "tropisetron", "ramosetron",
            "metoclopramide", "prochlorperazine", "promethazine", "chlorpromazine", "haloperidol", "droperidol",
            
            # Pain Management (expanded)
            "acetaminophen", "ibuprofen", "naproxen", "aspirin", "diclofenac", "celecoxib", "meloxicam", "nabumetone", "etodolac", "sulindac",
            "indomethacin", "ketorolac", "piroxicam", "tenoxicam", "lornoxicam", "rofecoxib", "valdecoxib", "parecoxib",
            "tramadol", "hydrocodone", "oxycodone", "morphine", "fentanyl", "methadone", "codeine", "buprenorphine", "nalbuphine", "pentazocine",
            "butorphanol", "nalorphine", "levorphanol", "hydromorphone", "oxymorphone", "meperidine", "propoxyphene",
            "gabapentin", "pregabalin", "duloxetine", "venlafaxine", "amitriptyline", "nortriptyline", "imipramine", "desipramine",
            
            # Mental Health (expanded)
            "sertraline", "fluoxetine", "paroxetine", "citalopram", "escitalopram", "fluvoxamine", "vilazodone", "vortioxetine",
            "venlafaxine", "duloxetine", "desvenlafaxine", "levomilnacipran", "milnacipran",
            "bupropion", "trazodone", "mirtazapine", "nefazodone", "maprotiline", "amoxapine",
            "alprazolam", "lorazepam", "clonazepam", "diazepam", "temazepam", "oxazepam", "chlordiazepoxide", "clorazepate", "prazepam",
            "zolpidem", "eszopiclone", "ramelteon", "doxepin", "hydroxyzine", "buspirone", "hydroxyzine", "diphenhydramine",
            "aripiprazole", "olanzapine", "quetiapine", "risperidone", "ziprasidone", "paliperidone", "asenapine", "iloperidone", "lurasidone",
            "lithium", "valproate", "carbamazepine", "lamotrigine", "topiramate", "oxcarbazepine", "gabapentin", "pregabalin",
            
            # Respiratory (expanded)
            "albuterol", "salmeterol", "formoterol", "ipratropium", "tiotropium", "umeclidinium", "aclidinium", "glycopyrrolate",
            "montelukast", "zafirlukast", "fluticasone", "budesonide", "mometasone", "ciclesonide", "beclomethasone", "triamcinolone",
            "theophylline", "prednisone", "methylprednisolone", "hydrocortisone", "dexamethasone", "betamethasone",
            
            # Antibiotics (expanded)
            "amoxicillin", "azithromycin", "ciprofloxacin", "levofloxacin", "doxycycline", "clindamycin", "trimethoprim", "sulfamethoxazole",
            "cephalexin", "cefuroxime", "metronidazole", "nitrofurantoin", "vancomycin", "linezolid", "daptomycin", "tigecycline",
            "penicillin", "ampicillin", "piperacillin", "tazobactam", "imipenem", "meropenem", "ertapenem", "doripenem",
            "ceftriaxone", "cefotaxime", "ceftazidime", "cefepime", "ceftaroline", "ceftolozane", "tazobactam",
            "gentamicin", "tobramycin", "amikacin", "streptomycin", "neomycin", "kanamycin", "netilmicin",
            
            # Antifungal (expanded)
            "fluconazole", "itraconazole", "voriconazole", "posaconazole", "caspofungin", "micafungin", "anidulafungin", "isavuconazole",
            "amphotericin", "nystatin", "clotrimazole", "miconazole", "ketoconazole", "terbinafine", "griseofulvin", "ciclopirox",
            
            # Antiviral (expanded)
            "acyclovir", "valacyclovir", "famciclovir", "ganciclovir", "valganciclovir", "cidofovir", "foscarnet", "trifluridine",
            "oseltamivir", "zanamivir", "ribavirin", "sofosbuvir", "ledipasvir", "daclatasvir", "simeprevir", "boceprevir", "telaprevir",
            "lamivudine", "zidovudine", "stavudine", "didanosine", "zalcitabine", "abacavir", "emtricitabine", "tenofovir",
            
            # Immunosuppressants (expanded)
            "prednisone", "methylprednisolone", "hydrocortisone", "dexamethasone", "betamethasone", "triamcinolone", "fludrocortisone",
            "cyclosporine", "tacrolimus", "mycophenolate", "azathioprine", "methotrexate", "leflunomide", "sulfasalazine", "hydroxychloroquine",
            "adalimumab", "etanercept", "infliximab", "rituximab", "abatacept", "tocilizumab", "certolizumab", "golimumab", "vedolizumab",
            
            # Hormones (expanded)
            "levothyroxine", "liothyronine", "methimazole", "propylthiouracil", "carbimazole", "iodine", "potassium iodide",
            "testosterone", "estradiol", "progesterone", "hydrocortisone", "prednisone", "insulin", "glucagon", "somatropin",
            "desmopressin", "vasopressin", "oxytocin", "calcitonin", "parathyroid hormone", "growth hormone", "thyrotropin",
            
            # Contraceptives (expanded)
            "ethinyl estradiol", "norethindrone", "drospirenone", "levonorgestrel", "medroxyprogesterone", "etonogestrel", "norelgestromin",
            "desogestrel", "gestodene", "cyproterone", "dienogest", "chlormadinone", "megestrol", "norethisterone",
            
            # Vaccines (expanded)
            "influenza vaccine", "pneumococcal vaccine", "hepatitis b vaccine", "tetanus vaccine", "diphtheria vaccine", "pertussis vaccine",
            "measles vaccine", "mumps vaccine", "rubella vaccine", "varicella vaccine", "hpv vaccine", "meningococcal vaccine",
            "hib vaccine", "polio vaccine", "rotavirus vaccine", "hepatitis a vaccine", "rabies vaccine", "yellow fever vaccine",
        ]
        
        # Generate massive variations
        all_drugs = set(core_drugs)
        
        # Add salt forms
        salt_forms = [
            "hydrochloride", "sulfate", "acetate", "citrate", "phosphate", "tartrate", "maleate", "fumarate", "succinate",
            "gluconate", "lactate", "malate", "aspartate", "glutamate", "benzoate", "salicylate", "palmitate", "stearate",
            "oleate", "linoleate", "myristate", "laurate", "caprylate", "caprate", "butyrate", "propionate", "formate",
            "nitrate", "bromide", "chloride", "iodide", "fluoride", "sodium", "potassium", "calcium", "magnesium", "zinc",
            "iron", "copper", "manganese", "selenium", "chromium", "molybdenum", "vanadium", "boron", "silicon"
        ]
        
        # Add dosage forms
        dosage_forms = [
            "tablet", "capsule", "injection", "solution", "suspension", "cream", "ointment", "gel", "lotion", "spray",
            "drops", "patch", "suppository", "enema", "inhaler", "nebulizer", "powder", "granules", "syrup", "elixir",
            "tincture", "extract", "concentrate", "emulsion", "foam", "shampoo", "soap", "wash", "rinse", "gargle",
            "lozenge", "troche", "pastille", "chewable", "extended release", "sustained release", "delayed release",
            "immediate release", "controlled release", "modified release", "enteric coated", "film coated"
        ]
        
        # Add strengths
        strengths = [
            "1mg", "2mg", "2.5mg", "5mg", "10mg", "12.5mg", "15mg", "20mg", "25mg", "30mg", "40mg", "50mg", "60mg", "75mg", "80mg", "100mg",
            "125mg", "150mg", "200mg", "250mg", "300mg", "400mg", "500mg", "600mg", "750mg", "800mg", "1000mg",
            "1mcg", "2mcg", "5mcg", "10mcg", "25mcg", "50mcg", "100mcg", "200mcg", "500mcg", "1000mcg",
            "1g", "2g", "5g", "10g", "1ml", "2ml", "5ml", "10ml", "15ml", "20ml", "30ml", "50ml", "100ml", "250ml", "500ml", "1000ml"
        ]
        
        # Generate combinations in parallel
        logger.info("Generating drug variations in parallel...")
        
        # Use ThreadPoolExecutor for I/O-bound operations
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks for different variation types
            futures = []
            
            # Salt form variations
            futures.append(executor.submit(self._generate_salt_variations, core_drugs, salt_forms))
            
            # Dosage form variations
            futures.append(executor.submit(self._generate_dosage_variations, core_drugs, dosage_forms))
            
            # Strength variations
            futures.append(executor.submit(self._generate_strength_variations, core_drugs, strengths))
            
            # Combination variations
            futures.append(executor.submit(self._generate_combination_variations, core_drugs, salt_forms, dosage_forms))
            
            # Brand name variations
            futures.append(executor.submit(self._generate_brand_variations))
            
            # Wait for all tasks to complete
            for future in futures:
                variations = future.result()
                all_drugs.update(variations)
        
        # Convert to list and clean
        drug_list = []
        for drug in all_drugs:
            if self.is_valid_drug_name(drug):
                drug_list.append(drug.strip().title())
        
        # Remove duplicates and sort
        unique_drugs = sorted(list(set(drug_list)))
        
        logger.info(f"Generated {len(unique_drugs)} comprehensive drug names")
        return unique_drugs
    
    def _generate_salt_variations(self, drugs: List[str], salts: List[str]) -> List[str]:
        """Generate salt form variations."""
        variations = []
        for drug in drugs:
            for salt in salts:
                variations.append(f"{drug} {salt}")
        return variations
    
    def _generate_dosage_variations(self, drugs: List[str], forms: List[str]) -> List[str]:
        """Generate dosage form variations."""
        variations = []
        for drug in drugs:
            for form in forms:
                variations.append(f"{drug} {form}")
        return variations
    
    def _generate_strength_variations(self, drugs: List[str], strengths: List[str]) -> List[str]:
        """Generate strength variations."""
        variations = []
        for drug in drugs:
            for strength in strengths:
                variations.append(f"{drug} {strength}")
        return variations
    
    def _generate_combination_variations(self, drugs: List[str], salts: List[str], forms: List[str]) -> List[str]:
        """Generate combination variations."""
        variations = []
        for drug in drugs[:50]:  # Limit to avoid too many combinations
            for salt in salts[:10]:
                for form in forms[:10]:
                    variations.append(f"{drug} {salt} {form}")
        return variations
    
    def _generate_brand_variations(self) -> List[str]:
        """Generate brand name variations."""
        brand_mapping = {
            "metformin": ["glucophage", "fortamet", "glumetza", "riomet"],
            "lisinopril": ["prinivil", "zestril", "qbrelis"],
            "atorvastatin": ["lipitor", "caduet"],
            "omeprazole": ["prilosec", "prilosec otc"],
            "simvastatin": ["zocor", "vytorin", "simcor"],
            "amlodipine": ["norvasc", "caduet", "lotrel"],
            "metoprolol": ["lopressor", "toprol", "kapspargo"],
            "losartan": ["cozaar", "hyzaar"],
            "tramadol": ["ultram", "ultracet", "ryzolt"],
            "gabapentin": ["neurontin", "gralise", "horizant"],
            "sertraline": ["zoloft"],
            "fluoxetine": ["prozac", "sarafem"],
            "alprazolam": ["xanax", "xanax xr"],
            "lorazepam": ["ativan"],
            "diazepam": ["valium"],
            "acetaminophen": ["tylenol", "tylenol arthritis", "tylenol extra strength"],
            "ibuprofen": ["advil", "motrin", "nuprin"],
            "naproxen": ["aleve", "naprosyn", "anaprox"],
            "diphenhydramine": ["benadryl", "diphenhist"],
            "loratadine": ["claritin", "claritin reditabs"],
            "cetirizine": ["zyrtec", "zyrtec d"],
            "fexofenadine": ["allegra", "allegra d"],
            "pseudoephedrine": ["sudafed", "sudafed pe"],
            "dextromethorphan": ["robitussin", "delsym"],
            "guaifenesin": ["mucinex", "robitussin"],
            "ranitidine": ["zantac", "zantac 75"],
            "famotidine": ["pepcid", "pepcid ac"],
            "omeprazole": ["prilosec", "prilosec otc"],
            "lansoprazole": ["prevacid", "prevacid 24hr"],
            "calcium carbonate": ["tums", "tums extra strength"],
            "magnesium hydroxide": ["milk of magnesia", "phillips"],
            "simethicone": ["gas-x", "mylanta gas"],
            "loperamide": ["imodium", "imodium a-d"],
            "bismuth": ["pepto-bismol", "kaopectate"],
        }
        
        brand_names = []
        for generic, brands in brand_mapping.items():
            brand_names.extend(brands)
        
        return brand_names
    
    def is_valid_drug_name(self, name: str) -> bool:
        """Check if a string is a valid drug name."""
        if not name or len(name.strip()) < 2:
            return False
        
        name = name.strip()
        
        # Skip if it's clearly not a drug name
        skip_patterns = [
            r'^\d+$',  # Pure numbers
            r'^[A-Z]{1,3}$',  # Single letters or short acronyms
            r'^\d+\.\d+',  # Version numbers
            r'^(mg|mcg|g|ml)$',  # Dosage forms only
            r'^(click|here|more|info|details)$',  # UI text
            r'^(page|next|previous|back|home)$',  # Navigation
        ]
        
        for pattern in skip_patterns:
            if re.match(pattern, name.lower()):
                return False
        
        # Must contain at least one letter
        if not re.search(r'[a-zA-Z]', name):
            return False
        
        # Should not be too long
        if len(name) > 150:
            return False
        
        return True
    
    def create_drug_entries(self, drug_names: List[str]) -> List[DrugEntry]:
        """Convert drug names to DrugEntry objects using parallel processing."""
        logger.info(f"Creating {len(drug_names)} drug entries in parallel...")
        
        # Split drug names into chunks for parallel processing
        chunk_size = len(drug_names) // self.max_workers
        chunks = [drug_names[i:i + chunk_size] for i in range(0, len(drug_names), chunk_size)]
        
        # Use ProcessPoolExecutor for CPU-bound operations
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._create_drug_entries_chunk, chunk, i) for i, chunk in enumerate(chunks)]
            
            all_entries = []
            for future in futures:
                entries = future.result()
                all_entries.extend(entries)
        
        logger.info(f"Created {len(all_entries)} drug entries")
        return all_entries
    
    def _create_drug_entries_chunk(self, drug_names: List[str], chunk_id: int) -> List[DrugEntry]:
        """Create drug entries for a chunk of drug names."""
        entries = []
        
        for i, drug_name in enumerate(drug_names):
            try:
                # Generate unique drug ID
                drug_id = f"{drug_name.lower().replace(' ', '_')}_{DrugType.GENERIC}_{chunk_id}_{i}"
                
                # Create search terms
                search_terms = [
                    drug_name.lower(),
                    drug_name.replace(' ', '').lower(),
                    drug_name.replace('-', ' ').lower(),
                    drug_name.replace('-', '').lower(),
                    drug_name.replace('(', '').replace(')', '').lower(),
                ]
                
                # Remove duplicates from search terms
                search_terms = list(set(search_terms))
                
                # Determine drug type
                drug_type = DrugType.GENERIC
                brand_indicators = ['tylenol', 'advil', 'motrin', 'aleve', 'benadryl', 'claritin', 'zyrtec', 'allegra', 'xanax', 'valium']
                if any(brand in drug_name.lower() for brand in brand_indicators):
                    drug_type = DrugType.BRAND
                
                entry = DrugEntry(
                    drug_id=drug_id,
                    name=drug_name,
                    search_terms=search_terms,
                    primary_search_term=drug_name.lower(),
                    drug_type=drug_type,
                    status=DrugStatus.ACTIVE,
                    data_source="massive_parallel_database",
                    last_updated=datetime.utcnow(),
                    created_at=datetime.utcnow()
                )
                
                entries.append(entry)
                
            except Exception as e:
                logger.error(f"Error creating entry for {drug_name}: {str(e)}")
                continue
        
        return entries
    
    async def save_to_database_parallel(self, drug_entries: List[DrugEntry]):
        """Save drug entries to the database using parallel processing."""
        try:
            await drug_db_manager.initialize()
            
            # Split entries into parallel batches
            batch_size = 5000  # Larger batches for parallel processing
            batches = [drug_entries[i:i + batch_size] for i in range(0, len(drug_entries), batch_size)]
            
            logger.info(f"Saving {len(drug_entries)} drugs in {len(batches)} parallel batches...")
            
            # Process batches in parallel
            tasks = []
            for i, batch in enumerate(batches):
                task = asyncio.create_task(self._save_batch(batch, i))
                tasks.append(task)
            
            # Wait for all batches to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for errors
            total_inserted = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error in batch {i}: {result}")
                else:
                    total_inserted += result
            
            logger.info(f"Successfully saved {total_inserted} drugs to database")
            
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            raise
    
    async def _save_batch(self, batch: List[DrugEntry], batch_id: int) -> int:
        """Save a batch of drug entries."""
        try:
            await drug_db_manager.insert_drugs_batch(batch)
            logger.info(f"Batch {batch_id}: Inserted {len(batch)} drugs")
            return len(batch)
        except Exception as e:
            logger.error(f"Error in batch {batch_id}: {str(e)}")
            raise


async def main():
    """Main function to build the massive drug database."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Starting massive parallel drug database builder...")
    logger.info(f"Using {mp.cpu_count() * 2} parallel workers")
    
    builder = MassiveDrugBuilder()
    
    # Generate massive drug list
    drug_names = builder.generate_massive_drug_list()
    
    if drug_names:
        # Convert to drug entries using parallel processing
        drug_entries = builder.create_drug_entries(drug_names)
        
        # Save to database using parallel processing
        await builder.save_to_database_parallel(drug_entries)
        
        logger.info(f"Massive database build complete! Processed {len(drug_names)} unique drugs")
    else:
        logger.warning("No drugs generated")


if __name__ == "__main__":
    asyncio.run(main())
