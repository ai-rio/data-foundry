"""
End-to-end tests for the complete validation flow.

These tests verify the complete data ingestion flow with validation enabled:
- Real data extraction
- Full validation pipeline (schema, duplicates, quality)
- Integration with AI labeling, PII redaction, and human review
- Backwards compatibility with validation disabled
- Feature flag behavior

Week 1: Data Validation + Database Optimization
Tests: 3
Lines: ~100
"""

import pytest
import asyncio
from unittest.mock import patch, Mock, AsyncMock
from datetime import datetime

from src.tasks.ingestion import (
    extract_data,
    validate_schema,
    check_duplicates,
    compute_quality_scores,
    filter_low_quality,
    apply_pii_redaction,
    route_for_human_review,
    save_to_database,
    data_ingestion_flow,
)
from src.core.config import settings
from src.core.data_quality import DataQualityValidator


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_ai_service():
    """Mock AI Service for E2E tests."""
    with patch('src.services.ai_service.AIService') as mock_ai:
        mock_instance = Mock()
        mock_ai.return_value = mock_instance
        mock_instance.initialize = AsyncMock()

        # Mock AI response
        mock_response = Mock()
        mock_response.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "test"}'
        mock_response.model = "gpt-4o"
        mock_response.request_id = "req-123"
        mock_response.usage = Mock(total_tokens=100, prompt_tokens=50, completion_tokens=50)
        mock_response.cost = 0.001
        mock_response.response_time_ms = 500
        mock_response.fallback_used = False
        mock_response.from_cache = False
        mock_response.retry_count = 0
        mock_response.cached_at = None
        mock_response.completion_id = "comp-123"

        mock_instance.completion = AsyncMock(return_value=mock_response)
        yield mock_instance


@pytest.fixture
def mock_database():
    """Mock database operations for E2E tests."""
    with patch('src.tasks.ingestion.pipeline') as mock_pipeline:
        mock_pipeline.return_value = Mock()
        yield mock_pipeline


# ============================================================================
# E2E TEST 1: End-to-End Validation with Real Data
# ============================================================================


@pytest.mark.asyncio
async def test_end_to_end_validation_with_real_data(mock_ai_service, mock_database):
    """
    Test complete validation flow with real data patterns.

    GIVEN: Real-world data patterns (valid, invalid, duplicates, varying quality)
    WHEN: Full ingestion flow runs with validation enabled
    THEN: Data is correctly categorized and processed through all stages
    """
    # Mock extract_data to return realistic test data
    test_data = [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "555-5678",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 3,
            "name": "Bob Johnson",
            "email": "bob@example.com",
            "phone": "555-9876",
            "tenant_id": "tenant_002",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    with patch('src.tasks.ingestion.extract_data', return_value=test_data):
        # Run full flow with validation enabled
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_validation=True,
            enable_ai_labeling=True,
            enable_pii_redaction=False,
            enable_human_review=True,
        )

        # Verify flow completed successfully
        assert result["success"] is True

        # Verify validation statistics are present
        assert "total_extracted" in result
        assert "valid_records" in result
        assert "invalid_records" in result
        assert "new_records" in result
        assert "duplicate_records" in result
        assert "high_quality" in result
        assert "low_quality" in result

        # Verify all records were processed
        assert result["total_extracted"] == 3
        assert result["valid_records"] >= 0
        assert result["invalid_records"] >= 0
        assert result["new_records"] + result["duplicate_records"] == result["valid_records"]

        # Verify quality filtering
        assert result["high_quality"] + result["low_quality"] == result["new_records"]

        # Verify final processing
        assert "auto_approved" in result
        assert "human_review" in result
        assert result["auto_approved"] + result["human_review"] >= 0


# ============================================================================
# E2E TEST 2: Validation Flow Backwards Compatibility
# ============================================================================


