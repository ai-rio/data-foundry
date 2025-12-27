"""
Unit tests for SubscriptionService following TDD principles.

This test suite follows the Test-Driven Development approach:
1. Tests are written FIRST (before implementation)
2. Tests define the expected behavior
3. Implementation will be written to make tests pass
4. Red-Green-Refactor cycle

Task: P3-001 (Subscription Creation)
Phase: 3 (Subscription Service)
Created: 2025-12-26

Test Coverage:
- Service initialization
- Subscription creation for all tiers (Gold, Silver, Bronze)
- Trial period support
- Database persistence
- Error handling (invalid inputs, API errors, not initialized)
- Edge cases and boundary conditions
"""

import os
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

import stripe

from src.services.stripe.subscription_service import SubscriptionService
from src.services.stripe.types import (
    SubscriptionServiceProtocol,
    SubscriptionData,
    SubscriptionTier,
    PriceType
)
from src.services.stripe.exceptions import (
    StripeServiceError,
    StripeAPIError
)
from src.services.stripe.config import StripeConfig
from src.models.stripe_billing import StripeSubscription


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def setup_environment():
    """Set up environment variables for price IDs."""
    # Gold tier prices
    os.environ["STRIPE_GOLD_AI_LABELS_PRICE_ID"] = "price_gold_ai_labels"
    os.environ["STRIPE_GOLD_HUMAN_AUDITS_PRICE_ID"] = "price_gold_human_audits"
    os.environ["STRIPE_GOLD_PLATFORM_FEE_PRICE_ID"] = "price_gold_platform_fee"

    # Silver tier prices
    os.environ["STRIPE_SILVER_AI_LABELS_PRICE_ID"] = "price_silver_ai_labels"
    os.environ["STRIPE_SILVER_HUMAN_AUDITS_PRICE_ID"] = "price_silver_human_audits"
    os.environ["STRIPE_SILVER_PLATFORM_FEE_PRICE_ID"] = "price_silver_platform_fee"

    # Bronze tier prices
    os.environ["STRIPE_BRONZE_AI_LABELS_PRICE_ID"] = "price_bronze_ai_labels"
    os.environ["STRIPE_BRONZE_HUMAN_AUDITS_PRICE_ID"] = "price_bronze_human_audits"
    os.environ["STRIPE_BRONZE_PLATFORM_FEE_PRICE_ID"] = "price_bronze_platform_fee"

    yield

    # Cleanup
    for key in list(os.environ.keys()):
        if key.startswith("STRIPE_") and "_PRICE_ID" in key:
            del os.environ[key]


@pytest.fixture
def sample_api_key():
    """Sample Stripe API key for testing."""
    return "sk_test_51AbC123xyz"


@pytest.fixture
def mock_stripe_subscription():
    """Mock Stripe subscription object."""
    now = datetime.now(timezone.utc)
    return {
        "id": "sub_test123",
        "customer": "cus_test123",
        "status": "active",
        "current_period_start": now,
        "current_period_end": now + timedelta(days=30),
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {"price": {"id": "price_gold_ai_labels", "type": "recurring"}},
                {"price": {"id": "price_gold_human_audits", "type": "recurring"}},
                {"price": {"id": "price_gold_platform_fee", "type": "recurring"}}
            ]
        }
    }


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.add = Mock()

    # Mock execute to return a mock result
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = Mock(return_value=None)  # No existing subscription
    session.execute = AsyncMock(return_value=mock_result)

    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def subscription_service():
    """Create SubscriptionService instance for testing."""
    return SubscriptionService()


# ============================================================================
# Test Class: SubscriptionService Initialization
# ============================================================================

class TestSubscriptionServiceInitialization:
    """Test suite for SubscriptionService initialization."""

    @pytest.mark.asyncio
    async def test_initialize_service_with_valid_api_key(self, subscription_service, sample_api_key):
        """Test service initialization with valid API key."""
        # Act
        await subscription_service.initialize(sample_api_key)

        # Assert
        assert subscription_service._initialized is True
        assert subscription_service.api_key == sample_api_key
        assert stripe.api_key == sample_api_key

    @pytest.mark.asyncio
    async def test_initialize_service_with_empty_api_key(self, subscription_service):
        """Test service initialization fails with empty API key."""
        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.initialize("")

        assert "API key cannot be empty" in str(exc_info.value)
        assert subscription_service._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_service_with_none_api_key(self, subscription_service):
        """Test service initialization fails with None API key."""
        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.initialize(None)

        assert "API key cannot be empty" in str(exc_info.value)


