"""
Signal Detection API Router Implementation

Implements signal detection endpoints following REST principles and OpenAPI standards.
This handles HTTP requests, validation, and response formatting for signal detection operations.

SECURITY HARDENING - Week 4 Phase 2.3:
- CRITICAL #1: Rate limiting using in-memory IP tracker (sliding window)
- CRITICAL #2: Admin authorization on PUT /config
- CRITICAL #3: Tenant isolation checks
- CRITICAL #4: Thread safety with threading.Lock
- CRITICAL #5: Bounded memory using deque(maxlen=10000)
- HIGH #1: Request size validation (1MB max)
- Generic error messages (no information disclosure)
- Hashed user IDs in logs
- Async I/O with asyncio.to_thread

Pattern reference: src/api/v1/quality/router.py, src/api/v1/abtest/router.py
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
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.v1.signals.contracts import (
    # Request models
    DetectSignalRequest,
    DetectBatchRequest,
    UpdateSignalConfigRequest,
    # Response models
    DetectSignalResponse,
    DetectBatchResponse,
    SignalConfigResponse,
    SignalTypesResponse,
    SignalTypeInfo,
    ErrorResponse,
    # Documentation
    SIGNALS_API_TAGS,
    SIGNALS_ENDPOINT_DESCRIPTIONS,
)
from src.core.signal_detector import SignalDetector
from src.core.security import get_current_user_token

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/signals",
    tags=SIGNALS_API_TAGS,
    responses={404: {"model": ErrorResponse, "description": "Not found"}},
)


# ============================================================================
# DATA RECORD ADAPTER
# ============================================================================

class _DataRecordAdapter:
    """
    Adapter to convert dict to DataRecord-like interface for SignalDetector.

    SignalDetector expects a DataRecord object with specific attributes.
    This adapter provides that interface from a plain dict.
    """

    def __init__(self, record_dict: Dict[str, Any]):
        """
        Initialize adapter with record data.

        Args:
            record_dict: Dictionary containing record data
        """
        self.id = record_dict.get("id") or record_dict.get("record_id", "unknown")
        self.data_preview = record_dict.get("data_preview", "")
        self.extracted_text = record_dict.get("extracted_text") or self._extract_text_from_raw(record_dict.get("raw_data", ""))
        self.data_quality_score = record_dict.get("data_quality_score", 0.5)
        self.access_count = record_dict.get("access_count", 0)
        self.tenant_id = record_dict.get("tenant_id", "")
        self.data_source = record_dict.get("data_source", "unknown")

    @staticmethod
    def _extract_text_from_raw(raw_data: str) -> str:
        """Extract text from raw_data JSON string."""
        if not raw_data:
            return ""
        try:
            parsed = json.loads(raw_data)
            # Look for common text fields
            for key in ["text", "content", "description", "message", "body"]:
                if key in parsed and parsed[key]:
                    return str(parsed[key])
            # If no text field found, return the raw_data as-is (truncated)
            return raw_data[:500] if len(raw_data) > 500 else raw_data
        except (json.JSONDecodeError, TypeError):
            return raw_data[:500] if raw_data else ""


# ============================================================================
# RATE LIMITING CONFIGURATION (CRITICAL #1)
# ============================================================================

# Simple in-memory rate limiter to prevent DOS attacks
# Tracks requests per IP address with sliding window
# Pattern reference: src/api/v1/quality/router.py:68-125
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

async def _rate_limit_detect(request: Request) -> None:
    """Rate limit check for /detect endpoint: 100 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=100, window_seconds=60)


async def _rate_limit_batch(request: Request) -> None:
    """Rate limit check for /detect-batch endpoint: 20 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=20, window_seconds=60)


async def _rate_limit_read(request: Request) -> None:
    """Rate limit check for read endpoints: 60 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=60, window_seconds=60)


