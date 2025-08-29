"""Logging configuration for RxVerify application."""
import logging
import sys
import os
from datetime import datetime
from app.config import settings

def setup_logging():
    """Configure logging for the application."""
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler for production
    if settings.LOG_LEVEL.upper() == "INFO":
        try:
            file_handler = logging.FileHandler(f"logs/rxverify_{datetime.now().strftime('%Y%m%d')}.log")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            # If file logging fails, just log to console
            print(f"Warning: Could not set up file logging: {e}")
    
    return root_logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module."""
    return logging.getLogger(name)

# Initialize logging
try:
    logger = setup_logging()
except Exception as e:
    # Fallback to basic logging if setup fails
    print(f"Warning: Logging setup failed: {e}")
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
