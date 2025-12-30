"""
Tests for JobTrackingService

TDD tests for the job tracking application service.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import Mock

from src.application.job_tracking_service import JobTrackingService
from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.exceptions import (
    JobNotFoundError,
    InvalidStateTransition,
)
from src.infrastructure.repositories.job_repository import InMemoryJobRepository


@pytest.fixture
def repo():
    """Create fresh in-memory repository."""
    return InMemoryJobRepository()


@pytest.fixture
def service(repo):
    """Create job tracking service with in-memory repository."""
    return JobTrackingService(repo)


class TestJobCreation:
    """Tests for JobTrackingService.create_job()."""

    @pytest.mark.asyncio
    async def test_create_job(self, service):
        """Should create a job in PENDING state."""
        job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024 * 1024,
        )

        assert job.id is not None
        assert job.tenant_id == "tenant-123"
        assert job.file_name == "data.csv"
        assert job.file_size == 1024 * 1024
        assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_job_with_complexity_tier(self, service):
        """Should accept complexity tier."""
        job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
            complexity_tier="complex",
        )

        assert job.complexity_tier == "complex"

    @pytest.mark.asyncio
    async def test_create_job_with_estimated_cost(self, service):
        """Should accept estimated cost."""
        job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
            estimated_cost=Decimal("1.50"),
        )

        assert job.estimated_cost == Decimal("1.50")

    @pytest.mark.asyncio
    async def test_create_job_with_metadata(self, service):
        """Should accept metadata."""
        job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
            metadata={"vertical": "healthcare"},
        )

        assert job.metadata.get("vertical") == "healthcare"

    @pytest.mark.asyncio
    async def test_create_job_persisted(self, service, repo):
        """Created job should be persisted in repository."""
        job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        retrieved = await repo.get(job.id)
        assert retrieved is not None
        assert retrieved.id == job.id


class TestStateTransitions:
    """Tests for job state transitions."""

    @pytest.mark.asyncio
    async def test_start_processing(self, service):
        """Should transition job from PENDING to PROCESSING."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        original_version = pending_job.version

        job = await service.start_processing(pending_job.id)

        assert job.status == JobStatus.PROCESSING
        assert job.started_at is not None
        assert job.version == original_version + 1

    @pytest.mark.asyncio
    async def test_start_processing_not_found(self, service):
        """Should raise JobNotFoundError for non-existent job."""
        with pytest.raises(JobNotFoundError):
            await service.start_processing("non-existent-id")

    @pytest.mark.asyncio
    async def test_mark_complete(self, service):
        """Should transition job from PROCESSING to COMPLETE."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        processing_job = await service.start_processing(pending_job.id)

        job = await service.mark_complete(
            job_id=processing_job.id,
            result_records=1000,
            result_url="https://example.com/results",
            actual_cost=Decimal("0.50"),
        )

        assert job.status == JobStatus.COMPLETE
        assert job.result_records == 1000
        assert job.result_url == "https://example.com/results"
        assert job.actual_cost == Decimal("0.50")
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_mark_complete_from_pending_fails(self, service):
        """Should fail to complete from PENDING state."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        with pytest.raises(InvalidStateTransition):
            await service.mark_complete(
                job_id=pending_job.id,
                result_records=100,
            )

    @pytest.mark.asyncio
    async def test_mark_failed(self, service):
        """Should transition job to FAILED state."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        processing_job = await service.start_processing(pending_job.id)

        job = await service.mark_failed(
            job_id=processing_job.id,
            error_message="Processing error",
        )

        assert job.status == JobStatus.FAILED
        assert job.error_message == "Processing error"

    @pytest.mark.asyncio
    async def test_mark_failed_from_pending(self, service):
        """Should allow failing from PENDING state."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        job = await service.mark_failed(
            job_id=pending_job.id,
            error_message="Validation error",
        )

        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_cancel_job(self, service):
        """Should transition job to CANCELLED state."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        job = await service.cancel_job(
            job_id=pending_job.id,
            reason="User requested cancellation",
        )

        assert job.status == JobStatus.CANCELLED
        assert job.metadata.get("cancellation_reason") == "User requested cancellation"

    @pytest.mark.asyncio
    async def test_cancel_processing_job(self, service):
        """Should allow cancelling a PROCESSING job."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        processing_job = await service.start_processing(pending_job.id)

        job = await service.cancel_job(processing_job.id)

        assert job.status == JobStatus.CANCELLED


