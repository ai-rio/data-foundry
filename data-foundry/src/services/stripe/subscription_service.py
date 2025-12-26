"""
SubscriptionService - Domain Layer for Stripe subscription operations.

This module provides subscription creation operations following TDD principles.
Implements SubscriptionServiceProtocol interface for dependency injection.

Implements:
- initialize(): Initialize service with Stripe API credentials
- create_subscription(): Create metered subscription with tier-based pricing
- update_subscription_tier(): Update subscription tier with proration
- cancel_subscription(): Cancel subscription (immediate or period-end)
- Database persistence to StripeSubscription model
- Comprehensive error handling and logging

Phase: 3 (Subscription Service)
Task: P3-001 (Subscription Creation), P3-002 (Tier Management)

Security Features:
- Proper error handling with custom exception classes
- Database persistence for Stripe subscription records
- Tenant isolation through tenant_id
- Stripe API integration with proper error handling
- Logging for all operations

Testing Approach: TDD (Test-Driven Development)
- Tests written FIRST in test_subscription_service.py
- Implementation follows to make tests pass
- Red-Green-Refactor cycle followed
- 90%+ test coverage target
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.stripe.types import (
    SubscriptionServiceProtocol,
    SubscriptionData,
    SubscriptionTier,
    PriceType
)
from typing import Any, Union
from src.services.stripe.exceptions import (
    StripeAPIError,
    StripeServiceError
)
from src.services.stripe.config import StripeConfig
from src.models.stripe_billing import StripeSubscription


logger = logging.getLogger(__name__)


class SubscriptionService(SubscriptionServiceProtocol):
    """
    Domain service for Stripe subscription operations.

    Implements SubscriptionServiceProtocol interface for dependency injection.
    Provides subscription creation operations with:
    - Stripe API integration
    - Tier-based pricing (Gold, Silver, Bronze)
    - Metered billing for usage-based components
    - Trial period support
    - Database persistence
    - Proper error handling and logging

    This service must be initialized with Stripe API credentials before use.

    Example:
        >>> service = SubscriptionService()
        >>> await service.initialize(api_key="sk_test_...")
        >>> subscription = await service.create_subscription(
        ...     tenant_id="tenant_123",
        ...     stripe_customer_id="cus_abc123",
        ...     tier=SubscriptionTier.GOLD,
        ...     trial_days=14
        ... )
    """

    def __init__(self):
        """Initialize SubscriptionService.

        The service must be initialized by calling initialize() before use.
        """
        self._initialized: bool = False
        self.api_key: Optional[str] = None
        self._config: Optional[StripeConfig] = None

    async def initialize(self, api_key: str) -> None:
        """
        Initialize SubscriptionService with Stripe API key.

        Args:
            api_key: Stripe secret API key (sk_test_... or sk_live_...)

        Raises:
            StripeServiceError: If api_key is empty or initialization fails

        Example:
            >>> service = SubscriptionService()
            >>> await service.initialize(api_key="sk_test_...")
        """
        if not api_key:
            raise StripeServiceError(
                "Stripe API key cannot be empty. "
                "Please provide a valid API key."
            )

        try:
            self.api_key = api_key
            stripe.api_key = self.api_key
            self._config = StripeConfig.from_environment()
            self._initialized = True
            logger.info("SubscriptionService initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize SubscriptionService: {e}")
            raise StripeServiceError(f"Failed to initialize SubscriptionService: {e}") from e

    def _ensure_initialized(self) -> None:
        """
        Ensure service is initialized before use.

        Raises:
            StripeServiceError: If service is not initialized
        """
        if not self._initialized:
            raise StripeServiceError(
                "SubscriptionService not initialized. Call initialize() before using the service."
            )

    @staticmethod
    def _validate_subscription_id(subscription_id: str) -> None:
        """
        Validate subscription ID format.

        Args:
            subscription_id: Stripe subscription ID to validate

        Raises:
            StripeServiceError: If subscription_id format is invalid
        """
        if not subscription_id:
            raise StripeServiceError("Subscription ID cannot be empty")

        if not subscription_id.startswith("sub_"):
            raise StripeServiceError("Subscription ID must start with 'sub_'")

        if len(subscription_id) < 10:
            raise StripeServiceError("Subscription ID must be at least 10 characters")

        if len(subscription_id) > 100:
            raise StripeServiceError("Subscription ID cannot exceed 100 characters")

    async def _verify_tenant_ownership(
        self,
        subscription_id: str,
        requesting_tenant_id: str,
        db_session: AsyncSession
    ) -> None:
        """
        Verify that the requesting tenant owns the subscription.

        Args:
            subscription_id: Stripe subscription ID
            requesting_tenant_id: Tenant ID of the requesting user
            db_session: Database session for querying

        Raises:
            StripeServiceError: If subscription not found or tenant doesn't own it
        """
        from sqlalchemy import select

        stmt = select(StripeSubscription).where(
            StripeSubscription.stripe_subscription_id == subscription_id
        )
        result = await db_session.execute(stmt)
        db_subscription = result.scalar_one_or_none()

        if not db_subscription:
            raise StripeServiceError("Subscription not found")

        if db_subscription.tenant_id != requesting_tenant_id:
            raise StripeServiceError("Access denied: tenant ownership verification failed")

    @staticmethod
    def _parse_timestamp(ts):
        """
        Convert timestamp to datetime.

        Handles both int/float timestamps and datetime objects.

        Args:
            ts: Timestamp (int/float) or datetime object

        Returns:
            datetime object or None if ts is None
        """
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts
        # Assume it's a timestamp
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    @staticmethod
    def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
        """
        Helper to get attribute from both dict and object.

        Args:
            obj: Object or dict to get attribute from
            key: Attribute/key name
            default: Default value if not found

        Returns:
            Attribute value or default
        """
        # For dictionaries, use get() method to avoid conflicts with built-in methods
        if isinstance(obj, dict):
            return obj.get(key, default)

        # For objects, use getattr
        if hasattr(obj, key):
            return getattr(obj, key)

        return default

    def _build_subscription_items(self, tier: SubscriptionTier) -> list:
        """
        Build subscription items array for Stripe API.

        Creates the subscription items structure with tier-specific price IDs
        for metered billing components (AI labels, human audits) and platform fee.

        Args:
            tier: Subscription tier (GOLD, SILVER, BRONZE)

        Returns:
            List of subscription item dictionaries for Stripe API

        Raises:
            StripeServiceError: If price IDs are not configured for the tier

        Example:
            >>> items = self._build_subscription_items(SubscriptionTier.GOLD)
            >>> len(items)
            3
        """
        if not self._config:
            self._config = StripeConfig.from_environment()

        # Get price IDs for the tier
        ai_labels_price = self._config.get_price_id(tier, PriceType.AI_LABELS)
        human_audits_price = self._config.get_price_id(tier, PriceType.HUMAN_AUDITS)
        platform_fee_price = self._config.get_price_id(tier, PriceType.PLATFORM_FEE)

        # Validate price IDs are configured
        if not all([ai_labels_price, human_audits_price, platform_fee_price]):
            missing = []
            if not ai_labels_price:
                missing.append(f"{tier.value}.ai_labels")
            if not human_audits_price:
                missing.append(f"{tier.value}.human_audits")
            if not platform_fee_price:
                missing.append(f"{tier.value}.platform_fee")

            raise StripeServiceError(
                f"Price IDs not configured for {tier.value} tier. "
                f"Missing: {', '.join(missing)}. "
                f"Please set environment variables: "
                f"STRIPE_{tier.value.upper()}_AI_LABELS_PRICE_ID, "
                f"STRIPE_{tier.value.upper()}_HUMAN_AUDITS_PRICE_ID, "
                f"STRIPE_{tier.value.upper()}_PLATFORM_FEE_PRICE_ID"
            )

        # Build subscription items
        # Note: The prices themselves are configured as metered in Stripe
        # We don't need to specify 'meter' parameter in the API call
        subscription_items = [
            {
                "price": ai_labels_price,
                # Price is configured with recurring.usage_type="metered" in Stripe
            },
            {
                "price": human_audits_price,
                # Price is configured with recurring.usage_type="metered" in Stripe
            },
            {
                "price": platform_fee_price,
                "quantity": 1  # Platform fee is fixed quantity
            }
        ]

        logger.debug(
            f"Built {len(subscription_items)} subscription items for {tier.value} tier"
        )
        return subscription_items

    async def create_subscription(
        self,
        tenant_id: str,
        stripe_customer_id: str,
        tier: SubscriptionTier,
        trial_days: Optional[int] = None,
        db_session: Optional[AsyncSession] = None
    ) -> SubscriptionData:
        """
        Create a metered subscription for a customer.

        Creates a new Stripe subscription with:
        - Tier-based pricing (Gold, Silver, Bronze)
        - Metered billing for AI labels and human audits
        - Fixed platform fee
        - Optional trial period

        Args:
            tenant_id: Tenant identifier for database record
            stripe_customer_id: Stripe customer ID (cus_*)
            tier: Subscription tier (GOLD, SILVER, BRONZE)
            trial_days: Optional trial period in days
            db_session: Optional database session for persistence

        Returns:
            SubscriptionData dictionary with subscription information

        Raises:
            StripeServiceError: If service not initialized or validation fails
            StripeAPIError: If Stripe API call fails

        Example:
            >>> subscription = await service.create_subscription(
            ...     tenant_id="tenant_123",
            ...     stripe_customer_id="cus_abc123",
            ...     tier=SubscriptionTier.GOLD,
            ...     trial_days=14,
            ...     db_session=session
            ... )
            >>> print(subscription['stripe_subscription_id'])
            'sub_test123'
        """
        self._ensure_initialized()

        try:
            # Build subscription items for the tier
            subscription_items = self._build_subscription_items(tier)

            # Prepare subscription parameters
            subscription_params = {
                "customer": stripe_customer_id,
                "items": subscription_items
            }

            # Add trial period if specified
            if trial_days and trial_days > 0:
                subscription_params["trial_period_days"] = trial_days
                logger.info(f"Creating subscription with {trial_days}-day trial period")

            # Create subscription in Stripe
            stripe_subscription = stripe.Subscription.create(**subscription_params)
            subscription_id = stripe_subscription.id if hasattr(stripe_subscription, 'id') else stripe_subscription.get('id')
            logger.info(
                f"Created Stripe subscription {subscription_id} "
                f"for customer {stripe_customer_id}, tier {tier.value}"
            )

            # Persist to database if session provided
            if db_session:
                try:
                    db_subscription = StripeSubscription(
                        tenant_id=tenant_id,
                        stripe_subscription_id=subscription_id,
                        stripe_customer_id=stripe_customer_id,
                        status=self._get_attr(stripe_subscription, 'status'),
                        current_period_start=self._parse_timestamp(
                            self._get_attr(stripe_subscription, 'current_period_start')
                        ),
                        current_period_end=self._parse_timestamp(
                            self._get_attr(stripe_subscription, 'current_period_end')
                        ),
                        cancel_at_period_end=self._get_attr(stripe_subscription, 'cancel_at_period_end', False),
                        tier=tier.value
                    )
                    db_session.add(db_subscription)
                    await db_session.commit()
                    await db_session.refresh(db_subscription)
                    logger.info(f"Persisted subscription to database")
                except Exception as db_error:
                    logger.error(f"Failed to persist subscription to database: {db_error}")
                    # Continue anyway - subscription was created in Stripe
                    # Database persistence is optional for consistency

            # Return subscription data as SubscriptionData TypedDict
            return self._stripe_subscription_to_subscription_data(
                stripe_subscription,
                tenant_id,
                stripe_customer_id,
                tier
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error creating subscription: {e}")
            raise StripeAPIError(
                f"Failed to create subscription: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except StripeServiceError:
            # Re-raise service errors as-is
            raise

        except Exception as e:
            logger.error(f"Unexpected error creating subscription: {e}")
            raise StripeServiceError(f"Failed to create subscription: {e}") from e

    def _stripe_subscription_to_subscription_data(
        self,
        stripe_subscription,
        tenant_id: str,
        stripe_customer_id: str,
        tier: SubscriptionTier
    ) -> SubscriptionData:
        """
        Convert Stripe subscription object to SubscriptionData TypedDict.

        Args:
            stripe_subscription: Stripe API subscription object
            tenant_id: Tenant identifier
            stripe_customer_id: Stripe customer ID
            tier: Subscription tier

        Returns:
            SubscriptionData dictionary with subscription information
        """
        # Helper to get attribute from both dict and object
        def get_attr(obj, key, default=None):
            if hasattr(obj, key):
                return getattr(obj, key)
            return obj.get(key, default) if isinstance(obj, dict) else default

        # Helper to convert timestamp to datetime and then to ISO format
        def parse_timestamp_to_iso(ts):
            if ts is None:
                return None
            if isinstance(ts, datetime):
                return ts.isoformat()
            # Assume it's a timestamp
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        # Convert timestamps to ISO format strings
        current_period_start = parse_timestamp_to_iso(get_attr(stripe_subscription, 'current_period_start'))
        current_period_end = parse_timestamp_to_iso(get_attr(stripe_subscription, 'current_period_end'))

        return SubscriptionData(
            tenant_id=tenant_id,
            stripe_subscription_id=get_attr(stripe_subscription, 'id'),
            stripe_customer_id=stripe_customer_id,
            status=get_attr(stripe_subscription, 'status', 'unknown'),
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            tier=tier.value,
            cancel_at_period_end=get_attr(stripe_subscription, 'cancel_at_period_end', False),
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat()
        )

    async def update_subscription_tier(
        self,
        stripe_subscription_id: str,
        new_tier: SubscriptionTier,
        db_session: Optional[AsyncSession] = None,
        requesting_tenant_id: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> SubscriptionData:
        """
        Update subscription tier with proration.

        Updates an existing subscription to a new tier with automatic proration
        for the billing difference. Handles both upgrades and downgrades.

        Args:
            stripe_subscription_id: Stripe subscription ID (sub_*)
            new_tier: New subscription tier (GOLD, SILVER, BRONZE)
            db_session: Optional database session for persistence
            requesting_tenant_id: Optional tenant ID for ownership verification
            idempotency_key: Optional idempotency key for duplicate request prevention

        Returns:
            SubscriptionData dictionary with updated subscription information

        Raises:
            StripeServiceError: If service not initialized or validation fails
            StripeAPIError: If Stripe API call fails

        Example:
            >>> updated = await service.update_subscription_tier(
            ...     stripe_subscription_id="sub_abc123",
            ...     new_tier=SubscriptionTier.GOLD,
            ...     db_session=session,
            ...     requesting_tenant_id="tenant_123"
            ... )
            >>> print(updated['tier'])
            'gold'
        """
        self._ensure_initialized()

        # Validate subscription ID format
        self._validate_subscription_id(stripe_subscription_id)

        # Verify tenant ownership if db_session and requesting_tenant_id provided
        if db_session and requesting_tenant_id:
            await self._verify_tenant_ownership(
                stripe_subscription_id,
                requesting_tenant_id,
                db_session
            )

        try:
            # Fetch current subscription from Stripe
            current_subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            current_status = self._get_attr(current_subscription, 'status', 'unknown')

            # Validate subscription can be updated
            if current_status == 'canceled':
                raise StripeServiceError(
                    "Cannot update tier for canceled subscription"
                )

            # Get current subscription items
            current_items = self._get_attr(current_subscription, 'items', {})
            current_items_data = self._get_attr(current_items, 'data', [])

            # Build new subscription items for the new tier
            new_items = self._build_updated_subscription_items(
                current_items_data,
                new_tier
            )

            # Check if tier is actually changing
            current_tier = self._detect_current_tier(current_items_data)
            if current_tier == new_tier.value:
                logger.info(
                    f"Subscription already on {new_tier.value} tier"
                )
                # Get tenant_id from database if available
                tenant_id = ''
                if db_session:
                    from sqlalchemy import select
                    stmt = select(StripeSubscription).where(
                        StripeSubscription.stripe_subscription_id == stripe_subscription_id
                    )
                    result = await db_session.execute(stmt)
                    db_sub = result.scalar_one_or_none()
                    if db_sub:
                        tenant_id = db_sub.tenant_id

                # Return current subscription data
                return self._stripe_subscription_to_subscription_data(
                    current_subscription,
                    tenant_id,
                    self._get_attr(current_subscription, 'customer', ''),
                    new_tier
                )

            # Update subscription in Stripe with proration
            logger.info(
                f"Updating subscription from {current_tier} to {new_tier.value} tier"
            )

            # Prepare modify parameters
            modify_params = {
                "items": new_items,
                "proration_behavior": "create_prorations"
            }

            # Add idempotency key if provided
            if idempotency_key:
                modify_params["idempotency_key"] = idempotency_key

            updated_subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                **modify_params
            )

            # Get tenant_id from database
            tenant_id = ''
            if db_session:
                try:
                    # Fetch database record
                    from sqlalchemy import select
                    stmt = select(StripeSubscription).where(
                        StripeSubscription.stripe_subscription_id == stripe_subscription_id
                    )
                    result = await db_session.execute(stmt)
                    db_subscription = result.scalar_one_or_none()

                    if db_subscription:
                        tenant_id = db_subscription.tenant_id

                        # Update tier
                        db_subscription.tier = new_tier.value
                        db_subscription.status = self._get_attr(updated_subscription, 'status', current_status)

                        # Update timestamps using the class method
                        db_subscription.current_period_start = self._parse_timestamp(
                            self._get_attr(updated_subscription, 'current_period_start')
                        )
                        db_subscription.current_period_end = self._parse_timestamp(
                            self._get_attr(updated_subscription, 'current_period_end')
                        )

                        await db_session.commit()
                        await db_session.refresh(db_subscription)
                        logger.info(f"Updated subscription tier in database")

                except Exception as db_error:
                    logger.error(f"Failed to update subscription in database: {db_error}")
                    # Continue anyway - subscription was updated in Stripe

            # Return updated subscription data
            return self._stripe_subscription_to_subscription_data(
                updated_subscription,
                tenant_id,
                self._get_attr(current_subscription, 'customer', ''),
                new_tier
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error updating subscription tier: {e}")
            raise StripeAPIError(
                f"Failed to update subscription tier: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except StripeServiceError:
            # Re-raise service errors as-is
            raise

        except Exception as e:
            logger.error(f"Unexpected error updating subscription tier: {e}")
            raise StripeServiceError(f"Failed to update subscription tier: {e}") from e

    async def cancel_subscription(
        self,
        stripe_subscription_id: str,
        at_period_end: bool = True,
        db_session: Optional[AsyncSession] = None,
        requesting_tenant_id: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> SubscriptionData:
        """
        Cancel subscription.

        Cancels a subscription either immediately or at the end of the current billing period.

        Args:
            stripe_subscription_id: Stripe subscription ID (sub_*)
            at_period_end: If True, cancel at period end; if False, cancel immediately
            db_session: Optional database session for persistence
            requesting_tenant_id: Optional tenant ID for ownership verification
            idempotency_key: Optional idempotency key for duplicate request prevention

        Returns:
            SubscriptionData dictionary with updated subscription information

        Raises:
            StripeServiceError: If service not initialized or validation fails
            StripeAPIError: If Stripe API call fails

        Example:
            >>> canceled = await service.cancel_subscription(
            ...     stripe_subscription_id="sub_abc123",
            ...     at_period_end=True,
            ...     db_session=session,
            ...     requesting_tenant_id="tenant_123"
            ... )
            >>> print(canceled['status'])
            'active'  # Still active until period end
        """
        self._ensure_initialized()

        # Validate subscription ID format
        self._validate_subscription_id(stripe_subscription_id)

        # Verify tenant ownership if db_session and requesting_tenant_id provided
        if db_session and requesting_tenant_id:
            await self._verify_tenant_ownership(
                stripe_subscription_id,
                requesting_tenant_id,
                db_session
            )

        try:
            # Fetch current subscription from Stripe
            current_subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            current_status = self._get_attr(current_subscription, 'status', 'unknown')

            # Validate subscription can be canceled
            if current_status == 'canceled':
                raise StripeServiceError(
                    "Subscription is already canceled"
                )

            # Get tenant_id from database
            tenant_id = ''
            if db_session:
                from sqlalchemy import select
                stmt = select(StripeSubscription).where(
                    StripeSubscription.stripe_subscription_id == stripe_subscription_id
                )
                result = await db_session.execute(stmt)
                db_sub = result.scalar_one_or_none()
                if db_sub:
                    tenant_id = db_sub.tenant_id

            if at_period_end:
                # Cancel at period end using modify
                logger.info(
                    "Scheduling subscription for cancellation at period end"
                )
                modify_params = {"cancel_at_period_end": True}
                if idempotency_key:
                    modify_params["idempotency_key"] = idempotency_key
                updated_subscription = stripe.Subscription.modify(
                    stripe_subscription_id,
                    **modify_params
                )
            else:
                # Cancel immediately using delete
                logger.info("Canceling subscription immediately")
                delete_params = {}
                if idempotency_key:
                    delete_params["idempotency_key"] = idempotency_key
                updated_subscription = stripe.Subscription.delete(
                    stripe_subscription_id,
                    **delete_params
                )

            # Update database if session provided
            if db_session:
                try:
                    from sqlalchemy import select
                    stmt = select(StripeSubscription).where(
                        StripeSubscription.stripe_subscription_id == stripe_subscription_id
                    )
                    result = await db_session.execute(stmt)
                    db_subscription = result.scalar_one_or_none()

                    if db_subscription:
                        # Update status
                        db_subscription.status = self._get_attr(updated_subscription, 'status', 'canceled')

                        # Update cancel_at_period_end flag
                        db_subscription.cancel_at_period_end = self._get_attr(
                            updated_subscription,
                            'cancel_at_period_end',
                            False
                        )

                        await db_session.commit()
                        await db_session.refresh(db_subscription)
                        logger.info(f"Updated subscription status in database")

                except Exception as db_error:
                    logger.error(f"Failed to update subscription in database: {db_error}")
                    # Continue anyway - subscription was canceled in Stripe

            # Return updated subscription data
            # Detect tier from items
            items = self._get_attr(updated_subscription, 'items', {})
            items_data = self._get_attr(items, 'data', [])
            detected_tier_value = self._detect_current_tier(items_data)

            # Convert to SubscriptionTier enum
            try:
                detected_tier = SubscriptionTier(detected_tier_value)
            except ValueError:
                # Default to BRONZE if detection fails
                detected_tier = SubscriptionTier.BRONZE

            return self._stripe_subscription_to_subscription_data(
                updated_subscription,
                tenant_id,
                self._get_attr(current_subscription, 'customer', ''),
                detected_tier
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error canceling subscription: {e}")
            raise StripeAPIError(
                f"Failed to cancel subscription: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except StripeServiceError:
            # Re-raise service errors as-is
            raise

        except Exception as e:
            logger.error(f"Unexpected error canceling subscription: {e}")
            raise StripeServiceError(f"Failed to cancel subscription: {e}") from e

    def _build_updated_subscription_items(
        self,
        current_items: list,
        new_tier: SubscriptionTier
    ) -> list:
        """
        Build updated subscription items array for tier change.

        Args:
            current_items: Current subscription items from Stripe
            new_tier: New tier to update to

        Returns:
            List of subscription item dictionaries for Stripe API

        Raises:
            StripeServiceError: If price IDs not configured for new tier
        """
        if not self._config:
            self._config = StripeConfig.from_environment()

        # Get price IDs for the new tier
        ai_labels_price = self._config.get_price_id(new_tier, PriceType.AI_LABELS)
        human_audits_price = self._config.get_price_id(new_tier, PriceType.HUMAN_AUDITS)
        platform_fee_price = self._config.get_price_id(new_tier, PriceType.PLATFORM_FEE)

        # Validate price IDs are configured
        if not all([ai_labels_price, human_audits_price, platform_fee_price]):
            missing = []
            if not ai_labels_price:
                missing.append(f"{new_tier.value}.ai_labels")
            if not human_audits_price:
                missing.append(f"{new_tier.value}.human_audits")
            if not platform_fee_price:
                missing.append(f"{new_tier.value}.platform_fee")

            raise StripeServiceError(
                f"Price IDs not configured for {new_tier.value} tier. "
                f"Missing: {', '.join(missing)}"
            )

        # Map price types to current items
        # We need to update existing items with new price IDs
        updated_items = []

        for item in current_items:
            item_id = self._get_attr(item, 'id')
            price = self._get_attr(item, 'price', {})
            price_id = self._get_attr(price, 'id', '')

            # Determine price type based on current price ID
            price_type = self._identify_price_type(price_id)

            # Map to new price ID
            if price_type == 'ai_labels' and ai_labels_price:
                updated_items.append({
                    "id": item_id,
                    "price": ai_labels_price
                })
            elif price_type == 'human_audits' and human_audits_price:
                updated_items.append({
                    "id": item_id,
                    "price": human_audits_price
                })
            elif price_type == 'platform_fee' and platform_fee_price:
                updated_items.append({
                    "id": item_id,
                    "price": platform_fee_price,
                    "quantity": 1
                })

        logger.debug(
            f"Built {len(updated_items)} updated subscription items for {new_tier.value} tier"
        )
        return updated_items

    def _identify_price_type(self, price_id: str) -> Optional[str]:
        """
        Identify price type (ai_labels, human_audits, platform_fee) from price ID.

        Args:
            price_id: Stripe price ID

        Returns:
            Price type string or None if not recognized
        """
        if not self._config:
            self._config = StripeConfig.from_environment()

        # Check each tier's price IDs
        for tier in [SubscriptionTier.GOLD, SubscriptionTier.SILVER, SubscriptionTier.BRONZE]:
            for price_type in PriceType:
                tier_price_id = self._config.get_price_id(tier, price_type)
                if tier_price_id and price_id == tier_price_id:
                    return price_type.value

        return None

    def _detect_current_tier(self, items_data: list) -> str:
        """
        Detect current subscription tier from items.

        Args:
            items_data: List of subscription items from Stripe

        Returns:
            Tier value string (gold, silver, bronze)
        """
        if not items_data:
            return "bronze"  # Default to bronze

        if not self._config:
            self._config = StripeConfig.from_environment()

        # Get first price ID to identify tier
        for item in items_data:
            price = self._get_attr(item, 'price', {})
            price_id = self._get_attr(price, 'id', '')

            if price_id:
                # Check each tier
                for tier in [SubscriptionTier.GOLD, SubscriptionTier.SILVER, SubscriptionTier.BRONZE]:
                    for price_type in PriceType:
                        tier_price_id = self._config.get_price_id(tier, price_type)
                        if tier_price_id and price_id == tier_price_id:
                            return tier.value

        return "bronze"  # Default if detection fails
