from typing import List
import os
import hashlib
import json
from openai import OpenAI
from app.embedding_config import embedding_config

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

# Simple in-memory cache for embeddings to reduce API calls
_embedding_cache = {}

async def embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts using OpenAI's text-embedding-ada-002 model.
    
    This provides real semantic embeddings that capture the meaning of drug information,
    enabling proper similarity search between related medications and content.
    
    Includes caching to reduce API calls and quota usage.
    """
    
    # Check configuration for embedding usage
    if not embedding_config.should_use_embeddings():
        print(f"Using fallback embeddings: {embedding_config.get_fallback_message()}")
        return await _generate_fallback_embeddings(texts)
    
    # If no OpenAI API key, fall back to improved stub embeddings
    if not client:
        return await _generate_fallback_embeddings(texts)
    
    # Check cache first to reduce API calls
    embeddings = []
    texts_to_fetch = []
    text_indices = []
    
    for i, text in enumerate(texts):
        # Create cache key from text hash
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        if text_hash in _embedding_cache:
            # Use cached embedding
            embeddings.append(_embedding_cache[text_hash])
        else:
            # Need to fetch this embedding
            texts_to_fetch.append(text)
            text_indices.append(i)
            embeddings.append(None)  # Placeholder
    
    # Only make API call for texts not in cache
    if texts_to_fetch:
        try:
            # Use OpenAI's text-embedding-ada-002 model for real semantic embeddings
            response = client.embeddings.create(
                model="text-embedding-ada-002",
                input=texts_to_fetch
            )
            
            # Extract embeddings from response and cache them
            for i, data in enumerate(response.data):
                embedding = data.embedding
                text_hash = hashlib.md5(texts_to_fetch[i].encode()).hexdigest()
                _embedding_cache[text_hash] = embedding
                embeddings[text_indices[i]] = embedding
            
        except Exception as e:
            print(f"OpenAI embedding failed: {e}. Falling back to stub embeddings.")
            # Fill in failed embeddings with fallback
            for i, text in enumerate(texts_to_fetch):
                fallback_embedding = await _generate_fallback_embeddings([text])
                embeddings[text_indices[i]] = fallback_embedding[0]
    
    return embeddings

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
