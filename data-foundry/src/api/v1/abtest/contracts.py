"""
A/B Testing API Contracts - OpenAPI 3.0 Specification

Defines the contract for A/B testing endpoints following OpenAPI standards.
This implements a contract-first approach for API design and documentation.

SECURITY HARDENING - Week 4 Phase 2.2:
- Input validation via Pydantic models
- Size limits on request payloads (HIGH #1)
- Field validators for ratio bounds
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# REQUEST MODELS
# ============================================================================

class CreateABTestRequest(BaseModel):
    """Request model for creating a new A/B test."""
    test_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique name for the A/B test"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional description of the test purpose"
    )
    variant_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of traffic to route to variant (0.0-1.0)"
    )
    control_name: str = Field(
        default="control",
        max_length=50,
        description="Name for the control treatment"
    )
    variant_name: str = Field(
        default="variant",
        max_length=50,
        description="Name for the variant treatment"
    )

    @field_validator('test_name')
    @classmethod
    def validate_test_name(cls, v: str) -> str:
        """
        Validate test name format.

        Ensures the test name contains only valid characters
        and doesn't contain special characters that could cause issues.
        """
        import re
        # Allow alphanumeric, hyphens, underscores, and spaces
        if not re.match(r'^[a-zA-Z0-9_\-\s]+$', v):
            raise ValueError(
                "test_name must contain only alphanumeric characters, "
                "hyphens, underscores, and spaces"
            )
        return v.strip()

    @field_validator('*')
    @classmethod
    def validate_request_size(cls, v: Any, info) -> Any:
        """
        Validate request size to prevent memory exhaustion (HIGH #1).

        Ensures the JSON representation of the entire request doesn't exceed 1MB.
        This prevents potential denial-of-service attacks through oversized requests.
        Pattern reference: src/api/v1/quality/contracts.py:30-53
        """
        import json
        # Only validate once, on the last field
        if info.field_name != "variant_name":
            return v

        # Get the full model as dict
        if hasattr(info, 'data'):
            try:
                request_json = json.dumps(info.data)
                size_bytes = len(request_json.encode('utf-8'))
                max_size = 1 * 1024 * 1024  # 1MB

                if size_bytes > max_size:
                    raise ValueError(
                        f"Request size exceeds maximum allowed size of {max_size} bytes. "
                        f"Got {size_bytes} bytes."
                    )
            except (TypeError, OverflowError) as e:
                raise ValueError(f"Invalid request format: {str(e)}")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "test_name": "test-validation-strategies",
                "description": "Testing strict vs lenient validation",
                "variant_ratio": 0.3,
                "control_name": "strict_validation",
                "variant_name": "lenient_validation"
            }
        }


class RecordPredictionRequest(BaseModel):
    """Request model for recording a prediction."""
    sample_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique sample identifier"
    )
    treatment: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Treatment identifier (must be registered)"
    )
    prediction: bool = Field(
        ...,
        description="Whether the prediction is positive (True) or negative (False)"
    )
    score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional prediction confidence score (0.0-1.0)"
    )
    ground_truth: Optional[bool] = Field(
        None,
        description="Ground truth label if known (for accuracy calculation)"
    )

    @field_validator('sample_id')
    @classmethod
    def validate_sample_id_not_empty(cls, v: str) -> str:
        """Ensure sample_id is not empty or just whitespace."""
        if not v or not v.strip():
            raise ValueError("sample_id cannot be empty")
        return v

    @field_validator('ground_truth')
    @classmethod
    def validate_request_size(cls, v: Any, info) -> Any:
        """
        Validate request size to prevent memory exhaustion (HIGH #1).

        Ensures the JSON representation of the entire request doesn't exceed 1MB.
        This prevents potential denial-of-service attacks through oversized requests.
        Pattern reference: src/api/v1/quality/contracts.py:30-53
        """
        import json
        # Only validate once, on the last field
        if info.field_name != "ground_truth":
            return v

        # Get the full model as dict
        if hasattr(info, 'data'):
            try:
                request_json = json.dumps(info.data)
                size_bytes = len(request_json.encode('utf-8'))
                max_size = 1 * 1024 * 1024  # 1MB

                if size_bytes > max_size:
                    raise ValueError(
                        f"Request size exceeds maximum allowed size of {max_size} bytes. "
                        f"Got {size_bytes} bytes."
                    )
            except (TypeError, OverflowError) as e:
                raise ValueError(f"Invalid request format: {str(e)}")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "sample_id": "sample-001",
                "treatment": "control",
                "prediction": True,
                "score": 0.85,
                "ground_truth": True
            }
        }


class UpdateVariantRatioRequest(BaseModel):
    """Request model for updating variant ratio (admin only)."""
    variant_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="New variant traffic ratio (0.0-1.0)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "variant_ratio": 0.7
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class ABTestMetadata(BaseModel):
    """Metadata for an A/B test."""
    test_id: str = Field(..., description="Unique test identifier")
    test_name: str = Field(..., description="Test name")
    description: Optional[str] = Field(None, description="Test description")
    variant_ratio: float = Field(..., ge=0.0, le=1.0, description="Variant ratio")
    control_name: str = Field(..., description="Control treatment name")
    variant_name: str = Field(..., description="Variant treatment name")
    created_at: datetime = Field(..., description="Creation timestamp")
    status: str = Field(default="active", description="Test status")

    class Config:
        json_schema_extra = {
            "example": {
                "test_id": "abtest-12345",
                "test_name": "test-validation-strategies",
                "description": "Testing strict vs lenient validation",
                "variant_ratio": 0.3,
                "control_name": "strict_validation",
                "variant_name": "lenient_validation",
                "created_at": "2025-01-15T10:30:00Z",
                "status": "active"
            }
        }


class CreateABTestResponse(BaseModel):
    """Response model for creating an A/B test."""
    test_id: str = Field(..., description="Unique test identifier")
    test_name: str = Field(..., description="Test name")
    description: Optional[str] = Field(None, description="Test description")
    variant_ratio: float = Field(..., ge=0.0, le=1.0, description="Variant ratio")
    control_name: str = Field(..., description="Control treatment name")
    variant_name: str = Field(..., description="Variant treatment name")
    created_at: datetime = Field(..., description="Creation timestamp")
    status: str = Field(default="active", description="Test status")
    message: str = Field(default="A/B test created successfully", description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "test_id": "abtest-12345",
                "test_name": "test-validation-strategies",
                "description": "Testing strict vs lenient validation",
                "variant_ratio": 0.3,
                "control_name": "strict_validation",
                "variant_name": "lenient_validation",
                "created_at": "2025-01-15T10:30:00Z",
                "status": "active",
                "message": "A/B test created successfully"
            }
        }


class ListABTestsResponse(BaseModel):
    """Response model for listing A/B tests."""
    tests: List[ABTestMetadata] = Field(
        default_factory=list,
        description="List of A/B tests"
    )
    total_tests: int = Field(..., ge=0, description="Total number of tests")

    class Config:
        json_schema_extra = {
            "example": {
                "tests": [
                    {
                        "test_id": "abtest-12345",
                        "test_name": "test-validation-strategies",
                        "description": "Testing strict vs lenient validation",
                        "variant_ratio": 0.3,
                        "control_name": "strict_validation",
                        "variant_name": "lenient_validation",
                        "created_at": "2025-01-15T10:30:00Z",
                        "status": "active"
                    }
                ],
                "total_tests": 1
            }
        }


class ABTestStatsResponse(BaseModel):
    """Response model for A/B test statistics."""
    test_id: str = Field(..., description="Test identifier")
    total_samples: int = Field(..., ge=0, description="Total samples assigned")
    control_samples: int = Field(..., ge=0, description="Samples assigned to control")
    variant_samples: int = Field(..., ge=0, description="Samples assigned to variant")
    control_ratio_actual: float = Field(..., ge=0.0, le=1.0, description="Actual control ratio")
    variant_ratio_actual: float = Field(..., ge=0.0, le=1.0, description="Actual variant ratio")
    variant_ratio_configured: float = Field(..., ge=0.0, le=1.0, description="Configured variant ratio")

    class Config:
        json_schema_extra = {
            "example": {
                "test_id": "abtest-12345",
                "total_samples": 100,
                "control_samples": 70,
                "variant_samples": 30,
                "control_ratio_actual": 0.70,
                "variant_ratio_actual": 0.30,
                "variant_ratio_configured": 0.30
            }
        }


class RecordPredictionResponse(BaseModel):
    """Response model for recording a prediction."""
    sample_id: str = Field(..., description="Sample identifier")
    treatment: str = Field(..., description="Treatment recorded")
    prediction: bool = Field(..., description="Prediction recorded")
    recorded_at: datetime = Field(default_factory=datetime.utcnow, description="Recording timestamp")
    message: str = Field(default="Prediction recorded successfully", description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "sample_id": "sample-001",
                "treatment": "control",
                "prediction": True,
                "recorded_at": "2025-01-15T10:30:00Z",
                "message": "Prediction recorded successfully"
            }
        }


class TreatmentMetricsResponse(BaseModel):
    """Response model for treatment-specific metrics."""
    treatment: str = Field(..., description="Treatment identifier")
    total_samples: int = Field(..., ge=0, description="Total samples for this treatment")
    predicted_positive: int = Field(..., ge=0, description="Predictions as positive")
    predicted_negative: int = Field(..., ge=0, description="Predictions as negative")
    positive_rate: float = Field(..., ge=0.0, le=1.0, description="Rate of positive predictions")

    # Confusion matrix (if ground truth available)
    true_positive: int = Field(default=0, ge=0, description="True positive count")
    true_negative: int = Field(default=0, ge=0, description="True negative count")
    false_positive: int = Field(default=0, ge=0, description="False positive count")
    false_negative: int = Field(default=0, ge=0, description="False negative count")

    # Performance metrics (if ground truth available)
    precision: Optional[float] = Field(None, ge=0.0, le=1.0, description="Precision score")
    recall: Optional[float] = Field(None, ge=0.0, le=1.0, description="Recall score")
    f1_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="F1 score")
    accuracy: Optional[float] = Field(None, ge=0.0, le=1.0, description="Accuracy score")

    class Config:
        json_schema_extra = {
            "example": {
                "treatment": "control",
                "total_samples": 100,
                "predicted_positive": 60,
                "predicted_negative": 40,
                "positive_rate": 0.60,
                "true_positive": 50,
                "true_negative": 35,
                "false_positive": 10,
                "false_negative": 5,
                "precision": 0.833,
                "recall": 0.909,
                "f1_score": 0.869,
                "accuracy": 0.85
            }
        }


class ABTestMetricsResponse(BaseModel):
    """Response model for full A/B test metrics."""
    test_id: str = Field(..., description="Test identifier")
    test_name: str = Field(..., description="Test name")
    treatments: Dict[str, TreatmentMetricsResponse] = Field(
        ...,
        description="Metrics per treatment"
    )
    comparison: Optional[Dict[str, Any]] = Field(
        None,
        description="Comparison metrics between treatments"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "test_id": "abtest-12345",
                "test_name": "test-validation-strategies",
                "treatments": {
                    "control": {
                        "treatment": "control",
                        "total_samples": 100,
                        "predicted_positive": 60,
                        "predicted_negative": 40,
                        "positive_rate": 0.60,
                        "precision": 0.833,
                        "recall": 0.909,
                        "f1_score": 0.869,
                        "accuracy": 0.85
                    },
                    "variant": {
                        "treatment": "variant",
                        "total_samples": 100,
                        "predicted_positive": 55,
                        "predicted_negative": 45,
                        "positive_rate": 0.55,
                        "precision": 0.85,
                        "recall": 0.85,
                        "f1_score": 0.85,
                        "accuracy": 0.82
                    }
                },
                "comparison": {
                    "precision_diff": -0.017,
                    "recall_diff": 0.059,
                    "f1_diff": 0.019
                }
            }
        }


class ExportMetricsResponse(BaseModel):
    """Response model for exporting metrics as JSON."""
    test_id: str = Field(..., description="Test identifier")
    test_name: str = Field(..., description="Test name")
    description: Optional[str] = Field(None, description="Test description")
    metrics: Dict[str, Any] = Field(..., description="Full metrics data")
    exported_at: datetime = Field(default_factory=datetime.utcnow, description="Export timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "test_id": "abtest-12345",
                "test_name": "test-validation-strategies",
                "description": "Testing strict vs lenient validation",
                "metrics": {
                    "distribution": {...},
                    "treatments": {...}
                },
                "exported_at": "2025-01-15T10:30:00Z"
            }
        }


class UpdateVariantRatioResponse(BaseModel):
    """Response model for updating variant ratio."""
    test_id: str = Field(..., description="Test identifier")
    variant_ratio: float = Field(..., ge=0.0, le=1.0, description="Updated variant ratio")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Update timestamp")
    message: str = Field(default="Variant ratio updated successfully", description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "test_id": "abtest-12345",
                "variant_ratio": 0.7,
                "updated_at": "2025-01-15T10:30:00Z",
                "message": "Variant ratio updated successfully"
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
                "message": "Invalid variant ratio",
                "details": {"field": "variant_ratio", "value": 1.5},
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
                "message": "Operation completed successfully",
                "data": {"test_id": "abtest-12345"},
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


# ============================================================================
# OPENAPI DOCUMENTATION
# ============================================================================

ABTEST_API_TAGS = [
    {
        "name": "abtest",
        "description": "A/B testing endpoints for experiment management and metrics collection",
        "externalDocs": {
            "description": "A/B Testing Documentation",
            "url": "https://docs.datafoundry.com/abtest"
        }
    }
]

ABTEST_ENDPOINT_DESCRIPTIONS = {
    "create": """
    Create a new A/B test.

    This endpoint creates a new A/B test with the specified configuration:
    - Sets up control and variant treatments
    - Configures traffic split ratio
    - Initializes metrics collection

    **Configuration Options:**
    - test_name: Unique identifier for the test
    - variant_ratio: Fraction of traffic to route to variant (0.0-1.0)
    - control_name: Name for control treatment (default: "control")
    - variant_name: Name for variant treatment (default: "variant")

    **Security:**
    - Rate limited: 20 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Create new experiments for comparing treatments
    - Test different validation strategies
    - Compare AI model performance
    """,

    "list": """
    List all A/B tests.

    This endpoint returns all A/B tests with their metadata:
    - Test names and descriptions
    - Configuration settings
    - Creation timestamps
    - Status information

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Browse existing experiments
    - Monitor active tests
    - Retrieve test configurations
    """,

    "stats": """
    Get A/B test statistics.

    This endpoint returns traffic distribution statistics:
    - Total samples assigned
    - Control/variant sample counts
    - Actual vs configured ratios
    - Treatment distribution

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Monitor traffic distribution
    - Verify ratio configuration
    - Check sample accumulation
    """,

    "record": """
    Record a prediction for an A/B test.

    This endpoint records a prediction with optional ground truth:
    - Associates prediction with treatment
    - Tracks sample_id for metrics
    - Optionally records ground truth label
    - Updates treatment metrics

    **Recording Details:**
    - sample_id: Must be unique per sample
    - treatment: Must be registered treatment
    - prediction: Boolean prediction result
    - ground_truth: Optional true label

    **Security:**
    - Rate limited: 100 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Record treatment assignments
    - Track predictions for analysis
    - Accumulate metrics
    """,

    "metrics": """
    Get full A/B test metrics.

    This endpoint returns comprehensive metrics:
    - Per-treatment performance metrics
    - Precision, recall, F1, accuracy
    - Confusion matrices
    - Comparison between treatments

    **Metrics Include:**
    - Treatment-specific performance
    - Confusion matrix counts
    - Positive prediction rates
    - Comparison statistics

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Analyze treatment performance
    - Compare control vs variant
    - Generate experiment reports
    """,

    "export": """
    Export A/B test metrics as JSON.

    This endpoint exports all metrics data:
    - Full treatment metrics
    - Distribution statistics
    - Comparison data
    - Export metadata

    **Security:**
    - Rate limited: 20 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Download experiment data
    - Archive test results
    - External analysis
    """,

    "update_ratio": """
    Update variant traffic ratio (admin only).

    This endpoint adjusts the traffic split:
    - Changes variant_ratio dynamically
    - Requires admin privileges
    - Affects future assignments

    **Configuration Changes:**
    - variant_ratio: New ratio (0.0-1.0)
    - Admin role required
    - Immediate effect

    **Security:**
    - Rate limited: 10 requests/minute per IP
    - Admin access required

    **Use Cases:**
    - Gradual rollout adjustment
    - Rollback to control
    - Dynamic traffic optimization
    """
}
