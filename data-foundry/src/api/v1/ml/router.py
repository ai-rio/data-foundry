"""
ML Predictor API Router Implementation

Implements ML predictor endpoints following REST principles and OpenAPI standards.
This handles HTTP requests, validation, and response formatting for ML prediction operations.

SECURITY HARDENING - Week 4 Phase 2.4:
- CRITICAL #1: Rate limiting using in-memory IP tracker (sliding window)
- CRITICAL #2: Admin authorization on POST /model/reload
- CRITICAL #3: Tenant isolation checks (optional for ML predictions)
- CRITICAL #4: Thread safety with threading.Lock
- CRITICAL #5: Bounded memory using deque(maxlen=10000)
- HIGH #1: Request size validation (1MB max single, 10MB max batch)
- Generic error messages (no information disclosure)
- Hashed user IDs in logs
- Async I/O with asyncio.to_thread

Pattern reference: src/api/v1/signals/router.py (96/100 score pattern)
"""

import asyncio
import functools
import hashlib
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.v1.ml.contracts import (
    # Request models
    PredictRequest,
    PredictBatchRequest,
    ExtractFeaturesRequest,
    # Response models
    PredictResponse,
    PredictBatchResponse,
    ModelInfoResponse,
    ExtractFeaturesResponse,
    ErrorResponse,
    SuccessResponse,
    # Documentation
    ML_API_TAGS,
    ML_ENDPOINT_DESCRIPTIONS,
)
from src.core.ml_predictor import MLPredictor, FeatureExtractor
from src.core.security import get_current_user_token

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/ml",
    tags=ML_API_TAGS,
    responses={404: {"model": ErrorResponse, "description": "Not found"}},
)


# ============================================================================
# DATA RECORD ADAPTER
# ============================================================================

class _DataRecordAdapter:
    """
    Adapter to convert dict to record-like interface for MLPredictor.

    MLPredictor can handle both dict and DataRecord-like objects.
    This adapter ensures consistent interface.
    """

    def __init__(self, record_dict: Dict[str, Any]):
        """
        Initialize adapter with record data.

        Args:
            record_dict: Dictionary containing record data
        """
        self._record = record_dict

    def __getattr__(self, name: str) -> Any:
        """Get attribute from underlying dict."""
        return self._record.get(name)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from dict."""
        return self._record.get(key, default)


# ============================================================================
# RATE LIMITING CONFIGURATION (CRITICAL #1)
# ============================================================================
# Pattern reference: src/api/v1/signals/router.py:114-195

class RateLimiter:
    """Simple in-memory rate limiter with IP-based tracking."""

    def __init__(self):
        # Dictionary to track request timestamps per IP
        self._requests: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def check_rate_limit(self, request: Request, max_requests: int, window_seconds: int = 60) -> bool:
        """
        Check if the request is within rate limits.

        Args:
            request: FastAPI Request object
            max_requests: Maximum number of requests allowed
            window_seconds: Time window in seconds (default 60)

        Returns:
            True if within limit, raises HTTPException if exceeded

        Raises:
            HTTPException: If rate limit is exceeded (429)
        """
        # Get client IP
        # Check for forwarded headers first (proxy/load balancer)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        current_time = time.time()

        with self._lock:
            # Initialize deque for this IP if not exists
            if ip not in self._requests:
                self._requests[ip] = deque(maxlen=max_requests)

            # Clean up old requests outside the time window
            cutoff_time = current_time - window_seconds
            while self._requests[ip] and self._requests[ip][0] < cutoff_time:
                self._requests[ip].popleft()

            # Check if limit exceeded
            if len(self._requests[ip]) >= max_requests:
                logger.warning(f"Rate limit exceeded for IP: {ip}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later."
                )

            # Add current request timestamp
            self._requests[ip].append(current_time)
            return True


# Global rate limiter instance
_rate_limiter = RateLimiter()


# ============================================================================
# RATE LIMITING DEPENDENCIES (CRITICAL #1)
# ============================================================================

async def _rate_limit_predict(request: Request) -> None:
    """Rate limit check for /predict endpoint: 100 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=100, window_seconds=60)


