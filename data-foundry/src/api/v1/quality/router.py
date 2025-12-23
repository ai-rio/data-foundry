"""
Data Quality API Router Implementation

Implements data quality validation endpoints following REST principles and OpenAPI standards.
This handles HTTP requests, validation, and response formatting for quality operations.

SECURITY HARDENING - Week 4 Phase 2.1 Fixes Applied:
- CRITICAL #1: Admin authorization on PUT /config
- CRITICAL #2: Rate limiting using in-memory IP tracker
- CRITICAL #3: Bounded memory using deque(maxlen)
- CRITICAL #4: Thread safety with threading.Lock
- CRITICAL #5: Tenant isolation checks
- CRITICAL #6: In-memory storage noted (full DB migration pending)
- HIGH #1: Generic error messages (no information disclosure)
- HIGH #2: Hashed user IDs in logs
- HIGH #3: Async I/O with asyncio.to_thread
- HIGH #4: Size limits on request records
"""

import asyncio
import functools
import hashlib
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from src.api.v1.quality.contracts import (
    # Request models
    ValidateRequest,
    ValidateBatchRequest,
    UpdateConfigRequest,
    # Response models
    ValidationResultResponse,
    ValidateBatchResponse,
    QualityMetricsResponse,
    QualityConfigResponse,
    ErrorResponse,
    SuccessResponse,
    # Documentation
    QUALITY_API_TAGS,
    QUALITY_ENDPOINT_DESCRIPTIONS,
)
from src.core.data_quality import DataQualityValidator
from src.core.security import get_current_user_token

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/quality",
    tags=QUALITY_API_TAGS,
    responses={404: {"model": ErrorResponse, "description": "Not found"}},
)


# ============================================================================
# RATE LIMITING CONFIGURATION (CRITICAL #2)
# ============================================================================

# Simple in-memory rate limiter to prevent DOS attacks
# Tracks requests per IP address with sliding window
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
# RATE LIMITING DEPENDENCIES (CRITICAL #2)
# ============================================================================

async def _rate_limit_validate(request: Request) -> None:
    """Rate limit check for /validate endpoint: 100 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=100, window_seconds=60)


async def _rate_limit_batch(request: Request) -> None:
    """Rate limit check for /validate-batch endpoint: 20 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=20, window_seconds=60)


async def _rate_limit_read(request: Request) -> None:
    """Rate limit check for read endpoints: 60 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=60, window_seconds=60)


async def _rate_limit_admin(request: Request) -> None:
    """Rate limit check for admin endpoints: 10 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=10, window_seconds=60)


# ============================================================================
# IN-MEMORY CONFIGURATION STORAGE (CRITICAL #6)
# ============================================================================

# WARNING: This is stored in-memory and will be lost on restart.
# Future enhancement: Persist to database for durability.
# CRITICAL #4: Thread safety added via locks
_config_lock = threading.Lock()

# Global configuration for the quality validator
# In production, this should be stored in a database or configuration service
_current_config = {
    "completeness_weight": DataQualityValidator.COMPLETENESS_WEIGHT,
    "validity_weight": DataQualityValidator.VALIDITY_WEIGHT,
    "error_penalty": DataQualityValidator.ERROR_PENALTY,
}


def get_current_config() -> Dict[str, float]:
    """Get the current quality validator configuration."""
    with _config_lock:
        return _current_config.copy()


def update_current_config(config: Dict[str, float]) -> None:
    """Update the quality validator configuration with thread safety."""
    with _config_lock:
        _current_config.update(config)
    logger.info(f"Quality validator configuration updated: {config}")


# ============================================================================
# BOUNDED METRICS STORAGE (CRITICAL #3, #4)
# ============================================================================

# WARNING: This is stored in-memory and will be lost on restart.
# Future enhancement: Persist to database for durability.
# CRITICAL #3: Using deque with maxlen to prevent unbounded memory growth
# CRITICAL #4: Thread safety added via lock
_metrics_lock = threading.Lock()

# In-memory storage for metrics with bounded size (max 10000 entries each)
# This prevents memory exhaustion from long-running processes
_metrics_storage = {
    "total_records": 0,
    "valid_records": 0,
    "invalid_records": 0,
    "quality_scores": deque(maxlen=10000),
    "completeness_scores": deque(maxlen=10000),
    "validity_scores": deque(maxlen=10000),
    "errors": deque(maxlen=10000),
}


