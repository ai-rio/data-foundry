"""
Admin/Monitoring API Contracts - OpenAPI 3.0 Specification

Defines the contract for admin and monitoring endpoints following OpenAPI standards.
This implements a contract-first approach for API design and documentation.

SECURITY HARDENING - Week 4 Phase 2.5:
- Input validation via Pydantic models
- Field validators for parameter bounds
- Pattern reference: src/api/v1/signals/contracts.py
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# REQUEST MODELS
# ============================================================================

class TriggerPipelineRequest(BaseModel):
    """Request model for triggering data ingestion pipeline (admin only)."""
    data_source: str = Field(
        default="sample_data",
        description="Source of data to process"
    )
    enable_validation: bool = Field(
        default=True,
        description="Enable data validation steps"
    )
    enable_ai_labeling: bool = Field(
        default=True,
        description="Enable AI labeling"
    )
    enable_pii_redaction: bool = Field(
        default=True,
        description="Enable PII redaction"
    )
    enable_human_review: bool = Field(
        default=True,
        description="Enable human review routing"
    )

    @field_validator('data_source')
    @classmethod
    def validate_data_source(cls, v: str) -> str:
        """
        Validate data_source parameter.

        Prevents path injection and ensures safe input.
        """
        if not v or len(v) > 255:
            raise ValueError("data_source must be 1-255 characters")
        # Prevent path injection
        if ".." in v or v.startswith(("/","\\")):
            raise ValueError("Invalid data_source path")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "data_source": "sample_data",
                "enable_validation": True,
                "enable_ai_labeling": True,
                "enable_pii_redaction": True,
                "enable_human_review": True
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class ComponentHealthStatus(BaseModel):
    """Health status of a single component."""
    name: str = Field(..., description="Component name")
    status: str = Field(..., description="Status: healthy, degraded, unhealthy")
    latency_ms: Optional[float] = Field(None, description="Response latency in milliseconds")
    error: Optional[str] = Field(None, description="Error message if unhealthy")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "database",
                "status": "healthy",
                "latency_ms": 5.2,
                "error": None,
                "metadata": {"pool_size": 10, "active_connections": 3}
            }
        }


class DetailedHealthResponse(BaseModel):
    """Response model for detailed health check."""
    status: str = Field(..., description="Overall system status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    components: Dict[str, ComponentHealthStatus] = Field(
        ...,
        description="Health status of each component"
    )
    uptime_seconds: Optional[float] = Field(None, description="System uptime in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2025-01-15T10:30:00Z",
                "components": {
                    "database": {
                        "name": "database",
                        "status": "healthy",
                        "latency_ms": 5.2,
                        "metadata": {"pool_size": 10}
                    },
                    "redis": {
                        "name": "redis",
                        "status": "healthy",
                        "latency_ms": 1.5
                    },
                    "label_studio": {
                        "name": "label_studio",
                        "status": "healthy",
                        "latency_ms": 45.0
                    }
                },
                "uptime_seconds": 3600.5
            }
        }


class AggregatedMetricsResponse(BaseModel):
    """Response model for aggregated metrics across all APIs."""
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Metrics timestamp")
    quality: Optional[Dict[str, Any]] = Field(None, description="Quality API metrics")
    abtest: Optional[Dict[str, Any]] = Field(None, description="A/B Testing API metrics")
    signals: Optional[Dict[str, Any]] = Field(None, description="Signal Detection API metrics")
    ml: Optional[Dict[str, Any]] = Field(None, description="ML Predictor API metrics")
    system: Optional[Dict[str, Any]] = Field(None, description="System-level metrics")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-01-15T10:30:00Z",
                "quality": {
                    "total_validations": 1500,
                    "valid_records": 1425,
                    "invalid_records": 75,
                    "avg_quality_score": 0.85
                },
                "abtest": {
                    "total_samples": 3000,
                    "control_count": 2100,
                    "variant_count": 900
                },
                "signals": {
                    "total_detections": 800,
                    "signals_detected": 450,
                    "avg_signal_strength": 72.5
                },
                "ml": {
                    "total_predictions": 200,
                    "success_rate": 0.95,
                    "avg_confidence": 0.87
                },
                "system": {
                    "uptime_seconds": 3600.5,
                    "memory_mb": 512,
                    "cpu_percent": 25.5
                }
            }
        }


class PipelineStatusResponse(BaseModel):
    """Response model for pipeline status check."""
    status: str = Field(..., description="Pipeline status: idle, running, completed, failed")
    last_run_id: Optional[str] = Field(None, description="Last pipeline run ID")
    last_run_time: Optional[datetime] = Field(None, description="Last pipeline run time")
    last_run_stats: Optional[Dict[str, Any]] = Field(None, description="Last run statistics")
    active_runs: int = Field(default=0, description="Number of active pipeline runs")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "idle",
                "last_run_id": "flow-run-abc123",
                "last_run_time": "2025-01-15T09:00:00Z",
                "last_run_stats": {
                    "total_extracted": 100,
                    "valid_records": 95,
                    "auto_approved": 80
                },
                "active_runs": 0
            }
        }


class TriggerPipelineResponse(BaseModel):
    """Response model for pipeline trigger."""
    message: str = Field(..., description="Status message")
    flow_run_id: str = Field(..., description="Prefect flow run ID")
    status: str = Field(..., description="Trigger status")
    parameters: Dict[str, Any] = Field(..., description="Pipeline parameters used")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Pipeline triggered successfully",
                "flow_run_id": "flow-run-abc123",
                "status": "started",
                "parameters": {
                    "data_source": "sample_data",
                    "enable_validation": True
                }
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
                "message": "Invalid request parameters",
                "details": {"field": "data_source"},
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


# ============================================================================
# OPENAPI DOCUMENTATION
# ============================================================================

ADMIN_API_TAGS = [
    {
        "name": "admin",
        "description": "Admin and monitoring endpoints for system health and metrics",
        "externalDocs": {
            "description": "Admin API Documentation",
            "url": "https://docs.datafoundry.com/admin"
        }
    }
]

ADMIN_ENDPOINT_DESCRIPTIONS = {
    "health_detailed": """
    Get detailed component health status.

    This endpoint checks the health of all system components:
    - Database connectivity and performance
    - Redis connectivity and performance
    - Label Studio availability
    - AI provider status (OpenAI, Anthropic)

    **Health Checks:**
    - Database: Connection pool status and query latency
    - Redis: Connectivity and memory usage
    - Label Studio: API availability
    - AI Providers: API key configuration and quota status

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - System monitoring dashboards
    - Health check automation
    - Troubleshooting system issues
    """,

    "metrics_aggregated": """
    Get aggregated metrics across all APIs.

    This endpoint aggregates metrics from all API modules:
    - Quality API: Validation metrics
    - A/B Testing API: Experiment metrics
    - Signals API: Detection metrics
    - ML API: Prediction metrics
    - System: Memory, CPU, uptime

    **Metrics Include:**
    - Total requests and success rates
    - Average quality scores
    - Signal detection statistics
    - ML prediction accuracy
    - System resource usage

    **Security:**
    - Rate limited: 30 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Performance monitoring
    - Capacity planning
    - Trend analysis
    - Dashboard aggregation
    """,

    "pipeline_status": """
    Get current data ingestion pipeline status.

    This endpoint reports the status of the Prefect-based data ingestion pipeline:
    - Current pipeline state (idle, running, completed, failed)
    - Last run information
    - Active run count
    - Last run statistics

    **Pipeline Information:**
    - Prefect flow run IDs
    - Run timestamps
    - Statistics from last run (records processed, validation results)
    - Active/concurrent runs

    **Security:**
    - Rate limited: 30 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Pipeline monitoring
    - Run status checks
    - Automation triggers
    """,

    "pipeline_trigger": """
    Trigger data ingestion pipeline (admin only).

    This endpoint triggers the Prefect data ingestion flow:
    - Extract data from specified source
    - Validate and process records
    - Apply AI labeling if enabled
    - Route to human review if needed

    **Pipeline Steps:**
    - Data extraction from source
    - Schema validation
    - Duplicate checking
    - Quality scoring and filtering
    - PII redaction (optional)
    - AI labeling (optional)
    - Human review routing (optional)
    - Database persistence

    **Security:**
    - Rate limited: 10 requests/minute per IP
    - Admin access required
    - Parameter validation enforced

    **Use Cases:**
    - Manual pipeline triggering
    - Scheduled data imports
    - Admin-initiated processing
    """
}
