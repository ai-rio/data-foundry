"""
Pytest fixtures for worker unit tests.

Provides common mocks and fixtures for testing the JobWorker.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from typing import Callable, Awaitable, Any

from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.repository import IJobRepository


@pytest.fixture
def mock_job_repo() -> AsyncMock:
    """Create a mock job repository for testing."""
    repo = AsyncMock(spec=IJobRepository)
    return repo


@pytest.fixture
def mock_flow_func() -> AsyncMock:
    """Create a mock data_ingestion_flow function."""
    flow = AsyncMock()
    flow.return_value = {
        "success": True,
        "total_records": 10,
        "valid_records": 8,
    }
    return flow


@pytest.fixture
def sample_pending_job() -> ProcessingJob:
    """Create a sample PENDING job for testing."""
    return ProcessingJob(
        id="job-test-001",
        tenant_id="tenant-123",
        version=1,
        file_name="data.csv",
        file_size=1024,
        file_key="tenant-123/job-test-001/data.csv",
        complexity_tier="simple",
        status=JobStatus.PENDING,
        error_message=None,
        retry_count=0,
        max_retries=3,
        created_at=datetime.utcnow(),
        started_at=None,
        completed_at=None,
        updated_at=datetime.utcnow(),
        estimated_cost=Decimal("1.00"),
        actual_cost=None,
        result_records=None,
        result_url=None,
        metadata={},
    )


@pytest.fixture
def sample_processing_job(sample_pending_job: ProcessingJob) -> ProcessingJob:
    """Create a sample PROCESSING job for testing."""
    job = sample_pending_job.model_copy(deep=True)
    job.status = JobStatus.PROCESSING
    job.started_at = datetime.utcnow()
    job.version = 2
    return job


@pytest.fixture
def sample_complete_job(sample_processing_job: ProcessingJob) -> ProcessingJob:
    """Create a sample COMPLETE job for testing."""
    job = sample_processing_job.model_copy(deep=True)
    job.status = JobStatus.COMPLETE
    job.completed_at = datetime.utcnow()
    job.result_records = 100
    job.version = 3
    return job


@pytest.fixture
def sample_failed_job(sample_processing_job: ProcessingJob) -> ProcessingJob:
    """Create a sample FAILED job for testing."""
    job = sample_processing_job.model_copy(deep=True)
    job.status = JobStatus.FAILED
    job.completed_at = datetime.utcnow()
    job.error_message = "Processing failed"
    job.retry_count = 1
    job.version = 3
    return job
