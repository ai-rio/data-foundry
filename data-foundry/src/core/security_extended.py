"""
Extended Security Module for Cost Service

Provides additional security controls for cost calculations:
- Tenant validation for billing operations
- Input sanitization for cost parameters
- Rate limiting for cost calculations
- Security decorators for cost service
"""

import logging
import os
import secrets
import re
import time
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
from functools import wraps

logger = logging.getLogger(__name__)

# Import base security functions
from .security import verify_api_key, create_tenant_token


class SecurityError(Exception):
    """Raised when security validation fails."""
    pass


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass


@dataclass
class SecurityContext:
    """Security context for cost calculations."""
    tenant_id: str
    user_id: Optional[str]
    request_id: str
    ip_address: Optional[str]
    timestamp: datetime
    permissions: Dict[str, bool]


class CostSecurityValidator:
    """Security validator specifically for cost calculations."""

    def __init__(
        self,
        enable_rate_limiting: bool = True,
        max_requests_per_minute: int = 1000,
        max_cost_per_hour: Optional[Decimal] = None
    ):
        self.enable_rate_limiting = enable_rate_limiting
        self.max_requests_per_minute = max_requests_per_minute
        self.max_cost_per_hour = max_cost_per_hour or Decimal("1000.00")

        # Rate limiting storage
        self._rate_limits: Dict[str, List[float]] = {}
        self._cost_trackers: Dict[str, tuple[Decimal, float]] = {}

        # Security patterns to block
        self._dangerous_patterns = [
            r"<script[^>]*>.*?</script>",
            r"union\s+select",
            r"drop\s+table",
            r"javascript:",
            r"data:text/html",
        ]

        # Approved models
        self._approved_models = {
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
            "claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku",
            "gemini-1.5-pro", "gemini-1.5-flash",
            "mistral-large", "mistral-medium", "mistral-small",
            "command-r-plus", "command-r"
        }

    def validate_tenant_billing_access(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> SecurityContext:
        """
        Validate tenant has billing access.
        Critical for preventing unauthorized billing calculations.
        """
        # Validate tenant_id format
        if not tenant_id or not isinstance(tenant_id, str):
            raise SecurityError("Invalid tenant ID")

        if len(tenant_id) > 255 or not re.match(r'^[a-zA-Z0-9_-]+$', tenant_id):
            raise SecurityError("Tenant ID contains invalid characters")

        # If API key provided, verify it
        if api_key:
            if not verify_api_key(api_key, tenant_id):
                raise SecurityError("Invalid API key for tenant")

        # Create security context
        context = SecurityContext(
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=secrets.token_urlsafe(16),
            ip_address=os.getenv("REQUEST_IP"),
            timestamp=datetime.utcnow(),
            permissions={"billing": True}
        )

        # Check rate limits
        if self.enable_rate_limiting:
            self._check_rate_limit(context)

        logger.info(f"Billing access validated for tenant {tenant_id}")
        return context

    def validate_cost_parameters(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate cost calculation parameters."""
        # Validate model
        if not model or not isinstance(model, str):
            raise SecurityError("Invalid model name")

        if model not in self._approved_models:
            raise SecurityError(f"Model {model} is not approved for billing")

        # Validate token counts
        if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
            raise SecurityError("Token counts must be integers")

        if prompt_tokens < 0 or completion_tokens < 0:
            raise SecurityError("Token counts cannot be negative")

        # Check for excessive usage
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens > 10000000:  # 10M tokens per request
            raise SecurityError(f"Excessive token count: {total_tokens}")

        # Sanitize metadata
        validated_metadata = {}
        if metadata:
            validated_metadata = self._sanitize_metadata(metadata)

        return validated_metadata

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize metadata to prevent injection."""
        sanitized = {}

        for key, value in metadata.items():
            # Validate key
            if not isinstance(key, str) or len(key) > 100:
                continue

            # Sanitize key
            safe_key = self._sanitize_string(key, 100)
            if not safe_key:
                continue

            # Validate value
            if isinstance(value, str):
                safe_value = self._sanitize_string(value, 1000)
                sanitized[safe_key] = safe_value
            elif isinstance(value, (int, float, bool)):
                sanitized[safe_key] = value
            elif isinstance(value, Decimal):
                sanitized[safe_key] = str(value)
            elif isinstance(value, dict):
                sanitized[safe_key] = self._sanitize_metadata(value)

        return sanitized

    def _sanitize_string(self, value: str, max_length: int = 255) -> str:
        """Sanitize string input."""
        if not value or not isinstance(value, str):
            return ""

        # Remove null bytes
        value = value.replace('\x00', '')

        # Check for dangerous patterns
        for pattern in self._dangerous_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                raise SecurityError(f"Input contains dangerous pattern: {pattern}")

        # Remove control characters except newlines and tabs
        value = ''.join(c for c in value if c.isprintable() or c in '\n\t')

        # Truncate and strip
        return value[:max_length].strip()

    def _check_rate_limit(self, context: SecurityContext):
        """Check if tenant exceeded rate limits."""
        now = time.time()
        minute_ago = now - 60

        # Clean old entries
        if context.tenant_id in self._rate_limits:
            self._rate_limits[context.tenant_id] = [
                ts for ts in self._rate_limits[context.tenant_id]
                if ts > minute_ago
            ]
        else:
            self._rate_limits[context.tenant_id] = []

        # Check limit
        recent_requests = len(self._rate_limits[context.tenant_id])
        if recent_requests >= self.max_requests_per_minute:
            raise RateLimitError(f"Rate limit exceeded: {recent_requests}/min")

        # Add current request
        self._rate_limits[context.tenant_id].append(now)


# Global validator instance
_cost_security_validator: Optional[CostSecurityValidator] = None


def get_cost_security_validator() -> CostSecurityValidator:
    """Get singleton cost security validator."""
    global _cost_security_validator
    if _cost_security_validator is None:
        _cost_security_validator = CostSecurityValidator()
    return _cost_security_validator


# Security decorators
def require_billing_access(func):
    """Decorator to require billing access validation."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        tenant_id = kwargs.get('tenant_id')
        if not tenant_id:
            raise SecurityError("Tenant ID required for billing operations")

        # Validate billing access
        validator = get_cost_security_validator()
        context = validator.validate_tenant_billing_access(
            tenant_id=tenant_id,
            user_id=kwargs.get('user_id'),
            api_key=kwargs.get('api_key')
        )

        # Add context
        kwargs['security_context'] = context

        return await func(*args, **kwargs)
    return wrapper


def validate_cost_inputs(func):
    """Decorator to validate cost calculation inputs."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        validator = get_cost_security_validator()

        # Validate parameters
        validated_metadata = validator.validate_cost_parameters(
            model=kwargs.get('model', ''),
            prompt_tokens=kwargs.get('prompt_tokens', 0),
            completion_tokens=kwargs.get('completion_tokens', 0),
            metadata=kwargs.get('metadata')
        )

        # Update with validated metadata
        kwargs['metadata'] = validated_metadata

        return await func(*args, **kwargs)
    return wrapper


# Export functions
def validate_tenant_access(tenant_id: str, **kwargs) -> SecurityContext:
    """Validate tenant billing access."""
    validator = get_cost_security_validator()
    return validator.validate_tenant_billing_access(tenant_id, **kwargs)


def encrypt_sensitive_data(data: str) -> str:
    """Encrypt sensitive data (placeholder)."""
    # In production, use proper encryption
    import hashlib
    import hmac
    key = os.getenv("ENCRYPTION_KEY", secrets.token_bytes(32))
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()


__all__ = [
    "SecurityError",
    "RateLimitError",
    "SecurityContext",
    "CostSecurityValidator",
    "validate_tenant_access",
    "encrypt_sensitive_data",
    "require_billing_access",
    "validate_cost_inputs",
    "get_cost_security_validator"
]