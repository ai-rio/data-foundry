"""
Stripe service module.

This package contains the modular Stripe service implementation with separate
concerns for customers, subscriptions, meter events, idempotency, retries, validation, and
batch processing.

Public API:
- Base Classes: StripeServiceBase for all service implementations
- Configuration: StripeConfig for centralized configuration management
- Services: Modular service classes for each concern
- Types: Enums, TypedDicts, and dataclasses for type safety
- Protocols: Protocol classes for dependency injection and testing
- Exceptions: Complete exception hierarchy for error handling

Phase: 3 (Subscription Service)
Task: P3-001 (Subscription Creation)
"""

# ============================================================================
# Base class exports
# ============================================================================

from .base import StripeServiceBase

# ============================================================================
# Configuration exports
# ============================================================================

from .config import StripeConfig

# ============================================================================
# Service exports
# ============================================================================

from .validation import ValidationService
from .retry_service import RetryService
from .idempotency_service import IdempotencyService
from .customer_service import CustomerService
from .subscription_service import SubscriptionService
from .meter_event_service import MeterEventService
from .batch_processor import BatchProcessor

# ============================================================================
# Type exports
# ============================================================================

from .types import (
    # Enums
    MeterType,
    SubscriptionTier,
    PriceType,
    EventStatus,
    RetryCategory,
    # TypedDicts
    CustomerData,
    SubscriptionData,
    MeterEventData,
    MeterEventResult,
    RetryConfig,
    IdempotencyConfig,
    # Dataclasses
    BatchResult,
    IdempotencyKeyInfo,
    CollisionMetrics,
    # Protocols (for dependency injection and testing)
    StripeClientProtocol,
    SecretManagerProtocol,
    IdempotencyServiceProtocol,
    RetryServiceProtocol,
    ValidationServiceProtocol,
    MeterEventServiceProtocol,
    BatchProcessorProtocol,
    CustomerServiceProtocol,
    SubscriptionServiceProtocol,
)

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
# Public API declaration
# ============================================================================

__all__ = [
    # Version
    "__version__",

    # ===== Base Classes =====
    "StripeServiceBase",

    # ===== Configuration =====
    "StripeConfig",

    # ===== Services =====
    "ValidationService",
    "RetryService",
    "IdempotencyService",
    "CustomerService",
    "SubscriptionService",
    "MeterEventService",
    "BatchProcessor",

    # ===== Enums =====
    "MeterType",
    "SubscriptionTier",
    "PriceType",
    "EventStatus",
    "RetryCategory",

    # ===== TypedDicts =====
    "CustomerData",
    "SubscriptionData",
    "MeterEventData",
    "MeterEventResult",
    "RetryConfig",
    "IdempotencyConfig",

    # ===== Dataclasses =====
    "BatchResult",
    "IdempotencyKeyInfo",
    "CollisionMetrics",

    # ===== Protocols =====
    "StripeClientProtocol",
    "SecretManagerProtocol",
    "IdempotencyServiceProtocol",
    "RetryServiceProtocol",
    "ValidationServiceProtocol",
    "MeterEventServiceProtocol",
    "BatchProcessorProtocol",
    "CustomerServiceProtocol",
    "SubscriptionServiceProtocol",

    # ===== Exceptions =====
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
