"""
Custom exception hierarchy for Stripe service operations.

This module defines a comprehensive exception hierarchy for Stripe service errors,
providing rich context for debugging, logging, and error handling.

Exception Hierarchy:
    StripeServiceError (base)
    ├── StripeInitializationError
    ├── StripeAPIError
    │   ├── StripeRateLimitError
    │   └── StripeServerError
    ├── StripeCustomerError
    │   ├── StripeCustomerNotFoundError
    │   └── StripeCustomerExistsError
    ├── StripeMeterError
    │   ├── StripeMeterValidationError
    │   └── StripeMeterQuotaError
    ├── StripeIdempotencyError
    │   └── StripeIdempotencyKeyTooLongError
    └── StripeBatchError

All exceptions support serialization via to_dict() method for logging and API responses.

SECURITY: Sensitive data (API keys, passwords, tokens) is automatically redacted
from to_dict() output to prevent credential leakage in logs and error responses.
"""

from typing import Optional, Any, Dict
import re


# ============================================================================
# Sensitive Data Sanitization
# ============================================================================

# Patterns to detect and redact sensitive data
# These patterns are applied to all exception messages before serialization
SENSITIVE_PATTERNS = [
    # Stripe API keys - matches sk_test_*, sk_live_*, rk_test_*, rk_live_* formats
    # Pattern: prefix + underscore + alphanumeric/underscore (minimum 10 chars total after prefix)
    (r'\bsk_[a-zA-Z0-9_]{10,}', '**REDACTED_API_KEY**'),
    (r'\brk_[a-zA-Z0-9_]{10,}', '**REDACTED_API_KEY**'),
    # Bearer tokens and similar auth tokens
    (r'Bearer\s+[a-zA-Z0-9\._\-]+', 'Bearer **REDACTED_TOKEN**'),
    # Passwords in various formats
    (r'password["\']?\s*[:=]\s*["\']?[^\s\'"]+', 'password:**REDACTED**'),
    (r'Password["\']?\s*[:=]\s*["\']?[^\s\'"]+', 'Password:**REDACTED**'),
    # Token patterns - more flexible to catch "Token: abc123xyz456"
    (r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9]{10,}', 'token:**REDACTED**'),
    (r'Token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9]{10,}', 'Token:**REDACTED**'),
    # API key patterns (generic)
    (r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9]{10,}', 'api_key:**REDACTED**'),
    (r'api[_-]?Key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9]{10,}', 'api_Key:**REDACTED**'),
    # Secret patterns
    (r'secret["\']?\s*[:=]\s*["\']?[^\s\'"]{8,}', 'secret:**REDACTED**'),
    (r'Secret["\']?\s*[:=]\s*["\']?[^\s\'"]{8,}', 'Secret:**REDACTED**'),
]


def _sanitize_sensitive_data(text: str) -> str:
    """
    Sanitize sensitive data from text before logging or serialization.

    This function applies regex patterns to detect and redact:
    - Stripe API keys (sk_test_, sk_live_, rk_test_, rk_live_)
    - Bearer tokens and authentication tokens
    - Passwords in various formats
    - Generic API keys and secrets

    Args:
        text: The text to sanitize

    Returns:
        Sanitized text with sensitive data replaced by redaction markers

    Example:
        >>> _sanitize_sensitive_data("API key: sk_test_51AbC123xyz")
        'API key: **REDACTED_API_KEY**'
        >>> _sanitize_sensitive_data("password: SuperSecret123!")
        'password: **REDACTED**'
    """
    if not isinstance(text, str):
        return text

    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


# ============================================================================
# Base Exception
# ============================================================================

