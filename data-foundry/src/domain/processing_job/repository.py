"""
Processing Job Repository Interface

Abstract interface for job persistence operations.
Follows Repository pattern from DDD.

SOLID Principles:
- Interface Segregation: Only essential CRUD operations exposed
- Dependency Inversion: Application layer depends on this interface
- Liskov Substitution: Postgres, MongoDB, In-Memory implementations can substitute
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List

from .aggregate import ProcessingJob, JobStatus


class IJobRepository(ABC):
    """
    Repository interface for ProcessingJob aggregate.

    This interface abstracts persistence details from the domain.
    Implementations may use PostgreSQL, MongoDB, DynamoDB, etc.

    The repository is responsible for:
    - Persisting and retrieving ProcessingJob aggregates
    - Maintaining aggregate boundaries
    - Handling optimistic concurrency (version checking)
    """

    @abstractmethod
    async def save(self, job: ProcessingJob) -> ProcessingJob:
        """
        Save a job (create or update).

        For new jobs (no existing record), creates a new entry.
        For existing jobs, updates and checks version for optimistic locking.

        Args:
            job: ProcessingJob aggregate to save

        Returns:
            Saved ProcessingJob with updated version

        Raises:
            JobConcurrencyError: If version mismatch (concurrent update)
            JobError: If save fails
        """
        pass

    @abstractmethod
    async def get(self, job_id: str) -> Optional[ProcessingJob]:
        """
        Retrieve a job by ID.

        Args:
            job_id: Unique job identifier

        Returns:
            ProcessingJob if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_by_id(self, job_id: str) -> ProcessingJob:
        """
        Retrieve a job by ID, raising if not found.

        Args:
            job_id: Unique job identifier

        Returns:
            ProcessingJob

        Raises:
            JobNotFoundError: If job doesn't exist
        """
        pass

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """
        Delete a job by ID.

        Args:
            job_id: Unique job identifier

        Returns:
            True if deleted, False if job didn't exist
        """
        pass

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProcessingJob]:
        """
        List jobs for a tenant.

        Args:
            tenant_id: Tenant identifier
            status: Optional status filter
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of ProcessingJob aggregates
        """
        pass

    @abstractmethod
    async def list_by_status(
        self,
        status: JobStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProcessingJob]:
        """
        List jobs by status across all tenants.

        Useful for background workers processing jobs.

        Args:
            status: Status to filter by
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of ProcessingJob aggregates
        """
        pass

    @abstractmethod
    async def count_by_tenant(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
    ) -> int:
        """
        Count jobs for a tenant.

        Args:
            tenant_id: Tenant identifier
            status: Optional status filter

        Returns:
            Count of matching jobs
        """
        pass

    @abstractmethod
    async def get_stale_processing_jobs(
        self,
        older_than: datetime,
        limit: int = 100,
    ) -> List[ProcessingJob]:
        """
        Get jobs stuck in PROCESSING state.

        Used for timeout detection and cleanup.

        Args:
            older_than: Get jobs with started_at before this time
            limit: Maximum number of results

        Returns:
            List of stale ProcessingJob aggregates
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> ProcessingJob:
        """
        Update job status directly.

        This is a convenience method for simple status updates.
        For complex updates, use save() with the full aggregate.

        Args:
            job_id: Job identifier
            status: New status
            error_message: Optional error message (for FAILED status)

        Returns:
            Updated ProcessingJob

        Raises:
            JobNotFoundError: If job doesn't exist
            InvalidStateTransition: If transition is not allowed
        """
        pass

    # -----------------------------------------------------------------
    # Worker-specific methods (Phase 2 Background Worker Support)
    # -----------------------------------------------------------------

    @abstractmethod
    async def claim_job(
        self,
        job_id: str,
        expected_version: int,
    ) -> ProcessingJob:
        """
        Claim a job for processing with optimistic locking.

        Atomically transitions a PENDING job to PROCESSING state
        only if the current version matches expected_version.
        This prevents multiple workers from claiming the same job.

        Args:
            job_id: Job identifier to claim
            expected_version: Expected current version (for optimistic locking)

        Returns:
            Updated ProcessingJob in PROCESSING state with incremented version

        Raises:
            JobNotFoundError: If job doesn't exist
            JobConcurrencyError: If version mismatch (another worker claimed it)
            InvalidStateTransition: If job is not in PENDING state
        """
        pass

    @abstractmethod
    async def mark_complete(
        self,
        job_id: str,
        version: int,
        result_records: int,
        result_url: Optional[str] = None,
    ) -> ProcessingJob:
        """
        Mark a job as COMPLETE with results.

        Updates job status to COMPLETE and records result metadata.

        Args:
            job_id: Job identifier
            version: Current version (for optimistic locking)
            result_records: Number of records processed successfully
            result_url: Optional URL to results

        Returns:
            Updated ProcessingJob in COMPLETE state

        Raises:
            JobNotFoundError: If job doesn't exist
            JobConcurrencyError: If version mismatch
            InvalidStateTransition: If job is not in PROCESSING state
        """
        pass

    @abstractmethod
    async def mark_failed(
        self,
        job_id: str,
        version: int,
        error_message: str,
    ) -> ProcessingJob:
        """
        Mark a job as FAILED with error information.

        Updates job status to FAILED and records error message.

        Args:
            job_id: Job identifier
            version: Current version (for optimistic locking)
            error_message: Description of the failure

        Returns:
            Updated ProcessingJob in FAILED state

        Raises:
            JobNotFoundError: If job doesn't exist
            JobConcurrencyError: If version mismatch
            InvalidStateTransition: If job is not in PROCESSING state
        """
        pass
