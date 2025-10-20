"""Configuration for embedding usage to manage OpenAI API quota."""

from app.config import settings

class EmbeddingConfig:
    """Configuration for embedding usage and quota management."""
    
    def __init__(self):
        # Check if embeddings should be disabled due to quota issues
        self.disabled = settings.DISABLE_EMBEDDINGS
        
        # Rate limiting settings
        self.max_requests_per_minute = 60  # Could be made configurable
        self.cache_size_limit = 1000  # Could be made configurable
        
        # Fallback settings
        self.use_fallback_only = settings.USE_FALLBACK_EMBEDDINGS
        
    def should_use_embeddings(self) -> bool:
        """Check if embeddings should be used based on configuration."""
        return not self.disabled and not self.use_fallback_only
    
    def get_fallback_message(self) -> str:
        """Get message explaining why fallback embeddings are being used."""
        if self.disabled:
            return "Embeddings disabled due to quota management"
        elif self.use_fallback_only:
            return "Using fallback embeddings to conserve API quota"
        else:
            return "Using fallback embeddings due to API error"

# Global configuration instance
embedding_config = EmbeddingConfig()
