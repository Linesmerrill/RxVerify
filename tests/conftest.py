"""
Pytest configuration and shared fixtures.
"""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, AsyncMock


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_medical_api_client():
    """Mock medical API client for testing."""
    mock_client = AsyncMock()
    
    # Mock successful RxNorm response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "drugGroup": {
            "conceptGroup": [
                {
                    "tty": "BN",
                    "conceptProperties": [
                        {
                            "rxcui": "161",
                            "name": "Tylenol",
                            "synonym": "Tylenol"
                        }
                    ]
                }
            ]
        }
    }
    
    mock_client.http_client.get.return_value = mock_response
    return mock_client


@pytest.fixture
def sample_drug_data():
    """Sample drug data for testing."""
    return {
        "tylenol": {
            "rxcui": "161",
            "name": "Tylenol",
            "generic_name": "acetaminophen",
            "brand_names": ["Tylenol"],
            "common_uses": ["Pain relief", "Fever reduction"],
            "drug_class": "Analgesic/Antipyretic"
        },
        "ivermectin": {
            "rxcui": "1373244",
            "name": "Ivermectin",
            "generic_name": "Ivermectin",
            "brand_names": ["Sklice", "Soolantra"],
            "common_uses": ["Parasitic infections", "Scabies", "Head lice"],
            "drug_class": "Antiparasitic"
        },
        "ibuprofen": {
            "rxcui": "5640",
            "name": "Ibuprofen",
            "generic_name": "ibuprofen",
            "brand_names": ["Advil", "Motrin"],
            "common_uses": ["Pain relief", "Inflammation", "Fever reduction"],
            "drug_class": "NSAID"
        }
    }


@pytest.fixture
def temp_db_file():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    return Mock()


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