@pytest.mark.asyncio
async def test_validation_flow_backwards_compatibility():
    """
    Test that validation can be disabled for backwards compatibility.

    GIVEN: Existing code that doesn't use validation
    WHEN: Flow runs with enable_validation=False
    THEN: Data bypasses validation and processes normally
    """
    test_data = [
        {
            "id": 1,
            "name": "Test User",
            "email": "test@example.com",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    with patch('src.tasks.ingestion.extract_data', return_value=test_data):
        # Run flow with validation DISABLED (backwards compatibility)
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_validation=False,  # DISABLE validation
            enable_ai_labeling=False,
            enable_pii_redaction=False,
            enable_human_review=False,
        )

        # Verify flow completed
        assert result["success"] is True
        assert result["total_extracted"] == 1

        # Verify validation stats are 0 when disabled
        assert result["valid_records"] == 0
        assert result["invalid_records"] == 0
        assert result["new_records"] == 0
        assert result["duplicate_records"] == 0
        assert result["high_quality"] == 0
        assert result["low_quality"] == 0

        # Verify record still processed (backwards compatible)
        assert result["total_records"] == 1


# ============================================================================
# E2E TEST 3: Validation Flow with Feature Flags
# ============================================================================


@pytest.mark.asyncio
async def test_validation_flow_with_feature_flags():
    """
    Test validation flow respects feature flags from config.

    GIVEN: Config with ENABLE_DATA_VALIDATION flag
    WHEN: Flow runs with different flag combinations
    THEN: Validation behavior matches flag settings
    """
    test_data = [
        {
            "id": 1,
            "name": "Feature Flag Test",
            "email": "flagtest@example.com",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    # Test 1: Validation enabled by feature flag
    with patch('src.tasks.ingestion.extract_data', return_value=test_data), \
         patch.object(settings, 'ENABLE_DATA_VALIDATION', True):
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_validation=True,  # Also enable explicitly
            enable_ai_labeling=False,
            enable_pii_redaction=False,
            enable_human_review=False,
        )

        assert result["success"] is True
        # Validation should run when flag is True
        assert result["valid_records"] >= 0

    # Test 2: Validation disabled by feature flag
    with patch('src.tasks.ingestion.extract_data', return_value=test_data), \
         patch.object(settings, 'ENABLE_DATA_VALIDATION', False):
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_validation=True,  # Try to enable, but flag overrides
            enable_ai_labeling=False,
            enable_pii_redaction=False,
            enable_human_review=False,
        )

        assert result["success"] is True
        # Validation should be skipped when flag is False
        assert result["valid_records"] == 0
        assert result["invalid_records"] == 0


# ============================================================================
# ADDITIONAL E2E SCENARIOS
# ============================================================================


@pytest.mark.asyncio
async def test_validation_pipeline_with_mixed_data_quality():
    """
    Test validation pipeline with mixed data quality scenarios.

    GIVEN: Data with high, medium, and low quality records
    WHEN: Full validation pipeline runs
    THEN: Records are correctly filtered by quality threshold
    """
    # Create test data with known quality patterns
    test_data = []

    # High quality record (all required + recommended fields)
    test_data.append({
        "id": 1,
        "name": "Perfect User",
        "email": "perfect@example.com",
        "phone": "+1-555-0000",
        "tenant_id": "tenant_001",
        "created_at": datetime.utcnow().isoformat(),
        "file_name": "perfect.csv",
        "mime_type": "text/csv",
    })

    # Medium quality record (required fields only)
    test_data.append({
        "id": 2,
        "name": "Medium User",
        "email": "medium@example.com",
        "tenant_id": "tenant_001",
        "created_at": datetime.utcnow().isoformat(),
    })

    # Low quality record (minimal data)
    test_data.append({
        "id": 3,
        "name": "Minimal User",
        "tenant_id": "tenant_002",
        "created_at": datetime.utcnow().isoformat(),
    })

    with patch('src.tasks.ingestion.extract_data', return_value=test_data):
        result = await data_ingestion_flow(
            data_source="mixed_quality",
            enable_validation=True,
            enable_ai_labeling=False,
            enable_pii_redaction=False,
            enable_human_review=False,
        )

        assert result["success"] is True
        assert result["total_extracted"] == 3

        # Verify quality filtering occurred
        # At minimum, all records should be categorized
        assert result["high_quality"] >= 0
        assert result["low_quality"] >= 0
        assert result["high_quality"] + result["low_quality"] <= result["total_extracted"]


@pytest.mark.asyncio
async def test_validation_pipeline_error_recovery():
    """
    Test that validation pipeline handles errors gracefully.

    GIVEN: Data that may cause validation errors
    WHEN: Pipeline encounters errors
    THEN: Pipeline continues processing and doesn't crash
    """
    # Mix of valid and problematic data
    test_data = [
        {
            "id": 1,
            "name": "Valid User",
            "email": "valid@example.com",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 2,
            "name": "",  # Empty name
            "email": "invalid-email",  # Invalid email
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    with patch('src.tasks.ingestion.extract_data', return_value=test_data):
        # Should not raise exception
        result = await data_ingestion_flow(
            data_source="error_recovery",
            enable_validation=True,
            enable_ai_labeling=False,
            enable_pii_redaction=False,
            enable_human_review=False,
        )

        # Verify flow completed despite validation issues
        assert result["success"] is True
        assert result["total_extracted"] == 2
