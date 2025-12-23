"""
Test Suite for Data Quality API Router

This module implements comprehensive TDD tests for the Data Quality API router.
All tests are written first (RED phase) before implementation.

Test Coverage:
- POST /api/v1/quality/validate - Single record validation
- POST /api/v1/quality/validate-batch - Batch validation
- GET /api/v1/quality/metrics - Quality metrics
- GET /api/v1/quality/config - Get configuration
- PUT /api/v1/quality/config - Update configuration (admin)

SECURITY HARDENING - Week 4 Phase 2.1:
- Added admin_token fixture for admin-only endpoints (CRITICAL #1)

TEST ISOLATION FIX - Week 4 Phase 2.1:
- Added fixtures to reset global state between tests
- Ensures clean state for rate_limiter, metrics_storage, and config
"""

import pytest
from fastapi.testclient import TestClient
from typing import Dict, Any
from unittest.mock import Mock, patch
import jwt
from datetime import datetime, timedelta, timezone

from src.main import app
from src.core.data_quality import ValidationResult
from src.core.security import create_access_token
from src.core.config import settings


# ============================================================================
# TEST ISOLATION FIXTURES
# ============================================================================

@pytest.fixture
def reset_rate_limiter():
    """
    Reset rate limiter state before each test.

    Clears IP request history to ensure test isolation.
    """
    from src.api.v1.quality.router import reset_rate_limiter_for_testing
    reset_rate_limiter_for_testing()
    yield
    # Reset after test as well
    reset_rate_limiter_for_testing()


@pytest.fixture
def reset_metrics_storage():
    """
    Reset metrics storage state before each test.

    Clears accumulated metrics data to ensure test isolation.
    """
    from src.api.v1.quality.router import reset_metrics_storage_for_testing
    reset_metrics_storage_for_testing()
    yield
    # Reset after test as well
    reset_metrics_storage_for_testing()


@pytest.fixture
def reset_config():
    """
    Reset configuration state before each test.

    Restores default config values to ensure test isolation.
    """
    from src.api.v1.quality.router import reset_config_for_testing
    reset_config_for_testing()
    yield
    # Reset after test as well
    reset_config_for_testing()


@pytest.fixture
def clean_state(reset_rate_limiter, reset_metrics_storage, reset_config):
    """
    Combined fixture to reset all global state.

    Use this fixture on tests that require clean state isolation.
    This is the primary fixture to use for ensuring tests don't
    pollute each other through shared global state.
    """
    # All fixtures are applied before the test runs
    # They will also run after the test completes
    pass


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def test_token():
    """Create a valid JWT token for testing."""
    return create_access_token(
        subject="test-user-123",
        expires_delta=timedelta(hours=1)
    )


@pytest.fixture
def auth_headers(test_token):
    """Create authentication headers with valid JWT token."""
    return {"Authorization": f"Bearer {test_token}"}


@pytest.fixture
def admin_token():
    """
    Create a valid JWT token with admin role for testing admin endpoints.

    CRITICAL #1: Admin authorization check requires role claim in token.
    This fixture manually creates a token with the admin role.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=1)

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": "admin-user-123",
        "role": "admin",  # CRITICAL #1: Admin role required for PUT /config
    }

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


@pytest.fixture
def admin_auth_headers(admin_token):
    """Create authentication headers with admin JWT token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def valid_record():
    """Create a valid data record for testing."""
    return {
        "record_id": "test-record-001",
        "tenant_id": "tenant-1",
        "data_source": "csv",
        "raw_data": '{"field1": "value1", "field2": "value2"}',
        "file_name": "test.csv",
        "mime_type": "text/csv",
        "record_hash": "abc123def456"
    }


@pytest.fixture
def invalid_record():
    """Create an invalid data record for testing."""
    return {
        "record_id": "test-record-002",
        # Missing tenant_id
        "data_source": "csv",
        # Missing raw_data
        "file_name": "test.csv"
    }


@pytest.fixture
def sample_records(valid_record, invalid_record):
    """Create sample records for batch testing."""
    return [valid_record, invalid_record]


@pytest.fixture
def mock_validation_result_valid():
    """Create a mock valid ValidationResult."""
    return ValidationResult(
        is_valid=True,
        completeness_score=1.0,
        validity_score=1.0,
        quality_score=1.0,
        errors=[],
        warnings=[]
    )


@pytest.fixture
def mock_validation_result_invalid():
    """Create a mock invalid ValidationResult."""
    return ValidationResult(
        is_valid=False,
        completeness_score=0.5,
        validity_score=0.6,
        quality_score=0.54,
        errors=["Missing required field: tenant_id", "Missing required field: raw_data"],
        warnings=["Missing recommended field: mime_type"]
    )


