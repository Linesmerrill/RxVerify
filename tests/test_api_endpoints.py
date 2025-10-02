"""
Tests for the API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app


class TestAPIEndpoints:
    """Test cases for API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
    
    def test_status_endpoint(self, client):
        """Test system status endpoint."""
        response = client.get("/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
    
    def test_cache_stats_endpoint(self, client):
        """Test cache stats endpoint."""
        response = client.get("/cache/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "cache_stats" in data
        assert "timestamp" in data
        
        cache_stats = data["cache_stats"]
        assert "total_medications" in cache_stats
        assert "total_searches" in cache_stats
        assert "top_searched" in cache_stats
    
    def test_clear_cache_endpoint(self, client):
        """Test clear cache endpoint."""
        response = client.post("/cache/clear")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "message" in data
    
    @patch('app.main.get_search_service')
    def test_search_endpoint_success(self, mock_get_search_service, client):
        """Test successful medication search."""
        # Mock search service
        mock_search_service = AsyncMock()
        mock_search_service.search_medications.return_value = [
            {
                "rxcui": "161",
                "name": "Tylenol",
                "generic_name": "acetaminophen",
                "brand_names": ["Tylenol"],
                "common_uses": ["Pain relief", "Fever reduction"],
                "drug_class": "Analgesic/Antipyretic",
                "source": "local"
            }
        ]
        mock_get_search_service.return_value = mock_search_service
        
        # Test search request
        response = client.post(
            "/search",
            json={"query": "tylenol", "limit": 5}
        )
        
        assert response.status_code == 200
        
        data = response.json()
        assert "results" in data
        assert "total_found" in data
        assert "processing_time_ms" in data
        
        results = data["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Tylenol"
        assert results[0]["generic_name"] == "acetaminophen"
        assert "Tylenol" in results[0]["brand_names"]
        assert "Pain relief" in results[0]["common_uses"]
    
    @patch('app.main.get_search_service')
    def test_search_endpoint_empty_results(self, mock_get_search_service, client):
        """Test search endpoint with empty results."""
        # Mock search service to return empty results
        mock_search_service = AsyncMock()
        mock_search_service.search_medications.return_value = []
        mock_get_search_service.return_value = mock_search_service
        
        response = client.post(
            "/search",
            json={"query": "nonexistent", "limit": 5}
        )
        
        assert response.status_code == 200
        
        data = response.json()
        assert data["results"] == []
        assert data["total_found"] == 0
    
    def test_search_endpoint_invalid_request(self, client):
        """Test search endpoint with invalid request."""
        # Missing query
        response = client.post(
            "/search",
            json={"limit": 5}
        )
        assert response.status_code == 422
        
        # Invalid limit
        response = client.post(
            "/search",
            json={"query": "test", "limit": -1}
        )
        assert response.status_code == 422
    
    def test_search_endpoint_short_query(self, client):
        """Test search endpoint with query too short."""
        response = client.post(
            "/search",
            json={"query": "a", "limit": 5}
        )
        
        assert response.status_code == 200
        
        data = response.json()
        assert data["results"] == []
        assert data["total_found"] == 0
    
    @patch('app.main.get_search_service')
    def test_search_endpoint_error_handling(self, mock_get_search_service, client):
        """Test search endpoint error handling."""
        # Mock search service to raise an exception
        mock_search_service = AsyncMock()
        mock_search_service.search_medications.side_effect = Exception("Search failed")
        mock_get_search_service.return_value = mock_search_service
        
        response = client.post(
            "/search",
            json={"query": "test", "limit": 5}
        )
        
        assert response.status_code == 500
        
        data = response.json()
        assert "detail" in data
        assert "Search failed" in data["detail"]
    
    @patch('app.main.get_search_service')
    def test_search_endpoint_consolidation(self, mock_get_search_service, client):
        """Test that search endpoint returns consolidated results."""
        # Mock search service to return multiple ivermectin results
        mock_search_service = AsyncMock()
        mock_search_service.search_medications.return_value = [
            {
                "rxcui": "1373244",
                "name": "Ivermectin",
                "generic_name": "Ivermectin",
                "brand_names": ["Sklice", "Soolantra", "Privermectin"],
                "common_uses": ["Parasitic infections", "Scabies", "Head lice"],
                "drug_class": "Antiparasitic",
                "source": "rxnorm"
            }
        ]
        mock_get_search_service.return_value = mock_search_service
        
        response = client.post(
            "/search",
            json={"query": "ivermectin", "limit": 5}
        )
        
        assert response.status_code == 200
        
        data = response.json()
        results = data["results"]
        
        # Should have consolidated result
        assert len(results) == 1
        assert results[0]["name"] == "Ivermectin"
        assert len(results[0]["brand_names"]) == 3
        assert "Sklice" in results[0]["brand_names"]
        assert "Soolantra" in results[0]["brand_names"]
        assert "Privermectin" in results[0]["brand_names"]
    
    def test_search_endpoint_performance_tracking(self, client):
        """Test that search endpoint tracks performance."""
        with patch('app.main.get_search_service') as mock_get_search_service:
            mock_search_service = AsyncMock()
            mock_search_service.search_medications.return_value = []
            mock_get_search_service.return_value = mock_search_service
            
            response = client.post(
                "/search",
                json={"query": "test", "limit": 5}
            )
            
            assert response.status_code == 200
            
            data = response.json()
            assert "processing_time_ms" in data
            assert isinstance(data["processing_time_ms"], (int, float))
            assert data["processing_time_ms"] >= 0
