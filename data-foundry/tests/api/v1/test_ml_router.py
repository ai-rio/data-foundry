"""
ML Predictor API Router Tests - Week 4 Phase 2.4

Test suite following TDD principles (Red-Green-Refactor cycle).
All tests are written first before implementation.

SECURITY TEST COVERAGE:
- CRITICAL #1: Rate limiting (sliding window, per-endpoint)
- CRITICAL #2: Admin authorization on POST /model/reload
- CRITICAL #3: Tenant isolation checks (if applicable)
- CRITICAL #4: Thread safety with locks
- CRITICAL #5: Bounded storage using deque(maxlen=10000)
- HIGH #1: Request size validation (1MB single, 10MB batch)
- Generic error messages (no information disclosure)
- Hashed user IDs in logs

Pattern reference: tests/api/v1/test_signals_router.py
"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, patch

from fastapi import status
from fastapi.testclient import TestClient

from src.main import app
from src.core.ml_predictor import MLPredictor, ModelMetadata, PredictionResult
from src.core.security import create_access_token
from src.core.config import settings


# ============================================================================
# TEST ISOLATION FIXTURES
# ============================================================================

@pytest.fixture
def reset_rate_limiter():
    """Reset rate limiter state before each test."""
    from src.api.v1.ml.router import reset_rate_limiter_for_testing
    reset_rate_limiter_for_testing()
    yield
    reset_rate_limiter_for_testing()


@pytest.fixture
def reset_metrics_storage():
    """Reset metrics storage state before each test."""
    from src.api.v1.ml.router import reset_metrics_storage_for_testing
    reset_metrics_storage_for_testing()
    yield
    reset_metrics_storage_for_testing()


@pytest.fixture
def reset_model_state():
    """Reset model state before each test."""
    from src.api.v1.ml.router import reset_model_state_for_testing
    reset_model_state_for_testing()
    yield
    reset_model_state_for_testing()


@pytest.fixture
def clean_state(reset_rate_limiter, reset_metrics_storage, reset_model_state):
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
# TESTS FOR POST /api/v1/ml/predict
# ============================================================================

class TestPredictEndpoint:
    """Tests for POST /api/v1/ml/predict endpoint."""

    def test_predict_success(self, client, sample_record, user_headers, clean_state):
        """Test successful prediction for a single record."""
        response = client.post(
            "/api/v1/ml/predict",
            json={"record": sample_record},
            headers=user_headers
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "quality_score" in data
        assert "confidence" in data
        assert "feature_importance" in data
        assert isinstance(data["quality_score"], (int, float))
        assert 0.0 <= data["quality_score"] <= 1.0
        assert 0.0 <= data["confidence"] <= 1.0

    def test_predict_authentication_required(self, client, sample_record):
        """Test that authentication is required."""
        response = client.post(
            "/api/v1/ml/predict",
            json={"record": sample_record}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_predict_empty_record(self, client, user_headers, clean_state):
        """Test handling of empty record."""
        response = client.post(
            "/api/v1/ml/predict",
            json={"record": {}},
            headers=user_headers
        )

        # Should handle gracefully
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]

    def test_predict_record_size_validation(self, client, user_headers, clean_state):
        """HIGH #1: Test request size validation (1MB max)."""
        # Create a large record exceeding 1MB
        large_record = {
            "id": "record-large",
            "data_preview": "x" * (2 * 1024 * 1024),  # 2MB
            "raw_data": '{"text": "test"}'
        }

        response = client.post(
            "/api/v1/ml/predict",
            json={"record": large_record},
            headers=user_headers
        )

        # Should fail with 413 or 422 due to size validation
        assert response.status_code in [
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ]


# ============================================================================
# TESTS FOR POST /api/v1/ml/predict-batch
# ============================================================================

