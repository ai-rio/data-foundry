"""
Jobs API Router

FastAPI router for job tracking and management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from src.api.v1.jobs.contracts import (
    JobStatusContract,
    JobListContract,
    JobRetryContract,
    JobCancelContract,
)
from src.application.job_tracking_service import JobTrackingService
from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.exceptions import (
    JobNotFoundError,
    InvalidStateTransition,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# -----------------------------------------------------------------
# Dependency Injection
# -----------------------------------------------------------------

async def get_job_service() -> JobTrackingService:
    """
    Dependency: Get configured JobTrackingService.
    """
    from src.infrastructure.repositories.job_repository import get_shared_in_memory_repository

    # For development, use shared in-memory repository singleton
    job_repo = get_shared_in_memory_repository()

    return JobTrackingService(repo=job_repo)


async def get_current_tenant(
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    """
    Dependency: Get current tenant ID from request header or default.

    In production, this would extract tenant from JWT token.
    For development/testing, reads from X-Tenant-ID header.

    Args:
        x_tenant_id: Optional tenant ID from X-Tenant-ID header

    Returns:
        The tenant ID from header, or default "test-tenant-001" if not provided
    """
    if x_tenant_id:
        return x_tenant_id
    return "test-tenant-001"


# -----------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------

def job_to_contract(job: ProcessingJob) -> JobStatusContract:
    """Convert domain job to API contract."""
    return JobStatusContract(
        job_id=job.id,
        tenant_id=job.tenant_id,
        status=job.status.value,
        file_name=job.file_name,
        file_size=job.file_size,
        complexity_tier=job.complexity_tier,
        estimated_cost=str(job.estimated_cost),
        actual_cost=str(job.actual_cost) if job.actual_cost else None,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result_records=job.result_records,
        result_url=job.result_url,
        error_message=job.error_message,
        retry_count=job.retry_count,
        can_retry=job.can_retry,
    )


# -----------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------

@router.get(
    "/{job_id}",
    response_model=JobStatusContract,
    summary="Get job status",
)
async def get_job_status(
    job_id: str,
    service: JobTrackingService = Depends(get_job_service),
    tenant_id: str = Depends(get_current_tenant),
) -> JobStatusContract:
    """
    Get the current status of a processing job.

    Returns detailed information including:
    - Current status
    - Processing timestamps
    - Cost information
    - Results (if complete)
    - Error details (if failed)
    """
    try:
        job = await service.get_job_or_fail(job_id)

        # Verify tenant access
        if job.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job",
            )

        return job_to_contract(job)

    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )


@router.get(
    "",
    response_model=JobListContract,
    summary="List jobs",
)
async def list_jobs(
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: JobTrackingService = Depends(get_job_service),
    tenant_id: str = Depends(get_current_tenant),
) -> JobListContract:
    """
    List jobs for the current tenant.

    Supports filtering by status and pagination.
    """
    # Convert status string to enum if provided
    status_enum = None
    if status_filter:
        try:
            status_enum = JobStatus(status_filter.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. "
                       f"Valid values: {[s.value for s in JobStatus]}",
            )

    jobs = await service.list_tenant_jobs(
        tenant_id=tenant_id,
        status=status_enum,
        limit=limit + 1,  # Request one extra to check for more
        offset=offset,
    )

    # Check if there are more results
    has_more = len(jobs) > limit
    jobs = jobs[:limit]

    total = await service.count_tenant_jobs(
        tenant_id=tenant_id,
        status=status_enum,
    )

    return JobListContract(
        jobs=[job_to_contract(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.post(
    "/{job_id}/retry",
    response_model=JobRetryContract,
    summary="Retry a failed job",
)
async def retry_job(
    job_id: str,
    service: JobTrackingService = Depends(get_job_service),
    tenant_id: str = Depends(get_current_tenant),
) -> JobRetryContract:
    """
    Retry a failed job.

    Only jobs in FAILED status with remaining retries can be retried.
    """
    try:
        # Check access
        job = await service.get_job_or_fail(job_id)
        if job.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job",
            )

        # Retry
        job = await service.retry_job(job_id)

        return JobRetryContract(
            job_id=job.id,
            status=job.status.value,
            retry_count=job.retry_count,
            message=f"Job queued for retry (attempt {job.retry_count + 1})",
        )

    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )


@router.post(
    "/{job_id}/cancel",
    response_model=JobStatusContract,
    summary="Cancel a job",
)
async def cancel_job(
    job_id: str,
    body: Optional[JobCancelContract] = None,
    service: JobTrackingService = Depends(get_job_service),
    tenant_id: str = Depends(get_current_tenant),
) -> JobStatusContract:
    """
    Cancel a pending or processing job.

    Completed or already cancelled jobs cannot be cancelled.
    """
    try:
        # Check access
        job = await service.get_job_or_fail(job_id)
        if job.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job",
            )

        reason = body.reason if body else None
        job = await service.cancel_job(job_id, reason=reason)

        return job_to_contract(job)

    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )


@router.get(
    "/{job_id}/download",
    summary="Get download URL for results",
)
async def get_download_url(
    job_id: str,
    service: JobTrackingService = Depends(get_job_service),
    tenant_id: str = Depends(get_current_tenant),
) -> dict:
    """
    Get a presigned URL to download job results.

    Only available for completed jobs with results.
    """
    try:
        job = await service.get_job_or_fail(job_id)

        if job.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job",
            )

        if job.status != JobStatus.COMPLETE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job is not complete (status: {job.status.value})",
            )

        if not job.result_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No results available for this job",
            )

        return {
            "job_id": job.id,
            "download_url": job.result_url,
            "expires_in_seconds": 3600,
        }

    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
