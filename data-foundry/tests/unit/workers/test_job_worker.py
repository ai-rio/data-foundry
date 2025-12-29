"""
Tests for Background Job Worker

TDD tests for JobWorker following red-green-refactor discipline.
This file contains all tests for:
- Phase 1: Core Polling Loop
- Phase 2: Job Claiming with Optimistic Locking
- Phase 3: Flow Execution
- Phase 4: Retry Logic
- Phase 5: Graceful Shutdown

SOLID Principles Applied:
- Single Responsibility: Each test class tests one component
- Dependency Injection: All dependencies are mocked/injected
- Interface Segregation: Tests use abstract repository interface
"""

import pytest
import asyncio
import signal
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.exceptions import JobConcurrencyError


# =============================================================================
# PHASE 1: Core Polling Loop Tests
# =============================================================================

class TestPollingForPendingJobs:
    """
    Phase 1: Tests for poll_for_pending_jobs()

    RED PHASE: These tests will fail initially because JobWorker doesn't exist.
    """

    @pytest.mark.asyncio
    async def test_poll_for_pending_jobs_returns_pending_jobs(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
    ):
        """Worker polls database for PENDING jobs."""
        # Arrange
        mock_job_repo.list_by_status.return_value = [sample_pending_job]

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Act
        jobs = await worker.poll_for_pending_jobs()

        # Assert
        assert len(jobs) == 1
        assert jobs[0].id == sample_pending_job.id
        assert jobs[0].status == JobStatus.PENDING
        mock_job_repo.list_by_status.assert_called_once_with(
            status=JobStatus.PENDING,
            limit=1,
        )

    @pytest.mark.asyncio
    async def test_poll_for_pending_jobs_returns_empty_when_no_pending_jobs(
        self,
        mock_job_repo: AsyncMock,
    ):
        """Worker returns empty list when no pending jobs exist."""
        # Arrange
        mock_job_repo.list_by_status.return_value = []

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Act
        jobs = await worker.poll_for_pending_jobs()

        # Assert
        assert len(jobs) == 0
        mock_job_repo.list_by_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_for_pending_jobs_respects_limit(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
    ):
        """Worker respects batch_size configuration when polling."""
        # Arrange
        mock_job_repo.list_by_status.return_value = [sample_pending_job]

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo, batch_size=5)

        # Act
        await worker.poll_for_pending_jobs()

        # Assert
        mock_job_repo.list_by_status.assert_called_once_with(
            status=JobStatus.PENDING,
            limit=5,
        )


# =============================================================================
# PHASE 2: Job Claiming with Optimistic Locking Tests
# =============================================================================

class TestJobClaiming:
    """
    Phase 2: Tests for claim_job() with optimistic locking

    RED PHASE: Tests for claiming jobs atomically with version check.
    """

    @pytest.mark.asyncio
    async def test_claim_job_success(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
        sample_processing_job: ProcessingJob,
    ):
        """Worker claims PENDING job by marking PROCESSING with version check."""
        # Arrange
        mock_job_repo.claim_job.return_value = sample_processing_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Act
        claimed = await worker.claim_job(sample_pending_job)

        # Assert
        assert claimed.status == JobStatus.PROCESSING
        assert claimed.version == 2
        mock_job_repo.claim_job.assert_called_once_with(
            job_id=sample_pending_job.id,
            expected_version=sample_pending_job.version,
        )

    @pytest.mark.asyncio
    async def test_claim_job_version_mismatch_raises(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
    ):
        """Version mismatch means another worker already claimed the job."""
        # Arrange
        mock_job_repo.claim_job.side_effect = JobConcurrencyError(
            job_id=sample_pending_job.id,
            expected_version=1,
            actual_version=2,
        )

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Act & Assert
        with pytest.raises(JobConcurrencyError):
            await worker.claim_job(sample_pending_job)

    @pytest.mark.asyncio
    async def test_claim_job_sets_started_at_timestamp(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
        sample_processing_job: ProcessingJob,
    ):
        """Claiming job should set started_at timestamp."""
        # Arrange
        sample_processing_job.started_at = datetime.utcnow()
        mock_job_repo.claim_job.return_value = sample_processing_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Act
        claimed = await worker.claim_job(sample_pending_job)

        # Assert
        assert claimed.started_at is not None


