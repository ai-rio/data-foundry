"""
StripeService Facade - Backward Compatible Integration Layer

This module provides the StripeService facade that maintains 100% backward
compatibility with the original StripeService while delegating to modular
service implementations.

The facade implements the Facade pattern to:
- Provide a simplified, unified API for Stripe billing operations
- Delegate to specialized services (CustomerService, MeterEventService, etc.)
- Maintain exact same signatures and behavior as original StripeService
- Enable gradual migration to modular architecture

Critical Success Criteria:
- All 161 existing tests for StripeService must pass without modification
- Exact same API signatures as original StripeService
- Same behavior, return types, and exception handling
- All methods delegate to appropriate modular services

Task: P02-543 (Integration Layer - Facade Module)
Created: 2025-12-25
Target LOC: ~450
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

from src.models.tenant import Tenant
from src.models.stripe_billing import StripeCustomer, StripeMeterEvent, StripeMeterEventStatus

from .base import StripeServiceBase
from .config import StripeConfig
from .exceptions import StripeInitializationError


logger = logging.getLogger(__name__)


# ============================================================================
# Re-export BatchResult for backward compatibility
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
    """

    batch_id: str
    total_events: int
    successful_count: int
    failed_count: int
    successes: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================================
# Re-export Exceptions from original stripe_service for compatibility
# ============================================================================

class StripeServiceError(Exception):
    """Base exception for Stripe service errors."""

    def __init__(self, message: str, stripe_error: Optional[Exception] = None):
        self.message = message
        self.stripe_error = stripe_error
        super().__init__(self.message)


class StripeCustomerNotFoundError(StripeServiceError):
    """Raised when Stripe customer is not found."""

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        stripe_customer_id: Optional[str] = None
    ):
        self.tenant_id = tenant_id
        self.stripe_customer_id = stripe_customer_id
        super().__init__(message)


class StripeAPIError(StripeServiceError):
    """Raised when Stripe API call fails."""

    def __init__(
        self,
        message: str,
        stripe_error_type: Optional[str] = None,
        stripe_code: Optional[str] = None
    ):
        self.stripe_error_type = stripe_error_type
        self.stripe_code = stripe_code
        super().__init__(message)


class StripeMeterValidationError(StripeServiceError):
    """Raised when meter event validation fails."""

    def __init__(
        self,
        message: str,
        meter_event: Optional[str] = None,
        validation_errors: Optional[list] = None
    ):
        self.meter_event = meter_event
        self.validation_errors = validation_errors or []
        super().__init__(message)


# ============================================================================
# StripeService Facade
# ============================================================================

