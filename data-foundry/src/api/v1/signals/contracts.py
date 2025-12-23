"""
Signal Detection API Contracts - OpenAPI 3.0 Specification

Defines the contract for signal detection endpoints following OpenAPI standards.
This implements a contract-first approach for API design and documentation.

SECURITY HARDENING - Week 4 Phase 2.3:
- Input validation via Pydantic models
- Size limits on request payloads (1MB max)
- Field validators for threshold bounds
- Pattern reference: src/api/v1/quality/contracts.py, src/api/v1/abtest/contracts.py
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# REQUEST MODELS
# ============================================================================

class DetectSignalRequest(BaseModel):
    """Request model for signal detection on a single record."""
    record: Dict[str, Any] = Field(
        ...,
        description="Data record to analyze for signals. Can contain any fields.",
        json_schema_extra={
            "max_size": 1048576  # 1MB max size
        }
    )

    @field_validator('record')
    @classmethod
    def validate_record_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate record size to prevent memory exhaustion.

        Ensures the JSON representation of the record doesn't exceed 1MB.
        This prevents potential denial-of-service attacks through oversized records.
        Pattern reference: src/api/v1/quality/contracts.py:30-53
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
                    "id": "record-001",
                    "tenant_id": "tenant-1",
                    "data_source": "reddit",
                    "data_preview": "Looking for a tool for data analysis",
                    "raw_data": '{"text": "Can anyone recommend a good data analysis tool?"}',
                    "data_quality_score": 0.95,
                    "access_count": 150
                }
            }
        }


class DetectBatchRequest(BaseModel):
    """Request model for batch signal detection."""
    records: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of data records to analyze for signals (max 1000 per batch)"
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
        Validate total batch size to prevent memory exhaustion.

        Ensures the total JSON size of all records doesn't exceed 10MB.
        This prevents potential denial-of-service attacks through oversized batches.
        Pattern reference: src/api/v1/quality/contracts.py:89-114
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
                        "id": "record-001",
                        "tenant_id": "tenant-1",
                        "data_source": "reddit",
                        "data_preview": "Looking for a tool",
                        "raw_data": '{"text": "recommend a tool"}',
                        "data_quality_score": 0.9,
                        "access_count": 100
                    },
                    {
                        "id": "record-002",
                        "tenant_id": "tenant-1",
                        "data_source": "reddit",
                        "data_preview": "Frustrated with current options",
                        "raw_data": '{"text": "I hate when software crashes"}',
                        "data_quality_score": 0.85,
                        "access_count": 80
                    }
                ]
            }
        }


class UpdateSignalConfigRequest(BaseModel):
    """Request model for updating signal detector configuration (admin only)."""
    threshold: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Signal strength threshold for analysis (0.0-100.0)"
    )

    @field_validator('threshold')
    @classmethod
    def validate_threshold_range(cls, v: float) -> float:
        """
        Validate threshold is within acceptable range.

        Pattern reference: src/api/v1/abtest/contracts.py:195-202
        """
        if not 0 <= v <= 100:
            raise ValueError(f"threshold must be between 0 and 100, got {v}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "threshold": 75.0
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class EngagementMetricsResponse(BaseModel):
    """Response model for engagement metrics."""
    data_quality_score: float = Field(..., ge=0.0, le=1.0, description="Data quality score")
    access_count: int = Field(..., ge=0, description="Access count")
    engagement_ratio: float = Field(..., ge=0.0, description="Engagement ratio")

    class Config:
        json_schema_extra = {
            "example": {
                "data_quality_score": 0.95,
                "access_count": 150,
                "engagement_ratio": 157.89
            }
        }


class DetectSignalResponse(BaseModel):
    """Response model for single record signal detection result."""
    signal_type: str = Field(..., description="Detected signal type (TOOL_REQUEST, PAIN_COMPLAINT, etc.)")
    signal_strength: float = Field(..., ge=0.0, le=100.0, description="Signal strength score (0-100)")
    evidence_snippets: List[str] = Field(
        default_factory=list,
        description="Evidence snippets showing matched patterns"
    )
    engagement_metrics: EngagementMetricsResponse = Field(
        ...,
        description="Engagement metrics for the record"
    )
    should_analyze: bool = Field(..., description="Whether signal exceeds threshold")

    class Config:
        json_schema_extra = {
            "example": {
                "signal_type": "TOOL_REQUEST",
                "signal_strength": 85.0,
                "evidence_snippets": [
                    "Looking for a tool for data analysis",
                    "Can anyone recommend a good data analysis tool?"
                ],
                "engagement_metrics": {
                    "data_quality_score": 0.95,
                    "access_count": 150,
                    "engagement_ratio": 157.89
                },
                "should_analyze": True
            }
        }


class DetectBatchResponse(BaseModel):
    """Response model for batch signal detection results."""
    results: List[DetectSignalResponse] = Field(
        ...,
        description="Individual signal detection results for each record"
    )
    total_records: int = Field(..., ge=0, description="Total number of records analyzed")
    signals_detected: int = Field(..., ge=0, description="Number of records with signals detected")
    should_analyze_count: int = Field(..., ge=0, description="Number of records exceeding threshold")
    signal_type_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of signal types detected"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "signal_type": "TOOL_REQUEST",
                        "signal_strength": 85.0,
                        "evidence_snippets": ["Looking for a tool"],
                        "engagement_metrics": {
                            "data_quality_score": 0.9,
                            "access_count": 100,
                            "engagement_ratio": 111.11
                        },
                        "should_analyze": True
                    },
                    {
                        "signal_type": "PAIN_COMPLAINT",
                        "signal_strength": 75.0,
                        "evidence_snippets": ["Frustrated with current options"],
                        "engagement_metrics": {
                            "data_quality_score": 0.85,
                            "access_count": 80,
                            "engagement_ratio": 94.12
                        },
                        "should_analyze": True
                    }
                ],
                "total_records": 2,
                "signals_detected": 2,
                "should_analyze_count": 2,
                "signal_type_distribution": {
                    "TOOL_REQUEST": 1,
                    "PAIN_COMPLAINT": 1
                }
            }
        }


class SignalConfigResponse(BaseModel):
    """Response model for signal detector configuration."""
    threshold: float = Field(..., ge=0.0, le=100.0, description="Current analysis threshold")
    enabled_signal_types: List[str] = Field(
        ...,
        description="List of enabled signal types"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "threshold": 70.0,
                "enabled_signal_types": [
                    "TOOL_REQUEST",
                    "PAIN_COMPLAINT",
                    "PRICE_MENTION",
                    "PROBLEM_SOLUTION",
                    "COMPARISON"
                ]
            }
        }


class SignalTypeInfo(BaseModel):
    """Information about a specific signal type."""
    name: str = Field(..., description="Signal type name")
    description: str = Field(..., description="Signal type description")
    patterns: List[str] = Field(..., description="Example patterns for this signal type")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "TOOL_REQUEST",
                "description": "User is explicitly requesting tool, software, or app recommendations",
                "patterns": [
                    "is there a (tool|app|software)",
                    "looking for (a tool|an app|software)",
                    "does anyone know of a",
                    "recommend me a"
                ]
            }
        }


class SignalTypesResponse(BaseModel):
    """Response model for listing available signal types."""
    signal_types: List[SignalTypeInfo] = Field(
        ...,
        description="List of available signal types with descriptions and patterns"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "signal_types": [
                    {
                        "name": "TOOL_REQUEST",
                        "description": "User is explicitly requesting tool, software, or app recommendations",
                        "patterns": [
                            "is there a (tool|app|software)",
                            "looking for (a tool|an app|software)"
                        ]
                    },
                    {
                        "name": "PAIN_COMPLAINT",
                        "description": "User expresses frustration or pain points",
                        "patterns": [
                            "i hate when",
                            "frustrated with",
                            "can't stand"
                        ]
                    }
                ]
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
                "message": "Invalid threshold value",
                "details": {"field": "threshold", "value": 150.0},
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
                "data": {"threshold": 75.0},
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


# ============================================================================
# OPENAPI DOCUMENTATION
# ============================================================================

SIGNALS_API_TAGS = [
    {
        "name": "signals",
        "description": "Signal detection endpoints for identifying opportunity signals in data",
        "externalDocs": {
            "description": "Signal Detection Documentation",
            "url": "https://docs.datafoundry.com/signals"
        }
    }
]

SIGNALS_ENDPOINT_DESCRIPTIONS = {
    "detect": """
    Detect opportunity signals in a single data record.

    This endpoint analyzes a data record for opportunity signals:
    - Tool/app/software requests
    - Pain complaints and frustrations
    - Price mentions and willingness to pay
    - Problem-solution patterns
    - Comparisons between alternatives

    **Signal Detection:**
    - Uses pattern matching against pre-compiled regex patterns
    - Calculates engagement metrics from data quality and access count
    - Returns signal strength (0-100) based on pattern matches and engagement
    - Provides evidence snippets showing where patterns were found

    **Security:**
    - Rate limited: 100 requests/minute per IP
    - Tenant isolation enforced
    - Max record size: 1MB

    **Use Cases:**
    - Real-time signal detection at data ingestion
    - Opportunity identification for sales
    - Lead qualification and scoring
    - Market research and trend analysis
    """,

    "detect_batch": """
    Detect opportunity signals in multiple data records.

    This endpoint performs batch signal detection on multiple records (up to 1000):
    - Processes all records independently
    - Returns individual results plus aggregate statistics
    - Provides signal type distribution across the batch

    **Batch Processing:**
    - Maximum batch size: 1000 records
    - Maximum total batch size: 10MB
    - Each record is analyzed independently
    - Aggregate statistics include signal counts and distribution

    **Security:**
    - Rate limited: 20 requests/minute per IP
    - Tenant isolation enforced for each record
    - Size limits enforced

    **Use Cases:**
    - Bulk signal detection for historical data
    - Initial signal assessment for new datasets
    - Periodic signal analysis
    - Lead batch processing
    """,

    "get_config": """
    Get current signal detector configuration.

    This endpoint returns the current configuration for the signal detector:
    - Analysis threshold value
    - List of enabled signal types

    **Configuration Details:**
    - Threshold: Signal strength required for analysis (0-100)
    - Signal types: Available opportunity signal patterns

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Understanding detection behavior
    - Configuration verification
    - Documentation generation
    """,

    "update_config": """
    Update signal detector configuration (admin only).

    This endpoint allows updating the signal detector configuration:
    - Adjust analysis threshold
    - Requires admin privileges

    **Configuration Changes:**
    - Threshold must be in range [0.0, 100.0]
    - Changes affect subsequent detections
    - Admin role required

    **Security:**
    - Rate limited: 10 requests/minute per IP
    - Admin access required
    - Configuration validation enforced

    **Use Cases:**
    - Fine-tuning sensitivity for specific use cases
    - A/B testing different thresholds
    - Adapting to changing data patterns
    """,

    "get_types": """
    List available signal types with descriptions.

    This endpoint returns all available opportunity signal types:
    - Signal type names
    - Descriptions of what each type detects
    - Example patterns for each type

    **Signal Types Include:**
    - TOOL_REQUEST: Tool/software/app requests
    - PAIN_COMPLAINT: User frustrations and pain points
    - PRICE_MENTION: Price discussions and willingness to pay
    - PROBLEM_SOLUTION: Problem-solving discussions
    - COMPARISON: Product/service comparisons

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Understanding available signal patterns
    - Building custom analysis pipelines
    - Documentation and training
    - Pattern reference for filtering
    """
}
