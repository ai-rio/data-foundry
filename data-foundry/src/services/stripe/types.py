"""
Type definitions and protocols for Stripe service modules.

This module defines:
- Protocol classes for dependency injection (allowing mock implementations)
- TypedDict definitions for structured data
- Enums for meter types and status codes
- Data classes for complex data structures

Phase: 2.5.1 (Foundation Layer)
Task: 2.5.1.1 - Create types.py with all Protocols & DTOs

Security Considerations:
- Type safety prevents runtime errors from incorrect data types
- Protocol definitions enable secure dependency injection for testing
- TypedDict structures enforce data validation at type-check level
"""

from typing import Protocol, TypedDict, Optional, Dict, Any, List, Callable, Awaitable, runtime_checkable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


# ============================================================================
# Enums
# ============================================================================

class MeterType(str, Enum):
    """Supported meter event types for usage-based billing.

    These correspond to Stripe meter IDs configured in the environment:
    - METER_AI_LABELS: AI-powered data labeling usage meter
    - METER_HUMAN_AUDITS: Human review workflow usage meter
    """
    AI_LABELS = "ai_labels"
    HUMAN_AUDITS = "human_audits"


class SubscriptionTier(str, Enum):
    """Subscription pricing tiers for Data Foundry billing.

    These correspond to Stripe price IDs configured in the environment:
    - GOLD: Premium tier with lowest per-unit costs ($0.08 AI labels, $99 platform fee)
    - SILVER: Mid-tier with balanced pricing ($0.10 AI labels, $49 platform fee)
    - BRONZE: Basic tier with higher per-unit costs ($0.12 AI labels, $0 platform fee)

    Task: P3-003 (Price ID Configuration)
    """
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


class PriceType(str, Enum):
    """Price types for subscription components.

    These correspond to the different billing components for each tier:
    - AI_LABELS: Per-unit price for AI-powered data labeling
    - HUMAN_AUDITS: Per-unit price for human review workflows (metered)
    - PLATFORM_FEE: Recurring monthly platform access fee

    Task: P3-003 (Price ID Configuration)
    """
    AI_LABELS = "ai_labels"
    HUMAN_AUDITS = "human_audits"
    PLATFORM_FEE = "platform_fee"


class EventStatus(str, Enum):
    """Status of a meter event.

    PENDING: Event is being processed or queued
    SUCCEEDED: Event was successfully reported to Stripe
    FAILED: Event failed during reporting
    """
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RetryCategory(str, Enum):
    """Classification of errors for retry logic.

    TRANSIENT: Errors that should be retried (429 rate limits, 5xx server errors)
    PERMANENT: Errors that should not be retried (400 bad request, 401 unauthorized, 404 not found)
    UNKNOWN: Default behavior when error type cannot be determined
    """
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


# ============================================================================
# TypedDict Definitions
# ============================================================================

class CustomerData(TypedDict, total=False):
    """Customer data structure for Stripe operations.

    Used for transferring customer information between service layers
    and for API responses. All fields are optional to support partial updates.
    """
    tenant_id: str
    stripe_customer_id: str
    email: Optional[str]
    name: Optional[str]
    metadata: Dict[str, str]
    created_at: Optional[str]
    updated_at: Optional[str]


class MeterEventData(TypedDict):
    """Meter event data structure.

    Represents a single meter event to be reported to Stripe.
    This is the input format for batch processing operations.
    """
    meter_event: str
    value: int
    tenant_id: str
    metadata: Optional[Dict[str, str]]


class MeterEventResult(TypedDict):
    """Result of a meter event submission.

    Returned by meter event reporting operations to indicate
    success or failure and provide additional context.
    """
    event_id: str
    status: str
    stripe_response: Optional[Dict[str, Any]]
    meter_event: str
    value: int


class RetryConfig(TypedDict, total=False):
    """Retry configuration settings.

    Controls the exponential backoff behavior for transient failures.
    All fields are optional with sensible defaults.
    """
    max_retries: int
    initial_delay_ms: int
    max_delay_ms: int
    backoff_multiplier: float
    jitter_enabled: bool


class IdempotencyConfig(TypedDict, total=False):
    """Idempotency configuration settings.

    Controls idempotency key generation and registry behavior.
    """
    max_key_length: int
    retention_hours: int
    max_registry_size: int


