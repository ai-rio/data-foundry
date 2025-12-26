"""
Stripe service module.

This package contains the modular Stripe service implementation with separate
concerns for customers, meter events, idempotency, retries, and validation.

Public API:
- Exceptions: Custom exception hierarchy for error handling
"""

# Version info
__version__ = "2.5.1"

# ============================================================================
# Exception exports
# ============================================================================

from .exceptions import (
    StripeServiceError,
    StripeInitializationError,
    StripeAPIError,
    StripeRateLimitError,
    StripeServerError,
    StripeCustomerError,
    StripeCustomerNotFoundError,
    StripeCustomerExistsError,
    StripeMeterError,
    StripeMeterValidationError,
    StripeMeterQuotaError,
    StripeIdempotencyError,
    StripeIdempotencyKeyTooLongError,
    StripeBatchError,
)

__all__ = [
    # Base exception
    "StripeServiceError",
    # Initialization errors
    "StripeInitializationError",
    # API errors
    "StripeAPIError",
    "StripeRateLimitError",
    "StripeServerError",
    # Customer errors
    "StripeCustomerError",
    "StripeCustomerNotFoundError",
    "StripeCustomerExistsError",
    # Meter errors
    "StripeMeterError",
    "StripeMeterValidationError",
    "StripeMeterQuotaError",
    # Idempotency errors
    "StripeIdempotencyError",
    "StripeIdempotencyKeyTooLongError",
    # Batch errors
    "StripeBatchError",
]