class TestRetryOperations:
    """Tests for job retry operations."""

    @pytest.mark.asyncio
    async def test_retry_job(self, service):
        """Should retry a failed job."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        # Fail the job first
        await service.mark_failed(pending_job.id, "Temporary error")

        # Retry
        job = await service.retry_job(pending_job.id)

        assert job.status == JobStatus.PENDING
        assert job.error_message is None

    @pytest.mark.asyncio
    async def test_retry_max_exceeded(self, service, repo):
        """Should fail retry when max retries exceeded."""
        # Create a job - version will be 1
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        # Get a fresh copy, update max_retries, and increment version for save
        job_to_update = await repo.get_by_id(pending_job.id)
        job_to_update.max_retries = 1
        job_to_update.version += 1  # Increment version for optimistic locking
        await repo.save(job_to_update)

        # Fail once - this will increment retry_count to 1
        await service.mark_failed(pending_job.id, "First error")

        # Fail should increment retry_count, making can_retry False
        job = await service.get_job(pending_job.id)
        assert job.retry_count == 1
        assert job.can_retry is False

        # Retry should fail
        with pytest.raises(InvalidStateTransition):
            await service.retry_job(pending_job.id)

    @pytest.mark.asyncio
    async def test_retry_from_pending_fails(self, service):
        """Should fail to retry from PENDING state."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        with pytest.raises(InvalidStateTransition):
            await service.retry_job(pending_job.id)