async def _rate_limit_batch(request: Request) -> None:
    """Rate limit check for /predict-batch endpoint: 20 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=20, window_seconds=60)


async def _rate_limit_read(request: Request) -> None:
    """Rate limit check for read endpoints: 60 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=60, window_seconds=60)


async def _rate_limit_admin(request: Request) -> None:
    """Rate limit check for admin endpoints: 10 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=10, window_seconds=60)


# ============================================================================
# MODEL STATE MANAGEMENT (CRITICAL #4: Thread Safety)
# ============================================================================

# Thread-safe model management
# Pattern reference: src/api/v1/signals/router.py:205-224
_model_lock = threading.Lock()
_global_predictor: Optional[MLPredictor] = None


def get_global_predictor() -> MLPredictor:
    """Get or create global MLPredictor instance (thread-safe)."""
    global _global_predictor
    with _model_lock:
        if _global_predictor is None:
            _global_predictor = MLPredictor()
        return _global_predictor


# ============================================================================
# BOUNDED METRICS STORAGE (CRITICAL #5: Bounded Storage)
# ============================================================================

# Pattern reference: src/api/v1/signals/router.py:236-246
_metrics_lock = threading.Lock()

# In-memory storage for metrics with bounded size (max 10000 entries each)
# This prevents memory exhaustion from long-running processes
_metrics_storage = {
    "total_predictions": 0,
    "quality_scores": deque(maxlen=10000),
    "confidences": deque(maxlen=10000),
}


async def get_ml_metrics() -> Dict[str, Any]:
    """
    Get aggregated ML metrics.

    Returns aggregated metrics across all predictions.
    """
    with _metrics_lock:
        storage = {
            "total_predictions": _metrics_storage["total_predictions"],
            "quality_scores": list(_metrics_storage["quality_scores"]),
            "confidences": list(_metrics_storage["confidences"]),
        }

    # Calculate averages
    avg_quality = 0.0
    avg_confidence = 0.0

    if storage["quality_scores"]:
        avg_quality = sum(storage["quality_scores"]) / len(storage["quality_scores"])

    if storage["confidences"]:
        avg_confidence = sum(storage["confidences"]) / len(storage["confidences"])

    return {
        "total_predictions": storage["total_predictions"],
        "avg_quality_score": round(avg_quality, 3),
        "avg_confidence": round(avg_confidence, 3),
    }


def update_metrics_storage(quality_score: float, confidence: float) -> None:
    """Update metrics storage with prediction result (thread-safe)."""
    with _metrics_lock:
        _metrics_storage["total_predictions"] += 1
        _metrics_storage["quality_scores"].append(quality_score)
        _metrics_storage["confidences"].append(confidence)


# ============================================================================
# SECURITY HELPER FUNCTIONS
# ============================================================================
# Pattern reference: src/api/v1/signals/router.py:303-358

def _hash_user_id(user_id: str) -> str:
    """
    Hash user ID for secure logging.

    Uses SHA-256 to hash user IDs before logging to prevent PII exposure.
    Pattern reference: src/api/v1/signals/router.py:303-310
    """
    return hashlib.sha256(user_id.encode('utf-8')).hexdigest()[:16]


async def _require_admin(current_user: dict = Depends(get_current_user_token)) -> dict:
    """
    Dependency to require admin role for sensitive operations (CRITICAL #2).

    Checks if the user has admin role. In production, this should query
    the database to get the user's current role rather than relying on
    JWT claims alone (which could be stale).

    TODO: Query database for current user role instead of using JWT claim
    Pattern reference: src/api/v1/signals/router.py:313-337
    """
    # For now, check if role is in token payload
    # Future: Query database to get current user role
    user_role = current_user.get("role")

    if user_role != "admin":
        logger.warning(
            f"Unauthorized model reload attempt by user {_hash_user_id(current_user.get('user_id', 'unknown'))}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required for this operation"
        )

    return current_user


# ============================================================================
# TEST ISOLATION HELPERS
# ============================================================================

def reset_rate_limiter_for_testing() -> None:
    """
    Reset the rate limiter to a fresh state for testing.

    Creates a new RateLimiter instance, clearing all IP request history.
    Use this in test fixtures to ensure test isolation.
    Pattern reference: src/api/v1/signals/router.py:365-375
    """
    global _rate_limiter
    with _rate_limiter._lock:
        _rate_limiter._requests.clear()


def reset_metrics_storage_for_testing() -> None:
    """
    Reset metrics storage to initial state for testing.

    Clears all accumulated metrics data. Use this in test fixtures
    to ensure test isolation.
    Pattern reference: src/api/v1/signals/router.py:378-394
    """
    global _metrics_storage
    with _metrics_lock:
        _metrics_storage = {
            "total_predictions": 0,
            "quality_scores": deque(maxlen=10000),
            "confidences": deque(maxlen=10000),
        }


def reset_model_state_for_testing() -> None:
    """
    Reset model state to initial state for testing.

    Clears the global predictor instance. Use this in test fixtures
    to ensure test isolation.
    """
    global _global_predictor
    with _model_lock:
        _global_predictor = None


# ============================================================================
# ERROR HANDLING (Generic Error Messages)
# ============================================================================

def handle_ml_error(func):
    """Decorator for consistent error handling in ML endpoints.
    Pattern reference: src/api/v1/signals/router.py:416-447
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            # Log detailed error server-side, return generic message to client
            logger.warning(f"Validation error in {func.__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Validation failed: check request format and data"
            )
        except PermissionError as e:
            logger.error(f"Permission error in {func.__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            # Log detailed error server-side, return generic message to client
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An internal error occurred. Please try again later."
            )
    return wrapper


# ============================================================================
# DEPENDENCIES
# ============================================================================

async def get_predictor() -> MLPredictor:
    """
    Dependency injection for ML predictor.

    Returns the global MLPredictor instance.
    Pattern reference: src/api/v1/signals/router.py:454-462
    """
    return get_global_predictor()


async def get_feature_extractor() -> FeatureExtractor:
    """
    Dependency injection for feature extractor.

    Returns a new FeatureExtractor instance.
    """
    return FeatureExtractor()


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict quality score for a single data record",
    description=ML_ENDPOINT_DESCRIPTIONS["predict"],
    responses={
        200: {"description": "Prediction completed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_ml_error
async def predict_quality(
    request: PredictRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    predictor: MLPredictor = Depends(get_predictor),
    _rate_limit: None = Depends(_rate_limit_predict),  # CRITICAL #1
):
    """
    Predict quality score for a single data record.

    Uses ML model to predict the quality score of the record.
    """
    # Create adapter from request dict
    record_adapter = _DataRecordAdapter(request.record)

    # Use asyncio.to_thread for blocking I/O
    result = await asyncio.to_thread(predictor.predict, record_adapter)

    # Update metrics storage
    update_metrics_storage(result.quality_score, result.confidence)

    # Hash user_id before logging
    logger.info(
        f"Prediction completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"quality_score={result.quality_score:.3f}, confidence={result.confidence:.3f}"
    )

    return PredictResponse(
        quality_score=result.quality_score,
        confidence=result.confidence,
        feature_importance=result.feature_importance,
        prediction_metadata=result.prediction_metadata
    )


@router.post(
    "/predict-batch",
    response_model=PredictBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict quality scores for multiple data records",
    description=ML_ENDPOINT_DESCRIPTIONS["predict_batch"],
    responses={
        200: {"description": "Batch prediction completed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_ml_error
async def predict_quality_batch(
    request: PredictBatchRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    predictor: MLPredictor = Depends(get_predictor),
    _rate_limit: None = Depends(_rate_limit_batch),  # CRITICAL #1
):
    """
    Predict quality scores for multiple data records.

    Processes all records and returns individual results plus aggregate statistics.
    """
    results = []
    total_quality = 0.0
    total_confidence = 0.0

    for record in request.records:
        # Create adapter
        record_adapter = _DataRecordAdapter(record)

        # Use asyncio.to_thread for blocking I/O
        result = await asyncio.to_thread(predictor.predict, record_adapter)

        # Update metrics storage
        update_metrics_storage(result.quality_score, result.confidence)

        # Convert to response model
        result_response = PredictResponse(
            quality_score=result.quality_score,
            confidence=result.confidence,
            feature_importance=result.feature_importance,
            prediction_metadata=result.prediction_metadata
        )
        results.append(result_response)

        # Update totals
        total_quality += result.quality_score
        total_confidence += result.confidence

    # Calculate averages
    avg_quality = total_quality / len(request.records) if request.records else 0.0
    avg_confidence = total_confidence / len(request.records) if request.records else 0.0

    # Hash user_id before logging
    logger.info(
        f"Batch prediction completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"total={len(request.records)}, avg_quality={avg_quality:.3f}, avg_confidence={avg_confidence:.3f}"
    )

    return PredictBatchResponse(
        results=results,
        total_records=len(request.records),
        avg_quality_score=round(avg_quality, 3),
        avg_confidence=round(avg_confidence, 3)
    )


@router.get(
    "/model/info",
    response_model=ModelInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ML model metadata",
    description=ML_ENDPOINT_DESCRIPTIONS["get_model_info"],
    responses={
        200: {"description": "Model info retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_ml_error
async def get_model_info(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    predictor: MLPredictor = Depends(get_predictor),
    _rate_limit: None = Depends(_rate_limit_read),  # CRITICAL #1
):
    """
    Get current ML model metadata.

    Returns information about the currently loaded model.
    """
    # Get model metadata
    metadata = predictor.get_model_metadata()

    # Hash user_id before logging
    logger.info(
        f"Model info retrieved for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"version={metadata.model_version}, loaded={metadata.is_loaded}"
    )

    return ModelInfoResponse(
        model_version=metadata.model_version,
        model_type=metadata.model_type,
        last_trained=metadata.last_trained,
        feature_count=metadata.feature_count,
        performance_metrics=metadata.performance_metrics,
        is_loaded=metadata.is_loaded
    )


@router.post(
    "/model/reload",
    response_model=ModelInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Reload the ML model from disk (admin only)",
    description=ML_ENDPOINT_DESCRIPTIONS["reload_model"],
    responses={
        200: {"description": "Model reloaded successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_ml_error
async def reload_model(
    http_request: Request,
    current_user: dict = Depends(_require_admin),  # CRITICAL #2: Admin check
    _rate_limit: None = Depends(_rate_limit_admin),  # CRITICAL #1
):
    """
    Reload the ML model from disk.

    Reloads the model and requires administrator role.
    """
    # Get predictor and reload model (async I/O for blocking call)
    predictor = get_global_predictor()
    metadata = await asyncio.to_thread(predictor.reload_model)

    # Update global predictor reference
    global _global_predictor
    with _model_lock:
        _global_predictor = predictor

    # Hash user_id before logging
    logger.info(
        f"Model reloaded by user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"version={metadata.model_version}, loaded={metadata.is_loaded}"
    )

    return ModelInfoResponse(
        model_version=metadata.model_version,
        model_type=metadata.model_type,
        last_trained=metadata.last_trained,
        feature_count=metadata.feature_count,
        performance_metrics=metadata.performance_metrics,
        is_loaded=metadata.is_loaded
    )


@router.post(
    "/features/extract",
    response_model=ExtractFeaturesResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract features from a data record",
    description=ML_ENDPOINT_DESCRIPTIONS["extract_features"],
    responses={
        200: {"description": "Features extracted successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_ml_error
async def extract_features(
    request: ExtractFeaturesRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    extractor: FeatureExtractor = Depends(get_feature_extractor),
    _rate_limit: None = Depends(_rate_limit_read),  # CRITICAL #1
):
    """
    Extract features from a data record.

    Returns extracted features for analysis or custom modeling.
    """
    # Create adapter from request dict
    record_adapter = _DataRecordAdapter(request.record)

    # Use asyncio.to_thread for blocking I/O
    result = await asyncio.to_thread(extractor.extract_features, record_adapter)

    # Hash user_id before logging
    logger.info(
        f"Feature extraction completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"feature_count={result.feature_count}, time_ms={result.extraction_time_ms:.2f}"
    )

    return ExtractFeaturesResponse(
        features=result.features,
        feature_count=result.feature_count,
        extraction_time_ms=result.extraction_time_ms
    )
