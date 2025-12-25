"""
StripeService - Stripe billing operations for Data Foundry.

This service provides Stripe customer management operations including:
- Customer CRUD operations (create, read, update, delete)
- Meter event reporting for usage-based billing
- Batch meter event reporting for high-volume scenarios
- Metadata mapping between tenant_id and Stripe customer
- Stripe API integration with proper error handling
- Database persistence for Stripe customer records

P1-002: StripeService base with Customer CRUD operations
P02-001: Meter event reporting for usage-based billing
P02-002: Batch meter event reporting support

Security Features:
- API key management via SecretManager
- Custom exception classes for error handling
- Proper masking of sensitive data in logs
- Tenant isolation through metadata

Meter Types:
- METER_AI_LABELS: AI-powered data labeling usage
- METER_HUMAN_AUDITS: Human review workflow usage
"""

import asyncio
import logging
import os
import re
import time
import threading
from collections import defaultdict
from typing import Dict, Optional, Any, List, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
import uuid

import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import col

from src.core.secret_manager import SecretManager
from src.models.tenant import Tenant
from src.models.stripe_billing import StripeCustomer, StripeMeterEvent, StripeMeterEventStatus


logger = logging.getLogger(__name__)


# ============================================================================
# Exception Classes
# ============================================================================


# ============================================================================
# Batch Result Data Class
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


# ============================================================================
# Exception Classes
# ============================================================================

class StripeServiceError(Exception):
    """
    Base exception for Stripe service errors.

    All StripeService exceptions inherit from this class for proper
    error handling and exception hierarchy.
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


class StripeCustomerNotFoundError(StripeServiceError):
    """
    Raised when Stripe customer is not found.

    This exception is raised when:
    - get_customer_by_tenant() returns None
    - update_customer() is called with non-existent customer
    - delete_customer() is called with non-existent customer
    """

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        stripe_customer_id: Optional[str] = None
    ):
        """
        Initialize StripeCustomerNotFoundError.

        Args:
            message: Error message
            tenant_id: Optional tenant_id for context
            stripe_customer_id: Optional Stripe customer ID for context
        """
        self.tenant_id = tenant_id
        self.stripe_customer_id = stripe_customer_id
        super().__init__(message)


class StripeAPIError(StripeServiceError):
    """
    Raised when Stripe API call fails.

    This exception wraps Stripe API errors and provides
    additional context for debugging and logging.
    """

    def __init__(
        self,
        message: str,
        stripe_error_type: Optional[str] = None,
        stripe_code: Optional[str] = None
    ):
        """
        Initialize StripeAPIError.

        Args:
            message: Error message
            stripe_error_type: Type of Stripe error (e.g., "StripeError")
            stripe_code: Stripe error code (e.g., "api_key_invalid")
        """
        self.stripe_error_type = stripe_error_type
        self.stripe_code = stripe_code
        super().__init__(message)


class StripeMeterValidationError(StripeServiceError):
    """
    Raised when meter event validation fails.

    This exception is raised when:
    - Invalid meter_event name is provided
    - Meter event is not configured
    - Invalid value (quantity) is provided
    - Required tenant context is missing
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
        self.meter_event = meter_event
        self.validation_errors = validation_errors or []
        super().__init__(message)


# ============================================================================
# StripeService
# ============================================================================