class TestQueryOperations:
    """Tests for job query operations."""

    @pytest.mark.asyncio
    async def test_get_job(self, service):
        """Should retrieve job by ID."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        job = await service.get_job(pending_job.id)

        assert job is not None
        assert job.id == pending_job.id

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, service):
        """Should return None for non-existent job."""
        job = await service.get_job("non-existent-id")

        assert job is None

    @pytest.mark.asyncio
    async def test_get_job_or_fail(self, service):
        """Should retrieve job or raise error."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        job = await service.get_job_or_fail(pending_job.id)

        assert job.id == pending_job.id

    @pytest.mark.asyncio
    async def test_get_job_or_fail_not_found(self, service):
        """Should raise JobNotFoundError."""
        with pytest.raises(JobNotFoundError):
            await service.get_job_or_fail("non-existent-id")

    @pytest.mark.asyncio
    async def test_list_tenant_jobs(self, service):
        """Should list jobs for a tenant."""
        # Create multiple jobs
        await service.create_job("tenant-1", "file1.csv", 1024)
        await service.create_job("tenant-1", "file2.csv", 2048)
        await service.create_job("tenant-2", "file3.csv", 3072)

        jobs = await service.list_tenant_jobs("tenant-1")

        assert len(jobs) == 2
        assert all(j.tenant_id == "tenant-1" for j in jobs)

    @pytest.mark.asyncio
    async def test_list_tenant_jobs_with_status(self, service):
        """Should filter by status."""
        job1 = await service.create_job("tenant-1", "file1.csv", 1024)
        await service.create_job("tenant-1", "file2.csv", 2048)
        await service.start_processing(job1.id)

        pending_jobs = await service.list_tenant_jobs("tenant-1", status=JobStatus.PENDING)
        processing_jobs = await service.list_tenant_jobs("tenant-1", status=JobStatus.PROCESSING)

        assert len(pending_jobs) == 1
        assert len(processing_jobs) == 1

    @pytest.mark.asyncio
    async def test_list_tenant_jobs_pagination(self, service):
        """Should support pagination."""
        for i in range(5):
            await service.create_job("tenant-1", f"file{i}.csv", 1024)

        page1 = await service.list_tenant_jobs("tenant-1", limit=2, offset=0)
        page2 = await service.list_tenant_jobs("tenant-1", limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_count_tenant_jobs(self, service):
        """Should count jobs for a tenant."""
        await service.create_job("tenant-1", "file1.csv", 1024)
        await service.create_job("tenant-1", "file2.csv", 2048)
        await service.create_job("tenant-2", "file3.csv", 3072)

        count = await service.count_tenant_jobs("tenant-1")

        assert count == 2

    @pytest.mark.asyncio
    async def test_count_tenant_jobs_with_status(self, service):
        """Should count with status filter."""
        job1 = await service.create_job("tenant-1", "file1.csv", 1024)
        await service.create_job("tenant-1", "file2.csv", 2048)
        await service.start_processing(job1.id)

        pending_count = await service.count_tenant_jobs("tenant-1", status=JobStatus.PENDING)
        processing_count = await service.count_tenant_jobs("tenant-1", status=JobStatus.PROCESSING)

        assert pending_count == 1
        assert processing_count == 1


class TestBackgroundOperations:
    """Tests for background operations."""

    @pytest.mark.asyncio
    async def test_handle_stale_jobs(self, service, repo):
        """Should fail jobs that have been processing too long."""
        # Create and start a job
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        # Get a fresh copy from the repo to modify started_at
        job_to_update = await repo.get_by_id(job.id)
        job_to_update.started_at = datetime.utcnow() - timedelta(hours=2)
        job_to_update.version += 1  # Increment version for optimistic locking
        await repo.save(job_to_update)

        # Handle stale jobs with 60 minute timeout
        failed_jobs = await service.handle_stale_jobs(timeout_minutes=60)

        assert len(failed_jobs) == 1
        assert failed_jobs[0].status == JobStatus.FAILED
        assert "timed out" in failed_jobs[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_handle_stale_jobs_respects_timeout(self, service):
        """Should not fail jobs that are within timeout."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        # Job just started - should not be stale
        failed_jobs = await service.handle_stale_jobs(timeout_minutes=60)

        assert len(failed_jobs) == 0

    @pytest.mark.asyncio
    async def test_get_pending_jobs(self, service):
        """Should return pending jobs ready for processing."""
        job1 = await service.create_job("tenant-1", "file1.csv", 1024)
        await service.create_job("tenant-1", "file2.csv", 2048)
        await service.create_job("tenant-1", "file3.csv", 3072)

        # Start one job
        await service.start_processing(job1.id)

        pending = await service.get_pending_jobs()

        assert len(pending) == 2
        assert all(j.status == JobStatus.PENDING for j in pending)


class TestVersioningAndConcurrency:
    """Tests for optimistic locking and version management."""

    @pytest.mark.asyncio
    async def test_version_increments_on_transition(self, service):
        """Version should increment on each state transition."""
        pending_job = await service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        initial_version = pending_job.version

        job = await service.start_processing(pending_job.id)
        assert job.version == initial_version + 1

        job = await service.mark_complete(job.id, result_records=100)
        assert job.version == initial_version + 2


class TestAMLJobTracking:
    """Tests for AML-specific job tracking functionality."""

    @pytest.mark.asyncio
    async def test_mark_complete_with_aml_risk_counts(self, service):
        """Should store AML risk level counts in job metadata."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        aml_risk_counts = {
            "LOW": 50,
            "MEDIUM": 30,
            "HIGH": 15,
            "CRITICAL": 5,
        }

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_risk_level_counts=aml_risk_counts,
        )

        assert completed_job.metadata["aml_results"]["risk_level_counts"] == aml_risk_counts
        assert completed_job.status == JobStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_mark_complete_with_aml_inter_rater_agreement(self, service):
        """Should store Cohen's Kappa score in job metadata."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_inter_rater_agreement=0.75,
        )

        assert completed_job.metadata["aml_results"]["inter_rater_agreement"] == 0.75

    @pytest.mark.asyncio
    async def test_mark_complete_with_aml_expert_review_count(self, service):
        """Should store expert review count in job metadata."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_expert_review_count=12,
        )

        assert completed_job.metadata["aml_results"]["expert_review_count"] == 12

    @pytest.mark.asyncio
    async def test_mark_complete_with_aml_audit_report_url(self, service):
        """Should store audit report URL in job metadata."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_audit_report_url="/reports/audit_job_123.pdf",
        )

        assert completed_job.metadata["aml_results"]["audit_report_url"] == "/reports/audit_job_123.pdf"

    @pytest.mark.asyncio
    async def test_mark_complete_with_all_aml_fields(self, service):
        """Should store all AML fields together in metadata."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        aml_risk_counts = {"LOW": 80, "MEDIUM": 15, "HIGH": 5, "CRITICAL": 0}

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_risk_level_counts=aml_risk_counts,
            aml_inter_rater_agreement=0.82,
            aml_expert_review_count=3,
            aml_audit_report_url="/reports/audit_456.pdf",
        )

        aml_results = completed_job.metadata["aml_results"]
        assert aml_results["risk_level_counts"] == aml_risk_counts
        assert aml_results["inter_rater_agreement"] == 0.82
        assert aml_results["expert_review_count"] == 3
        assert aml_results["audit_report_url"] == "/reports/audit_456.pdf"

    @pytest.mark.asyncio
    async def test_mark_complete_with_zero_inter_rater_agreement(self, service):
        """
        CRITICAL BUG FIX TEST: Should store zero (0.0) inter-rater agreement score.

        This test ensures that a valid score of 0.0 is not treated as falsy
        and is properly stored in metadata. The old bug used `any()` with
        `is not None` checks which failed for 0.0 values.
        """
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_inter_rater_agreement=0.0,  # Valid score indicating no agreement
        )

        # CRITICAL: 0.0 should be stored, not treated as falsy
        assert "aml_results" in completed_job.metadata
        assert completed_job.metadata["aml_results"]["inter_rater_agreement"] == 0.0

    @pytest.mark.asyncio
    async def test_mark_complete_with_zero_expert_review_count(self, service):
        """Should store zero expert review count."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_expert_review_count=0,  # Explicit zero means no reviews needed
        )

        # Zero is a valid count and should be stored
        assert "aml_results" in completed_job.metadata
        assert completed_job.metadata["aml_results"]["expert_review_count"] == 0

    @pytest.mark.asyncio
    async def test_mark_complete_without_aml_fields(self, service):
        """Should complete job successfully without AML fields."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        completed_job = await service.mark_complete(
            job_id=job.id,
            result_records=100,
        )

        assert completed_job.status == JobStatus.COMPLETE
        assert "aml_results" not in completed_job.metadata

    @pytest.mark.asyncio
    async def test_get_aml_job_metrics_from_metadata(self, service, repo):
        """Should retrieve AML metrics from job metadata."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        # Store AML results in metadata
        aml_risk_counts = {"LOW": 45, "MEDIUM": 30, "HIGH": 20, "CRITICAL": 5}
        typology_counts = {"ML": 25, "TF": 15, "PEP": 10, "FRAUD": 30, "SANCTIONS": 20}

        await service.mark_complete(
            job_id=job.id,
            result_records=100,
            aml_risk_level_counts=aml_risk_counts,
            aml_inter_rater_agreement=0.68,
            aml_expert_review_count=8,
        )

        # Add typology counts and average confidence to metadata
        # Need to update the job directly and save to repository
        job_updated = await service.get_job_or_fail(job.id)
        job_updated.metadata["aml_results"]["typology_counts"] = typology_counts
        job_updated.metadata["aml_results"]["average_confidence"] = 0.75
        # Increment version to satisfy optimistic locking
        job_updated.version += 1
        await repo.save(job_updated)

        metrics = await service.get_aml_job_metrics(job.id)

        assert metrics["total_transactions"] == 100
        assert metrics["risk_distribution"] == aml_risk_counts
        assert metrics["typology_distribution"] == typology_counts
        assert metrics["average_confidence"] == 0.75
        assert metrics["expert_review_count"] == 8
        assert metrics["inter_rater_agreement"] == 0.68

    @pytest.mark.asyncio
    async def test_get_aml_job_metrics_from_labels(self, service):
        """Should calculate AML metrics from provided labels."""
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus
        from decimal import Decimal

        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)
        await service.mark_complete(job_id=job.id, result_records=5)

        # Create mock AML labels
        mock_labels = []
        for i, (risk, typology, confidence) in enumerate([
            (AMLRiskLevel.LOW, "ML", Decimal("0.65")),
            (AMLRiskLevel.MEDIUM, "TF", Decimal("0.72")),
            (AMLRiskLevel.HIGH, "PEP", Decimal("0.58")),
            (AMLRiskLevel.LOW, "ML", Decimal("0.81")),
            (AMLRiskLevel.MEDIUM, "TF", Decimal("0.70")),
        ]):
            label = Mock()
            label.risk_level = risk
            label.typology = typology
            label.confidence_score = confidence
            label.expert_review_status = AMLExpertReviewStatus.PENDING if i < 2 else AMLExpertReviewStatus.AGREED
            mock_labels.append(label)

        metrics = await service.get_aml_job_metrics(job.id, aml_labels=mock_labels)

        assert metrics["total_transactions"] == 5
        assert metrics["risk_distribution"]["LOW"] == 2
        assert metrics["risk_distribution"]["MEDIUM"] == 2
        assert metrics["risk_distribution"]["HIGH"] == 1
        assert metrics["typology_distribution"]["ML"] == 2
        assert metrics["typology_distribution"]["TF"] == 2
        assert metrics["typology_distribution"]["PEP"] == 1
        assert metrics["expert_review_count"] == 2
        assert abs(metrics["average_confidence"] - 0.692) < 0.01  # (0.65+0.72+0.58+0.81+0.70)/5

    @pytest.mark.asyncio
    async def test_get_aml_job_metrics_empty_labels(self, service):
        """Should handle empty labels list gracefully."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)
        await service.mark_complete(job_id=job.id, result_records=0)

        metrics = await service.get_aml_job_metrics(job.id, aml_labels=[])

        assert metrics["total_transactions"] == 0
        assert metrics["risk_distribution"] == {}
        assert metrics["typology_distribution"] == {}
        assert metrics["average_confidence"] == 0.0
        assert metrics["expert_review_count"] == 0

    @pytest.mark.asyncio
    async def test_get_aml_job_metrics_nonexistent_job(self, service):
        """Should raise JobNotFoundError for non-existent job."""
        with pytest.raises(JobNotFoundError):
            await service.get_aml_job_metrics("non-existent-job-id")

    @pytest.mark.asyncio
    async def test_get_aml_job_metrics_partial_metadata(self, service):
        """Should handle partial AML metadata gracefully."""
        job = await service.create_job("tenant-1", "file.csv", 1024)
        await service.start_processing(job.id)

        # Store only partial AML results
        await service.mark_complete(
            job_id=job.id,
            result_records=50,
            aml_risk_level_counts={"LOW": 30, "MEDIUM": 20},
        )

        metrics = await service.get_aml_job_metrics(job.id)

        assert metrics["total_transactions"] == 50
        assert metrics["risk_distribution"] == {"LOW": 30, "MEDIUM": 20}
        assert metrics["typology_distribution"] == {}  # Not stored
        assert metrics["average_confidence"] == 0.0  # Not stored
        assert metrics["expert_review_count"] == 0  # Not stored
        assert metrics["inter_rater_agreement"] is None  # Not stored
