"""
Data Quality API Contracts - OpenAPI 3.0 Specification

Defines the contract for data quality validation endpoints following OpenAPI standards.
This implements a contract-first approach for API design and documentation.

SECURITY HARDENING - Week 4 Phase 2.1 Fixes Applied:
- HIGH #4: Added max size validation to prevent oversized records
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# REQUEST MODELS
# ============================================================================

class ValidateRequest(BaseModel):
    """Request model for single record validation."""
    record: Dict[str, Any] = Field(
        ...,
        description="Data record to validate. Can contain any fields.",
        json_schema_extra={
            "max_size": 1048576  # HIGH #4: Max 1MB per record
        }
    )

    @field_validator('record')
    @classmethod
    def validate_record_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate record size to prevent memory exhaustion (HIGH #4).

        Ensures the JSON representation of the record doesn't exceed 1MB.
        This prevents potential denial-of-service attacks through oversized records.
        """
        import json
        try:
            record_json = json.dumps(v)
            size_bytes = len(record_json.encode('utf-8'))
            max_size = 1 * 1024 * 1024  # 1MB

            if size_bytes > max_size:
                raise ValueError(
                    f"Record size exceeds maximum allowed size of {max_size} bytes. "
                    f"Got {size_bytes} bytes."
                )
        except (TypeError, OverflowError) as e:
            raise ValueError(f"Invalid record format: {str(e)}")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "record": {
                    "record_id": "test-record-001",
                    "tenant_id": "tenant-1",
                    "data_source": "csv",
                    "raw_data": '{"field1": "value1"}',
                    "file_name": "test.csv",
                    "mime_type": "text/csv"
                }
            }
        }


class ValidateBatchRequest(BaseModel):
    """Request model for batch record validation."""
    records: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of data records to validate (max 1000 per batch)"
    )

    @field_validator('records')
    @classmethod
    def validate_records_not_empty(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure records list is not empty."""
        if not v:
            raise ValueError("records list cannot be empty")
        return v

    @field_validator('records')
    @classmethod
    def validate_batch_size(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate total batch size to prevent memory exhaustion (HIGH #4).

        Ensures the total JSON size of all records doesn't exceed 10MB.
        This prevents potential denial-of-service attacks through oversized batches.
        """
        import json
        total_size = 0
        max_batch_size = 10 * 1024 * 1024  # 10MB total for batch

        for i, record in enumerate(v):
            try:
                record_json = json.dumps(record)
                size_bytes = len(record_json.encode('utf-8'))
                total_size += size_bytes

                if total_size > max_batch_size:
                    raise ValueError(
                        f"Batch total size exceeds maximum allowed size of {max_batch_size} bytes. "
                        f"Exceeded at record {i + 1}."
                    )
            except (TypeError, OverflowError) as e:
                raise ValueError(f"Invalid record format at index {i}: {str(e)}")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "records": [
                    {
                        "record_id": "record-001",
                        "tenant_id": "tenant-1",
                        "data_source": "csv",
                        "raw_data": '{"field": "value"}'
                    },
                    {
                        "record_id": "record-002",
                        "tenant_id": "tenant-1",
                        "data_source": "json",
                        "raw_data": '{"field": "value"}'
                    }
                ]
            }
        }


