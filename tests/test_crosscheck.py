from app.models import RetrievedDoc, Source
from app.crosscheck import unify_with_crosscheck


def test_unify_disagreement():
    docs = [
        RetrievedDoc(rxcui="123", source=Source.DAILYMED, id="a", url=None, title="Atorvastatin", text="Dose: 10mg daily", score=0.9),
        RetrievedDoc(rxcui="123", source=Source.DRUGBANK, id="b", url=None, title="Atorvastatin", text="Dose: 20mg daily", score=0.8),
    ]
    ctx = unify_with_crosscheck(docs)
    assert ctx["disagreements"], "Should detect differing dosage values"
