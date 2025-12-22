"""
Test-Driven Development for Consent Management System

This test file defines the expected behavior of the consent management system
before implementation begins, following TDD principles.

Tests are written first, then implementation follows to make them pass.

GDPR References:
- Article 7(1): Conditions for consent
- Article 7(3): Right to withdraw consent
- Article 21: Right to object to processing
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock
from typing import Optional

# Import the classes we will create
from src.core.consent_manager import ConsentManager, ConsentRecord


class TestConsentRecord:
    """Test the ConsentRecord data model"""

    def test_consent_record_creation_minimal(self):
        """Test creating consent record with minimal required fields"""
        record = ConsentRecord(
            user_id="user123",
            consent_type="data_processing",
            consent_text="I consent to processing of my data",
            granted_at=datetime.now(timezone.utc),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0"
        )

        assert record.user_id == "user123"
        assert record.consent_type == "data_processing"
        assert record.status == "active"  # Default should be active
        assert record.withdrawn_at is None

    def test_consent_record_withdrawal(self):
        """Test withdrawing consent"""
        record = ConsentRecord(
            user_id="user123",
            consent_type="data_processing",
            consent_text="I consent to processing of my data",
            granted_at=datetime.now(timezone.utc),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0"
        )

        # Withdraw consent
        record.withdraw()

        assert record.status == "withdrawn"
        assert record.withdrawn_at is not None
        assert record.withdrawn_at >= record.granted_at


class TestConsentManager:
    """Test the ConsentManager business logic"""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager"""
        mock_db = AsyncMock()
        mock_db.create_consent_record = AsyncMock(return_value="consent_id_123")
        mock_db.get_active_consent = AsyncMock(return_value=None)  # No existing consent
        mock_db.update_consent_record = AsyncMock()
        return mock_db

    @pytest.fixture
    def mock_audit_service(self):
        """Mock audit service"""
        mock_audit = AsyncMock()
        mock_audit.log_consent_granted = AsyncMock()
        mock_audit.log_consent_withdrawn = AsyncMock()
        return mock_audit

    @pytest.fixture
    def consent_manager(self, mock_db_manager, mock_audit_service):
        """Create consent manager with mocked dependencies"""
        return ConsentManager(mock_db_manager, mock_audit_service)

    @pytest.mark.asyncio
    async def test_record_consent_success(self, consent_manager, mock_db_manager, mock_audit_service):
        """Test successful consent recording"""

        # Given
        user_id = "user123"
        consent_type = "data_processing"
        consent_text = "I consent to processing of my personal data for analytics purposes"
        metadata = {
            "ip": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }

        # When
        result = await consent_manager.record_consent(user_id, consent_type, consent_text, metadata)

        # Then
        assert result.user_id == user_id
        assert result.consent_type == consent_type
        assert result.consent_text == consent_text
        assert result.status == "active"
        assert result.granted_at is not None

        # Verify database was called
        mock_db_manager.create_consent_record.assert_called_once()

        # Verify audit was called
        mock_audit_service.log_consent_granted.assert_called_once_with(
            user_id=user_id,
            consent_type=consent_type,
            timestamp=result.granted_at
        )

    @pytest.mark.asyncio
    async def test_record_consent_requires_consent_text(self, consent_manager):
        """Test that consent text is required"""

        # Given
        user_id = "user123"
        consent_type = "data_processing"
        consent_text = ""  # Empty consent text
        metadata = {"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"}

        # When & Then
        with pytest.raises(ValueError, match="Consent text cannot be empty"):
            await consent_manager.record_consent(user_id, consent_type, consent_text, metadata)

    @pytest.mark.asyncio
    async def test_verify_consent_no_existing_consent(self, consent_manager, mock_db_manager):
        """Test consent verification when no consent exists"""

        # Given
        user_id = "user123"
        consent_type = "data_processing"
        mock_db_manager.get_active_consent.return_value = None

        # When
        result = await consent_manager.verify_consent(user_id, consent_type)

        # Then
        assert result is False
        mock_db_manager.get_active_consent.assert_called_once_with(user_id, consent_type)

    @pytest.mark.asyncio
    async def test_verify_consent_existing_active_consent(self, consent_manager, mock_db_manager):
        """Test consent verification when active consent exists"""

        # Given
        user_id = "user123"
        consent_type = "data_processing"

        existing_consent = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            consent_text="I consent",
            granted_at=datetime.now(timezone.utc) - timedelta(days=1),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0"
        )

        mock_db_manager.get_active_consent.return_value = existing_consent

        # When
        result = await consent_manager.verify_consent(user_id, consent_type)

        # Then
        assert result is True
        mock_db_manager.get_active_consent.assert_called_once_with(user_id, consent_type)

    @pytest.mark.asyncio
    async def test_verify_consent_withdrawn_consent(self, consent_manager, mock_db_manager):
        """Test consent verification when consent has been withdrawn"""

        # Given
        user_id = "user123"
        consent_type = "data_processing"

        withdrawn_consent = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            consent_text="I consent",
            granted_at=datetime.now(timezone.utc) - timedelta(days=1),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0"
        )
        withdrawn_consent.withdraw()

        mock_db_manager.get_active_consent.return_value = withdrawn_consent

        # When
        result = await consent_manager.verify_consent(user_id, consent_type)

        # Then
        assert result is False
        mock_db_manager.get_active_consent.assert_called_once_with(user_id, consent_type)

    @pytest.mark.asyncio
    async def test_withdraw_consent_success(self, consent_manager, mock_db_manager, mock_audit_service):
        """Test successful consent withdrawal"""

        # Given
        user_id = "user123"
        consent_type = "data_processing"

        existing_consent = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            consent_text="I consent",
            granted_at=datetime.now(timezone.utc) - timedelta(days=1),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0"
        )

        mock_db_manager.get_active_consent.return_value = existing_consent

        # When
        result = await consent_manager.withdraw_consent(user_id, consent_type)

        # Then
        assert result is True
        assert existing_consent.status == "withdrawn"
        assert existing_consent.withdrawn_at is not None

        # Verify database update was called
        mock_db_manager.update_consent_record.assert_called_once_with(existing_consent)

        # Verify audit was called
        mock_audit_service.log_consent_withdrawn.assert_called_once()

    @pytest.mark.asyncio
    async def test_withdraw_consent_no_existing_consent(self, consent_manager, mock_db_manager):
        """Test consent withdrawal when no consent exists"""

        # Given
        user_id = "user123"
        consent_type = "data_processing"
        mock_db_manager.get_active_consent.return_value = None

        # When
        result = await consent_manager.withdraw_consent(user_id, consent_type)

        # Then
        assert result is False
        mock_db_manager.update_consent_record.assert_not_called()


