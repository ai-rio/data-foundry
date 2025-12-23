"""
ML Predictor API Contracts - OpenAPI 3.0 Specification

Defines the contract for ML predictor endpoints following OpenAPI standards.
This implements a contract-first approach for API design and documentation.

SECURITY HARDENING - Week 4 Phase 2.4:
- Input validation via Pydantic models
- Size limits on request payloads (1MB single, 10MB batch)
- Field validators for score bounds
- Pattern reference: src/api/v1/signals/contracts.py, src/api/v1/quality/contracts.py
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# REQUEST MODELS
# ============================================================================

class PredictRequest(BaseModel):
    """Request model for quality score prediction on a single record."""
    record: Dict[str, Any] = Field(
        ...,
        description="Data record to predict quality score for. Can contain any fields.",
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
        Pattern reference: src/api/v1/signals/contracts.py:33-57
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


class PredictBatchRequest(BaseModel):
    """Request model for batch quality score prediction."""
    records: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of data records to predict quality scores for (max 1000 per batch)"
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
        Pattern reference: src/api/v1/signals/contracts.py:92-120
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


class ExtractFeaturesRequest(BaseModel):
    """Request model for feature extraction from a data record."""
    record: Dict[str, Any] = Field(
        ...,
        description="Data record to extract features from. Can contain any fields."
    )

    @field_validator('record')
    @classmethod
    def validate_record_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate record size to prevent memory exhaustion."""
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
                    "data_preview": "Looking for a tool for data analysis",
                    "raw_data": '{"text": "Can anyone recommend a good data analysis tool?"}',
                    "data_quality_score": 0.95,
                    "access_count": 150
                }
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class PredictResponse(BaseModel):
    """Response model for single record quality score prediction."""
    quality_score: float = Field(..., ge=0.0, le=1.0, description="Predicted quality score (0.0-1.0)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence (0.0-1.0)")
    feature_importance: Dict[str, float] = Field(
        default_factory=dict,
        description="Feature importance scores for the prediction"
    )
    prediction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional prediction metadata (model version, feature count, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "quality_score": 0.92,
                "confidence": 0.87,
                "feature_importance": {
                    "quality_score": 0.4,
                    "access_count": 0.2,
                    "text_length": 0.15,
                    "word_count": 0.1,
                    "source_type": 0.05,
                    "other": 0.1
                },
                "prediction_metadata": {
                    "model_version": "1.0.0",
                    "feature_count": 11
                }
            }
        }


class PredictBatchResponse(BaseModel):
    """Response model for batch quality score prediction."""
    results: List[PredictResponse] = Field(
        ...,
        description="Individual prediction results for each record"
    )
    total_records: int = Field(..., ge=0, description="Total number of records predicted")
    avg_quality_score: float = Field(..., ge=0.0, le=1.0, description="Average quality score across batch")
    avg_confidence: float = Field(..., ge=0.0, le=1.0, description="Average confidence across batch")

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "quality_score": 0.92,
                        "confidence": 0.87,
                        "feature_importance": {
                            "quality_score": 0.4,
                            "access_count": 0.2,
                            "text_length": 0.15
                        },
                        "prediction_metadata": {
                            "model_version": "1.0.0",
                            "feature_count": 11
                        }
                    },
                    {
                        "quality_score": 0.78,
                        "confidence": 0.75,
                        "feature_importance": {
                            "quality_score": 0.35,
                            "access_count": 0.25,
                            "text_length": 0.2
                        },
                        "prediction_metadata": {
                            "model_version": "1.0.0",
                            "feature_count": 11
                        }
                    }
                ],
                "total_records": 2,
                "avg_quality_score": 0.85,
                "avg_confidence": 0.81
            }
        }


class ModelInfoResponse(BaseModel):
    """Response model for model metadata."""
    model_version: str = Field(..., description="Model version identifier")
    model_type: str = Field(..., description="Model type/algorithm")
    last_trained: Optional[datetime] = Field(None, description="Last training date")
    feature_count: int = Field(..., ge=0, description="Number of features used by model")
    performance_metrics: Dict[str, float] = Field(
        default_factory=dict,
        description="Model performance metrics (accuracy, precision, recall, etc.)"
    )
    is_loaded: bool = Field(..., description="Whether model is currently loaded")

    class Config:
        json_schema_extra = {
            "example": {
                "model_version": "1.0.0",
                "model_type": "RandomForestClassifier",
                "last_trained": "2025-01-15T10:30:00Z",
                "feature_count": 11,
                "performance_metrics": {
                    "accuracy": 0.85,
                    "precision": 0.82,
                    "recall": 0.88
                },
                "is_loaded": True
            }
        }


