from collections import defaultdict
from typing import List, Dict
from app.models import RetrievedDoc, UnifiedDrugRecord, SourceRef, Source, FieldEvidence

# Minimal demo: parse fields from RetrievedDoc.text via naive heuristics/regex in real life.

def parse_doc(doc: RetrievedDoc) -> Dict[str, List[FieldEvidence]]:
    # TODO: replace with structured parsing per source (e.g., DailyMed XML)
    evid = FieldEvidence(value=doc.text[:280], sources=[SourceRef(source=doc.source, id=doc.id, url=doc.url)])
    return {"dosage": [evid]}  # example only


def unify_with_crosscheck(docs: List[RetrievedDoc]) -> Dict:
    # Group by RxCUI (unknown RxCUI goes under "unknown")
    groups: Dict[str, List[RetrievedDoc]] = defaultdict(list)
    for d in docs:
        groups[d.rxcui or "unknown"].append(d)

    unified_records = []
    for rxcui, items in groups.items():
        name = best_name(items)
        fields: Dict[str, List[FieldEvidence]] = defaultdict(list)
        refs = []
        for d in items:
            parsed = parse_doc(d)
            for k, v in parsed.items():
                fields[k].extend(v)
            refs.append(SourceRef(source=d.source, id=d.id, url=d.url))
        unified_records.append(UnifiedDrugRecord(
            rxcui=rxcui, name=name, references=refs,
            dosage=fields.get("dosage", []),
        ).dict())

    # Simple disagreement detection (per field, compare unique values)
    disagreements = []
    for rec in unified_records:
        for field in ("dosage", "warnings", "interactions"):
            field_values = rec.get(field, [])
            if isinstance(field_values, list) and len(field_values) > 0:
                vals = {str(ev.get("value", "")).strip() for ev in field_values}
                if len(vals) > 1:
                    disagreements.append({"rxcui": rec["rxcui"], "field": field, "values": list(vals)})

    return {"records": unified_records, "disagreements": disagreements}


def best_name(items: List[RetrievedDoc]) -> str:
    # Prefer RxNorm title, else first non‑empty
    for d in items:
        if d.source == Source.RXNORM and d.title:
            return d.title
    for d in items:
        if d.title:
            return d.title
    return "Unknown Drug"
