# Stripe Service Modular Architecture Design

## Overview

This document outlines the refactored modular architecture for the StripeService, transforming the current monolithic ~1700 LOC implementation into a set of focused, testable, and maintainable service classes following the Single Responsibility Principle.

## Current State Analysis

### Existing Functionality (Phase 1 & 2)

| Phase | Feature | Lines | Responsibility |
|-------|---------|-------|----------------|
| P1-002 | Customer CRUD | ~250 | Create, read, update, delete customers |
| P02-001 | Meter Event Reporting | ~150 | Report single meter events to Stripe |
| P02-002 | Batch Processing | ~200 | Process multiple events in batches |
| P02-003 | Retry Logic | ~200 | Exponential backoff with jitter |
| P02-004 | Idempotency | ~300 | Key generation, registry, collision detection |
| P02-005 | Pipeline Integration | N/A | UsageCalculationService integration |

### Current Issues

1. **Single Responsibility Violation**: One class handles customers, meters, retries, idempotency
2. **Tight Coupling**: Retry logic embedded in meter reporting
3. **Difficult Testing**: Mocking requires understanding entire class
4. **Hard to Extend**: Adding new features requires modifying core class

---

## Proposed Module Structure

```
src/services/stripe/
├── __init__.py                    # Public API exports & facade
├── base.py                        # Base service class & initialization
├── customer_service.py            # Customer CRUD operations
├── meter_event_service.py         # Meter event reporting
├── idempotency_service.py         # Key generation & registry
├── retry_service.py               # Exponential backoff logic
├── batch_processor.py             # Batch operations
├── validation.py                  # Validators & sanitizers
├── exceptions.py                  # Custom exception hierarchy
├── types.py                       # Type definitions & protocols
└── config.py                      # Configuration management
```

---

## Module Specifications

### 1. `types.py` - Type Definitions & Protocols

**Purpose**: Define interfaces (protocols) and type definitions for dependency injection and type safety.

```python
"""
Type definitions and protocols for Stripe service modules.

This module defines:
- Protocol classes for dependency injection (allowing mock implementations)
- TypedDict definitions for structured data
- Enums for meter types and status codes
- Generic type aliases for common patterns
"""

from typing import Protocol, TypedDict, Optional, Dict, Any, List, Callable, Awaitable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


# ============================================================================
# Enums
# ============================================================================

class MeterType(str, Enum):
    """Supported meter event types for usage-based billing."""
    AI_LABELS = "ai_labels"
    HUMAN_AUDITS = "human_audits"


class EventStatus(str, Enum):
    """Status of a meter event."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RetryCategory(str, Enum):
    """Classification of errors for retry logic."""
    TRANSIENT = "transient"      # Should retry (429, 500, 502, 503, 504)
    PERMANENT = "permanent"       # Should not retry (400, 401, 404)
    UNKNOWN = "unknown"           # Default behavior


# ============================================================================
# TypedDict Definitions
# ============================================================================

class CustomerData(TypedDict, total=False):
    """Customer data structure for Stripe operations."""
    tenant_id: str
    stripe_customer_id: str
    email: Optional[str]
    name: Optional[str]
    metadata: Dict[str, str]
    created_at: Optional[str]
    updated_at: Optional[str]


class MeterEventData(TypedDict):
    """Meter event data structure."""
    meter_event: str
    value: int
    tenant_id: str
    metadata: Optional[Dict[str, str]]


class MeterEventResult(TypedDict):
    """Result of a meter event submission."""
    event_id: str
    status: str
    stripe_response: Optional[Dict[str, Any]]
    meter_event: str
    value: int


class RetryConfig(TypedDict, total=False):
    """Retry configuration settings."""
    max_retries: int
    initial_delay_ms: int
    max_delay_ms: int
    backoff_multiplier: float
    jitter_enabled: bool


class IdempotencyConfig(TypedDict, total=False):
    """Idempotency configuration settings."""
    max_key_length: int
    retention_hours: int
    max_registry_size: int


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class BatchResult:
    """
    Result of a batch meter event reporting operation.

    Attributes:
        batch_id: Unique identifier for this batch operation
        total_events: Total number of events in the batch
        successful_count: Number of events that succeeded
        failed_count: Number of events that failed
        successes: List of successful event results
        failures: List of failed event results with error details
    """
    batch_id: str
    total_events: int
    successful_count: int
    failed_count: int
    successes: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class IdempotencyKeyInfo:
    """Information about an idempotency key."""
    key: str
    registered_at: datetime
    tenant_id: str
    meter_event: str
    value: int
    batch_id: Optional[str] = None


@dataclass
class CollisionMetrics:
    """Metrics for idempotency key collision detection."""
    total_keys_generated: int = 0
    collision_count: int = 0
    near_collision_count: int = 0
    registry_size: int = 0

    @property
    def collision_rate(self) -> float:
        """Calculate collision rate as percentage."""
        if self.total_keys_generated == 0:
            return 0.0
        return ((self.collision_count + self.near_collision_count) /
                self.total_keys_generated * 100)


# ============================================================================
# Protocol Definitions (Interfaces for Dependency Injection)
# ============================================================================

class StripeClientProtocol(Protocol):
    """
    Protocol for Stripe API client operations.

    Allows injection of mock clients for testing.
    """

    def create_customer(self, **kwargs) -> Dict[str, Any]:
        """Create a Stripe customer."""
        ...

    def retrieve_customer(self, customer_id: str) -> Dict[str, Any]:
        """Retrieve a Stripe customer."""
        ...

    def modify_customer(self, customer_id: str, **kwargs) -> Dict[str, Any]:
        """Modify a Stripe customer."""
        ...

    def delete_customer(self, customer_id: str) -> bool:
        """Delete a Stripe customer."""
        ...

    def create_meter_event(self, **kwargs) -> Dict[str, Any]:
        """Create a meter event."""
        ...


class SecretManagerProtocol(Protocol):
    """Protocol for secret management."""

    def get_secret(self, key: str) -> Optional[str]:
        """Retrieve a secret by key."""
        ...


class IdempotencyServiceProtocol(Protocol):
    """Protocol for idempotency key operations."""

    def generate_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        batch_id: Optional[str] = None
    ) -> str:
        """Generate a unique idempotency key."""
        ...

    def is_registered(self, key: str) -> bool:
        """Check if a key is already registered."""
        ...

    def register_key(self, key: str) -> None:
        """Register an idempotency key."""
        ...

    def get_metrics(self) -> CollisionMetrics:
        """Get collision detection metrics."""
        ...


class RetryServiceProtocol(Protocol):
    """Protocol for retry logic."""

    async def execute_with_retry(
        self,
        func: Callable[..., Awaitable[Any]],
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """Execute a function with retry logic."""
        ...

    def is_transient_error(self, error: Exception) -> bool:
        """Determine if an error is transient."""
        ...


class ValidationServiceProtocol(Protocol):
    """Protocol for validation operations."""

    def validate_meter_event(self, meter_event: str, value: int) -> List[str]:
        """Validate meter event parameters."""
        ...

    def sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """Sanitize metadata for Stripe API."""
        ...

    def sanitize_idempotency_component(self, component: str) -> str:
        """Sanitize a component for idempotency key generation."""
        ...


class MeterEventServiceProtocol(Protocol):
    """Protocol for meter event operations."""

    async def report_usage(
        self,
        meter_event: str,
        value: int,
        tenant_id: str,
        metadata: Optional[Dict[str, str]] = None,
        stripe_customer_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> MeterEventResult:
        """Report a single meter event."""
        ...


class BatchProcessorProtocol(Protocol):
    """Protocol for batch processing operations."""

    async def process_batch(
        self,
        events: List[MeterEventData],
        tenant_id: str,
        stripe_customer_id: Optional[str] = None
    ) -> BatchResult:
        """Process a batch of meter events."""
        ...

    def generate_batch_id(self, tenant_id: str) -> str:
        """Generate a unique batch ID."""
        ...


class CustomerServiceProtocol(Protocol):
    """Protocol for customer operations."""

    async def create_customer(
        self,
        tenant_id: str,
        tenant_name: str,
        email: str,
        name: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> str:
        """Create a Stripe customer."""
        ...

    async def get_customer_by_tenant(
        self,
        tenant_id: str
    ) -> Optional[CustomerData]:
        """Get customer by tenant ID."""
        ...

    async def update_customer(
        self,
        stripe_customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> CustomerData:
        """Update a customer."""
        ...

    async def delete_customer(
        self,
        stripe_customer_id: str
    ) -> bool:
        """Delete a customer."""
        ...
```

**Dependencies**: None (this is the foundation module)

**Public Interface**:
- `MeterType` enum
- `EventStatus` enum
- `RetryCategory` enum
- `CustomerData`, `MeterEventData`, `MeterEventResult` TypedDicts
- `BatchResult`, `IdempotencyKeyInfo`, `CollisionMetrics` dataclasses
- All Protocol classes for dependency injection

---

### 2. `exceptions.py` - Custom Exception Hierarchy

**Purpose**: Centralized exception definitions with rich context for error handling.

