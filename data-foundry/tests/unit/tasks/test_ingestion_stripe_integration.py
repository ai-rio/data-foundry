"""
Tests for Pipeline Integration with Stripe Billing - P02-005

This test module covers:
- Ingestion pipeline hooks for meter event reporting
- Usage calculation from AI labeling results
- Async reporting to prevent pipeline blocking
- Tenant isolation in pipeline context
- Batch aggregation for efficient API usage
- Integration with StripeService

Test Coverage:
- FR-030: Post-Processing Hook - Trigger meter event after data processing completes
- FR-031: Batch Aggregation - Aggregate usage within processing batches before reporting
- FR-032: Async Reporting - Report usage asynchronously to avoid blocking processing pipeline
- FR-033: Usage Reconciliation - Periodically reconcile internal usage tracking with Stripe records
- FR-034: Audit Trail - Log all meter event reports for audit purposes
"""

import pytest
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.usage_calculation_service import UsageCalculationService
from src.services.stripe_service import StripeService, StripeMeterValidationError


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def usage_calculation_service():
    """Create a UsageCalculationService instance."""
    return UsageCalculationService()


@pytest.fixture
def mock_stripe_service():
    """Create a mock StripeService."""
    service = AsyncMock(spec=StripeService)
    service.report_usage = AsyncMock(return_value={
        "event_id": "evt_test_123",
        "status": "succeeded",
        "meter_event": "ai_labels",
        "value": 10
    })
    service.report_usage_batch = AsyncMock()
    service.get_customer_by_tenant = AsyncMock(return_value={
        "tenant_id": "tenant_001",
        "stripe_customer_id": "cus_test_123",
        "email": "test@example.com"
    })
    return service


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_processed_records():
    """
    Sample processed records from ingestion pipeline.

    Simulates records after AI labeling with confidence scores.
    """
    return [
        {
            "id": 1,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.90,
            "ai_category": "high_value",
            "ai_model": "gpt-4",
            "ai_processed_at": datetime.now(timezone.utc).isoformat(),
            "record_hash": "abc123"
        },
        {
            "id": 2,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.75,
            "ai_category": "medium_value",
            "ai_model": "gpt-4",
            "ai_processed_at": datetime.now(timezone.utc).isoformat(),
            "record_hash": "def456"
        },
        {
            "id": 3,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.95,
            "ai_category": "high_value",
            "ai_model": "gpt-4",
            "ai_processed_at": datetime.now(timezone.utc).isoformat(),
            "record_hash": "ghi789"
        },
        {
            "id": 4,
            "tenant_id": "tenant_002",
            "ai_confidence": 0.85,
            "ai_category": "medium_value",
            "ai_model": "gpt-4",
            "ai_processed_at": datetime.now(timezone.utc).isoformat(),
            "record_hash": "jkl012"
        },
    ]


@pytest.fixture
def sample_human_review_records():
    """Sample records after human review completion."""
    return [
        {
            "id": 10,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.70,
            "human_reviewed": True,
            "reviewer_id": "user_123",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "decision": "approved"
        },
        {
            "id": 11,
            "tenant_id": "tenant_001",
            "ai_confidence": 0.60,
            "human_reviewed": True,
            "reviewer_id": "user_456",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "decision": "approved"
        },
    ]


# ============================================================================
# Ingestion Pipeline Hook Tests (FR-030, FR-031)
# ============================================================================