class PriceIdMapping(TypedDict, total=False):
    """Mapping of subscription tier and price type to Stripe price IDs.

    Structure: {price_type: price_id}
    Example: {"ai_labels": "price_123", "human_audits": "price_456", "platform_fee": "price_789"}

    Task: P3-003 (Price ID Configuration)
    """
    ai_labels: str
    human_audits: str
    platform_fee: str


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class BatchResult:
    """
    Result of a batch meter event reporting operation.

    Tracks the outcome of processing multiple meter events in a single batch.
    Provides detailed information about successful and failed events.

    Attributes:
        batch_id: Unique identifier for this batch operation
        total_events: Total number of events in the batch
        successful_count: Number of events that succeeded
        failed_count: Number of events that failed
        successes: List of successful event results
        failures: List of failed event results with error details

    Example:
        >>> result = BatchResult(
        ...     batch_id="batch_20250125_1234",
        ...     total_events=5,
        ...     successful_count=4,
        ...     failed_count=1,
        ...     successes=[...],
        ...     failures=[...]
        ... )
        >>> print(f"Processed {result.successful_count}/{result.total_events}")
    """
    batch_id: str
    total_events: int
    successful_count: int
    failed_count: int
    successes: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class IdempotencyKeyInfo:
    """
    Information about an idempotency key.

    Encapsulates metadata about a registered idempotency key
    for tracking and debugging purposes.

    Attributes:
        key: The idempotency key string
        registered_at: Timestamp when the key was registered
        tenant_id: Tenant identifier associated with the key
        meter_event: Meter event name
        value: Event value/quantity
        batch_id: Optional batch identifier for batch operations
    """
    key: str
    registered_at: datetime
    tenant_id: str
    meter_event: str
    value: int
    batch_id: Optional[str] = None


@dataclass
class CollisionMetrics:
    """
    Metrics for idempotency key collision detection.

    Tracks statistics about key generation to detect potential
    issues with uniqueness or high-volume concurrent requests.

    Attributes:
        total_keys_generated: Total number of keys generated
        collision_count: Number of exact collisions detected
        near_collision_count: Number of near-collisions detected
        registry_size: Current size of the idempotency registry

    Example:
        >>> metrics = CollisionMetrics(
        ...     total_keys_generated=1000,
        ...     collision_count=0,
        ...     near_collision_count=2,
        ...     registry_size=500
        ... )
        >>> print(f"Collision rate: {metrics.collision_rate:.2f}%")
    """
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

    Allows injection of mock clients for testing without depending
    on the actual Stripe SDK. Defines the contract that any Stripe
    client implementation must satisfy.
    """

    def create_customer(self, **kwargs) -> Dict[str, Any]:
        """Create a Stripe customer.

        Args:
            **kwargs: Customer creation parameters

        Returns:
            Dictionary representing the created customer
        """
        ...

    def retrieve_customer(self, customer_id: str) -> Dict[str, Any]:
        """Retrieve a Stripe customer.

        Args:
            customer_id: Stripe customer ID

        Returns:
            Dictionary representing the customer
        """
        ...

    def modify_customer(self, customer_id: str, **kwargs) -> Dict[str, Any]:
        """Modify a Stripe customer.

        Args:
            customer_id: Stripe customer ID
            **kwargs: Customer modification parameters

        Returns:
            Dictionary representing the updated customer
        """
        ...

    def delete_customer(self, customer_id: str) -> bool:
        """Delete a Stripe customer.

        Args:
            customer_id: Stripe customer ID

        Returns:
            True if deletion was successful
        """
        ...

    def create_meter_event(self, **kwargs) -> Dict[str, Any]:
        """Create a meter event.

        Args:
            **kwargs: Meter event creation parameters

        Returns:
            Dictionary representing the created meter event
        """
        ...


class SecretManagerProtocol(Protocol):
    """Protocol for secret management.

    Provides a secure interface for retrieving sensitive configuration
    such as API keys. Allows mocking for testing and alternative
    secret storage implementations.
    """

    def get_secret(self, key: str) -> Optional[str]:
        """Retrieve a secret by key.

        Args:
            key: Secret identifier/key name

        Returns:
            Secret value if found, None otherwise
        """
        ...


@runtime_checkable
class IdempotencyServiceProtocol(Protocol):
    """Protocol for idempotency key operations.

    Defines the interface for generating, validating, and tracking
    idempotency keys to ensure exactly-once semantics for meter events.
    """

    def generate_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        batch_id: Optional[str] = None
    ) -> str:
        """Generate a unique idempotency key.

        Args:
            tenant_id: Tenant identifier
            meter_event: Meter event name
            value: Event value/quantity
            batch_id: Optional batch identifier

        Returns:
            Unique idempotency key string
        """
        ...

    def is_registered(self, key: str) -> bool:
        """Check if a key is already registered.

        Args:
            key: Idempotency key to check

        Returns:
            True if key is registered and not expired
        """
        ...

    def register_key(self, key: str) -> None:
        """Register an idempotency key.

        Args:
            key: Idempotency key to register
        """
        ...

    def get_metrics(self) -> CollisionMetrics:
        """Get collision detection metrics.

        Returns:
            Current collision metrics
        """
        ...


class RetryServiceProtocol(Protocol):
    """Protocol for retry logic.

    Defines the interface for executing operations with automatic
    retry and exponential backoff for transient failures.
    """

    async def execute_with_retry(
        self,
        func: Callable[..., Awaitable[Any]],
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """Execute a function with retry logic.

        Args:
            func: Async function to execute
            operation_name: Descriptive name for logging
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function execution

        Raises:
            Exception: If all retry attempts fail
        """
        ...

    def is_transient_error(self, error: Exception) -> bool:
        """Determine if an error is transient.

        Args:
            error: Exception to classify

        Returns:
            True if error should be retried
        """
        ...


class ValidationServiceProtocol(Protocol):
    """Protocol for validation operations.

    Defines the interface for validating and sanitizing inputs
    to prevent injection attacks and ensure data integrity.
    """

    def validate_meter_event(self, meter_event: str, value: int) -> List[str]:
        """Validate meter event parameters.

        Args:
            meter_event: Meter event name to validate
            value: Event value to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        ...

    def sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """Sanitize metadata for Stripe API.

        Removes dangerous characters and validates types to prevent
        injection attacks. Blocks reserved keys.

        Args:
            metadata: Raw metadata dictionary

        Returns:
            Sanitized metadata with string values

        Raises:
            StripeMeterValidationError: If validation fails
        """
        ...

    def sanitize_idempotency_component(self, component: str) -> str:
        """Sanitize a component for idempotency key generation.

        Removes dangerous characters that could be used in injection
        attacks or cause key collisions.

        Args:
            component: Raw component string

        Returns:
            Sanitized component string safe for idempotency keys
        """
        ...


