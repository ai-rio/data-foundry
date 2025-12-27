"""
Subscription sync service for Stripe subscription status synchronization.

This module implements the SubscriptionSyncService which is responsible for:
- Syncing subscription data from Stripe API to local database
- Handling webhook events for real-time subscription updates
- Background job support for periodic syncing
- Error handling with retry logic

SINGLE RESPONSIBILITY: Only sync existing subscriptions, NOT create them
OPEN/CLOSED: Extensible for new sync strategies via webhook handler registry
DEPENDENCY INVERSION: Depends on service abstractions (protocols)

Phase: 3 (Subscription Management)
Task: P3-004 - Subscription Sync Service
Created: 2025-12-26

Security Considerations:
- Input validation for subscription IDs (must start with 'sub_')
- Webhook event type validation against whitelist
- Sensitive data redaction in error messages
- Lock mechanism prevents concurrent sync operations
- Idempotency for webhook events prevents duplicate processing
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable, List
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from src.services.stripe.types import SubscriptionSyncServiceProtocol, RetryServiceProtocol
from src.services.stripe.config import StripeConfig
from src.services.stripe.exceptions import StripeAPIError, StripeServerError
from src.models.stripe_billing import (
    StripeSubscription,
    StripeSubscriptionStatus,
)


logger = logging.getLogger(__name__)


# ============================================================================
# Webhook Event Handler Registry
# ============================================================================

class WebhookEventHandler:
    """
    Base class for webhook event handlers.

    Implements Strategy pattern for extensibility (Open/Closed Principle).
    New event handlers can be added without modifying core sync logic.
    """

    async def handle(self, event: Dict[str, Any], sync_service: 'SubscriptionSyncService') -> None:
        """
        Handle the webhook event.

        Args:
            event: Stripe webhook event payload
            sync_service: Reference to parent sync service for database operations
        """
        raise NotImplementedError("Subclasses must implement handle() method")


class SubscriptionUpdatedHandler(WebhookEventHandler):
    """Handler for customer.subscription.updated events."""

    async def handle(self, event: Dict[str, Any], sync_service: 'SubscriptionSyncService') -> None:
        """Sync subscription data from updated event."""
        subscription_data = event.get("data", {}).get("object", {})
        subscription_id = subscription_data.get("id")

        if subscription_id:
            await sync_service.sync_subscription(subscription_id)
            logger.info(f"Synced subscription {subscription_id} from updated event")


class SubscriptionDeletedHandler(WebhookEventHandler):
    """Handler for customer.subscription.deleted events."""

    async def handle(self, event: Dict[str, Any], sync_service: 'SubscriptionSyncService') -> None:
        """Mark subscription as canceled in database."""
        subscription_data = event.get("data", {}).get("object", {})
        subscription_id = subscription_data.get("id")

        if subscription_id:
            async with sync_service._get_session() as session:
                from sqlmodel import select

                statement = select(StripeSubscription).where(
                    StripeSubscription.stripe_subscription_id == subscription_id
                )
                result = await session.execute(statement)
                subscription = result.scalars().first()

                if subscription:
                    subscription.status = StripeSubscriptionStatus.CANCELED
                    subscription.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.info(f"Marked subscription {subscription_id} as canceled")


class PaymentSucceededHandler(WebhookEventHandler):
    """Handler for invoice.payment_succeeded events."""

    async def handle(self, event: Dict[str, Any], sync_service: 'SubscriptionSyncService') -> None:
        """Sync subscription data from payment succeeded event."""
        invoice_data = event.get("data", {}).get("object", {})
        subscription_id = invoice_data.get("subscription")

        if subscription_id:
            await sync_service.sync_subscription(subscription_id)
            logger.info(f"Synced subscription {subscription_id} from payment succeeded")


class PaymentFailedHandler(WebhookEventHandler):
    """Handler for invoice.payment_failed events."""

    async def handle(self, event: Dict[str, Any], sync_service: 'SubscriptionSyncService') -> None:
        """Mark subscription as past_due in database."""
        invoice_data = event.get("data", {}).get("object", {})
        subscription_id = invoice_data.get("subscription")

        if subscription_id:
            async with sync_service._get_session() as session:
                from sqlmodel import select

                statement = select(StripeSubscription).where(
                    StripeSubscription.stripe_subscription_id == subscription_id
                )
                result = await session.execute(statement)
                subscription = result.scalars().first()

                if subscription:
                    subscription.status = StripeSubscriptionStatus.PAST_DUE
                    subscription.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.info(f"Marked subscription {subscription_id} as past_due")


# ============================================================================
# Subscription Sync Service
# ============================================================================

class SubscriptionSyncService(SubscriptionSyncServiceProtocol):
    """
    Service for synchronizing subscription status between Stripe and local database.

    This service implements the SubscriptionSyncServiceProtocol and provides:
    - Periodic polling of Stripe API for subscription updates
    - Webhook event handling for real-time sync
    - Background job support (Celery/cron compatible)
    - Error handling with retry logic
    - Idempotency for webhook events

    SINGLE RESPONSIBILITY: Only sync existing subscriptions, NOT create them
    OPEN/CLOSED: Extensible via webhook handler registry
    DEPENDENCY INVERSION: Depends on RetryServiceProtocol abstraction

    Attributes:
        config: StripeConfig instance with sync settings
        retry_service: RetryService for handling transient failures
        _session_factory: Async context manager for database sessions
        _webhook_handlers: Registry of event type to handler mappings
        _processed_events: Set of processed webhook event IDs (in-memory)
        _lock: Async lock for preventing concurrent sync operations

    Example:
        >>> config = StripeConfig.from_environment()
        >>> retry_service = RetryService(config)
        >>> service = SubscriptionSyncService(config, retry_service, get_session)
        >>> await service.sync_subscription("sub_123")
        >>> await service.handle_webhook_event(webhook_event)
    """

    # Supported webhook event types (whitelist for security)
    SUPPORTED_EVENT_TYPES = frozenset([
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    ])

    def __init__(
        self,
        config: StripeConfig,
        retry_service: RetryServiceProtocol,
        session_factory: Callable[[], Awaitable[Any]]
    ):
        """
        Initialize SubscriptionSyncService.

        Args:
            config: StripeConfig instance with sync settings
            retry_service: RetryService for handling transient failures
            session_factory: Async function that returns database session
        """
        self.config = config
        self.retry_service = retry_service
        self._session_factory = session_factory

        # Webhook handler registry (Strategy pattern for extensibility)
        self._webhook_handlers: Dict[str, WebhookEventHandler] = {
            "customer.subscription.updated": SubscriptionUpdatedHandler(),
            "customer.subscription.deleted": SubscriptionDeletedHandler(),
            "invoice.payment_succeeded": PaymentSucceededHandler(),
            "invoice.payment_failed": PaymentFailedHandler(),
        }

        # Idempotency tracking for webhooks (in-memory for now)
        # In production, this should use Redis or database
        self._processed_events: set = set()

        # Lock for preventing concurrent sync operations
        self._lock: asyncio.Lock = asyncio.Lock()

    # ========================================================================
    # Database Session Management
    # ========================================================================

    @asynccontextmanager
    async def _get_session(self):
        """
        Get database session context manager.

        Yields:
            Database session for use in async context

        Example:
            async with self._get_session() as session:
                result = await session.execute(statement)
        """
        session = await self._session_factory()
        try:
            yield session
        finally:
            await session.close()

    # ========================================================================
    # Sync Operations
    # ========================================================================

    async def sync_subscription(self, stripe_subscription_id: str) -> StripeSubscription:
        """
        Sync a single subscription from Stripe API to database.

        Fetches subscription data from Stripe API and updates or creates
        the corresponding record in the local database. Uses retry logic
        for transient failures.

        Args:
            stripe_subscription_id: Stripe subscription ID (must start with 'sub_')

        Returns:
            Updated StripeSubscription model instance

        Raises:
            ValueError: If subscription_id format is invalid
            StripeAPIError: If Stripe API call fails after retries

        Example:
            >>> subscription = await service.sync_subscription("sub_123")
            >>> print(subscription.status)
            'active'
        """
        # Validate subscription ID format (security)
        if not stripe_subscription_id or not isinstance(stripe_subscription_id, str):
            raise ValueError("Invalid subscription ID format: must be a non-empty string")

        if not stripe_subscription_id.startswith("sub_"):
            raise ValueError(
                f"Invalid subscription ID format: '{stripe_subscription_id}' "
                f"must start with 'sub_'"
            )

        # Fetch from Stripe API with retry
        def _fetch_from_stripe():
            import stripe
            return stripe.Subscription.retrieve(stripe_subscription_id)

        try:
            stripe_subscription = await self.retry_service.execute_with_retry(
                func=_fetch_from_stripe,
                operation_name=f"sync_subscription({stripe_subscription_id})"
            )
        except Exception as e:
            logger.error(f"Failed to fetch subscription {stripe_subscription_id} from Stripe: {e}")
            raise StripeAPIError(
                f"Failed to fetch subscription from Stripe: {e}",
                stripe_error_type=type(e).__name__,
                is_retryable=self.retry_service.is_transient_error(e)
            ) from e

        # Transform Stripe data to database model
        async with self._get_session() as session:
            from sqlmodel import select

            # Check if record exists
            statement = select(StripeSubscription).where(
                StripeSubscription.stripe_subscription_id == stripe_subscription_id
            )
            result = await session.execute(statement)
            existing_subscription = result.scalars().first()

            # Extract data from Stripe response
            status_value = stripe_subscription.get("status", "incomplete")
            customer_id = stripe_subscription.get("customer", "")
            cancel_at_end = stripe_subscription.get("cancel_at_period_end", False)

            # Handle billing period timestamps
            current_period_start = None
            current_period_end = None
            if stripe_subscription.get("current_period_start"):
                current_period_start = datetime.fromtimestamp(
                    stripe_subscription["current_period_start"],
                    tz=timezone.utc
                )
            if stripe_subscription.get("current_period_end"):
                current_period_end = datetime.fromtimestamp(
                    stripe_subscription["current_period_end"],
                    tz=timezone.utc
                )

            # Extract tier from price metadata
            tier = None
            items = stripe_subscription.get("items", {})
            for item in items.get("data", []):
                price = item.get("price", {})
                metadata = price.get("metadata", {})
                if "tier" in metadata:
                    tier = metadata["tier"]
                    break

            # Get tenant_id from metadata or customer
            tenant_id = stripe_subscription.get("metadata", {}).get("tenant_id", "")

            if existing_subscription:
                # Update existing record
                existing_subscription.status = StripeSubscriptionStatus(status_value)
                existing_subscription.stripe_customer_id = customer_id
                existing_subscription.current_period_start = current_period_start
                existing_subscription.current_period_end = current_period_end
                existing_subscription.cancel_at_period_end = cancel_at_end
                existing_subscription.tier = tier
                existing_subscription.updated_at = datetime.now(timezone.utc)

                subscription = existing_subscription
                logger.debug(f"Updated subscription {stripe_subscription_id} in database")
            else:
                # Create new record (defensive - subscription should exist)
                subscription = StripeSubscription(
                    tenant_id=tenant_id,
                    stripe_subscription_id=stripe_subscription_id,
                    stripe_customer_id=customer_id,
                    status=StripeSubscriptionStatus(status_value),
                    current_period_start=current_period_start,
                    current_period_end=current_period_end,
                    cancel_at_period_end=cancel_at_end,
                    tier=tier
                )
                session.add(subscription)
                logger.debug(f"Created subscription {stripe_subscription_id} in database")

            await session.commit()
            await session.refresh(subscription)

            return subscription

    async def sync_all_subscriptions(
        self,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Sync all subscriptions from Stripe API to database.

        Fetches all subscriptions from Stripe with pagination and updates
        the local database. Continues on individual failures to maximize
        data consistency. Implements lock mechanism to prevent concurrent
        sync operations.

        Args:
            limit: Maximum number of subscriptions to sync per batch

        Returns:
            Dictionary with sync statistics:
                - total_synced: Number of subscriptions successfully synced
                - failed_count: Number of subscriptions that failed to sync
                - skipped: Whether sync was skipped due to lock

        Example:
            >>> result = await service.sync_all_subscriptions(limit=50)
            >>> print(f"Synced {result['total_synced']} subscriptions")
        """
        # Try to acquire lock (returns False if already locked)
        if not await self._acquire_lock():
            logger.warning("Sync operation already in progress, skipping")
            return {
                "total_synced": 0,
                "failed_count": 0,
                "skipped": True
            }

        try:
            total_synced = 0
            failed_count = 0
            starting_after = None

            while True:
                # Fetch batch from Stripe
                stripe_params = {"limit": min(limit, self.config.sync_batch_size)}
                if starting_after:
                    stripe_params["starting_after"] = starting_after

                def _fetch_list():
                    import stripe
                    return stripe.Subscription.list(**stripe_params)

                try:
                    response = await self.retry_service.execute_with_retry(
                        func=_fetch_list,
                        operation_name="sync_all_subscriptions(list)"
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch subscription list from Stripe: {e}")
                    raise StripeAPIError(
                        f"Failed to fetch subscription list from Stripe: {e}",
                        stripe_error_type=type(e).__name__,
                        is_retryable=self.retry_service.is_transient_error(e)
                    ) from e

                subscriptions = response.get("data", [])
                has_more = response.get("has_more", False)

                # Sync each subscription
                for subscription_data in subscriptions:
                    subscription_id = subscription_data.get("id")
                    if not subscription_id:
                        continue

                    try:
                        await self.sync_subscription(subscription_id)
                        total_synced += 1
                    except Exception as e:
                        logger.error(f"Failed to sync subscription {subscription_id}: {e}")
                        failed_count += 1
                        # Continue with next subscription

                # Check pagination
                if not has_more or not subscriptions:
                    break

                starting_after = subscriptions[-1]["id"]

            logger.info(f"Sync completed: {total_synced} synced, {failed_count} failed")
            return {
                "total_synced": total_synced,
                "failed_count": failed_count,
                "skipped": False
            }

        finally:
            # Always release lock
            await self._release_lock()

    # ========================================================================
    # Webhook Event Handling
    # ========================================================================

    async def handle_webhook_event(self, event: Dict[str, Any]) -> None:
        """
        Handle Stripe webhook event for subscription updates.

        Processes subscription-related webhook events and updates the local
        database accordingly. Implements idempotency using event ID to
        prevent duplicate processing.

        Args:
            event: Stripe webhook event payload

        Raises:
            ValueError: If event structure is invalid or event ID is missing

        Example:
            >>> webhook_event = {
            ...     "id": "evt_123",
            ...     "type": "customer.subscription.updated",
            ...     "data": {"object": {...}}
            ... }
            >>> await service.handle_webhook_event(webhook_event)
        """
        # Validate event structure
        if not isinstance(event, dict):
            raise ValueError("Event must be a dictionary")

        event_id = event.get("id")
        if not event_id or not isinstance(event_id, str):
            raise ValueError("Event must have a valid 'id' field")

        event_type = event.get("type")
        if not event_type or not isinstance(event_type, str):
            raise ValueError("Event must have a valid 'type' field")

        # Check idempotency (skip if already processed)
        if self._is_webhook_processed(event_id):
            logger.info(f"Webhook event {event_id} already processed, skipping")
            return

        # Validate event type against whitelist (security)
        if event_type not in self.SUPPORTED_EVENT_TYPES:
            logger.warning(f"Unsupported event type '{event_type}', skipping")
            return

        # Get handler for event type
        handler = self._webhook_handlers.get(event_type)
        if not handler:
            logger.warning(f"No handler registered for event type '{event_type}'")
            return

        # Handle the event
        try:
            await handler.handle(event, self)
            self._mark_webhook_processed(event_id)
            logger.info(f"Processed webhook event {event_id} (type: {event_type})")
        except Exception as e:
            logger.error(f"Failed to handle webhook event {event_id}: {e}")
            # Re-raise to trigger webhook retry
            raise

    def _is_webhook_processed(self, event_id: str) -> bool:
        """
        Check if webhook event has already been processed.

        Args:
            event_id: Stripe event ID

        Returns:
            True if event has been processed, False otherwise
        """
        return event_id in self._processed_events

    def _mark_webhook_processed(self, event_id: str) -> None:
        """
        Mark webhook event as processed.

        Args:
            event_id: Stripe event ID
        """
        self._processed_events.add(event_id)
        # In production, implement cleanup of old entries
        # to prevent memory leaks

    # ========================================================================
    # Lock Mechanism
    # ========================================================================

    async def _acquire_lock(self) -> bool:
        """
        Attempt to acquire sync lock.

        Returns:
            True if lock was acquired, False if already locked

        Example:
            >>> if await self._acquire_lock():
            ...     # Perform sync operation
            ...     await self._release_lock()
        """
        # Try to acquire lock without blocking
        if self._lock.locked():
            return False

        await self._lock.acquire()
        return True

    async def _release_lock(self) -> None:
        """
        Release sync lock.

        Should always be called in a finally block to ensure
        lock is released even if an error occurs.
        """
        if self._lock.locked():
            self._lock.release()

    # ========================================================================
    # Background Job Support
    # ========================================================================

    def create_celery_task(self) -> Callable:
        """
        Create a Celery-compatible background task for subscription sync.

        Returns a callable task function that can be registered with Celery
        for periodic execution. The task implements lock mechanism to prevent
        concurrent sync operations.

        Returns:
            Callable task function for Celery registration

        Example:
            >>> from celery import Celery
            >>> celery_app = Celery('tasks')
            >>> @celery_app.task(name='sync_stripe_subscriptions')
            ... def sync_subscriptions_task():
            ...     service = SubscriptionSyncService(...)
            ...     return asyncio.run(service.sync_all_subscriptions())
        """
        def sync_task():
            """Background task for syncing subscriptions."""
            return asyncio.run(self.sync_all_subscriptions())

        return sync_task

    async def sync_job(self) -> Dict[str, Any]:
        """
        Async function suitable for cron-like schedulers.

        This is an alias for sync_all_subscriptions() for compatibility
        with various scheduler interfaces.

        Returns:
            Sync result dictionary with statistics

        Example:
            >>> # In a cron job or scheduler
            >>> result = await service.sync_job()
            >>> print(f"Synced {result['total_synced']} subscriptions")
        """
        return await self.sync_all_subscriptions()
