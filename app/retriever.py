"""Real-time medical information retrieval for RxVerify.

This module now queries medical databases in real-time instead of searching pre-loaded data.
"""

from typing import List
from app.medical_apis import get_medical_api_client
from app.models import RetrievedDoc
import logging

logger = logging.getLogger(__name__)

async def retrieve(question: str, top_k: int = 6) -> List[RetrievedDoc]:
    """Retrieve medical information from live databases in real-time.
    
    This function now queries RxNorm, DailyMed, OpenFDA, and DrugBank APIs
    instead of searching a pre-loaded vector database.
    """
    logger.info(f"Starting real-time retrieval for: {question}")
    
    try:
        # Get the medical API client
        api_client = await get_medical_api_client()
        
        # Check if this is a side effects query to prioritize relevant sources
        is_side_effects_query = any(term in question.lower() for term in [
            "side effect", "side effects", "adverse", "reaction", "reactions",
            "what should i expect", "what to expect", "symptoms", "problems"
        ])
        
        if is_side_effects_query:
            # For side effects, prioritize DailyMed and OpenFDA with higher limits
            logger.info("Side effects query detected - prioritizing DailyMed and OpenFDA")
            # Get more from DailyMed and OpenFDA, fewer from RxNorm and DrugBank
            daily_med_limit = max(3, top_k // 3)
            openfda_limit = max(3, top_k // 3)
            rxnorm_limit = max(1, top_k // 6)
            drugbank_limit = max(1, top_k // 6)
        else:
            # Standard distribution
            daily_med_limit = max(2, top_k // 4)
            openfda_limit = max(2, top_k // 4)
            rxnorm_limit = max(2, top_k // 4)
            drugbank_limit = max(2, top_k // 4)
        
        # Search all medical databases with appropriate limits
        docs = await api_client.search_all_sources_custom(
            question, 
            daily_med_limit, 
            openfda_limit, 
            rxnorm_limit, 
            drugbank_limit
        )
        
        # Apply relevance filtering to ensure quality
        # Filter out documents with very low scores or empty content
        filtered_docs = []
        for doc in docs:
            if doc.score > 0.5 and doc.text.strip():  # Basic quality filter
                filtered_docs.append(doc)
        
        # For side effects queries, prioritize documents with side effects content
        if is_side_effects_query:
            def side_effects_score(doc):
                score = doc.score
                # Boost score if document contains side effects keywords
                side_effects_keywords = ["adverse", "reaction", "side effect", "warning", "precaution"]
                text_lower = doc.text.lower()
                for keyword in side_effects_keywords:
                    if keyword in text_lower:
                        score += 0.2  # Boost score for relevant content
                return score
            
            # Sort by side effects relevance
            filtered_docs.sort(key=side_effects_score, reverse=True)
        
        # Limit to requested number of results
        final_docs = filtered_docs[:top_k]
        
        logger.info(f"Retrieved {len(final_docs)} relevant documents from live medical databases")
        
        return final_docs
        
    except Exception as e:
        logger.error(f"Error during real-time retrieval: {e}")
        # Return empty list on error - in production you might want to fall back to cached data
        return []
