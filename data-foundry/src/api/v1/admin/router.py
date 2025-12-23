"""
Admin/Monitoring API Router Implementation - Week 4 Phase 2.5

Implements admin and monitoring endpoints following REST principles and OpenAPI standards.
This handles HTTP requests, validation, and response formatting for admin operations.

SECURITY HARDENING - Week 4 Phase 2.5:
- CRITICAL #1: Rate limiting using in-memory IP tracker (sliding window)
- CRITICAL #2: Admin authorization on POST /pipeline/trigger
- CRITICAL #4: Thread safety with threading.Lock
- CRITICAL #5: Bounded memory using deque(maxlen=10000)
- Generic error messages (no information disclosure)
- Hashed user IDs in logs
- Async I/O with asyncio.to_thread

Pattern reference: src/api/v1/signals/router.py (96/100 score)
"""

import asyncio
import functools
import hashlib
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.v1.admin.contracts import (
    # Request models
    TriggerPipelineRequest,
    # Response models
    DetailedHealthResponse,
    AggregatedMetricsResponse,
    PipelineStatusResponse,
    TriggerPipelineResponse,
    ComponentHealthStatus,
    ErrorResponse,
    # Documentation
    ADMIN_API_TAGS,
    ADMIN_ENDPOINT_DESCRIPTIONS,
)
from src.core.security import get_current_user_token
from src.tasks.ingestion import data_ingestion_flow

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/admin",
    tags=ADMIN_API_TAGS,
    responses={404: {"model": ErrorResponse, "description": "Not found"}},
)


# ============================================================================
# SYSTEM STARTUP TIME
# ============================================================================

_startup_time = time.time()


def get_system_uptime() -> float:
    """Get system uptime in seconds."""
    return time.time() - _startup_time


# ============================================================================
# RATE LIMITING CONFIGURATION (CRITICAL #1)
# ============================================================================

# Pattern reference: src/api/v1/signals/router.py:114-168
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
        """
        # Get client IP
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

async def _rate_limit_read(request: Request) -> None:
    """Rate limit check for read endpoints: 60 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=60, window_seconds=60)


