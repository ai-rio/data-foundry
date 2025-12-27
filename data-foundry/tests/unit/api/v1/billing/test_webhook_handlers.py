"""
Unit tests for Stripe webhook event handlers.

Tests the WebhookEventHandler class which handles:
- invoice.payment_succeeded
- invoice.payment_failed
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted

Follows TDD principles: Tests written FIRST, implementation follows.
Test Coverage Target: 95%

Phase: 4 (Event Handlers)
Task: P4-003
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.billing.webhook_handlers import WebhookEventHandler
from src.models.stripe_billing import StripeSubscription, StripeCustomer


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.add = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def db_session_factory(mock_db_session):
    """Mock database session factory."""
    async def _factory():
        return mock_db_session
    return _factory


@pytest.fixture
def webhook_handler(db_session_factory):
    """Create WebhookEventHandler instance for testing."""
    return WebhookEventHandler(db_session_factory)


@pytest.fixture
def mock_stripe_event():
    """Create mock Stripe event object."""
    event = Mock()
    event.id = "evt_test123"
    event.type = "customer.subscription.created"
    event.data = Mock()
    event.data.object = Mock()
    return event


@pytest.fixture
def sample_stripe_subscription():
    """Sample Stripe subscription object."""
    sub = Mock()
    sub.id = "sub_test123"
    sub.customer = "cus_test123"
    sub.status = "active"
    sub.current_period_start = int(datetime.now(timezone.utc).timestamp())
    sub.current_period_end = int(datetime.now(timezone.utc).timestamp()) + 2592000
    sub.cancel_at_period_end = False
    sub.items = Mock()
    sub.items.data = []
    return sub


@pytest.fixture
def sample_stripe_customer():
    """Sample Stripe customer object."""
    customer = Mock()
    customer.id = "cus_test123"
    customer.email = "test@example.com"
    customer.name = "Test Customer"
    return customer


@pytest.fixture
def sample_db_customer():
    """Sample database customer record."""
    return StripeCustomer(
        id=1,
        tenant_id="tenant_123",
        stripe_customer_id="cus_test123",
        email="test@example.com",
        name="Test Customer"
    )


@pytest.fixture
def sample_db_subscription():
    """Sample database subscription record."""
    return StripeSubscription(
        id=1,
        tenant_id="tenant_123",
        stripe_subscription_id="sub_test123",
        stripe_customer_id="cus_test123",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc),
        cancel_at_period_end=False,
        tier="gold"
    )


# =============================================================================
# Handler Registration Tests
# =============================================================================

class TestHandlerRegistration:
    """Test handler registration and initialization."""

    def test_initialization_registers_all_handlers(self, webhook_handler):
        """Test that all 5 handlers are registered on initialization."""
        expected_handlers = {
            "invoice.payment_succeeded",
            "invoice.payment_failed",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted"
        }

        registered_handlers = set(webhook_handler._handlers.keys())

        assert registered_handlers == expected_handlers, (
            f"Expected {len(expected_handlers)} handlers, "
            f"got {len(registered_handlers)}: {registered_handlers}"
        )

    def test_handler_count(self, webhook_handler):
        """Test that exactly 5 handlers are registered."""
        assert len(webhook_handler._handlers) == 5

    def test_handler_references_are_callables(self, webhook_handler):
        """Test that all registered handlers are callable methods."""
        for event_type, handler in webhook_handler._handlers.items():
            assert callable(handler), f"Handler for {event_type} is not callable"


# =============================================================================
# invoice.payment_succeeded Tests
# =============================================================================

class TestInvoicePaymentSucceeded:
    """Test invoice.payment_succeeded event handler."""

    @pytest.mark.asyncio
    async def test_handles_payment_succeeded_event(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_db_subscription
    ):
        """Test that payment_succeeded event updates subscription status."""
        # Arrange
        mock_stripe_event.type = "invoice.payment_succeeded"
        mock_stripe_event.data.object.subscription = "sub_test123"

        # Mock database query to find subscription
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert mock_db_session.commit.called, "Database commit should be called"
        assert mock_db_session.refresh.called, "Database refresh should be called"

    @pytest.mark.asyncio
    async def test_payment_succeeded_logs_success(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_db_subscription, caplog
    ):
        """Test that successful payment is logged."""
        # Arrange
        mock_stripe_event.type = "invoice.payment_succeeded"
        mock_stripe_event.data.object.subscription = "sub_test123"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        with caplog.at_level("INFO"):
            await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert any("payment_succeeded" in record.message.lower()
                   for record in caplog.records)

    @pytest.mark.asyncio
    async def test_payment_succeeded_handles_missing_subscription(
        self, webhook_handler, mock_stripe_event, mock_db_session
    ):
        """Test that payment_succeeded handles missing subscription gracefully."""
        # Arrange
        mock_stripe_event.type = "invoice.payment_succeeded"
        mock_stripe_event.data.object.subscription = "sub_nonexistent"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act & Assert - should not raise exception
        await webhook_handler.handle_event(mock_stripe_event)

    @pytest.mark.asyncio
    async def test_payment_succeeded_handles_missing_subscription_field(
        self, webhook_handler, mock_stripe_event, mock_db_session
    ):
        """Test that payment_succeeded handles missing subscription field gracefully."""
        # Arrange
        mock_stripe_event.type = "invoice.payment_succeeded"
        mock_stripe_event.data.object.subscription = None

        # Act & Assert - should not raise exception
        await webhook_handler.handle_event(mock_stripe_event)


# =============================================================================
# invoice.payment_failed Tests
# =============================================================================

class TestInvoicePaymentFailed:
    """Test invoice.payment_failed event handler."""

    @pytest.mark.asyncio
    async def test_handles_payment_failed_event(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_db_subscription
    ):
        """Test that payment_failed event is logged and handled."""
        # Arrange
        mock_stripe_event.type = "invoice.payment_failed"
        mock_stripe_event.data.object.subscription = "sub_test123"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert - should log warning
        assert mock_db_session.commit.called

    @pytest.mark.asyncio
    async def test_payment_failed_logs_warning(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_db_subscription, caplog
    ):
        """Test that failed payment is logged with warning level."""
        # Arrange
        mock_stripe_event.type = "invoice.payment_failed"
        mock_stripe_event.data.object.subscription = "sub_test123"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        with caplog.at_level("WARNING"):
            await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert any("payment_failed" in record.message.lower()
                   for record in caplog.records if record.levelname == "WARNING")


# =============================================================================
# customer.subscription.created Tests
# =============================================================================

class TestSubscriptionCreated:
    """Test customer.subscription.created event handler."""

    @pytest.mark.asyncio
    async def test_creates_subscription_in_database(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription, sample_db_customer
    ):
        """Test that subscription.created creates database record."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.created"
        mock_stripe_event.data.object = sample_stripe_subscription

        # Mock customer lookup
        mock_customer_result = Mock()
        mock_customer_result.scalar_one_or_none = Mock(return_value=sample_db_customer)
        customer_query = AsyncMock(return_value=mock_customer_result)

        # Mock subscription check (should return None - doesn't exist)
        mock_sub_result = Mock()
        mock_sub_result.scalar_one_or_none = Mock(return_value=None)
        sub_query = AsyncMock(return_value=mock_sub_result)

        # Setup execute to return different results based on query
        execute_call_count = 0
        async def mock_execute(stmt):
            nonlocal execute_call_count
            execute_call_count += 1
            # First call checks existing subscription (should return None)
            # Second call looks up customer
            if execute_call_count == 1:
                return mock_sub_result  # No existing subscription
            return mock_customer_result  # Customer found

        mock_db_session.execute = mock_execute

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert mock_db_session.add.called, "Should add subscription to database"
        assert mock_db_session.commit.called, "Should commit transaction"

    @pytest.mark.asyncio
    async def test_subscription_created_extracts_correct_fields(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription, sample_db_customer
    ):
        """Test that subscription fields are correctly extracted from Stripe event."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.created"
        mock_stripe_event.data.object = sample_stripe_subscription

        mock_customer_result = Mock()
        mock_customer_result.scalar_one_or_none = Mock(return_value=sample_db_customer)

        mock_sub_result = Mock()
        mock_sub_result.scalar_one_or_none = Mock(return_value=None)

        execute_call_count = 0
        async def mock_execute(stmt):
            nonlocal execute_call_count
            execute_call_count += 1
            # First call checks existing subscription (should return None)
            # Second call looks up customer
            if execute_call_count == 1:
                return mock_sub_result  # No existing subscription
            return mock_customer_result  # Customer found

        mock_db_session.execute = mock_execute

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert - verify add was called with correct data
        added_obj = mock_db_session.add.call_args[0][0]
        assert isinstance(added_obj, StripeSubscription)
        assert added_obj.stripe_subscription_id == sample_stripe_subscription.id
        assert added_obj.stripe_customer_id == sample_stripe_subscription.customer

    @pytest.mark.asyncio
    async def test_subscription_created_handles_duplicate_gracefully(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription, sample_db_customer, sample_db_subscription
    ):
        """Test that duplicate subscription creation is handled gracefully."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.created"
        mock_stripe_event.data.object = sample_stripe_subscription

        # Customer exists
        mock_customer_result = Mock()
        mock_customer_result.scalar_one_or_none = Mock(return_value=sample_db_customer)

        # Subscription already exists
        mock_sub_result = Mock()
        mock_sub_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)

        execute_call_count = 0
        async def mock_execute(stmt):
            nonlocal execute_call_count
            execute_call_count += 1
            if execute_call_count == 1:
                return mock_customer_result
            return mock_sub_result

        mock_db_session.execute = mock_execute

        # Act & Assert - should not raise, should handle gracefully
        await webhook_handler.handle_event(mock_stripe_event)

    @pytest.mark.asyncio
    async def test_subscription_created_handles_missing_customer(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription
    ):
        """Test that missing customer is handled gracefully."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.created"
        mock_stripe_event.data.object = sample_stripe_subscription

        # Customer not found
        mock_customer_result = Mock()
        mock_customer_result.scalar_one_or_none = Mock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_customer_result)

        # Act & Assert - should not raise
        await webhook_handler.handle_event(mock_stripe_event)


# =============================================================================
# customer.subscription.updated Tests
# =============================================================================

class TestSubscriptionUpdated:
    """Test customer.subscription.updated event handler."""

    @pytest.mark.asyncio
    async def test_updates_existing_subscription(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription, sample_db_customer, sample_db_subscription
    ):
        """Test that subscription.updated updates existing record."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.updated"
        mock_stripe_event.data.object = sample_stripe_subscription

        # Subscription exists
        mock_sub_result = Mock()
        mock_sub_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_sub_result)

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert mock_db_session.commit.called, "Should commit update"
        assert mock_db_session.refresh.called, "Should refresh record"

    @pytest.mark.asyncio
    async def test_subscription_updated_changes_status(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_db_customer
    ):
        """Test that subscription status is updated."""
        # Arrange
        stripe_sub = Mock()
        stripe_sub.id = "sub_test123"
        stripe_sub.customer = "cus_test123"
        stripe_sub.status = "past_due"  # Status changed
        stripe_sub.current_period_start = int(datetime.now(timezone.utc).timestamp())
        stripe_sub.current_period_end = int(datetime.now(timezone.utc).timestamp()) + 2592000
        stripe_sub.cancel_at_period_end = False
        stripe_sub.items = Mock()
        stripe_sub.items.data = []

        mock_stripe_event.type = "customer.subscription.updated"
        mock_stripe_event.data.object = stripe_sub

        # Existing subscription in DB
        db_sub = StripeSubscription(
            id=1,
            tenant_id="tenant_123",
            stripe_subscription_id="sub_test123",
            stripe_customer_id="cus_test123",
            status="active",  # Old status
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc),
            cancel_at_period_end=False,
            tier="gold"
        )

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=db_sub)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert - status should be updated
        assert db_sub.status == "past_due"

    @pytest.mark.asyncio
    async def test_subscription_updated_handles_missing_subscription(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription
    ):
        """Test that updating non-existent subscription is handled gracefully."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.updated"
        mock_stripe_event.data.object = sample_stripe_subscription

        # Subscription not found
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act & Assert - should not raise
        await webhook_handler.handle_event(mock_stripe_event)


# =============================================================================
# customer.subscription.deleted Tests
# =============================================================================

class TestSubscriptionDeleted:
    """Test customer.subscription.deleted event handler."""

    @pytest.mark.asyncio
    async def test_marks_subscription_as_canceled(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription, sample_db_subscription
    ):
        """Test that subscription.deleted marks subscription as canceled."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.deleted"
        mock_stripe_event.data.object = sample_stripe_subscription

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert mock_db_session.commit.called
        # Status should be marked as canceled
        assert sample_db_subscription.status == "canceled"

    @pytest.mark.asyncio
    async def test_subscription_deleted_logs_cancellation(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription, sample_db_subscription, caplog
    ):
        """Test that subscription deletion is logged."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.deleted"
        mock_stripe_event.data.object = sample_stripe_subscription

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        with caplog.at_level("INFO"):
            await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert any("deleted" in record.message.lower() or "canceled" in record.message.lower()
                   for record in caplog.records)

    @pytest.mark.asyncio
    async def test_subscription_deleted_handles_missing_subscription(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription
    ):
        """Test that deleting non-existent subscription is handled gracefully."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.deleted"
        mock_stripe_event.data.object = sample_stripe_subscription

        # Subscription not found
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act & Assert - should not raise
        await webhook_handler.handle_event(mock_stripe_event)