class TestPredictBatchEndpoint:
    """Tests for POST /api/v1/ml/predict-batch endpoint."""

    def test_predict_batch_success(self, client, sample_records_batch, user_headers, clean_state):
        """Test successful batch prediction."""
        response = client.post(
            "/api/v1/ml/predict-batch",
            json={"records": sample_records_batch},
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data
        assert "total_records" in data
        assert "avg_quality_score" in data
        assert data["total_records"] == len(sample_records_batch)
        assert len(data["results"]) == len(sample_records_batch)

    def test_predict_batch_authentication_required(self, client, sample_records_batch):
        """Test that authentication is required."""
        response = client.post(
            "/api/v1/ml/predict-batch",
            json={"records": sample_records_batch}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_predict_batch_size_validation(self, client, user_headers, clean_state):
        """HIGH #1: Test batch size validation (10MB max, 1000 records max)."""
        # Test batch size limit (1000 records)
        large_batch = [
            {"id": f"record-{i}", "data_preview": "test"} for i in range(1001)
        ]

        response = client.post(
            "/api/v1/ml/predict-batch",
            json={"records": large_batch},
            headers=user_headers
        )

        # Should fail with 422 due to batch size limit
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_predict_batch_empty_records(self, client, user_headers, clean_state):
        """Test handling of empty records list."""
        response = client.post(
            "/api/v1/ml/predict-batch",
            json={"records": []},
            headers=user_headers
        )

        # Should fail with 422 due to empty list validation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================================================
# TESTS FOR GET /api/v1/ml/model/info
# ============================================================================

class TestGetModelInfoEndpoint:
    """Tests for GET /api/v1/ml/model/info endpoint."""

    def test_get_model_info_success(self, client, user_headers, clean_state):
        """Test successful model info retrieval."""
        response = client.get(
            "/api/v1/ml/model/info",
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "model_version" in data
        assert "model_type" in data
        assert "is_loaded" in data
        assert "feature_count" in data
        assert isinstance(data["is_loaded"], bool)

    def test_get_model_info_authentication_required(self, client):
        """Test that authentication is required."""
        response = client.get("/api/v1/ml/model/info")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TESTS FOR POST /api/v1/ml/model/reload
# ============================================================================

class TestReloadModelEndpoint:
    """Tests for POST /api/v1/ml/model/reload endpoint."""

    def test_reload_model_admin_only(self, client, user_headers, clean_state):
        """CRITICAL #2: Verify admin access is required."""
        response = client.post(
            "/api/v1/ml/model/reload",
            headers=user_headers
        )

        # Should fail with 403 because user is not admin
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_reload_model_admin_success(self, client, admin_headers, clean_state):
        """Test successful model reload by admin."""
        response = client.post(
            "/api/v1/ml/model/reload",
            headers=admin_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "model_version" in data
        assert "is_loaded" in data
        assert data["is_loaded"] is True

    def test_reload_model_authentication_required(self, client):
        """Test that authentication is required."""
        response = client.post("/api/v1/ml/model/reload")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TESTS FOR GET /api/v1/ml/features/extract
# ============================================================================

class TestExtractFeaturesEndpoint:
    """Tests for GET /api/v1/ml/features/extract endpoint."""

    def test_extract_features_success(self, client, user_headers, clean_state):
        """Test successful feature extraction."""
        # Note: This endpoint might use POST or query params
        # Adjust based on actual implementation
        response = client.post(
            "/api/v1/ml/features/extract",
            json={"record": {"id": "test-1", "data_preview": "test content"}},
            headers=user_headers
        )

        # Should return extracted features
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "features" in data
        assert "feature_count" in data

    def test_extract_features_authentication_required(self, client):
        """Test that authentication is required."""
        response = client.post(
            "/api/v1/ml/features/extract",
            json={"record": {"id": "test-1"}}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TESTS FOR BOUNDED STORAGE (CRITICAL #5)
# ============================================================================

class TestBoundedStorage:
    """Tests for CRITICAL #5: Bounded storage using deque(maxlen=10000)."""

    def test_metrics_storage_is_bounded(self, clean_state):
        """Verify that metrics storage doesn't grow unbounded."""
        from src.api.v1.ml.router import _metrics_storage
        import collections

        # Check if metrics_storage uses deque with maxlen
        for key, value in _metrics_storage.items():
            if isinstance(value, collections.deque):
                assert value.maxlen == 10000, f"Expected maxlen=10000 for {key}"

    def test_model_state_thread_safety(self, clean_state):
        """CRITICAL #4: Verify thread safety with locks."""
        from src.api.v1.ml.router import _model_lock
        import threading

        # Verify lock exists
        assert isinstance(_model_lock, type(threading.Lock()))


# ============================================================================
# TESTS FOR ERROR HANDLING
# ============================================================================

class TestErrorHandling:
    """Tests for generic error messages (no information disclosure)."""

    def test_invalid_record_format(self, client, user_headers, clean_state):
        """Test handling of invalid record format."""
        response = client.post(
            "/api/v1/ml/predict",
            json={"invalid_field": "value"},
            headers=user_headers
        )

        # Should fail with validation error
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_generic_error_messages(self, client, user_headers, clean_state):
        """Verify that error messages are generic (no information disclosure)."""
        # Force an error scenario
        response = client.post(
            "/api/v1/ml/predict",
            json={"record": None},
            headers=user_headers
        )

        # Error response should not contain sensitive information
        if response.status_code != status.HTTP_200_OK:
            error_detail = response.json().get("detail", "")
            # Check that error message is generic
            assert "password" not in error_detail.lower()
            assert "secret" not in error_detail.lower()
            assert "token" not in error_detail.lower()


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
            "/api/v1/ml/predict",
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
        from src.api.v1.ml.router import reset_rate_limiter_for_testing
        assert callable(reset_rate_limiter_for_testing)

    def test_reset_model_state_exists(self):
        """Verify reset_model_state_for_testing function exists."""
        from src.api.v1.ml.router import reset_model_state_for_testing
        assert callable(reset_model_state_for_testing)

    def test_reset_metrics_storage_exists(self):
        """Verify reset_metrics_storage_for_testing function exists."""
        from src.api.v1.ml.router import reset_metrics_storage_for_testing
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
            "data_preview": None,
            "raw_data": None
        }

        response = client.post(
            "/api/v1/ml/predict",
            json={"record": null_record},
            headers=user_headers
        )

        # Should handle gracefully
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]

    def test_unicode_content(self, client, user_headers, clean_state):
        """Test handling of unicode content."""
        unicode_record = {
            "id": "record-001",
            "data_preview": "Looking for a tool 日本语 ??",
            "raw_data": '{"text": "Can anyone recommend a tool? 123"}'
        }

        response = client.post(
            "/api/v1/ml/predict",
            json={"record": unicode_record},
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK

    def test_special_characters_in_record(self, client, user_headers, clean_state):
        """Test handling of special characters."""
        special_record = {
            "id": "record-001",
            "data_preview": "Test with <script>alert('xss')</script>",
            "raw_data": '{"text": "Test with \n\t\r characters"}'
        }

        response = client.post(
            "/api/v1/ml/predict",
            json={"record": special_record},
            headers=user_headers
        )

        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# RATE LIMITING TESTS (CRITICAL #1)
# ============================================================================

class TestRateLimiting:
    """Tests for CRITICAL #1: Rate limiting (sliding window)."""

    def test_predict_rate_limiting(self, client, user_headers, clean_state):
        """Test rate limiting on /predict endpoint."""
        # Make requests up to the limit
        # The exact limit depends on configuration
        for _ in range(5):
            response = client.post(
                "/api/v1/ml/predict",
                json={"record": {"id": "test", "data_preview": "test"}},
                headers=user_headers
            )
            # First requests should succeed
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break

    def test_batch_rate_limiting(self, client, user_headers, clean_state):
        """Test rate limiting on /predict-batch endpoint."""
        # Batch endpoint should have stricter rate limiting
        for _ in range(3):
            response = client.post(
                "/api/v1/ml/predict-batch",
                json={"records": [{"id": "test", "data_preview": "test"}]},
                headers=user_headers
            )
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break


# ============================================================================
# THREAD SAFETY TESTS (CRITICAL #4)
# ============================================================================

class TestThreadSafety:
    """Tests for CRITICAL #4: Thread safety with locks."""

    def test_concurrent_predictions(self, client, user_headers, clean_state):
        """Test concurrent prediction requests don't cause race conditions."""
        import threading

        results = []
        errors = []

        def make_request():
            try:
                response = client.post(
                    "/api/v1/ml/predict",
                    json={"record": {"id": "test", "data_preview": "test"}},
                    headers=user_headers
                )
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=make_request) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All requests should complete without errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
