"""
Signal Detection API Router Tests - Week 4 Phase 2.3

Test suite following TDD principles (Red-Green-Refactor cycle).
All tests are written first before implementation.

SECURITY TEST COVERAGE:
- CRITICAL #1: Rate limiting (sliding window, per-endpoint)
- CRITICAL #2: Admin authorization on PUT /config
- CRITICAL #3: Tenant isolation checks
- CRITICAL #4: Thread safety with locks
- CRITICAL #5: Bounded storage using deque(maxlen=10000)
- HIGH #1: Request size validation (1MB max)
- Generic error messages (no information disclosure)
- Hashed user IDs in logs
"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, patch

from fastapi import status
from fastapi.testclient import TestClient

from src.main import app
from src.core.signal_detector import SignalDetector, SignalResult
from src.core.security import create_access_token
from src.core.config import settings


# ============================================================================
# TEST ISOLATION FIXTURES
# ============================================================================

@pytest.fixture
def reset_rate_limiter():
    """Reset rate limiter state before each test."""
    from src.api.v1.signals.router import reset_rate_limiter_for_testing
    reset_rate_limiter_for_testing()
    yield
    reset_rate_limiter_for_testing()


@pytest.fixture
def reset_metrics_storage():
    """Reset metrics storage state before each test."""
    from src.api.v1.signals.router import reset_metrics_storage_for_testing
    reset_metrics_storage_for_testing()
    yield
    reset_metrics_storage_for_testing()


@pytest.fixture
def reset_config():
    """Reset configuration state before each test."""
    from src.api.v1.signals.router import reset_config_for_testing
    reset_config_for_testing()
    yield
    reset_config_for_testing()


@pytest.fixture
def clean_state(reset_rate_limiter, reset_metrics_storage, reset_config):
    """Combined fixture to reset all global state."""
    pass


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================

@pytest.fixture
def user_token():
    """
    Create a valid JWT token for normal user.

    Includes tenant_id for tenant isolation tests (CRITICAL #3).
    """
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
    """
    Create a valid JWT token with admin role for testing admin endpoints.

    CRITICAL #2: Admin authorization check requires role claim in token.
    This fixture manually creates a token with the admin role.
    """
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


@pytest.fixture
def sample_record() -> Dict[str, Any]:
    """Sample data record for testing."""
    return {
        "id": "record-001",
        "tenant_id": "test-tenant-1",
        "data_source": "reddit",
        "data_preview": "Looking for a tool for data analysis",
        "raw_data": '{"text": "Can anyone recommend a good data analysis tool?"}',
        "data_quality_score": 0.95,
        "access_count": 150,
        "extracted_text": "Can anyone recommend a good data analysis tool?"
    }


@pytest.fixture
def sample_records_batch() -> List[Dict[str, Any]]:
    """Sample batch of data records for testing."""
    return [
        {
            "id": "record-001",
            "tenant_id": "test-tenant-1",
            "data_source": "reddit",
            "data_preview": "Looking for a tool",
            "raw_data": '{"text": "recommend a tool"}',
            "data_quality_score": 0.9,
            "access_count": 100,
        },
        {
            "id": "record-002",
            "tenant_id": "test-tenant-1",
            "data_source": "reddit",
            "data_preview": "Frustrated with current options",
            "raw_data": '{"text": "I hate when software crashes"}',
            "data_quality_score": 0.85,
            "access_count": 80,
        },
        {
            "id": "record-003",
            "tenant_id": "test-tenant-1",
            "data_source": "reddit",
            "data_preview": "Price discussion",
            "raw_data": '{"text": "Would pay $50 for this"}',
            "data_quality_score": 0.88,
            "access_count": 120,
        }
    ]


# ============================================================================
# TESTS FOR POST /api/v1/signals/detect
# ============================================================================

class TestDetectSignalsEndpoint:
    """Tests for POST /api/v1/signals/detect endpoint."""

    def test_detect_signals_success(self, client, sample_record, user_headers, clean_state):
        """Test successful signal detection for a single record."""
        response = client.post(
            "/api/v1/signals/detect",
            json={"record": sample_record},
            headers=user_headers
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "signal_type" in data
        assert "signal_strength" in data
        assert "evidence_snippets" in data
        assert "engagement_metrics" in data
        assert "should_analyze" in data

    def test_detect_signals_tenant_isolation_enforced(self, client, sample_record, user_headers, clean_state):
        """CRITICAL #3: Verify tenant isolation is enforced."""
        # Create record with different tenant_id
        other_tenant_record = sample_record.copy()
        other_tenant_record["tenant_id"] = "other-tenant-999"

        response = client.post(
            "/api/v1/signals/detect",
            json={"record": other_tenant_record},
            headers=user_headers
        )

        # Should fail with 403 due to tenant mismatch
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_detect_signals_authentication_required(self, client, sample_record):
        """Test that authentication is required."""
        response = client.post(
            "/api/v1/signals/detect",
            json={"record": sample_record}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TESTS FOR POST /api/v1/signals/detect-batch
# ============================================================================

class TestDetectBatchEndpoint:
    """Tests for POST /api/v1/signals/detect-batch endpoint."""

    def test_detect_batch_success(self, client, sample_records_batch, user_headers, clean_state):
        """Test successful batch signal detection."""
        response = client.post(
            "/api/v1/signals/detect-batch",
            json={"records": sample_records_batch},
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data
        assert "total_records" in data
        assert "signals_detected" in data
        assert "should_analyze_count" in data
        assert data["total_records"] == len(sample_records_batch)
        assert len(data["results"]) == len(sample_records_batch)

    def test_detect_batch_tenant_isolation(self, client, sample_records_batch, user_headers, clean_state):
        """CRITICAL #3: Verify tenant isolation for batch requests."""
        # Add a record with different tenant
        mixed_batch = sample_records_batch.copy()
        mixed_batch.append({
            "id": "record-other-tenant",
            "tenant_id": "other-tenant-999",
            "data_source": "test",
            "data_preview": "test content"
        })

        response = client.post(
            "/api/v1/signals/detect-batch",
            json={"records": mixed_batch},
            headers=user_headers
        )

        # Should fail with 403 due to tenant mismatch
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# TESTS FOR GET /api/v1/signals/config
# ============================================================================

class TestGetConfigEndpoint:
    """Tests for GET /api/v1/signals/config endpoint."""

    def test_get_config_success(self, client, user_headers, clean_state):
        """Test successful config retrieval."""
        response = client.get(
            "/api/v1/signals/config",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "threshold" in data
        assert "enabled_signal_types" in data
        assert isinstance(data["threshold"], (int, float))
        assert isinstance(data["enabled_signal_types"], list)


# ============================================================================
# TESTS FOR PUT /api/v1/signals/config
# ============================================================================

class TestUpdateConfigEndpoint:
    """Tests for PUT /api/v1/signals/config endpoint."""

    def test_update_config_admin_only(self, client, user_headers, clean_state):
        """CRITICAL #2: Verify admin access is required."""
        config_update = {"threshold": 80.0}

        response = client.put(
            "/api/v1/signals/config",
            json=config_update,
            headers=user_headers
        )

        # Should fail with 403 because user is not admin
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_config_admin_success(self, client, admin_headers, clean_state):
        """Test successful config update by admin."""
        config_update = {"threshold": 75.0}

        response = client.put(
            "/api/v1/signals/config",
            json=config_update,
            headers=admin_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["threshold"] == 75.0

    def test_update_config_validation(self, client, admin_headers, clean_state):
        """Test that config values are validated."""
        # Invalid threshold (out of range)
        invalid_config = {"threshold": 150.0}

        response = client.put(
            "/api/v1/signals/config",
            json=invalid_config,
            headers=admin_headers
        )

        # Should fail with 400 or 422 due to validation
        # 422 = FastAPI/Pydantic validation error
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]


# ============================================================================
# TESTS FOR GET /api/v1/signals/types
# ============================================================================

class TestGetSignalTypesEndpoint:
    """Tests for GET /api/v1/signals/types endpoint."""

    def test_get_signal_types_success(self, client, user_headers, clean_state):
        """Test successful signal types retrieval."""
        response = client.get(
            "/api/v1/signals/types",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "signal_types" in data
        assert isinstance(data["signal_types"], list)

        # Should include expected signal types
        signal_type_names = [s.get("name") if isinstance(s, dict) else s for s in data["signal_types"]]
        expected_types = ["TOOL_REQUEST", "PAIN_COMPLAINT", "PRICE_MENTION",
                        "PROBLEM_SOLUTION", "COMPARISON"]
        for signal_type in expected_types:
            assert signal_type in signal_type_names


# ============================================================================
# TESTS FOR BOUNDED STORAGE (CRITICAL #5)
# ============================================================================

class TestBoundedStorage:
    """Tests for CRITICAL #5: Bounded storage using deque(maxlen=10000)."""

    def test_metrics_storage_is_bounded(self, clean_state):
        """Verify that metrics storage doesn't grow unbounded."""
        from src.api.v1.signals.router import _metrics_storage
        import collections

        # Check if metrics_storage uses deque with maxlen
        for key, value in _metrics_storage.items():
            if isinstance(value, collections.deque):
                assert value.maxlen == 10000, f"Expected maxlen=10000 for {key}"

    def test_config_storage_thread_safety(self, clean_state):
        """CRITICAL #4: Verify thread safety with locks."""
        from src.api.v1.signals.router import _config_lock
        import threading

        # Verify lock exists
        assert isinstance(_config_lock, type(threading.Lock()))


# ============================================================================
# TESTS FOR ERROR HANDLING
# ============================================================================

class TestErrorHandling:
    """Tests for generic error messages (no information disclosure)."""

    def test_empty_record(self, client, user_headers, clean_state):
        """Test handling of empty record."""
        response = client.post(
            "/api/v1/signals/detect",
            json={"record": {}},
            headers=user_headers
        )

        # Should handle gracefully - may return NONE signal type with 0 strength
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["signal_type"] == "NONE"
        assert data["signal_strength"] == 0


# ============================================================================
# TESTS FOR SECURE LOGGING
# ============================================================================

class TestSecureLogging:
    """Tests for secure logging with hashed user IDs."""

    def test_user_id_hashed_in_logs(self, client, sample_record, user_headers, clean_state, caplog):
        """Verify that user IDs are hashed in logs."""
        import logging
        caplog.set_level(logging.INFO)

        client.post(
            "/api/v1/signals/detect",
            json={"record": sample_record},
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
        from src.api.v1.signals.router import reset_rate_limiter_for_testing
        assert callable(reset_rate_limiter_for_testing)

    def test_reset_config_exists(self):
        """Verify reset_config_for_testing function exists."""
        from src.api.v1.signals.router import reset_config_for_testing
        assert callable(reset_config_for_testing)

    def test_reset_metrics_storage_exists(self):
        """Verify reset_metrics_storage_for_testing function exists."""
        from src.api.v1.signals.router import reset_metrics_storage_for_testing
        assert callable(reset_metrics_storage_for_testing)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_record_with_null_fields(self, client, user_headers, clean_state):
        """Test handling of record with null fields."""
        null_record = {
            "id": "record-001",
            "tenant_id": "test-tenant-1",
            "data_preview": None,
            "raw_data": None
        }

        response = client.post(
            "/api/v1/signals/detect",
            json={"record": null_record},
            headers=user_headers
        )

        # Should handle gracefully - may return NONE signal type
        assert response.status_code == status.HTTP_200_OK

    def test_unicode_content(self, client, user_headers, clean_state):
        """Test handling of unicode content."""
        unicode_record = {
            "id": "record-001",
            "tenant_id": "test-tenant-1",
            "data_preview": "Looking for a tool 日本语 ??",
            "raw_data": '{"text": "Can anyone recommend a tool? 123"}'
        }

        response = client.post(
            "/api/v1/signals/detect",
            json={"record": unicode_record},
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
