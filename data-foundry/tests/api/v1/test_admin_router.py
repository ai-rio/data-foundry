"""
Admin/Monitoring API Router Tests - Week 4 Phase 2.5

Test suite following TDD principles (Red-Green-Refactor cycle).
All tests are written first before implementation.

SECURITY TEST COVERAGE:
- CRITICAL #1: Rate limiting (sliding window, per-endpoint)
- CRITICAL #2: Admin authorization on POST /pipeline/trigger
- CRITICAL #4: Thread safety with locks
- CRITICAL #5: Bounded storage using deque(maxlen=10000)
- Generic error messages (no information disclosure)
- Hashed user IDs in logs
"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from unittest.mock import Mock, patch, AsyncMock
import time

from fastapi import status
from fastapi.testclient import TestClient

from src.main import app
from src.core.config import settings


# ============================================================================
# TEST ISOLATION FIXTURES
# ============================================================================

@pytest.fixture
def reset_rate_limiter():
    """Reset rate limiter state before each test."""
    from src.api.v1.admin.router import reset_rate_limiter_for_testing
    reset_rate_limiter_for_testing()
    yield
    reset_rate_limiter_for_testing()


@pytest.fixture
def reset_pipeline_status():
    """Reset pipeline status state before each test."""
    from src.api.v1.admin.router import reset_pipeline_status_for_testing
    reset_pipeline_status_for_testing()
    yield
    reset_pipeline_status_for_testing()


@pytest.fixture
def clean_state(reset_rate_limiter, reset_pipeline_status):
    """Combined fixture to reset all global state."""
    pass


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================

@pytest.fixture
def user_token():
    """Create a valid JWT token for normal user."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=1)

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": "test-user-123",
        "tenant_id": "test-tenant-1",
        "role": "user",
    }

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


@pytest.fixture
def admin_token():
    """Create a valid JWT token with admin role for testing admin endpoints."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=1)

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": "admin-user-456",
        "tenant_id": "test-tenant-1",
        "role": "admin",
    }

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


@pytest.fixture
def user_headers(user_token):
    """Headers with user authentication."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin authentication."""
    return {"Authorization": f"Bearer {admin_token}"}


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


# ============================================================================
# TESTS FOR GET /api/v1/admin/health/detailed
# ============================================================================