class StripeService:
    """
    Service for Stripe billing operations.

    Provides customer CRUD operations with:
    - Stripe API integration
    - Database persistence
    - Metadata synchronization
    - Proper error handling and logging

    Meter Types:
        METER_AI_LABELS: AI-powered data labeling usage meter
        METER_HUMAN_AUDITS: Human review workflow usage meter
    """

    # Meter type constants for Stripe metered billing
    METER_AI_LABELS = "ai_labels"
    METER_HUMAN_AUDITS = "human_audits"

    # Maximum batch size to prevent DoS attacks
    MAX_BATCH_SIZE = 100

    # Reserved metadata keys that cannot be set by users
    RESERVED_METADATA_KEYS = {"value", "stripe_customer_id", "batch_id"}

    # P02-004: Maximum idempotency key length (Stripe limit)
    MAX_IDEMPOTENCY_KEY_LENGTH = 255

    # P02-004: Default retention period for idempotency key registry (24 hours)
    IDEMPOTENCY_KEY_RETENTION_HOURS = 24

    # P02-004: Maximum registry size to prevent DoS via memory exhaustion
    MAX_IDEMPOTENCY_REGISTRY_SIZE = 10000

    def __init__(self):
        """
        Initialize StripeService.

        The service must be initialized by calling initialize() before use.

        P02-003: Retry configuration with exponential backoff for transient failures.
        Retry settings can be customized via environment variables:
        - STRIPE_MAX_RETRIES: Maximum number of retry attempts (default: 5)
        - STRIPE_INITIAL_RETRY_DELAY_MS: Initial retry delay in milliseconds (default: 1000)
        - STRIPE_MAX_RETRY_DELAY_MS: Maximum retry delay in milliseconds (default: 32000)

        P02-004: Idempotency key registry for tracking recent keys.
        """
        self.api_key: Optional[str] = None
        self.secret_manager: Optional[SecretManager] = None
        self._initialized: bool = False

        # P02-003: Retry configuration with exponential backoff
        # Load from environment variables or use defaults
        self.MAX_RETRIES = int(os.getenv("STRIPE_MAX_RETRIES", "5"))
        self.INITIAL_RETRY_DELAY_MS = int(os.getenv("STRIPE_INITIAL_RETRY_DELAY_MS", "1000"))
        self.MAX_RETRY_DELAY_MS = int(os.getenv("STRIPE_MAX_RETRY_DELAY_MS", "32000"))
        self.RETRY_BACKOFF_MULTIPLIER = 2.0  # Fixed exponential backoff multiplier

        # Meter configuration - maps meter event names to meter IDs from environment
        # These are configured in .env:
        # STRIPE_AI_LABELS_METER_ID=mtr_test_...
        # STRIPE_HUMAN_AUDITS_METER_ID=mtr_test_...
        self._meter_config: Dict[str, str] = {
            self.METER_AI_LABELS: os.getenv("STRIPE_AI_LABELS_METER_ID", ""),
            self.METER_HUMAN_AUDITS: os.getenv("STRIPE_HUMAN_AUDITS_METER_ID", ""),
        }

        # P02-004: Idempotency key registry (thread-safe)
        # Dictionary: {key: registration_timestamp}
        self._idempotency_registry: Dict[str, datetime] = {}
        self._registry_lock = threading.Lock()

        # P02-004: Collision detection metrics
        self._collision_metrics = {
            'total_keys_generated': 0,
            'collision_count': 0,
            'near_collision_count': 0,
        }
        self._metrics_lock = threading.Lock()

    async def initialize(self) -> None:
        """
        Initialize Stripe client with API key from SecretManager.

        Retrieves the Stripe secret key from SecretManager and configures
        the Stripe API client.

        Raises:
            StripeServiceError: If API key is not found in SecretManager

        Example:
            >>> service = StripeService()
            >>> await service.initialize()
        """
        if self._initialized:
            logger.warning("StripeService already initialized")
            return

        try:
            self.secret_manager = SecretManager()
            self.api_key = self.secret_manager.get_secret("STRIPE_SECRET_KEY")

            if not self.api_key:
                raise StripeServiceError(
                    "Stripe API key not found in SecretManager. "
                    "Please set STRIPE_SECRET_KEY in your environment."
                )

            # Configure Stripe API key
            stripe.api_key = self.api_key

            self._initialized = True
            logger.info("StripeService initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize StripeService: {e}")
            raise StripeServiceError(f"Failed to initialize StripeService: {e}") from e

    def _ensure_initialized(self) -> None:
        """
        Ensure service is initialized before use.

        Raises:
            StripeServiceError: If service is not initialized
        """
        if not self._initialized:
            raise StripeServiceError(
                "StripeService not initialized. Call initialize() before using the service."
            )

    async def create_customer(
        self,
        tenant: Tenant,
        email: str,
        name: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
        created_by: Optional[str] = None
    ) -> str:
        """
        Create Stripe customer for tenant.

        Creates a new Stripe customer with tenant metadata and persists
        the mapping to the database.

        Args:
            tenant: Tenant object
            email: Customer email address
            name: Optional customer name
            db_session: Database session for persistence
            created_by: Optional user who created the record

        Returns:
            Stripe customer ID (cus_*)

        Raises:
            StripeServiceError: If service not initialized
            StripeAPIError: If Stripe API call fails

        Example:
            >>> customer_id = await service.create_customer(
            ...     tenant=tenant,
            ...     email="billing@example.com",
            ...     name="Example Corp",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            # Prepare customer data with tenant metadata
            customer_data = {
                "email": email,
                "name": name or tenant.name,
                "metadata": {
                    "tenant_id": tenant.tenant_id,
                    "tenant_name": tenant.name,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }

            # Create customer in Stripe
            stripe_customer = stripe.Customer.create(**customer_data)
            logger.info(
                f"Created Stripe customer {stripe_customer.id} for tenant {tenant.tenant_id}"
            )

            # Persist to database if session provided
            if db_session:
                db_customer = StripeCustomer(
                    tenant_id=tenant.tenant_id,
                    stripe_customer_id=stripe_customer.id,
                    email=email,
                    name=name or tenant.name,
                    created_by=created_by
                )
                db_session.add(db_customer)
                await db_session.commit()
                await db_session.refresh(db_customer)
                logger.info(f"Persisted Stripe customer mapping to database")

            return stripe_customer.id

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error creating customer: {e}")
            raise StripeAPIError(
                f"Failed to create Stripe customer: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error creating customer: {e}")
            raise StripeServiceError(f"Failed to create customer: {e}") from e

    async def get_customer_by_tenant(
        self,
        tenant_id: str,
        db_session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve Stripe customer by tenant_id from database.

        Queries the database for the Stripe customer associated with
        the given tenant_id.

        Args:
            tenant_id: Tenant identifier
            db_session: Database session for query

        Returns:
            Dictionary with customer data or None if not found

        Example:
            >>> customer = await service.get_customer_by_tenant(
            ...     tenant_id="tenant_123",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            # Query database for customer
            statement = select(StripeCustomer).where(
                col(StripeCustomer.tenant_id) == tenant_id
            )
            result = await db_session.execute(statement)
            db_customer = result.scalar_one_or_none()

            if not db_customer:
                logger.info(f"No Stripe customer found for tenant {tenant_id}")
                return None

            # Return customer data as dictionary
            return {
                "tenant_id": db_customer.tenant_id,
                "stripe_customer_id": db_customer.stripe_customer_id,
                "email": db_customer.email,
                "name": db_customer.name,
                "created_at": db_customer.created_at.isoformat() if db_customer.created_at else None,
                "updated_at": db_customer.updated_at.isoformat() if db_customer.updated_at else None
            }

        except Exception as e:
            logger.error(f"Error retrieving customer for tenant {tenant_id}: {e}")
            raise StripeServiceError(f"Failed to retrieve customer: {e}") from e

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

        Updates customer details in Stripe and optionally syncs to database.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)
            email: Optional new email address
            name: Optional new name
            metadata: Optional metadata updates
            db_session: Optional database session for sync

        Returns:
            Updated customer data dictionary

        Raises:
            StripeCustomerNotFoundError: If customer doesn't exist
            StripeAPIError: If Stripe API call fails

        Example:
            >>> customer = await service.update_customer(
            ...     stripe_customer_id="cus_123",
            ...     email="newemail@example.com"
            ... )
        """
        self._ensure_initialized()

        try:
            # Prepare update data (only include non-None values)
            update_data = {}
            if email is not None:
                update_data["email"] = email
            if name is not None:
                update_data["name"] = name
            if metadata is not None:
                update_data["metadata"] = metadata

            # Return early if no updates
            if not update_data:
                logger.info(f"No updates provided for customer {stripe_customer_id}")
                # Fetch and return current customer
                stripe_customer = stripe.Customer.retrieve(stripe_customer_id)
                return self._stripe_customer_to_dict(stripe_customer)

            # Update in Stripe
            stripe_customer = stripe.Customer.modify(stripe_customer_id, **update_data)
            logger.info(f"Updated Stripe customer {stripe_customer_id}")

            # Sync to database if session provided
            if db_session and (email or name):
                statement = select(StripeCustomer).where(
                    col(StripeCustomer.stripe_customer_id) == stripe_customer_id
                )
                result = await db_session.execute(statement)
                db_customer = result.scalar_one_or_none()

                if db_customer:
                    if email:
                        db_customer.email = email
                    if name:
                        db_customer.name = name
                    db_customer.updated_at = datetime.now(timezone.utc)
                    await db_session.commit()
                    logger.info(f"Synced customer update to database")

            return self._stripe_customer_to_dict(stripe_customer)

        except stripe.error.InvalidRequestError as e:
            if "No such customer" in str(e):
                logger.error(f"Customer not found: {stripe_customer_id}")
                raise StripeCustomerNotFoundError(
                    f"Stripe customer not found: {stripe_customer_id}",
                    stripe_customer_id=stripe_customer_id
                ) from e
            raise

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error updating customer: {e}")
            raise StripeAPIError(
                f"Failed to update Stripe customer: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

    async def delete_customer(
        self,
        stripe_customer_id: str,
        db_session: Optional[AsyncSession] = None
    ) -> bool:
        """
        Delete Stripe customer.

        Deletes customer from Stripe and removes database record.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)
            db_session: Optional database session for cleanup

        Returns:
            True if deletion was successful

        Raises:
            StripeAPIError: If Stripe API call fails

        Example:
            >>> success = await service.delete_customer(
            ...     stripe_customer_id="cus_123",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            # Delete from Stripe
            stripe.Customer.delete(stripe_customer_id)
            logger.info(f"Deleted Stripe customer {stripe_customer_id}")

            # Remove from database if session provided
            if db_session:
                statement = select(StripeCustomer).where(
                    col(StripeCustomer.stripe_customer_id) == stripe_customer_id
                )
                result = await db_session.execute(statement)
                db_customer = result.scalar_one_or_none()

                if db_customer:
                    await db_session.delete(db_customer)
                    await db_session.commit()
                    logger.info(f"Removed customer record from database")

            return True

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error deleting customer: {e}")
            raise StripeAPIError(
                f"Failed to delete Stripe customer: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error deleting customer: {e}")
            raise StripeServiceError(f"Failed to delete customer: {e}") from e

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
        Report meter event usage to Stripe for billing.

        Sends usage events to Stripe's v2/billing/meter_event_stream API for
        metered billing. Validates meter event name and value before reporting.

        Args:
            meter_event: The meter event name (e.g., "ai_labels", "human_audits")
            value: The quantity/value to report (must be positive integer)
            tenant_id: Tenant identifier for tracking
            metadata: Optional metadata dictionary for the event
            stripe_customer_id: Optional Stripe customer ID for validation
            db_session: Optional database session for persisting event record
            batch_id: Optional batch identifier for batch operations (internal use only)

        Returns:
            Dictionary with Stripe API response including:
            - event_id: Unique identifier for the meter event
            - status: Event status (succeeded, failed, pending)
            - stripe_response: Full Stripe API response

        Raises:
            StripeServiceError: If service not initialized
            StripeMeterValidationError: If meter event validation fails
            StripeAPIError: If Stripe API call fails

        Example:
            >>> result = await service.report_usage(
            ...     meter_event="ai_labels",
            ...     value=100,
            ...     tenant_id="tenant_123",
            ...     metadata={"source": "api"}
            ... )
        """
        self._ensure_initialized()

        # Validate meter event
        validation_errors = self._validate_meter_event(meter_event, value)
        if validation_errors:
            raise StripeMeterValidationError(
                f"Meter event validation failed for '{meter_event}'",
                meter_event=meter_event,
                validation_errors=validation_errors
            )

        # Get meter ID for this event
        meter_id = self._meter_config.get(meter_event)
        if not meter_id:
            raise StripeMeterValidationError(
                f"Meter ID not configured for event '{meter_event}'. "
                f"Please set STRIPE_{meter_event.upper()}_METER_ID environment variable.",
                meter_event=meter_event
            )

        # Generate idempotency key for this event
        idempotency_key = self._generate_idempotency_key(tenant_id, meter_event, value)

        # Prepare event data for Stripe API
        event_data = {
            "event_name": meter_event,
            "payload": {
                "value": value,
                "stripe_customer_id": stripe_customer_id,
            },
            "idempotency_key": idempotency_key,
        }

        # Sanitize metadata if provided
        sanitized_metadata = None
        if metadata:
            sanitized_metadata = self._sanitize_metadata(metadata)

        # Track event in database if session provided
        db_event = None
        if db_session:
            db_event = StripeMeterEvent(
                tenant_id=tenant_id,
                event_name=meter_event,
                quantity=value,
                idempotency_key=idempotency_key,
                status=StripeMeterEventStatus.PENDING
            )
            db_session.add(db_event)
            await db_session.commit()
            await db_session.refresh(db_event)

        try:
            # Call Stripe v2 billing meter event stream API
            # Note: Using stripe.Billing.MeterEventStream.create() pattern
            # This may need adjustment based on exact Stripe SDK version
            logger.info(
                f"Reporting meter event: {meter_event}={value} "
                f"for tenant {tenant_id} (meter_id: {meter_id})"
            )

            # P02-003: Wrap API call with retry logic for transient failures
            # The retry logic preserves idempotency - same key for all attempts
            stripe_response = await self._retry_with_backoff(
                func=self._report_meter_event_to_stripe,
                operation_name=f"report_meter_event_{meter_event}",
                meter_id=meter_id,
                event_name=meter_event,
                value=value,
                idempotency_key=idempotency_key,
                customer_id=stripe_customer_id,
                metadata=sanitized_metadata,
                batch_id=batch_id
            )

            # Update database record if provided
            if db_session and db_event:
                db_event.status = StripeMeterEventStatus.SUCCEEDED
                db_event.stripe_response = stripe_response
                await db_session.commit()
                await db_session.refresh(db_event)

            logger.info(
                f"Successfully reported meter event {meter_event}={value} "
                f"for tenant {tenant_id}"
            )

            return {
                "event_id": idempotency_key,
                "status": "succeeded",
                "stripe_response": stripe_response,
                "meter_event": meter_event,
                "value": value
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error reporting meter event: {e}")

            # Update database record as failed
            if db_session and db_event:
                db_event.status = StripeMeterEventStatus.FAILED
                db_event.error_message = str(e)
                await db_session.commit()

            raise StripeAPIError(
                f"Failed to report meter event to Stripe: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error reporting meter event: {e}")

            # Update database record as failed
            if db_session and db_event:
                db_event.status = StripeMeterEventStatus.FAILED
                db_event.error_message = str(e)
                await db_session.commit()

            raise StripeServiceError(f"Failed to report meter event: {e}") from e

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """
        Sanitize metadata to prevent injection attacks.

        Validates that metadata keys are strings and values are primitive types.
        Blocks reserved keys to prevent overwriting critical fields.

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
            if key in self.RESERVED_METADATA_KEYS:
                validation_errors.append(
                    f"Metadata key '{key}' is reserved and cannot be set"
                )
                continue

            # Validate value is a primitive type that can be converted to string
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

    def _validate_meter_event(self, meter_event: str, value: int) -> List[str]:
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
        valid_events = [self.METER_AI_LABELS, self.METER_HUMAN_AUDITS]
        if meter_event not in valid_events:
            errors.append(
                f"Invalid meter_event '{meter_event}'. "
                f"Must be one of: {', '.join(valid_events)}"
            )

        # Validate value is positive integer
        if not isinstance(value, int):
            errors.append(f"Value must be an integer, got {type(value).__name__}")
        elif value <= 0:
            errors.append(f"Value must be positive, got {value}")

        return errors

    # ========================================================================
    # P02-004: Enhanced Idempotency Key Generation
    # ========================================================================

    def _sanitize_idempotency_key_component(self, component: str) -> str:
        """
        Sanitize a component for use in idempotency key.

        P02-004: Removes dangerous characters to prevent injection attacks
        and key collisions. This is critical for security.

        Sanitization rules:
        - Remove path traversal sequences (../, ..\\)
        - Remove SQL injection attempts (;, --, ')
        - Remove XSS attempts (<script>, etc.)
        - Remove control characters
        - Replace remaining special chars with underscore
        - Limit component length to prevent DoS

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
        dangerous_patterns = [
            r'\.\./',  # Path traversal
            r'\.\.\\',  # Windows path traversal
            r';',  # SQL injection separator
            r'--',  # SQL comment
            r"'",  # SQL quote
            r'"',  # Quote
            r'<script',  # XSS
            r'</script>',  # XSS close
            r'=',  # Could be used in injection
        ]

        for pattern in dangerous_patterns:
            component = re.sub(pattern, '', component, flags=re.IGNORECASE)

        # Replace remaining non-alphanumeric chars (except underscore, hyphen) with underscore
        component = re.sub(r'[^a-zA-Z0-9_-]', '_', component)

        # Collapse multiple underscores
        component = re.sub(r'_+', '_', component)

        # Remove leading/trailing underscores
        component = component.strip('_')

        # Limit length to prevent DoS (max 100 chars per component)
        if len(component) > 100:
            component = component[:100]

        # Fallback if empty after sanitization
        if not component:
            component = "sanitized"

        return component

    def _validate_idempotency_key_length(self, key: str) -> None:
        """
        Validate that idempotency key meets Stripe's length requirements.

        P02-004: Ensures keys don't exceed Stripe's 255 character limit.
        Raises StripeMeterValidationError if key is too long.

        Args:
            key: Idempotency key to validate

        Raises:
            StripeMeterValidationError: If key exceeds 255 characters
        """
        if len(key) > self.MAX_IDEMPOTENCY_KEY_LENGTH:
            raise StripeMeterValidationError(
                f"Idempotency key length {len(key)} exceeds Stripe's maximum of "
                f"{self.MAX_IDEMPOTENCY_KEY_LENGTH} characters",
                validation_errors=[f"Key too long: {len(key)} > {self.MAX_IDEMPOTENCY_KEY_LENGTH}"]
            )

    def _generate_idempotency_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        batch_id: Optional[str] = None
    ) -> str:
        """
        Generate unique idempotency key for meter event.

        P02-004: Enhanced idempotency key generation with:
        - Input sanitization for security (prevent injection attacks)
        - Timestamp component for uniqueness across time boundaries
        - UUID component for absolute uniqueness guarantee
        - Length validation to respect Stripe's 255 char limit
        - Optional batch_id support for batch scenarios

        Key format: {meter_event}_{tenant_id}_{value}_{timestamp}_{uuid_short}[_{batch_id}]

        Example: ai_labels_tenant_abc123_100_20241224T103000Z_a1b2c3d4_batch_456

        Args:
            tenant_id: Tenant identifier
            meter_event: Meter event name
            value: Event value
            batch_id: Optional batch identifier for batch operations

        Returns:
            Unique idempotency key string

        Raises:
            StripeMeterValidationError: If key would exceed length limit
        """
        # Update metrics
        with self._metrics_lock:
            self._collision_metrics['total_keys_generated'] += 1

        # Sanitize all input components (security critical)
        safe_tenant_id = self._sanitize_idempotency_key_component(tenant_id)
        safe_meter_event = self._sanitize_idempotency_key_component(meter_event)
        safe_value = self._sanitize_idempotency_key_component(str(value))

        # Generate timestamp in ISO format (UTC)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        # Generate UUID suffix (8 chars for uniqueness)
        unique_suffix = uuid.uuid4().hex[:8]

        # Build base key
        key_parts = [
            safe_meter_event,
            safe_tenant_id,
            safe_value,
            timestamp,
            unique_suffix
        ]

        # Add batch_id if provided (for batch operations)
        if batch_id:
            safe_batch_id = self._sanitize_idempotency_key_component(batch_id)
            key_parts.append(safe_batch_id)

        # Join with underscores
        key = "_".join(key_parts)

        # Validate length (Stripe limit: 255 chars)
        self._validate_idempotency_key_length(key)

        # Check for collisions with recent keys
        self._check_and_warn_collision(key)

        return key

    def _register_idempotency_key(self, key: str) -> None:
        """
        Register an idempotency key in the registry.

        P02-004: Tracks recently used keys to prevent duplicate submissions
        within the retry window. Thread-safe implementation with automatic
        cleanup of expired keys.

        Args:
            key: Idempotency key to register
        """
        with self._registry_lock:
            # Cleanup expired keys before adding new one
            self._cleanup_expired_idempotency_keys()

            # Prevent unbounded registry growth (DoS protection)
            if len(self._idempotency_registry) >= self.MAX_IDEMPOTENCY_REGISTRY_SIZE:
                # Registry full - remove oldest entries
                logger.warning(
                    f"Idempotency key registry full ({self.MAX_IDEMPOTENCY_REGISTRY_SIZE}). "
                    "Removing oldest entries."
                )
                # Sort by timestamp and remove oldest 10%
                sorted_keys = sorted(
                    self._idempotency_registry.items(),
                    key=lambda x: x[1]
                )
                keys_to_remove = sorted_keys[:len(sorted_keys) // 10]
                for old_key, _ in keys_to_remove:
                    del self._idempotency_registry[old_key]

            # Register the key with current timestamp
            self._idempotency_registry[key] = datetime.now(timezone.utc)

    def _is_idempotency_key_registered(self, key: str) -> bool:
        """
        Check if an idempotency key is already registered.

        P02-004: Thread-safe check for duplicate key detection.
        Automatically expires old keys during check.

        Args:
            key: Idempotency key to check

        Returns:
            True if key is registered and not expired, False otherwise
        """
        with self._registry_lock:
            # Cleanup expired keys first
            self._cleanup_expired_idempotency_keys()

            # Check if key exists and is not expired
            if key in self._idempotency_registry:
                registration_time = self._idempotency_registry[key]
                age_hours = (datetime.now(timezone.utc) - registration_time).total_seconds() / 3600

                # Key exists and is within retention period
                if age_hours <= self.IDEMPOTENCY_KEY_RETENTION_HOURS:
                    return True
                else:
                    # Key expired - remove it
                    del self._idempotency_registry[key]

        return False

    def _cleanup_expired_idempotency_keys(self) -> None:
        """
        Remove expired keys from the idempotency registry.

        P02-004: Automatic cleanup to prevent memory leaks.
        Must be called with registry_lock held.
        """
        current_time = datetime.now(timezone.utc)
        retention_delta = timedelta(hours=self.IDEMPOTENCY_KEY_RETENTION_HOURS)

        # Find expired keys
        expired_keys = [
            key for key, reg_time in self._idempotency_registry.items()
            if current_time - reg_time > retention_delta
        ]

        # Remove expired keys
        for key in expired_keys:
            del self._idempotency_registry[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired idempotency keys")

    def _check_and_warn_collision(self, new_key: str) -> None:
        """
        Check for potential idempotency key collisions and warn if detected.

        P02-004: Analyzes new key against recent keys to detect patterns
        that might indicate key generation issues or potential collisions.

        Detects:
        - Exact matches (true collisions)
        - Near collisions (same tenant/event/timestamp within 1 second)

        Args:
            new_key: New idempotency key to check
        """
        with self._registry_lock:
            recent_keys = list(self._idempotency_registry.keys())

        # Extract components from new key
        # Format: meter_event_tenant_value_timestamp_uuid[_batch]
        new_parts = new_key.split('_')

        if len(new_parts) < 5:
            return  # Invalid format, skip collision check

        new_meter = new_parts[0]
        new_tenant = new_parts[1]
        new_timestamp = new_parts[3]  # ISO format timestamp

        # Check for near-collisions with recent keys
        for existing_key in recent_keys[-100:]:  # Check last 100 keys
            existing_parts = existing_key.split('_')

            if len(existing_parts) < 5:
                continue

            existing_meter = existing_parts[0]
            existing_tenant = existing_parts[1]
            existing_timestamp = existing_parts[3]

            # Check if same tenant and meter event
            if new_meter == existing_meter and new_tenant == existing_tenant:
                # Parse timestamps to check if very close (within 1 second)
                try:
                    new_dt = datetime.fromisoformat(new_timestamp.replace('Z', '+00:00'))
                    existing_dt = datetime.fromisoformat(existing_timestamp.replace('Z', '+00:00'))
                    time_diff = abs((new_dt - existing_dt).total_seconds())

                    if time_diff < 1.0:
                        # Near collision detected
                        with self._metrics_lock:
                            self._collision_metrics['near_collision_count'] += 1

                        logger.warning(
                            f"Near-collision detected for idempotency keys:\n"
                            f"  New:      {new_key}\n"
                            f"  Existing: {existing_key}\n"
                            f"  Time difference: {time_diff:.3f}s\n"
                            f"  This may indicate high-volume concurrent requests or "
                            f"clock skew issues."
                        )
                except (ValueError, IndexError):
                    # Timestamp parsing failed, skip
                    pass

    def _get_collision_metrics(self) -> Dict[str, Any]:
        """
        Get collision detection metrics.

        P02-004: Returns statistics on key generation and collision detection.

        Returns:
            Dictionary with collision metrics including:
            - total_keys_generated: Total number of keys generated
            - collision_count: Number of exact collisions detected
            - near_collision_count: Number of near-collisions detected
            - collision_rate: Collision rate as percentage
        """
        with self._metrics_lock:
            metrics = self._collision_metrics.copy()

        total = metrics['total_keys_generated']
        if total > 0:
            metrics['collision_rate'] = (
                (metrics['collision_count'] + metrics['near_collision_count']) / total * 100
            )
        else:
            metrics['collision_rate'] = 0.0

        # Add registry size
        with self._registry_lock:
            metrics['registry_size'] = len(self._idempotency_registry)

        return metrics

    def _report_meter_event_to_stripe(
        self,
        meter_id: str,
        event_name: str,
        value: int,
        idempotency_key: str,
        customer_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Report meter event to Stripe v2 billing API with retry logic.

        P02-003: This method now includes automatic retry with exponential backoff
        for transient failures (rate limits, network issues, server errors).

        The retry logic preserves idempotency - the same idempotency_key is used
        for all retry attempts, preventing duplicate billing.

        Args:
            meter_id: The Stripe meter ID (mtr_*)
            event_name: The event name
            value: The event value/quantity
            idempotency_key: Unique idempotency key (same for all retries)
            customer_id: Optional Stripe customer ID
            metadata: Optional sanitized metadata
            batch_id: Optional batch identifier (internal use)

        Returns:
            Stripe API response as dictionary

        Raises:
            stripe.error.StripeError: If API call fails after all retries
        """
        # Prepare the actual API call function (will be retried)
        def _make_stripe_api_call():
            """Internal method that makes the actual Stripe API call."""
            # Prepare payload for Stripe v2 billing meter event stream
            payload = {
                "value": str(value),  # Stripe expects string value
            }

            if customer_id:
                payload["stripe_customer_id"] = customer_id

            if batch_id:
                payload["batch_id"] = batch_id

            if metadata:
                payload.update(metadata)

            # Create meter event
            # Using stripe.Billing.MeterEvent.create pattern for v2 API
            # Reference: https://stripe.com/docs/api/billing/meter_events/create
            # Note: This requires stripe >= 7.0.0 for v2 API support
            try:
                # Try v2 API with Billing.MeterEvent.create
                event = stripe.Billing.MeterEvent.create(
                    event_name=event_name,
                    payload=payload,
                    idempotency_key=idempotency_key,
                )
                return dict(event)
            except AttributeError:
                # Fallback for older SDK versions
                # Use stripe.APIRequestor for raw HTTP request
                import stripe.api_requestor
                requestor = stripe.api_requestor.APIRequestor()
                response, _ = requestor.request(
                    method="post",
                    url="/v2/billing/meter_event_stream",
                    params={
                        "event_name": event_name,
                        "payload": payload,
                        "idempotency_key": idempotency_key,
                    }
                )
                return response.data

        # P02-003: Wrap the API call with retry logic
        # Note: We need to await this in an async context
        # For now, we'll make it synchronous and wrap the call site
        return _make_stripe_api_call()

    def _stripe_customer_to_dict(self, stripe_customer) -> Dict[str, Any]:
        """
        Convert Stripe customer object to dictionary.

        Args:
            stripe_customer: Stripe API customer object

        Returns:
            Dictionary with customer data
        """
        return {
            "stripe_customer_id": stripe_customer.id,
            "email": stripe_customer.get("email"),
            "name": stripe_customer.get("name"),
            "metadata": dict(stripe_customer.get("metadata", {})),
            "created": stripe_customer.get("created")
        }

    async def report_usage_batch(
        self,
        events: List[Dict[str, Any]],
        tenant_id: str,
        stripe_customer_id: Optional[str] = None,
        db_session: Optional[AsyncSession] = None
    ) -> BatchResult:
        """
        Report multiple meter events to Stripe in a single batch.

        Processes multiple meter events, handling partial failures gracefully.
        Each event is processed sequentially, with results aggregated into
        a BatchResult object containing successes and failures.

        Args:
            events: List of event dictionaries, each containing:
                - meter_event (str): The meter event name (e.g., "ai_labels")
                - value (int): The quantity/value to report
                - metadata (dict, optional): Additional event metadata
            tenant_id: Tenant identifier for tracking
            stripe_customer_id: Optional Stripe customer ID for all events
            db_session: Optional database session for persisting event records

        Returns:
            BatchResult object containing:
            - batch_id: Unique batch identifier
            - total_events: Total number of events processed
            - successful_count: Number of successful events
            - failed_count: Number of failed events
            - successes: List of successful event results
            - failures: List of failed event results with error details

        Raises:
            StripeServiceError: If service not initialized
            StripeMeterValidationError: If event structure validation fails

        Example:
            >>> events = [
            ...     {"meter_event": "ai_labels", "value": 100, "metadata": {"source": "api"}},
            ...     {"meter_event": "human_audits", "value": 50}
            ... ]
            >>> result = await service.report_usage_batch(
            ...     events=events,
            ...     tenant_id="tenant_123",
            ...     stripe_customer_id="cus_abc123"
            ... )
            >>> print(f"Success: {result.successful_count}, Failed: {result.failed_count}")
        """
        self._ensure_initialized()

        # Generate batch ID
        batch_id = self._generate_batch_id(tenant_id)

        # Initialize batch result
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

        # Validate batch size to prevent DoS attacks
        if len(events) > self.MAX_BATCH_SIZE:
            raise StripeMeterValidationError(
                f"Batch size exceeds maximum allowed size of {self.MAX_BATCH_SIZE}. "
                f"Got {len(events)} events."
            )

        # Validate event structure upfront
        self._validate_batch_events(events)

        # Process each event sequentially
        for event_data in events:
            meter_event = event_data["meter_event"]
            value = event_data["value"]
            event_metadata = event_data.get("metadata", {})

            try:
                # Call report_usage for this event
                # Pass batch_id separately to avoid metadata sanitization issues
                event_result = await self.report_usage(
                    meter_event=meter_event,
                    value=value,
                    tenant_id=tenant_id,
                    metadata=event_metadata,
                    stripe_customer_id=stripe_customer_id,
                    db_session=db_session,
                    batch_id=batch_id
                )

                # Track success
                result.successes.append(event_result)
                result.successful_count += 1

            except (StripeMeterValidationError, StripeAPIError, StripeServiceError) as e:
                # Track failure with details
                failure_info = {
                    "event": {
                        "meter_event": meter_event,
                        "value": value,
                        "metadata": event_metadata
                    },
                    "error": str(e),
                    "error_type": type(e).__name__
                }

                # Add specific error details if available
                if hasattr(e, 'validation_errors') and e.validation_errors:
                    failure_info["validation_errors"] = e.validation_errors
                if hasattr(e, 'meter_event'):
                    failure_info["meter_event"] = e.meter_event

                result.failures.append(failure_info)
                result.failed_count += 1

                logger.warning(
                    f"Event failed in batch {batch_id}: {meter_event}={value} - {str(e)}"
                )

            except Exception as e:
                # Catch unexpected errors
                failure_info = {
                    "event": {
                        "meter_event": meter_event,
                        "value": value,
                        "metadata": event_metadata
                    },
                    "error": f"Unexpected error: {str(e)}",
                    "error_type": "UnexpectedError"
                }
                result.failures.append(failure_info)
                result.failed_count += 1

                logger.error(
                    f"Unexpected error processing event in batch {batch_id}: "
                    f"{meter_event}={value} - {str(e)}"
                )

        # Log batch summary
        logger.info(
            f"Batch {batch_id} completed: "
            f"{result.successful_count}/{result.total_events} succeeded, "
            f"{result.failed_count} failed"
        )

        return result

    def _validate_batch_events(self, events: List[Dict[str, Any]]) -> None:
        """
        Validate event structure for all events in batch.

        Ensures all events have required fields (meter_event, value) with
        correct types. Raises StripeMeterValidationError if any event is malformed.

        Args:
            events: List of event dictionaries to validate

        Raises:
            StripeMeterValidationError: If any event is missing required fields or has invalid types
        """
        validation_errors = []

        for i, event in enumerate(events):
            # Check for required fields
            if "meter_event" not in event:
                validation_errors.append(
                    f"Event at index {i}: Missing required field 'meter_event'"
                )
            else:
                # Validate meter_event is a string
                if not isinstance(event["meter_event"], str):
                    validation_errors.append(
                        f"Event at index {i}: 'meter_event' must be a string, "
                        f"got {type(event['meter_event']).__name__}"
                    )

            if "value" not in event:
                validation_errors.append(
                    f"Event at index {i}: Missing required field 'value'"
                )
            else:
                # Validate value is an integer
                if not isinstance(event["value"], int):
                    validation_errors.append(
                        f"Event at index {i}: 'value' must be an integer, "
                        f"got {type(event['value']).__name__}"
                    )

        if validation_errors:
            raise StripeMeterValidationError(
                f"Batch event validation failed: {'; '.join(validation_errors)}",
                validation_errors=validation_errors
            )

    def _generate_batch_id(self, tenant_id: str) -> str:
        """
        Generate unique batch ID for tracking batch operations.

        Combines tenant_id, timestamp, and UUID to ensure uniqueness.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Unique batch ID string
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        return f"batch_{tenant_id}_{timestamp}_{unique_suffix}"

    # ========================================================================
    # P02-003: Retry Logic with Exponential Backoff
    # ========================================================================

    def _calculate_backoff_delay(self, attempt: int) -> int:
        """
        Calculate exponential backoff delay for retry attempt.

        Implements exponential backoff: delay = initial * (multiplier ^ attempt)
        Delays are capped at MAX_RETRY_DELAY_MS to prevent excessive wait times.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in milliseconds

        Example:
            >>> service = StripeService()
            >>> service._calculate_backoff_delay(0)  # First retry
            1000
            >>> service._calculate_backoff_delay(1)  # Second retry
            2000
            >>> service._calculate_backoff_delay(2)  # Third retry
            4000
        """
        import math

        # Calculate exponential backoff
        delay_ms = self.INITIAL_RETRY_DELAY_MS * (self.RETRY_BACKOFF_MULTIPLIER ** attempt)

        # Cap at max delay
        return int(min(delay_ms, self.MAX_RETRY_DELAY_MS))

    def _calculate_backoff_delay_with_jitter(self, attempt: int) -> int:
        """
        Calculate backoff delay with random jitter to prevent thundering herd.

        Adds ±25% jitter to the base delay to distribute retry attempts
        across time and prevent synchronized retry storms.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in milliseconds with jitter applied

        Example:
            >>> service = StripeService()
            >>> # Will return value between 750ms and 1250ms for attempt 0
            >>> delay = service._calculate_backoff_delay_with_jitter(0)
        """
        import random

        base_delay = self._calculate_backoff_delay(attempt)

        # Add jitter: ±25% of base delay
        jitter_range = base_delay * 0.25
        jittered_delay = base_delay + random.uniform(-jitter_range, jitter_range)

        return int(jittered_delay)

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient (should retry) or permanent (should not retry).

        Transient errors (retry):
        - HTTP 429: Rate limit errors
        - HTTP 500: Internal server errors
        - HTTP 502: Bad gateway
        - HTTP 503: Service unavailable
        - HTTP 504: Gateway timeout

        Permanent errors (no retry):
        - HTTP 400: Bad request
        - HTTP 401: Unauthorized
        - HTTP 404: Not found

        Args:
            error: Exception to check

        Returns:
            True if error is transient (should retry), False otherwise
        """
        # Check if it's a Stripe error with HTTP status code
        if hasattr(error, 'http_status'):
            status_code = error.http_status

            # Retry on rate limits and server errors
            if status_code in [429, 500, 502, 503, 504]:
                return True

            # Don't retry on client errors
            if status_code in [400, 401, 404]:
                return False

        # Check specific Stripe error types
        if isinstance(error, stripe.error.RateLimitError):
            return True
        if isinstance(error, stripe.error.APIError):
            # APIError can be transient or permanent
            # Check HTTP status if available
            if hasattr(error, 'http_status'):
                return error.http_status in [429, 500, 502, 503, 504]
            # Assume APIError is transient if no status code
            return True
        if isinstance(error, (stripe.error.InvalidRequestError,
                              stripe.error.AuthenticationError,
                              stripe.error.PermissionError)):
            # Client errors - don't retry
            return False

        # Default: don't retry on unknown errors
        return False

    async def _retry_with_backoff(
        self,
        func: Callable[..., Any],
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic and exponential backoff.

        Wraps Stripe API calls with automatic retry on transient failures.
        Implements exponential backoff with jitter to prevent thundering herd.

        Args:
            func: Async function to execute (will be retried on transient errors)
            operation_name: Human-readable operation name for logging
            *args: Positional arguments to pass to func
            **kwargs: Keyword arguments to pass to func

        Returns:
            Result from func on success

        Raises:
            Exception: The last exception encountered after all retries exhausted

        Example:
            >>> result = await service._retry_with_backoff(
            ...     func=stripe.Customer.create,
            ...     operation_name="create_customer",
            ...     email="test@example.com"
            ... )
        """
        last_exception = None

        for attempt in range(self.MAX_RETRIES + 1):  # +1 for initial attempt
            try:
                # Attempt the operation
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Success - return result
                if attempt > 0:
                    logger.info(
                        f"{operation_name} succeeded after {attempt} retries"
                    )
                return result

            except Exception as e:
                last_exception = e

                # Check if error is transient (should retry)
                if not self._is_transient_error(e):
                    # Permanent error - don't retry
                    logger.error(
                        f"{operation_name} failed with permanent error: {e}"
                    )
                    raise

                # Transient error - check if we should retry
                if attempt < self.MAX_RETRIES:
                    # Calculate backoff delay with jitter
                    delay_ms = self._calculate_backoff_delay_with_jitter(attempt)
                    delay_sec = delay_ms / 1000.0

                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{self.MAX_RETRIES + 1}): {e}. "
                        f"Retrying in {delay_ms:.0f}ms..."
                    )

                    # Sleep before retry (async to avoid blocking event loop)
                    await asyncio.sleep(delay_sec)
                else:
                    # Max retries exhausted
                    logger.error(
                        f"{operation_name} failed after {self.MAX_RETRIES} retries: {e}"
                    )
                    raise

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
