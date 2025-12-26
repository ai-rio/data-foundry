"""
SubscriptionService - Domain Layer for Stripe subscription operations.

This module provides subscription creation operations following TDD principles.
Implements SubscriptionServiceProtocol interface for dependency injection.

Implements:
- initialize(): Initialize service with Stripe API credentials
- create_subscription(): Create metered subscription with tier-based pricing
- Database persistence to StripeSubscription model
- Comprehensive error handling and logging

Phase: 3 (Subscription Service)
Task: P3-001 (Subscription Creation)

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
                    # Helper to get attribute from both dict and object
                    def get_attr(obj, key, default=None):
                        if hasattr(obj, key):
                            return getattr(obj, key)
                        return obj.get(key, default) if isinstance(obj, dict) else default

                    # Helper to convert timestamp to datetime (handles both int/float and datetime objects)
                    def parse_timestamp(ts):
                        if ts is None:
                            return None
                        if isinstance(ts, datetime):
                            return ts
                        # Assume it's a timestamp
                        return datetime.fromtimestamp(ts, tz=timezone.utc)

                    db_subscription = StripeSubscription(
                        tenant_id=tenant_id,
                        stripe_subscription_id=subscription_id,
                        stripe_customer_id=stripe_customer_id,
                        status=get_attr(stripe_subscription, 'status'),
                        current_period_start=parse_timestamp(get_attr(stripe_subscription, 'current_period_start')),
                        current_period_end=parse_timestamp(get_attr(stripe_subscription, 'current_period_end')),
                        cancel_at_period_end=get_attr(stripe_subscription, 'cancel_at_period_end', False),
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
