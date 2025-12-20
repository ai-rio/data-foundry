"""Basic tests for the Data Foundry main application."""

import pytest
from fastapi.testclient import TestClient

from src.main import app

# Create test client
client = TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check_returns_200(self):
        """Test that health check returns 200 status code."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_returns_correct_structure(self):
        """Test that health check returns the expected data structure."""
        response = client.get("/health")
        data = response.json()

        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "environment" in data
        assert data["status"] == "healthy"


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_returns_200(self):
        """Test that root endpoint returns 200 status code."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_welcome_message(self):
        """Test that root endpoint returns welcome message."""
        response = client.get("/")
        data = response.json()

        assert "message" in data
        assert "Data Foundry" in data["message"]
        assert "description" in data
        assert "version" in data
        assert "docs" in data
        assert "health" in data


@pytest.mark.unit
class TestConfiguration:
    """Test application configuration."""

    def test_app_title(self):
        """Test that the app has the correct title."""
        assert app.title == "Data Foundry"

    def test_app_version(self):
        """Test that the app has a version."""
        assert app.version is not None
        assert len(app.version) > 0

    def test_app_has_docs_url(self):
        """Test that the app has docs URL configured."""
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
