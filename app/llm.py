import os
from typing import Dict, List
from openai import OpenAI

# Initialize OpenAI client (will be None if no API key)
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

from app.prompts import SYSTEM_PROMPT

async def generate_drug_response(question: str, context: Dict) -> str:
    """
    Generate a comprehensive drug information response using OpenAI.
    
    Args:
        question: User's question about drugs
        context: Retrieved and cross-checked drug information
        
    Returns:
        Formatted response with citations and source information
    """
    
    # Check if OpenAI client is available
    if not client:
        return _generate_fallback_response(question, context)
    
    # Format the context for the LLM
    context_text = _format_context_for_llm(context)
    
    # Create the user message with context
    user_message = f"""
Question: {question}

Context Information:
{context_text}

IMPORTANT INSTRUCTIONS:
1. Answer based ONLY on the provided context - NO HALLUCINATIONS
2. If asked about side effects, provide COMPREHENSIVE coverage including:
   - Most common and important side effects FIRST (e.g., muscle pain for statins)
   - Serious side effects and warnings
   - Organ system breakdown (musculoskeletal, liver, gastrointestinal, etc.)
   - Use clear section headers, bullet points, and organized structure
3. If information is missing, clearly state "Information not available in the provided sources"
4. Always include inline citations like [RxNorm:ID], [DailyMed:ID], [OpenFDA:ID], [DrugBank:ID]
5. If sources disagree, clearly indicate the differences with source citations
6. Be honest about what you know and what you don't know
7. Structure your response with clear headings and bullet points for readability

Please provide a comprehensive, well-organized answer based on the available information.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # You can change this to gpt-4, gpt-3.5-turbo, etc.
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,  # Low temperature for factual responses
            max_tokens=2000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        # Fallback to a structured response if LLM fails
        return _generate_fallback_response(question, context)

def _format_context_for_llm(context: Dict) -> str:
    """Format the context data for LLM consumption."""
    
    if not context.get("records"):
        return "No relevant drug information found."
    
    formatted_context = []
    
    for record in context["records"]:
        # Drug header
        drug_info = f"Drug: {record['name']} (RxCUI: {record['rxcui']})\n"
        
        # Add each field with source citations
        for field_name in ["dosage", "indications", "warnings", "adverse_events", "interactions", "mechanism"]:
            field_data = record.get(field_name, [])
            if field_data:
                field_text = f"{field_name.title()}: "
                field_entries = []
                
                for entry in field_data:
                    if isinstance(entry, dict):
                        value = entry.get("value", "")
                        sources = entry.get("sources", [])
                        source_citations = []
                        
                        for source in sources:
                            if isinstance(source, dict):
                                source_name = source.get("source", "").upper()
                                source_id = source.get("id", "")
                                source_citations.append(f"[{source_name}:{source_id}]")
                        
                        if source_citations:
                            field_entries.append(f"{value} {' '.join(source_citations)}")
                        else:
                            field_entries.append(value)
                
                if field_entries:
                    field_text += "; ".join(field_entries)
                    drug_info += field_text + "\n"
        
        # Add source references
        if record.get("references"):
            refs = []
            for ref in record["references"]:
                if isinstance(ref, dict):
                    source_name = ref.get("source", "").upper()
                    source_id = ref.get("id", "")
                    refs.append(f"[{source_name}:{source_id}]")
            
            if refs:
                drug_info += f"Sources: {' '.join(refs)}\n"
        
        formatted_context.append(drug_info)
    
    # Add disagreement information if any
    if context.get("disagreements"):
        formatted_context.append("\n⚠️  SOURCE DISAGREEMENTS:")
        for disagreement in context["disagreements"]:
            rxcui = disagreement.get("rxcui", "Unknown")
            field = disagreement.get("field", "Unknown")
            values = disagreement.get("values", [])
            
            formatted_context.append(f"  {field.title()} for RxCUI {rxcui}:")
            for value in values:
                formatted_context.append(f"    - {value}")
    
    return "\n".join(formatted_context)

def _generate_fallback_response(question: str, context: Dict) -> str:
    """Generate a fallback response if LLM fails."""
    
    if not context.get("records"):
        return f"I'm sorry, I couldn't find any information about '{question}'. Please try rephrasing your question or consult a healthcare professional."
    
    # Simple template-based response
    response = f"Based on the available information about your question: '{question}'\n\n"
    
    for record in context["records"]:
        response += f"Drug: {record['name']}\n"
        
        # Add basic dosage info if available
        if record.get("dosage"):
            response += "Dosage Information:\n"
            for dosage_entry in record["dosage"]:
                if isinstance(dosage_entry, dict):
                    value = dosage_entry.get("value", "")
                    sources = dosage_entry.get("sources", [])
                    source_citations = []
                    
                    for source in sources:
                        if isinstance(source, dict):
                            source_name = source.get("source", "").upper()
                            source_id = source.get("id", "")
                            source_citations.append(f"[{source_name}:{source_id}]")
                    
                    if source_citations:
                        response += f"  - {value} {' '.join(source_citations)}\n"
                    else:
                        response += f"  - {value}\n"
        
        response += "\n"
    
    response += "\nNote: This is a fallback response. For the most accurate information, please consult a healthcare professional."
    return response