```python
"""
Custom exception hierarchy for Stripe service operations.

Exception Hierarchy:
    StripeServiceError (base)
    ├── StripeInitializationError - Service initialization failures
    ├── StripeAPIError - Stripe API call failures
    │   ├── StripeRateLimitError - Rate limit exceeded (429)
    │   └── StripeServerError - Server errors (5xx)
    ├── StripeCustomerError - Customer operation failures
    │   ├── StripeCustomerNotFoundError - Customer not found
    │   └── StripeCustomerExistsError - Customer already exists
    ├── StripeMeterError - Meter event failures
    │   ├── StripeMeterValidationError - Validation failures
    │   └── StripeMeterQuotaError - Quota exceeded
    ├── StripeIdempotencyError - Idempotency failures
    │   └── StripeIdempotencyKeyTooLongError - Key length exceeded
    └── StripeBatchError - Batch processing failures
"""

from typing import Optional, List, Any, Dict


class StripeServiceError(Exception):
    """
    Base exception for all Stripe service errors.

    Attributes:
        message: Human-readable error message
        stripe_error: Optional underlying Stripe API error
        context: Optional additional context dictionary
    """

    def __init__(
        self,
        message: str,
        stripe_error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.stripe_error = stripe_error
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "context": self.context,
            "has_stripe_error": self.stripe_error is not None
        }


class StripeInitializationError(StripeServiceError):
    """Raised when service initialization fails."""
    pass


class StripeAPIError(StripeServiceError):
    """
    Raised when Stripe API call fails.

    Attributes:
        stripe_error_type: Type of Stripe error (e.g., "StripeError")
        stripe_code: Stripe error code (e.g., "api_key_invalid")
        http_status: HTTP status code if available
        is_retryable: Whether the error is transient and retryable
    """

    def __init__(
        self,
        message: str,
        stripe_error_type: Optional[str] = None,
        stripe_code: Optional[str] = None,
        http_status: Optional[int] = None,
        is_retryable: bool = False,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.stripe_error_type = stripe_error_type
        self.stripe_code = stripe_code
        self.http_status = http_status
        self.is_retryable = is_retryable


class StripeRateLimitError(StripeAPIError):
    """Raised when Stripe rate limit is exceeded (HTTP 429)."""

    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, http_status=429, is_retryable=True, **kwargs)
        self.retry_after = retry_after


class StripeServerError(StripeAPIError):
    """Raised when Stripe server error occurs (HTTP 5xx)."""

    def __init__(self, message: str, http_status: int = 500, **kwargs):
        super().__init__(message, http_status=http_status, is_retryable=True, **kwargs)


class StripeCustomerError(StripeServiceError):
    """Base exception for customer operation failures."""

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        stripe_customer_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.tenant_id = tenant_id
        self.stripe_customer_id = stripe_customer_id


class StripeCustomerNotFoundError(StripeCustomerError):
    """Raised when Stripe customer is not found."""
    pass


class StripeCustomerExistsError(StripeCustomerError):
    """Raised when attempting to create a customer that already exists."""
    pass


class StripeMeterError(StripeServiceError):
    """Base exception for meter event failures."""

    def __init__(
        self,
        message: str,
        meter_event: Optional[str] = None,
        tenant_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.meter_event = meter_event
        self.tenant_id = tenant_id


class StripeMeterValidationError(StripeMeterError):
    """Raised when meter event validation fails."""

    def __init__(
        self,
        message: str,
        validation_errors: Optional[List[str]] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.validation_errors = validation_errors or []


class StripeMeterQuotaError(StripeMeterError):
    """Raised when meter event quota is exceeded."""
    pass


class StripeIdempotencyError(StripeServiceError):
    """Base exception for idempotency failures."""

    def __init__(
        self,
        message: str,
        idempotency_key: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.idempotency_key = idempotency_key


class StripeIdempotencyKeyTooLongError(StripeIdempotencyError):
    """Raised when idempotency key exceeds maximum length."""

    def __init__(
        self,
        message: str,
        key_length: int,
        max_length: int = 255,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.key_length = key_length
        self.max_length = max_length


class StripeBatchError(StripeServiceError):
    """Raised when batch processing fails."""

    def __init__(
        self,
        message: str,
        batch_id: Optional[str] = None,
        successful_count: int = 0,
        failed_count: int = 0,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.batch_id = batch_id
        self.successful_count = successful_count
        self.failed_count = failed_count
```

**Dependencies**: None

**Public Interface**:
- All exception classes
- Each exception's `to_dict()` method for serialization

---

### 3. `config.py` - Configuration Management

**Purpose**: Centralized configuration with environment variable support and validation.

```python
"""
Configuration management for Stripe service modules.

Supports:
- Environment variable loading with defaults
- Configuration validation
- Runtime configuration updates
- Meter ID mapping
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from .types import RetryConfig, IdempotencyConfig, MeterType


@dataclass
class StripeConfig:
    """
    Centralized configuration for Stripe services.

    Loads configuration from environment variables with sensible defaults.
    """

    # API Configuration
    api_key: Optional[str] = field(default=None, repr=False)  # Never log API key

    # Retry Configuration
    max_retries: int = field(default_factory=lambda: int(os.getenv("STRIPE_MAX_RETRIES", "5")))
    initial_retry_delay_ms: int = field(default_factory=lambda: int(os.getenv("STRIPE_INITIAL_RETRY_DELAY_MS", "1000")))
    max_retry_delay_ms: int = field(default_factory=lambda: int(os.getenv("STRIPE_MAX_RETRY_DELAY_MS", "32000")))
    retry_backoff_multiplier: float = 2.0
    jitter_enabled: bool = True

    # Idempotency Configuration
    max_idempotency_key_length: int = 255  # Stripe limit
    idempotency_retention_hours: int = 24
    max_idempotency_registry_size: int = 10000

    # Batch Configuration
    max_batch_size: int = 100

    # Meter Configuration
    meter_ids: Dict[str, str] = field(default_factory=dict)

    # Validation Configuration
    reserved_metadata_keys: frozenset = field(
        default_factory=lambda: frozenset({"value", "stripe_customer_id", "batch_id"})
    )

    def __post_init__(self):
        """Load meter IDs from environment after initialization."""
        if not self.meter_ids:
            self.meter_ids = {
                MeterType.AI_LABELS.value: os.getenv("STRIPE_AI_LABELS_METER_ID", ""),
                MeterType.HUMAN_AUDITS.value: os.getenv("STRIPE_HUMAN_AUDITS_METER_ID", ""),
            }

    @classmethod
    def from_environment(cls) -> "StripeConfig":
        """Create configuration from environment variables."""
        return cls()

    def validate(self) -> List[str]:
        """
        Validate configuration values.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if self.max_retries < 0:
            errors.append(f"max_retries must be >= 0, got {self.max_retries}")

        if self.initial_retry_delay_ms < 0:
            errors.append(f"initial_retry_delay_ms must be >= 0, got {self.initial_retry_delay_ms}")

        if self.max_retry_delay_ms < self.initial_retry_delay_ms:
            errors.append(
                f"max_retry_delay_ms ({self.max_retry_delay_ms}) must be >= "
                f"initial_retry_delay_ms ({self.initial_retry_delay_ms})"
            )

        if self.max_batch_size < 1:
            errors.append(f"max_batch_size must be >= 1, got {self.max_batch_size}")

        if self.max_batch_size > 1000:
            errors.append(f"max_batch_size must be <= 1000, got {self.max_batch_size}")

        return errors

    def get_retry_config(self) -> RetryConfig:
        """Get retry configuration as TypedDict."""
        return RetryConfig(
            max_retries=self.max_retries,
            initial_delay_ms=self.initial_retry_delay_ms,
            max_delay_ms=self.max_retry_delay_ms,
            backoff_multiplier=self.retry_backoff_multiplier,
            jitter_enabled=self.jitter_enabled
        )

    def get_idempotency_config(self) -> IdempotencyConfig:
        """Get idempotency configuration as TypedDict."""
        return IdempotencyConfig(
            max_key_length=self.max_idempotency_key_length,
            retention_hours=self.idempotency_retention_hours,
            max_registry_size=self.max_idempotency_registry_size
        )

    def get_meter_id(self, meter_type: MeterType) -> Optional[str]:
        """Get meter ID for a meter type."""
        meter_id = self.meter_ids.get(meter_type.value, "")
        return meter_id if meter_id else None
```

**Dependencies**: `types.py`

**Public Interface**:
- `StripeConfig` dataclass
- `from_environment()` class method
- `validate()` method
- Configuration getters

---

### 4. `validation.py` - Validators & Sanitizers

**Purpose**: Centralized input validation and sanitization to prevent injection attacks.

