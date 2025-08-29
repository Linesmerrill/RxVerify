"""Configuration settings for MedRAG application."""
import os
from typing import Optional

class Settings:
    """Application settings loaded from environment variables."""
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "1000"))
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))
    
    # ChromaDB Configuration
    CHROMADB_PATH: str = os.getenv("CHROMADB_PATH", "./chroma_db")
    CHROMADB_COLLECTION: str = os.getenv("CHROMADB_COLLECTION", "drug_docs")
    
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_WORKERS: int = int(os.getenv("API_WORKERS", "1"))
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Security Configuration
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required settings."""
        if not cls.OPENAI_API_KEY:
            print("⚠️  Warning: OPENAI_API_KEY not set. LLM responses will use fallback mode.")
        return True

# Global settings instance
settings = Settings()
