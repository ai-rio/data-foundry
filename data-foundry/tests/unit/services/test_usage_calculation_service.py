"""
Tests for UsageCalculationService - P02-005: Integration with ingestion pipeline

This test module covers:
- Usage calculation from AI labeling results (confidence threshold-based)
- Tenant isolation enforcement (no cross-tenant data leakage)
- Input validation for confidence scores
- Edge cases (null values, no confidence, negative values)
- Batch aggregation by tenant
- Security requirements for 95% security score
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock

from src.services.usage_calculation_service import (
    UsageCalculationService,
    UsageCalculationError,
    UsageValidationError
)
from src.services.stripe_service import StripeService


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def usage_service():
    """Create a UsageCalculationService instance for testing."""
    return UsageCalculationService()


@pytest.fixture
def sample_records():
    """Sample records for testing usage calculation."""
    return [
        {
            "id": 1,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.90,
            "ai_category": "high_value",
            "processed_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": 2,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.75,
            "ai_category": "medium_value",
            "processed_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": 3,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.95,
            "ai_category": "high_value",
            "processed_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": 4,
            "tenant_id": "tenant_002",
            "ai_confidence": 0.85,
            "ai_category": "medium_value",
            "processed_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": 5,
            "tenant_id": "tenant_002",
            "ai_confidence": 0.70,
            "ai_category": "low_value",
            "processed_at": datetime.now(timezone.utc).isoformat()
        },
    ]


@pytest.fixture
def sample_human_review_records():
    """Sample human review records for testing."""
    return [
        {
            "id": 10,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.70,
            "human_reviewed": True,
            "reviewed_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": 11,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.60,
            "human_reviewed": True,
            "reviewed_at": datetime.now(timezone.utc).isoformat()
        },
    ]


# ============================================================================
# Usage Calculation Tests (TDD - Red-Green-Refactor)
# ============================================================================

class TestUsageCalculation:
    """Test suite for usage calculation functionality."""

    def test_calculate_usage_from_records_basic(self, usage_service, sample_records):
        """
        Test basic usage calculation from records.

        Given: A list of records with confidence scores
        When: Calculating usage with default threshold (0.85)
        Then: AI_LABELS and HUMAN_AUDITS are calculated correctly
        """
        # Arrange & Act
        result = usage_service.calculate_usage_from_records(
            records=sample_records,
            confidence_threshold=0.85
        )

        # Assert - TDD verification
        assert "tenant_001" in result
        assert "tenant_002" in result

        # tenant_001: 2 records >= 0.85 (id 1, 3), 1 record < 0.85 (id 2)
        assert result["tenant_001"]["ai_labels"] == 2
        assert result["tenant_001"]["human_audits"] == 1

        # tenant_002: 1 record >= 0.85 (id 4), 1 record < 0.85 (id 5)
        assert result["tenant_002"]["ai_labels"] == 1
        assert result["tenant_002"]["human_audits"] == 1

    def test_calculate_usage_with_custom_threshold(self, usage_service, sample_records):
        """
        Test usage calculation with custom confidence threshold.

        Given: A list of records with confidence scores
        When: Calculating usage with threshold=0.90
        Then: Classification uses the custom threshold
        """
        result = usage_service.calculate_usage_from_records(
            records=sample_records,
            confidence_threshold=0.90
        )

        # tenant_001: 2 records >= 0.90 (id 1 with 0.90, id 3 with 0.95), 1 record < 0.90 (id 2)
        assert result["tenant_001"]["ai_labels"] == 2
        assert result["tenant_001"]["human_audits"] == 1

        # tenant_002: 0 records >= 0.90, 2 records < 0.90
        assert result["tenant_002"]["ai_labels"] == 0
        assert result["tenant_002"]["human_audits"] == 2

    def test_calculate_usage_empty_records(self, usage_service):
        """
        Test usage calculation with empty record list.

        Given: An empty list of records
        When: Calculating usage
        Then: Returns empty dict (no tenants)
        """
        result = usage_service.calculate_usage_from_records(
            records=[],
            confidence_threshold=0.85
        )

        assert result == {}

    def test_calculate_usage_missing_confidence(self, usage_service):
        """
        Test usage calculation with missing confidence scores.

        Given: Records without ai_confidence field
        When: Calculating usage
        Then: Treats as human audit (conservative approach)
        """
        records = [
            {"id": 1, "tenant_id": "tenant_001"},
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": None},
            {"id": 3, "tenant_id": "tenant_001", "ai_confidence": 0.90},
        ]

        result = usage_service.calculate_usage_from_records(
            records=records,
            confidence_threshold=0.85
        )

        # Only id 3 has confidence >= 0.85
        assert result["tenant_001"]["ai_labels"] == 1
        # id 1 and 2 treated as human audits
        assert result["tenant_001"]["human_audits"] == 2

    def test_calculate_usage_invalid_confidence_types(self, usage_service):
        """
        Test usage calculation with invalid confidence score types.

        Given: Records with non-numeric confidence scores
        When: Calculating usage
        Then: Treats invalid types as human audits (conservative approach)
        """
        records = [
            {"id": 1, "tenant_id": "tenant_001", "ai_confidence": "high"},
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": []},
            {"id": 3, "tenant_id": "tenant_001", "ai_confidence": 0.90},
        ]

        result = usage_service.calculate_usage_from_records(records, 0.85)

        # Invalid types treated as human audits
        assert result["tenant_001"]["ai_labels"] == 1  # Only id 3
        assert result["tenant_001"]["human_audits"] == 2  # id 1, 2

    def test_calculate_usage_negative_confidence(self, usage_service):
        """
        Test usage calculation with negative confidence scores.

        Given: Records with negative confidence scores
        When: Calculating usage
        Then: Treats as human audit (value out of range)
        """
        records = [
            {"id": 1, "tenant_id": "tenant_001", "ai_confidence": -0.5},
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": 0.90},
        ]

        result = usage_service.calculate_usage_from_records(
            records=records,
            confidence_threshold=0.85
        )

        # Negative treated as human audit
        assert result["tenant_001"]["ai_labels"] == 1
        assert result["tenant_001"]["human_audits"] == 1

    def test_calculate_usage_confidence_above_one(self, usage_service):
        """
        Test usage calculation with confidence > 1.0.

        Given: Records with confidence scores > 1.0
        When: Calculating usage
        Then: Treats as human audit (value out of range)
        """
        records = [
            {"id": 1, "tenant_id": "tenant_001", "ai_confidence": 1.5},
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": 0.90},
        ]

        result = usage_service.calculate_usage_from_records(
            records=records,
            confidence_threshold=0.85
        )

        # 1.5 treated as human audit (out of range)
        assert result["tenant_001"]["ai_labels"] == 1
        assert result["tenant_001"]["human_audits"] == 1


# ============================================================================
# Tenant Isolation Tests (Security - 95% score requirement)
# ============================================================================

class TestTenantIsolation:
    """Test suite for tenant isolation enforcement."""

    def test_tenant_isolation_enforcement(self, usage_service, sample_records):
        """
        Test that tenant isolation is enforced.

        Given: Records from multiple tenants
        When: Calculating usage
        Then: Each tenant's usage is calculated separately
        """
        result = usage_service.calculate_usage_from_records(
            records=sample_records,
            confidence_threshold=0.85
        )

        # Verify tenant isolation
        assert len(result) == 2  # tenant_001 and tenant_002
        assert result["tenant_001"]["ai_labels"] == 2
        assert result["tenant_002"]["ai_labels"] == 1

        # No cross-tenant data leakage
        tenant_001_total = result["tenant_001"]["ai_labels"] + result["tenant_001"]["human_audits"]
        tenant_002_total = result["tenant_002"]["ai_labels"] + result["tenant_002"]["human_audits"]

        assert tenant_001_total == 3  # All tenant_001 records
        assert tenant_002_total == 2  # All tenant_002 records

    def test_missing_tenant_id_raises_error(self, usage_service):
        """
        Test that missing tenant_id raises error.

        Given: Records without tenant_id
        When: Calculating usage
        Then: Raises UsageValidationError
        """
        records = [
            {"id": 1, "ai_confidence": 0.90},  # Missing tenant_id
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": 0.85},
        ]

        with pytest.raises(UsageValidationError) as exc_info:
            usage_service.calculate_usage_from_records(records, 0.85)

        assert "tenant_id" in str(exc_info.value).lower()

    def test_tenant_aggregation_for_batch_reporting(self, usage_service):
        """
        Test that usage is aggregated per tenant for batch reporting.

        Given: Records from multiple tenants with varying confidence
        When: Calculating usage for batch reporting
        Then: Returns aggregation per tenant
        """
        records = [
            {"id": 1, "tenant_id": "tenant_001", "ai_confidence": 0.90},
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": 0.95},
            {"id": 3, "tenant_id": "tenant_001", "ai_confidence": 0.70},
            {"id": 4, "tenant_id": "tenant_002", "ai_confidence": 0.85},
            {"id": 5, "tenant_id": "tenant_002", "ai_confidence": 0.60},
        ]

        result = usage_service.calculate_usage_for_batch_reporting(
            records=records,
            confidence_threshold=0.85
        )

        # Verify batch aggregation format
        assert "aggregations" in result
        assert len(result["aggregations"]) == 2

        # Check tenant_001 aggregation
        tenant_001_agg = next(a for a in result["aggregations"] if a["tenant_id"] == "tenant_001")
        assert tenant_001_agg["ai_labels_count"] == 2
        assert tenant_001_agg["human_audits_count"] == 1
        assert "meter_events" in tenant_001_agg

        # Check tenant_002 aggregation
        tenant_002_agg = next(a for a in result["aggregations"] if a["tenant_id"] == "tenant_002")
        assert tenant_002_agg["ai_labels_count"] == 1
        assert tenant_002_agg["human_audits_count"] == 1


# ============================================================================
# Batch Preparation Tests
# ============================================================================

class TestBatchPreparation:
    """Test suite for batch preparation functionality."""

    def test_prepare_meter_events_batch(self, usage_service, sample_records):
        """
        Test preparing meter events for batch reporting.

        Given: Usage calculation results
        When: Preparing meter events batch
        Then: Returns properly formatted batch events
        """
        usage_result = usage_service.calculate_usage_from_records(
            records=sample_records,
            confidence_threshold=0.85
        )

        batch_events = usage_service.prepare_meter_events_batch(
            usage_calculation=usage_result,
            batch_id="batch_001"
        )

        # Verify batch structure
        assert "batch_id" in batch_events
        assert batch_events["batch_id"] == "batch_001"
        assert "events" in batch_events

        # Should have 4 events (2 per tenant)
        assert len(batch_events["events"]) == 4

        # Verify event structure
        first_event = batch_events["events"][0]
        assert "meter_event" in first_event
        assert "value" in first_event
        assert "tenant_id" in first_event
        assert "metadata" in first_event

    def test_prepare_batch_with_zero_values(self, usage_service):
        """
        Test preparing batch with zero usage values.

        Given: Usage calculation with zero values for some tenants
        When: Preparing meter events batch
        Then: Zero-value events are filtered out
        """
        usage_result = {
            "tenant_001": {"ai_labels": 0, "human_audits": 5},
            "tenant_002": {"ai_labels": 3, "human_audits": 0},
        }

        batch_events = usage_service.prepare_meter_events_batch(
            usage_calculation=usage_result,
            batch_id="batch_002"
        )

        # Only non-zero events should be included
        assert len(batch_events["events"]) == 2
        assert all(e["value"] > 0 for e in batch_events["events"])

    def test_prepare_batch_metadata(self, usage_service, sample_records):
        """
        Test that batch events include proper metadata.

        Given: Usage calculation results
        When: Preparing meter events batch
        Then: Events include audit trail metadata
        """
        usage_result = usage_service.calculate_usage_from_records(
            records=sample_records,
            confidence_threshold=0.85
        )

        batch_events = usage_service.prepare_meter_events_batch(
            usage_calculation=usage_result,
            batch_id="batch_003",
            source="ingestion_pipeline"
        )

        # Verify metadata
        for event in batch_events["events"]:
            assert "metadata" in event
            assert event["metadata"]["source"] == "ingestion_pipeline"
            assert event["metadata"]["batch_id"] == "batch_003"
            assert "calculated_at" in event["metadata"]


# ============================================================================
# Input Validation Tests
# ============================================================================

class TestInputValidation:
    """Test suite for input validation."""

    def test_validate_confidence_threshold_bounds(self, usage_service):
        """
        Test confidence threshold validation.

        Given: Invalid confidence threshold values
        When: Calculating usage
        Then: Raises UsageValidationError
        """
        # Test threshold < 0
        with pytest.raises(UsageValidationError):
            usage_service.calculate_usage_from_records(
                records=[{"id": 1, "tenant_id": "t1", "ai_confidence": 0.5}],
                confidence_threshold=-0.1
            )

        # Test threshold > 1
        with pytest.raises(UsageValidationError):
            usage_service.calculate_usage_from_records(
                records=[{"id": 1, "tenant_id": "t1", "ai_confidence": 0.5}],
                confidence_threshold=1.1
            )

    def test_validate_records_input_type(self, usage_service):
        """
        Test that records input must be a list.

        Given: Non-list input for records
        When: Calculating usage
        Then: Raises UsageValidationError
        """
        with pytest.raises(UsageValidationError):
            usage_service.calculate_usage_from_records(
                records=None,  # Not a list
                confidence_threshold=0.85
            )

        with pytest.raises(UsageValidationError):
            usage_service.calculate_usage_from_records(
                records="not_a_list",
                confidence_threshold=0.85
            )


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestEdgeCases:
    """Test suite for edge cases."""

    def test_all_records_same_tenant(self, usage_service):
        """
        Test when all records are from the same tenant.

        Given: All records from a single tenant
        When: Calculating usage
        Then: Returns single tenant aggregation
        """
        records = [
            {"id": i, "tenant_id": "tenant_001", "ai_confidence": 0.8 + i * 0.02}
            for i in range(1, 6)
        ]

        result = usage_service.calculate_usage_from_records(records, 0.85)

        assert len(result) == 1
        assert "tenant_001" in result
        assert result["tenant_001"]["ai_labels"] + result["tenant_001"]["human_audits"] == 5

    def test_mixed_confidence_at_threshold(self, usage_service):
        """
        Test records with confidence exactly at threshold.

        Given: Records with confidence == threshold
        When: Calculating usage
        Then: Treated as AI_LABELS (>= threshold)
        """
        records = [
            {"id": 1, "tenant_id": "tenant_001", "ai_confidence": 0.85},
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": 0.84},
        ]

        result = usage_service.calculate_usage_from_records(records, 0.85)

        # 0.85 is >= threshold, so AI_LABELS
        assert result["tenant_001"]["ai_labels"] == 1
        assert result["tenant_001"]["human_audits"] == 1

    def test_large_batch_performance(self, usage_service):
        """
        Test performance with large record batches.

        Given: A large batch of records (1000+)
        When: Calculating usage
        Then: Completes within reasonable time
        """
        import time

        records = [
            {
                "id": i,
                "tenant_id": f"tenant_{i % 10}",  # 10 tenants
                "ai_confidence": 0.5 + (i % 50) / 100.0
            }
            for i in range(1000)
        ]

        start = time.time()
        result = usage_service.calculate_usage_from_records(records, 0.85)
        elapsed = time.time() - start

        # Should complete quickly (< 1 second for 1000 records)
        assert elapsed < 1.0
        assert len(result) == 10  # 10 tenants