```python
"""
Validation and sanitization utilities for Stripe service operations.

Provides:
- Meter event validation
- Metadata sanitization
- Idempotency key component sanitization
- Input type validation
"""

import re
import logging
from typing import Dict, Any, List, Optional, Set

from .types import MeterType, ValidationServiceProtocol
from .exceptions import StripeMeterValidationError
from .config import StripeConfig


logger = logging.getLogger(__name__)


class ValidationService(ValidationServiceProtocol):
    """
    Centralized validation and sanitization service.

    Implements security-focused validation to prevent:
    - Injection attacks (SQL, XSS, path traversal)
    - Invalid data reaching Stripe API
    - Reserved key conflicts
    """

    # Dangerous patterns for sanitization
    DANGEROUS_PATTERNS = [
        r'\.\./',        # Path traversal
        r'\.\.\\',       # Windows path traversal
        r';',            # SQL injection separator
        r'--',           # SQL comment
        r"'",            # SQL quote
        r'"',            # Quote
        r'<script',      # XSS
        r'</script>',    # XSS close
        r'=',            # Could be used in injection
    ]

    # Maximum component length for DoS prevention
    MAX_COMPONENT_LENGTH = 100

    def __init__(self, config: Optional[StripeConfig] = None):
        """
        Initialize ValidationService.

        Args:
            config: Optional configuration (uses defaults if not provided)
        """
        self.config = config or StripeConfig()
        self._valid_meter_events: Set[str] = {
            MeterType.AI_LABELS.value,
            MeterType.HUMAN_AUDITS.value
        }

    def validate_meter_event(self, meter_event: str, value: int) -> List[str]:
        """
        Validate meter event parameters.

        Args:
            meter_event: The meter event name to validate
            value: The quantity/value to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate meter_event name
        if meter_event not in self._valid_meter_events:
            errors.append(
                f"Invalid meter_event '{meter_event}'. "
                f"Must be one of: {', '.join(sorted(self._valid_meter_events))}"
            )

        # Validate value is positive integer
        if not isinstance(value, int):
            errors.append(f"Value must be an integer, got {type(value).__name__}")
        elif value <= 0:
            errors.append(f"Value must be positive, got {value}")

        return errors

    def validate_batch_events(self, events: List[Dict[str, Any]]) -> List[str]:
        """
        Validate event structure for all events in a batch.

        Args:
            events: List of event dictionaries to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        for i, event in enumerate(events):
            # Check for required fields
            if "meter_event" not in event:
                errors.append(f"Event at index {i}: Missing required field 'meter_event'")
            elif not isinstance(event["meter_event"], str):
                errors.append(
                    f"Event at index {i}: 'meter_event' must be a string, "
                    f"got {type(event['meter_event']).__name__}"
                )

            if "value" not in event:
                errors.append(f"Event at index {i}: Missing required field 'value'")
            elif not isinstance(event["value"], int):
                errors.append(
                    f"Event at index {i}: 'value' must be an integer, "
                    f"got {type(event['value']).__name__}"
                )

        return errors

    def sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """
        Sanitize metadata to prevent injection attacks.

        Args:
            metadata: Metadata dictionary to sanitize

        Returns:
            Sanitized metadata dictionary with string values

        Raises:
            StripeMeterValidationError: If metadata contains invalid types or reserved keys
        """
        if not isinstance(metadata, dict):
            raise StripeMeterValidationError(
                f"Metadata must be a dictionary, got {type(metadata).__name__}"
            )

        sanitized = {}
        validation_errors = []

        for key, value in metadata.items():
            # Validate key is a string
            if not isinstance(key, str):
                validation_errors.append(
                    f"Metadata key '{key}' must be a string, got {type(key).__name__}"
                )
                continue

            # Check for reserved keys
            if key in self.config.reserved_metadata_keys:
                validation_errors.append(
                    f"Metadata key '{key}' is reserved and cannot be set"
                )
                continue

            # Validate value is a primitive type
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = str(value)
            else:
                validation_errors.append(
                    f"Metadata value for key '{key}' must be a primitive type "
                    f"(str, int, float, bool), got {type(value).__name__}"
                )

        if validation_errors:
            raise StripeMeterValidationError(
                f"Metadata validation failed: {'; '.join(validation_errors)}",
                validation_errors=validation_errors
            )

        return sanitized

    def sanitize_idempotency_component(self, component: str) -> str:
        """
        Sanitize a component for use in idempotency key.

        Removes dangerous characters to prevent injection attacks and key collisions.

        Args:
            component: Raw component string to sanitize

        Returns:
            Sanitized component string safe for idempotency keys
        """
        if not component:
            return "empty"

        # Convert to string if not already
        if not isinstance(component, str):
            component = str(component)

        # Remove control characters
        component = ''.join(char for char in component if ord(char) >= 32)

        # Remove dangerous sequences
        for pattern in self.DANGEROUS_PATTERNS:
            component = re.sub(pattern, '', component, flags=re.IGNORECASE)

        # Replace non-alphanumeric chars (except underscore, hyphen) with underscore
        component = re.sub(r'[^a-zA-Z0-9_-]', '_', component)

        # Collapse multiple underscores
        component = re.sub(r'_+', '_', component)

        # Remove leading/trailing underscores
        component = component.strip('_')

        # Limit length to prevent DoS
        if len(component) > self.MAX_COMPONENT_LENGTH:
            component = component[:self.MAX_COMPONENT_LENGTH]

        # Fallback if empty after sanitization
        if not component:
            component = "sanitized"

        return component

    def validate_batch_size(self, size: int) -> None:
        """
        Validate batch size is within limits.

        Args:
            size: Batch size to validate

        Raises:
            StripeMeterValidationError: If batch size exceeds maximum
        """
        if size > self.config.max_batch_size:
            raise StripeMeterValidationError(
                f"Batch size exceeds maximum allowed size of {self.config.max_batch_size}. "
                f"Got {size} events."
            )

    def validate_idempotency_key_length(self, key: str) -> None:
        """
        Validate that idempotency key meets Stripe's length requirements.

        Args:
            key: Idempotency key to validate

        Raises:
            StripeMeterValidationError: If key exceeds 255 characters
        """
        max_length = self.config.max_idempotency_key_length
        if len(key) > max_length:
            raise StripeMeterValidationError(
                f"Idempotency key length {len(key)} exceeds Stripe's maximum of "
                f"{max_length} characters",
                validation_errors=[f"Key too long: {len(key)} > {max_length}"]
            )
```

**Dependencies**: `types.py`, `exceptions.py`, `config.py`

**Public Interface**:
- `ValidationService` class implementing `ValidationServiceProtocol`
- `validate_meter_event()` - Validate meter event parameters
- `validate_batch_events()` - Validate batch event structure
- `sanitize_metadata()` - Sanitize metadata for Stripe API
- `sanitize_idempotency_component()` - Sanitize idempotency key components
- `validate_batch_size()` - Validate batch size limits
- `validate_idempotency_key_length()` - Validate idempotency key length

---

### 5. `idempotency_service.py` - Key Generation & Registry

**Purpose**: Thread-safe idempotency key generation with collision detection.

```python
"""
Idempotency key generation and registry service.

Provides:
- Unique idempotency key generation with timestamp and UUID
- Thread-safe key registry with automatic cleanup
- Collision detection and metrics
- Key validation (length, format)
"""

import uuid
import threading
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from .types import IdempotencyServiceProtocol, CollisionMetrics, IdempotencyKeyInfo
from .config import StripeConfig
from .validation import ValidationService


logger = logging.getLogger(__name__)


class IdempotencyService(IdempotencyServiceProtocol):
    """
    Thread-safe idempotency key generation and registry.

    Features:
    - Input sanitization for security
    - Timestamp + UUID for uniqueness
    - Thread-safe registry with TTL-based cleanup
    - Collision detection and metrics
    """

    def __init__(
        self,
        config: Optional[StripeConfig] = None,
        validation_service: Optional[ValidationService] = None
    ):
        """
        Initialize IdempotencyService.

        Args:
            config: Optional configuration (uses defaults if not provided)
            validation_service: Optional validation service (creates one if not provided)
        """
        self.config = config or StripeConfig()
        self.validation = validation_service or ValidationService(self.config)

        # Thread-safe registry: {key: IdempotencyKeyInfo}
        self._registry: Dict[str, IdempotencyKeyInfo] = {}
        self._registry_lock = threading.Lock()

        # Collision metrics
        self._metrics = CollisionMetrics()
        self._metrics_lock = threading.Lock()

    def generate_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        batch_id: Optional[str] = None
    ) -> str:
        """
        Generate unique idempotency key for meter event.

        Key format: {meter_event}_{tenant_id}_{value}_{timestamp}_{uuid_short}[_{batch_id}]

        Args:
            tenant_id: Tenant identifier
            meter_event: Meter event name
            value: Event value
            batch_id: Optional batch identifier

        Returns:
            Unique idempotency key string

        Raises:
            StripeMeterValidationError: If key would exceed length limit
        """
        # Update metrics
        with self._metrics_lock:
            self._metrics.total_keys_generated += 1

        # Sanitize all input components
        safe_tenant_id = self.validation.sanitize_idempotency_component(tenant_id)
        safe_meter_event = self.validation.sanitize_idempotency_component(meter_event)
        safe_value = self.validation.sanitize_idempotency_component(str(value))

        # Generate timestamp and UUID
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        unique_suffix = uuid.uuid4().hex[:8]

        # Build key
        key_parts = [safe_meter_event, safe_tenant_id, safe_value, timestamp, unique_suffix]

        if batch_id:
            safe_batch_id = self.validation.sanitize_idempotency_component(batch_id)
            key_parts.append(safe_batch_id)

        key = "_".join(key_parts)

        # Validate length
        self.validation.validate_idempotency_key_length(key)

        # Check for collisions
        self._check_and_warn_collision(key, tenant_id, meter_event)

        # Register key
        key_info = IdempotencyKeyInfo(
            key=key,
            registered_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            meter_event=meter_event,
            value=value,
            batch_id=batch_id
        )
        self.register_key(key, key_info)

        return key

    def is_registered(self, key: str) -> bool:
        """
        Check if an idempotency key is already registered.

        Args:
            key: Idempotency key to check

        Returns:
            True if key is registered and not expired
        """
        with self._registry_lock:
            self._cleanup_expired_keys()

            if key in self._registry:
                info = self._registry[key]
                age_hours = (datetime.now(timezone.utc) - info.registered_at).total_seconds() / 3600

                if age_hours <= self.config.idempotency_retention_hours:
                    return True
                else:
                    del self._registry[key]

        return False

    def register_key(self, key: str, info: Optional[IdempotencyKeyInfo] = None) -> None:
        """
        Register an idempotency key in the registry.

        Args:
            key: Idempotency key to register
            info: Optional key info (creates minimal info if not provided)
        """
        with self._registry_lock:
            self._cleanup_expired_keys()

            # Prevent unbounded growth
            if len(self._registry) >= self.config.max_idempotency_registry_size:
                logger.warning(
                    f"Idempotency registry full ({self.config.max_idempotency_registry_size}). "
                    "Removing oldest entries."
                )
                self._evict_oldest_entries()

            # Register key
            if info is None:
                info = IdempotencyKeyInfo(
                    key=key,
                    registered_at=datetime.now(timezone.utc),
                    tenant_id="unknown",
                    meter_event="unknown",
                    value=0
                )

            self._registry[key] = info

    def get_metrics(self) -> CollisionMetrics:
        """
        Get collision detection metrics.

        Returns:
            CollisionMetrics with current statistics
        """
        with self._metrics_lock:
            metrics = CollisionMetrics(
                total_keys_generated=self._metrics.total_keys_generated,
                collision_count=self._metrics.collision_count,
                near_collision_count=self._metrics.near_collision_count
            )

        with self._registry_lock:
            metrics.registry_size = len(self._registry)

        return metrics

    def clear_registry(self) -> None:
        """Clear all keys from registry (for testing)."""
        with self._registry_lock:
            self._registry.clear()

    def _cleanup_expired_keys(self) -> None:
        """Remove expired keys from registry. Must be called with lock held."""
        current_time = datetime.now(timezone.utc)
        retention_delta = timedelta(hours=self.config.idempotency_retention_hours)

        expired_keys = [
            key for key, info in self._registry.items()
            if current_time - info.registered_at > retention_delta
        ]

        for key in expired_keys:
            del self._registry[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired idempotency keys")

    def _evict_oldest_entries(self) -> None:
        """Evict oldest 10% of entries. Must be called with lock held."""
        sorted_entries = sorted(
            self._registry.items(),
            key=lambda x: x[1].registered_at
        )

        entries_to_remove = max(1, len(sorted_entries) // 10)
        for key, _ in sorted_entries[:entries_to_remove]:
            del self._registry[key]

    def _check_and_warn_collision(
        self,
        new_key: str,
        tenant_id: str,
        meter_event: str
    ) -> None:
        """Check for potential collisions and log warnings."""
        with self._registry_lock:
            recent_keys = list(self._registry.values())[-100:]

        new_parts = new_key.split('_')
        if len(new_parts) < 5:
            return

        new_timestamp = new_parts[3]

        for info in recent_keys:
            if info.tenant_id == tenant_id and info.meter_event == meter_event:
                existing_parts = info.key.split('_')
                if len(existing_parts) >= 5:
                    existing_timestamp = existing_parts[3]

                    try:
                        new_dt = datetime.strptime(new_timestamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                        existing_dt = datetime.strptime(existing_timestamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                        time_diff = abs((new_dt - existing_dt).total_seconds())

                        if time_diff < 1.0:
                            with self._metrics_lock:
                                self._metrics.near_collision_count += 1

                            logger.warning(
                                f"Near-collision detected for idempotency keys:\n"
                                f"  New:      {new_key}\n"
                                f"  Existing: {info.key}\n"
                                f"  Time difference: {time_diff:.3f}s"
                            )
                    except (ValueError, IndexError):
                        pass
```

