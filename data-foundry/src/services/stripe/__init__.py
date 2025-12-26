"""
Stripe service module.

This package contains the modular Stripe service implementation with separate
concerns for customers, meter events, idempotency, retries, validation, and
batch processing.

Public API:
- Exceptions: Custom exception hierarchy for error handling
- Services: BatchProcessor for batch meter event processing
"""

# Version info
__version__ = "2.5.3"

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

# ============================================================================
# Service exports
# ============================================================================

from .batch_processor import BatchProcessor

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
    # Services
    "BatchProcessor",
]