# ============================================================================
# Test Class: Subscription Creation - Gold Tier
# ============================================================================

class TestSubscriptionCreationGoldTier:
    """Test suite for Gold tier subscription creation."""

    @pytest.mark.asyncio
    async def test_create_subscription_gold_tier(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test creating Gold tier subscription with metered billing."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        tenant_id = "tenant_gold_001"
        stripe_customer_id = "cus_gold_001"

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            result = await subscription_service.create_subscription(
                tenant_id=tenant_id,
                stripe_customer_id=stripe_customer_id,
                tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

            # Assert - Stripe API called
            mock_create.assert_called_once()
            call_args = mock_create.call_args[1]
            assert call_args["customer"] == stripe_customer_id
            assert len(call_args["items"]) == 3

            # Assert - Price IDs for Gold tier
            price_ids = [item["price"] for item in call_args["items"]]
            assert "price_gold_ai_labels" in price_ids
            assert "price_gold_human_audits" in price_ids
            assert "price_gold_platform_fee" in price_ids

            # Assert - Return value
            assert result["stripe_subscription_id"] == "sub_test123"
            assert result["stripe_customer_id"] == stripe_customer_id
            assert result["status"] == "active"
            assert result["tier"] == "gold"

            # Assert - Database persisted
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_subscription_gold_with_trial_period(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test creating Gold tier subscription with trial period."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        tenant_id = "tenant_gold_002"
        stripe_customer_id = "cus_gold_002"
        trial_days = 14

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            await subscription_service.create_subscription(
                tenant_id=tenant_id,
                stripe_customer_id=stripe_customer_id,
                tier=SubscriptionTier.GOLD,
                trial_days=trial_days,
                db_session=mock_db_session
            )

            # Assert
            call_args = mock_create.call_args[1]
            assert call_args["trial_period_days"] == trial_days


# ============================================================================
# Test Class: Subscription Creation - Silver Tier
# ============================================================================

class TestSubscriptionCreationSilverTier:
    """Test suite for Silver tier subscription creation."""

    @pytest.mark.asyncio
    async def test_create_subscription_silver_tier(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test creating Silver tier subscription."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        tenant_id = "tenant_silver_001"
        stripe_customer_id = "cus_silver_001"

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            result = await subscription_service.create_subscription(
                tenant_id=tenant_id,
                stripe_customer_id=stripe_customer_id,
                tier=SubscriptionTier.SILVER,
                db_session=mock_db_session
            )

            # Assert - Stripe API called with Silver price IDs
            call_args = mock_create.call_args[1]
            price_ids = [item["price"] for item in call_args["items"]]
            assert "price_silver_ai_labels" in price_ids
            assert "price_silver_human_audits" in price_ids
            assert "price_silver_platform_fee" in price_ids

            # Assert - Return value
            assert result["tier"] == "silver"


# ============================================================================
# Test Class: Subscription Creation - Bronze Tier
# ============================================================================

class TestSubscriptionCreationBronzeTier:
    """Test suite for Bronze tier subscription creation."""

    @pytest.mark.asyncio
    async def test_create_subscription_bronze_tier(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test creating Bronze tier subscription."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        tenant_id = "tenant_bronze_001"
        stripe_customer_id = "cus_bronze_001"

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            result = await subscription_service.create_subscription(
                tenant_id=tenant_id,
                stripe_customer_id=stripe_customer_id,
                tier=SubscriptionTier.BRONZE,
                db_session=mock_db_session
            )

            # Assert - Stripe API called with Bronze price IDs
            call_args = mock_create.call_args[1]
            price_ids = [item["price"] for item in call_args["items"]]
            assert "price_bronze_ai_labels" in price_ids
            assert "price_bronze_human_audits" in price_ids
            assert "price_bronze_platform_fee" in price_ids

            # Assert - Return value
            assert result["tier"] == "bronze"


# ============================================================================
# Test Class: Database Persistence
# ============================================================================

class TestSubscriptionPersistence:
    """Test suite for database persistence."""

    @pytest.mark.asyncio
    async def test_create_subscription_persists_to_database(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test that subscription is persisted to database correctly."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        tenant_id = "tenant_persist_001"
        stripe_customer_id = "cus_persist_001"

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            await subscription_service.create_subscription(
                tenant_id=tenant_id,
                stripe_customer_id=stripe_customer_id,
                tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

            # Assert - Database add called with StripeSubscription
            mock_db_session.add.assert_called_once()
            added_obj = mock_db_session.add.call_args[0][0]
            assert isinstance(added_obj, StripeSubscription)
            assert added_obj.tenant_id == tenant_id
            assert added_obj.stripe_subscription_id == "sub_test123"
            assert added_obj.stripe_customer_id == stripe_customer_id
            assert added_obj.status == "active"
            assert added_obj.tier == "gold"
            assert added_obj.cancel_at_period_end is False

            # Assert - Commit and refresh called
            mock_db_session.commit.assert_called_once()
            mock_db_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_subscription_without_db_session(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription
    ):
        """Test subscription creation without database session."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        tenant_id = "tenant_no_db_001"
        stripe_customer_id = "cus_no_db_001"

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            result = await subscription_service.create_subscription(
                tenant_id=tenant_id,
                stripe_customer_id=stripe_customer_id,
                tier=SubscriptionTier.GOLD,
                db_session=None
            )

            # Assert - Still returns subscription data
            assert result["stripe_subscription_id"] == "sub_test123"
            assert result["tier"] == "gold"


# ============================================================================
# Test Class: Error Handling
# ============================================================================

class TestSubscriptionErrorHandling:
    """Test suite for error handling."""

    @pytest.mark.asyncio
    async def test_create_subscription_not_initialized(
        self,
        subscription_service
    ):
        """Test that create_subscription fails if service not initialized."""
        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.create_subscription(
                tenant_id="tenant_001",
                stripe_customer_id="cus_001",
                tier=SubscriptionTier.GOLD
            )

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_subscription_stripe_api_error(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test handling of Stripe API errors."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        tenant_id = "tenant_error_001"
        stripe_customer_id = "cus_error_001"

        with patch('stripe.Subscription.create') as mock_create:
            # Simulate Stripe API error
            mock_create.side_effect = stripe.error.InvalidRequestError(
                "No such customer",
                "customer"
            )

            # Act & Assert
            with pytest.raises(StripeAPIError) as exc_info:
                await subscription_service.create_subscription(
                    tenant_id=tenant_id,
                    stripe_customer_id=stripe_customer_id,
                    tier=SubscriptionTier.GOLD,
                    db_session=mock_db_session
                )

            assert "Failed to create subscription" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_subscription_with_invalid_customer_id(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test handling of invalid customer ID."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.side_effect = stripe.error.InvalidRequestError(
                "Invalid customer ID",
                "customer"
            )

            # Act & Assert
            with pytest.raises(StripeAPIError):
                await subscription_service.create_subscription(
                    tenant_id="tenant_001",
                    stripe_customer_id="invalid_customer",
                    tier=SubscriptionTier.GOLD,
                    db_session=mock_db_session
                )


# ============================================================================
# Test Class: Edge Cases
# ============================================================================

class TestSubscriptionEdgeCases:
    """Test suite for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_create_subscription_with_zero_trial_days(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test subscription with zero trial days (no trial)."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            await subscription_service.create_subscription(
                tenant_id="tenant_001",
                stripe_customer_id="cus_001",
                tier=SubscriptionTier.GOLD,
                trial_days=0,
                db_session=mock_db_session
            )

            # Assert - trial_period_days should not be in call
            call_args = mock_create.call_args[1]
            assert "trial_period_days" not in call_args or call_args.get("trial_period_days") == 0

    @pytest.mark.asyncio
    async def test_create_subscription_all_tiers_use_correct_price_ids(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test that all tiers use correct price IDs from config."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        tiers_to_test = [
            (SubscriptionTier.GOLD, "price_gold_ai_labels", "price_gold_human_audits", "price_gold_platform_fee"),
            (SubscriptionTier.SILVER, "price_silver_ai_labels", "price_silver_human_audits", "price_silver_platform_fee"),
            (SubscriptionTier.BRONZE, "price_bronze_ai_labels", "price_bronze_human_audits", "price_bronze_platform_fee")
        ]

        for tier, ai_price, audit_price, platform_price in tiers_to_test:
            with patch('stripe.Subscription.create') as mock_create:
                mock_create.return_value = mock_stripe_subscription

                # Act
                await subscription_service.create_subscription(
                    tenant_id=f"tenant_{tier.value}",
                    stripe_customer_id=f"cus_{tier.value}",
                    tier=tier,
                    db_session=mock_db_session
                )

                # Assert - Correct price IDs used
                call_args = mock_create.call_args[1]
                price_ids = [item["price"] for item in call_args["items"]]
                assert ai_price in price_ids
                assert audit_price in price_ids
                assert platform_price in price_ids


# ============================================================================
# Test Class: Protocol Compliance
# ============================================================================

class TestSubscriptionServiceProtocol:
    """Test suite for SubscriptionServiceProtocol compliance."""

    def test_subscription_service_implements_protocol(self, subscription_service):
        """Test that SubscriptionService implements SubscriptionServiceProtocol."""
        assert isinstance(subscription_service, SubscriptionServiceProtocol)

    def test_subscription_service_has_initialize_method(self, subscription_service):
        """Test that service has initialize method."""
        assert hasattr(subscription_service, 'initialize')
        assert callable(subscription_service.initialize)

    def test_subscription_service_has_create_subscription_method(self, subscription_service):
        """Test that service has create_subscription method."""
        assert hasattr(subscription_service, 'create_subscription')
        assert callable(subscription_service.create_subscription)


# ============================================================================
# Test Class: Data Transformation
# ============================================================================

class TestSubscriptionDataTransformation:
    """Test suite for data transformation helpers."""

    @pytest.mark.asyncio
    async def test_stripe_subscription_to_data_transformation(
        self,
        subscription_service,
        sample_api_key,
        mock_stripe_subscription,
        mock_db_session
    ):
        """Test transformation from Stripe subscription to SubscriptionData."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        with patch('stripe.Subscription.create') as mock_create:
            mock_create.return_value = mock_stripe_subscription

            # Act
            result = await subscription_service.create_subscription(
                tenant_id="tenant_001",
                stripe_customer_id="cus_001",
                tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

            # Assert - SubscriptionData structure
            assert isinstance(result, dict)
            assert "tenant_id" in result
            assert "stripe_subscription_id" in result
            assert "stripe_customer_id" in result
            assert "status" in result
            assert "tier" in result
            assert "cancel_at_period_end" in result
            assert isinstance(result["cancel_at_period_end"], bool)


# ============================================================================
# Test Class: Subscription Tier Update - P3-002
# ============================================================================

class TestSubscriptionTierUpdate:
    """Test suite for subscription tier updates (P3-002)."""

    @pytest.mark.asyncio
    async def test_update_tier_bronze_to_silver(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test upgrading subscription from Bronze to Silver tier."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_bronze_001"

        # Mock current subscription (Bronze tier)
        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {
                "data": [
                    {
                        "id": "si_item1",
                        "price": {"id": "price_bronze_ai_labels", "type": "recurring"}
                    },
                    {
                        "id": "si_item2",
                        "price": {"id": "price_bronze_human_audits", "type": "recurring"}
                    },
                    {
                        "id": "si_item3",
                        "price": {"id": "price_bronze_platform_fee", "type": "recurring"}
                    }
                ]
            }
        }

        # Mock updated subscription (Silver tier)
        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels", "type": "recurring"}},
                    {"price": {"id": "price_silver_human_audits", "type": "recurring"}},
                    {"price": {"id": "price_silver_platform_fee", "type": "recurring"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                result = await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=mock_db_session
                )

                # Assert - Stripe API called
                mock_retrieve.assert_called_once_with(subscription_id)
                mock_modify.assert_called_once()

                # Assert - Modify called with correct parameters
                call_args = mock_modify.call_args
                assert call_args[0][0] == subscription_id
                modify_params = call_args[1]
                assert "items" in modify_params
                assert modify_params["proration_behavior"] == "create_prorations"

                # Assert - Price IDs updated to Silver tier
                items = modify_params["items"]
                price_ids = {item["price"] for item in items}
                assert "price_silver_ai_labels" in price_ids
                assert "price_silver_human_audits" in price_ids
                assert "price_silver_platform_fee" in price_ids

                # Assert - Return value
                assert result["stripe_subscription_id"] == subscription_id
                assert result["tier"] == "silver"

    @pytest.mark.asyncio
    async def test_update_tier_silver_to_gold(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test upgrading subscription from Silver to Gold tier."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_silver_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_silver_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_silver_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "items": {
                "data": [
                    {"price": {"id": "price_gold_ai_labels"}},
                    {"price": {"id": "price_gold_human_audits"}},
                    {"price": {"id": "price_gold_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                result = await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.GOLD,
                    db_session=mock_db_session
                )

                # Assert - Price IDs updated to Gold tier
                call_args = mock_modify.call_args
                modify_params = call_args[1]
                items = modify_params["items"]
                price_ids = {item["price"] for item in items}
                assert "price_gold_ai_labels" in price_ids
                assert "price_gold_human_audits" in price_ids
                assert "price_gold_platform_fee" in price_ids

                # Assert - Return value
                assert result["tier"] == "gold"

    @pytest.mark.asyncio
    async def test_update_tier_gold_to_silver_downgrade(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test downgrading subscription from Gold to Silver tier."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_gold_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_gold_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_gold_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_gold_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels"}},
                    {"price": {"id": "price_silver_human_audits"}},
                    {"price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                result = await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=mock_db_session
                )

                # Assert - Price IDs updated to Silver tier
                call_args = mock_modify.call_args
                modify_params = call_args[1]
                items = modify_params["items"]
                price_ids = {item["price"] for item in items}
                assert "price_silver_ai_labels" in price_ids
                assert "price_silver_human_audits" in price_ids
                assert "price_silver_platform_fee" in price_ids

                # Assert - Return value
                assert result["tier"] == "silver"

    @pytest.mark.asyncio
    async def test_update_tier_same_tier_noop(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test updating to the same tier (should be a no-op)."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_gold_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_gold_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_gold_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_gold_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            # Act
            result = await subscription_service.update_subscription_tier(
                stripe_subscription_id=subscription_id,
                new_tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

            # Assert - Should not call modify (same tier)
            # Just return current subscription data
            assert result["tier"] == "gold"
            assert result["stripe_subscription_id"] == subscription_id

    @pytest.mark.asyncio
    async def test_update_tier_without_db_session(
        self,
        subscription_service,
        sample_api_key
    ):
        """Test tier update without database session (optional persistence)."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_bronze_002"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels"}},
                    {"price": {"id": "price_silver_human_audits"}},
                    {"price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                result = await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=None
                )

                # Assert - Still returns subscription data
                assert result["tier"] == "silver"


class TestSubscriptionTierUpdateErrorHandling:
    """Test suite for tier update error handling."""

    @pytest.mark.asyncio
    async def test_update_tier_not_initialized(
        self,
        subscription_service,
        mock_db_session
    ):
        """Test that tier update fails if service not initialized."""
        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.update_subscription_tier(
                stripe_subscription_id="sub_001",
                new_tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_tier_stripe_api_error(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test handling of Stripe API errors during tier update."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_error_001"

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.side_effect = stripe.error.InvalidRequestError(
                "No such subscription",
                "subscription"
            )

            # Act & Assert
            with pytest.raises(StripeAPIError) as exc_info:
                await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.GOLD,
                    db_session=mock_db_session
                )

            assert "Failed to update subscription tier" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_tier_modify_fails(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test handling of Stripe modify API errors."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_modify_error_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.side_effect = stripe.error.APIError("API connection failed")

                # Act & Assert
                with pytest.raises(StripeAPIError):
                    await subscription_service.update_subscription_tier(
                        stripe_subscription_id=subscription_id,
                        new_tier=SubscriptionTier.GOLD,
                        db_session=mock_db_session
                    )


# ============================================================================
# Test Class: Subscription Cancellation - P3-002
# ============================================================================

class TestSubscriptionCancellation:
    """Test suite for subscription cancellation (P3-002)."""

    @pytest.mark.asyncio
    async def test_cancel_subscription_immediate(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test immediate subscription cancellation (at_period_end=False)."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_cancel_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {"data": []}
        }

        canceled_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "canceled",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.delete') as mock_delete:
                mock_delete.return_value = canceled_subscription

                # Act
                result = await subscription_service.cancel_subscription(
                    stripe_subscription_id=subscription_id,
                    at_period_end=False,
                    db_session=mock_db_session
                )

                # Assert - Stripe delete called
                mock_retrieve.assert_called_once_with(subscription_id)
                mock_delete.assert_called_once_with(subscription_id)

                # Assert - Return value
                assert result["stripe_subscription_id"] == subscription_id
                assert result["status"] == "canceled"

    @pytest.mark.asyncio
    async def test_cancel_subscription_at_period_end(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test canceling subscription at period end (at_period_end=True)."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_cancel_period_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {"data": []}
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": True,
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                result = await subscription_service.cancel_subscription(
                    stripe_subscription_id=subscription_id,
                    at_period_end=True,
                    db_session=mock_db_session
                )

                # Assert - Stripe modify called
                mock_modify.assert_called_once()

                # Assert - Modify called with correct parameters
                call_args = mock_modify.call_args
                assert call_args[0][0] == subscription_id
                modify_params = call_args[1]
                assert modify_params["cancel_at_period_end"] is True

                # Assert - Return value
                assert result["stripe_subscription_id"] == subscription_id
                assert result["cancel_at_period_end"] is True
                assert result["status"] == "active"  # Still active until period end

    @pytest.mark.asyncio
    async def test_cancel_subscription_without_db_session(
        self,
        subscription_service,
        sample_api_key
    ):
        """Test cancellation without database session."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_cancel_no_db_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {"data": []}
        }

        canceled_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "canceled",
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.delete') as mock_delete:
                mock_delete.return_value = canceled_subscription

                # Act
                result = await subscription_service.cancel_subscription(
                    stripe_subscription_id=subscription_id,
                    at_period_end=False,
                    db_session=None
                )

                # Assert - Still returns subscription data
                assert result["status"] == "canceled"


class TestSubscriptionCancellationErrorHandling:
    """Test suite for cancellation error handling."""

    @pytest.mark.asyncio
    async def test_cancel_subscription_not_initialized(
        self,
        subscription_service,
        mock_db_session
    ):
        """Test that cancellation fails if service not initialized."""
        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.cancel_subscription(
                stripe_subscription_id="sub_001",
                at_period_end=False,
                db_session=mock_db_session
            )

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_subscription_invalid_id(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test handling of invalid subscription ID."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.side_effect = stripe.error.InvalidRequestError(
                "No such subscription",
                "subscription"
            )

            # Act & Assert
            with pytest.raises(StripeAPIError):
                await subscription_service.cancel_subscription(
                    stripe_subscription_id="sub_invalid_001",
                    at_period_end=False,
                    db_session=mock_db_session
                )

    @pytest.mark.asyncio
    async def test_cancel_subscription_delete_fails(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test handling of Stripe delete API errors."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_delete_error_001"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.delete') as mock_delete:
                mock_delete.side_effect = stripe.error.APIError("API connection failed")

                # Act & Assert
                with pytest.raises(StripeAPIError):
                    await subscription_service.cancel_subscription(
                        stripe_subscription_id=subscription_id,
                        at_period_end=False,
                        db_session=mock_db_session
                    )


class TestSubscriptionEdgeCases:
    """Test suite for edge cases in tier updates and cancellations."""

    @pytest.mark.asyncio
    async def test_update_tier_already_canceled_subscription(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test updating tier on already canceled subscription."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_canceled_001"

        canceled_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "canceled",
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = canceled_subscription

            # Act & Assert
            with pytest.raises(StripeServiceError) as exc_info:
                await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.GOLD,
                    db_session=mock_db_session
                )

            assert "canceled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_already_canceled_subscription(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test canceling an already canceled subscription."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_already_canceled_001"

        canceled_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "canceled",
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = canceled_subscription

            # Act & Assert
            with pytest.raises(StripeServiceError) as exc_info:
                await subscription_service.cancel_subscription(
                    stripe_subscription_id=subscription_id,
                    at_period_end=False,
                    db_session=mock_db_session
                )

            assert "canceled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_tier_with_trial_subscription(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test updating tier on subscription with active trial."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_trial_001"

        trial_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "trialing",
            "trial_start": int(datetime.now(timezone.utc).timestamp()),
            "trial_end": int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp()),
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "trialing",
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels"}},
                    {"price": {"id": "price_silver_human_audits"}},
                    {"price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = trial_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                result = await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=mock_db_session
                )

                # Assert - Should allow tier update during trial
                assert result["tier"] == "silver"
                assert result["status"] == "trialing"


# ============================================================================
# Test Class: Subscription ID Validation - Security
# ============================================================================

class TestSubscriptionIDValidation:
    """Test suite for subscription ID format validation (P3-002 security fixes)."""

    @pytest.mark.asyncio
    async def test_update_subscription_invalid_format_empty_string(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that update_subscription_tier rejects empty subscription ID."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.update_subscription_tier(
                stripe_subscription_id="",
                new_tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

        assert "cannot be empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_subscription_invalid_format_not_sub_prefix(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that update_subscription_tier rejects ID without 'sub_' prefix."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.update_subscription_tier(
                stripe_subscription_id="invalid_id_123",
                new_tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

        assert "must start with 'sub_'" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_subscription_invalid_format_too_short(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that update_subscription_tier rejects ID shorter than 10 characters."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.update_subscription_tier(
                stripe_subscription_id="sub_123",
                new_tier=SubscriptionTier.GOLD,
                db_session=mock_db_session
            )

        assert "at least 10 characters" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_subscription_invalid_format(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that cancel_subscription rejects invalid format ID."""
        # Arrange
        await subscription_service.initialize(sample_api_key)

        # Act & Assert
        with pytest.raises(StripeServiceError) as exc_info:
            await subscription_service.cancel_subscription(
                stripe_subscription_id="invalid_format",
                at_period_end=False,
                db_session=mock_db_session
            )

        assert "must start with 'sub_'" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_subscription_valid_format_works(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that valid subscription ID format passes validation."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_valid_abc_123_xyz"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels"}},
                    {"price": {"id": "price_silver_human_audits"}},
                    {"price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act - Should not raise validation error
                result = await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=mock_db_session
                )

                # Assert
                assert result["tier"] == "silver"


# ============================================================================
# Test Class: Authorization and Cross-Tenant Access - Security
# ============================================================================

class TestCrossTenantAuthorization:
    """Test suite for cross-tenant authorization (P3-002 security fixes)."""

    def _create_mock_db_session_with_subscription(self, tenant_id: str):
        """Helper to create a mock DB session that returns a subscription."""
        session = AsyncMock(spec=AsyncSession)
        session.add = Mock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        # Create a mock subscription with specific tenant_id
        mock_subscription = Mock()
        mock_subscription.tenant_id = tenant_id
        mock_subscription.stripe_subscription_id = "sub_auth_001"
        mock_subscription.stripe_customer_id = "cus_001"
        mock_subscription.status = "active"
        mock_subscription.tier = "bronze"

        # Mock execute to return a result with the subscription
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_subscription)
        session.execute = AsyncMock(return_value=mock_result)

        return session, mock_subscription

    @pytest.mark.asyncio
    async def test_update_subscription_cross_tenant_denied(
        self,
        subscription_service,
        sample_api_key
    ):
        """Test that cross-tenant tier update is denied."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_auth_001"

        # Mock DB session for tenant "tenant_001"
        db_session, db_subscription = self._create_mock_db_session_with_subscription("tenant_001")

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            # Act & Assert - Try to update from different tenant
            with pytest.raises(StripeServiceError) as exc_info:
                await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.GOLD,
                    db_session=db_session,
                    requesting_tenant_id="tenant_002"  # Different tenant!
                )

            assert "access denied" in str(exc_info.value).lower() or "ownership" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_subscription_cross_tenant_with_different_tenant_id(
        self,
        subscription_service,
        sample_api_key
    ):
        """Test that update fails when requesting tenant doesn't match subscription owner."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_auth_002"

        # Mock DB session for tenant "original_tenant"
        db_session, db_subscription = self._create_mock_db_session_with_subscription("original_tenant")

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            # Act & Assert
            with pytest.raises(StripeServiceError) as exc_info:
                await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=db_session,
                    requesting_tenant_id="attacker_tenant"
                )

            assert "access denied" in str(exc_info.value).lower() or "ownership" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_subscription_cross_tenant_denied(
        self,
        subscription_service,
        sample_api_key
    ):
        """Test that cross-tenant cancellation is denied."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_auth_003"

        # Mock DB session for tenant "tenant_owner"
        db_session, db_subscription = self._create_mock_db_session_with_subscription("tenant_owner")

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            # Act & Assert - Try to cancel from different tenant
            with pytest.raises(StripeServiceError) as exc_info:
                await subscription_service.cancel_subscription(
                    stripe_subscription_id=subscription_id,
                    at_period_end=False,
                    db_session=db_session,
                    requesting_tenant_id="tenant_attacker"
                )

            assert "access denied" in str(exc_info.value).lower() or "ownership" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_subscription_same_tenant_allowed(
        self,
        subscription_service,
        sample_api_key
    ):
        """Test that same-tenant tier update is allowed."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_auth_004"

        # Mock DB session for tenant "tenant_same"
        db_session, db_subscription = self._create_mock_db_session_with_subscription("tenant_same")

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels"}},
                    {"price": {"id": "price_silver_human_audits"}},
                    {"price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act - Same tenant, should be allowed
                result = await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=db_session,
                    requesting_tenant_id="tenant_same"  # Same tenant!
                )

                # Assert
                assert result["tier"] == "silver"


# ============================================================================
# Test Class: Idempotency Key Support - Security
# ============================================================================

class TestIdempotencyKeySupport:
    """Test suite for idempotency key support (P3-002 security fixes)."""

    @pytest.mark.asyncio
    async def test_update_subscription_idempotent_with_key(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that idempotency key is passed to Stripe API for tier update."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_idem_001"
        idempotency_key = "idemp_key_12345"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels"}},
                    {"price": {"id": "price_silver_human_audits"}},
                    {"price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=mock_db_session,
                    idempotency_key=idempotency_key
                )

                # Assert - Idempotency key was passed to Stripe API
                call_args = mock_modify.call_args
                modify_params = call_args[1]
                assert modify_params["idempotency_key"] == idempotency_key

    @pytest.mark.asyncio
    async def test_update_subscription_without_idempotency_key(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that tier update works without idempotency key (optional)."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_idem_002"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"id": "si_item1", "price": {"id": "price_bronze_ai_labels"}},
                    {"id": "si_item2", "price": {"id": "price_bronze_human_audits"}},
                    {"id": "si_item3", "price": {"id": "price_bronze_platform_fee"}}
                ]
            }
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "items": {
                "data": [
                    {"price": {"id": "price_silver_ai_labels"}},
                    {"price": {"id": "price_silver_human_audits"}},
                    {"price": {"id": "price_silver_platform_fee"}}
                ]
            }
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act - No idempotency key provided
                await subscription_service.update_subscription_tier(
                    stripe_subscription_id=subscription_id,
                    new_tier=SubscriptionTier.SILVER,
                    db_session=mock_db_session
                )

                # Assert - Should work without idempotency key
                mock_modify.assert_called_once()
                call_args = mock_modify.call_args
                modify_params = call_args[1]
                assert "idempotency_key" not in modify_params

    @pytest.mark.asyncio
    async def test_cancel_subscription_idempotent(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that idempotency key is passed to Stripe API for cancellation."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_idem_003"
        idempotency_key = "idemp_cancel_123"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {"data": []}
        }

        canceled_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "canceled",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.delete') as mock_delete:
                mock_delete.return_value = canceled_subscription

                # Act
                await subscription_service.cancel_subscription(
                    stripe_subscription_id=subscription_id,
                    at_period_end=False,
                    db_session=mock_db_session,
                    idempotency_key=idempotency_key
                )

                # Assert - Idempotency key was passed to Stripe API
                call_args = mock_delete.call_args
                delete_params = call_args[1]
                assert delete_params["idempotency_key"] == idempotency_key

    @pytest.mark.asyncio
    async def test_cancel_subscription_at_period_end_with_idempotency(
        self,
        subscription_service,
        sample_api_key,
        mock_db_session
    ):
        """Test that idempotency key works for cancel-at-period-end."""
        # Arrange
        await subscription_service.initialize(sample_api_key)
        subscription_id = "sub_idem_004"
        idempotency_key = "idemp_period_123"

        current_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "items": {"data": []}
        }

        updated_subscription = {
            "id": subscription_id,
            "customer": "cus_001",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": True,
            "items": {"data": []}
        }

        with patch('stripe.Subscription.retrieve') as mock_retrieve:
            mock_retrieve.return_value = current_subscription

            with patch('stripe.Subscription.modify') as mock_modify:
                mock_modify.return_value = updated_subscription

                # Act
                await subscription_service.cancel_subscription(
                    stripe_subscription_id=subscription_id,
                    at_period_end=True,
                    db_session=mock_db_session,
                    idempotency_key=idempotency_key
                )

                # Assert - Idempotency key was passed to Stripe modify API
                call_args = mock_modify.call_args
                modify_params = call_args[1]
                assert modify_params["idempotency_key"] == idempotency_key
                assert modify_params["cancel_at_period_end"] is True