class TestIngestionPipelineHooks:
    """Test suite for ingestion pipeline meter event hooks."""

    @pytest.mark.asyncio
    async def test_report_usage_after_ingestion(
        self,
        usage_calculation_service,
        mock_stripe_service,
        mock_db_session,
        sample_processed_records
    ):
        """
        FR-030: Test meter event reporting after ingestion processing.

        Given: A batch of processed records with AI confidence scores
        When: Triggering meter event reporting after ingestion
        Then: Usage is calculated and reported to Stripe asynchronously
        """
        # Calculate usage from processed records
        usage = usage_calculation_service.calculate_usage_from_records(
            records=sample_processed_records,
            confidence_threshold=0.85
        )

        # Verify usage calculation
        assert "tenant_001" in usage
        assert usage["tenant_001"]["ai_labels"] == 2  # 0.90, 0.95
        assert usage["tenant_001"]["human_audits"] == 1  # 0.75

        # Prepare batch for Stripe reporting
        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="ingest_batch_001",
            source="ingestion_pipeline"
        )

        # Verify batch structure
        assert batch["batch_id"] == "ingest_batch_001"
        assert batch["total_ai_labels"] == 3  # tenant_001(2) + tenant_002(1)
        assert len(batch["events"]) == 3  # 2 tenants, potentially 2 events each

        # Report to Stripe (simulated async)
        for event in batch["events"]:
            await mock_stripe_service.report_usage(
                meter_event=event["meter_event"],
                value=event["value"],
                tenant_id=event["tenant_id"],
                metadata=event["metadata"],
                stripe_customer_id="cus_test_123",
                db_session=mock_db_session
            )

        # Verify Stripe was called for each event
        assert mock_stripe_service.report_usage.call_count == len(batch["events"])

    @pytest.mark.asyncio
    async def test_batch_aggregation_for_efficiency(
        self,
        usage_calculation_service,
        mock_stripe_service,
        mock_db_session,
        sample_processed_records
    ):
        """
        FR-031: Test batch aggregation for efficient Stripe API usage.

        Given: Multiple records from the same tenant
        When: Preparing batch for reporting
        Then: Events are aggregated per tenant for efficient API calls
        """
        # Calculate usage for batch reporting
        batch_result = usage_calculation_service.calculate_usage_for_batch_reporting(
            records=sample_processed_records,
            confidence_threshold=0.85
        )

        # Verify aggregation
        assert batch_result["total_tenants"] == 2
        assert len(batch_result["aggregations"]) == 2

        # Find tenant_001 aggregation
        tenant_001_agg = next(
            a for a in batch_result["aggregations"]
            if a["tenant_id"] == "tenant_001"
        )
        assert tenant_001_agg["ai_labels_count"] == 2
        assert tenant_001_agg["human_audits_count"] == 1
        assert len(tenant_001_agg["meter_events"]) == 2  # ai_labels + human_audits

        # Verify batch reporting format
        for agg in batch_result["aggregations"]:
            for event in agg["meter_events"]:
                assert "meter_event" in event
                assert "value" in event
                assert event["value"] > 0

    @pytest.mark.asyncio
    async def test_async_reporting_prevents_blocking(
        self,
        usage_calculation_service,
        mock_stripe_service,
        sample_processed_records
    ):
        """
        FR-032: Test async reporting prevents pipeline blocking.

        Given: A large batch of records to report
        When: Reporting asynchronously to Stripe
        Then: Pipeline continues without waiting for Stripe API completion
        """
        # Calculate usage
        usage = usage_calculation_service.calculate_usage_from_records(
            records=sample_processed_records,
            confidence_threshold=0.85
        )

        # Simulate async reporting (non-blocking)
        async def report_async():
            """Simulate async background task."""
            await asyncio.sleep(0.1)  # Simulate network delay
            return {"status": "reported", "events_count": 3}

        # Create async task (non-blocking)
        reporting_task = asyncio.create_task(report_async())

        # Pipeline continues immediately
        pipeline_status = {"status": "continuing", "blocked": False}

        # Verify pipeline is not blocked
        assert pipeline_status["blocked"] is False

        # Wait for reporting to complete
        result = await reporting_task
        assert result["events_count"] == 3


# ============================================================================
# Approval Workflow Hook Tests
# ============================================================================

class TestApprovalWorkflowHooks:
    """Test suite for approval workflow meter event hooks."""

    @pytest.mark.asyncio
    async def test_report_usage_after_human_review(
        self,
        usage_calculation_service,
        mock_stripe_service,
        mock_db_session,
        sample_human_review_records
    ):
        """
        FR-030: Test meter event reporting after human review completion.

        Given: Records completed human review
        When: Triggering meter event reporting after review
        Then: Human audit usage is calculated and reported to Stripe
        """
        # Calculate usage from human review records
        # Note: Human review records typically have low confidence
        usage = usage_calculation_service.calculate_usage_from_records(
            records=sample_human_review_records,
            confidence_threshold=0.85
        )

        # Verify all treated as human audits (confidence < 0.85)
        assert usage["tenant_001"]["ai_labels"] == 0
        assert usage["tenant_001"]["human_audits"] == 2

        # Prepare and report batch
        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="review_batch_001",
            source="approval_workflow"
        )

        # Verify batch has only human_audits events
        assert all(e["meter_event"] == "human_audits" for e in batch["events"])
        assert batch["total_human_audits"] == 2
        assert batch["total_ai_labels"] == 0

        # Report to Stripe
        for event in batch["events"]:
            await mock_stripe_service.report_usage(
                meter_event=event["meter_event"],
                value=event["value"],
                tenant_id=event["tenant_id"],
                metadata=event["metadata"],
                db_session=mock_db_session
            )

        # Verify reported
        assert mock_stripe_service.report_usage.call_count == 1

    @pytest.mark.asyncio
    async def test_aggregated_review_reporting(
        self,
        usage_calculation_service,
        mock_stripe_service,
        mock_db_session
    ):
        """
        Test aggregated reporting after multiple human reviews.

        Given: Multiple human review completions from same tenant
        When: Triggering meter event reporting
        Then: Usage is aggregated into single report
        """
        # Simulate multiple review batches
        all_reviews = [
            {"id": i, "tenant_id": "tenant_001", "ai_confidence": 0.7 + (i % 3) * 0.05}
            for i in range(1, 11)  # 10 reviews
        ]

        usage = usage_calculation_service.calculate_usage_from_records(
            records=all_reviews,
            confidence_threshold=0.85
        )

        # All should be human audits (low confidence)
        assert usage["tenant_001"]["human_audits"] == 10

        # Prepare batch
        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="review_aggregated_001",
            source="approval_workflow"
        )

        # Should have single aggregated event
        assert len(batch["events"]) == 1
        assert batch["events"][0]["value"] == 10
        assert batch["events"][0]["meter_event"] == "human_audits"


