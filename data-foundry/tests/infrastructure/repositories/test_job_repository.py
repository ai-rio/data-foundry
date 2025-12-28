"""
Tests for Job Repository Implementations

TDD tests for InMemoryJobRepository (and structure for PostgreSQL implementation).
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.exceptions import (
    JobNotFoundError,
    JobConcurrencyError,
    InvalidStateTransition,
)
from src.infrastructure.repositories.job_repository import (
    InMemoryJobRepository,
    JobRepository,
    ProcessingJobDB,
)


@pytest.fixture
def repo():
    """Create fresh in-memory repository."""
    return InMemoryJobRepository()


@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
    return ProcessingJob.create(
        tenant_id="tenant-123",
        file_name="data.csv",
        file_size=1024,
        complexity_tier="simple",
    )


class TestInMemoryJobRepositorySave:
    """Tests for InMemoryJobRepository.save()."""

    @pytest.mark.asyncio
    async def test_save_new_job(self, repo, sample_job):
        """Should save a new job."""
        saved = await repo.save(sample_job)

        assert saved.id == sample_job.id
        assert saved.tenant_id == sample_job.tenant_id

    @pytest.mark.asyncio
    async def test_save_returns_same_job(self, repo, sample_job):
        """Should return the saved job."""
        saved = await repo.save(sample_job)

        assert saved is sample_job

    @pytest.mark.asyncio
    async def test_save_update_existing(self, repo, sample_job):
        """Should update existing job."""
        await repo.save(sample_job)

        sample_job.transition_to_processing()
        updated = await repo.save(sample_job)

        assert updated.status == JobStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_save_optimistic_locking(self, repo, sample_job):
        """Should enforce version checking."""
        await repo.save(sample_job)

        # Create a stale copy with old version
        stale_job = ProcessingJob.create(
            tenant_id=sample_job.tenant_id,
            file_name=sample_job.file_name,
            file_size=sample_job.file_size,
        )
        # Override ID to match but version is same (both are version 1)
        stale_job = ProcessingJob(
            id=sample_job.id,
            tenant_id=sample_job.tenant_id,
            version=sample_job.version,  # Same version as saved
            file_name=sample_job.file_name,
            file_size=sample_job.file_size,
            file_key=None,
            complexity_tier="simple",
            status=JobStatus.PENDING,
            error_message=None,
            retry_count=0,
            max_retries=3,
            created_at=sample_job.created_at,
            started_at=None,
            completed_at=None,
            updated_at=sample_job.updated_at,
            estimated_cost=sample_job.estimated_cost,
            actual_cost=None,
            result_records=None,
            result_url=None,
            metadata={},
        )

        # First update
        sample_job.transition_to_processing()  # This increments version to 2
        await repo.save(sample_job)

        # Now try to save stale job with version 1 expecting version 0
        stale_job.transition_to_processing()  # version becomes 2, expects 1 in repo

        with pytest.raises(JobConcurrencyError):
            await repo.save(stale_job)


class TestInMemoryJobRepositoryGet:
    """Tests for InMemoryJobRepository.get()."""

    @pytest.mark.asyncio
    async def test_get_existing(self, repo, sample_job):
        """Should retrieve existing job."""
        await repo.save(sample_job)

        retrieved = await repo.get(sample_job.id)

        assert retrieved is not None
        assert retrieved.id == sample_job.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo):
        """Should return None for non-existent job."""
        retrieved = await repo.get("nonexistent-id")

        assert retrieved is None


class TestInMemoryJobRepositoryGetById:
    """Tests for InMemoryJobRepository.get_by_id()."""

    @pytest.mark.asyncio
    async def test_get_by_id_existing(self, repo, sample_job):
        """Should retrieve existing job."""
        await repo.save(sample_job)

        retrieved = await repo.get_by_id(sample_job.id)

        assert retrieved.id == sample_job.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo):
        """Should raise JobNotFoundError for non-existent job."""
        with pytest.raises(JobNotFoundError):
            await repo.get_by_id("nonexistent-id")


class TestInMemoryJobRepositoryDelete:
    """Tests for InMemoryJobRepository.delete()."""

    @pytest.mark.asyncio
    async def test_delete_existing(self, repo, sample_job):
        """Should delete existing job."""
        await repo.save(sample_job)

        result = await repo.delete(sample_job.id)

        assert result is True
        assert await repo.get(sample_job.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, repo):
        """Should return False for non-existent job."""
        result = await repo.delete("nonexistent-id")

        assert result is False


class TestInMemoryJobRepositoryListByTenant:
    """Tests for InMemoryJobRepository.list_by_tenant()."""

    @pytest.mark.asyncio
    async def test_list_by_tenant(self, repo):
        """Should list jobs for a tenant."""
        for i in range(3):
            job = ProcessingJob.create(
                tenant_id="tenant-1",
                file_name=f"file{i}.csv",
                file_size=1024,
            )
            await repo.save(job)

        # Add job for different tenant
        other = ProcessingJob.create(
            tenant_id="tenant-2",
            file_name="other.csv",
            file_size=1024,
        )
        await repo.save(other)

        jobs = await repo.list_by_tenant("tenant-1")

        assert len(jobs) == 3
        assert all(j.tenant_id == "tenant-1" for j in jobs)

    @pytest.mark.asyncio
    async def test_list_by_tenant_with_status(self, repo):
        """Should filter by status."""
        job1 = ProcessingJob.create("tenant-1", "file1.csv", 1024)
        job2 = ProcessingJob.create("tenant-1", "file2.csv", 1024)
        await repo.save(job1)
        await repo.save(job2)

        job1.transition_to_processing()
        await repo.save(job1)

        pending = await repo.list_by_tenant("tenant-1", status=JobStatus.PENDING)
        processing = await repo.list_by_tenant("tenant-1", status=JobStatus.PROCESSING)

        assert len(pending) == 1
        assert len(processing) == 1

    @pytest.mark.asyncio
    async def test_list_by_tenant_pagination(self, repo):
        """Should support pagination."""
        for i in range(5):
            job = ProcessingJob.create("tenant-1", f"file{i}.csv", 1024)
            await repo.save(job)

        page1 = await repo.list_by_tenant("tenant-1", limit=2, offset=0)
        page2 = await repo.list_by_tenant("tenant-1", limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_list_by_tenant_ordered_by_created(self, repo):
        """Should order by created_at descending."""
        jobs = []
        for i in range(3):
            job = ProcessingJob.create("tenant-1", f"file{i}.csv", 1024)
            await repo.save(job)
            jobs.append(job)

        result = await repo.list_by_tenant("tenant-1")

        # Most recent first
        assert result[0].created_at >= result[1].created_at
        assert result[1].created_at >= result[2].created_at


class TestInMemoryJobRepositoryListByStatus:
    """Tests for InMemoryJobRepository.list_by_status()."""

    @pytest.mark.asyncio
    async def test_list_by_status(self, repo):
        """Should list jobs by status."""
        job1 = ProcessingJob.create("tenant-1", "file1.csv", 1024)
        job2 = ProcessingJob.create("tenant-2", "file2.csv", 1024)
        await repo.save(job1)
        await repo.save(job2)

        job1.transition_to_processing()
        await repo.save(job1)

        processing = await repo.list_by_status(JobStatus.PROCESSING)
        pending = await repo.list_by_status(JobStatus.PENDING)

        assert len(processing) == 1
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_list_by_status_pagination(self, repo):
        """Should support pagination."""
        for i in range(5):
            job = ProcessingJob.create("tenant-1", f"file{i}.csv", 1024)
            await repo.save(job)

        page1 = await repo.list_by_status(JobStatus.PENDING, limit=2, offset=0)
        page2 = await repo.list_by_status(JobStatus.PENDING, limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2


class TestInMemoryJobRepositoryCountByTenant:
    """Tests for InMemoryJobRepository.count_by_tenant()."""

    @pytest.mark.asyncio
    async def test_count_by_tenant(self, repo):
        """Should count jobs for tenant."""
        for i in range(3):
            job = ProcessingJob.create("tenant-1", f"file{i}.csv", 1024)
            await repo.save(job)

        count = await repo.count_by_tenant("tenant-1")

        assert count == 3

    @pytest.mark.asyncio
    async def test_count_by_tenant_with_status(self, repo):
        """Should count with status filter."""
        job1 = ProcessingJob.create("tenant-1", "file1.csv", 1024)
        job2 = ProcessingJob.create("tenant-1", "file2.csv", 1024)
        await repo.save(job1)
        await repo.save(job2)

        job1.transition_to_processing()
        await repo.save(job1)

        pending_count = await repo.count_by_tenant("tenant-1", status=JobStatus.PENDING)
        processing_count = await repo.count_by_tenant("tenant-1", status=JobStatus.PROCESSING)

        assert pending_count == 1
        assert processing_count == 1


class TestInMemoryJobRepositoryStaleJobs:
    """Tests for InMemoryJobRepository.get_stale_processing_jobs()."""

    @pytest.mark.asyncio
    async def test_get_stale_processing_jobs(self, repo):
        """Should find stale processing jobs."""
        job = ProcessingJob.create("tenant-1", "file.csv", 1024)
        await repo.save(job)
        job.transition_to_processing()
        # Manually set started_at to the past
        job.started_at = datetime.utcnow() - timedelta(hours=2)
        await repo.save(job)

        cutoff = datetime.utcnow() - timedelta(hours=1)
        stale = await repo.get_stale_processing_jobs(older_than=cutoff)

        assert len(stale) == 1
        assert stale[0].id == job.id

    @pytest.mark.asyncio
    async def test_get_stale_excludes_recent(self, repo):
        """Should exclude recently started jobs."""
        job = ProcessingJob.create("tenant-1", "file.csv", 1024)
        await repo.save(job)
        job.transition_to_processing()
        await repo.save(job)

        cutoff = datetime.utcnow() - timedelta(hours=1)
        stale = await repo.get_stale_processing_jobs(older_than=cutoff)

        assert len(stale) == 0

    @pytest.mark.asyncio
    async def test_get_stale_excludes_non_processing(self, repo):
        """Should only include PROCESSING jobs."""
        job = ProcessingJob.create("tenant-1", "file.csv", 1024)
        await repo.save(job)
        # Job is PENDING, not PROCESSING

        cutoff = datetime.utcnow() + timedelta(hours=1)  # Future cutoff
        stale = await repo.get_stale_processing_jobs(older_than=cutoff)

        assert len(stale) == 0


class TestInMemoryJobRepositoryUpdateStatus:
    """Tests for InMemoryJobRepository.update_status()."""

    @pytest.mark.asyncio
    async def test_update_status_to_processing(self, repo, sample_job):
        """Should update status to PROCESSING."""
        await repo.save(sample_job)

        updated = await repo.update_status(sample_job.id, JobStatus.PROCESSING)

        assert updated.status == JobStatus.PROCESSING
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_update_status_to_failed(self, repo, sample_job):
        """Should update status to FAILED with error message."""
        await repo.save(sample_job)
        sample_job.transition_to_processing()
        await repo.save(sample_job)

        updated = await repo.update_status(
            sample_job.id,
            JobStatus.FAILED,
            error_message="Processing error",
        )

        assert updated.status == JobStatus.FAILED
        assert updated.error_message == "Processing error"

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition(self, repo, sample_job):
        """Should raise InvalidStateTransition for invalid transition."""
        await repo.save(sample_job)

        with pytest.raises(InvalidStateTransition):
            # PENDING -> COMPLETE is not allowed
            await repo.update_status(sample_job.id, JobStatus.COMPLETE)


class TestInMemoryJobRepositoryClear:
    """Tests for InMemoryJobRepository.clear()."""

    @pytest.mark.asyncio
    async def test_clear(self, repo, sample_job):
        """Should clear all jobs."""
        await repo.save(sample_job)

        repo.clear()

        assert await repo.get(sample_job.id) is None


class TestProcessingJobDB:
    """Tests for ProcessingJobDB SQLModel."""

    def test_create_db_model(self):
        """Should create database model with defaults."""
        db_job = ProcessingJobDB(
            id="job-123",
            tenant_id="tenant-456",
            file_name="data.csv",
            file_size=1024,
        )

        assert db_job.id == "job-123"
        assert db_job.tenant_id == "tenant-456"
        assert db_job.status == "pending"
        assert db_job.version == 1
        assert db_job.retry_count == 0
        assert db_job.max_retries == 3

    def test_db_model_fields(self):
        """Should have all required fields."""
        db_job = ProcessingJobDB(
            id="job-123",
            tenant_id="tenant-456",
            file_name="data.csv",
            file_size=1024,
            file_key="tenant/job/data.csv",
            complexity_tier="complex",
            status="processing",
            error_message="Error occurred",
            retry_count=1,
            estimated_cost="1.50",
            actual_cost="1.25",
            result_records=1000,
            result_url="https://example.com/results",
            metadata_json='{"key": "value"}',
        )

        assert db_job.file_key == "tenant/job/data.csv"
        assert db_job.complexity_tier == "complex"
        assert db_job.estimated_cost == "1.50"
        assert db_job.actual_cost == "1.25"
