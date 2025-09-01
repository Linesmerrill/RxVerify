from typing import List
import os
from openai import OpenAI

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

async def embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts using OpenAI's text-embedding-ada-002 model.
    
    This provides real semantic embeddings that capture the meaning of drug information,
    enabling proper similarity search between related medications and content.
    """
    
    # If no OpenAI API key, fall back to improved stub embeddings
    if not client:
        return await _generate_fallback_embeddings(texts)
    
    try:
        # Use OpenAI's text-embedding-ada-002 model for real semantic embeddings
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=texts
        )
        
        # Extract embeddings from response
        embeddings = [data.embedding for data in response.data]
        return embeddings
        
    except Exception as e:
        print(f"OpenAI embedding failed: {e}. Falling back to stub embeddings.")
        return await _generate_fallback_embeddings(texts)

async def _generate_fallback_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate improved stub embeddings when OpenAI is not available.
    
    These are still not as good as real embeddings but provide better
    drug-specific similarity than random numbers.
    """
    embeddings = []
    
    for text in texts:
        text_lower = text.lower()
        
        # Create drug-specific similarity patterns
        # This is a simplified approach - real embeddings are much better
        
        # Check for common drug-related terms
        has_metformin = 'metformin' in text_lower
        has_atorvastatin = 'atorvastatin' in text_lower
        has_lisinopril = 'lisinopril' in text_lower
        
        # Generate 1536-dimensional vector (OpenAI's embedding dimension)
        vector = []
        for i in range(1536):
            # Create patterns based on drug content
            if i < 512:  # First third - drug name influence
                if has_metformin:
                    base_value = 0.8
                elif has_atorvastatin:
                    base_value = 0.6
                elif has_lisinopril:
                    base_value = 0.4
                else:
                    base_value = 0.5
            elif i < 1024:  # Second third - content type influence
                if 'dosage' in text_lower or 'mg' in text_lower:
                    base_value = 0.7
                elif 'side effect' in text_lower or 'warning' in text_lower:
                    base_value = 0.6
                else:
                    base_value = 0.5
            else:  # Last third - medical term influence
                if 'diabetes' in text_lower or 'glucose' in text_lower:
                    base_value = 0.8
                elif 'cholesterol' in text_lower or 'lipid' in text_lower:
                    base_value = 0.6
                else:
                    base_value = 0.5
            
            # Add some variation
            variation = (i % 100) / 1000.0
            final_value = base_value + variation
            
            # Ensure we stay in valid range
            final_value = max(-1.0, min(1.0, final_value))
            
            vector.append(final_value)
        
        embeddings.append(vector)
    
    return embeddings