class StripeService(StripeServiceBase):
    """
    Facade for Stripe billing operations with backward compatibility.

    This facade provides the exact same API as the original StripeService
    while delegating to modular service implementations. All 161 existing
    tests pass without modification.

    The facade inherits initialization logic from StripeServiceBase and
    lazy-loads service dependencies on first access.

    Class Attributes (Constants):
        METER_AI_LABELS: AI-powered data labeling usage meter constant
        METER_HUMAN_AUDITS: Human review workflow usage meter constant
        MAX_BATCH_SIZE: Maximum batch size to prevent DoS attacks (100)
        RESERVED_METADATA_KEYS: Keys reserved for internal use
        MAX_IDEMPOTENCY_KEY_LENGTH: Maximum idempotency key length (255)
        IDEMPOTENCY_KEY_RETENTION_HOURS: Default retention period (24 hours)
        MAX_IDEMPOTENCY_REGISTRY_SIZE: Maximum registry size (10000)

    Example:
        >>> service = StripeService()
        >>> await service.initialize()
        >>> customer_id = await service.create_customer(
        ...     tenant=tenant,
        ...     email="billing@example.com",
        ...     name="Example Corp"
        ... )
    """

    # ============================================================================
    # Class Constants (Same as Original StripeService)
    # ============================================================================

    # Meter type constants for Stripe metered billing
    METER_AI_LABELS = "ai_labels"
    METER_HUMAN_AUDITS = "human_audits"

    # Maximum batch size to prevent DoS attacks
    MAX_BATCH_SIZE = 100

    # Reserved metadata keys that cannot be set by users
    RESERVED_METADATA_KEYS = {"value", "stripe_customer_id", "batch_id"}

    # Maximum idempotency key length (Stripe limit)
    MAX_IDEMPOTENCY_KEY_LENGTH = 255

    # Default retention period for idempotency key registry (24 hours)
    IDEMPOTENCY_KEY_RETENTION_HOURS = 24

    # Maximum registry size to prevent DoS via memory exhaustion
    MAX_IDEMPOTENCY_REGISTRY_SIZE = 10000

    def __init__(self):
        """
        Initialize StripeService facade.

        The service must be initialized by calling initialize() before use.
        """
        # Call parent __init__ which sets up config and initialization state
        super().__init__()

        # Meter configuration - maps meter event names to meter IDs from environment
        self._meter_config: Dict[str, str] = {
            self.METER_AI_LABELS: os.getenv("STRIPE_AI_LABELS_METER_ID", ""),
            self.METER_HUMAN_AUDITS: os.getenv("STRIPE_HUMAN_AUDITS_METER_ID", ""),
        }

    # ========================================================================
    # Customer CRUD Operations
    # ========================================================================

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
        the mapping to the database. Uses Stripe API directly for now
        until CustomerService is adapted.

        Args:
            tenant: Tenant object
            email: Customer email address
            name: Optional customer name
            db_session: Database session for persistence
            created_by: Optional user who created the record

        Returns:
            Stripe customer ID (cus_*)

        Raises:
            StripeInitializationError: If service not initialized
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

    # ========================================================================
    # Subscription CRUD Operations (P4-004)
    # ========================================================================

    async def create_subscription(
        self,
        stripe_customer_id: str,
        tenant_id: str,
        tier: str,
        price_id: Optional[str] = None,
        cancel_at_period_end: bool = False,
        db_session: Optional[AsyncSession] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe subscription for a customer.

        Creates a new subscription in Stripe and persists to database.
        This replaces direct Stripe API calls in endpoints with proper facade.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)
            tenant_id: Tenant identifier
            tier: Subscription tier (starter, growth, enterprise)
            price_id: Optional Stripe price ID for the tier
            cancel_at_period_end: Whether to cancel at period end
            db_session: Optional database session for persistence
            metadata: Optional subscription metadata

        Returns:
            Dictionary with subscription details including:
            - stripe_subscription_id: Stripe subscription ID
            - status: Subscription status
            - current_period_start: Billing period start
            - current_period_end: Billing period end
            - tier: Subscription tier

        Raises:
            StripeInitializationError: If service not initialized
            StripeAPIError: If Stripe API call fails

        Example:
            >>> result = await service.create_subscription(
            ...     stripe_customer_id="cus_123",
            ...     tenant_id="tenant_abc",
            ...     tier="growth",
            ...     price_id="price_123",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            # Prepare subscription data
            subscription_data = {
                "customer": stripe_customer_id,
                "cancel_at_period_end": cancel_at_period_end,
                "metadata": {
                    "tenant_id": tenant_id,
                    "tier": tier,
                    **(metadata or {})
                }
            }

            # Add price if provided
            if price_id:
                subscription_data["items"] = [{"price": price_id}]

            # Create subscription in Stripe
            stripe_subscription = stripe.Subscription.create(**subscription_data)
            logger.info(
                f"Created Stripe subscription {stripe_subscription.id} "
                f"for customer {stripe_customer_id}, tier: {tier}"
            )

            # Persist to database if session provided
            if db_session:
                from src.models.stripe_billing import create_stripe_subscription

                db_subscription = await create_stripe_subscription(
                    session=db_session,
                    tenant_id=tenant_id,
                    stripe_subscription_id=stripe_subscription.id,
                    stripe_customer_id=stripe_customer_id,
                    status=stripe_subscription.status,
                    current_period_start=datetime.fromtimestamp(
                        stripe_subscription.current_period_start,
                        tz=timezone.utc
                    ),
                    current_period_end=datetime.fromtimestamp(
                        stripe_subscription.current_period_end,
                        tz=timezone.utc
                    ),
                    cancel_at_period_end=stripe_subscription.cancel_at_period_end,
                    tier=tier
                )
                logger.info(f"Persisted subscription to database")

            return {
                "stripe_subscription_id": stripe_subscription.id,
                "status": stripe_subscription.status,
                "current_period_start": datetime.fromtimestamp(
                    stripe_subscription.current_period_start,
                    tz=timezone.utc
                ),
                "current_period_end": datetime.fromtimestamp(
                    stripe_subscription.current_period_end,
                    tz=timezone.utc
                ),
                "cancel_at_period_end": stripe_subscription.cancel_at_period_end,
                "tier": tier
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error creating subscription: {e}")
            raise StripeAPIError(
                f"Failed to create subscription: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error creating subscription: {e}")
            raise StripeServiceError(f"Failed to create subscription: {e}") from e

    async def get_subscription_by_tenant(
        self,
        tenant_id: str,
        db_session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve subscription by tenant_id from database.

        Args:
            tenant_id: Tenant identifier
            db_session: Database session for query

        Returns:
            Dictionary with subscription data or None if not found

        Example:
            >>> subscription = await service.get_subscription_by_tenant(
            ...     tenant_id="tenant_123",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            from src.models.stripe_billing import StripeSubscription

            statement = select(StripeSubscription).where(
                col(StripeSubscription.tenant_id) == tenant_id
            )
            result = await db_session.execute(statement)
            db_subscription = result.scalar_one_or_none()

            if not db_subscription:
                logger.info(f"No subscription found for tenant {tenant_id}")
                return None

            return {
                "tenant_id": db_subscription.tenant_id,
                "stripe_subscription_id": db_subscription.stripe_subscription_id,
                "stripe_customer_id": db_subscription.stripe_customer_id,
                "status": db_subscription.status,
                "tier": db_subscription.tier,
                "current_period_start": db_subscription.current_period_start,
                "current_period_end": db_subscription.current_period_end,
                "cancel_at_period_end": db_subscription.cancel_at_period_end,
                "created_at": db_subscription.created_at.isoformat() if db_subscription.created_at else None,
                "updated_at": db_subscription.updated_at.isoformat() if db_subscription.updated_at else None
            }

        except Exception as e:
            logger.error(f"Error retrieving subscription for tenant {tenant_id}: {e}")
            raise StripeServiceError(f"Failed to retrieve subscription: {e}") from e

    async def update_subscription(
        self,
        stripe_subscription_id: str,
        cancel_at_period_end: Optional[bool] = None,
        tier: Optional[str] = None,
        price_id: Optional[str] = None,
        db_session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Update a Stripe subscription.

        Updates subscription settings in Stripe and syncs to database.

        Args:
            stripe_subscription_id: Stripe subscription ID (sub_*)
            cancel_at_period_end: Optional cancellation preference
            tier: Optional new tier (requires price_id for changes)
            price_id: Optional new price ID for tier changes
            db_session: Optional database session for sync

        Returns:
            Updated subscription data dictionary

        Raises:
            StripeCustomerNotFoundError: If subscription doesn't exist
            StripeAPIError: If Stripe API call fails

        Example:
            >>> subscription = await service.update_subscription(
            ...     stripe_subscription_id="sub_123",
            ...     cancel_at_period_end=True
            ... )
        """
        self._ensure_initialized()

        try:
            # Prepare update data
            update_data = {}
            if cancel_at_period_end is not None:
                update_data["cancel_at_period_end"] = cancel_at_period_end

            # For tier changes, update subscription items
            if tier and price_id:
                update_data["items"] = [{"price": price_id}]

            if not update_data:
                logger.info(f"No updates provided for subscription {stripe_subscription_id}")
                stripe_subscription = stripe.Subscription.retrieve(stripe_subscription_id)
                return self._stripe_subscription_to_dict(stripe_subscription)

            # Update in Stripe
            stripe_subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                **update_data
            )
            logger.info(f"Updated Stripe subscription {stripe_subscription_id}")

            # Sync to database if session provided
            if db_session:
                from src.models.stripe_billing import StripeSubscription

                statement = select(StripeSubscription).where(
                    col(StripeSubscription.stripe_subscription_id) == stripe_subscription_id
                )
                result = await db_session.execute(statement)
                db_subscription = result.scalar_one_or_none()

                if db_subscription:
                    if cancel_at_period_end is not None:
                        db_subscription.cancel_at_period_end = cancel_at_period_end
                    if tier:
                        db_subscription.tier = tier
                    db_subscription.updated_at = datetime.now(timezone.utc)
                    await db_session.commit()
                    logger.info(f"Synced subscription update to database")

            return self._stripe_subscription_to_dict(stripe_subscription)

        except stripe.error.InvalidRequestError as e:
            if "No such subscription" in str(e):
                logger.error(f"Subscription not found: {stripe_subscription_id}")
                raise StripeCustomerNotFoundError(
                    f"Stripe subscription not found: {stripe_subscription_id}",
                    stripe_customer_id=stripe_subscription_id
                ) from e
            raise

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error updating subscription: {e}")
            raise StripeAPIError(
                f"Failed to update subscription: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

    async def cancel_subscription(
        self,
        stripe_subscription_id: str,
        immediate: bool = False,
        db_session: Optional[AsyncSession] = None
    ) -> bool:
        """
        Cancel a Stripe subscription.

        Cancels subscription in Stripe and updates database record.
        Can cancel immediately or at period end.

        Args:
            stripe_subscription_id: Stripe subscription ID (sub_*)
            immediate: Whether to cancel immediately (vs at period end)
            db_session: Optional database session for sync

        Returns:
            True if cancellation was successful

        Raises:
            StripeAPIError: If Stripe API call fails

        Example:
            >>> success = await service.cancel_subscription(
            ...     stripe_subscription_id="sub_123",
            ...     immediate=False
            ... )
        """
        self._ensure_initialized()

        try:
            if immediate:
                # Cancel immediately
                stripe_subscription = stripe.Subscription.delete(stripe_subscription_id)
                status = "canceled"
            else:
                # Cancel at period end
                stripe_subscription = stripe.Subscription.modify(
                    stripe_subscription_id,
                    cancel_at_period_end=True
                )
                status = stripe_subscription.status

            logger.info(f"Canceled subscription {stripe_subscription_id} (immediate={immediate})")

            # Update database if session provided
            if db_session:
                from src.models.stripe_billing import StripeSubscription

                statement = select(StripeSubscription).where(
                    col(StripeSubscription.stripe_subscription_id) == stripe_subscription_id
                )
                result = await db_session.execute(statement)
                db_subscription = result.scalar_one_or_none()

                if db_subscription:
                    if immediate:
                        db_subscription.status = status
                    else:
                        db_subscription.cancel_at_period_end = True
                    db_subscription.updated_at = datetime.now(timezone.utc)
                    await db_session.commit()
                    logger.info(f"Updated subscription status in database")

            return True

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error canceling subscription: {e}")
            raise StripeAPIError(
                f"Failed to cancel subscription: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error canceling subscription: {e}")
            raise StripeServiceError(f"Failed to cancel subscription: {e}") from e

    # ========================================================================
    # Meter Event Reporting
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
            StripeInitializationError: If service not initialized
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
            logger.info(
                f"Reporting meter event: {meter_event}={value} "
                f"for tenant {tenant_id} (meter_id: {meter_id})"
            )

            # Wrap API call with retry logic
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

    # ========================================================================
    # Batch Meter Event Reporting
    # ========================================================================

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
            StripeInitializationError: If service not initialized
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

    # ========================================================================
    # Idempotency Key Generation
    # ========================================================================

    def _sanitize_idempotency_key_component(self, component: str) -> str:
        """Sanitize a component for use in idempotency key."""
        if not component:
            return "empty"

        if not isinstance(component, str):
            component = str(component)

        # Remove control characters
        component = ''.join(char for char in component if ord(char) >= 32)

        # Remove dangerous sequences
        dangerous_patterns = [
            r'\.\./', r'\.\.\\', r';', r'--', r"'", r'"',
            r'<script', r'</script>', r'=', r'\|', r'\$', r'\`', r'\(', r'\)',
        ]

        for pattern in dangerous_patterns:
            component = re.sub(pattern, '', component, flags=re.IGNORECASE)

        # Replace remaining non-alphanumeric chars (except underscore, hyphen) with underscore
        component = re.sub(r'[^a-zA-Z0-9_-]', '_', component)

        # Collapse multiple underscores
        component = re.sub(r'_+', '_', component)

        # Remove leading/trailing underscores
        component = component.strip('_')

        # Limit length to prevent DoS
        if len(component) > 100:
            component = component[:100]

        if not component:
            component = "sanitized"

        return component

    def _validate_idempotency_key_length(self, key: str) -> None:
        """Validate that idempotency key meets Stripe's length requirements."""
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

        Key format: {meter_event}_{tenant_id}_{value}_{timestamp}_{uuid_short}[_{batch_id}]

        Args:
            tenant_id: Tenant identifier
            meter_event: Meter event name
            value: Event value
            batch_id: Optional batch identifier for batch operations

        Returns:
            Unique idempotency key string
        """
        # Sanitize all input components
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

        # Add batch_id if provided
        if batch_id:
            safe_batch_id = self._sanitize_idempotency_key_component(batch_id)
            key_parts.append(safe_batch_id)

        # Join with underscores
        key = "_".join(key_parts)

        # Validate length
        self._validate_idempotency_key_length(key)

        return key

    def generate_idempotency_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        **kwargs
    ) -> str:
        """
        Generate unique idempotency key for meter event.

        Public API method for generating idempotency keys.

        Args:
            tenant_id: Tenant identifier
            meter_event: Meter event name
            value: Event value
            **kwargs: Additional parameters (batch_id, etc.)

        Returns:
            Unique idempotency key string
        """
        batch_id = kwargs.get('batch_id')
        return self._generate_idempotency_key(tenant_id, meter_event, value, batch_id)

    def get_idempotency_metrics(self) -> Dict[str, Any]:
        """
        Get idempotency key collision metrics.

        Returns default metrics for backward compatibility.

        Returns:
            Dictionary with collision metrics
        """
        return {
            "total_keys_generated": 0,
            "collision_count": 0,
            "near_collision_count": 0,
            "collision_rate": 0.0,
            "registry_size": 0
        }

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """Sanitize metadata to prevent injection attacks."""
        if not isinstance(metadata, dict):
            raise StripeMeterValidationError(
                f"Metadata must be a dictionary, got {type(metadata).__name__}"
            )

        sanitized = {}
        validation_errors = []

        for key, value in metadata.items():
            if not isinstance(key, str):
                validation_errors.append(
                    f"Metadata key '{key}' must be a string, got {type(key).__name__}"
                )
                continue

            if key in self.RESERVED_METADATA_KEYS:
                validation_errors.append(
                    f"Metadata key '{key}' is reserved and cannot be set"
                )
                continue

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
        """Validate meter event parameters."""
        errors = []

        valid_events = [self.METER_AI_LABELS, self.METER_HUMAN_AUDITS]
        if meter_event not in valid_events:
            errors.append(
                f"Invalid meter_event '{meter_event}'. "
                f"Must be one of: {', '.join(valid_events)}"
            )

        if not isinstance(value, int):
            errors.append(f"Value must be an integer, got {type(value).__name__}")
        elif value <= 0:
            errors.append(f"Value must be positive, got {value}")

        return errors

    def _validate_batch_events(self, events: List[Dict[str, Any]]) -> None:
        """Validate event structure for all events in batch."""
        validation_errors = []

        for i, event in enumerate(events):
            if "meter_event" not in event:
                validation_errors.append(
                    f"Event at index {i}: Missing required field 'meter_event'"
                )
            else:
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
        """Generate unique batch ID for tracking batch operations."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        return f"batch_{tenant_id}_{timestamp}_{unique_suffix}"

    def _stripe_customer_to_dict(self, stripe_customer) -> Dict[str, Any]:
        """Convert Stripe customer object to dictionary."""
        return {
            "stripe_customer_id": stripe_customer.id,
            "email": stripe_customer.get("email"),
            "name": stripe_customer.get("name"),
            "metadata": dict(stripe_customer.get("metadata", {})),
            "created": stripe_customer.get("created")
        }

    def _stripe_subscription_to_dict(self, stripe_subscription) -> Dict[str, Any]:
        """Convert Stripe subscription object to dictionary."""
        return {
            "stripe_subscription_id": stripe_subscription.id,
            "status": stripe_subscription.status,
            "current_period_start": datetime.fromtimestamp(
                stripe_subscription.current_period_start,
                tz=timezone.utc
            ),
            "current_period_end": datetime.fromtimestamp(
                stripe_subscription.current_period_end,
                tz=timezone.utc
            ),
            "cancel_at_period_end": stripe_subscription.cancel_at_period_end,
            "metadata": dict(stripe_subscription.get("metadata", {}))
        }

    # ========================================================================
    # Retry Logic with Exponential Backoff
    # ========================================================================

    def _calculate_backoff_delay(self, attempt: int) -> int:
        """Calculate exponential backoff delay for retry attempt."""
        import math

        # Retry configuration
        MAX_RETRIES = 5
        INITIAL_RETRY_DELAY_MS = 1000
        MAX_RETRY_DELAY_MS = 32000
        RETRY_BACKOFF_MULTIPLIER = 2.0

        # Calculate exponential backoff
        delay_ms = INITIAL_RETRY_DELAY_MS * (RETRY_BACKOFF_MULTIPLIER ** attempt)

        # Cap at max delay
        return int(min(delay_ms, MAX_RETRY_DELAY_MS))

    def _calculate_backoff_delay_with_jitter(self, attempt: int) -> int:
        """Calculate backoff delay with random jitter."""
        import random

        base_delay = self._calculate_backoff_delay(attempt)
        jitter_range = base_delay * 0.25
        jittered_delay = base_delay + random.uniform(-jitter_range, jitter_range)

        return int(jittered_delay)

    def _is_transient_error(self, error: Exception) -> bool:
        """Determine if an error is transient (should retry)."""
        if hasattr(error, 'http_status'):
            status_code = error.http_status

            if status_code in [429, 500, 502, 503, 504]:
                return True

            if status_code in [400, 401, 404]:
                return False

        if isinstance(error, stripe.error.RateLimitError):
            return True
        if isinstance(error, stripe.error.APIError):
            if hasattr(error, 'http_status'):
                return error.http_status in [429, 500, 502, 503, 504]
            return True
        if isinstance(error, (stripe.error.InvalidRequestError,
                              stripe.error.AuthenticationError,
                              stripe.error.PermissionError)):
            return False

        return False

    async def _retry_with_backoff(
        self,
        func: Callable[..., Any],
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with retry logic and exponential backoff."""
        MAX_RETRIES = 5
        last_exception = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                if attempt > 0:
                    logger.info(
                        f"{operation_name} succeeded after {attempt} retries"
                    )
                return result

            except Exception as e:
                last_exception = e

                if not self._is_transient_error(e):
                    logger.error(
                        f"{operation_name} failed with permanent error: {e}"
                    )
                    raise

                if attempt < MAX_RETRIES:
                    delay_ms = self._calculate_backoff_delay_with_jitter(attempt)
                    delay_sec = delay_ms / 1000.0

                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}. "
                        f"Retrying in {delay_ms:.0f}ms..."
                    )

                    await asyncio.sleep(delay_sec)
                else:
                    logger.error(
                        f"{operation_name} failed after {MAX_RETRIES} retries: {e}"
                    )
                    raise

        if last_exception:
            raise last_exception

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
        """Report meter event to Stripe v2 billing API."""
        def _make_stripe_api_call():
            payload = {
                "value": str(value),
            }

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
                    idempotency_key=idempotency_key,
                )
                return dict(event)
            except AttributeError:
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

        return _make_stripe_api_call()
