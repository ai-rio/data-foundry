"""
Rate limiting middleware for API endpoints.

Uses slowapi for token bucket rate limiting.
Configures different limits for different endpoint types.
"""

from fastapi import Request, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging


logger = logging.getLogger(__name__)


# Initialize rate limiter
# In production, this should use Redis storage for distributed rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/hour"],  # 200 requests per hour default
    storage_uri="memory://",  # In production, use Redis
    headers_enabled=True  # Include rate limit headers in response
)


# Rate limit configurations for different endpoint types
RATE_LIMITS = {
    "webhook": "100/minute",  # Webhooks: 100 per minute (high limit for burst traffic)
    "usage": "60/minute",     # Usage queries: 60 per minute
    "billing": "30/minute",   # Billing operations: 30 per minute
    "default": "200/hour"     # Default: 200 per hour
}


def get_rate_limit(endpoint_type: str = "default") -> str:
    """
    Get rate limit for endpoint type.

    Args:
        endpoint_type: Type of endpoint (webhook, usage, billing, default)

    Returns:
        Rate limit string (e.g., "60/minute")
    """
    return RATE_LIMITS.get(endpoint_type, RATE_LIMITS["default"])


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    """
    Handle rate limit exceeded errors.

    Args:
        request: FastAPI request
        exc: RateLimitExceeded exception

    Returns:
        HTTPException with 429 status
    """
    logger.warning(
        f"Rate limit exceeded for {request.client.host if request.client else 'unknown'}",
        extra={
            "path": request.url.path,
            "method": request.method
        }
    )

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please try again later.",
        headers={
            "Retry-After": str(exc.retry_after) if hasattr(exc, 'retry_after') else "60",
            "X-RateLimit-Limit": str(exc.detail.limit) if hasattr(exc, 'detail') else "",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(exc.detail.reset) if hasattr(exc, 'detail') else ""
        }
    )
