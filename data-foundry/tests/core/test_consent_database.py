"""
Test-Driven Development for Consent Database Models

This test file defines the expected behavior of the consent database models
before implementation begins, following TDD principles.

Tests are written first, then implementation follows to make them pass.
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, String, DateTime, Text, JSON, Index
from sqlmodel import SQLModel, Field, Session, select
from typing import Optional, Dict, Any

# Import the models we will create
from src.models.consent import ConsentRecordDB


class TestConsentRecordDB:
    """Test the ConsentRecord SQLModel"""

    def test_consent_model_creation(self):
        """Test creating consent record with all fields"""
        # Given
        consent_data = {
            "user_id": "user123",
            "consent_type": "data_processing",
            "consent_text": "I consent to processing of my personal data for analytics purposes",
            "granted_at": datetime.now(timezone.utc),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "status": "active",
            "consent_metadata": {"source": "web_form", "version": "1.0"}
        }

        # When
        record = ConsentRecordDB(**consent_data)

        # Then
        assert record.user_id == consent_data["user_id"]
        assert record.consent_type == consent_data["consent_type"]
        assert record.consent_text == consent_data["consent_text"]
        assert record.granted_at == consent_data["granted_at"]
        assert record.ip_address == consent_data["ip_address"]
        assert record.user_agent == consent_data["user_agent"]
        assert record.status == consent_data["status"]
        assert record.consent_metadata == consent_data["consent_metadata"]
        assert record.withdrawn_at is None
        assert record.id is None  # Not persisted yet

    def test_consent_model_defaults(self):
        """Test creating consent record with required fields only"""
        # Given
        consent_data = {
            "user_id": "user123",
            "consent_type": "data_processing",
            "consent_text": "I consent to processing of my personal data for analytics purposes",
            "granted_at": datetime.now(timezone.utc),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }

        # When
        record = ConsentRecordDB(**consent_data)

        # Then
        assert record.user_id == consent_data["user_id"]
        assert record.consent_type == consent_data["consent_type"]
        assert record.consent_text == consent_data["consent_text"]
        assert record.granted_at == consent_data["granted_at"]
        assert record.ip_address == consent_data["ip_address"]
        assert record.user_agent == consent_data["user_agent"]
        assert record.status == "active"  # Default value
        assert record.consent_metadata == {}  # Default value
        assert record.withdrawn_at is None  # Default value

    def test_consent_model_basic_properties(self):
        """Test basic model properties and field accessibility"""
        # Given
        consent_data = {
            "user_id": "user123",
            "consent_type": "data_processing",
            "consent_text": "I consent to processing of my personal data for analytics purposes",
            "granted_at": datetime.now(timezone.utc),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }

        # When
        record = ConsentRecordDB(**consent_data)

        # Then - Test basic properties
        assert hasattr(record, 'id')  # Primary key
        assert hasattr(record, 'user_id')
        assert hasattr(record, 'consent_type')
        assert hasattr(record, 'consent_text')
        assert hasattr(record, 'granted_at')
        assert hasattr(record, 'ip_address')
        assert hasattr(record, 'user_agent')
        assert hasattr(record, 'status')
        assert hasattr(record, 'withdrawn_at')
        assert hasattr(record, 'consent_metadata')
        assert hasattr(record, 'created_at')
        assert hasattr(record, 'updated_at')

        # Test field types
        assert isinstance(record.user_id, str)
        assert isinstance(record.consent_type, str)
        assert isinstance(record.consent_text, str)
        assert isinstance(record.granted_at, datetime)
        assert isinstance(record.ip_address, str)
        assert isinstance(record.user_agent, str)
        assert isinstance(record.status, str)
        assert isinstance(record.consent_metadata, dict)

    def test_consent_model_withdrawal(self):
        """Test withdrawing consent"""
        # Given
        consent_data = {
            "user_id": "user123",
            "consent_type": "data_processing",
            "consent_text": "I consent to processing of my personal data for analytics purposes",
            "granted_at": datetime.now(timezone.utc) - timedelta(days=1),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }
        record = ConsentRecordDB(**consent_data)

        # When
        record.withdraw()

        # Then
        assert record.status == "withdrawn"
        assert record.withdrawn_at is not None
        assert record.withdrawn_at > record.granted_at

    def test_consent_model_is_active(self):
        """Test is_active method"""
        # Given
        consent_data = {
            "user_id": "user123",
            "consent_type": "data_processing",
            "consent_text": "I consent to processing of my personal data for analytics purposes",
            "granted_at": datetime.now(timezone.utc),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }
        record = ConsentRecordDB(**consent_data)

        # Then
        assert record.is_active() is True

        # When
        record.withdraw()

        # Then
        assert record.is_active() is False

    def test_consent_model_table_name(self):
        """Test that table name is correctly set"""
        # Then
        assert ConsentRecordDB.__tablename__ == "consent_records"

    def test_consent_model_indexes(self):
        """Test that necessary indexes are defined"""
        # Check if indexes are properly defined for common queries
        # This would typically be checked via SQLAlchemy inspection
        table = ConsentRecordDB.__table__

        # Check for user_id index (for user consent lookups)
        user_index = None
        for index in table.indexes:
            if "user_id" in str(index.columns):
                user_index = index
                break
        assert user_index is not None, "Missing index on user_id column"

        # Check for consent_type index (for type-based queries)
        type_index = None
        for index in table.indexes:
            if "consent_type" in str(index.columns):
                type_index = index
                break
        assert type_index is not None, "Missing index on consent_type column"

    def test_consent_model_columns(self):
        """Test that all required columns are defined"""
        table = ConsentRecordDB.__table__

        # Check primary key
        assert table.primary_key.columns.keys() == ["id"]

        # Check required columns exist
        expected_columns = [
            "id", "user_id", "consent_type", "consent_text",
            "granted_at", "ip_address", "user_agent", "status",
            "withdrawn_at", "consent_metadata", "created_at", "updated_at"
        ]

        actual_columns = list(table.columns.keys())
        for col in expected_columns:
            assert col in actual_columns, f"Missing column: {col}"

    def test_consent_model_json_metadata(self):
        """Test that metadata column supports JSON"""
        # Given
        complex_metadata = {
            "source": "mobile_app",
            "version": "2.1.0",
            "preferences": {
                "marketing_emails": True,
                "analytics": False,
                "personalization": True
            },
            "consent_flow": [
                "page1",
                "page2",
                "confirmation"
            ]
        }

        consent_data = {
            "user_id": "user123",
            "consent_type": "data_processing",
            "consent_text": "I consent to processing of my personal data for analytics purposes",
            "granted_at": datetime.now(timezone.utc),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "consent_metadata": complex_metadata
        }

        # When
        record = ConsentRecordDB(**consent_data)

        # Then
        assert record.consent_metadata == complex_metadata
        assert record.consent_metadata["preferences"]["marketing_emails"] is True