async def get_quality_metrics() -> Dict[str, Any]:
    """
    Get aggregated quality metrics.

    Returns mock metrics for demonstration.
    In production, this would query a database or metrics service.
    """
    with _metrics_lock:
        storage = {
            "total_records": _metrics_storage["total_records"],
            "valid_records": _metrics_storage["valid_records"],
            "invalid_records": _metrics_storage["invalid_records"],
            "quality_scores": list(_metrics_storage["quality_scores"]),
            "completeness_scores": list(_metrics_storage["completeness_scores"]),
            "validity_scores": list(_metrics_storage["validity_scores"]),
            "errors": list(_metrics_storage["errors"]),
        }

    total = storage["total_records"]
    valid = storage["valid_records"]
    invalid = storage["invalid_records"]

    # Calculate averages
    avg_quality = (
        sum(storage["quality_scores"]) / len(storage["quality_scores"])
        if storage["quality_scores"] else 0.0
    )
    avg_completeness = (
        sum(storage["completeness_scores"]) / len(storage["completeness_scores"])
        if storage["completeness_scores"] else 0.0
    )
    avg_validity = (
        sum(storage["validity_scores"]) / len(storage["validity_scores"])
        if storage["validity_scores"] else 0.0
    )

    # Get common errors
    error_counts: Dict[str, int] = {}
    for error in storage["errors"]:
        error_counts[error] = error_counts.get(error, 0) + 1

    common_errors = [
        {"error": error, "count": count}
        for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    return {
        "total_records": total,
        "valid_records": valid,
        "invalid_records": invalid,
        "avg_quality_score": round(avg_quality, 2),
        "avg_completeness_score": round(avg_completeness, 2),
        "avg_validity_score": round(avg_validity, 2),
        "common_errors": common_errors
    }


def update_metrics_storage(validation_result) -> None:
    """Update metrics storage with validation result (thread-safe)."""
    with _metrics_lock:
        _metrics_storage["total_records"] += 1
        if validation_result.is_valid:
            _metrics_storage["valid_records"] += 1
        else:
            _metrics_storage["invalid_records"] += 1

        _metrics_storage["quality_scores"].append(validation_result.quality_score)
        _metrics_storage["completeness_scores"].append(validation_result.completeness_score)
        _metrics_storage["validity_scores"].append(validation_result.validity_score)

        for error in validation_result.errors:
            _metrics_storage["errors"].append(error)


# ============================================================================
# SECURITY HELPER FUNCTIONS
# ============================================================================

def _hash_user_id(user_id: str) -> str:
    """
    Hash user ID for secure logging (HIGH #2).

    Uses SHA-256 to hash user IDs before logging to prevent PII exposure.
    """
    return hashlib.sha256(user_id.encode('utf-8')).hexdigest()[:16]


async def _require_admin(current_user: dict = Depends(get_current_user_token)) -> dict:
    """
    Dependency to require admin role for sensitive operations (CRITICAL #1).

    Checks if the user has admin role. In production, this should query
    the database to get the user's current role rather than relying on
    JWT claims alone (which could be stale).

    TODO: Query database for current user role instead of using JWT claim
    """
    # For now, check if role is in token payload
    # Future: Query database to get current user role
    user_role = current_user.get("role")

    if user_role != "admin":
        logger.warning(
            f"Unauthorized config update attempt by user {_hash_user_id(current_user.get('user_id', 'unknown'))}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required for this operation"
        )

    return current_user


def _check_tenant_access(record: Dict[str, Any], current_user: dict) -> None:
    """
    Verify user can only access their own tenant's data (CRITICAL #5).

    Raises HTTPException if tenant_id in record doesn't match user's tenant.
    """
    user_tenant_id = current_user.get("tenant_id")
    record_tenant_id = record.get("tenant_id")

    if record_tenant_id and user_tenant_id and record_tenant_id != user_tenant_id:
        logger.warning(
            f"Tenant access denied: user {_hash_user_id(current_user.get('user_id', 'unknown'))} "
            f"attempted to access tenant {record_tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot access records from other tenants"
        )


# ============================================================================
# TEST ISOLATION HELPERS
# ============================================================================

def reset_rate_limiter_for_testing() -> None:
    """
    Reset the rate limiter to a fresh state for testing.

    Creates a new RateLimiter instance, clearing all IP request history.
    Use this in test fixtures to ensure test isolation.
    """
    global _rate_limiter
    with _rate_limiter._lock:
        _rate_limiter._requests.clear()


def reset_metrics_storage_for_testing() -> None:
    """
    Reset metrics storage to initial state for testing.

    Clears all accumulated metrics data. Use this in test fixtures
    to ensure test isolation.
    """
    global _metrics_storage
    with _metrics_lock:
        _metrics_storage = {
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "quality_scores": deque(maxlen=10000),
            "completeness_scores": deque(maxlen=10000),
            "validity_scores": deque(maxlen=10000),
            "errors": deque(maxlen=10000),
        }


def reset_config_for_testing() -> None:
    """
    Reset configuration to default values for testing.

    Restores config to DataQualityValidator defaults. Use this in test
    fixtures to ensure test isolation.
    """
    global _current_config
    with _config_lock:
        _current_config = {
            "completeness_weight": DataQualityValidator.COMPLETENESS_WEIGHT,
            "validity_weight": DataQualityValidator.VALIDITY_WEIGHT,
            "error_penalty": DataQualityValidator.ERROR_PENALTY,
        }


# ============================================================================
# ERROR HANDLING (HIGH #1 - Generic Error Messages)
# ============================================================================

def handle_quality_error(func):
    """Decorator for consistent error handling in quality endpoints."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            # HIGH #1: Log detailed error server-side, return generic message to client
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
            # HIGH #1: Log detailed error server-side, return generic message to client
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An internal error occurred. Please try again later."
            )
    return wrapper


# ============================================================================
# DEPENDENCIES
# ============================================================================

async def get_validator() -> DataQualityValidator:
    """
    Dependency injection for quality validator with current configuration.

    Returns a DataQualityValidator instance configured with current settings.
    """
    config = get_current_config()
    return DataQualityValidator(
        completeness_weight=config["completeness_weight"],
        validity_weight=config["validity_weight"],
        error_penalty=config["error_penalty"]
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/validate",
    response_model=ValidationResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate a single data record",
    description=QUALITY_ENDPOINT_DESCRIPTIONS["validate"],
    responses={
        200: {"description": "Record validated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_quality_error
async def validate_record(
    request: ValidateRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    validator: DataQualityValidator = Depends(get_validator),
    _rate_limit: None = Depends(_rate_limit_validate),  # CRITICAL #2
):
    """
    Validate a single data record.

    Performs comprehensive quality validation including:
    - Required field checks
    - Recommended field checks
    - Format validation (email, phone, timestamps)
    - Score calculation
    """
    # CRITICAL #5: Tenant isolation check
    _check_tenant_access(request.record, current_user)

    # HIGH #3: Use asyncio.to_thread for blocking I/O
    result = await asyncio.to_thread(validator.validate_record, request.record)

    # Update metrics storage
    update_metrics_storage(result)

    # Safely format scores for logging
    quality_score_str = f"{result.quality_score:.2f}" if isinstance(result.quality_score, (int, float)) else str(result.quality_score)

    # HIGH #2: Hash user_id before logging
    logger.info(
        f"Record validation completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"is_valid={result.is_valid}, quality_score={quality_score_str}"
    )

    return ValidationResultResponse(
        is_valid=result.is_valid,
        completeness_score=result.completeness_score,
        validity_score=result.validity_score,
        quality_score=result.quality_score,
        errors=result.errors,
        warnings=result.warnings
    )


@router.post(
    "/validate-batch",
    response_model=ValidateBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate multiple data records",
    description=QUALITY_ENDPOINT_DESCRIPTIONS["validate_batch"],
    responses={
        200: {"description": "Batch validated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_quality_error
async def validate_batch(
    request: ValidateBatchRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    validator: DataQualityValidator = Depends(get_validator),
    _rate_limit: None = Depends(_rate_limit_batch),  # CRITICAL #2
):
    """
    Validate multiple data records in a single request.

    Processes all records and returns individual results plus aggregate statistics.
    """
    results = []
    valid_count = 0
    invalid_count = 0
    quality_scores = []

    # Validate each record
    for record in request.records:
        # CRITICAL #5: Tenant isolation check for each record
        _check_tenant_access(record, current_user)

        # HIGH #3: Use asyncio.to_thread for blocking I/O
        result = await asyncio.to_thread(validator.validate_record, record)

        # Update metrics storage
        update_metrics_storage(result)

        # Convert to response model
        result_response = ValidationResultResponse(
            is_valid=result.is_valid,
            completeness_score=result.completeness_score,
            validity_score=result.validity_score,
            quality_score=result.quality_score,
            errors=result.errors,
            warnings=result.warnings
        )
        results.append(result_response)

        # Update counts
        if result.is_valid:
            valid_count += 1
        else:
            invalid_count += 1

        quality_scores.append(result.quality_score)

    # Calculate average quality score
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    # HIGH #2: Hash user_id before logging
    logger.info(
        f"Batch validation completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"total={len(request.records)}, valid={valid_count}, invalid={invalid_count}"
    )

    return ValidateBatchResponse(
        results=results,
        total_records=len(request.records),
        valid_count=valid_count,
        invalid_count=invalid_count,
        avg_quality_score=round(avg_quality, 2)
    )


@router.get(
    "/metrics",
    response_model=QualityMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get quality metrics",
    description=QUALITY_ENDPOINT_DESCRIPTIONS["metrics"],
    responses={
        200: {"description": "Metrics retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_quality_error
async def get_metrics(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    _rate_limit: None = Depends(_rate_limit_read),  # CRITICAL #2
):
    """
    Get aggregated quality metrics.

    Returns aggregate statistics across all processed records.
    """
    metrics = await get_quality_metrics()

    # HIGH #2: Hash user_id before logging
    logger.info(
        f"Metrics retrieved for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"total_records={metrics['total_records']}, "
        f"avg_quality_score={metrics['avg_quality_score']}"
    )

    return QualityMetricsResponse(**metrics)


@router.get(
    "/config",
    response_model=QualityConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Get quality validator configuration",
    description=QUALITY_ENDPOINT_DESCRIPTIONS["get_config"],
    responses={
        200: {"description": "Configuration retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_quality_error
async def get_config(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    _rate_limit: None = Depends(_rate_limit_read),  # CRITICAL #2
):
    """
    Get current quality validator configuration.

    Returns current weights and field lists.
    """
    config = get_current_config()

    # HIGH #2: Hash user_id before logging
    logger.info(f"Configuration retrieved for user {_hash_user_id(current_user.get('user_id', 'unknown'))}")

    return QualityConfigResponse(
        completeness_weight=config["completeness_weight"],
        validity_weight=config["validity_weight"],
        error_penalty=config["error_penalty"],
        required_fields=DataQualityValidator.REQUIRED_FIELDS.copy(),
        recommended_fields=DataQualityValidator.RECOMMENDED_FIELDS.copy()
    )


@router.put(
    "/config",
    response_model=QualityConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Update quality validator configuration",
    description=QUALITY_ENDPOINT_DESCRIPTIONS["update_config"],
    responses={
        200: {"description": "Configuration updated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid configuration"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_quality_error
async def update_config(
    request: UpdateConfigRequest,
    http_request: Request,
    current_user: dict = Depends(_require_admin),  # CRITICAL #1: Admin check
    _rate_limit: None = Depends(_rate_limit_admin),  # CRITICAL #2
):
    """
    Update quality validator configuration.

    Updates scoring weights and error penalties for subsequent validations.
    Requires administrator role.
    """
    # Validate the configuration by trying to create a validator
    try:
        test_validator = DataQualityValidator(
            completeness_weight=request.completeness_weight,
            validity_weight=request.validity_weight,
            error_penalty=request.error_penalty
        )
        # Test that it works
        test_result = test_validator.validate_record({
            "record_id": "test",
            "tenant_id": "test",
            "data_source": "test",
            "raw_data": "{}"
        })
    except ValueError as e:
        # HIGH #1: Generic error message to client
        logger.error(f"Invalid configuration attempt: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid configuration values provided"
        )

    # Update the configuration
    new_config = {
        "completeness_weight": request.completeness_weight,
        "validity_weight": request.validity_weight,
        "error_penalty": request.error_penalty
    }
    update_current_config(new_config)

    # HIGH #2: Hash user_id before logging
    logger.info(
        f"Configuration updated by user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"completeness={request.completeness_weight}, "
        f"validity={request.validity_weight}, "
        f"error_penalty={request.error_penalty}"
    )

    # Return the updated configuration
    return QualityConfigResponse(
        completeness_weight=request.completeness_weight,
        validity_weight=request.validity_weight,
        error_penalty=request.error_penalty,
        required_fields=DataQualityValidator.REQUIRED_FIELDS.copy(),
        recommended_fields=DataQualityValidator.RECOMMENDED_FIELDS.copy()
    )