class ExtractFeaturesResponse(BaseModel):
    """Response model for feature extraction."""
    features: Dict[str, Any] = Field(..., description="Extracted feature values")
    feature_count: int = Field(..., ge=0, description="Number of features extracted")
    extraction_time_ms: float = Field(..., ge=0.0, description="Time taken for extraction in milliseconds")

    class Config:
        json_schema_extra = {
            "example": {
                "features": {
                    "text_length": 150,
                    "word_count": 25,
                    "has_preview": 1,
                    "has_raw_data": 1,
                    "quality_score": 0.95,
                    "access_count": 150,
                    "source_type": 42,
                    "avg_word_length": 4.5,
                    "unique_word_ratio": 0.8
                },
                "feature_count": 9,
                "extraction_time_ms": 2.5
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
                "message": "Invalid request format",
                "details": {"field": "record", "issue": "required field missing"},
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
                "message": "Model reloaded successfully",
                "data": {"model_version": "1.0.0"},
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


# ============================================================================
# OPENAPI DOCUMENTATION
# ============================================================================

ML_API_TAGS = [
    {
        "name": "ml",
        "description": "ML predictor endpoints for quality scoring and feature extraction",
        "externalDocs": {
            "description": "ML Predictor Documentation",
            "url": "https://docs.datafoundry.com/ml"
        }
    }
]

ML_ENDPOINT_DESCRIPTIONS = {
    "predict": """
    Predict quality score for a single data record.

    This endpoint uses machine learning to predict the quality score of a data record:
    - Analyzes text content and metadata
    - Returns predicted quality score (0.0-1.0)
    - Provides confidence score for the prediction
    - Includes feature importance for interpretability

    **Prediction Features:**
    - Text-based features (length, word count, complexity)
    - Quality-based features (existing quality score, access count)
    - Source-based features (data source type)
    - Heuristic-based scoring for fast predictions

    **Security:**
    - Rate limited: 100 requests/minute per IP
    - Max record size: 1MB
    - Authentication required

    **Use Cases:**
    - Real-time quality scoring at data ingestion
    - Data quality assessment
    - Record prioritization for processing
    - Quality trend analysis
    """,

    "predict_batch": """
    Predict quality scores for multiple data records.

    This endpoint performs batch quality prediction on multiple records (up to 1000):
    - Processes all records independently
    - Returns individual results plus aggregate statistics
    - Provides average quality and confidence scores

    **Batch Processing:**
    - Maximum batch size: 1000 records
    - Maximum total batch size: 10MB
    - Each record is predicted independently
    - Aggregate statistics include averages

    **Security:**
    - Rate limited: 20 requests/minute per IP
    - Size limits enforced
    - Authentication required

    **Use Cases:**
    - Bulk quality scoring for historical data
    - Initial quality assessment for new datasets
    - Periodic quality analysis
    - Batch record processing
    """,

    "get_model_info": """
    Get current ML model metadata.

    This endpoint returns information about the currently loaded ML model:
    - Model version and type
    - Feature count
    - Performance metrics
    - Model load status

    **Model Information:**
    - Version: Model version identifier
    - Type: Algorithm used (e.g., RandomForestClassifier)
    - Features: Number of features used
    - Performance: Accuracy, precision, recall metrics
    - Status: Whether model is loaded

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Authentication required

    **Use Cases:**
    - Understanding model behavior
    - Model verification
    - Documentation generation
    - Debugging predictions
    """,

    "reload_model": """
    Reload the ML model from disk (admin only).

    This endpoint reloads the ML model:
    - Loads latest model from disk
    - Requires admin privileges
    - Returns updated model metadata

    **Model Reload:**
    - Unloads current model
    - Loads new model from configured path
    - Updates model metadata
    - Admin role required

    **Security:**
    - Rate limited: 10 requests/minute per IP
    - Admin access required
    - Thread-safe reload operation

    **Use Cases:**
    - Deploying new model versions
    - Model refresh without restart
    - A/B testing different models
    - Model rollback
    """,

    "extract_features": """
    Extract features from a data record.

    This endpoint extracts ML features from a data record:
    - Returns feature dictionary
    - Provides feature count
    - Includes extraction timing

    **Feature Extraction:**
    - Text-based features (length, word count, complexity)
    - Quality-based features (quality score, access count)
    - Source-based features (data source type)
    - Completeness features (field presence)

    **Security:**
    - Rate limited: 60 requests/minute per IP
    - Max record size: 1MB
    - Authentication required

    **Use Cases:**
    - Feature exploration
    - Building custom models
    - Understanding feature engineering
    - Debugging predictions
    """
}