**Dependencies**: `types.py`, `config.py`, `validation.py`

**Public Interface**:
- `IdempotencyService` class implementing `IdempotencyServiceProtocol`
- `generate_key()` - Generate unique idempotency key
- `is_registered()` - Check if key is registered
- `register_key()` - Register a key
- `get_metrics()` - Get collision metrics
- `clear_registry()` - Clear registry (for testing)

---

### 6. `retry_service.py` - Exponential Backoff Logic

**Purpose**: Configurable retry logic with exponential backoff and jitter.

```python
"""
Retry service with exponential backoff and jitter.

Provides:
- Configurable retry attempts and delays
- Exponential backoff with optional jitter
- Transient error detection
- Async-aware retry execution
"""

import asyncio
import random
import logging
from typing import Callable, Any, Awaitable, Optional

import stripe

from .types import RetryServiceProtocol, RetryCategory
from .config import StripeConfig
from .exceptions import StripeAPIError, StripeRateLimitError, StripeServerError


logger = logging.getLogger(__name__)


class RetryService(RetryServiceProtocol):
    """
    Retry service with exponential backoff and jitter.

    Implements intelligent retry logic that:
    - Retries transient errors (429, 5xx)
    - Does not retry permanent errors (400, 401, 404)
    - Uses exponential backoff to reduce load
    - Adds jitter to prevent thundering herd
    """

    def __init__(self, config: Optional[StripeConfig] = None):
        """
        Initialize RetryService.

        Args:
            config: Optional configuration (uses defaults if not provided)
        """
        self.config = config or StripeConfig()

    async def execute_with_retry(
        self,
        func: Callable[..., Any],
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic and exponential backoff.

        Args:
            func: Function to execute (sync or async)
            operation_name: Human-readable operation name for logging
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func on success

        Raises:
            Exception: The last exception after all retries exhausted
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Success
                if attempt > 0:
                    logger.info(f"{operation_name} succeeded after {attempt} retries")
                return result

            except Exception as e:
                last_exception = e

                # Check if error is transient
                if not self.is_transient_error(e):
                    logger.error(f"{operation_name} failed with permanent error: {e}")
                    raise

                # Check if we should retry
                if attempt < self.config.max_retries:
                    delay_ms = self.calculate_backoff_delay(attempt)
                    delay_sec = delay_ms / 1000.0

                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{self.config.max_retries + 1}): {e}. "
                        f"Retrying in {delay_ms:.0f}ms..."
                    )

                    await asyncio.sleep(delay_sec)
                else:
                    logger.error(f"{operation_name} failed after {self.config.max_retries} retries: {e}")
                    raise

        if last_exception:
            raise last_exception

    def is_transient_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient (should retry).

        Transient errors (retry):
        - HTTP 429: Rate limit
        - HTTP 500-504: Server errors

        Permanent errors (no retry):
        - HTTP 400: Bad request
        - HTTP 401: Unauthorized
        - HTTP 404: Not found

        Args:
            error: Exception to classify

        Returns:
            True if error is transient
        """
        category = self.classify_error(error)
        return category == RetryCategory.TRANSIENT

    def classify_error(self, error: Exception) -> RetryCategory:
        """
        Classify an error for retry logic.

        Args:
            error: Exception to classify

        Returns:
            RetryCategory (TRANSIENT, PERMANENT, or UNKNOWN)
        """
        # Check HTTP status if available
        if hasattr(error, 'http_status'):
            status = error.http_status
            if status in [429, 500, 502, 503, 504]:
                return RetryCategory.TRANSIENT
            if status in [400, 401, 404]:
                return RetryCategory.PERMANENT

        # Check Stripe error types
        if isinstance(error, stripe.error.RateLimitError):
            return RetryCategory.TRANSIENT
        if isinstance(error, stripe.error.APIError):
            if hasattr(error, 'http_status') and error.http_status in [429, 500, 502, 503, 504]:
                return RetryCategory.TRANSIENT
            return RetryCategory.TRANSIENT  # Assume transient if unknown
        if isinstance(error, (stripe.error.InvalidRequestError,
                              stripe.error.AuthenticationError,
                              stripe.error.PermissionError)):
            return RetryCategory.PERMANENT

        return RetryCategory.UNKNOWN

    def calculate_backoff_delay(self, attempt: int) -> int:
        """
        Calculate backoff delay for retry attempt.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in milliseconds
        """
        # Exponential backoff
        delay_ms = self.config.initial_retry_delay_ms * (
            self.config.retry_backoff_multiplier ** attempt
        )

        # Cap at max delay
        delay_ms = min(delay_ms, self.config.max_retry_delay_ms)

        # Add jitter if enabled
        if self.config.jitter_enabled:
            jitter_range = delay_ms * 0.25
            delay_ms = delay_ms + random.uniform(-jitter_range, jitter_range)

        return int(delay_ms)

    def wrap_stripe_error(self, error: Exception) -> StripeAPIError:
        """
        Wrap a Stripe error in our exception hierarchy.

        Args:
            error: Stripe error to wrap

        Returns:
            Appropriate StripeAPIError subclass
        """
        http_status = getattr(error, 'http_status', None)

        if http_status == 429:
            retry_after = getattr(error, 'headers', {}).get('Retry-After')
            return StripeRateLimitError(
                str(error),
                retry_after=int(retry_after) if retry_after else None,
                stripe_error=error
            )
        elif http_status and http_status >= 500:
            return StripeServerError(
                str(error),
                http_status=http_status,
                stripe_error=error
            )
        else:
            return StripeAPIError(
                str(error),
                stripe_error_type=type(error).__name__,
                stripe_code=getattr(error, 'code', None),
                http_status=http_status,
                is_retryable=self.is_transient_error(error),
                stripe_error=error
            )
```

**Dependencies**: `types.py`, `config.py`, `exceptions.py`

**Public Interface**:
- `RetryService` class implementing `RetryServiceProtocol`
- `execute_with_retry()` - Execute with automatic retry
- `is_transient_error()` - Classify error as transient
- `classify_error()` - Get error category
- `calculate_backoff_delay()` - Calculate retry delay
- `wrap_stripe_error()` - Wrap Stripe errors

---

### 7. `customer_service.py` - Customer CRUD Operations

**Purpose**: Stripe customer lifecycle management.

