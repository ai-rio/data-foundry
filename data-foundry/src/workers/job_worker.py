"""
Background Job Worker

Processes data ingestion jobs from PostgreSQL queue.

This worker:
1. Polls for PENDING jobs
2. Claims jobs with optimistic locking (prevents duplicate processing)
3. Executes data_ingestion_flow() synchronously
4. Updates job status to COMPLETE/FAILED
5. Implements retry logic with exponential backoff
6. Handles graceful shutdown on SIGTERM

SOLID Principles:
- Single Responsibility: Worker only handles job polling and execution
- Open/Closed: Easy to extend with different flow functions
- Liskov Substitution: Works with any IJobRepository implementation
- Interface Segregation: Minimal interface dependencies
- Dependency Inversion: All dependencies injected
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Callable, Awaitable, Any, Dict, List, Optional, TYPE_CHECKING

from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.repository import IJobRepository
from src.domain.processing_job.exceptions import JobConcurrencyError
from src.workers.metrics import WorkerMetrics

if TYPE_CHECKING:
    from src.workers.config import WorkerConfig

logger = logging.getLogger(__name__)

# Default flow function - can be overridden via dependency injection
_DEFAULT_FLOW_FUNC = None  # Will be imported lazily to avoid circular imports


def _get_default_flow_func():
    """Lazily import the default flow function to avoid circular imports."""
    global _DEFAULT_FLOW_FUNC
    if _DEFAULT_FLOW_FUNC is None:
        from src.tasks.ingestion import data_ingestion_flow
        _DEFAULT_FLOW_FUNC = data_ingestion_flow
    return _DEFAULT_FLOW_FUNC


# Transient errors that should trigger retry
TRANSIENT_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
    asyncio.TimeoutError,
)

# Exponential backoff multiplier (4^attempt gives 1, 4, 16, 64, ...)
BACKOFF_MULTIPLIER = 4


class JobWorker:
    """
    Background worker that processes data ingestion jobs.

    The worker implements a polling loop that:
    1. Polls for PENDING jobs from the database
    2. Claims a job using optimistic locking (version check)
    3. Executes the data_ingestion_flow() function
    4. Updates job status based on execution result
    5. Handles graceful shutdown on SIGTERM

    Retry Logic:
    - Transient errors (ConnectionError, TimeoutError) trigger retry
    - Exponential backoff: base * 4^attempt (1s, 4s, 16s)
    - Non-transient errors fail immediately

    Usage:
        worker = JobWorker(
            job_repo=repository,
            flow_func=data_ingestion_flow,
            poll_interval=5.0,
            max_retries=3,
        )
        await worker.run()
    """

    def __init__(
        self,
        job_repo: IJobRepository,
        flow_func: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
        poll_interval: float = 5.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        batch_size: int = 1,
    ):
        """
        Initialize the job worker.

        Args:
            job_repo: Repository for job persistence
            flow_func: Data ingestion flow function (defaults to data_ingestion_flow)
            poll_interval: Seconds between polling for new jobs
            max_retries: Maximum retry attempts for transient failures
            backoff_base: Base for exponential backoff (seconds)
            batch_size: Number of jobs to poll at once
        """
        self._job_repo = job_repo
        self._flow_func = flow_func or _get_default_flow_func()
        self._poll_interval = poll_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._batch_size = batch_size

        # Shutdown flag
        self._should_shutdown = False

        # Metrics
        self._metrics = WorkerMetrics()

    @classmethod
    def from_config(
        cls,
        job_repo: IJobRepository,
        config: WorkerConfig,
        flow_func: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
    ) -> JobWorker:
        """
        Create a JobWorker from a WorkerConfig instance.

        This factory method simplifies worker creation from configuration.

        Args:
            job_repo: Repository for job persistence
            config: WorkerConfig instance with worker settings
            flow_func: Optional flow function override

        Returns:
            Configured JobWorker instance

        Example:
            config = WorkerConfig()  # Loads from environment
            worker = JobWorker.from_config(job_repo, config)
            await worker.run()
        """
        return cls(
            job_repo=job_repo,
            flow_func=flow_func,
            poll_interval=config.poll_interval,
            max_retries=config.max_retries,
            backoff_base=config.backoff_base,
            batch_size=config.batch_size,
        )

    # -----------------------------------------------------------------
    # Public Methods
    # -----------------------------------------------------------------

    async def run(self) -> None:
        """
        Main worker loop.

        Polls for jobs and processes them until shutdown signal received.
        """
        logger.info("JobWorker starting...")
        self._setup_signal_handlers()

        while not self._should_shutdown:
            try:
                await self._run_once()
            except Exception as e:
                logger.error(f"Worker error during polling: {e}", exc_info=True)

            # Wait before next poll (unless shutting down)
            if not self._should_shutdown:
                await asyncio.sleep(self._poll_interval)

        logger.info("JobWorker shutdown complete")

    async def poll_for_pending_jobs(self) -> List[ProcessingJob]:
        """
        Poll database for PENDING jobs.

        Returns:
            List of PENDING jobs to process
        """
        jobs = await self._job_repo.list_by_status(
            status=JobStatus.PENDING,
            limit=self._batch_size,
        )
        logger.debug(f"Polled {len(jobs)} pending jobs")
        return jobs

    async def claim_job(self, job: ProcessingJob) -> ProcessingJob:
        """
        Claim a job by updating status to PROCESSING with version check.

        Uses optimistic locking to prevent duplicate processing.

        Args:
            job: Job to claim

        Returns:
            Claimed job in PROCESSING state

        Raises:
            JobConcurrencyError: If another worker already claimed the job
        """
        claimed = await self._job_repo.claim_job(
            job_id=job.id,
            expected_version=job.version,
        )
        logger.info(f"Claimed job {job.id} (version {claimed.version})")
        return claimed

    async def execute_job(self, job: ProcessingJob) -> ProcessingJob:
        """
        Execute the data ingestion flow for a job.

        Args:
            job: Job to execute (must be in PROCESSING state)

        Returns:
            Updated job in COMPLETE or FAILED state
        """
        try:
            # Execute the flow function with centralized parameters
            params = self._build_flow_parameters(job)
            result = await self._flow_func(**params)

            # Handle flow result
            return await self._handle_flow_result(job, result)

        except Exception as e:
            logger.error(f"Job {job.id} execution failed: {e}", exc_info=True)
            return await self._job_repo.mark_failed(
                job_id=job.id,
                version=job.version,
                error_message=str(e),
            )

    async def _handle_flow_result(
        self, job: ProcessingJob, result: Any
    ) -> ProcessingJob:
        """
        Handle the result from flow function execution.

        Args:
            job: Job that was executed
            result: Result from flow function

        Returns:
            Updated job in COMPLETE or FAILED state
        """
        # Check if flow returned success=False
        if isinstance(result, dict) and not result.get("success", True):
            error_msg = result.get("error", "Flow returned success=False")
            logger.warning(f"Job {job.id} flow returned failure: {error_msg}")
            return await self._job_repo.mark_failed(
                job_id=job.id,
                version=job.version,
                error_message=error_msg,
            )

        # Extract result records
        result_records = 0
        if isinstance(result, dict):
            result_records = result.get("valid_records", 0)

        # Mark complete
        completed = await self._job_repo.mark_complete(
            job_id=job.id,
            version=job.version,
            result_records=result_records,
        )
        logger.info(f"Job {job.id} completed with {result_records} records")
        return completed

    async def execute_job_with_retry(self, job: ProcessingJob) -> ProcessingJob:
        """
        Execute job with exponential backoff retry for transient failures.

        Backoff formula: backoff_base * 4^attempt
        - Attempt 0: 1s (first retry after first failure)
        - Attempt 1: 4s
        - Attempt 2: 16s

        Args:
            job: Job to execute (must be in PROCESSING state)

        Returns:
            Updated job in COMPLETE or FAILED state
        """
        last_error: Optional[Exception] = None
        params = self._build_flow_parameters(job)

        for attempt in range(self._max_retries):
            try:
                # Try to execute the flow
                result = await self._flow_func(**params)

                # Check if flow returned success=False (non-transient, don't retry)
                if isinstance(result, dict) and not result.get("success", True):
                    error_msg = result.get("error", "Flow returned success=False")
                    return await self._job_repo.mark_failed(
                        job_id=job.id,
                        version=job.version,
                        error_message=error_msg,
                    )

                # Success - mark complete
                result_records = 0
                if isinstance(result, dict):
                    result_records = result.get("valid_records", 0)

                return await self._job_repo.mark_complete(
                    job_id=job.id,
                    version=job.version,
                    result_records=result_records,
                )

            except TRANSIENT_ERRORS as e:
                # Transient error - retry with backoff
                last_error = e
                await self._handle_transient_error(job, e, attempt)

            except Exception as e:
                # Non-transient error - fail immediately
                logger.error(f"Job {job.id} non-transient error: {e}", exc_info=True)
                return await self._job_repo.mark_failed(
                    job_id=job.id,
                    version=job.version,
                    error_message=str(e),
                )

        # All retries exhausted
        error_message = f"Retries exhausted ({self._max_retries} attempts): {last_error}"
        return await self._job_repo.mark_failed(
            job_id=job.id,
            version=job.version,
            error_message=error_message,
        )

    async def _handle_transient_error(
        self, job: ProcessingJob, error: Exception, attempt: int
    ) -> None:
        """
        Handle a transient error during job execution.

        Logs the error and sleeps for the appropriate backoff time
        if there are retries remaining.

        Args:
            job: Job being executed
            error: The transient error that occurred
            attempt: Current attempt number (0-based)
        """
        if attempt < self._max_retries - 1:
            backoff = self._calculate_backoff(attempt)
            logger.warning(
                f"Job {job.id} transient error (attempt {attempt + 1}/{self._max_retries}), "
                f"retrying in {backoff}s: {error}"
            )
            await asyncio.sleep(backoff)
        else:
            logger.error(
                f"Job {job.id} transient error exhausted retries: {error}"
            )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current worker metrics.

        Returns:
            Dictionary with jobs_processed, jobs_completed, jobs_failed, etc.
        """
        return self._metrics.to_dict()

    # -----------------------------------------------------------------
    # Internal Methods
    # -----------------------------------------------------------------

    async def _run_once(self) -> None:
        """
        Run one iteration of the polling loop.

        Polls for jobs and processes them (if not shutting down).
        """
        if self._should_shutdown:
            return

        jobs = await self.poll_for_pending_jobs()

        for job in jobs:
            if self._should_shutdown:
                logger.info("Shutdown requested, not claiming new jobs")
                break

            try:
                claimed = await self.claim_job(job)
                await self._process_job(claimed)
            except JobConcurrencyError:
                # Another worker claimed the job - this is normal
                logger.debug(f"Job {job.id} already claimed by another worker")

    async def _process_job(self, job: ProcessingJob) -> ProcessingJob:
        """
        Process a single job with metrics tracking.

        Args:
            job: Job to process (must be in PROCESSING state)

        Returns:
            Updated job after processing
        """
        self._metrics.start_job()

        try:
            result = await self.execute_job_with_retry(job)

            if result.status == JobStatus.COMPLETE:
                self._metrics.record_job_completed()
            else:
                self._metrics.record_job_failed()

            return result

        except Exception as e:
            self._metrics.record_job_failed()
            logger.error(f"Job {job.id} processing error: {e}", exc_info=True)
            raise

    def _handle_sigterm(self, signum=None, frame=None) -> None:
        """
        Handle SIGTERM signal for graceful shutdown.

        Sets shutdown flag to stop accepting new jobs.
        Current job in progress will be allowed to complete.
        """
        logger.info("SIGTERM received, initiating graceful shutdown...")
        self._should_shutdown = True

    def _setup_signal_handlers(self) -> None:
        """
        Set up signal handlers for graceful shutdown.
        """
        try:
            signal.signal(signal.SIGTERM, self._handle_sigterm)
            signal.signal(signal.SIGINT, self._handle_sigterm)
            logger.debug("Signal handlers registered")
        except Exception as e:
            # Signal handling may not work in all contexts (e.g., threads)
            logger.warning(f"Could not register signal handlers: {e}")

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay for a given attempt number.

        Formula: backoff_base * 4^attempt
        - Attempt 0: base * 1 = 1s (default)
        - Attempt 1: base * 4 = 4s
        - Attempt 2: base * 16 = 16s

        Args:
            attempt: Zero-based attempt number

        Returns:
            Delay in seconds before next retry
        """
        return self._backoff_base * (BACKOFF_MULTIPLIER ** attempt)

    def _build_flow_parameters(self, job: ProcessingJob) -> Dict[str, Any]:
        """
        Build parameters dict for the flow function call.

        Centralizes flow parameter construction for consistency.

        Args:
            job: Job to build parameters for

        Returns:
            Dictionary of parameters for the flow function
        """
        return {
            "data_source": job.file_key,
            "job_id": job.id,
            "tenant_id": job.tenant_id,
            "enable_validation": True,
            "enable_ai_labeling": True,
            "enable_pii_redaction": True,
            "enable_human_review": False,
        }

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Check if an error is transient and should trigger retry.

        Args:
            error: Exception to check

        Returns:
            True if the error is transient, False otherwise
        """
        return isinstance(error, TRANSIENT_ERRORS)
