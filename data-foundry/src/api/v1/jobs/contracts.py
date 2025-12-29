"""
Jobs API Contracts

Pydantic models for job-related API operations.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JobStatusContract(BaseModel):
    """
    API Response: Job status details.
    """
    job_id: str = Field(..., description="Job identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    status: str = Field(..., description="Current status")

    # File info
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    complexity_tier: str = Field(..., description="Processing complexity")

    # Cost
    estimated_cost: str = Field(..., description="Estimated cost (USD)")
    actual_cost: Optional[str] = Field(None, description="Actual cost (USD)")

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    result_records: Optional[int] = Field(None, description="Records processed")
    result_url: Optional[str] = Field(None, description="Results download URL")
    error_message: Optional[str] = Field(None, description="Error if failed")

    # Retry info
    retry_count: int = Field(default=0, description="Number of retries")
    can_retry: bool = Field(default=False, description="Can be retried")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "tenant_id": "tenant-123",
                "status": "complete",
                "file_name": "customer_data.csv",
                "file_size": 1048576,
                "complexity_tier": "simple",
                "estimated_cost": "0.006089",
                "actual_cost": "0.005500",
                "created_at": "2025-01-15T10:30:00Z",
                "started_at": "2025-01-15T10:30:05Z",
                "completed_at": "2025-01-15T10:31:30Z",
                "result_records": 10000,
                "result_url": "https://storage.example.com/results/...",
                "error_message": None,
                "retry_count": 0,
                "can_retry": False
            }
        }
    }


class JobListContract(BaseModel):
    """
    API Response: List of jobs with pagination.
    """
    jobs: List[JobStatusContract] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total matching jobs")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="More results available")


class JobRetryContract(BaseModel):
    """
    API Response: Job retry result.
    """
    job_id: str
    status: str
    retry_count: int
    message: str


class JobCancelContract(BaseModel):
    """
    API Request: Job cancellation.
    """
    reason: Optional[str] = Field(
        default=None,
        description="Reason for cancellation"
    )


class JobStatsContract(BaseModel):
    """
    API Response: Job statistics for a tenant.
    """
    tenant_id: str
    total_jobs: int
    pending: int
    processing: int
    complete: int
    failed: int
    cancelled: int
    total_estimated_cost: str
    total_actual_cost: str