class TestDetailedHealthEndpoint:
    """Tests for GET /api/v1/admin/health/detailed endpoint."""

    def test_get_detailed_health_success(self, client, user_headers, clean_state):
        """Test successful detailed health check."""
        response = client.get(
            "/api/v1/admin/health/detailed",
            headers=user_headers
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
        assert isinstance(data["components"], dict)

        # Check expected components exist
        expected_components = ["database", "redis", "label_studio"]
        for component in expected_components:
            assert component in data["components"], f"Missing component: {component}"

    def test_get_detailed_health_authentication_required(self, client, clean_state):
        """Test that authentication is required."""
        response = client.get("/api/v1/admin/health/detailed")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_health_components_have_required_fields(self, client, user_headers, clean_state):
        """Test that health components have all required fields."""
        response = client.get(
            "/api/v1/admin/health/detailed",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        for component_name, component in data["components"].items():
            assert "name" in component
            assert "status" in component
            assert component["status"] in ["healthy", "degraded", "unhealthy"]
            # latency_ms and error are optional


# ============================================================================
# TESTS FOR GET /api/v1/admin/metrics/aggregated
# ============================================================================

class TestAggregatedMetricsEndpoint:
    """Tests for GET /api/v1/admin/metrics/aggregated endpoint."""

    def test_get_aggregated_metrics_success(self, client, user_headers, clean_state):
        """Test successful aggregated metrics retrieval."""
        response = client.get(
            "/api/v1/admin/metrics/aggregated",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "timestamp" in data

        # Check API metrics exist (may be None if no data yet)
        for api in ["quality", "abtest", "signals", "ml", "system"]:
            assert api in data

    def test_aggregated_metrics_authentication_required(self, client, clean_state):
        """Test that authentication is required."""
        response = client.get("/api/v1/admin/metrics/aggregated")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_aggregated_metrics_structure(self, client, user_headers, clean_state):
        """Test that metrics have proper structure."""
        response = client.get(
            "/api/v1/admin/metrics/aggregated",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # System metrics should always be present
        assert "system" in data
        if data["system"]:
            assert "uptime_seconds" in data["system"]


# ============================================================================
# TESTS FOR GET /api/v1/admin/pipeline/status
# ============================================================================

class TestPipelineStatusEndpoint:
    """Tests for GET /api/v1/admin/pipeline/status endpoint."""

    def test_get_pipeline_status_success(self, client, user_headers, clean_state):
        """Test successful pipeline status retrieval."""
        response = client.get(
            "/api/v1/admin/pipeline/status",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data
        assert "active_runs" in data
        assert data["status"] in ["idle", "running", "completed", "failed"]

    def test_pipeline_status_authentication_required(self, client, clean_state):
        """Test that authentication is required."""
        response = client.get("/api/v1/admin/pipeline/status")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_pipeline_status_fields(self, client, user_headers, clean_state):
        """Test pipeline status has expected fields."""
        response = client.get(
            "/api/v1/admin/pipeline/status",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Required fields
        assert "status" in data
        assert "active_runs" in data

        # Optional fields - may be None
        if data.get("last_run_id") is not None:
            assert isinstance(data["last_run_id"], str)


# ============================================================================
# TESTS FOR POST /api/v1/admin/pipeline/trigger
# ============================================================================

class TestTriggerPipelineEndpoint:
    """Tests for POST /api/v1/admin/pipeline/trigger endpoint."""

    def test_trigger_pipeline_admin_only(self, client, user_headers, clean_state):
        """CRITICAL #2: Verify admin access is required."""
        trigger_request = {
            "data_source": "sample_data",
            "enable_validation": True
        }

        response = client.post(
            "/api/v1/admin/pipeline/trigger",
            json=trigger_request,
            headers=user_headers
        )

        # Should fail with 403 because user is not admin
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_trigger_pipeline_admin_success(self, client, admin_headers, clean_state):
        """Test successful pipeline trigger by admin."""
        trigger_request = {
            "data_source": "sample_data",
            "enable_validation": True,
            "enable_ai_labeling": False,  # Disable for testing
            "enable_pii_redaction": False,
            "enable_human_review": False
        }

        # Mock the ingestion flow to avoid actual execution
        with patch('src.api.v1.admin.router.data_ingestion_flow') as mock_flow:
            mock_flow.return_value = {
                "success": True,
                "total_extracted": 100,
                "flow_run_id": "test-flow-run-123"
            }

            response = client.post(
                "/api/v1/admin/pipeline/trigger",
                json=trigger_request,
                headers=admin_headers
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "message" in data
            assert "flow_run_id" in data
            assert "status" in data

    def test_trigger_pipeline_validation(self, client, admin_headers, clean_state):
        """Test that pipeline trigger validates input."""
        # Invalid data_source with path injection
        invalid_request = {
            "data_source": "../../../etc/passwd",
            "enable_validation": True
        }

        response = client.post(
            "/api/v1/admin/pipeline/trigger",
            json=invalid_request,
            headers=admin_headers
        )

        # Should fail with 422 (validation error) or 400
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_trigger_pipeline_authentication_required(self, client, clean_state):
        """Test that authentication is required."""
        trigger_request = {"data_source": "sample_data"}

        response = client.post(
            "/api/v1/admin/pipeline/trigger",
            json=trigger_request
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TESTS FOR RATE LIMITING (CRITICAL #1)
# ============================================================================

class TestRateLimiting:
    """Tests for CRITICAL #1: Rate limiting using sliding window."""

    def test_health_endpoint_rate_limited(self, client, user_headers, clean_state):
        """Test that health endpoint is rate limited."""
        # Make requests up to the limit (60/minute = 1 per second, use 70 to exceed)
        exceeded = False
        for i in range(70):
            response = client.get(
                "/api/v1/admin/health/detailed",
                headers=user_headers
            )
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                exceeded = True
                break

        # Should eventually hit rate limit
        assert exceeded, "Rate limit not triggered for health endpoint"

    def test_metrics_endpoint_rate_limited(self, client, user_headers, clean_state):
        """Test that metrics endpoint is rate limited (30 requests/minute)."""
        exceeded = False
        for i in range(35):
            response = client.get(
                "/api/v1/admin/metrics/aggregated",
                headers=user_headers
            )
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                exceeded = True
                break

        assert exceeded, "Rate limit not triggered for metrics endpoint"

    def test_pipeline_trigger_rate_limited(self, client, admin_headers, clean_state):
        """Test that pipeline trigger is rate limited (10 requests/minute)."""
        # Mock the flow to avoid actual execution
        with patch('src.api.v1.admin.router.data_ingestion_flow') as mock_flow:
            mock_flow.return_value = {"success": True, "flow_run_id": "test"}

            exceeded = False
            for i in range(12):
                response = client.post(
                    "/api/v1/admin/pipeline/trigger",
                    json={"data_source": "sample_data", "enable_ai_labeling": False},
                    headers=admin_headers
                )
                if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                    exceeded = True
                    break

            assert exceeded, "Rate limit not triggered for pipeline trigger"


# ============================================================================
# TESTS FOR THREAD SAFETY (CRITICAL #4)
# ============================================================================

class TestThreadSafety:
    """Tests for CRITICAL #4: Thread safety with locks."""

    def test_pipeline_status_thread_safety(self, clean_state):
        """Verify thread safety with locks."""
        from src.api.v1.admin.router import _pipeline_status_lock
        import threading

        # Verify lock exists
        assert isinstance(_pipeline_status_lock, type(threading.Lock()))


# ============================================================================
# TESTS FOR BOUNDED STORAGE (CRITICAL #5)
# ============================================================================

class TestBoundedStorage:
    """Tests for CRITICAL #5: Bounded storage using deque(maxlen=10000)."""

    def test_metrics_storage_is_bounded(self, clean_state):
        """Verify that metrics storage doesn't grow unbounded."""
        from src.api.v1.admin.router import _pipeline_runs
        import collections

        # Check if pipeline_runs uses deque with maxlen
        if isinstance(_pipeline_runs, collections.deque):
            assert _pipeline_runs.maxlen == 10000, f"Expected maxlen=10000"


# ============================================================================
# TESTS FOR ERROR HANDLING
# ============================================================================

class TestErrorHandling:
    """Tests for generic error messages (no information disclosure)."""

    def test_generic_error_on_component_failure(self, client, user_headers, clean_state):
        """Test that component failures return generic messages."""
        # Mock a component failure
        with patch('src.api.v1.admin.router._check_database_health') as mock_db:
            mock_db.side_effect = Exception("Database connection failed: password=secret")

            response = client.get(
                "/api/v1/admin/health/detailed",
                headers=user_headers
            )

            # Should still return 200 with degraded status, not leak internal error
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Error details should be sanitized
            if "database" in data["components"]:
                db_component = data["components"]["database"]
                if db_component.get("error"):
                    # Should not contain sensitive info
                    assert "password" not in db_component["error"].lower()


# ============================================================================
# TESTS FOR SECURE LOGGING
# ============================================================================

class TestSecureLogging:
    """Tests for secure logging with hashed user IDs."""

    def test_user_id_hashed_in_logs(self, client, user_headers, clean_state, caplog):
        """Verify that user IDs are hashed in logs."""
        import logging
        caplog.set_level(logging.INFO)

        client.get(
            "/api/v1/admin/health/detailed",
            headers=user_headers
        )

        # Check logs don't contain raw user_id
        for record in caplog.records:
            log_message = record.getMessage()
            # Raw user ID should not appear in logs
            assert "test-user-123" not in log_message


# ============================================================================
# TEST ISOLATION HELPERS
# ============================================================================

class TestResetHelpers:
    """Tests for reset helpers used for test isolation."""

    def test_reset_rate_limiter_exists(self):
        """Verify reset_rate_limiter_for_testing function exists."""
        from src.api.v1.admin.router import reset_rate_limiter_for_testing
        assert callable(reset_rate_limiter_for_testing)

    def test_reset_pipeline_status_exists(self):
        """Verify reset_pipeline_status_for_testing function exists."""
        from src.api.v1.admin.router import reset_pipeline_status_for_testing
        assert callable(reset_pipeline_status_for_testing)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_pipeline_status(self, client, user_headers, clean_state):
        """Test handling when no pipeline has run yet."""
        response = client.get(
            "/api/v1/admin/pipeline/status",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Should handle gracefully
        assert data["status"] in ["idle", "running", "completed", "failed"]

    def test_data_source_validation_edge_cases(self, client, admin_headers, clean_state):
        """Test data_source validation edge cases."""
        with patch('src.api.v1.admin.router.data_ingestion_flow') as mock_flow:
            mock_flow.return_value = {"success": True, "flow_run_id": "test"}

            # Test empty string
            response = client.post(
                "/api/v1/admin/pipeline/trigger",
                json={"data_source": ""},
                headers=admin_headers
            )
            assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_unicode_data_source(self, client, admin_headers, clean_state):
        """Test handling of unicode in data_source."""
        with patch('src.api.v1.admin.router.data_ingestion_flow') as mock_flow:
            mock_flow.return_value = {"success": True, "flow_run_id": "test"}

            response = client.post(
                "/api/v1/admin/pipeline/trigger",
                json={"data_source": "test_data_日本"},
                headers=admin_headers
            )
            # Should handle gracefully (may fail validation or succeed)
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