async def _rate_limit_admin(request: Request) -> None:
    """Rate limit check for admin endpoints: 10 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=10, window_seconds=60)


# ============================================================================
# IN-MEMORY CONFIGURATION STORAGE (CRITICAL #4: Thread Safety)
# ============================================================================

# WARNING: This is stored in-memory and will be lost on restart.
# Future enhancement: Persist to database for durability.
# CRITICAL #4: Thread safety added via locks
_config_lock = threading.Lock()

# Global configuration for the signal detector
# In production, this should be stored in a database or configuration service
_current_config = {
    "threshold": 70.0,  # Default threshold from SignalDetector
}


def get_current_config() -> Dict[str, float]:
    """Get the current signal detector configuration (thread-safe)."""
    with _config_lock:
        return _current_config.copy()


def update_current_config(config: Dict[str, float]) -> None:
    """Update the signal detector configuration with thread safety."""
    with _config_lock:
        _current_config.update(config)
    logger.info(f"Signal detector configuration updated: {config}")


# ============================================================================
# BOUNDED METRICS STORAGE (CRITICAL #5: Bounded Storage)
# ============================================================================

# WARNING: This is stored in-memory and will be lost on restart.
# Future enhancement: Persist to database for durability.
# CRITICAL #5: Using deque with maxlen to prevent unbounded memory growth
# CRITICAL #4: Thread safety added via lock
# Pattern reference: src/api/v1/quality/router.py:185-203
_metrics_lock = threading.Lock()

# In-memory storage for metrics with bounded size (max 10000 entries each)
# This prevents memory exhaustion from long-running processes
_metrics_storage = {
    "total_detections": 0,
    "signals_detected": 0,
    "should_analyze_count": 0,
    "signal_type_distribution": {},
    "signal_strengths": deque(maxlen=10000),
}


async def get_signal_metrics() -> Dict[str, Any]:
    """
    Get aggregated signal metrics.

    Returns aggregated metrics across all detections.
    """
    with _metrics_lock:
        storage = {
            "total_detections": _metrics_storage["total_detections"],
            "signals_detected": _metrics_storage["signals_detected"],
            "should_analyze_count": _metrics_storage["should_analyze_count"],
            "signal_type_distribution": _metrics_storage["signal_type_distribution"].copy(),
            "signal_strengths": list(_metrics_storage["signal_strengths"]),
        }

    # Calculate average signal strength
    avg_strength = 0.0
    if storage["signal_strengths"]:
        avg_strength = sum(storage["signal_strengths"]) / len(storage["signal_strengths"])

    return {
        "total_detections": storage["total_detections"],
        "signals_detected": storage["signals_detected"],
        "should_analyze_count": storage["should_analyze_count"],
        "signal_type_distribution": storage["signal_type_distribution"],
        "avg_signal_strength": round(avg_strength, 2),
    }


def update_metrics_storage(signal_result, signal_type: str) -> None:
    """Update metrics storage with signal detection result (thread-safe)."""
    with _metrics_lock:
        _metrics_storage["total_detections"] += 1

        if signal_type != "NONE":
            _metrics_storage["signals_detected"] += 1

        if signal_result.should_analyze:
            _metrics_storage["should_analyze_count"] += 1

        # Update distribution
        if signal_type in _metrics_storage["signal_type_distribution"]:
            _metrics_storage["signal_type_distribution"][signal_type] += 1
        else:
            _metrics_storage["signal_type_distribution"][signal_type] = 1

        # Store signal strength
        _metrics_storage["signal_strengths"].append(signal_result.signal_strength)


# ============================================================================
# SECURITY HELPER FUNCTIONS
# ============================================================================

def _hash_user_id(user_id: str) -> str:
    """
    Hash user ID for secure logging.

    Uses SHA-256 to hash user IDs before logging to prevent PII exposure.
    Pattern reference: src/api/v1/quality/router.py:284-290
    """
    return hashlib.sha256(user_id.encode('utf-8')).hexdigest()[:16]


async def _require_admin(current_user: dict = Depends(get_current_user_token)) -> dict:
    """
    Dependency to require admin role for sensitive operations (CRITICAL #2).

    Checks if the user has admin role. In production, this should query
    the database to get the user's current role rather than relying on
    JWT claims alone (which could be stale).

    TODO: Query database for current user role instead of using JWT claim
    Pattern reference: src/api/v1/quality/router.py:293-316
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
    Verify user can only access their own tenant's data (CRITICAL #3).

    Raises HTTPException if tenant_id in record doesn't match user's tenant.
    Pattern reference: src/api/v1/quality/router.py:319-336
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
    Pattern reference: src/api/v1/quality/router.py:343-352
    """
    global _rate_limiter
    with _rate_limiter._lock:
        _rate_limiter._requests.clear()


def reset_metrics_storage_for_testing() -> None:
    """
    Reset metrics storage to initial state for testing.

    Clears all accumulated metrics data. Use this in test fixtures
    to ensure test isolation.
    Pattern reference: src/api/v1/quality/router.py:355-372
    """
    global _metrics_storage
    with _metrics_lock:
        _metrics_storage = {
            "total_detections": 0,
            "signals_detected": 0,
            "should_analyze_count": 0,
            "signal_type_distribution": {},
            "signal_strengths": deque(maxlen=10000),
        }


def reset_config_for_testing() -> None:
    """
    Reset configuration to default values for testing.

    Restores config to default SignalDetector settings. Use this in test
    fixtures to ensure test isolation.
    Pattern reference: src/api/v1/quality/router.py:375-388
    """
    global _current_config
    with _config_lock:
        _current_config = {
            "threshold": 70.0,
        }


# ============================================================================
# ERROR HANDLING (Generic Error Messages)
# ============================================================================

def handle_signals_error(func):
    """Decorator for consistent error handling in signal endpoints.
    Pattern reference: src/api/v1/quality/router.py:395-424
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

async def get_detector() -> SignalDetector:
    """
    Dependency injection for signal detector with current configuration.

    Returns a SignalDetector instance configured with current settings.
    Pattern reference: src/api/v1/quality/router.py:431-442
    """
    config = get_current_config()
    return SignalDetector(threshold=config["threshold"])


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/detect",
    response_model=DetectSignalResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect signals in a single data record",
    description=SIGNALS_ENDPOINT_DESCRIPTIONS["detect"],
    responses={
        200: {"description": "Signals detected successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_signals_error
async def detect_signals(
    request: DetectSignalRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    detector: SignalDetector = Depends(get_detector),
    _rate_limit: None = Depends(_rate_limit_detect),  # CRITICAL #1
):
    """
    Detect opportunity signals in a single data record.

    Analyzes the record for opportunity signals using pattern matching
    and engagement metrics.
    """
    # CRITICAL #3: Tenant isolation check
    _check_tenant_access(request.record, current_user)

    # Create DataRecord adapter from request dict
    record_adapter = _DataRecordAdapter(request.record)

    # HIGH #3: Use asyncio.to_thread for blocking I/O
    result = await asyncio.to_thread(detector.detect_signals, record_adapter)

    # Update metrics storage
    update_metrics_storage(result, result.signal_type)

    # Hash user_id before logging
    logger.info(
        f"Signal detection completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"signal_type={result.signal_type}, strength={result.signal_strength:.2f}"
    )

    return DetectSignalResponse(
        signal_type=result.signal_type,
        signal_strength=result.signal_strength,
        evidence_snippets=result.evidence_snippets,
        engagement_metrics={
            "data_quality_score": result.engagement_metrics.get("data_quality_score", 0.0),
            "access_count": result.engagement_metrics.get("access_count", 0),
            "engagement_ratio": result.engagement_metrics.get("engagement_ratio", 0.0),
        },
        should_analyze=result.should_analyze
    )


@router.post(
    "/detect-batch",
    response_model=DetectBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect signals in multiple data records",
    description=SIGNALS_ENDPOINT_DESCRIPTIONS["detect_batch"],
    responses={
        200: {"description": "Batch detection completed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_signals_error
async def detect_signals_batch(
    request: DetectBatchRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    detector: SignalDetector = Depends(get_detector),
    _rate_limit: None = Depends(_rate_limit_batch),  # CRITICAL #1
):
    """
    Detect opportunity signals in multiple data records.

    Processes all records and returns individual results plus aggregate statistics.
    """
    results = []
    signals_detected = 0
    should_analyze_count = 0
    signal_type_distribution = {}

    # Validate each record
    for record in request.records:
        # CRITICAL #3: Tenant isolation check for each record
        _check_tenant_access(record, current_user)

        # Create DataRecord adapter
        record_adapter = _DataRecordAdapter(record)

        # HIGH #3: Use asyncio.to_thread for blocking I/O
        result = await asyncio.to_thread(detector.detect_signals, record_adapter)

        # Update metrics storage
        update_metrics_storage(result, result.signal_type)

        # Convert to response model
        result_response = DetectSignalResponse(
            signal_type=result.signal_type,
            signal_strength=result.signal_strength,
            evidence_snippets=result.evidence_snippets,
            engagement_metrics={
                "data_quality_score": result.engagement_metrics.get("data_quality_score", 0.0),
                "access_count": result.engagement_metrics.get("access_count", 0),
                "engagement_ratio": result.engagement_metrics.get("engagement_ratio", 0.0),
            },
            should_analyze=result.should_analyze
        )
        results.append(result_response)

        # Update counts
        if result.signal_type != "NONE":
            signals_detected += 1

        if result.should_analyze:
            should_analyze_count += 1

        # Update distribution
        if result.signal_type in signal_type_distribution:
            signal_type_distribution[result.signal_type] += 1
        else:
            signal_type_distribution[result.signal_type] = 1

    # Hash user_id before logging
    logger.info(
        f"Batch detection completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"total={len(request.records)}, signals_detected={signals_detected}, should_analyze={should_analyze_count}"
    )

    return DetectBatchResponse(
        results=results,
        total_records=len(request.records),
        signals_detected=signals_detected,
        should_analyze_count=should_analyze_count,
        signal_type_distribution=signal_type_distribution
    )


@router.get(
    "/config",
    response_model=SignalConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Get signal detector configuration",
    description=SIGNALS_ENDPOINT_DESCRIPTIONS["get_config"],
    responses={
        200: {"description": "Configuration retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_signals_error
async def get_config(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    _rate_limit: None = Depends(_rate_limit_read),  # CRITICAL #1
):
    """
    Get current signal detector configuration.

    Returns current threshold and enabled signal types.
    """
    config = get_current_config()

    # Hash user_id before logging
    logger.info(f"Configuration retrieved for user {_hash_user_id(current_user.get('user_id', 'unknown'))}")

    # Get available signal types from SignalDetector
    enabled_signal_types = list(SignalDetector.DEFAULT_OPPORTUNITY_PATTERNS.keys())

    return SignalConfigResponse(
        threshold=config["threshold"],
        enabled_signal_types=enabled_signal_types
    )


@router.put(
    "/config",
    response_model=SignalConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Update signal detector configuration (admin only)",
    description=SIGNALS_ENDPOINT_DESCRIPTIONS["update_config"],
    responses={
        200: {"description": "Configuration updated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid configuration"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_signals_error
async def update_config(
    request: UpdateSignalConfigRequest,
    http_request: Request,
    current_user: dict = Depends(_require_admin),  # CRITICAL #2: Admin check
    _rate_limit: None = Depends(_rate_limit_admin),  # CRITICAL #1
):
    """
    Update signal detector configuration.

    Updates the analysis threshold for subsequent detections.
    Requires administrator role.
    """
    # Validate the configuration by trying to create a detector
    try:
        test_detector = SignalDetector(threshold=request.threshold)
        # Test that it works with a minimal record
        test_record = _DataRecordAdapter({
            "id": "test",
            "data_preview": "test content",
            "raw_data": '{"text": "test content"}',
            "data_quality_score": 0.5,
            "access_count": 10,
        })
        test_result = test_detector.detect_signals(test_record)
    except ValueError as e:
        # Generic error message to client
        logger.error(f"Invalid configuration attempt: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid configuration values provided"
        )

    # Update the configuration
    new_config = {
        "threshold": request.threshold,
    }
    update_current_config(new_config)

    # Hash user_id before logging
    logger.info(
        f"Configuration updated by user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"threshold={request.threshold}"
    )

    # Return the updated configuration
    enabled_signal_types = list(SignalDetector.DEFAULT_OPPORTUNITY_PATTERNS.keys())

    return SignalConfigResponse(
        threshold=request.threshold,
        enabled_signal_types=enabled_signal_types
    )


@router.get(
    "/types",
    response_model=SignalTypesResponse,
    status_code=status.HTTP_200_OK,
    summary="List available signal types",
    description=SIGNALS_ENDPOINT_DESCRIPTIONS["get_types"],
    responses={
        200: {"description": "Signal types retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_signals_error
async def get_signal_types(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    _rate_limit: None = Depends(_rate_limit_read),  # CRITICAL #1
):
    """
    List all available signal types.

    Returns signal types with descriptions and example patterns.
    """
    # Get signal types from SignalDetector
    signal_types = []
    for signal_type, patterns in SignalDetector.DEFAULT_OPPORTUNITY_PATTERNS.items():
        # Create description based on signal type
        descriptions = {
            "TOOL_REQUEST": "User is explicitly requesting tool, software, or app recommendations",
            "PAIN_COMPLAINT": "User expresses frustration or pain points with current solutions",
            "PRICE_MENTION": "User mentions pricing, costs, or willingness to pay",
            "PROBLEM_SOLUTION": "User is seeking solutions to specific problems",
            "COMPARISON": "User is comparing different products, services, or approaches",
        }

        signal_types.append(SignalTypeInfo(
            name=signal_type,
            description=descriptions.get(signal_type, f"Signal type: {signal_type}"),
            patterns=patterns[:3]  # Show first 3 patterns as examples
        ))

    # Hash user_id before logging
    logger.info(
        f"Signal types retrieved for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"total_types={len(signal_types)}"
    )

    return SignalTypesResponse(
        signal_types=signal_types
    )