class StripeServiceError(Exception):
    """
    Base exception for all Stripe service errors.

    All StripeService exceptions inherit from this class for proper
    error handling and exception hierarchy.

    Attributes:
        message: Human-readable error message
        stripe_error: Optional underlying Stripe API error

    Example:
        >>> try:
        ...     # Stripe operation
        ...     pass
        ... except StripeServiceError as e:
        ...     logger.error("Stripe error: %s", e.to_dict())
    """

    def __init__(self, message: str, stripe_error: Optional[Exception] = None):
        """
        Initialize StripeServiceError.

        Args:
            message: Error message describing what went wrong
            stripe_error: Optional underlying Stripe API error
        """
        self.message = message
        self.stripe_error = stripe_error
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for logging/serialization.

        SECURITY: Sensitive data (API keys, passwords, tokens) is automatically
        redacted from the message before serialization to prevent credential
        leakage in logs and error responses.

        Returns:
            Dictionary containing error type, sanitized message, and context

        Example:
            >>> exc = StripeServiceError("Failed with API key: sk_test_51AbC123xyz")
            >>> exc.to_dict()
            {'error_type': 'StripeServiceError',
             'message': 'Failed with API key: **REDACTED_API_KEY**'}
        """
        return {
            "error_type": self.__class__.__name__,
            "message": _sanitize_sensitive_data(self.message),
        }


# ============================================================================
# Initialization Errors
# ============================================================================

class StripeInitializationError(StripeServiceError):
    """
    Raised when service initialization fails.

    This exception is raised when:
    - Stripe API key is invalid or missing
    - Secret manager fails to retrieve credentials
    - Required configuration is missing
    - Service dependencies cannot be initialized

    Example:
        >>> raise StripeInitializationError("Invalid Stripe API key")
    """
    pass


# ============================================================================
# API Errors
# ============================================================================

class StripeAPIError(StripeServiceError):
    """
    Raised when Stripe API call fails.

    This exception wraps Stripe API errors and provides
    additional context for debugging and logging.

    Attributes:
        message: Error message
        stripe_error_type: Type of Stripe error (e.g., "StripeError")
        stripe_code: Stripe error code (e.g., "api_key_invalid")
        http_status: HTTP status code (if available)
        is_retryable: Whether this error is retryable

    Example:
        >>> raise StripeAPIError(
        ...     "API call failed",
        ...     stripe_error_type="InvalidRequestError",
        ...     stripe_code="parameter_invalid",
        ...     http_status=400,
        ...     is_retryable=False
        ... )
    """

    def __init__(
        self,
        message: str,
        stripe_error_type: Optional[str] = None,
        stripe_code: Optional[str] = None,
        http_status: Optional[int] = None,
        is_retryable: bool = False
    ):
        """
        Initialize StripeAPIError.

        Args:
            message: Error message
            stripe_error_type: Type of Stripe error (e.g., "StripeError")
            stripe_code: Stripe error code (e.g., "api_key_invalid")
            http_status: HTTP status code
            is_retryable: Whether this error can be retried
        """
        super().__init__(message)
        self.stripe_error_type = stripe_error_type
        self.stripe_code = stripe_code
        self.http_status = http_status
        self.is_retryable = is_retryable

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with API context."""
        base_dict = super().to_dict()
        base_dict.update({
            "stripe_error_type": self.stripe_error_type,
            "stripe_code": self.stripe_code,
            "http_status": self.http_status,
            "is_retryable": self.is_retryable,
        })
        return base_dict


