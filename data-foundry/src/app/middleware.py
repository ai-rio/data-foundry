"""
Middleware for Data Foundry application
"""

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings
from src.core.security import verify_token


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and set tenant context for multi-tenancy.
    """

    async def dispatch(self, request: Request, call_next):
        # Extract token from Authorization header
        authorization = request.headers.get("Authorization")
        tenant_id = None

        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
            try:
                payload = verify_token(token)
                tenant_id = payload.get("tenant_id")
            except Exception:
                # Invalid token - continue without tenant context
                pass

        # Set tenant context in request state
        request.state.tenant_id = tenant_id

        # Continue processing
        response = await call_next(request)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Basic rate limiting middleware.

    TODO: Implement proper rate limiting with Redis
    """

    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls  # Max calls per period
        self.period = period  # Period in seconds
        self.clients = {}  # In-memory store (use Redis in production)

    async def dispatch(self, request: Request, call_next):
        # Get client identifier
        client_id = self._get_client_id(request)

        # Check rate limit (basic implementation)
        if not self._is_allowed(client_id):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

        # Continue processing
        response = await call_next(request)
        return response

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get tenant ID first, then fall back to IP
        if hasattr(request.state, "tenant_id") and request.state.tenant_id:
            return f"tenant_{request.state.tenant_id}"

        # Get IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return f"ip_{forwarded_for.split(',')[0].strip()}"

        return f"ip_{request.client.host}"

    def _is_allowed(self, client_id: str) -> bool:
        """Check if client is allowed to make request."""
        import time

        now = time.time()

        # Clean old entries
        cutoff = now - self.period
        self.clients[client_id] = [
            timestamp
            for timestamp in self.clients.get(client_id, [])
            if timestamp > cutoff
        ]

        # Check if under limit
        if len(self.clients.get(client_id, [])) < self.calls:
            self.clients.setdefault(client_id, []).append(now)
            return True

        return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        # Remove server header for security
        if "server" in response.headers:
            del response.headers["server"]

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all requests for monitoring and debugging.
    """

    async def dispatch(self, request: Request, call_next):
        import logging
        import time

        logger = logging.getLogger("data_foundry.requests")

        start_time = time.time()

        # Log request
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "url": str(request.url),
                "client_ip": request.client.host,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "user_agent": request.headers.get("User-Agent"),
            },
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log response
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                    "tenant_id": getattr(request.state, "tenant_id", None),
                },
            )

            return response

        except Exception as e:
            # Log error
            duration = time.time() - start_time
            logger.error(
                "Request failed",
                extra={
                    "method": request.method,
                    "url": str(request.url),
                    "duration_ms": round(duration * 1000, 2),
                    "error": str(e),
                    "tenant_id": getattr(request.state, "tenant_id", None),
                },
                exc_info=True,
            )
            raise


class CORSMiddleware(BaseHTTPMiddleware):
    """
    Custom CORS middleware with tenant-aware origins.
    """

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")

        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response()
        else:
            response = await call_next(request)

        # Set CORS headers
        if origin and self._is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Tenant-ID"
            )

        return response

    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed."""
        # In production, check against allowed origins per tenant
        if settings.DEBUG:
            return True

        # Check against configured CORS origins
        allowed_origins = settings.CORS_ORIGINS
        return origin in allowed_origins


# Response type for OPTIONS
from fastapi import Response