```python
"""
Customer CRUD service for Stripe operations.

Provides:
- Create customer with tenant mapping
- Retrieve customer by tenant ID
- Update customer details
- Delete customer with cleanup
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import col

from .types import CustomerServiceProtocol, CustomerData, SecretManagerProtocol
from .config import StripeConfig
from .exceptions import (
    StripeCustomerNotFoundError,
    StripeCustomerExistsError,
    StripeAPIError,
    StripeServiceError
)
from .retry_service import RetryService


logger = logging.getLogger(__name__)


class CustomerService(CustomerServiceProtocol):
    """
    Service for Stripe customer CRUD operations.

    Manages customer lifecycle with:
    - Stripe API integration
    - Database persistence
    - Tenant metadata synchronization
    """

    def __init__(
        self,
        config: Optional[StripeConfig] = None,
        retry_service: Optional[RetryService] = None,
        db_session: Optional[AsyncSession] = None
    ):
        """
        Initialize CustomerService.

        Args:
            config: Optional configuration
            retry_service: Optional retry service for API calls
            db_session: Optional database session for persistence
        """
        self.config = config or StripeConfig()
        self.retry_service = retry_service or RetryService(self.config)
        self.db_session = db_session

    async def create_customer(
        self,
        tenant_id: str,
        tenant_name: str,
        email: str,
        name: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> str:
        """
        Create Stripe customer for tenant.

        Args:
            tenant_id: Tenant identifier
            tenant_name: Tenant name for metadata
            email: Customer email address
            name: Optional customer name (defaults to tenant_name)
            created_by: Optional user who created the record

        Returns:
            Stripe customer ID (cus_*)

        Raises:
            StripeAPIError: If Stripe API call fails
        """
        try:
            customer_data = {
                "email": email,
                "name": name or tenant_name,
                "metadata": {
                    "tenant_id": tenant_id,
                    "tenant_name": tenant_name,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }

            # Create in Stripe with retry
            stripe_customer = await self.retry_service.execute_with_retry(
                func=stripe.Customer.create,
                operation_name=f"create_customer_{tenant_id}",
                **customer_data
            )

            logger.info(f"Created Stripe customer {stripe_customer.id} for tenant {tenant_id}")

            # Persist to database if session available
            if self.db_session:
                await self._persist_customer(
                    tenant_id=tenant_id,
                    stripe_customer_id=stripe_customer.id,
                    email=email,
                    name=name or tenant_name,
                    created_by=created_by
                )

            return stripe_customer.id

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error creating customer: {e}")
            raise self.retry_service.wrap_stripe_error(e)

    async def get_customer_by_tenant(
        self,
        tenant_id: str
    ) -> Optional[CustomerData]:
        """
        Retrieve Stripe customer by tenant_id.

        Args:
            tenant_id: Tenant identifier

        Returns:
            CustomerData or None if not found
        """
        if not self.db_session:
            raise StripeServiceError("Database session required for customer lookup")

        try:
            # Import here to avoid circular imports
            from src.models.stripe_billing import StripeCustomer

            statement = select(StripeCustomer).where(
                col(StripeCustomer.tenant_id) == tenant_id
            )
            result = await self.db_session.execute(statement)
            db_customer = result.scalar_one_or_none()

            if not db_customer:
                logger.info(f"No Stripe customer found for tenant {tenant_id}")
                return None

            return CustomerData(
                tenant_id=db_customer.tenant_id,
                stripe_customer_id=db_customer.stripe_customer_id,
                email=db_customer.email,
                name=db_customer.name,
                created_at=db_customer.created_at.isoformat() if db_customer.created_at else None,
                updated_at=db_customer.updated_at.isoformat() if db_customer.updated_at else None
            )

        except Exception as e:
            logger.error(f"Error retrieving customer for tenant {tenant_id}: {e}")
            raise StripeServiceError(f"Failed to retrieve customer: {e}")

    async def update_customer(
        self,
        stripe_customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> CustomerData:
        """
        Update Stripe customer.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)
            email: Optional new email
            name: Optional new name
            metadata: Optional metadata updates

        Returns:
            Updated CustomerData

        Raises:
            StripeCustomerNotFoundError: If customer doesn't exist
        """
        try:
            update_data = {}
            if email is not None:
                update_data["email"] = email
            if name is not None:
                update_data["name"] = name
            if metadata is not None:
                update_data["metadata"] = metadata

            if not update_data:
                # No updates, fetch current state
                stripe_customer = await self.retry_service.execute_with_retry(
                    func=stripe.Customer.retrieve,
                    operation_name=f"retrieve_customer_{stripe_customer_id}",
                    id=stripe_customer_id
                )
                return self._stripe_customer_to_dict(stripe_customer)

            stripe_customer = await self.retry_service.execute_with_retry(
                func=stripe.Customer.modify,
                operation_name=f"update_customer_{stripe_customer_id}",
                id=stripe_customer_id,
                **update_data
            )

            logger.info(f"Updated Stripe customer {stripe_customer_id}")

            # Sync to database
            if self.db_session and (email or name):
                await self._sync_customer_to_db(stripe_customer_id, email, name)

            return self._stripe_customer_to_dict(stripe_customer)

        except stripe.error.InvalidRequestError as e:
            if "No such customer" in str(e):
                raise StripeCustomerNotFoundError(
                    f"Customer not found: {stripe_customer_id}",
                    stripe_customer_id=stripe_customer_id
                )
            raise self.retry_service.wrap_stripe_error(e)

    async def delete_customer(
        self,
        stripe_customer_id: str
    ) -> bool:
        """
        Delete Stripe customer.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)

        Returns:
            True if deletion was successful
        """
        try:
            await self.retry_service.execute_with_retry(
                func=stripe.Customer.delete,
                operation_name=f"delete_customer_{stripe_customer_id}",
                id=stripe_customer_id
            )

            logger.info(f"Deleted Stripe customer {stripe_customer_id}")

            # Remove from database
            if self.db_session:
                await self._delete_customer_from_db(stripe_customer_id)

            return True

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error deleting customer: {e}")
            raise self.retry_service.wrap_stripe_error(e)

    async def _persist_customer(
        self,
        tenant_id: str,
        stripe_customer_id: str,
        email: str,
        name: str,
        created_by: Optional[str]
    ) -> None:
        """Persist customer to database."""
        from src.models.stripe_billing import StripeCustomer

        db_customer = StripeCustomer(
            tenant_id=tenant_id,
            stripe_customer_id=stripe_customer_id,
            email=email,
            name=name,
            created_by=created_by
        )
        self.db_session.add(db_customer)
        await self.db_session.commit()
        await self.db_session.refresh(db_customer)
        logger.info("Persisted Stripe customer mapping to database")

    async def _sync_customer_to_db(
        self,
        stripe_customer_id: str,
        email: Optional[str],
        name: Optional[str]
    ) -> None:
        """Sync customer updates to database."""
        from src.models.stripe_billing import StripeCustomer

        statement = select(StripeCustomer).where(
            col(StripeCustomer.stripe_customer_id) == stripe_customer_id
        )
        result = await self.db_session.execute(statement)
        db_customer = result.scalar_one_or_none()

        if db_customer:
            if email:
                db_customer.email = email
            if name:
                db_customer.name = name
            db_customer.updated_at = datetime.now(timezone.utc)
            await self.db_session.commit()
            logger.info("Synced customer update to database")

    async def _delete_customer_from_db(self, stripe_customer_id: str) -> None:
        """Delete customer from database."""
        from src.models.stripe_billing import StripeCustomer

        statement = select(StripeCustomer).where(
            col(StripeCustomer.stripe_customer_id) == stripe_customer_id
        )
        result = await self.db_session.execute(statement)
        db_customer = result.scalar_one_or_none()

        if db_customer:
            await self.db_session.delete(db_customer)
            await self.db_session.commit()
            logger.info("Removed customer record from database")

    def _stripe_customer_to_dict(self, stripe_customer) -> CustomerData:
        """Convert Stripe customer to CustomerData."""
        return CustomerData(
            stripe_customer_id=stripe_customer.id,
            email=stripe_customer.get("email"),
            name=stripe_customer.get("name"),
            metadata=dict(stripe_customer.get("metadata", {}))
        )
```

**Dependencies**: `types.py`, `config.py`, `exceptions.py`, `retry_service.py`

**Public Interface**:
- `CustomerService` class implementing `CustomerServiceProtocol`
- `create_customer()` - Create new customer
- `get_customer_by_tenant()` - Get customer by tenant ID
- `update_customer()` - Update customer details
- `delete_customer()` - Delete customer

---

### 8. `meter_event_service.py` - Meter Event Reporting

**Purpose**: Single meter event reporting with validation and idempotency.