class StripeRateLimitError(StripeAPIError):
    """
    Raised when Stripe rate limit is exceeded (HTTP 429).

    This exception indicates that the API rate limit has been exceeded
    and the request should be retried after the specified delay.

    Attributes:
        retry_after: Seconds to wait before retrying (from Retry-After header)

    Example:
        >>> raise StripeRateLimitError("Rate limit exceeded", retry_after=60)
    """

    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        """
        Initialize StripeRateLimitError.

        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
            **kwargs: Additional arguments passed to StripeAPIError
        """
        super().__init__(message, http_status=429, is_retryable=True, **kwargs)
        self.retry_after = retry_after

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with rate limit context."""
        base_dict = super().to_dict()
        base_dict["retry_after"] = self.retry_after
        return base_dict


class StripeServerError(StripeAPIError):
    """
    Raised when Stripe server error occurs (HTTP 5xx).

    This exception indicates a server-side error from Stripe's API.
    These errors are typically retryable.

    Attributes:
        http_status: HTTP status code (5xx)

    Example:
        >>> raise StripeServerError("Internal server error", http_status=500)
    """

    def __init__(self, message: str, http_status: int = 500, **kwargs):
        """
        Initialize StripeServerError.

        Args:
            message: Error message
            http_status: HTTP status code (default: 500)
            **kwargs: Additional arguments passed to StripeAPIError
        """
        super().__init__(message, http_status=http_status, is_retryable=True, **kwargs)


# ============================================================================
# Customer Errors
# ============================================================================

class StripeCustomerError(StripeServiceError):
    """
    Base exception for customer operation failures.

    Provides rich context including tenant_id and stripe_customer_id
    for debugging and logging.

    Attributes:
        tenant_id: Optional tenant_id for context
        stripe_customer_id: Optional Stripe customer ID for context

    Example:
        >>> raise StripeCustomerError(
        ...     "Customer operation failed",
        ...     tenant_id="tenant_123",
        ...     stripe_customer_id="cus_abc123"
        ... )
    """

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        stripe_customer_id: Optional[str] = None
    ):
        """
        Initialize StripeCustomerError.

        Args:
            message: Error message
            tenant_id: Optional tenant_id for context
            stripe_customer_id: Optional Stripe customer ID for context
        """
        super().__init__(message)
        self.tenant_id = tenant_id
        self.stripe_customer_id = stripe_customer_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with customer context."""
        base_dict = super().to_dict()
        base_dict.update({
            "tenant_id": self.tenant_id,
            "stripe_customer_id": self.stripe_customer_id,
        })
        return base_dict


class StripeCustomerNotFoundError(StripeCustomerError):
    """
    Raised when Stripe customer is not found.

    This exception is raised when:
    - get_customer_by_tenant() returns None
    - update_customer() is called with non-existent customer
    - delete_customer() is called with non-existent customer

    Example:
        >>> raise StripeCustomerNotFoundError(
        ...     "Customer not found",
        ...     tenant_id="tenant_123",
        ...     stripe_customer_id="cus_abc123"
        ... )
    """
    pass


class StripeCustomerExistsError(StripeCustomerError):
    """
    Raised when attempting to create a customer that already exists.

    This exception is raised when:
    - create_customer() is called for a tenant that already has a customer
    - A duplicate customer is detected

    Example:
        >>> raise StripeCustomerExistsError(
        ...     "Customer already exists",
        ...     tenant_id="tenant_123",
        ...     stripe_customer_id="cus_abc123"
        ... )
    """
    pass


# ============================================================================
# Meter Errors
# ============================================================================

class StripeMeterError(StripeServiceError):
    """
    Base exception for meter event failures.

    Provides rich context including tenant_id for debugging and logging.

    Attributes:
        tenant_id: Optional tenant_id for context
        meter_event: Optional meter event name for context

    Example:
        >>> raise StripeMeterError(
        ...     "Meter operation failed",
        ...     tenant_id="tenant_123",
        ...     meter_event="ai_labels"
        ... )
    """

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        meter_event: Optional[str] = None
    ):
        """
        Initialize StripeMeterError.

        Args:
            message: Error message
            tenant_id: Optional tenant_id for context
            meter_event: Optional meter event name for context
        """
        super().__init__(message)
        self.tenant_id = tenant_id
        self.meter_event = meter_event

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with meter context."""
        base_dict = super().to_dict()
        base_dict.update({
            "tenant_id": self.tenant_id,
            "meter_event": self.meter_event,
        })
        return base_dict


class StripeMeterValidationError(StripeMeterError):
    """
    Raised when meter event validation fails.

    This exception is raised when:
    - Invalid meter_event name is provided
    - Meter event is not configured
    - Invalid value (quantity) is provided
    - Required tenant context is missing

    Attributes:
        validation_errors: List of specific validation errors

    Example:
        >>> raise StripeMeterValidationError(
        ...     "Invalid meter event",
        ...     meter_event="invalid_event",
        ...     validation_errors=["Unknown meter event", "Invalid value"]
        ... )
    """

    def __init__(
        self,
        message: str,
        meter_event: Optional[str] = None,
        validation_errors: Optional[list] = None
    ):
        """
        Initialize StripeMeterValidationError.

        Args:
            message: Error message describing what went wrong
            meter_event: Optional meter event name that failed validation
            validation_errors: Optional list of specific validation errors
        """
        super().__init__(message, meter_event=meter_event)
        self.validation_errors = validation_errors or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with validation details."""
        base_dict = super().to_dict()
        base_dict["validation_errors"] = self.validation_errors
        return base_dict