class TestGDPRCompliance:
    """Test specific GDPR compliance requirements"""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager"""
        mock_db = AsyncMock()
        mock_db.create_consent_record = AsyncMock(return_value="consent_id_123")
        mock_db.get_active_consent = AsyncMock(return_value=None)  # No existing consent
        mock_db.update_consent_record = AsyncMock()
        return mock_db

    @pytest.fixture
    def mock_audit_service(self):
        """Mock audit service"""
        mock_audit = AsyncMock()
        mock_audit.log_consent_granted = AsyncMock()
        mock_audit.log_consent_withdrawn = AsyncMock()
        return mock_audit

    @pytest.fixture
    def consent_manager(self, mock_db_manager, mock_audit_service):
        """Create consent manager with mocked dependencies"""
        return ConsentManager(mock_db_manager, mock_audit_service)

    @pytest.mark.asyncio
    async def test_consent_must_be_specific_and_informed(self, consent_manager):
        """GDPR Art 7(1): Consent must be specific and informed"""

        # Given - Vague consent text should be rejected
        vague_consent_text = "I agree to terms"

        # When & Then
        with pytest.raises(ValueError, match="Consent text must be specific"):
            await consent_manager.record_consent("user123", "data_processing", vague_consent_text, {})

    @pytest.mark.asyncio
    async def test_consent_must_be_documented_with_timestamp(self, consent_manager):
        """GDPR Art 7(3): Controller must be able to demonstrate consent"""

        # Given
        consent_result = await consent_manager.record_consent(
            "user123",
            "data_processing",
            "I consent to processing of my personal data for analytics purposes",
            {"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"}
        )

        # Then
        assert consent_result.granted_at is not None
        assert isinstance(consent_result.granted_at, datetime)
        assert consent_result.consent_text is not None
        assert len(consent_result.consent_text) > 0

    @pytest.mark.asyncio
    async def test_right_to_withdraw_consent(self, consent_manager, mock_db_manager):
        """GDPR Art 7(3): Data subject has right to withdraw consent"""

        # Given - Record initial consent
        consent_result = await consent_manager.record_consent(
            "user123",
            "data_processing",
            "I consent to processing of my personal data for analytics purposes",
            {"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"}
        )

        # Mock the database to return the consent when withdrawing
        mock_db_manager.get_active_consent.return_value = consent_result

        # When - Withdraw consent
        withdrawal_result = await consent_manager.withdraw_consent("user123", "data_processing")

        # Then
        assert withdrawal_result is True
        assert consent_result.status == "withdrawn"
        assert consent_result.withdrawn_at is not None

        # Verify consent is no longer valid
        is_valid = await consent_manager.verify_consent("user123", "data_processing")
        assert is_valid is False