```python
"""
Meter event reporting service for Stripe usage-based billing.

Provides:
- Single meter event reporting
- Validation and sanitization
- Idempotency key integration
- Database persistence
"""

import logging
from typing import Optional, Dict, Any

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from .types import MeterEventServiceProtocol, MeterEventResult, MeterType
from .config import StripeConfig
from .exceptions import StripeMeterValidationError, StripeAPIError, StripeServiceError
from .validation import ValidationService
from .idempotency_service import IdempotencyService
from .retry_service import RetryService


logger = logging.getLogger(__name__)


class MeterEventService(MeterEventServiceProtocol):
    """
    Service for reporting meter events to Stripe.

    Features:
    - Input validation
    - Idempotency key generation
    - Retry logic for transient failures
    - Database persistence
    """

    def __init__(
        self,
        config: Optional[StripeConfig] = None,
        validation_service: Optional[ValidationService] = None,
        idempotency_service: Optional[IdempotencyService] = None,
        retry_service: Optional[RetryService] = None,
        db_session: Optional[AsyncSession] = None
    ):
        """
        Initialize MeterEventService.

        Args:
            config: Optional configuration
            validation_service: Optional validation service
            idempotency_service: Optional idempotency service
            retry_service: Optional retry service
            db_session: Optional database session
        """
        self.config = config or StripeConfig()
        self.validation = validation_service or ValidationService(self.config)
        self.idempotency = idempotency_service or IdempotencyService(self.config, self.validation)
        self.retry = retry_service or RetryService(self.config)
        self.db_session = db_session

    async def report_usage(
        self,
        meter_event: str,
        value: int,
        tenant_id: str,
        metadata: Optional[Dict[str, str]] = None,
        stripe_customer_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> MeterEventResult:
        """
        Report meter event usage to Stripe.

        Args:
            meter_event: Meter event name (ai_labels, human_audits)
            value: Quantity to report (positive integer)
            tenant_id: Tenant identifier
            metadata: Optional metadata dictionary
            stripe_customer_id: Optional Stripe customer ID
            batch_id: Optional batch identifier

        Returns:
            MeterEventResult with event details

        Raises:
            StripeMeterValidationError: If validation fails
            StripeAPIError: If Stripe API call fails
        """
        # Validate meter event
        validation_errors = self.validation.validate_meter_event(meter_event, value)
        if validation_errors:
            raise StripeMeterValidationError(
                f"Meter event validation failed for '{meter_event}'",
                meter_event=meter_event,
                validation_errors=validation_errors
            )

        # Get meter ID
        meter_id = self.config.get_meter_id(MeterType(meter_event))
        if not meter_id:
            raise StripeMeterValidationError(
                f"Meter ID not configured for event '{meter_event}'. "
                f"Please set STRIPE_{meter_event.upper()}_METER_ID environment variable.",
                meter_event=meter_event
            )

        # Generate idempotency key
        idempotency_key = self.idempotency.generate_key(
            tenant_id=tenant_id,
            meter_event=meter_event,
            value=value,
            batch_id=batch_id
        )

        # Sanitize metadata
        sanitized_metadata = None
        if metadata:
            sanitized_metadata = self.validation.sanitize_metadata(metadata)

        # Create database record
        db_event = None
        if self.db_session:
            db_event = await self._create_db_event(
                tenant_id=tenant_id,
                meter_event=meter_event,
                value=value,
                idempotency_key=idempotency_key
            )

        try:
            # Report to Stripe with retry
            stripe_response = await self.retry.execute_with_retry(
                func=self._report_to_stripe,
                operation_name=f"report_meter_event_{meter_event}",
                meter_id=meter_id,
                event_name=meter_event,
                value=value,
                idempotency_key=idempotency_key,
                customer_id=stripe_customer_id,
                metadata=sanitized_metadata,
                batch_id=batch_id
            )

            # Update database as succeeded
            if self.db_session and db_event:
                await self._update_db_event_success(db_event, stripe_response)

            logger.info(
                f"Successfully reported meter event {meter_event}={value} "
                f"for tenant {tenant_id}"
            )

            return MeterEventResult(
                event_id=idempotency_key,
                status="succeeded",
                stripe_response=stripe_response,
                meter_event=meter_event,
                value=value
            )

        except stripe.error.StripeError as e:
            if self.db_session and db_event:
                await self._update_db_event_failure(db_event, str(e))

            logger.error(f"Stripe API error reporting meter event: {e}")
            raise self.retry.wrap_stripe_error(e)

        except Exception as e:
            if self.db_session and db_event:
                await self._update_db_event_failure(db_event, str(e))

            logger.error(f"Unexpected error reporting meter event: {e}")
            raise StripeServiceError(f"Failed to report meter event: {e}")

    def _report_to_stripe(
        self,
        meter_id: str,
        event_name: str,
        value: int,
        idempotency_key: str,
        customer_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Report meter event to Stripe API."""
        payload = {"value": str(value)}

        if customer_id:
            payload["stripe_customer_id"] = customer_id
        if batch_id:
            payload["batch_id"] = batch_id
        if metadata:
            payload.update(metadata)

        try:
            event = stripe.Billing.MeterEvent.create(
                event_name=event_name,
                payload=payload,
                idempotency_key=idempotency_key
            )
            return dict(event)
        except AttributeError:
            # Fallback for older SDK
            import stripe.api_requestor
            requestor = stripe.api_requestor.APIRequestor()
            response, _ = requestor.request(
                method="post",
                url="/v2/billing/meter_event_stream",
                params={
                    "event_name": event_name,
                    "payload": payload,
                    "idempotency_key": idempotency_key
                }
            )
            return response.data

    async def _create_db_event(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        idempotency_key: str
    ):
        """Create pending database event record."""
        from src.models.stripe_billing import StripeMeterEvent, StripeMeterEventStatus

        db_event = StripeMeterEvent(
            tenant_id=tenant_id,
            event_name=meter_event,
            quantity=value,
            idempotency_key=idempotency_key,
            status=StripeMeterEventStatus.PENDING
        )
        self.db_session.add(db_event)
        await self.db_session.commit()
        await self.db_session.refresh(db_event)
        return db_event

    async def _update_db_event_success(self, db_event, stripe_response: Dict):
        """Update database event as succeeded."""
        from src.models.stripe_billing import StripeMeterEventStatus

        db_event.status = StripeMeterEventStatus.SUCCEEDED
        db_event.stripe_response = stripe_response
        await self.db_session.commit()
        await self.db_session.refresh(db_event)

    async def _update_db_event_failure(self, db_event, error_message: str):
        """Update database event as failed."""
        from src.models.stripe_billing import StripeMeterEventStatus

        db_event.status = StripeMeterEventStatus.FAILED
        db_event.error_message = error_message
        await self.db_session.commit()
```

**Dependencies**: `types.py`, `config.py`, `exceptions.py`, `validation.py`, `idempotency_service.py`, `retry_service.py`

**Public Interface**:
- `MeterEventService` class implementing `MeterEventServiceProtocol`
- `report_usage()` - Report single meter event

---

### 9. `batch_processor.py` - Batch Operations

**Purpose**: Process multiple meter events with partial failure handling.

```python
"""
Batch processor for multiple meter events.

Provides:
- Batch event processing with partial failure handling
- Batch ID generation
- Aggregated results tracking
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from .types import BatchProcessorProtocol, BatchResult, MeterEventData
from .config import StripeConfig
from .exceptions import StripeMeterValidationError, StripeAPIError, StripeServiceError
from .validation import ValidationService
from .meter_event_service import MeterEventService


logger = logging.getLogger(__name__)


class BatchProcessor(BatchProcessorProtocol):
    """
    Batch processor for multiple meter events.

    Features:
    - Validates batch size and event structure
    - Processes events sequentially with partial failure handling
    - Tracks successes and failures separately
    """

    def __init__(
        self,
        config: Optional[StripeConfig] = None,
        validation_service: Optional[ValidationService] = None,
        meter_event_service: Optional[MeterEventService] = None,
        db_session: Optional[AsyncSession] = None
    ):
        """
        Initialize BatchProcessor.

        Args:
            config: Optional configuration
            validation_service: Optional validation service
            meter_event_service: Optional meter event service
            db_session: Optional database session
        """
        self.config = config or StripeConfig()
        self.validation = validation_service or ValidationService(self.config)
        self.meter_event_service = meter_event_service
        self.db_session = db_session

        # Create meter event service if not provided
        if not self.meter_event_service:
            self.meter_event_service = MeterEventService(
                config=self.config,
                validation_service=self.validation,
                db_session=self.db_session
            )

    async def process_batch(
        self,
        events: List[MeterEventData],
        tenant_id: str,
        stripe_customer_id: Optional[str] = None
    ) -> BatchResult:
        """
        Process a batch of meter events.

        Args:
            events: List of meter event data dictionaries
            tenant_id: Tenant identifier
            stripe_customer_id: Optional Stripe customer ID

        Returns:
            BatchResult with success/failure details

        Raises:
            StripeMeterValidationError: If batch validation fails
        """
        # Generate batch ID
        batch_id = self.generate_batch_id(tenant_id)

        # Initialize result
        result = BatchResult(
            batch_id=batch_id,
            total_events=len(events),
            successful_count=0,
            failed_count=0,
            successes=[],
            failures=[]
        )

        # Handle empty batch
        if not events:
            logger.info(f"Empty batch received for tenant {tenant_id}")
            return result

        # Validate batch size
        self.validation.validate_batch_size(len(events))

        # Validate event structure
        validation_errors = self.validation.validate_batch_events(events)
        if validation_errors:
            raise StripeMeterValidationError(
                f"Batch event validation failed: {'; '.join(validation_errors)}",
                validation_errors=validation_errors
            )

        # Process each event
        for event_data in events:
            meter_event = event_data["meter_event"]
            value = event_data["value"]
            event_metadata = event_data.get("metadata", {})

            try:
                event_result = await self.meter_event_service.report_usage(
                    meter_event=meter_event,
                    value=value,
                    tenant_id=tenant_id,
                    metadata=event_metadata,
                    stripe_customer_id=stripe_customer_id,
                    batch_id=batch_id
                )

                result.successes.append(dict(event_result))
                result.successful_count += 1

            except (StripeMeterValidationError, StripeAPIError, StripeServiceError) as e:
                failure_info = self._create_failure_info(event_data, e)
                result.failures.append(failure_info)
                result.failed_count += 1

                logger.warning(
                    f"Event failed in batch {batch_id}: {meter_event}={value} - {str(e)}"
                )

            except Exception as e:
                failure_info = self._create_failure_info(event_data, e, is_unexpected=True)
                result.failures.append(failure_info)
                result.failed_count += 1

                logger.error(
                    f"Unexpected error processing event in batch {batch_id}: "
                    f"{meter_event}={value} - {str(e)}"
                )

        logger.info(
            f"Batch {batch_id} completed: "
            f"{result.successful_count}/{result.total_events} succeeded, "
            f"{result.failed_count} failed"
        )

        return result

    def generate_batch_id(self, tenant_id: str) -> str:
        """
        Generate unique batch ID.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Unique batch ID string
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        return f"batch_{tenant_id}_{timestamp}_{unique_suffix}"

    def _create_failure_info(
        self,
        event_data: MeterEventData,
        error: Exception,
        is_unexpected: bool = False
    ) -> Dict[str, Any]:
        """Create failure info dictionary."""
        failure_info = {
            "event": {
                "meter_event": event_data["meter_event"],
                "value": event_data["value"],
                "metadata": event_data.get("metadata", {})
            },
            "error": f"Unexpected error: {str(error)}" if is_unexpected else str(error),
            "error_type": "UnexpectedError" if is_unexpected else type(error).__name__
        }

        if hasattr(error, 'validation_errors') and error.validation_errors:
            failure_info["validation_errors"] = error.validation_errors
        if hasattr(error, 'meter_event'):
            failure_info["meter_event"] = error.meter_event

        return failure_info
```

**Dependencies**: `types.py`, `config.py`, `exceptions.py`, `validation.py`, `meter_event_service.py`

**Public Interface**:
- `BatchProcessor` class implementing `BatchProcessorProtocol`
- `process_batch()` - Process batch of events
- `generate_batch_id()` - Generate unique batch ID

---

### 10. `base.py` - Base Service & Initialization

**Purpose**: Service initialization and API key management.

