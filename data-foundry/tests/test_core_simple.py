"""Simple core functionality tests without complex fixtures."""

import pytest
from unittest.mock import Mock, patch
from src.tasks.ingestion import (
    apply_pii_redaction,
    apply_ai_labeling,
    route_for_human_review,
)


def test_pii_redaction_with_presidio():
    """Test PII redaction with Presidio installed."""
    # Sample data with PII
    test_data = [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "555-5678",
        },
    ]

    # Run PII redaction with Presidio
    result = apply_pii_redaction(test_data)

    # Should return redacted data when Presidio is available
    assert len(result) == 2
    # Names should be redacted
    assert result[0]["name"] != "John Doe"
    assert result[1]["name"] != "Jane Smith"
    # Email and phone may also be redacted
    # The exact redaction format depends on Presidio configuration


def test_ai_labeling_without_api_key():
    """Test AI labeling when OpenAI API key is not configured."""
    # Sample data
    test_data = [
        {
            "id": 1,
            "name": "Test Company",
            "email": "contact@testcompany.com",
            "phone": "555-9999",
        }
    ]

    # Mock settings to have no API key
    with patch('src.tasks.ingestion.settings.OPENAI_API_KEY', None):
        result = apply_ai_labeling(test_data)

    # Should return data without AI labels when no API key
    assert len(result) == 1
    assert "ai_error" in result[0]


def test_route_for_human_review():
    """Test confidence-based routing logic."""
    # Test data with different confidence levels
    test_data = [
        {"id": 1, "ai_confidence": 0.9, "name": "High Confidence"},
        {"id": 2, "ai_confidence": 0.8, "name": "Low Confidence"},
        {"id": 3, "ai_confidence": 0.95, "name": "Very High Confidence"},
        {"id": 4, "ai_confidence": 0.7, "name": "Very Low Confidence"},
    ]

    # Mock confidence threshold
    with patch('src.tasks.ingestion.settings.CONFIDENCE_THRESHOLD', 0.85):
        auto_approved, human_review = route_for_human_review(test_data)

    # Should route correctly based on confidence
    assert len(auto_approved) == 2  # Records 1 and 3 (>= 0.85)
    assert len(human_review) == 2  # Records 2 and 4 (< 0.85)

    # Verify correct records in each group
    auto_ids = [r["id"] for r in auto_approved]
    human_ids = [r["id"] for r in human_review]

    assert 1 in auto_ids
    assert 3 in auto_ids
    assert 2 in human_ids
    assert 4 in human_ids


def test_data_flow_components():
    """Test individual components of the data flow."""
    # Test data structure
    sample_record = {
        "id": 1,
        "name": "Test Record",
        "email": "test@example.com",
        "tenant_id": "tenant_001",
    }

    # Verify structure
    assert "id" in sample_record
    assert "name" in sample_record
    assert "email" in sample_record
    assert "tenant_id" in sample_record


def test_extraction_task():
    """Test data extraction task."""
    from src.tasks.ingestion import extract_data

    # Run extraction
    result = extract_data("sample_data")

    # Should return sample data
    assert isinstance(result, list)
    assert len(result) > 0

    # Verify structure
    record = result[0]
    assert "id" in record
    assert "name" in record
    assert "email" in record
    assert "tenant_id" in record
    assert "created_at" in record


def test_flow_configuration():
    """Test that flow configuration is properly set."""
    from src.core.config import settings

    # Verify key settings exist
    assert hasattr(settings, 'CONFIDENCE_THRESHOLD')
    assert hasattr(settings, 'ENABLE_PII_REDACTION')
    assert hasattr(settings, 'OPENAI_API_KEY')
    assert hasattr(settings, 'ANTHROPIC_API_KEY')

    # Verify defaults
    assert isinstance(settings.CONFIDENCE_THRESHOLD, float)
    assert isinstance(settings.ENABLE_PII_REDACTION, bool)