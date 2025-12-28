"""
Tests for ProcessingJob Aggregate

TDD tests for job state machine and transitions.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.exceptions import InvalidStateTransition


class TestProcessingJobCreation:
    """Tests for ProcessingJob creation."""

    def test_create_with_factory(self):
        """Factory method should create job with defaults."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024 * 1024,
        )

        assert job.tenant_id == "tenant-123"
        assert job.file_name == "data.csv"
        assert job.file_size == 1024 * 1024
        assert job.status == JobStatus.PENDING
        assert job.id is not None
        assert job.version == 1
        assert job.estimated_cost > 0

    def test_create_with_custom_cost(self):
        """Should accept custom cost estimate."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
            estimated_cost=Decimal("1.50"),
        )

        assert job.estimated_cost == Decimal("1.50")

    def test_create_with_complexity_tier(self):
        """Should accept complexity tier."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
            complexity_tier="complex",
        )

        assert job.complexity_tier == "complex"

    def test_timestamps_initialized(self):
        """Should initialize created_at and updated_at."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        assert job.created_at is not None
        assert job.updated_at is not None
        assert job.started_at is None
        assert job.completed_at is None


class TestJobStatusTransitions:
    """Tests for job state machine transitions."""

    @pytest.fixture
    def pending_job(self):
        """Create a job in PENDING state."""
        return ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

    @pytest.fixture
    def processing_job(self, pending_job):
        """Create a job in PROCESSING state."""
        pending_job.transition_to_processing()
        return pending_job

    def test_pending_to_processing(self, pending_job):
        """PENDING -> PROCESSING should succeed."""
        original_version = pending_job.version

        pending_job.transition_to_processing()

        assert pending_job.status == JobStatus.PROCESSING
        assert pending_job.started_at is not None
        assert pending_job.version == original_version + 1

    def test_pending_to_failed(self, pending_job):
        """PENDING -> FAILED should succeed."""
        pending_job.transition_to_failed(error_message="Validation error")

        assert pending_job.status == JobStatus.FAILED
        assert pending_job.error_message == "Validation error"
        assert pending_job.retry_count == 1

    def test_pending_to_cancelled(self, pending_job):
        """PENDING -> CANCELLED should succeed."""
        pending_job.transition_to_cancelled(reason="User request")

        assert pending_job.status == JobStatus.CANCELLED
        assert pending_job.metadata.get("cancellation_reason") == "User request"

    def test_processing_to_complete(self, processing_job):
        """PROCESSING -> COMPLETE should succeed."""
        processing_job.transition_to_complete(
            result_records=1000,
            result_url="https://example.com/results",
            actual_cost=Decimal("0.50"),
        )

        assert processing_job.status == JobStatus.COMPLETE
        assert processing_job.result_records == 1000
        assert processing_job.result_url == "https://example.com/results"
        assert processing_job.actual_cost == Decimal("0.50")
        assert processing_job.completed_at is not None

    def test_processing_to_failed(self, processing_job):
        """PROCESSING -> FAILED should succeed."""
        processing_job.transition_to_failed(error_message="Timeout")

        assert processing_job.status == JobStatus.FAILED
        assert processing_job.error_message == "Timeout"

    def test_processing_to_cancelled(self, processing_job):
        """PROCESSING -> CANCELLED should succeed."""
        processing_job.transition_to_cancelled()

        assert processing_job.status == JobStatus.CANCELLED

    def test_failed_to_pending_retry(self, pending_job):
        """FAILED -> PENDING (retry) should succeed."""
        pending_job.transition_to_failed(error_message="First failure")
        pending_job.retry()

        assert pending_job.status == JobStatus.PENDING
        assert pending_job.error_message is None
        assert pending_job.started_at is None

    def test_max_retries_exceeded(self, pending_job):
        """Should prevent retry when max retries exceeded."""
        pending_job.max_retries = 2

        # Fail twice
        for i in range(2):
            pending_job.transition_to_failed(error_message=f"Failure {i+1}")
            if i < 1:
                pending_job.retry()

        # Third retry should fail
        with pytest.raises(InvalidStateTransition):
            pending_job.retry()


class TestInvalidTransitions:
    """Tests for invalid state transitions."""

    @pytest.fixture
    def pending_job(self):
        return ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

    def test_pending_to_complete_invalid(self, pending_job):
        """PENDING -> COMPLETE should fail."""
        with pytest.raises(InvalidStateTransition) as exc_info:
            pending_job.transition_to_complete(result_records=100)

        assert exc_info.value.current_state == "pending"
        assert exc_info.value.attempted_state == "complete"

    def test_complete_to_processing_invalid(self, pending_job):
        """COMPLETE -> PROCESSING should fail."""
        pending_job.transition_to_processing()
        pending_job.transition_to_complete(result_records=100)

        with pytest.raises(InvalidStateTransition):
            pending_job.transition_to_processing()

    def test_cancelled_to_processing_invalid(self, pending_job):
        """CANCELLED -> PROCESSING should fail."""
        pending_job.transition_to_cancelled()

        with pytest.raises(InvalidStateTransition):
            pending_job.transition_to_processing()

    def test_complete_is_terminal(self, pending_job):
        """Complete should be a terminal state."""
        pending_job.transition_to_processing()
        pending_job.transition_to_complete(result_records=100)

        assert pending_job.is_terminal is True
        assert len(pending_job.get_allowed_transitions()) == 0


class TestJobProperties:
    """Tests for computed properties."""

    def test_can_retry_when_failed(self):
        """can_retry should be True for failed jobs with retries left."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        job.transition_to_failed(error_message="Error")

        assert job.can_retry is True

    def test_can_retry_when_max_exceeded(self):
        """can_retry should be False when max retries exceeded."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        job.max_retries = 1
        job.transition_to_failed(error_message="Error")

        assert job.can_retry is False

    def test_processing_duration(self):
        """Should calculate processing duration."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        job.transition_to_processing()

        # Should be non-zero (small but positive)
        assert job.processing_duration_seconds is not None
        assert job.processing_duration_seconds >= 0

    def test_processing_duration_none_when_not_started(self):
        """processing_duration should be None when job not started."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        assert job.processing_duration_seconds is None

    def test_is_processing(self):
        """is_processing should return True only when processing."""
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        assert job.is_processing is False

        job.transition_to_processing()
        assert job.is_processing is True

        job.transition_to_complete(result_records=100)
        assert job.is_processing is False


class TestJobAllowedTransitions:
    """Tests for allowed transitions query."""

    def test_pending_allowed_transitions(self):
        """PENDING should allow PROCESSING, FAILED, CANCELLED."""
        assert JobStatus.PENDING.allowed_transitions == [
            JobStatus.PROCESSING,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        ]

    def test_processing_allowed_transitions(self):
        """PROCESSING should allow COMPLETE, FAILED, CANCELLED."""
        assert JobStatus.PROCESSING.allowed_transitions == [
            JobStatus.COMPLETE,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        ]

    def test_complete_no_transitions(self):
        """COMPLETE should have no allowed transitions."""
        assert JobStatus.COMPLETE.allowed_transitions == []

    def test_cancelled_no_transitions(self):
        """CANCELLED should have no allowed transitions."""
        assert JobStatus.CANCELLED.allowed_transitions == []

    def test_failed_allows_pending(self):
        """FAILED should allow PENDING for retry."""
        assert JobStatus.PENDING in JobStatus.FAILED.allowed_transitions