```python
"""
Base service class for Stripe service initialization.

Provides:
- API key initialization from SecretManager
- Service initialization validation
- Common service utilities
"""

import logging
from typing import Optional

import stripe

from .types import SecretManagerProtocol
from .config import StripeConfig
from .exceptions import StripeInitializationError


logger = logging.getLogger(__name__)


class StripeServiceBase:
    """
    Base class for Stripe service initialization.

    Handles:
    - API key retrieval from SecretManager
    - Stripe client configuration
    - Initialization state tracking
    """

    def __init__(
        self,
        config: Optional[StripeConfig] = None,
        secret_manager: Optional[SecretManagerProtocol] = None
    ):
        """
        Initialize StripeServiceBase.

        Args:
            config: Optional configuration
            secret_manager: Optional secret manager (uses default if not provided)
        """
        self.config = config or StripeConfig()
        self._secret_manager = secret_manager
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize Stripe client with API key.

        Retrieves API key from SecretManager and configures Stripe client.

        Raises:
            StripeInitializationError: If initialization fails
        """
        if self._initialized:
            logger.warning("StripeService already initialized")
            return

        try:
            # Get secret manager
            if self._secret_manager is None:
                from src.core.secret_manager import SecretManager
                self._secret_manager = SecretManager()

            # Get API key
            api_key = self._secret_manager.get_secret("STRIPE_SECRET_KEY")

            if not api_key:
                raise StripeInitializationError(
                    "Stripe API key not found in SecretManager. "
                    "Please set STRIPE_SECRET_KEY in your environment."
                )

            # Store in config
            self.config.api_key = api_key

            # Configure Stripe
            stripe.api_key = api_key

            self._initialized = True
            logger.info("StripeService initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize StripeService: {e}")
            raise StripeInitializationError(f"Failed to initialize StripeService: {e}")

    def ensure_initialized(self) -> None:
        """
        Ensure service is initialized.

        Raises:
            StripeInitializationError: If not initialized
        """
        if not self._initialized:
            raise StripeInitializationError(
                "StripeService not initialized. Call initialize() before using the service."
            )

    @property
    def is_initialized(self) -> bool:
        """Check if service is initialized."""
        return self._initialized
```

**Dependencies**: `types.py`, `config.py`, `exceptions.py`

**Public Interface**:
- `StripeServiceBase` class
- `initialize()` - Initialize service
- `ensure_initialized()` - Validate initialization
- `is_initialized` property

---

### 11. `__init__.py` - Public API & Facade

**Purpose**: Provide backward-compatible facade and public API exports.

```python
"""
Stripe Service Package - Public API

This package provides modular Stripe billing services:
- CustomerService: Customer CRUD operations
- MeterEventService: Single meter event reporting
- BatchProcessor: Batch meter event processing
- IdempotencyService: Idempotency key management
- RetryService: Retry logic with exponential backoff
- ValidationService: Input validation and sanitization

For backward compatibility, the StripeService facade is provided
which maintains the original monolithic API.

Usage (New Modular API):
    from src.services.stripe import (
        CustomerService,
        MeterEventService,
        BatchProcessor,
        StripeConfig
    )

    config = StripeConfig.from_environment()
    customer_service = CustomerService(config=config, db_session=session)
    await customer_service.create_customer(...)

Usage (Backward Compatible):
    from src.services.stripe import StripeService

    service = StripeService()
    await service.initialize()
    await service.create_customer(...)
"""

# Configuration
from .config import StripeConfig

# Types and Protocols
from .types import (
    MeterType,
    EventStatus,
    RetryCategory,
    CustomerData,
    MeterEventData,
    MeterEventResult,
    BatchResult,
    CollisionMetrics,
    # Protocols for dependency injection
    StripeClientProtocol,
    SecretManagerProtocol,
    IdempotencyServiceProtocol,
    RetryServiceProtocol,
    ValidationServiceProtocol,
    MeterEventServiceProtocol,
    BatchProcessorProtocol,
    CustomerServiceProtocol,
)

# Exceptions
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

# Services
from .base import StripeServiceBase
from .validation import ValidationService
from .idempotency_service import IdempotencyService
from .retry_service import RetryService
from .customer_service import CustomerService
from .meter_event_service import MeterEventService
from .batch_processor import BatchProcessor

# Backward compatible facade
from .facade import StripeService


__all__ = [
    # Configuration
    "StripeConfig",

    # Types
    "MeterType",
    "EventStatus",
    "RetryCategory",
    "CustomerData",
    "MeterEventData",
    "MeterEventResult",
    "BatchResult",
    "CollisionMetrics",

    # Protocols
    "StripeClientProtocol",
    "SecretManagerProtocol",
    "IdempotencyServiceProtocol",
    "RetryServiceProtocol",
    "ValidationServiceProtocol",
    "MeterEventServiceProtocol",
    "BatchProcessorProtocol",
    "CustomerServiceProtocol",

    # Exceptions
    "StripeServiceError",
    "StripeInitializationError",
    "StripeAPIError",
    "StripeRateLimitError",
    "StripeServerError",
    "StripeCustomerError",
    "StripeCustomerNotFoundError",
    "StripeCustomerExistsError",
    "StripeMeterError",
    "StripeMeterValidationError",
    "StripeMeterQuotaError",
    "StripeIdempotencyError",
    "StripeIdempotencyKeyTooLongError",
    "StripeBatchError",

    # Services
    "StripeServiceBase",
    "ValidationService",
    "IdempotencyService",
    "RetryService",
    "CustomerService",
    "MeterEventService",
    "BatchProcessor",

    # Facade (backward compatible)
    "StripeService",
]
```

---

### 12. `facade.py` - Backward Compatible Facade

**Purpose**: Maintain backward compatibility with existing StripeService API.

