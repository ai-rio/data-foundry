"""
Consent API Endpoint Integration Tests

Tests all consent management API endpoints with actual database interactions,
authentication, authorization, and request/response validation.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException, status

# Import API components
from src.api.v1.consent.router import router, ConsentRateLimiter, verify_user_access
from src.api.v1.consent.contracts import (
    GrantConsentRequest,
    WithdrawConsentRequest,
    ObjectToProcessingRequest,
    VerifyConsentRequest,
    ConsentQueryParams,
    ConsentRecordResponse,
    ConsentHistoryResponse,
    ConsentVerificationResponse,
    ObjectionResponse,
    ErrorResponse,
)

# Import system components
from src.core.security import SecurityManager
from src.core.consent_manager import ConsentManager
from src.core.database import DatabaseManager
from src.core.audit_service import AuditService


class TestConsentAPIBase:
    """Base class for API tests with common setup."""

    @pytest.fixture
    def app(self, consent_manager):
        """Create FastAPI app with consent router."""
        app = FastAPI(
            title="Consent Management API Test",
            description="Test API for consent management endpoints",
            version="1.0.0"
        )

        # Override dependencies to use test fixtures
        app.dependency_overrides[router.dependencies[0].dependency] = lambda: consent_manager

        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    async def auth_headers(self, security_manager, test_user_data):
        """Create authenticated headers for requests."""
        token_claims = {
            "user_id": test_user_data["user_id"],
            "tenant_id": test_user_data["tenant_id"],
            "permissions": ["read:consent", "write:consent", "delete:consent"]
        }

        token = await security_manager.generate_token(token_claims)
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture
    async def unauthorized_headers(self, security_manager):
        """Create headers for unauthorized user."""
        token_claims = {
            "user_id": "unauthorized_user",
            "tenant_id": "other_tenant",
            "permissions": ["read:public"]
        }

        token = await security_manager.generate_token(token_claims)
        return {"Authorization": f"Bearer {token}"}


class TestGrantConsentEndpoint(TestConsentAPIBase):
    """Test the grant consent endpoint."""

    def test_grant_consent_success(self, client, auth_headers, test_user_data, sample_consent_text):
        """Test successful consent granting."""
        request_data = {
            "consent_type": "analytics_processing",
            "consent_text": sample_consent_text,
            "metadata": {
                "ip": test_user_data["ip_address"],
                "user_agent": test_user_data["user_agent"],
                "source": "web_form",
                "version": "1.0"
            }
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "consent_id" in data or "success" in data
        if "consent_id" in data:
            assert data["consent_id"] is not None

    def test_grant_consent_invalid_text(self, client, auth_headers, test_user_data):
        """Test consent granting with invalid text."""
        request_data = {
            "consent_type": "test_consent",
            "consent_text": "I agree",  # Too vague
            "metadata": {
                "ip": test_user_data["ip_address"],
                "user_agent": test_user_data["user_agent"]
            }
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "specific" in data["detail"].lower() or "vague" in data["detail"].lower()

    def test_grant_consent_missing_metadata(self, client, auth_headers, sample_consent_text):
        """Test consent granting with missing required metadata."""
        request_data = {
            "consent_type": "test_consent",
            "consent_text": sample_consent_text,
            "metadata": {
                "source": "web_form"
                # Missing IP and user_agent
            }
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "ip" in data["detail"].lower() or "user_agent" in data["detail"].lower()

    def test_grant_consent_unauthorized(self, client, unauthorized_headers, sample_consent_text):
        """Test consent granting without proper authorization."""
        request_data = {
            "consent_type": "test_consent",
            "consent_text": sample_consent_text,
            "metadata": {"ip": "192.168.1.1", "user_agent": "TestAgent"}
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers=unauthorized_headers
        )

        assert response.status_code in [401, 403]

    def test_grant_consent_rate_limit(self, client, auth_headers, sample_consent_text):
        """Test rate limiting on grant consent endpoint."""
        request_data = {
            "consent_type": "test_consent",
            "consent_text": sample_consent_text,
            "metadata": {"ip": "192.168.1.1", "user_agent": "TestAgent"}
        }

        # Make rapid requests
        responses = []
        for _ in range(120):  # Exceed typical rate limit
            response = client.post(
                "/consent/grant",
                json=request_data,
                headers=auth_headers
            )
            responses.append(response.status_code)

        # Should eventually be rate limited
        assert 429 in responses  # Too Many Requests

    def test_grant_consent_duplicate(self, client, auth_headers, sample_consent_text, test_user_data):
        """Test granting duplicate consent."""
        request_data = {
            "consent_type": "duplicate_test",
            "consent_text": sample_consent_text,
            "metadata": {
                "ip": test_user_data["ip_address"],
                "user_agent": test_user_data["user_agent"]
            }
        }

        # First request should succeed
        response1 = client.post("/consent/grant", json=request_data, headers=auth_headers)
        assert response1.status_code == 200

        # Second request should also succeed (creates new version)
        response2 = client.post("/consent/grant", json=request_data, headers=auth_headers)
        assert response2.status_code == 200


class TestVerifyConsentEndpoint(TestConsentAPIBase):
    """Test the verify consent endpoint."""

    @pytest.fixture(autouse=True)
    async def setup_test_consent(self, consent_manager, test_user_data, sample_consent_text):
        """Create a test consent for verification tests."""
        await consent_manager.record_consent(
            user_id=test_user_data["user_id"],
            consent_type="verification_test",
            consent_text=sample_consent_text,
            metadata={
                "ip": test_user_data["ip_address"],
                "user_agent": test_user_data["user_agent"]
            }
        )

    def test_verify_active_consent(self, client, auth_headers):
        """Test verifying an active consent."""
        request_data = {
            "consent_type": "verification_test"
        }

        response = client.post(
            "/consent/verify",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_consent"] is True
        assert data["consent_type"] == "verification_test"
        assert "granted_at" in data

    def test_verify_nonexistent_consent(self, client, auth_headers):
        """Test verifying a consent that doesn't exist."""
        request_data = {
            "consent_type": "nonexistent_consent"
        }

        response = client.post(
            "/consent/verify",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_consent"] is False
        assert data["consent_type"] == "nonexistent_consent"

    def test_verify_withdrawn_consent(self, client, auth_headers, consent_manager, test_user_data):
        """Test verifying a withdrawn consent."""
        # Withdraw the consent first
        await consent_manager.withdraw_consent(test_user_data["user_id"], "verification_test")

        request_data = {
            "consent_type": "verification_test"
        }

        response = client.post(
            "/consent/verify",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_consent"] is False

    def test_verify_missing_consent_type(self, client, auth_headers):
        """Test verification with missing consent type."""
        request_data = {}  # Missing consent_type

        response = client.post(
            "/consent/verify",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error


class TestWithdrawConsentEndpoint(TestConsentAPIBase):
    """Test the withdraw consent endpoint."""

    @pytest.fixture(autouse=True)
    async def setup_test_consent(self, consent_manager, test_user_data, sample_consent_text):
        """Create a test consent for withdrawal tests."""
        await consent_manager.record_consent(
            user_id=test_user_data["user_id"],
            consent_type="withdrawal_test",
            consent_text=sample_consent_text,
            metadata={
                "ip": test_user_data["ip_address"],
                "user_agent": test_user_data["user_agent"]
            }
        )

    def test_withdraw_active_consent(self, client, auth_headers):
        """Test withdrawing an active consent."""
        request_data = {
            "consent_type": "withdrawal_test",
            "reason": "User requested withdrawal"
        }

        response = client.post(
            "/consent/withdraw",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "withdrawn_at" in data

        # Verify consent is now withdrawn
        verify_data = {
            "consent_type": "withdrawal_test"
        }
        verify_response = client.post("/consent/verify", json=verify_data, headers=auth_headers)
        assert verify_response.json()["has_consent"] is False

    def test_withdraw_nonexistent_consent(self, client, auth_headers):
        """Test withdrawing a consent that doesn't exist."""
        request_data = {
            "consent_type": "nonexistent_consent"
        }

        response = client.post(
            "/consent/withdraw",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_withdraw_already_withdrawn(self, client, auth_headers, consent_manager, test_user_data):
        """Test withdrawing an already withdrawn consent."""
        # Withdraw the consent first
        await consent_manager.withdraw_consent(test_user_data["user_id"], "withdrawal_test")

        request_data = {
            "consent_type": "withdrawal_test"
        }

        response = client.post(
            "/consent/withdraw",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 404  # Already withdrawn/not found

    def test_withdraw_unauthorized(self, client, unauthorized_headers):
        """Test withdrawal without proper authorization."""
        request_data = {
            "consent_type": "withdrawal_test"
        }

        response = client.post(
            "/consent/withdraw",
            json=request_data,
            headers=unauthorized_headers
        )

        assert response.status_code in [401, 403]


class TestObjectionEndpoint(TestConsentAPIBase):
    """Test the objection to processing endpoint."""

    def test_file_objection(self, client, auth_headers):
        """Test filing an objection to processing."""
        request_data = {
            "consent_type": "direct_marketing",
            "reason": "I object to processing my data for direct marketing purposes under GDPR Article 21",
            "category": "marketing"
        }

        response = client.post(
            "/consent/object",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "objection_id" in data or "recorded_at" in data

    def test_file_objection_short_reason(self, client, auth_headers):
        """Test objection with insufficient reason."""
        request_data = {
            "consent_type": "test_processing",
            "reason": "No",  # Too short
            "category": "general"
        }

        response = client.post(
            "/consent/object",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 400
        data = response.json()
        assert "reason" in data["detail"].lower()

    def test_file_objection_unauthorized(self, client, unauthorized_headers):
        """Test objection without proper authorization."""
        request_data = {
            "consent_type": "test_processing",
            "reason": "I object to this processing",
            "category": "general"
        }

        response = client.post(
            "/consent/object",
            json=request_data,
            headers=unauthorized_headers
        )

        assert response.status_code in [401, 403]

    def test_check_objection(self, client, auth_headers, consent_manager, test_user_data):
        """Test checking for existing objections."""
        # First file an objection
        await consent_manager.object_to_processing(
            user_id=test_user_data["user_id"],
            consent_type="test_processing",
            reason="Test objection for API testing",
            category="test"
        )

        # Check for objection
        response = client.get(
            "/consent/check-objection/test_processing",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_objection"] is True
        assert data["consent_type"] == "test_processing"


class TestConsentHistoryEndpoint(TestConsentAPIBase):
    """Test the consent history endpoint."""

    @pytest.fixture(autouse=True)
    async def setup_multiple_consents(self, consent_manager, test_user_data, sample_consent_text):
        """Create multiple consent records for history testing."""
        consent_types = ["history_test_1", "history_test_2", "history_test_3"]

        for consent_type in consent_types:
            await consent_manager.record_consent(
                user_id=test_user_data["user_id"],
                consent_type=consent_type,
                consent_text=sample_consent_text,
                metadata={
                    "ip": test_user_data["ip_address"],
                    "user_agent": test_user_data["user_agent"]
                }
            )

        # Withdraw one consent
        await consent_manager.withdraw_consent(test_user_data["user_id"], "history_test_2")

    def test_get_consent_history(self, client, auth_headers):
        """Test retrieving consent history."""
        response = client.get(
            "/consent/history",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "consents" in data
        assert len(data["consents"]) >= 3

        # Check that withdrawn consent is included
        consent_types = [c["consent_type"] for c in data["consents"]]
        assert "history_test_1" in consent_types
        assert "history_test_2" in consent_types
        assert "history_test_3" in consent_types

    def test_get_consent_history_filtered(self, client, auth_headers):
        """Test retrieving consent history with filters."""
        params = {
            "status": "active",
            "limit": 2
        }

        response = client.get(
            "/consent/history",
            params=params,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "consents" in data
        assert len(data["consents"]) <= 2

        # All returned consents should be active
        for consent in data["consents"]:
            assert consent["status"] == "active"

    def test_get_consent_history_pagination(self, client, auth_headers):
        """Test pagination of consent history."""
        params = {
            "limit": 1,
            "offset": 0
        }

        # Get first page
        response1 = client.get(
            "/consent/history",
            params=params,
            headers=auth_headers
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["consents"]) == 1

        # Get second page
        params["offset"] = 1
        response2 = client.get(
            "/consent/history",
            params=params,
            headers=auth_headers
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["consents"]) == 1

        # Ensure different results
        assert data1["consents"][0]["consent_type"] != data2["consents"][0]["consent_type"]

    def test_get_consent_history_unauthorized(self, client, unauthorized_headers):
        """Test retrieving consent history without authorization."""
        response = client.get(
            "/consent/history",
            headers=unauthorized_headers
        )

        assert response.status_code in [401, 403]


class TestErrorHandling(TestConsentAPIBase):
    """Test error handling across all endpoints."""

    def test_invalid_json(self, client, auth_headers):
        """Test handling of invalid JSON in request body."""
        response = client.post(
            "/consent/grant",
            data="invalid json",
            headers=auth_headers,
            headers={"Content-Type": "application/json", **auth_headers}
        )

        assert response.status_code == 422

    def test_missing_required_field(self, client, auth_headers):
        """Test handling of missing required fields."""
        request_data = {
            "consent_type": "test_consent"
            # Missing consent_text and metadata
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 422

    def test_invalid_token(self, client):
        """Test handling of invalid authentication token."""
        headers = {"Authorization": "Bearer invalid_token"}

        response = client.get(
            "/consent/history",
            headers=headers
        )

        assert response.status_code in [401, 403]

    def test_expired_token(self, client, security_manager, test_user_data):
        """Test handling of expired authentication token."""
        # Create expired token
        token_claims = {
            "user_id": test_user_data["user_id"],
            "tenant_id": test_user_data["tenant_id"],
            "exp": datetime.now(timezone.utc) - timedelta(hours=1)  # Expired
        }

        expired_token = await security_manager.generate_token(token_claims)
        headers = {"Authorization": f"Bearer {expired_token}"}

        response = client.get(
            "/consent/history",
            headers=headers
        )

        assert response.status_code in [401, 403]

    def test_database_error_handling(self, client, auth_headers, monkeypatch):
        """Test handling of database errors."""
        # Mock database manager to raise an error
        async def mock_create_consent(*args, **kwargs):
            raise Exception("Database connection failed")

        monkeypatch.setattr(
            "src.core.consent_manager.ConsentManager.record_consent",
            mock_create_consent
        )

        request_data = {
            "consent_type": "test_consent",
            "consent_text": "Valid consent text for testing database error handling",
            "metadata": {"ip": "192.168.1.1", "user_agent": "TestAgent"}
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers=auth_headers
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data


class TestRequestResponseValidation(TestConsentAPIBase):
    """Test request and response validation."""

    def test_response_structure(self, client, auth_headers, sample_consent_text):
        """Test that responses have correct structure."""
        # Test grant consent response
        grant_data = {
            "consent_type": "response_test",
            "consent_text": sample_consent_text,
            "metadata": {"ip": "192.168.1.1", "user_agent": "TestAgent"}
        }

        grant_response = client.post(
            "/consent/grant",
            json=grant_data,
            headers=auth_headers
        )

        assert grant_response.status_code == 200
        grant_data = grant_response.json()
        assert isinstance(grant_data, dict)

        # Test verify consent response
        verify_data = {
            "consent_type": "response_test"
        }

        verify_response = client.post(
            "/consent/verify",
            json=verify_data,
            headers=auth_headers
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert "has_consent" in verify_data
        assert isinstance(verify_data["has_consent"], bool)
        assert "consent_type" in verify_data
        assert isinstance(verify_data["consent_type"], str)

        # Test history response
        history_response = client.get(
            "/consent/history",
            headers=auth_headers
        )

        assert history_response.status_code == 200
        history_data = history_response.json()
        assert "consents" in history_data
        assert isinstance(history_data["consents"], list)

    def test_cors_headers(self, client, auth_headers):
        """Test that CORS headers are properly set."""
        response = client.options(
            "/consent/grant",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                **auth_headers
            }
        )

        # CORS headers should be present if implemented
        # This test depends on the actual CORS implementation

    def test_content_type_handling(self, client, auth_headers, sample_consent_text):
        """Test handling of different content types."""
        # Test with application/json
        request_data = {
            "consent_type": "content_type_test",
            "consent_text": sample_consent_text,
            "metadata": {"ip": "192.168.1.1", "user_agent": "TestAgent"}
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers={"Content-Type": "application/json", **auth_headers}
        )
        assert response.status_code == 200

        # Test without content-type header
        response = client.post(
            "/consent/grant",
            data=json.dumps(request_data),
            headers=auth_headers
        )
        assert response.status_code == 200


class TestAPIPerformance(TestConsentAPIBase):
    """Test API endpoint performance."""

    def test_concurrent_requests(self, client, auth_headers, sample_consent_text):
        """Test handling of concurrent requests."""
        import concurrent.futures
        import threading

        request_data = {
            "consent_type": "concurrent_test",
            "consent_text": sample_consent_text,
            "metadata": {"ip": "192.168.1.1", "user_agent": "TestAgent"}
        }

        def make_request(request_id):
            """Make a single request with unique ID."""
            data = request_data.copy()
            data["consent_type"] = f"concurrent_test_{request_id}"

            response = client.post(
                "/consent/grant",
                json=data,
                headers=auth_headers
            )
            return response.status_code

        # Make 20 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            results = [f.result() for f in futures]

        # All requests should succeed
        assert all(status == 200 for status in results)

    def test_large_payload_handling(self, client, auth_headers):
        """Test handling of large request payloads."""
        large_consent_text = "I consent " * 10000  # Large text
        large_metadata = {
            "ip": "192.168.1.1",
            "user_agent": "TestAgent",
            "large_field": "x" * 10000  # Large metadata field
        }

        request_data = {
            "consent_type": "large_payload_test",
            "consent_text": large_consent_text,
            "metadata": large_metadata
        }

        response = client.post(
            "/consent/grant",
            json=request_data,
            headers=auth_headers,
            timeout=30.0  # Longer timeout for large payload
        )

        # Should either succeed or fail with appropriate error
        if response.status_code == 200:
            # Success case
            pass
        elif response.status_code == 413:
            # Payload too large
            pass
        else:
            # Other error
            assert False, f"Unexpected status code: {response.status_code}"


# Utility function to run all API tests
async def run_api_integration_tests():
    """Run all API integration tests and return results."""
    import subprocess
    import sys

    cmd = [
        sys.executable, "-m", "pytest",
        __file__,
        "-v",
        "--tb=short",
        "--cov=src.api",
        "--cov-report=html:api_coverage_html",
        "--cov-report=xml:api_coverage.xml",
        "--html=api_test_report.html",
        "--self-contained-html"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    return {
        "exit_code": result.returncode,
        "output": result.stdout,
        "errors": result.stderr
    }


if __name__ == "__main__":
    # Run tests when executed directly
    import asyncio
    results = asyncio.run(run_api_integration_tests())
    print(f"API Integration Tests: {'PASSED' if results['exit_code'] == 0 else 'FAILED'}")