class UpdateConfigRequest(BaseModel):
    """Request model for updating quality validator configuration."""
    completeness_weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weight for completeness score in quality calculation (0.0-1.0)"
    )
    validity_weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weight for validity score in quality calculation (0.0-1.0)"
    )
    error_penalty: float = Field(
        ...,
        gt=0.0,
        le=1.0,
        description="Penalty subtracted from validity per error (0.0-1.0, exclusive of 0.0)"
    )

    @field_validator('validity_weight')
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        """
        Ensure completeness_weight and validity_weight sum to approximately 1.0.

        This is a soft validation - weights don't need to sum exactly to 1.0
        because they're normalized during calculation.
        """
        if 'completeness_weight' in info.data:
            completeness = info.data['completeness_weight']
            total = completeness + v
            if total < 0.8 or total > 1.2:
                raise ValueError(
                    f"Sum of completeness_weight and validity_weight should be close to 1.0, got {total}"
                )
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "completeness_weight": 0.6,
                "validity_weight": 0.4,
                "error_penalty": 0.2
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class ValidationResultResponse(BaseModel):
    """Response model for single record validation result."""
    is_valid: bool = Field(..., description="Whether the record passes validation")
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Completeness score (0.0-1.0)")
    validity_score: float = Field(..., ge=0.0, le=1.0, description="Validity score (0.0-1.0)")
    quality_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score (0.0-1.0)")
    errors: List[str] = Field(default_factory=list, description="Validation error messages")
    warnings: List[str] = Field(default_factory=list, description="Validation warning messages")

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": True,
                "completeness_score": 0.85,
                "validity_score": 1.0,
                "quality_score": 0.91,
                "errors": [],
                "warnings": ["Missing recommended field: file_name"]
            }
        }


class ValidateBatchResponse(BaseModel):
    """Response model for batch validation results."""
    results: List[ValidationResultResponse] = Field(
        ...,
        description="Individual validation results for each record"
    )
    total_records: int = Field(..., ge=0, description="Total number of records validated")
    valid_count: int = Field(..., ge=0, description="Number of valid records")
    invalid_count: int = Field(..., ge=0, description="Number of invalid records")
    avg_quality_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Average quality score across all records"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "is_valid": True,
                        "completeness_score": 1.0,
                        "validity_score": 1.0,
                        "quality_score": 1.0,
                        "errors": [],
                        "warnings": []
                    },
                    {
                        "is_valid": False,
                        "completeness_score": 0.5,
                        "validity_score": 0.6,
                        "quality_score": 0.54,
                        "errors": ["Missing required field: tenant_id"],
                        "warnings": []
                    }
                ],
                "total_records": 2,
                "valid_count": 1,
                "invalid_count": 1,
                "avg_quality_score": 0.77
            }
        }


class QualityMetricsResponse(BaseModel):
    """Response model for quality metrics."""
    total_records: int = Field(..., ge=0, description="Total number of records processed")
    valid_records: int = Field(..., ge=0, description="Number of valid records")
    invalid_records: int = Field(..., ge=0, description="Number of invalid records")
    avg_quality_score: float = Field(..., ge=0.0, le=1.0, description="Average quality score")
    avg_completeness_score: float = Field(..., ge=0.0, le=1.0, description="Average completeness score")
    avg_validity_score: float = Field(..., ge=0.0, le=1.0, description="Average validity score")
    common_errors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Most common validation errors with occurrence counts"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_records": 100,
                "valid_records": 85,
                "invalid_records": 15,
                "avg_quality_score": 0.82,
                "avg_completeness_score": 0.88,
                "avg_validity_score": 0.75,
                "common_errors": [
                    {"error": "Missing required field: email", "count": 10},
                    {"error": "Invalid email format", "count": 5}
                ]
            }
        }