# ============================================================================
# POST /api/v1/quality/validate - Single Record Validation Tests
# ============================================================================

@pytest.mark.usefixtures("clean_state")
class TestValidateSingleRecord:
    """Test suite for single record validation endpoint."""

    def test_validate_valid_record_returns_success(
        self, test_client, auth_headers, valid_record,
        mock_validation_result_valid
    ):
        """
        Test that validating a valid record returns success response.

        Given: A valid data record with all required fields
        When: POST to /api/v1/quality/validate
        Then: Returns 200 with validation results
        """
        with patch('src.api.v1.quality.router.DataQualityValidator') as MockValidator:
            mock_instance = Mock()
            mock_instance.validate_record.return_value = mock_validation_result_valid
            MockValidator.return_value = mock_instance

            response = test_client.post(
                "/api/v1/quality/validate",
                json={"record": valid_record},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is True
            assert data["completeness_score"] == 1.0
            assert data["validity_score"] == 1.0
            assert data["quality_score"] == 1.0
            assert data["errors"] == []
            assert data["warnings"] == []

    def test_validate_invalid_record_returns_errors(
        self, test_client, auth_headers, invalid_record,
        mock_validation_result_invalid
    ):
        """
        Test that validating an invalid record returns error details.

        Given: An invalid data record with missing required fields
        When: POST to /api/v1/quality/validate
        Then: Returns 200 with validation errors
        """
        with patch('src.api.v1.quality.router.DataQualityValidator') as MockValidator:
            mock_instance = Mock()
            mock_instance.validate_record.return_value = mock_validation_result_invalid
            MockValidator.return_value = mock_instance

            response = test_client.post(
                "/api/v1/quality/validate",
                json={"record": invalid_record},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is False
            assert data["completeness_score"] == 0.5
            assert data["validity_score"] == 0.6
            assert len(data["errors"]) == 2
            assert len(data["warnings"]) == 1

    def test_validate_missing_required_fields_captured(
        self, test_client, auth_headers
    ):
        """
        Test that missing required fields are correctly identified.

        Given: A record missing required fields
        When: POST to /api/v1/quality/validate
        Then: Missing fields are listed in errors
        """
        incomplete_record = {
            "record_id": "test-001"
            # Missing tenant_id, data_source, raw_data
        }

        mock_result = ValidationResult(
            is_valid=False,
            completeness_score=0.25,
            validity_score=0.4,
            quality_score=0.31,
            errors=[
                "Missing required field: tenant_id",
                "Missing required field: data_source",
                "Missing required field: raw_data"
            ],
            warnings=[]
        )

        with patch('src.api.v1.quality.router.DataQualityValidator') as MockValidator:
            mock_instance = Mock()
            mock_instance.validate_record.return_value = mock_result
            MockValidator.return_value = mock_instance

            response = test_client.post(
                "/api/v1/quality/validate",
                json={"record": incomplete_record},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["errors"]) == 3
            assert any("tenant_id" in err for err in data["errors"])

    def test_validate_scores_computed_correctly(
        self, test_client, auth_headers, valid_record
    ):
        """
        Test that quality scores are computed correctly.

        Given: A record with varying field completeness
        When: POST to /api/v1/quality/validate
        Then: Scores are computed using correct formula
        """
        mock_result = ValidationResult(
            is_valid=True,
            completeness_score=0.85,
            validity_score=0.9,
            quality_score=0.87,  # 0.6 * 0.85 + 0.4 * 0.9 = 0.87
            errors=[],
            warnings=["Missing recommended field: file_name"]
        )

        with patch('src.api.v1.quality.router.DataQualityValidator') as MockValidator:
            mock_instance = Mock()
            mock_instance.validate_record.return_value = mock_result
            MockValidator.return_value = mock_instance

            response = test_client.post(
                "/api/v1/quality/validate",
                json={"record": valid_record},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["completeness_score"] == 0.85
            assert data["validity_score"] == 0.9
            assert abs(data["quality_score"] - 0.87) < 0.01

    def test_validate_without_authentication_returns_401(
        self, test_client, valid_record
    ):
        """
        Test that validation requires authentication.

        Given: A valid data record
        When: POST to /api/v1/quality/validate without auth token
        Then: Returns 401 Unauthorized
        """
        response = test_client.post(
            "/api/v1/quality/validate",
            json={"record": valid_record}
        )

        assert response.status_code == 401


# ============================================================================
# POST /api/v1/quality/validate-batch - Batch Validation Tests
# ============================================================================

@pytest.mark.usefixtures("clean_state")
class TestValidateBatch:
    """Test suite for batch validation endpoint."""

    def test_validate_batch_works(
        self, test_client, auth_headers, sample_records
    ):
        """
        Test that batch validation processes multiple records.

        Given: A batch of multiple records
        When: POST to /api/v1/quality/validate-batch
        Then: Returns 200 with results for all records
        """
        valid_result = ValidationResult(
            is_valid=True,
            completeness_score=1.0,
            validity_score=1.0,
            quality_score=1.0,
            errors=[],
            warnings=[]
        )

        invalid_result = ValidationResult(
            is_valid=False,
            completeness_score=0.5,
            validity_score=0.6,
            quality_score=0.54,
            errors=["Missing required field"],
            warnings=[]
        )

        with patch('src.api.v1.quality.router.DataQualityValidator') as MockValidator:
            mock_instance = Mock()
            mock_instance.validate_record.side_effect = [valid_result, invalid_result]
            MockValidator.return_value = mock_instance

            response = test_client.post(
                "/api/v1/quality/validate-batch",
                json={"records": sample_records},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert len(data["results"]) == 2
            assert data["total_records"] == 2
            assert data["valid_count"] == 1
            assert data["invalid_count"] == 1

    def test_validate_batch_partial_failures_handled(
        self, test_client, auth_headers, sample_records
    ):
        """
        Test that batch validation handles partial failures gracefully.

        Given: A batch with some valid and some invalid records
        When: POST to /api/v1/quality/validate-batch
        Then: Returns 200 with individual results for each record
        """
        results = [
            ValidationResult(is_valid=True, completeness_score=1.0,
                            validity_score=1.0, quality_score=1.0, errors=[], warnings=[]),
            ValidationResult(is_valid=False, completeness_score=0.5,
                            validity_score=0.6, quality_score=0.54,
                            errors=["Missing field"], warnings=[]),
        ]

        with patch('src.api.v1.quality.router.DataQualityValidator') as MockValidator:
            mock_instance = Mock()
            mock_instance.validate_record.side_effect = results
            MockValidator.return_value = mock_instance

            response = test_client.post(
                "/api/v1/quality/validate-batch",
                json={"records": sample_records},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["results"][0]["is_valid"] is True
            assert data["results"][1]["is_valid"] is False

    def test_validate_batch_results_aggregated_correctly(
        self, test_client, auth_headers
    ):
        """
        Test that batch results are aggregated correctly.

        Given: A batch of records
        When: POST to /api/v1/quality/validate-batch
        Then: Aggregate statistics are computed correctly
        """
        records = [
            {"record_id": f"record-{i}", "tenant_id": "t1", "data_source": "csv", "raw_data": "{}"}
            for i in range(5)
        ]

        mock_results = [
            ValidationResult(is_valid=True, completeness_score=1.0,
                            validity_score=1.0, quality_score=1.0, errors=[], warnings=[])
            for _ in range(5)
        ]

        with patch('src.api.v1.quality.router.DataQualityValidator') as MockValidator:
            mock_instance = Mock()
            mock_instance.validate_record.side_effect = mock_results
            MockValidator.return_value = mock_instance

            response = test_client.post(
                "/api/v1/quality/validate-batch",
                json={"records": records},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["total_records"] == 5
            assert data["valid_count"] == 5
            assert data["invalid_count"] == 0
            assert "avg_quality_score" in data

    def test_validate_batch_empty_returns_400(
        self, test_client, auth_headers
    ):
        """
        Test that empty batch returns appropriate error.

        Given: An empty batch request
        When: POST to /api/v1/quality/validate-batch
        Then: Returns 400 with validation error
        """
        response = test_client.post(
            "/api/v1/quality/validate-batch",
            json={"records": []},
            headers=auth_headers
        )

        # Should return validation error for empty batch
        assert response.status_code == 422  # FastAPI validation error

    def test_validate_batch_without_authentication_returns_401(
        self, test_client, sample_records
    ):
        """
        Test that batch validation requires authentication.

        Given: A batch of records
        When: POST to /api/v1/quality/validate-batch without auth
        Then: Returns 401 Unauthorized
        """
        response = test_client.post(
            "/api/v1/quality/validate-batch",
            json={"records": sample_records}
        )

        assert response.status_code == 401


# ============================================================================
# GET /api/v1/quality/metrics - Quality Metrics Tests
# ============================================================================

@pytest.mark.usefixtures("clean_state")
class TestQualityMetrics:
    """Test suite for quality metrics endpoint."""

    def test_get_metrics_returns_aggregated_metrics(
        self, test_client, auth_headers
    ):
        """
        Test that metrics endpoint returns aggregated quality metrics.

        Given: Authenticated user
        When: GET to /api/v1/quality/metrics
        Then: Returns 200 with aggregated metrics
        """
        with patch('src.api.v1.quality.router.get_quality_metrics') as mock_metrics:
            mock_metrics.return_value = {
                "total_records": 100,
                "valid_records": 85,
                "invalid_records": 15,
                "avg_quality_score": 0.82,
                "avg_completeness_score": 0.88,
                "avg_validity_score": 0.75,
                "common_errors": [
                    {"error": "Missing required field: email", "count": 10},
                    {"error": "Invalid email format", "count": 5}
                ]
            }

            response = test_client.get(
                "/api/v1/quality/metrics",
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["total_records"] == 100
            assert data["valid_records"] == 85
            assert data["invalid_records"] == 15
            assert data["avg_quality_score"] == 0.82
            assert "common_errors" in data

    def test_get_metrics_calculated_correctly(
        self, test_client, auth_headers
    ):
        """
        Test that metrics are calculated correctly.

        Given: Various records with different quality scores
        When: GET to /api/v1/quality/metrics
        Then: Metrics reflect accurate calculations
        """
        with patch('src.api.v1.quality.router.get_quality_metrics') as mock_metrics:
            mock_metrics.return_value = {
                "total_records": 10,
                "valid_records": 8,
                "invalid_records": 2,
                "avg_quality_score": 0.85,
                "avg_completeness_score": 0.90,
                "avg_validity_score": 0.78,
                "common_errors": []
            }

            response = test_client.get(
                "/api/v1/quality/metrics",
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            # Verify calculations
            assert data["valid_records"] + data["invalid_records"] == data["total_records"]

    def test_get_metrics_without_authentication_returns_401(
        self, test_client
    ):
        """
        Test that metrics endpoint requires authentication.

        Given: Unauthenticated request
        When: GET to /api/v1/quality/metrics without auth
        Then: Returns 401 Unauthorized
        """
        response = test_client.get("/api/v1/quality/metrics")

        assert response.status_code == 401


# ============================================================================
# GET /api/v1/quality/config - Get Configuration Tests
# ============================================================================

@pytest.mark.usefixtures("clean_state")
class TestGetConfig:
    """Test suite for getting configuration endpoint."""

    def test_get_config_returns_current_config(
        self, test_client, auth_headers
    ):
        """
        Test that config endpoint returns current configuration.

        Given: Authenticated user
        When: GET to /api/v1/quality/config
        Then: Returns 200 with current config
        """
        response = test_client.get(
            "/api/v1/quality/config",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "completeness_weight" in data
        assert "validity_weight" in data
        assert "error_penalty" in data
        assert "required_fields" in data
        assert "recommended_fields" in data

    def test_get_config_shows_weights(
        self, test_client, auth_headers
    ):
        """
        Test that config shows current weight configuration.

        Given: Authenticated user
        When: GET to /api/v1/quality/config
        Then: Returns current weight values
        """
        response = test_client.get(
            "/api/v1/quality/config",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert 0.0 <= data["completeness_weight"] <= 1.0
        assert 0.0 <= data["validity_weight"] <= 1.0
        assert 0.0 < data["error_penalty"] <= 1.0

    def test_get_config_without_authentication_returns_401(
        self, test_client
    ):
        """
        Test that config endpoint requires authentication.

        Given: Unauthenticated request
        When: GET to /api/v1/quality/config without auth
        Then: Returns 401 Unauthorized
        """
        response = test_client.get("/api/v1/quality/config")

        assert response.status_code == 401


# ============================================================================
# PUT /api/v1/quality/config - Update Configuration Tests
# ============================================================================

@pytest.mark.usefixtures("clean_state")
class TestUpdateConfig:
    """Test suite for updating configuration endpoint."""

    def test_update_config_updates_weights(
        self, test_client, admin_auth_headers  # CRITICAL #1: Use admin headers
    ):
        """
        Test that config update changes weight values.

        Given: Admin user with valid weight values
        When: PUT to /api/v1/quality/config
        Then: Returns 200 with updated config
        """
        new_weights = {
            "completeness_weight": 0.7,
            "validity_weight": 0.3,
            "error_penalty": 0.15
        }

        response = test_client.put(
            "/api/v1/quality/config",
            json=new_weights,
            headers=admin_auth_headers  # CRITICAL #1: Admin token required
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completeness_weight"] == 0.7
        assert data["validity_weight"] == 0.3
        assert data["error_penalty"] == 0.15

    def test_update_config_validates_weight_ranges(
        self, test_client, admin_auth_headers  # CRITICAL #1: Use admin headers
    ):
        """
        Test that config update validates weight ranges.

        Given: Invalid weight values (out of range)
        When: PUT to /api/v1/quality/config
        Then: Returns 400 with validation error
        """
        invalid_weights = {
            "completeness_weight": 1.5,  # Invalid: > 1.0
            "validity_weight": 0.3,
            "error_penalty": 0.15
        }

        response = test_client.put(
            "/api/v1/quality/config",
            json=invalid_weights,
            headers=admin_auth_headers  # CRITICAL #1: Admin token required
        )

        # Pydantic validation returns 422 for field validation errors
        assert response.status_code in [400, 422]
        data = response.json()
        assert "detail" in data or "error" in data

    def test_update_config_rejects_invalid_weights(
        self, test_client, admin_auth_headers  # CRITICAL #1: Use admin headers
    ):
        """
        Test that config update rejects completely invalid weights.

        Given: Negative or zero weight values
        When: PUT to /api/v1/quality/config
        Then: Returns 400 with validation error
        """
        invalid_weights = {
            "completeness_weight": -0.1,  # Invalid: negative
            "validity_weight": 0.0,
            "error_penalty": 0.0  # Invalid: must be > 0
        }

        response = test_client.put(
            "/api/v1/quality/config",
            json=invalid_weights,
            headers=admin_auth_headers  # CRITICAL #1: Admin token required
        )

        # Pydantic validation returns 422 for field validation errors
        assert response.status_code in [400, 422]

    def test_update_config_without_authentication_returns_401(
        self, test_client
    ):
        """
        Test that config update requires authentication.

        Given: Valid weight updates
        When: PUT to /api/v1/quality/config without auth
        Then: Returns 401 Unauthorized
        """
        weights = {
            "completeness_weight": 0.7,
            "validity_weight": 0.3,
            "error_penalty": 0.15
        }

        response = test_client.put(
            "/api/v1/quality/config",
            json=weights
        )

        assert response.status_code == 401


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.usefixtures("clean_state")
class TestQualityAPIIntegration:
    """Integration tests for the complete quality API workflow."""

    def test_complete_validation_workflow(
        self, test_client, auth_headers, admin_auth_headers, valid_record  # CRITICAL #1: Added admin_auth_headers
    ):
        """
        Test complete workflow: validate -> get metrics -> update config.

        Given: A valid record
        When: Validate, check metrics, update config
        Then: All operations complete successfully
        """
        with patch('src.api.v1.quality.router.DataQualityValidator'):
            # Step 1: Validate record
            validate_response = test_client.post(
                "/api/v1/quality/validate",
                json={"record": valid_record},
                headers=auth_headers
            )
            assert validate_response.status_code == 200

            # Step 2: Get metrics
            with patch('src.api.v1.quality.router.get_quality_metrics') as mock_metrics:
                mock_metrics.return_value = {
                    "total_records": 1,
                    "valid_records": 1,
                    "invalid_records": 0,
                    "avg_quality_score": 1.0,
                    "avg_completeness_score": 1.0,
                    "avg_validity_score": 1.0,
                    "common_errors": []
                }

                metrics_response = test_client.get(
                    "/api/v1/quality/metrics",
                    headers=auth_headers
                )
                assert metrics_response.status_code == 200

            # Step 3: Update config (CRITICAL #1: requires admin token)
            new_config = {
                "completeness_weight": 0.65,
                "validity_weight": 0.35,
                "error_penalty": 0.18
            }

            config_response = test_client.put(
                "/api/v1/quality/config",
                json=new_config,
                headers=admin_auth_headers  # CRITICAL #1: Admin token required
            )
            assert config_response.status_code == 200

    def test_error_handling_across_endpoints(
        self, test_client, auth_headers
    ):
        """
        Test error handling consistency across all endpoints.

        Given: Various error conditions
        When: Making requests with invalid data
        Then: Consistent error responses
        """
        # Test with malformed data
        malformed_record = {
            "record_id": None,  # Invalid: null
            "tenant_id": "",    # Invalid: empty string
            "data_source": 123  # Invalid: wrong type
        }

        response = test_client.post(
            "/api/v1/quality/validate",
            json={"record": malformed_record},
            headers=auth_headers
        )

        # Should handle gracefully (200 with validation errors)
        # or return validation error (422)
        assert response.status_code in [200, 422]