```python
"""
Backward-compatible facade for StripeService.

This facade maintains the original StripeService API while delegating
to the new modular services internally. Existing code using StripeService
will continue to work without modification.

Migration Path:
1. Continue using StripeService facade (no changes required)
2. Gradually migrate to modular services for new code
3. Eventually deprecate facade when all code migrated
"""

import logging
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from .types import BatchResult, MeterType, SecretManagerProtocol
from .config import StripeConfig
from .base import StripeServiceBase
from .customer_service import CustomerService
from .meter_event_service import MeterEventService
from .batch_processor import BatchProcessor
from .idempotency_service import IdempotencyService
from .validation import ValidationService
from .retry_service import RetryService
from .exceptions import StripeServiceError, StripeMeterValidationError


logger = logging.getLogger(__name__)


class StripeService(StripeServiceBase):
    """
    Backward-compatible facade for Stripe billing operations.

    This class maintains the original StripeService API while delegating
    to modular services internally. All existing code will continue to work.

    Attributes:
        METER_AI_LABELS: Meter type constant for AI labels
        METER_HUMAN_AUDITS: Meter type constant for human audits
        MAX_BATCH_SIZE: Maximum batch size constant
    """

    # Backward compatible constants
    METER_AI_LABELS = MeterType.AI_LABELS.value
    METER_HUMAN_AUDITS = MeterType.HUMAN_AUDITS.value
    MAX_BATCH_SIZE = 100
    RESERVED_METADATA_KEYS = {"value", "stripe_customer_id", "batch_id"}
    MAX_IDEMPOTENCY_KEY_LENGTH = 255
    IDEMPOTENCY_KEY_RETENTION_HOURS = 24
    MAX_IDEMPOTENCY_REGISTRY_SIZE = 10000

    def __init__(
        self,
        config: Optional[StripeConfig] = None,
        secret_manager: Optional[SecretManagerProtocol] = None
    ):
        """
        Initialize StripeService facade.

        Args:
            config: Optional configuration
            secret_manager: Optional secret manager
        """
        super().__init__(config=config, secret_manager=secret_manager)

        # Internal services (lazy initialized)
        self._validation: Optional[ValidationService] = None
        self._idempotency: Optional[IdempotencyService] = None
        self._retry: Optional[RetryService] = None
        self._customer: Optional[CustomerService] = None
        self._meter_event: Optional[MeterEventService] = None
        self._batch_processor: Optional[BatchProcessor] = None

        # Backward compatible retry config from environment
        import os
        self.MAX_RETRIES = int(os.getenv("STRIPE_MAX_RETRIES", "5"))
        self.INITIAL_RETRY_DELAY_MS = int(os.getenv("STRIPE_INITIAL_RETRY_DELAY_MS", "1000"))
        self.MAX_RETRY_DELAY_MS = int(os.getenv("STRIPE_MAX_RETRY_DELAY_MS", "32000"))
        self.RETRY_BACKOFF_MULTIPLIER = 2.0

    def _ensure_initialized(self) -> None:
        """Backward compatible initialization check."""
        self.ensure_initialized()

    def _get_services(self, db_session: Optional[AsyncSession] = None):
        """Lazy initialize internal services."""
        if self._validation is None:
            self._validation = ValidationService(self.config)
        if self._idempotency is None:
            self._idempotency = IdempotencyService(self.config, self._validation)
        if self._retry is None:
            self._retry = RetryService(self.config)
        if self._customer is None:
            self._customer = CustomerService(
                config=self.config,
                retry_service=self._retry,
                db_session=db_session
            )
        if self._meter_event is None:
            self._meter_event = MeterEventService(
                config=self.config,
                validation_service=self._validation,
                idempotency_service=self._idempotency,
                retry_service=self._retry,
                db_session=db_session
            )
        if self._batch_processor is None:
            self._batch_processor = BatchProcessor(
                config=self.config,
                validation_service=self._validation,
                meter_event_service=self._meter_event,
                db_session=db_session
            )

        # Update db_session if provided
        if db_session:
            self._customer.db_session = db_session
            self._meter_event.db_session = db_session
            self._batch_processor.db_session = db_session

    # ========================================================================
    # Customer CRUD (P1-002)
    # ========================================================================

    async def create_customer(
        self,
        tenant,  # Tenant object for backward compatibility
        email: str,
        name: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
        created_by: Optional[str] = None
    ) -> str:
        """
        Create Stripe customer for tenant.

        Backward compatible API - delegates to CustomerService.
        """
        self._ensure_initialized()
        self._get_services(db_session)

        return await self._customer.create_customer(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.name,
            email=email,
            name=name,
            created_by=created_by
        )

    async def get_customer_by_tenant(
        self,
        tenant_id: str,
        db_session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve Stripe customer by tenant_id.

        Backward compatible API - delegates to CustomerService.
        """
        self._ensure_initialized()
        self._get_services(db_session)

        result = await self._customer.get_customer_by_tenant(tenant_id)
        return dict(result) if result else None

    async def update_customer(
        self,
        stripe_customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        db_session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Update Stripe customer.

        Backward compatible API - delegates to CustomerService.
        """
        self._ensure_initialized()
        self._get_services(db_session)

        result = await self._customer.update_customer(
            stripe_customer_id=stripe_customer_id,
            email=email,
            name=name,
            metadata=metadata
        )
        return dict(result)

    async def delete_customer(
        self,
        stripe_customer_id: str,
        db_session: Optional[AsyncSession] = None
    ) -> bool:
        """
        Delete Stripe customer.

        Backward compatible API - delegates to CustomerService.
        """
        self._ensure_initialized()
        self._get_services(db_session)

        return await self._customer.delete_customer(stripe_customer_id)

    # ========================================================================
    # Meter Event Reporting (P02-001)
    # ========================================================================

    async def report_usage(
        self,
        meter_event: str,
        value: int,
        tenant_id: str,
        metadata: Optional[Dict[str, str]] = None,
        stripe_customer_id: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Report meter event usage to Stripe.

        Backward compatible API - delegates to MeterEventService.
        """
        self._ensure_initialized()
        self._get_services(db_session)

        result = await self._meter_event.report_usage(
            meter_event=meter_event,
            value=value,
            tenant_id=tenant_id,
            metadata=metadata,
            stripe_customer_id=stripe_customer_id,
            batch_id=batch_id
        )
        return dict(result)

    # ========================================================================
    # Batch Processing (P02-002)
    # ========================================================================

    async def report_usage_batch(
        self,
        events: List[Dict[str, Any]],
        tenant_id: str,
        stripe_customer_id: Optional[str] = None,
        db_session: Optional[AsyncSession] = None
    ) -> BatchResult:
        """
        Report multiple meter events in a batch.

        Backward compatible API - delegates to BatchProcessor.
        """
        self._ensure_initialized()
        self._get_services(db_session)

        return await self._batch_processor.process_batch(
            events=events,
            tenant_id=tenant_id,
            stripe_customer_id=stripe_customer_id
        )

    # ========================================================================
    # Backward Compatible Private Methods
    # ========================================================================

    def _validate_meter_event(self, meter_event: str, value: int) -> List[str]:
        """Backward compatible validation."""
        if self._validation is None:
            self._validation = ValidationService(self.config)
        return self._validation.validate_meter_event(meter_event, value)

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """Backward compatible metadata sanitization."""
        if self._validation is None:
            self._validation = ValidationService(self.config)
        return self._validation.sanitize_metadata(metadata)

    def _validate_batch_events(self, events: List[Dict[str, Any]]) -> None:
        """Backward compatible batch validation."""
        if self._validation is None:
            self._validation = ValidationService(self.config)
        errors = self._validation.validate_batch_events(events)
        if errors:
            raise StripeMeterValidationError(
                f"Batch event validation failed: {'; '.join(errors)}",
                validation_errors=errors
            )

    def _generate_batch_id(self, tenant_id: str) -> str:
        """Backward compatible batch ID generation."""
        if self._batch_processor is None:
            self._batch_processor = BatchProcessor(config=self.config)
        return self._batch_processor.generate_batch_id(tenant_id)

    def _generate_idempotency_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        batch_id: Optional[str] = None
    ) -> str:
        """Backward compatible idempotency key generation."""
        if self._idempotency is None:
            self._idempotency = IdempotencyService(self.config)
        return self._idempotency.generate_key(tenant_id, meter_event, value, batch_id)

    def _get_collision_metrics(self) -> Dict[str, Any]:
        """Backward compatible collision metrics."""
        if self._idempotency is None:
            self._idempotency = IdempotencyService(self.config)
        metrics = self._idempotency.get_metrics()
        return {
            'total_keys_generated': metrics.total_keys_generated,
            'collision_count': metrics.collision_count,
            'near_collision_count': metrics.near_collision_count,
            'collision_rate': metrics.collision_rate,
            'registry_size': metrics.registry_size
        }

    def _calculate_backoff_delay(self, attempt: int) -> int:
        """Backward compatible backoff calculation."""
        if self._retry is None:
            self._retry = RetryService(self.config)
        return self._retry.calculate_backoff_delay(attempt)

    def _is_transient_error(self, error: Exception) -> bool:
        """Backward compatible transient error check."""
        if self._retry is None:
            self._retry = RetryService(self.config)
        return self._retry.is_transient_error(error)

    async def _retry_with_backoff(
        self,
        func,
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """Backward compatible retry with backoff."""
        if self._retry is None:
            self._retry = RetryService(self.config)
        return await self._retry.execute_with_retry(func, operation_name, *args, **kwargs)
```

---

## Dependency Graph

```
                    +-----------+
                    |  types.py |  (Foundation - no deps)
                    +-----------+
                          |
         +----------------+----------------+
         |                |                |
         v                v                v
  +------------+  +-----------+    +------------+
  |exceptions.py|  | config.py|    |            |
  +------------+  +-----------+    |            |
         |                |        |            |
         +--------+-------+        |            |
                  |                |            |
                  v                |            |
           +-------------+         |            |
           |validation.py|<--------+            |
           +-------------+                      |
                  |                             |
         +--------+--------+                    |
         |                 |                    |
         v                 v                    |
+------------------+  +-------------+           |
|idempotency_service|  |retry_service|           |
+------------------+  +-------------+           |
         |                 |                    |
         +--------+--------+                    |
                  |                             |
                  v                             |
        +------------------+                    |
        |meter_event_service|                   |
        +------------------+                    |
                  |                             |
         +--------+--------+                    |
         |                 |                    |
         v                 v                    |
+---------------+  +----------------+           |
|batch_processor|  |customer_service|<----------+
+---------------+  +----------------+
         |                 |
         +--------+--------+
                  |
                  v
            +---------+
            | base.py |
            +---------+
                  |
                  v
            +-----------+
            | facade.py |  (StripeService)
            +-----------+
                  |
                  v
            +-----------+
            |__init__.py|  (Public exports)
            +-----------+
```

---

## Integration with Existing Code

### UsageCalculationService Integration

The `UsageCalculationService` (P02-005) already works with the StripeService interface. With the new modular architecture:

```python
# Before (still works via facade)
from src.services.stripe_service import StripeService

stripe_service = StripeService()
await stripe_service.initialize()
await stripe_service.report_usage(...)

# After (new modular approach)
from src.services.stripe import MeterEventService, BatchProcessor, StripeConfig

config = StripeConfig.from_environment()
meter_service = MeterEventService(config=config, db_session=session)
batch_processor = BatchProcessor(config=config, meter_event_service=meter_service)

# Use batch processor for pipeline integration
batch = usage_calc_service.prepare_meter_events_batch(usage, batch_id="...")
result = await batch_processor.process_batch(batch["events"], tenant_id="...")
```

### Test Migration Strategy

1. **Phase 1**: Keep existing tests working via facade
2. **Phase 2**: Add new tests for individual services
3. **Phase 3**: Migrate existing tests to use modular services
4. **Phase 4**: Deprecate facade tests

---

## Testing Strategy

### Unit Tests per Module

Each module gets its own test file:

```
tests/unit/services/stripe/
├── test_types.py                    # Type validation tests
├── test_exceptions.py               # Exception hierarchy tests
├── test_config.py                   # Configuration tests
├── test_validation.py               # Validation service tests
├── test_idempotency_service.py      # Idempotency tests
├── test_retry_service.py            # Retry logic tests
├── test_customer_service.py         # Customer CRUD tests
├── test_meter_event_service.py      # Meter event tests
├── test_batch_processor.py          # Batch processing tests
├── test_base.py                     # Base service tests
├── test_facade.py                   # Facade backward compatibility tests
└── conftest.py                      # Shared fixtures
```

### Mocking Strategy

The Protocol-based design enables easy mocking:

```python
# Mock IdempotencyService for MeterEventService tests
class MockIdempotencyService:
    def generate_key(self, tenant_id, meter_event, value, batch_id=None):
        return f"mock_key_{tenant_id}_{meter_event}"

    def is_registered(self, key):
        return False

    def register_key(self, key):
        pass

    def get_metrics(self):
        return CollisionMetrics()

# Use in test
meter_service = MeterEventService(
    idempotency_service=MockIdempotencyService()
)
```

---

## Migration Plan

### Phase 1: Create Module Structure (Week 1)
1. Create `src/services/stripe/` directory
2. Implement `types.py`, `exceptions.py`, `config.py`
3. Implement `validation.py`

### Phase 2: Core Services (Week 2)
1. Implement `idempotency_service.py`
2. Implement `retry_service.py`
3. Unit tests for each

### Phase 3: Domain Services (Week 3)
1. Implement `customer_service.py`
2. Implement `meter_event_service.py`
3. Implement `batch_processor.py`
4. Unit tests for each

### Phase 4: Integration (Week 4)
1. Implement `base.py`
2. Implement `facade.py`
3. Implement `__init__.py`
4. Integration tests
5. Verify backward compatibility

### Phase 5: Deprecation (Future)
1. Add deprecation warnings to facade
2. Migrate all consumers to modular services
3. Remove facade

---

## Benefits of This Architecture

1. **Single Responsibility**: Each module has one clear purpose
2. **Testability**: Protocols enable easy mocking
3. **Extensibility**: Add new meter types without modifying core logic
4. **Maintainability**: Smaller files, clearer dependencies
5. **Backward Compatibility**: Facade preserves existing API
6. **Type Safety**: Protocols and TypedDicts provide clear contracts
7. **Configuration**: Centralized, validated configuration
8. **Error Handling**: Rich exception hierarchy with context
