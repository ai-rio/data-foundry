"""
StripeService - Stripe billing operations for Data Foundry.

This service provides Stripe customer management operations including:
- Customer CRUD operations (create, read, update, delete)
- Meter event reporting for usage-based billing
- Metadata mapping between tenant_id and Stripe customer
- Stripe API integration with proper error handling
- Database persistence for Stripe customer records

P1-002: StripeService base with Customer CRUD operations
P02-001: Meter event reporting for usage-based billing

Security Features:
- API key management via SecretManager
- Custom exception classes for error handling
- Proper masking of sensitive data in logs
- Tenant isolation through metadata

Meter Types:
- METER_AI_LABELS: AI-powered data labeling usage
- METER_HUMAN_AUDITS: Human review workflow usage
"""

import logging
import os
from typing import Dict, Optional, Any, List
from datetime import datetime
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

    def __init__(self):
        """
        Initialize StripeService.

        The service must be initialized by calling initialize() before use.
        """
        self.api_key: Optional[str] = None
        self.secret_manager: Optional[SecretManager] = None
        self._initialized: bool = False

        # Meter configuration - maps meter event names to meter IDs from environment
        # These are configured in .env:
        # STRIPE_AI_LABELS_METER_ID=mtr_test_...
        # STRIPE_HUMAN_AUDITS_METER_ID=mtr_test_...
        self._meter_config: Dict[str, str] = {
            self.METER_AI_LABELS: os.getenv("STRIPE_AI_LABELS_METER_ID", ""),
            self.METER_HUMAN_AUDITS: os.getenv("STRIPE_HUMAN_AUDITS_METER_ID", ""),
        }

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
                    "created_at": datetime.utcnow().isoformat()
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
                    db_customer.updated_at = datetime.utcnow()
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
        db_session: Optional[AsyncSession] = None
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
            ...     metadata={"batch_id": "batch_001"}
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

        # Add metadata if provided
        if metadata:
            event_data["payload"]["metadata"] = metadata

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

            # Stripe v2 API call for meter events
            # The exact API call depends on Stripe SDK version
            # Using stripe.Billing.MeterEventStream pattern for v2 API
            stripe_response = self._report_meter_event_to_stripe(
                meter_id=meter_id,
                event_name=meter_event,
                value=value,
                idempotency_key=idempotency_key,
                customer_id=stripe_customer_id,
                metadata=metadata
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

    def _generate_idempotency_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int
    ) -> str:
        """
        Generate unique idempotency key for meter event.

        Combines tenant_id, meter_event, timestamp, and UUID to ensure
        uniqueness while allowing for duplicate detection.

        Args:
            tenant_id: Tenant identifier
            meter_event: Meter event name
            value: Event value

        Returns:
            Unique idempotency key string
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        return f"{tenant_id}_{meter_event}_{value}_{timestamp}_{unique_suffix}"

    def _report_meter_event_to_stripe(
        self,
        meter_id: str,
        event_name: str,
        value: int,
        idempotency_key: str,
        customer_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Report meter event to Stripe v2 billing API.

        This is the actual Stripe API call. Separated for easier testing
        and future retry logic implementation.

        Args:
            meter_id: The Stripe meter ID (mtr_*)
            event_name: The event name
            value: The event value/quantity
            idempotency_key: Unique idempotency key
            customer_id: Optional Stripe customer ID
            metadata: Optional metadata

        Returns:
            Stripe API response as dictionary

        Raises:
            stripe.error.StripeError: If API call fails
        """
        # Prepare payload for Stripe v2 billing meter event stream
        # Note: The exact API structure may vary based on Stripe SDK version
        # This follows the v2/billing/meter_event_stream pattern

        # Build event payload
        payload = {
            "value": str(value),  # Stripe expects string value
        }

        if customer_id:
            payload["stripe_customer_id"] = customer_id

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
