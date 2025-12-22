"""
Tests for Consent API Endpoints

Tests all consent management API endpoints to ensure:
- GDPR compliance
- Proper request/response validation
- Error handling
- Rate limiting
- Authentication and authorization
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any

from src.main import app
from src.api.v1.consent.contracts import (
    GrantConsentRequest,
    WithdrawConsentRequest,
    ObjectToProcessingRequest,
    ConsentType,
    ObjectionCategory,
    MetadataModel,
)
from src.models.consent import ConsentRecordDB
from src.models.enums import ConsentStatus


class TestConsentEndpoints:
    """Test suite for consent API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Create authentication headers."""
        return {"Authorization": "Bearer test_token"}

    @pytest.fixture
    def mock_current_user(self):
        """Mock current user for authentication."""
        return {
            "user_id": "test_user_123",
            "tenant_id": "test_tenant_123",
            "email": "test@example.com",
            "role": "user"
        }

    @pytest.fixture
    def sample_consent_request(self):
        """Sample consent request for testing."""
        return GrantConsentRequest(
            user_id="test_user_123",
            consent_type=ConsentType.DATA_PROCESSING,
            consent_text="I consent to the processing of my personal data for the purpose of improving services. This includes analysis of usage patterns, personalization of content, and storage of data for a period of 2 years. I understand that I can withdraw this consent at any time.",
            metadata=MetadataModel(
                ip="192.168.1.1",
                user_agent="Mozilla/5.0 (Test Browser)",
                purpose="service_improvement",
                retention_period="2_years",
                source="webform"
            )
        )

    @pytest.fixture
    def sample_withdraw_request(self):
        """Sample withdraw request for testing."""
        return WithdrawConsentRequest(
            user_id="test_user_123",
            consent_type=ConsentType.DATA_PROCESSING,
            reason="No longer wish to participate",
            metadata=MetadataModel(
                ip="192.168.1.1",
                user_agent="Mozilla/5.0 (Test Browser)"
            )
        )

    @pytest.fixture
    def sample_objection_request(self):
        """Sample objection request for testing."""
        return ObjectToProcessingRequest(
            user_id="test_user_123",
            consent_type=ConsentType.MARKETING,
            reason="I do not want my data used for marketing purposes",
            category=ObjectionCategory.DIRECT_MARKETING,
            metadata=MetadataModel(
                ip="192.168.1.1",
                user_agent="Mozilla/5.0 (Test Browser)"
            )
        )

    @pytest.fixture
    def mock_consent_record(self):
        """Mock consent record for testing."""
        return ConsentRecordDB(
            id=1,
            user_id="test_user_123",
            consent_type="data_processing",
            consent_text="Sample consent text for testing purposes. This includes detailed explanation of data processing activities.",
            granted_at=datetime.now(timezone.utc),
            ip_address="hashed_ip",
            user_agent="test_browser",
            status=ConsentStatus.ACTIVE,
            consent_metadata={"source": "webform"}
        )

    # Test Grant Consent Endpoint
    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_grant_consent_success(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        sample_consent_request,
        mock_consent_record
    ):
        """Test successful consent granting."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Mock the consent manager
        mock_manager_instance = AsyncMock()
        mock_manager_instance.record_consent.return_value = mock_consent_record
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make request
        response = client.post(
            "/api/v1/consent/grant",
            json=sample_consent_request.dict(),
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "Consent granted successfully" in data["message"]
        assert data["data"]["user_id"] == "test_user_123"
        assert data["data"]["consent_type"] == "data_processing"

    @patch('src.api.v1.consent.router.get_current_user_token')
    async def test_grant_consent_invalid_text(
        self,
        mock_auth,
        client,
        auth_headers,
        mock_current_user
    ):
        """Test consent granting with invalid text."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Create invalid request (too short text)
        invalid_request = {
            "user_id": "test_user_123",
            "consent_type": "data_processing",
            "consent_text": "I agree",  # Too short and generic
            "metadata": {
                "ip": "192.168.1.1",
                "user_agent": "Test Browser"
            }
        }

        # Make request
        response = client.post(
            "/api/v1/consent/grant",
            json=invalid_request,
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 422  # Validation error

    # Test Withdraw Consent Endpoint
    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_withdraw_consent_success(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        sample_withdraw_request
    ):
        """Test successful consent withdrawal."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Mock the consent manager
        mock_manager_instance = AsyncMock()
        mock_manager_instance.withdraw_consent.return_value = True
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make request
        response = client.post(
            "/api/v1/consent/withdraw",
            json=sample_withdraw_request.dict(),
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Consent withdrawn successfully" in data["message"]
        assert data["data"]["user_id"] == "test_user_123"

    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_withdraw_consent_not_found(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        sample_withdraw_request
    ):
        """Test withdrawing non-existent consent."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Mock the consent manager to return False (consent not found)
        mock_manager_instance = AsyncMock()
        mock_manager_instance.withdraw_consent.return_value = False
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make request
        response = client.post(
            "/api/v1/consent/withdraw",
            json=sample_withdraw_request.dict(),
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 404
        assert "No active consent found" in response.json()["detail"]

    # Test Verify Consent Endpoint
    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_verify_consent_active(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        mock_consent_record
    ):
        """Test verifying active consent."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Mock the consent manager
        mock_manager_instance = AsyncMock()
        mock_manager_instance.verify_consent.return_value = True
        mock_manager_instance.db_manager = AsyncMock()
        mock_manager_instance.db_manager.get_active_consent.return_value = mock_consent_record
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make request
        response = client.get(
            "/api/v1/consent/verify/test_user_123/data_processing",
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test_user_123"
        assert data["consent_type"] == "data_processing"
        assert data["has_consent"] is True

    # Test Object to Processing Endpoint
    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_object_to_processing_success(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        sample_objection_request
    ):
        """Test successful processing objection."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Mock the consent manager
        mock_manager_instance = AsyncMock()
        mock_manager_instance.object_to_processing.return_value = True
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make request
        response = client.post(
            "/api/v1/consent/object",
            json=sample_objection_request.dict(),
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == "test_user_123"
        assert data["consent_type"] == "marketing"
        assert data["category"] == "direct_marketing"

    # Test Get User Consents Endpoint
    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_get_user_consents_success(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        mock_consent_record
    ):
        """Test getting user consents successfully."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Mock the consent manager
        mock_manager_instance = AsyncMock()
        mock_manager_instance.db_manager = AsyncMock()
        mock_manager_instance.db_manager.get_consent_history.return_value = [
            mock_consent_record.to_dict() if hasattr(mock_consent_record, 'to_dict') else {
                "id": 1,
                "user_id": "test_user_123",
                "consent_type": "data_processing",
                "consent_text": "Sample consent text",
                "granted_at": datetime.now(timezone.utc).isoformat(),
                "status": ConsentStatus.ACTIVE.value,
                "metadata": {}
            }
        ]
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make request
        response = client.get(
            "/api/v1/consent/user/test_user_123",
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["user_id"] == "test_user_123"

    # Test Get Consent History Endpoint
    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_get_consent_history_success(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        mock_consent_record
    ):
        """Test getting consent history successfully."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Create multiple consent records for testing pagination
        consent_records = []
        for i in range(25):
            record = {
                "id": i,
                "user_id": "test_user_123",
                "consent_type": "data_processing",
                "consent_text": f"Sample consent text {i}",
                "granted_at": datetime.now(timezone.utc).isoformat(),
                "status": ConsentStatus.ACTIVE.value,
                "metadata": {}
            }
            consent_records.append(record)

        # Mock the consent manager
        mock_manager_instance = AsyncMock()
        mock_manager_instance.db_manager = AsyncMock()
        mock_manager_instance.db_manager.get_consent_history.return_value = consent_records
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make request with pagination
        response = client.get(
            "/api/v1/consent/user/test_user_123/history?page=1&per_page=10",
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test_user_123"
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert len(data["records"]) == 10
        assert data["total"] == 25
        assert data["has_more"] is True

    # Test Authentication Required
    def test_endpoints_require_authentication(self, client):
        """Test that all endpoints require authentication."""
        endpoints = [
            ("POST", "/api/v1/consent/grant", {}),
            ("POST", "/api/v1/consent/withdraw", {}),
            ("GET", "/api/v1/consent/verify/user123/data_processing", None),
            ("POST", "/api/v1/consent/object", {}),
            ("GET", "/api/v1/consent/user/user123", None),
            ("GET", "/api/v1/consent/user/user123/history", None),
        ]

        for method, endpoint, data in endpoints:
            if method == "POST":
                response = client.post(endpoint, json=data)
            else:
                response = client.get(endpoint)

            # Should return 401 or 403 for unauthenticated requests
            assert response.status_code in [401, 403]

    # Test Rate Limiting
    @patch('src.api.v1.consent.router.get_current_user_token')
    @patch('src.api.v1.consent.router.ConsentManager')
    @patch('src.api.v1.consent.router.DatabaseManager')
    @patch('src.api.v1.consent.router.AuditService')
    async def test_rate_limiting(
        self,
        mock_audit_service,
        mock_db_manager,
        mock_consent_manager,
        mock_auth,
        client,
        auth_headers,
        mock_current_user,
        sample_consent_request
    ):
        """Test rate limiting on consent endpoints."""
        # Setup mocks
        mock_auth.return_value = mock_current_user

        # Mock the consent manager
        mock_manager_instance = AsyncMock()
        mock_manager_instance.record_consent.return_value = None
        mock_consent_manager.return_value = mock_manager_instance

        # Mock database manager
        mock_db_instance = AsyncMock()
        mock_db_instance.initialize.return_value = None
        mock_db_manager.return_value = mock_db_instance

        # Mock audit service
        mock_audit_instance = AsyncMock()
        mock_audit_service.return_value = mock_audit_instance

        # Make many requests to trigger rate limiting
        responses = []
        for i in range(105):  # Exceed default rate limit of 100
            response = client.post(
                "/api/v1/consent/grant",
                json=sample_consent_request.dict(),
                headers=auth_headers
            )
            responses.append(response)
            if response.status_code == 429:
                break

        # Should eventually hit rate limit
        rate_limited = any(r.status_code == 429 for r in responses)
        assert rate_limited, "Rate limiting should be triggered after many requests"