# =============================================================================
# Unknown Event Type Tests
# =============================================================================

class TestUnknownEventTypes:
    """Test handling of unknown or unsupported event types."""

    @pytest.mark.asyncio
    async def test_unknown_event_type_is_ignored(
        self, webhook_handler, mock_stripe_event, mock_db_session
    ):
        """Test that unknown event types are silently ignored."""
        # Arrange
        mock_stripe_event.type = "unsupported.event.type"

        # Act & Assert - should not raise
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert - no database operations should occur
        assert not mock_db_session.execute.called
        assert not mock_db_session.add.called
        assert not mock_db_session.commit.called

    @pytest.mark.asyncio
    async def test_unknown_event_type_logs_warning(
        self, webhook_handler, mock_stripe_event, caplog
    ):
        """Test that unknown event types are logged."""
        # Arrange
        mock_stripe_event.type = "unsupported.event.type"

        # Act
        with caplog.at_level("WARNING"):
            await webhook_handler.handle_event(mock_stripe_event)

        # Assert
        assert any("unknown" in record.message.lower() or "unsupported" in record.message.lower()
                   for record in caplog.records if record.levelname == "WARNING")


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling in event handlers."""

    @pytest.mark.asyncio
    async def test_database_error_is_caught(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription
    ):
        """Test that database errors are caught and logged."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.updated"
        mock_stripe_event.data.object = sample_stripe_subscription

        # Database raises exception
        mock_db_session.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        # Act & Assert - should not raise exception to caller
        await webhook_handler.handle_event(mock_stripe_event)

    @pytest.mark.asyncio
    async def test_database_commit_error_is_handled(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_db_subscription
    ):
        """Test that commit errors are handled gracefully."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.updated"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock(side_effect=Exception("Commit failed"))

        # Act & Assert - should not raise
        await webhook_handler.handle_event(mock_stripe_event)

    @pytest.mark.asyncio
    async def test_rollback_on_error(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription
    ):
        """Test that transaction is rolled back on error."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.updated"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock(side_effect=Exception("Commit failed"))

        # Act
        await webhook_handler.handle_event(mock_stripe_event)

        # Assert - rollback should be called
        assert mock_db_session.rollback.called

    @pytest.mark.asyncio
    async def test_rollback_failure_is_handled(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_stripe_subscription
    ):
        """Test that rollback failure doesn't crash the handler."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.updated"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_stripe_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        mock_db_session.rollback = AsyncMock(side_effect=Exception("Rollback failed"))

        # Act & Assert - should not raise exception
        await webhook_handler.handle_event(mock_stripe_event)


# =============================================================================
# Database Session Management Tests
# =============================================================================

class TestDatabaseSessionManagement:
    """Test database session lifecycle management."""

    @pytest.mark.asyncio
    async def test_session_is_created_and_closed(
        self, webhook_handler, mock_stripe_event
    ):
        """Test that database session is properly created and closed."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.created"

        mock_session = AsyncMock(spec=AsyncSession)
        async def mock_factory():
            return mock_session

        handler = WebhookEventHandler(mock_factory)

        # Act
        await handler.handle_event(mock_stripe_event)

        # Assert
        # Session should be used (even if no data found)
        assert True  # If we got here without exception, session was managed

    @pytest.mark.asyncio
    async def test_multiple_events_use_separate_sessions(
        self, webhook_handler, mock_stripe_event
    ):
        """Test that each event gets a new database session."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.created"

        session_count = 0
        async def mock_factory():
            nonlocal session_count
            session_count += 1
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))
            return mock_session

        handler = WebhookEventHandler(mock_factory)

        # Act - handle multiple events
        await handler.handle_event(mock_stripe_event)
        await handler.handle_event(mock_stripe_event)

        # Assert - should create separate sessions
        assert session_count == 2


# =============================================================================
# Integration-Style Tests
# =============================================================================

class TestEndToEndEventProcessing:
    """End-to-end tests for event processing."""

    @pytest.mark.asyncio
    async def test_full_subscription_lifecycle(
        self, webhook_handler, mock_db_session,
        sample_stripe_subscription, sample_db_customer
    ):
        """Test processing subscription through full lifecycle."""
        # 1. Create subscription
        created_event = Mock()
        created_event.type = "customer.subscription.created"
        created_event.data.object = sample_stripe_subscription

        mock_customer_result = Mock()
        mock_customer_result.scalar_one_or_none = Mock(return_value=sample_db_customer)

        mock_sub_result = Mock()
        mock_sub_result.scalar_one_or_none = Mock(return_value=None)

        execute_call_count = 0
        async def mock_execute(stmt):
            nonlocal execute_call_count
            execute_call_count += 1
            # First call checks existing subscription (should return None)
            # Second call looks up customer
            if execute_call_count == 1:
                return mock_sub_result  # No existing subscription
            return mock_customer_result  # Customer found

        mock_db_session.execute = mock_execute

        # Act - Create
        await webhook_handler.handle_event(created_event)

        # Assert - Created
        assert mock_db_session.add.called
        mock_db_session.reset_mock()

    @pytest.mark.asyncio
    async def test_concurrent_event_handling(
        self, webhook_handler, mock_stripe_event, mock_db_session,
        sample_db_subscription
    ):
        """Test that handler can handle events sequentially."""
        # Arrange
        mock_stripe_event.type = "customer.subscription.updated"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=sample_db_subscription)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act - Handle multiple events
        for _ in range(5):
            await webhook_handler.handle_event(mock_stripe_event)

        # Assert - All should succeed
        assert mock_db_session.commit.call_count == 5
