"""
Upload API Contracts

Pydantic models for API request/response validation.
Separate from domain models to allow API evolution.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class UploadResponseContract(BaseModel):
    """
    API Response: Successful file upload.

    Contains job information for tracking processing status.
    """
    job_id: str = Field(..., description="Processing job identifier")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes", ge=0)
    complexity_tier: str = Field(..., description="Processing complexity tier")
    estimated_cost: str = Field(..., description="Estimated processing cost (USD)")
    status: str = Field(..., description="Current job status")
    storage_key: str = Field(..., description="Storage location key")
    created_at: datetime = Field(..., description="Job creation timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "customer_data.csv",
                "size_bytes": 1048576,
                "complexity_tier": "simple",
                "estimated_cost": "0.006089",
                "status": "pending",
                "storage_key": "tenant-123/job-456/customer_data.csv",
                "created_at": "2025-01-15T10:30:00Z"
            }
        }
    }


class ValidationErrorContract(BaseModel):
    """
    API Response: Validation error.

    Returned when file validation fails.
    """
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    errors: List[str] = Field(..., description="Detailed error messages")

    model_config = {
        "json_schema_extra": {
            "example": {
                "code": "FILE_VALIDATION_ERROR",
                "message": "File validation failed",
                "errors": [
                    "File type 'exe' is not allowed. Allowed types: csv, json, xlsx, pdf",
                    "File size 150.5MB exceeds maximum of 100.0MB"
                ]
            }
        }
    }


class UploadMetadataContract(BaseModel):
    """
    API Request: Optional upload metadata.

    Can be included in multipart form or as JSON body.
    """
    vertical: Optional[str] = Field(
        default="general",
        description="Industry vertical for specialized processing"
    )
    auto_start: Optional[bool] = Field(
        default=True,
        description="Automatically start processing after upload"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Optional tags for organization"
    )
    callback_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for completion notification"
    )


class BulkUploadResponseContract(BaseModel):
    """
    API Response: Bulk upload result.

    Contains results for each file in the batch.
    """
    total: int = Field(..., description="Total files in batch")
    successful: int = Field(..., description="Successfully uploaded files")
    failed: int = Field(..., description="Failed uploads")
    results: List[UploadResponseContract] = Field(
        ...,
        description="Individual upload results"
    )
    errors: Optional[List[ValidationErrorContract]] = Field(
        default=None,
        description="Errors for failed uploads"
    )
