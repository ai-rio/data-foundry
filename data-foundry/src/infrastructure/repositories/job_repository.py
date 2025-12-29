"""
Job Repository Implementation

PostgreSQL and In-Memory implementations of IJobRepository.

SOLID Principles:
- Liskov Substitution: Both implementations substitute for IJobRepository
- Single Responsibility: Only handles job persistence
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlmodel import Field, SQLModel

from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.repository import IJobRepository
from src.domain.processing_job.exceptions import (
    JobNotFoundError,
    JobConcurrencyError,
    InvalidStateTransition,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# SQLModel Database Model
# -----------------------------------------------------------------

class ProcessingJobDB(SQLModel, table=True):
    """
    Database model for processing jobs.

    This is the persistence model - separate from the domain aggregate.
    The repository maps between domain and persistence models.
    """

    __tablename__ = "processing_jobs"

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    version: int = Field(default=1)

    # File information
    file_name: str
    file_size: int
    file_key: Optional[str] = None
    complexity_tier: str = "simple"

    # Status
    status: str = "pending"
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Cost
    estimated_cost: str = "0.00"  # Store as string for precision
    actual_cost: Optional[str] = None

    # Results
    result_records: Optional[int] = None
    result_url: Optional[str] = None
    metadata_json: Optional[str] = None  # JSON string for metadata dict


# -----------------------------------------------------------------
# PostgreSQL Repository
# -----------------------------------------------------------------

class JobRepository(IJobRepository):
    """
    PostgreSQL implementation of IJobRepository.

    Uses SQLAlchemy async session for database operations.
    Implements optimistic locking via version field.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize with async session.

        Args:
            session: SQLAlchemy async session
        """
        self._session = session

    def _to_db_model(self, job: ProcessingJob) -> ProcessingJobDB:
        """Convert domain aggregate to database model."""
        import json

        return ProcessingJobDB(
            id=job.id,
            tenant_id=job.tenant_id,
            version=job.version,
            file_name=job.file_name,
            file_size=job.file_size,
            file_key=job.file_key,
            complexity_tier=job.complexity_tier,
            status=job.status.value,
            error_message=job.error_message,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
            estimated_cost=str(job.estimated_cost),
            actual_cost=str(job.actual_cost) if job.actual_cost else None,
            result_records=job.result_records,
            result_url=job.result_url,
            metadata_json=json.dumps(job.metadata) if job.metadata else None,
        )

    def _from_db_model(self, db_job: ProcessingJobDB) -> ProcessingJob:
        """Convert database model to domain aggregate."""
        import json

        return ProcessingJob(
            id=db_job.id,
            tenant_id=db_job.tenant_id,
            version=db_job.version,
            file_name=db_job.file_name,
            file_size=db_job.file_size,
            file_key=db_job.file_key,
            complexity_tier=db_job.complexity_tier,
            status=JobStatus(db_job.status),
            error_message=db_job.error_message,
            retry_count=db_job.retry_count,
            max_retries=db_job.max_retries,
            created_at=db_job.created_at,
            started_at=db_job.started_at,
            completed_at=db_job.completed_at,
            updated_at=db_job.updated_at,
            estimated_cost=Decimal(db_job.estimated_cost),
            actual_cost=Decimal(db_job.actual_cost) if db_job.actual_cost else None,
            result_records=db_job.result_records,
            result_url=db_job.result_url,
            metadata=json.loads(db_job.metadata_json) if db_job.metadata_json else {},
        )

    async def save(self, job: ProcessingJob) -> ProcessingJob:
        """Save job with optimistic locking."""
        # Check if exists
        existing = await self._session.get(ProcessingJobDB, job.id)

        if existing is None:
            # Create new
            db_job = self._to_db_model(job)
            self._session.add(db_job)
            await self._session.commit()
            await self._session.refresh(db_job)
            logger.debug(f"Created job: {job.id}")
            return self._from_db_model(db_job)
        else:
            # Update with optimistic locking
            if existing.version != job.version - 1:
                raise JobConcurrencyError(
                    job_id=job.id,
                    expected_version=job.version - 1,
                    actual_version=existing.version,
                )

            # Update fields
            db_job = self._to_db_model(job)
            for key, value in db_job.__dict__.items():
                if not key.startswith("_") and key != "id":
                    setattr(existing, key, value)

            await self._session.commit()
            await self._session.refresh(existing)
            logger.debug(f"Updated job: {job.id} to version {job.version}")
            return self._from_db_model(existing)

    async def get(self, job_id: str) -> Optional[ProcessingJob]:
        """Get job by ID."""
        db_job = await self._session.get(ProcessingJobDB, job_id)
        if db_job is None:
            return None
        return self._from_db_model(db_job)

    async def get_by_id(self, job_id: str) -> ProcessingJob:
        """Get job by ID, raise if not found."""
        job = await self.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    async def delete(self, job_id: str) -> bool:
        """Delete job by ID."""
        result = await self._session.execute(
            delete(ProcessingJobDB).where(ProcessingJobDB.id == job_id)
        )
        await self._session.commit()
        return result.rowcount > 0

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProcessingJob]:
        """List jobs for tenant."""
        query = select(ProcessingJobDB).where(
            ProcessingJobDB.tenant_id == tenant_id
        )

        if status:
            query = query.where(ProcessingJobDB.status == status.value)

        query = query.order_by(ProcessingJobDB.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self._session.execute(query)
        db_jobs = result.scalars().all()

        return [self._from_db_model(db_job) for db_job in db_jobs]

    async def list_by_status(
        self,
        status: JobStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProcessingJob]:
        """List jobs by status."""
        query = select(ProcessingJobDB).where(
            ProcessingJobDB.status == status.value
        )
        query = query.order_by(ProcessingJobDB.created_at.asc())
        query = query.limit(limit).offset(offset)

        result = await self._session.execute(query)
        db_jobs = result.scalars().all()

        return [self._from_db_model(db_job) for db_job in db_jobs]

    async def count_by_tenant(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
    ) -> int:
        """Count jobs for tenant."""
        query = select(func.count()).select_from(ProcessingJobDB).where(
            ProcessingJobDB.tenant_id == tenant_id
        )

        if status:
            query = query.where(ProcessingJobDB.status == status.value)

        result = await self._session.execute(query)
        return result.scalar() or 0

    async def get_stale_processing_jobs(
        self,
        older_than: datetime,
        limit: int = 100,
    ) -> List[ProcessingJob]:
        """Get jobs stuck in PROCESSING state."""
        query = select(ProcessingJobDB).where(
            ProcessingJobDB.status == JobStatus.PROCESSING.value,
            ProcessingJobDB.started_at < older_than,
        )
        query = query.limit(limit)

        result = await self._session.execute(query)
        db_jobs = result.scalars().all()

        return [self._from_db_model(db_job) for db_job in db_jobs]

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> ProcessingJob:
        """Update job status directly."""
        job = await self.get_by_id(job_id)

        # Validate transition
        if status not in job.status.allowed_transitions:
            raise InvalidStateTransition(
                job_id=job_id,
                current_state=job.status.value,
                attempted_state=status.value,
                allowed_transitions=[s.value for s in job.status.allowed_transitions],
            )

        # Apply transition via domain methods
        if status == JobStatus.PROCESSING:
            job.transition_to_processing()
        elif status == JobStatus.COMPLETE:
            job.transition_to_complete(result_records=0)
        elif status == JobStatus.FAILED:
            job.transition_to_failed(error_message=error_message or "Unknown error")
        elif status == JobStatus.CANCELLED:
            job.transition_to_cancelled()

        return await self.save(job)


# -----------------------------------------------------------------
# In-Memory Repository (for testing)
# -----------------------------------------------------------------

class InMemoryJobRepository(IJobRepository):
    """
    In-memory implementation for testing.

    Stores jobs in a dictionary - no persistence.
    Uses deep copies to simulate real database behavior where
    objects are independent of their stored representations.
    """

    def __init__(self):
        self._jobs: Dict[str, ProcessingJob] = {}

    async def save(self, job: ProcessingJob) -> ProcessingJob:
        """Save job to memory with optimistic locking."""
        if job.id in self._jobs:
            existing = self._jobs[job.id]
            if existing.version != job.version - 1:
                raise JobConcurrencyError(
                    job_id=job.id,
                    expected_version=job.version - 1,
                    actual_version=existing.version,
                )

        # Store a deep copy to prevent reference mutation issues
        self._jobs[job.id] = job.model_copy(deep=True)
        return job

    async def get(self, job_id: str) -> Optional[ProcessingJob]:
        """Get job from memory, returning a copy."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        # Return a copy to prevent mutation of stored data
        return job.model_copy(deep=True)

    async def get_by_id(self, job_id: str) -> ProcessingJob:
        """Get job, raise if not found."""
        job = await self.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    async def delete(self, job_id: str) -> bool:
        """Delete job from memory."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProcessingJob]:
        """List jobs by tenant, returning copies."""
        jobs = [
            job.model_copy(deep=True) for job in self._jobs.values()
            if job.tenant_id == tenant_id
            and (status is None or job.status == status)
        ]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[offset:offset + limit]

    async def list_by_status(
        self,
        status: JobStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProcessingJob]:
        """List jobs by status, returning copies."""
        jobs = [
            job.model_copy(deep=True) for job in self._jobs.values()
            if job.status == status
        ]
        jobs.sort(key=lambda j: j.created_at)
        return jobs[offset:offset + limit]

    async def count_by_tenant(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
    ) -> int:
        """Count jobs for tenant."""
        return len(await self.list_by_tenant(tenant_id, status))

    async def get_stale_processing_jobs(
        self,
        older_than: datetime,
        limit: int = 100,
    ) -> List[ProcessingJob]:
        """Get stale processing jobs, returning copies."""
        jobs = [
            job.model_copy(deep=True) for job in self._jobs.values()
            if job.status == JobStatus.PROCESSING
            and job.started_at
            and job.started_at < older_than
        ]
        return jobs[:limit]

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> ProcessingJob:
        """Update job status."""
        job = await self.get_by_id(job_id)

        if status == JobStatus.PROCESSING:
            job.transition_to_processing()
        elif status == JobStatus.COMPLETE:
            job.transition_to_complete(result_records=0)
        elif status == JobStatus.FAILED:
            job.transition_to_failed(error_message=error_message or "Unknown error")
        elif status == JobStatus.CANCELLED:
            job.transition_to_cancelled()

        return await self.save(job)

    def clear(self) -> None:
        """Clear all jobs (for testing)."""
        self._jobs.clear()


# -----------------------------------------------------------------
# Shared Singleton Instance (for development/testing)
# -----------------------------------------------------------------

# Global singleton instance for in-memory repository
# This ensures all endpoints share the same job storage during development
_shared_in_memory_repository: Optional[InMemoryJobRepository] = None


def get_shared_in_memory_repository() -> InMemoryJobRepository:
    """
    Get the shared singleton InMemoryJobRepository instance.

    This function provides a single shared repository instance that all
    API endpoints can use during development/testing. This solves the issue
    where separate repository instances meant jobs created in one endpoint
    were invisible to other endpoints.

    Returns:
        InMemoryJobRepository: The shared singleton repository instance
    """
    global _shared_in_memory_repository
    if _shared_in_memory_repository is None:
        _shared_in_memory_repository = InMemoryJobRepository()
        logger.info("Created shared InMemoryJobRepository singleton")
    return _shared_in_memory_repository


def reset_shared_in_memory_repository() -> None:
    """
    Reset the shared repository singleton.

    This is useful for testing to ensure a clean state between tests.
    """
    global _shared_in_memory_repository
    if _shared_in_memory_repository is not None:
        _shared_in_memory_repository.clear()
        _shared_in_memory_repository = None
        logger.info("Reset shared InMemoryJobRepository singleton")