async def _rate_limit_metrics(request: Request) -> None:
    """Rate limit check for metrics endpoints: 30 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=30, window_seconds=60)


async def _rate_limit_admin(request: Request) -> None:
    """Rate limit check for admin endpoints: 10 requests/minute."""
    _rate_limiter.check_rate_limit(request, max_requests=10, window_seconds=60)


# ============================================================================
# PIPELINE STATUS STORAGE (CRITICAL #4: Thread Safety)
# ============================================================================

# CRITICAL #4: Thread safety added via locks
# CRITICAL #5: Bounded storage using deque(maxlen=10000)
_pipeline_status_lock = threading.Lock()

# Current pipeline status
_current_pipeline_status = {
    "status": "idle",  # idle, running, completed, failed
    "last_run_id": None,
    "last_run_time": None,
    "last_run_stats": None,
    "active_runs": 0,
}

# Pipeline run history (bounded to 10000 entries)
_pipeline_runs: deque = deque(maxlen=10000)


def get_pipeline_status() -> Dict[str, Any]:
    """Get current pipeline status (thread-safe)."""
    with _pipeline_status_lock:
        return _current_pipeline_status.copy()


def update_pipeline_status(status_update: Dict[str, Any]) -> None:
    """Update pipeline status with thread safety."""
    with _pipeline_status_lock:
        _current_pipeline_status.update(status_update)


def add_pipeline_run(run_info: Dict[str, Any]) -> None:
    """Add a pipeline run to history (thread-safe, bounded)."""
    with _pipeline_status_lock:
        _pipeline_runs.append(run_info)


# ============================================================================
# HEALTH CHECK FUNCTIONS
# ============================================================================

async def _check_database_health() -> ComponentHealthStatus:
    """Check database health with latency measurement."""
    start_time = time.time()
    try:
        from src.core.config import settings
        import asyncpg

        # Simple connection test
        conn = await asyncio.wait_for(
            asyncpg.connect(settings.DATABASE_URL),
            timeout=5.0
        )
        latency_ms = (time.time() - start_time) * 1000
        await conn.close()

        return ComponentHealthStatus(
            name="database",
            status="healthy",
            latency_ms=round(latency_ms, 2),
            metadata={"pool_size": settings.DATABASE_POOL_SIZE}
        )
    except asyncio.TimeoutError:
        return ComponentHealthStatus(
            name="database",
            status="degraded",
            latency_ms=5000.0,
            error="Connection timeout"
        )
    except Exception as e:
        logger.warning(f"Database health check failed: {str(e)}")
        return ComponentHealthStatus(
            name="database",
            status="unhealthy",
            error="Connection failed"
        )


async def _check_redis_health() -> ComponentHealthStatus:
    """Check Redis health with latency measurement."""
    start_time = time.time()
    try:
        import redis.asyncio as aioredis
        from src.core.config import settings

        client = await aioredis.from_url(settings.REDIS_URL)
        await asyncio.wait_for(client.ping(), timeout=2.0)
        latency_ms = (time.time() - start_time) * 1000
        await client.close()

        return ComponentHealthStatus(
            name="redis",
            status="healthy",
            latency_ms=round(latency_ms, 2)
        )
    except asyncio.TimeoutError:
        return ComponentHealthStatus(
            name="redis",
            status="degraded",
            latency_ms=2000.0,
            error="Connection timeout"
        )
    except Exception as e:
        logger.warning(f"Redis health check failed: {str(e)}")
        return ComponentHealthStatus(
            name="redis",
            status="unhealthy",
            error="Connection failed"
        )


async def _check_label_studio_health() -> ComponentHealthStatus:
    """Check Label Studio health with latency measurement."""
    start_time = time.time()
    try:
        from src.core.config import settings

        # Simple URL check (can't make actual API call without valid credentials)
        import httpx
        async with httpx.AsyncClient() as client:
            response = await asyncio.wait_for(
                client.get(settings.LABEL_STUDIO_URL, timeout=5.0),
                timeout=5.0
            )
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code < 500:
                return ComponentHealthStatus(
                    name="label_studio",
                    status="healthy",
                    latency_ms=round(latency_ms, 2)
                )
            else:
                return ComponentHealthStatus(
                    name="label_studio",
                    status="degraded",
                    latency_ms=round(latency_ms, 2),
                    error=f"HTTP {response.status_code}"
                )
    except asyncio.TimeoutError:
        return ComponentHealthStatus(
            name="label_studio",
            status="degraded",
            latency_ms=5000.0,
            error="Connection timeout"
        )
    except Exception as e:
        logger.warning(f"Label Studio health check failed: {str(e)}")
        return ComponentHealthStatus(
            name="label_studio",
            status="unhealthy",
            error="Connection failed"
        )


async def _check_ai_providers_health() -> ComponentHealthStatus:
    """Check AI providers health."""
    try:
        from src.core.config import settings
        openai_configured = bool(settings.secure_openai_api_key())
        anthropic_configured = bool(settings.secure_anthropic_api_key())

        providers_configured = sum([openai_configured, anthropic_configured])

        if providers_configured > 0:
            return ComponentHealthStatus(
                name="ai_providers",
                status="healthy",
                metadata={
                    "openai_configured": openai_configured,
                    "anthropic_configured": anthropic_configured
                }
            )
        else:
            return ComponentHealthStatus(
                name="ai_providers",
                status="degraded",
                error="No AI providers configured"
            )
    except Exception as e:
        logger.warning(f"AI providers health check failed: {str(e)}")
        return ComponentHealthStatus(
            name="ai_providers",
            status="unhealthy",
            error="Configuration check failed"
        )


# ============================================================================
# SECURITY HELPER FUNCTIONS
# ============================================================================

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

    Checks if the user has admin role.
    Pattern reference: src/api/v1/signals/router.py:313-337
    """
    user_role = current_user.get("role")

    if user_role != "admin":
        logger.warning(
            f"Unauthorized pipeline trigger attempt by user {_hash_user_id(current_user.get('user_id', 'unknown'))}"
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
    Pattern reference: src/api/v1/signals/router.py:365-375
    """
    global _rate_limiter
    with _rate_limiter._lock:
        _rate_limiter._requests.clear()


def reset_pipeline_status_for_testing() -> None:
    """
    Reset pipeline status to initial state for testing.
    """
    global _current_pipeline_status, _pipeline_runs
    with _pipeline_status_lock:
        _current_pipeline_status = {
            "status": "idle",
            "last_run_id": None,
            "last_run_time": None,
            "last_run_stats": None,
            "active_runs": 0,
        }
        _pipeline_runs.clear()


# ============================================================================
# ERROR HANDLING (Generic Error Messages)
# ============================================================================

def handle_admin_error(func):
    """Decorator for consistent error handling in admin endpoints.
    Pattern reference: src/api/v1/signals/router.py:416-447
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error in {func.__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Validation failed: check request format and parameters"
            )
        except PermissionError as e:
            logger.error(f"Permission error in {func.__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An internal error occurred. Please try again later."
            )
    return wrapper


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get(
    "/health/detailed",
    response_model=DetailedHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detailed component health status",
    description=ADMIN_ENDPOINT_DESCRIPTIONS["health_detailed"],
    responses={
        200: {"description": "Health check completed"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_admin_error
async def get_detailed_health(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    _rate_limit: None = Depends(_rate_limit_read),
):
    """
    Get detailed health status of all system components.

    Checks database, Redis, Label Studio, and AI providers.
    """
    # Run health checks in parallel
    results = await asyncio.gather(
        _check_database_health(),
        _check_redis_health(),
        _check_label_studio_health(),
        _check_ai_providers_health(),
        return_exceptions=True
    )

    components = {}
    overall_status = "healthy"

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Health check error: {str(result)}")
            continue

        if isinstance(result, ComponentHealthStatus):
            components[result.name] = result
            if result.status == "unhealthy":
                overall_status = "unhealthy"
            elif result.status == "degraded" and overall_status == "healthy":
                overall_status = "degraded"

    # Hash user_id before logging
    logger.info(
        f"Health check completed for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"overall_status={overall_status}"
    )

    return DetailedHealthResponse(
        status=overall_status,
        components=components,
        uptime_seconds=round(get_system_uptime(), 2)
    )


@router.get(
    "/metrics/aggregated",
    response_model=AggregatedMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated metrics across all APIs",
    description=ADMIN_ENDPOINT_DESCRIPTIONS["metrics_aggregated"],
    responses={
        200: {"description": "Metrics retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_admin_error
async def get_aggregated_metrics(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    _rate_limit: None = Depends(_rate_limit_metrics),
):
    """
    Get aggregated metrics from all API modules.

    Collects metrics from quality, abtest, signals, ml APIs plus system metrics.
    """
    metrics = {
        "quality": None,
        "abtest": None,
        "signals": None,
        "ml": None,
        "system": None
    }

    # Try to get metrics from each API (may fail if not yet imported)
    try:
        from src.api.v1.quality.router import get_quality_metrics
        metrics["quality"] = await get_quality_metrics()
    except (ImportError, AttributeError):
        pass

    try:
        from src.api.v1.abtest.router import get_abtest_metrics
        metrics["abtest"] = await get_abtest_metrics()
    except (ImportError, AttributeError):
        pass

    try:
        from src.api.v1.signals.router import get_signal_metrics
        metrics["signals"] = await get_signal_metrics()
    except (ImportError, AttributeError):
        pass

    try:
        from src.api.v1.ml.router import get_ml_metrics
        metrics["ml"] = await get_ml_metrics()
    except (ImportError, AttributeError):
        pass

    # System metrics
    try:
        import psutil
        metrics["system"] = {
            "uptime_seconds": round(get_system_uptime(), 2),
            "memory_mb": round(psutil.virtual_memory().used / (1024 * 1024), 2),
            "cpu_percent": psutil.cpu_percent(interval=0.1)
        }
    except ImportError:
        # Fallback if psutil not available
        metrics["system"] = {
            "uptime_seconds": round(get_system_uptime(), 2),
            "memory_mb": None,
            "cpu_percent": None,
            "note": "psutil not available - install for full system metrics"
        }

    # Hash user_id before logging
    logger.info(
        f"Aggregated metrics retrieved for user {_hash_user_id(current_user.get('user_id', 'unknown'))}"
    )

    return AggregatedMetricsResponse(**metrics)


@router.get(
    "/pipeline/status",
    response_model=PipelineStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current pipeline status",
    description=ADMIN_ENDPOINT_DESCRIPTIONS["pipeline_status"],
    responses={
        200: {"description": "Pipeline status retrieved"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_admin_error
async def get_pipeline_status_endpoint(
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    _rate_limit: None = Depends(_rate_limit_metrics),
):
    """
    Get current data ingestion pipeline status.

    Returns status, last run info, and active runs.
    """
    status_data = get_pipeline_status()

    # Hash user_id before logging
    logger.info(
        f"Pipeline status retrieved for user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
        f"status={status_data['status']}"
    )

    return PipelineStatusResponse(**status_data)


@router.post(
    "/pipeline/trigger",
    response_model=TriggerPipelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger data ingestion pipeline (admin only)",
    description=ADMIN_ENDPOINT_DESCRIPTIONS["pipeline_trigger"],
    responses={
        200: {"description": "Pipeline triggered successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_admin_error
async def trigger_pipeline(
    request: TriggerPipelineRequest,
    http_request: Request,
    current_user: dict = Depends(_require_admin),  # CRITICAL #2: Admin check
    _rate_limit: None = Depends(_rate_limit_admin),
):
    """
    Trigger the data ingestion pipeline.

    Requires administrator role.
    """
    # Update pipeline status to running
    update_pipeline_status({
        "status": "running",
        "active_runs": _current_pipeline_status["active_runs"] + 1
    })

    try:
        # Trigger the flow (Prefect flows are sync but we call them in async context)
        # Use asyncio.to_thread to avoid blocking the event loop
        flow_result = await asyncio.to_thread(
            data_ingestion_flow,
            data_source=request.data_source,
            enable_validation=request.enable_validation,
            enable_ai_labeling=request.enable_ai_labeling,
            enable_pii_redaction=request.enable_pii_redaction,
            enable_human_review=request.enable_human_review,
        )

        # Update pipeline status
        run_id = str(flow_result.get("flow_run_id", f"manual-{int(time.time())}"))
        update_pipeline_status({
            "status": "completed",
            "last_run_id": run_id,
            "last_run_time": datetime.now(timezone.utc),
            "last_run_stats": flow_result,
            "active_runs": max(0, _current_pipeline_status["active_runs"] - 1)
        })

        # Add to history
        add_pipeline_run({
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stats": flow_result
        })

        # Hash user_id before logging
        logger.info(
            f"Pipeline triggered by user {_hash_user_id(current_user.get('user_id', 'unknown'))}: "
            f"run_id={run_id}, status=completed"
        )

        return TriggerPipelineResponse(
            message="Pipeline triggered successfully",
            flow_run_id=run_id,
            status="completed",
            parameters={
                "data_source": request.data_source,
                "enable_validation": request.enable_validation,
                "enable_ai_labeling": request.enable_ai_labeling,
                "enable_pii_redaction": request.enable_pii_redaction,
                "enable_human_review": request.enable_human_review,
            }
        )

    except Exception as e:
        # Update pipeline status to failed
        update_pipeline_status({
            "status": "failed",
            "active_runs": max(0, _current_pipeline_status["active_runs"] - 1)
        })

        # Re-raise for error handler to process
        raise