class StripeMeterQuotaError(StripeMeterError):
    """
    Raised when meter event quota is exceeded.

    This exception is raised when:
    - Usage exceeds configured limits
    - Quota constraints are violated

    Example:
        >>> raise StripeMeterQuotaError(
        ...     "Quota exceeded",
        ...     tenant_id="tenant_123",
        ...     meter_event="ai_labels"
        ... )
    """
    pass


# ============================================================================
# Idempotency Errors
# ============================================================================

class StripeIdempotencyError(StripeServiceError):
    """
    Base exception for idempotency failures.

    Provides context about the idempotency key involved in the error.

    Attributes:
        idempotency_key: The idempotency key that caused the error

    Example:
        >>> raise StripeIdempotencyError(
        ...     "Idempotency check failed",
        ...     idempotency_key="idemp_abc123"
        ... )
    """

    def __init__(
        self,
        message: str,
        idempotency_key: Optional[str] = None
    ):
        """
        Initialize StripeIdempotencyError.

        Args:
            message: Error message
            idempotency_key: Optional idempotency key for context
        """
        super().__init__(message)
        self.idempotency_key = idempotency_key

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with idempotency context."""
        base_dict = super().to_dict()
        base_dict["idempotency_key"] = self.idempotency_key
        return base_dict


class StripeIdempotencyKeyTooLongError(StripeIdempotencyError):
    """
    Raised when idempotency key exceeds maximum length.

    This exception is raised when:
    - Generated idempotency key exceeds Stripe's limit (255 characters)
    - Custom idempotency key is too long

    Attributes:
        key_length: The actual length of the key
        max_length: The maximum allowed length (default: 255)

    Example:
        >>> raise StripeIdempotencyKeyTooLongError(
        ...     "Idempotency key too long",
        ...     idempotency_key="very_long_key...",
        ...     key_length=300,
        ...     max_length=255
        ... )
    """

    def __init__(
        self,
        message: str,
        idempotency_key: Optional[str] = None,
        key_length: Optional[int] = None,
        max_length: int = 255
    ):
        """
        Initialize StripeIdempotencyKeyTooLongError.

        Args:
            message: Error message
            idempotency_key: Optional idempotency key that is too long
            key_length: Optional actual length of the key
            max_length: Maximum allowed length (default: 255)
        """
        super().__init__(message, idempotency_key=idempotency_key)
        self.key_length = key_length
        self.max_length = max_length

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with length details."""
        base_dict = super().to_dict()
        base_dict.update({
            "key_length": self.key_length,
            "max_length": self.max_length,
        })
        return base_dict


# ============================================================================
# Batch Processing Errors
# ============================================================================

class StripeBatchError(StripeServiceError):
    """
    Raised when batch processing fails.

    This exception is raised when:
    - Batch processing encounters unrecoverable errors
    - All events in a batch fail
    - Batch size exceeds limits

    Attributes:
        batch_id: Optional batch identifier for context
        failed_count: Number of failed events
        total_count: Total number of events in batch

    Example:
        >>> raise StripeBatchError(
        ...     "Batch processing failed",
        ...     batch_id="batch_123",
        ...     failed_count=10,
        ...     total_count=50
        ... )
    """

    def __init__(
        self,
        message: str,
        batch_id: Optional[str] = None,
        failed_count: Optional[int] = None,
        total_count: Optional[int] = None
    ):
        """
        Initialize StripeBatchError.

        Args:
            message: Error message
            batch_id: Optional batch identifier
            failed_count: Optional number of failed events
            total_count: Optional total number of events
        """
        super().__init__(message)
        self.batch_id = batch_id
        self.failed_count = failed_count
        self.total_count = total_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary with batch context."""
        base_dict = super().to_dict()
        base_dict.update({
            "batch_id": self.batch_id,
            "failed_count": self.failed_count,
            "total_count": self.total_count,
        })
        return base_dict