class QualityConfigResponse(BaseModel):
    """Response model for quality validator configuration."""
    completeness_weight: float = Field(..., ge=0.0, le=1.0, description="Current completeness weight")
    validity_weight: float = Field(..., ge=0.0, le=1.0, description="Current validity weight")
    error_penalty: float = Field(..., gt=0.0, le=1.0, description="Current error penalty")
    required_fields: List[str] = Field(..., description="List of required fields")
    recommended_fields: List[str] = Field(..., description="List of recommended fields")

    class Config:
        json_schema_extra = {
            "example": {
                "completeness_weight": 0.6,
                "validity_weight": 0.4,
                "error_penalty": 0.2,
                "required_fields": ["record_id", "tenant_id", "data_source", "raw_data"],
                "recommended_fields": ["file_name", "mime_type", "record_hash"]
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid weight value",
                "details": {"field": "completeness_weight", "value": 1.5},
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


class SuccessResponse(BaseModel):
    """Standard success response model."""
    success: bool = Field(default=True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Configuration updated successfully",
                "data": {"completeness_weight": 0.7, "validity_weight": 0.3},
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


# ============================================================================
# OPENAPI DOCUMENTATION
# ============================================================================

QUALITY_API_TAGS = [
    {
        "name": "quality",
        "description": "Data quality validation endpoints for data record assessment",
        "externalDocs": {
            "description": "Data Quality Documentation",
            "url": "https://docs.datafoundry.com/quality"
        }
    }
]

QUALITY_ENDPOINT_DESCRIPTIONS = {
    "validate": """
    Validate a single data record.

    This endpoint performs comprehensive quality validation on a single data record:
    - Checks for required fields (record_id, tenant_id, data_source, raw_data)
    - Validates recommended fields (file_name, mime_type, record_hash)
    - Performs format validation on specific fields (email, phone, timestamps)
    - Computes completeness, validity, and quality scores

    **Validation Rules:**
    - Required fields must be present and non-null
    - Recommended fields generate warnings but don't affect validity
    - Format validation runs only if the field is present
    - Quality score formula: 0.6 * completeness + 0.4 * validity

    **Security:**
    - Rate limited: 100 requests/minute per IP
    - Tenant isolation enforced
    - Max record size: 1MB

    **Use Cases:**
    - Real-time data quality checks at ingestion
    - Pre-processing validation before AI enrichment
    - Data quality monitoring and alerting
    """,

    "validate_batch": """
    Validate multiple data records in a single request.

    This endpoint performs batch validation on multiple records (up to 1000):
    - Processes all records independently
    - Returns individual results for each record
    - Provides aggregate statistics across the batch
    - Handles partial failures gracefully

    **Batch Processing:**
    - Maximum batch size: 1000 records
    - Maximum total batch size: 10MB
    - Each record is validated independently
    - Aggregate statistics include counts and averages
    - Failed validations don't stop batch processing

    **Security:**
    - Rate limited: 20 requests/minute per IP
    - Tenant isolation enforced for each record
    - Size limits enforced

    **Use Cases:**
    - Bulk data quality checks
    - Initial data assessment for new datasets
    - Periodic quality audits
    """,

    "metrics": """
    Get aggregated quality metrics.

    This endpoint returns aggregated quality metrics across all processed records:
    - Total record counts (valid/invalid)
    - Average scores (quality, completeness, validity)
    - Most common validation errors
    - Trend information for quality monitoring

    **Metrics Include:**
    - Aggregate counts and averages
    - Common error patterns
    - Quality score distributions
    - Historical trends (if available)

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Data quality dashboards
    - Monitoring and alerting
    - Quality trend analysis
    """,

    "get_config": """
    Get current quality validator configuration.

    This endpoint returns the current configuration for the quality validator:
    - Scoring weights (completeness, validity)
    - Error penalty settings
    - Required and recommended field lists

    **Configuration Details:**
    - Weights used for quality score calculation
    - Fields checked during validation
    - Error penalty values

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Understanding validation behavior
    - Configuration verification
    - Documentation generation
    """,

    "update_config": """
    Update quality validator configuration.

    This endpoint allows updating the quality validator configuration:
    - Adjust scoring weights
    - Change error penalties
    - Requires admin privileges

    **Configuration Changes:**
    - Weights must be in valid range [0.0, 1.0]
    - Error penalty must be > 0.0 and <= 1.0
    - Changes affect subsequent validations
    - Admin role required

    **Security:**
    - Rate limited: 10 requests/minute per IP
    - Admin access required
    - Configuration validation enforced

    **Use Cases:**
    - Fine-tuning validation for specific use cases
    - A/B testing different quality thresholds
    - Adapting to changing data patterns
    """
}