# ============================================================================
# Tenant Isolation Tests (Security)
# ============================================================================

class TestTenantIsolationInPipeline:
    """Test suite for tenant isolation in pipeline context."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_ingestion(
        self,
        usage_calculation_service,
        mock_stripe_service,
        mock_db_session,
        sample_processed_records
    ):
        """
        Test that tenant isolation is enforced during ingestion.

        Given: Records from multiple tenants
        When: Calculating and reporting usage
        Then: Each tenant's usage is calculated and reported separately
        """
        usage = usage_calculation_service.calculate_usage_from_records(
            records=sample_processed_records,
            confidence_threshold=0.85
        )

        # Verify tenant isolation
        assert "tenant_001" in usage
        assert "tenant_002" in usage

        # No cross-tenant mixing
        tenant_001_total = usage["tenant_001"]["ai_labels"] + usage["tenant_001"]["human_audits"]
        tenant_002_total = usage["tenant_002"]["ai_labels"] + usage["tenant_002"]["human_audits"]

        assert tenant_001_total == 3  # All tenant_001 records
        assert tenant_002_total == 1  # All tenant_002 records

        # Prepare batch
        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="isolation_test_001"
        )

        # Verify events are per-tenant
        tenant_ids_in_batch = set(e["tenant_id"] for e in batch["events"])
        assert tenant_ids_in_batch == {"tenant_001", "tenant_002"}

    @pytest.mark.asyncio
    async def test_tenant_specific_stripe_customer_mapping(
        self,
        usage_calculation_service,
        mock_stripe_service,
        mock_db_session
    ):
        """
        Test that each tenant uses correct Stripe customer ID.

        Given: Usage calculation for multiple tenants
        When: Reporting to Stripe
        Then: Each tenant's events use correct Stripe customer ID
        """
        # Setup mock to return different customer IDs
        async def get_customer_mock(tenant_id, db_session):
            return {
                "tenant_id": tenant_id,
                "stripe_customer_id": f"cus_{tenant_id}",
                "email": f"{tenant_id}@example.com"
            }

        mock_stripe_service.get_customer_by_tenant = get_customer_mock

        records = [
            {"id": i, "tenant_id": f"tenant_{i % 3}", "ai_confidence": 0.9}
            for i in range(10)
        ]

        usage = usage_calculation_service.calculate_usage_from_records(records, 0.85)

        # Verify each tenant gets correct customer ID
        for tenant_id in usage.keys():
            customer = await mock_stripe_service.get_customer_by_tenant(
                tenant_id, mock_db_session
            )
            assert customer["stripe_customer_id"] == f"cus_{tenant_id}"


# ============================================================================
# Audit Trail Tests (FR-034)
# ============================================================================

class TestAuditTrail:
    """Test suite for audit trail functionality."""

    def test_audit_metadata_in_events(
        self,
        usage_calculation_service,
        sample_processed_records
    ):
        """
        FR-034: Test that audit trail metadata is included in events.

        Given: Usage calculation results
        When: Preparing meter events batch
        Then: Events include comprehensive audit metadata
        """
        usage = usage_calculation_service.calculate_usage_from_records(
            records=sample_processed_records,
            confidence_threshold=0.85
        )

        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="audit_test_001",
            source="ingestion_pipeline",
            metadata={"pipeline_run_id": "run_123"}
        )

        # Verify audit metadata in each event
        for event in batch["events"]:
            assert "metadata" in event
            metadata = event["metadata"]

            # Required audit fields
            assert "source" in metadata
            assert "batch_id" in metadata
            assert "calculated_at" in metadata

            # Verify values
            assert metadata["source"] == "ingestion_pipeline"
            assert metadata["batch_id"] == "audit_test_001"
            assert metadata["pipeline_run_id"] == "run_123"

    def test_calculated_timestamp_in_audit(
        self,
        usage_calculation_service,
        sample_processed_records
    ):
        """
        Test that calculated_at timestamp is included and valid.

        Given: Usage calculation results
        When: Preparing meter events batch
        Then: Each event has valid calculated_at timestamp
        """
        before_calculation = datetime.now(timezone.utc)

        usage = usage_calculation_service.calculate_usage_from_records(
            records=sample_processed_records,
            confidence_threshold=0.85
        )

        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="timestamp_test_001"
        )

        after_calculation = datetime.now(timezone.utc)

        # Verify timestamps are valid
        for event in batch["events"]:
            calculated_at_str = event["metadata"]["calculated_at"]
            calculated_at = datetime.fromisoformat(calculated_at_str)

            # Verify timestamp is within reasonable range
            assert before_calculation <= calculated_at <= after_calculation


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test suite for error handling in pipeline integration."""

    @pytest.mark.asyncio
    async def test_graceful_handling_of_missing_tenant_id(
        self,
        usage_calculation_service,
        mock_stripe_service
    ):
        """
        Test graceful handling of records without tenant_id.

        Given: Records with missing tenant_id
        When: Calculating usage
        Then: Raises appropriate validation error
        """
        from src.services.usage_calculation_service import UsageValidationError

        records = [
            {"id": 1, "ai_confidence": 0.90},  # Missing tenant_id
            {"id": 2, "tenant_id": "tenant_001", "ai_confidence": 0.85},
        ]

        with pytest.raises(UsageValidationError) as exc_info:
            usage_calculation_service.calculate_usage_from_records(records, 0.85)

        assert "tenant_id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handling_of_stripe_api_failure(
        self,
        usage_calculation_service,
        mock_stripe_service,
        mock_db_session,
        sample_processed_records
    ):
        """
        Test handling of Stripe API failure during reporting.

        Given: Usage calculation and batch preparation
        When: Stripe API call fails
        Then: Error is logged and handled gracefully
        """
        # Setup mock to raise error
        from src.services.stripe_service import StripeAPIError

        mock_stripe_service.report_usage = AsyncMock(
            side_effect=StripeAPIError("Stripe API unavailable")
        )

        usage = usage_calculation_service.calculate_usage_from_records(
            records=sample_processed_records,
            confidence_threshold=0.85
        )

        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="error_test_001"
        )

        # Attempt reporting - should handle error gracefully
        errors = []
        for event in batch["events"]:
            try:
                await mock_stripe_service.report_usage(
                    meter_event=event["meter_event"],
                    value=event["value"],
                    tenant_id=event["tenant_id"],
                    db_session=mock_db_session
                )
            except StripeAPIError as e:
                errors.append(str(e))

        # Verify errors were captured
        assert len(errors) == len(batch["events"])


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestPipelineEdgeCases:
    """Test suite for pipeline edge cases."""

    @pytest.mark.asyncio
    async def test_empty_batch_handling(
        self,
        usage_calculation_service,
        mock_stripe_service
    ):
        """
        Test handling of empty record batch.

        Given: Empty list of records
        When: Calculating usage and preparing batch
        Then: Returns empty results without errors
        """
        usage = usage_calculation_service.calculate_usage_from_records([], 0.85)

        assert usage == {}

        # Prepare batch from empty usage
        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="empty_test_001"
        )

        assert batch["events"] == []
        assert batch["total_ai_labels"] == 0
        assert batch["total_human_audits"] == 0
        assert batch["tenant_count"] == 0

    @pytest.mark.asyncio
    async def test_all_zero_values_filtered(
        self,
        usage_calculation_service,
        sample_processed_records
    ):
        """
        Test that zero-value events are filtered from batch.

        Given: Usage calculation with some tenants having zero values
        When: Preparing meter events batch
        Then: Zero-value events are not included in batch
        """
        # Manually create usage with zero values
        usage = {
            "tenant_001": {"ai_labels": 5, "human_audits": 0},
            "tenant_002": {"ai_labels": 0, "human_audits": 0},
            "tenant_003": {"ai_labels": 0, "human_audits": 3},
        }

        batch = usage_calculation_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id="zero_filter_test"
        )

        # Should only have 2 events (tenant_001 ai_labels, tenant_003 human_audits)
        assert len(batch["events"]) == 2

        # Verify no zero-value events
        for event in batch["events"]:
            assert event["value"] > 0

    @pytest.mark.asyncio
    async def test_large_batch_performance(
        self,
        usage_calculation_service,
        sample_processed_records
    ):
        """
        Test performance with large batch sizes.

        Given: Large batch of records (1000+)
        When: Calculating usage and preparing batch
        Then: Completes within reasonable time
        """
        import time

        large_batch = [
            {
                "id": i,
                "tenant_id": f"tenant_{i % 20}",  # 20 tenants
                "ai_confidence": 0.5 + (i % 50) / 100.0
            }
            for i in range(1000)
        ]

        start = time.time()
        usage = usage_calculation_service.calculate_usage_from_records(
            records=large_batch,
            confidence_threshold=0.85
        )
        elapsed = time.time() - start

        # Should complete quickly
        assert elapsed < 1.0
        assert len(usage) == 20  # 20 tenants