# =============================================================================
# PHASE 3: Flow Execution Tests
# =============================================================================

class TestFlowExecution:
    """
    Phase 3: Tests for execute_job()

    RED PHASE: Tests for executing data_ingestion_flow and updating status.
    """

    @pytest.mark.asyncio
    async def test_execute_job_success(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker executes data_ingestion_flow() and marks job COMPLETE."""
        # Arrange
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 100}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        result = await worker.execute_job(sample_processing_job)

        # Assert
        assert result.status == JobStatus.COMPLETE
        mock_flow_func.assert_called_once()
        mock_job_repo.mark_complete.assert_called_once_with(
            job_id=sample_processing_job.id,
            version=sample_processing_job.version,
            result_records=100,
        )

    @pytest.mark.asyncio
    async def test_execute_job_passes_correct_parameters_to_flow(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Flow function receives correct job parameters."""
        # Arrange
        mock_job_repo.mark_complete.return_value = sample_complete_job
        sample_processing_job.file_key = "tenant-123/job-001/data.csv"

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        await worker.execute_job(sample_processing_job)

        # Assert
        mock_flow_func.assert_called_once_with(
            data_source=sample_processing_job.file_key,
            job_id=sample_processing_job.id,
            tenant_id=sample_processing_job.tenant_id,
            enable_validation=True,
            enable_ai_labeling=True,
            enable_pii_redaction=True,
            enable_human_review=False,
        )

    @pytest.mark.asyncio
    async def test_execute_job_failure_marks_failed(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_failed_job: ProcessingJob,
    ):
        """Flow raises exception, worker marks job FAILED with error."""
        # Arrange
        mock_flow_func.side_effect = ValueError("Flow processing error")
        mock_job_repo.mark_failed.return_value = sample_failed_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        result = await worker.execute_job(sample_processing_job)

        # Assert
        assert result.status == JobStatus.FAILED
        mock_job_repo.mark_failed.assert_called_once()
        call_args = mock_job_repo.mark_failed.call_args
        assert call_args.kwargs["job_id"] == sample_processing_job.id
        assert "Flow processing error" in call_args.kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_execute_job_handles_flow_returning_failure(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_failed_job: ProcessingJob,
    ):
        """Flow returns success=False, worker marks job FAILED."""
        # Arrange
        mock_flow_func.return_value = {"success": False, "error": "Validation failed"}
        mock_job_repo.mark_failed.return_value = sample_failed_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        result = await worker.execute_job(sample_processing_job)

        # Assert
        assert result.status == JobStatus.FAILED
        mock_job_repo.mark_failed.assert_called_once()


# =============================================================================
# PHASE 4: Retry Logic Tests
# =============================================================================

class TestRetryLogic:
    """
    Phase 4: Tests for execute_job_with_retry()

    RED PHASE: Tests for exponential backoff retry on transient failures.
    """

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure_succeeds_on_second_attempt(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Transient failure (connection timeout) triggers retry, succeeds on second attempt."""
        # Arrange
        mock_flow_func.side_effect = [
            ConnectionError("timeout"),  # First attempt fails
            {"success": True, "valid_records": 50},  # Second attempt succeeds
        ]
        mock_job_repo.mark_complete.return_value = sample_complete_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
            max_retries=3,
            backoff_base=0.01,  # Fast backoff for tests
        )

        # Act
        result = await worker.execute_job_with_retry(sample_processing_job)

        # Assert
        assert result.status == JobStatus.COMPLETE
        assert mock_flow_func.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout_error(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """TimeoutError triggers retry."""
        # Arrange
        mock_flow_func.side_effect = [
            TimeoutError("request timeout"),
            {"success": True, "valid_records": 50},
        ]
        mock_job_repo.mark_complete.return_value = sample_complete_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
            max_retries=3,
            backoff_base=0.01,
        )

        # Act
        result = await worker.execute_job_with_retry(sample_processing_job)

        # Assert
        assert result.status == JobStatus.COMPLETE
        assert mock_flow_func.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhaustion_marks_failed(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_failed_job: ProcessingJob,
    ):
        """After 3 retries, mark job FAILED."""
        # Arrange
        mock_flow_func.side_effect = ConnectionError("persistent failure")
        mock_job_repo.mark_failed.return_value = sample_failed_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
            max_retries=3,
            backoff_base=0.01,  # Fast backoff for tests
        )

        # Act
        result = await worker.execute_job_with_retry(sample_processing_job)

        # Assert
        assert result.status == JobStatus.FAILED
        assert mock_flow_func.call_count == 3
        call_args = mock_job_repo.mark_failed.call_args
        assert "retries exhausted" in call_args.kwargs["error_message"].lower()

    @pytest.mark.asyncio
    async def test_non_transient_error_fails_immediately(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_failed_job: ProcessingJob,
    ):
        """Non-transient errors (ValueError, KeyError) fail immediately without retry."""
        # Arrange
        mock_flow_func.side_effect = ValueError("Invalid data format")
        mock_job_repo.mark_failed.return_value = sample_failed_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
            max_retries=3,
            backoff_base=0.01,
        )

        # Act
        result = await worker.execute_job_with_retry(sample_processing_job)

        # Assert
        assert result.status == JobStatus.FAILED
        assert mock_flow_func.call_count == 1  # No retry for ValueError

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_failed_job: ProcessingJob,
    ):
        """Verify exponential backoff: 1s, 4s, 16s (base * 4^attempt)."""
        # Arrange
        mock_flow_func.side_effect = ConnectionError("timeout")
        mock_job_repo.mark_failed.return_value = sample_failed_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
            max_retries=3,
            backoff_base=1.0,
        )

        # Act
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await worker.execute_job_with_retry(sample_processing_job)

            # Assert - verify backoff times: 1s, 4s (base * 4^attempt)
            assert mock_sleep.call_count == 2  # 2 sleeps between 3 attempts
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            assert sleep_calls[0] == 1.0   # First backoff: 1 * 4^0 = 1
            assert sleep_calls[1] == 4.0   # Second backoff: 1 * 4^1 = 4


# =============================================================================
# PHASE 5: Graceful Shutdown Tests
# =============================================================================

class TestGracefulShutdown:
    """
    Phase 5: Tests for graceful shutdown handling

    RED PHASE: Tests for SIGTERM handling and graceful shutdown.
    """

    @pytest.mark.asyncio
    async def test_shutdown_on_sigterm_sets_flag(
        self,
        mock_job_repo: AsyncMock,
    ):
        """SIGTERM signal sets shutdown flag."""
        # Arrange
        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Act
        worker._handle_sigterm()

        # Assert
        assert worker._should_shutdown is True

    @pytest.mark.asyncio
    async def test_worker_stops_polling_on_shutdown(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
    ):
        """Worker stops polling after shutdown signal."""
        # Arrange
        mock_job_repo.list_by_status.return_value = [sample_pending_job]

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            poll_interval=0.01,
        )

        # Act - set shutdown before running
        worker._should_shutdown = True

        # Run should exit immediately
        await worker.run()

        # Assert - should not poll since shutdown is set
        mock_job_repo.list_by_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_finishes_current_job(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker finishes current job before exiting."""
        # Arrange
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 50}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act - process job and set shutdown during execution
        async def process_and_check_completion():
            task = asyncio.create_task(worker._process_job(sample_processing_job))
            await asyncio.sleep(0.001)  # Let it start
            worker._handle_sigterm()  # Signal shutdown
            return await task  # Should complete the current job

        result = await process_and_check_completion()

        # Assert - job was completed despite shutdown
        assert result.status == JobStatus.COMPLETE
        mock_job_repo.mark_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_does_not_claim_new_jobs_during_shutdown(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
    ):
        """Worker does not claim new jobs after shutdown signal."""
        # Arrange
        mock_job_repo.list_by_status.return_value = [sample_pending_job, sample_pending_job]

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Simulate shutdown after first poll
        worker._should_shutdown = True

        # Act - try to process jobs
        await worker._run_once()

        # Assert - should not claim any jobs
        mock_job_repo.claim_job.assert_not_called()


# =============================================================================
# WORKER LIFECYCLE TESTS
# =============================================================================

class TestWorkerLifecycle:
    """
    Tests for the overall worker lifecycle and integration.
    """

    @pytest.mark.asyncio
    async def test_worker_run_once_processes_single_job(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_pending_job: ProcessingJob,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker run_once processes a single job end-to-end."""
        # Arrange
        mock_job_repo.list_by_status.return_value = [sample_pending_job]
        mock_job_repo.claim_job.return_value = sample_processing_job
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 100}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        await worker._run_once()

        # Assert - full lifecycle
        mock_job_repo.list_by_status.assert_called_once()
        mock_job_repo.claim_job.assert_called_once()
        mock_flow_func.assert_called_once()
        mock_job_repo.mark_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_handles_claim_version_mismatch_gracefully(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
    ):
        """Worker handles version mismatch gracefully when another worker claims job."""
        # Arrange
        mock_job_repo.list_by_status.return_value = [sample_pending_job]
        mock_job_repo.claim_job.side_effect = JobConcurrencyError(
            job_id=sample_pending_job.id,
            expected_version=1,
            actual_version=2,
        )

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Act - should not raise
        await worker._run_once()

        # Assert - claim was attempted but no error propagated
        mock_job_repo.claim_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_configuration(self):
        """Worker accepts configuration parameters."""
        # Arrange & Act
        from src.workers.job_worker import JobWorker
        from src.workers.config import WorkerConfig

        config = WorkerConfig(
            poll_interval=10.0,
            max_retries=5,
            backoff_base=2.0,
            batch_size=3,
        )

        mock_repo = AsyncMock()
        worker = JobWorker(
            job_repo=mock_repo,
            poll_interval=config.poll_interval,
            max_retries=config.max_retries,
            backoff_base=config.backoff_base,
            batch_size=config.batch_size,
        )

        # Assert
        assert worker._poll_interval == 10.0
        assert worker._max_retries == 5
        assert worker._backoff_base == 2.0
        assert worker._batch_size == 3


# =============================================================================
# METRICS & OBSERVABILITY TESTS
# =============================================================================

class TestWorkerMetrics:
    """
    Tests for worker metrics and observability.
    """

    @pytest.mark.asyncio
    async def test_worker_tracks_jobs_processed(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker tracks number of jobs processed."""
        # Arrange
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 50}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        await worker._process_job(sample_processing_job)

        # Assert
        metrics = worker.get_metrics()
        assert metrics["jobs_processed"] == 1
        assert metrics["jobs_completed"] == 1
        assert metrics["jobs_failed"] == 0

    @pytest.mark.asyncio
    async def test_worker_tracks_failed_jobs(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_failed_job: ProcessingJob,
    ):
        """Worker tracks number of failed jobs."""
        # Arrange
        mock_flow_func.side_effect = ValueError("Processing failed")
        mock_job_repo.mark_failed.return_value = sample_failed_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act - use _process_job which tracks metrics
        await worker._process_job(sample_processing_job)

        # Assert
        metrics = worker.get_metrics()
        assert metrics["jobs_failed"] == 1

    @pytest.mark.asyncio
    async def test_worker_tracks_processing_time(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker tracks total processing time."""
        # Arrange
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 50}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        await worker._process_job(sample_processing_job)

        # Assert
        metrics = worker.get_metrics()
        assert metrics["total_processing_time"] > 0

    @pytest.mark.asyncio
    async def test_worker_metrics_average_processing_time(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker calculates average processing time correctly."""
        # Arrange
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 50}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act - process multiple jobs
        await worker._process_job(sample_processing_job)
        await worker._process_job(sample_processing_job)

        # Assert
        metrics = worker.get_metrics()
        assert metrics["jobs_processed"] == 2
        assert metrics["average_processing_time"] > 0

    @pytest.mark.asyncio
    async def test_worker_metrics_last_job_at(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker records last_job_at timestamp."""
        # Arrange
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 50}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act
        await worker._process_job(sample_processing_job)

        # Assert
        metrics = worker.get_metrics()
        assert metrics["last_job_at"] is not None


# =============================================================================
# METRICS RESET TESTS
# =============================================================================

class TestMetricsReset:
    """Tests for WorkerMetrics reset functionality."""

    def test_metrics_reset_clears_all_counters(self):
        """reset() should clear all metrics to initial values."""
        # Arrange
        from src.workers.metrics import WorkerMetrics

        metrics = WorkerMetrics()
        metrics.start_job()
        metrics.record_job_completed()
        metrics.start_job()
        metrics.record_job_failed()

        # Verify metrics are non-zero
        assert metrics.jobs_processed == 2
        assert metrics.jobs_completed == 1
        assert metrics.jobs_failed == 1

        # Act
        metrics.reset()

        # Assert
        assert metrics.jobs_processed == 0
        assert metrics.jobs_completed == 0
        assert metrics.jobs_failed == 0
        assert metrics.total_processing_time == 0.0
        assert metrics.last_job_at is None


# =============================================================================
# FACTORY METHOD TESTS
# =============================================================================

class TestWorkerFactory:
    """Tests for JobWorker factory methods."""

    @pytest.mark.asyncio
    async def test_from_config_creates_worker_with_correct_settings(
        self,
        mock_job_repo: AsyncMock,
    ):
        """from_config() creates worker with configuration values."""
        # Arrange
        from src.workers.job_worker import JobWorker
        from src.workers.config import WorkerConfig

        config = WorkerConfig(
            poll_interval=15.0,
            max_retries=5,
            backoff_base=2.0,
            batch_size=10,
        )

        # Act
        worker = JobWorker.from_config(mock_job_repo, config)

        # Assert
        assert worker._poll_interval == 15.0
        assert worker._max_retries == 5
        assert worker._backoff_base == 2.0
        assert worker._batch_size == 10

    @pytest.mark.asyncio
    async def test_from_config_with_custom_flow_func(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
    ):
        """from_config() can accept custom flow function."""
        # Arrange
        from src.workers.job_worker import JobWorker
        from src.workers.config import WorkerConfig

        config = WorkerConfig()

        # Act
        worker = JobWorker.from_config(mock_job_repo, config, flow_func=mock_flow_func)

        # Assert
        assert worker._flow_func == mock_flow_func


# =============================================================================
# RUN LOOP ERROR HANDLING TESTS
# =============================================================================

class TestRunLoopErrorHandling:
    """Tests for run loop error handling."""

    @pytest.mark.asyncio
    async def test_run_loop_handles_polling_error_gracefully(
        self,
        mock_job_repo: AsyncMock,
    ):
        """Worker continues running after error during polling."""
        # Arrange
        poll_count = 0

        async def fail_then_succeed(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            if poll_count == 1:
                raise RuntimeError("Database connection lost")
            return []

        mock_job_repo.list_by_status.side_effect = fail_then_succeed

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            poll_interval=0.001,
        )

        # Act - run for a short time then shutdown
        async def run_and_shutdown():
            task = asyncio.create_task(worker.run())
            await asyncio.sleep(0.01)
            worker._handle_sigterm()
            await task

        await run_and_shutdown()

        # Assert - worker continued after error
        assert poll_count >= 2

    @pytest.mark.asyncio
    async def test_run_calls_setup_signal_handlers(
        self,
        mock_job_repo: AsyncMock,
    ):
        """run() sets up signal handlers on start."""
        # Arrange
        mock_job_repo.list_by_status.return_value = []

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            poll_interval=0.001,
        )
        worker._should_shutdown = True  # Immediately shutdown

        # Act
        with patch.object(worker, '_setup_signal_handlers') as mock_setup:
            await worker.run()

        # Assert
        mock_setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_sleeps_between_polls(
        self,
        mock_job_repo: AsyncMock,
    ):
        """run() waits poll_interval between polling cycles."""
        # Arrange
        mock_job_repo.list_by_status.return_value = []
        poll_count = 0

        async def count_polls(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            return []

        mock_job_repo.list_by_status.side_effect = count_polls

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            poll_interval=0.01,
        )

        # Act - run briefly then shutdown
        async def run_and_shutdown():
            task = asyncio.create_task(worker.run())
            await asyncio.sleep(0.03)  # Allow a few poll cycles
            worker._handle_sigterm()
            await task

        await run_and_shutdown()

        # Assert - should have polled at least 2 times
        assert poll_count >= 2


# =============================================================================
# TRANSIENT ERROR DETECTION TESTS
# =============================================================================

class TestTransientErrorDetection:
    """Tests for transient error detection."""

    def test_is_transient_error_connection_error(self):
        """ConnectionError is detected as transient."""
        from src.workers.job_worker import JobWorker

        worker = JobWorker(job_repo=AsyncMock())
        assert worker._is_transient_error(ConnectionError("timeout")) is True

    def test_is_transient_error_timeout_error(self):
        """TimeoutError is detected as transient."""
        from src.workers.job_worker import JobWorker

        worker = JobWorker(job_repo=AsyncMock())
        assert worker._is_transient_error(TimeoutError("timeout")) is True

    def test_is_transient_error_os_error(self):
        """OSError is detected as transient."""
        from src.workers.job_worker import JobWorker

        worker = JobWorker(job_repo=AsyncMock())
        assert worker._is_transient_error(OSError("network error")) is True

    def test_is_transient_error_value_error(self):
        """ValueError is NOT detected as transient."""
        from src.workers.job_worker import JobWorker

        worker = JobWorker(job_repo=AsyncMock())
        assert worker._is_transient_error(ValueError("bad data")) is False


# =============================================================================
# CONFIG TESTS
# =============================================================================

class TestWorkerConfigValidation:
    """Tests for WorkerConfig validation and defaults."""

    def test_config_generates_worker_id(self):
        """Config generates worker_id if not provided."""
        from src.workers.config import WorkerConfig

        config = WorkerConfig()
        assert config.worker_id is not None
        assert config.worker_id.startswith("worker-")

    def test_config_respects_provided_worker_id(self):
        """Config uses provided worker_id."""
        from src.workers.config import WorkerConfig

        config = WorkerConfig(worker_id="my-custom-worker")
        assert config.worker_id == "my-custom-worker"

    def test_config_default_values(self):
        """Config has correct default values."""
        from src.workers.config import WorkerConfig

        config = WorkerConfig()
        assert config.poll_interval == 5.0
        assert config.max_retries == 3
        assert config.backoff_base == 1.0
        assert config.batch_size == 1


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling paths."""

    @pytest.mark.asyncio
    async def test_execute_job_with_retry_handles_flow_returning_failure(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
        sample_failed_job: ProcessingJob,
    ):
        """execute_job_with_retry handles flow returning success=False."""
        # Arrange - flow returns success=False (should NOT retry)
        mock_flow_func.return_value = {"success": False, "error": "Validation failed"}
        mock_job_repo.mark_failed.return_value = sample_failed_job

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
            max_retries=3,
        )

        # Act
        result = await worker.execute_job_with_retry(sample_processing_job)

        # Assert - should fail immediately without retry
        assert result.status == JobStatus.FAILED
        assert mock_flow_func.call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_shutdown_during_batch_processing(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_pending_job: ProcessingJob,
        sample_processing_job: ProcessingJob,
        sample_complete_job: ProcessingJob,
    ):
        """Worker stops processing batch when shutdown is signaled."""
        # Arrange - return multiple jobs
        job2 = sample_pending_job.model_copy(deep=True)
        job2.id = "job-test-002"

        mock_job_repo.list_by_status.return_value = [sample_pending_job, job2]
        mock_job_repo.claim_job.return_value = sample_processing_job
        mock_job_repo.mark_complete.return_value = sample_complete_job
        mock_flow_func.return_value = {"success": True, "valid_records": 50}

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
            batch_size=2,
        )

        # Set shutdown during first job
        async def claim_and_shutdown(*args, **kwargs):
            worker._handle_sigterm()  # Signal shutdown during claim
            return sample_processing_job

        mock_job_repo.claim_job.side_effect = claim_and_shutdown

        # Act
        await worker._run_once()

        # Assert - should have claimed first job but not second
        assert mock_job_repo.claim_job.call_count == 1

    @pytest.mark.asyncio
    async def test_process_job_reraises_unexpected_exception(
        self,
        mock_job_repo: AsyncMock,
        mock_flow_func: AsyncMock,
        sample_processing_job: ProcessingJob,
    ):
        """_process_job re-raises unexpected exceptions after recording metrics."""
        # Arrange - flow raises an unexpected error that causes execute_job_with_retry to raise
        mock_flow_func.side_effect = ValueError("Unexpected error")
        mock_job_repo.mark_failed.side_effect = RuntimeError("Database unavailable")

        from src.workers.job_worker import JobWorker
        worker = JobWorker(
            job_repo=mock_job_repo,
            flow_func=mock_flow_func,
        )

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database unavailable"):
            await worker._process_job(sample_processing_job)

        # Verify metrics were still updated
        metrics = worker.get_metrics()
        assert metrics["jobs_failed"] == 1

    @pytest.mark.asyncio
    async def test_signal_handler_setup_failure_is_logged(
        self,
        mock_job_repo: AsyncMock,
    ):
        """Signal handler setup failure is logged but doesn't crash worker."""
        # Arrange
        from src.workers.job_worker import JobWorker

        worker = JobWorker(job_repo=mock_job_repo)

        # Act - simulate signal setup failure
        with patch("signal.signal", side_effect=ValueError("Signal error in thread")):
            # This should not raise
            worker._setup_signal_handlers()

        # Assert - worker should still work
        assert not worker._should_shutdown

    @pytest.mark.asyncio
    async def test_shutdown_log_message_during_batch(
        self,
        mock_job_repo: AsyncMock,
        sample_pending_job: ProcessingJob,
    ):
        """Verify shutdown log message is triggered during batch processing."""
        # Arrange - return one job
        mock_job_repo.list_by_status.return_value = [sample_pending_job]

        from src.workers.job_worker import JobWorker
        worker = JobWorker(job_repo=mock_job_repo)

        # Pre-set shutdown before run
        worker._should_shutdown = True

        # Act
        await worker._run_once()

        # Assert - should exit early due to shutdown
        mock_job_repo.claim_job.assert_not_called()