class MeterEventServiceProtocol(Protocol):
    """Protocol for meter event operations.

    Defines the interface for reporting meter events to Stripe,
    including both single events and batch processing.
    """

    async def report_usage(
        self,
        meter_event: str,
        value: int,
        tenant_id: str,
        metadata: Optional[Dict[str, str]] = None,
        stripe_customer_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> MeterEventResult:
        """Report a single meter event.

        Args:
            meter_event: Meter event name
            value: Event value/quantity
            tenant_id: Tenant identifier
            metadata: Optional metadata dictionary
            stripe_customer_id: Optional Stripe customer ID
            batch_id: Optional batch identifier

        Returns:
            MeterEventResult with submission status
        """
        ...


class BatchProcessorProtocol(Protocol):
    """Protocol for batch processing operations.

    Defines the interface for processing multiple meter events
    in a single batch for improved throughput.
    """

    async def process_batch(
        self,
        events: List[MeterEventData],
        tenant_id: str,
        stripe_customer_id: Optional[str] = None
    ) -> BatchResult:
        """Process a batch of meter events.

        Args:
            events: List of meter event data
            tenant_id: Tenant identifier
            stripe_customer_id: Optional Stripe customer ID

        Returns:
            BatchResult with aggregate statistics
        """
        ...

    def generate_batch_id(self, tenant_id: str) -> str:
        """Generate a unique batch ID.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Unique batch identifier string
        """
        ...


class CustomerServiceProtocol(Protocol):
    """Protocol for customer operations.

    Defines the interface for Stripe customer CRUD operations
    with database persistence.
    """

    async def create_customer(
        self,
        tenant_id: str,
        tenant_name: str,
        email: str,
        name: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> str:
        """Create a Stripe customer.

        Args:
            tenant_id: Tenant identifier
            tenant_name: Tenant name for metadata
            email: Customer email address
            name: Optional customer name
            created_by: Optional user identifier

        Returns:
            Stripe customer ID
        """
        ...

    async def get_customer_by_tenant(
        self,
        tenant_id: str
    ) -> Optional[CustomerData]:
        """Get customer by tenant ID.

        Args:
            tenant_id: Tenant identifier

        Returns:
            CustomerData if found, None otherwise
        """
        ...

    async def update_customer(
        self,
        stripe_customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> CustomerData:
        """Update a customer.

        Args:
            stripe_customer_id: Stripe customer ID
            email: Optional new email address
            name: Optional new name
            metadata: Optional metadata updates

        Returns:
            Updated customer data
        """
        ...

    async def delete_customer(
        self,
        stripe_customer_id: str
    ) -> bool:
        """Delete a customer.

        Args:
            stripe_customer_id: Stripe customer ID

        Returns:
            True if deletion was successful
        """
        ...