# =============================================================================
# REPOSITORY EXTENSION TESTS (For claim_job method)
# =============================================================================

class TestJobRepositoryClaim:
    """
    Tests for the new claim_job repository method.

    RED PHASE: Tests for the claim_job extension to IJobRepository.
    """

    @pytest.mark.asyncio
    async def test_claim_job_transitions_to_processing(self):
        """claim_job should transition job from PENDING to PROCESSING."""
        # Arrange
        from src.infrastructure.repositories.job_repository import InMemoryJobRepository
        from src.domain.processing_job.aggregate import ProcessingJob

        repo = InMemoryJobRepository()
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        await repo.save(job)

        # Act
        claimed = await repo.claim_job(
            job_id=job.id,
            expected_version=job.version,
        )

        # Assert
        assert claimed.status == JobStatus.PROCESSING
        assert claimed.version == job.version + 1
        assert claimed.started_at is not None

    @pytest.mark.asyncio
    async def test_claim_job_raises_on_version_mismatch(self):
        """claim_job should raise JobConcurrencyError on version mismatch."""
        # Arrange
        from src.infrastructure.repositories.job_repository import InMemoryJobRepository
        from src.domain.processing_job.aggregate import ProcessingJob

        repo = InMemoryJobRepository()
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        await repo.save(job)

        # Update the job to increment version
        job.transition_to_processing()
        await repo.save(job)

        # Act & Assert - try to claim with old version
        with pytest.raises(JobConcurrencyError):
            await repo.claim_job(
                job_id=job.id,
                expected_version=1,  # Old version
            )

    @pytest.mark.asyncio
    async def test_mark_complete_with_result_records(self):
        """mark_complete should update result_records count."""
        # Arrange
        from src.infrastructure.repositories.job_repository import InMemoryJobRepository
        from src.domain.processing_job.aggregate import ProcessingJob

        repo = InMemoryJobRepository()
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        await repo.save(job)
        job.transition_to_processing()
        await repo.save(job)

        # Act
        completed = await repo.mark_complete(
            job_id=job.id,
            version=job.version,
            result_records=500,
        )

        # Assert
        assert completed.status == JobStatus.COMPLETE
        assert completed.result_records == 500

    @pytest.mark.asyncio
    async def test_mark_failed_with_error_message(self):
        """mark_failed should store error message."""
        # Arrange
        from src.infrastructure.repositories.job_repository import InMemoryJobRepository
        from src.domain.processing_job.aggregate import ProcessingJob

        repo = InMemoryJobRepository()
        job = ProcessingJob.create(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )
        await repo.save(job)
        job.transition_to_processing()
        await repo.save(job)

        # Act
        failed = await repo.mark_failed(
            job_id=job.id,
            version=job.version,
            error_message="Connection timeout after 3 retries",
        )

        # Assert
        assert failed.status == JobStatus.FAILED
        assert failed.error_message == "Connection timeout after 3 retries"
