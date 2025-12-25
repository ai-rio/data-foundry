"""
TDD tests for P1-001 Stripe billing critical fixes.

Uses RED-GREEN-REFACTOR cycle for each fix:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass tests
3. REFACTOR: Improve while maintaining green tests

Quality Gates:
- Security Score: >= 90% (currently 65%)
- Architecture Alignment: >= 90% (currently 72%)
- Test Coverage: >= 85% (currently 97% - PASS)
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

import pytest
from enum import Enum
from sqlalchemy import text
from unittest.mock import Mock, patch, AsyncMock


class TestEnumStatusClasses:
    """
    RED PHASE: Tests for enum status classes.

    These tests verify that:
    1. StripeSubscriptionStatus enum exists with correct values
    2. StripeMeterEventStatus enum exists with correct values
    3. Enums are properly defined as str, Enum types
    """

    def test_stripe_subscription_status_enum_exists(self):
        """
        Test that StripeSubscriptionStatus enum exists.

        Expected enum values:
        - ACTIVE
        - CANCELED
        - PAST_DUE
        - TRIALING
        - INCOMPLETE
        """
        from src.models.stripe_billing import StripeSubscriptionStatus

        # Verify it's an Enum
        assert issubclass(StripeSubscriptionStatus, Enum)

        # Verify all expected values exist
        expected_values = ['ACTIVE', 'CANCELED', 'PAST_DUE', 'TRIALING', 'INCOMPLETE']
        for value in expected_values:
            assert hasattr(StripeSubscriptionStatus, value), f"Missing value: {value}"

        # Verify enum values are strings
        for member in StripeSubscriptionStatus:
            assert isinstance(member.value, str), f"Enum value {member} should be string"

    def test_stripe_subscription_status_enum_values(self):
        """
        Test that StripeSubscriptionStatus enum has correct string values.

        Expected mappings:
        - ACTIVE -> 'active'
        - CANCELED -> 'canceled'
        - PAST_DUE -> 'past_due'
        - TRIALING -> 'trialing'
        - INCOMPLETE -> 'incomplete'
        """
        from src.models.stripe_billing import StripeSubscriptionStatus

        assert StripeSubscriptionStatus.ACTIVE.value == 'active'
        assert StripeSubscriptionStatus.CANCELED.value == 'canceled'
        assert StripeSubscriptionStatus.PAST_DUE.value == 'past_due'
        assert StripeSubscriptionStatus.TRIALING.value == 'trialing'
        assert StripeSubscriptionStatus.INCOMPLETE.value == 'incomplete'

    def test_stripe_meter_event_status_enum_exists(self):
        """
        Test that StripeMeterEventStatus enum exists.

        Expected enum values:
        - PENDING
        - SUCCEEDED
        - FAILED
        """
        from src.models.stripe_billing import StripeMeterEventStatus

        # Verify it's an Enum
        assert issubclass(StripeMeterEventStatus, Enum)

        # Verify all expected values exist
        expected_values = ['PENDING', 'SUCCEEDED', 'FAILED']
        for value in expected_values:
            assert hasattr(StripeMeterEventStatus, value), f"Missing value: {value}"

        # Verify enum values are strings
        for member in StripeMeterEventStatus:
            assert isinstance(member.value, str), f"Enum value {member} should be string"

    def test_stripe_meter_event_status_enum_values(self):
        """
        Test that StripeMeterEventStatus enum has correct string values.

        Expected mappings:
        - PENDING -> 'pending'
        - SUCCEEDED -> 'succeeded'
        - FAILED -> 'failed'
        """
        from src.models.stripe_billing import StripeMeterEventStatus

        assert StripeMeterEventStatus.PENDING.value == 'pending'
        assert StripeMeterEventStatus.SUCCEEDED.value == 'succeeded'
        assert StripeMeterEventStatus.FAILED.value == 'failed'


class TestMigrationConstraints:
    """
    RED PHASE: Tests for migration constraints and security features.

    These tests verify that the migration file includes:
    1. Foreign key constraints
    2. Row-Level Security (RLS)
    3. CHECK constraints
    4. Audit trail fields
    5. Composite indexes
    """

    def test_migration_file_exists(self):
        """Test that migration file exists and is readable."""
        migration_path = os.path.join(
            os.path.dirname(__file__), '../../../src/database/migrations/create_stripe_billing_tables.py'
        )
        assert os.path.exists(migration_path), "Migration file does not exist"

    def test_migration_includes_foreign_key_constraints(self):
        """Test that migration includes FK constraints to tenants table."""
        migration_path = os.path.join(
            os.path.dirname(__file__), '../../../src/database/migrations/create_stripe_billing_tables.py'
        )

        with open(migration_path, 'r') as f:
            content = f.read()

        # Check for FK constraint in stripe_subscriptions
        assert 'fk_stripe_subscriptions_tenant' in content, \
            "FK constraint fk_stripe_subscriptions_tenant not found in migration"
        assert 'FOREIGN KEY (tenant_id)' in content, \
            "FOREIGN KEY definition not found in migration"
        assert 'REFERENCES tenants(tenant_id)' in content, \
            "FK reference to tenants table not found"
        assert 'ON DELETE CASCADE' in content, \
            "ON DELETE CASCADE not found in migration"

    def test_migration_includes_row_level_security(self):
        """Test that migration enables RLS and creates tenant isolation policies."""
        migration_path = os.path.join(
            os.path.dirname(__file__), '../../../src/database/migrations/create_stripe_billing_tables.py'
        )

        with open(migration_path, 'r') as f:
            content = f.read()

        # Check for RLS enablement
        assert 'ENABLE ROW LEVEL SECURITY' in content, \
            "RLS enablement not found in migration"
        assert 'FORCE ROW LEVEL SECURITY' in content, \
            "RLS force not found in migration"

        # Check for tenant isolation policies
        assert 'tenant_isolation_stripe_subscriptions' in content, \
            "RLS policy for stripe_subscriptions not found"
        assert 'tenant_isolation_stripe_meter_events' in content, \
            "RLS policy for stripe_meter_events not found"
        assert 'current_setting(\'app.tenant_id\'' in content, \
            "Tenant isolation using app.tenant_id not found"

    def test_migration_includes_check_constraints(self):
        """Test that migration includes CHECK constraints for status validation."""
        migration_path = os.path.join(
            os.path.dirname(__file__), '../../../src/database/migrations/create_stripe_billing_tables.py'
        )

        with open(migration_path, 'r') as f:
            content = f.read()

        # Check for CHECK constraint on subscription status
        assert 'chk_stripe_subscriptions_status' in content, \
            "CHECK constraint for subscription status not found"
        assert "'active', 'canceled', 'past_due', 'trialing', 'incomplete'" in content, \
            "Valid subscription status values not found in CHECK constraint"

        # Check for CHECK constraint on meter event status
        assert 'chk_stripe_meter_events_status' in content, \
            "CHECK constraint for meter event status not found"
        assert "'pending', 'succeeded', 'failed'" in content, \
            "Valid meter event status values not found in CHECK constraint"

    def test_migration_includes_audit_trail_fields(self):
        """Test that migration includes created_by and updated_by fields."""
        migration_path = os.path.join(
            os.path.dirname(__file__), '../../../src/database/migrations/create_stripe_billing_tables.py'
        )

        with open(migration_path, 'r') as f:
            content = f.read()

        # Check for audit fields in stripe_subscriptions
        assert 'created_by VARCHAR(100)' in content, \
            "created_by field not found in migration"
        assert 'updated_by VARCHAR(100)' in content, \
            "updated_by field not found in migration"

    def test_migration_includes_composite_indexes(self):
        """Test that migration includes composite indexes on (tenant_id, status)."""
        migration_path = os.path.join(
            os.path.dirname(__file__), '../../../src/database/migrations/create_stripe_billing_tables.py'
        )

        with open(migration_path, 'r') as f:
            content = f.read()

        # Check for composite indexes
        assert 'idx_stripe_subscriptions_tenant_status' in content, \
            "Composite index for stripe_subscriptions not found"
        assert 'idx_stripe_meter_events_tenant_status' in content, \
            "Composite index for stripe_meter_events not found"
        assert 'ON stripe_subscriptions(tenant_id, status)' in content, \
            "Composite index definition for stripe_subscriptions incorrect"
        assert 'ON stripe_meter_events(tenant_id, status)' in content, \
            "Composite index definition for stripe_meter_events incorrect"


class TestAuditTrailFields:
    """
    RED PHASE: Tests for audit trail fields in models.

    These tests verify that:
    1. created_by field exists on both models
    2. updated_by field exists on both models
    """

    def test_audit_fields_stripe_subscriptions_model(self):
        """
        Test that StripeSubscription model has audit trail fields.

        Should have:
        - created_by: Optional[str]
        - updated_by: Optional[str]
        """
        from src.models.stripe_billing import StripeSubscription

        # Check for created_by field
        assert hasattr(StripeSubscription, 'created_by'), \
            "StripeSubscription missing created_by field"

        # Check for updated_by field
        assert hasattr(StripeSubscription, 'updated_by'), \
            "StripeSubscription missing updated_by field"

    def test_audit_fields_stripe_meter_events_model(self):
        """
        Test that StripeMeterEvent model has audit trail fields.

        Should have:
        - created_by: Optional[str]
        - updated_by: Optional[str]
        """
        from src.models.stripe_billing import StripeMeterEvent

        # Check for created_by field
        assert hasattr(StripeMeterEvent, 'created_by'), \
            "StripeMeterEvent missing created_by field"

        # Check for updated_by field
        assert hasattr(StripeMeterEvent, 'updated_by'), \
            "StripeMeterEvent missing updated_by field"


class TestEnumUsageInModels:
    """
    Tests that enums are properly used in models.
    """

    def test_subscription_model_uses_enum(self):
        """Test that StripeSubscription.status field uses StripeSubscriptionStatus enum."""
        from src.models.stripe_billing import StripeSubscription, StripeSubscriptionStatus
        from sqlalchemy import inspect

        # Get the type annotation for status field
        # Note: SQLModel fields are stored differently, so we check if we can import and use it
        subscription = StripeSubscription(
            tenant_id="test_tenant",
            stripe_subscription_id="sub_test",
            stripe_customer_id="cus_test",
            status=StripeSubscriptionStatus.ACTIVE
        )

        assert subscription.status == StripeSubscriptionStatus.ACTIVE
        assert subscription.status.value == 'active'

    def test_meter_event_model_uses_enum(self):
        """Test that StripeMeterEvent.status field uses StripeMeterEventStatus enum."""
        from src.models.stripe_billing import StripeMeterEvent, StripeMeterEventStatus

        event = StripeMeterEvent(
            tenant_id="test_tenant",
            event_name="test_event",
            quantity=100,
            idempotency_key="test_key",
            status=StripeMeterEventStatus.PENDING
        )

        assert event.status == StripeMeterEventStatus.PENDING
        assert event.status.value == 'pending'


class TestDatabaseFunctions:
    """
    Tests for database helper functions.
    """

    @pytest.mark.asyncio
    async def test_create_stripe_subscription_function_exists(self):
        """Test that create_stripe_subscription function exists and is callable."""
        from src.models.stripe_billing import create_stripe_subscription
        from unittest.mock import AsyncMock, Mock

        # Create a mock session
        mock_session = Mock()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock the StripeSubscription to avoid actual model creation
        with patch('src.models.stripe_billing.StripeSubscription') as MockSubscription:
            mock_instance = Mock()
            MockSubscription.return_value = mock_instance

            # Call the function
            result = await create_stripe_subscription(
                session=mock_session,
                tenant_id="test_tenant",
                stripe_subscription_id="sub_test123",
                stripe_customer_id="cus_test123",
                status="active"
            )

            # Verify the function worked correctly
            mock_session.add.assert_called_once_with(mock_instance)
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once_with(mock_instance)

    @pytest.mark.asyncio
    async def test_create_stripe_meter_event_function_exists(self):
        """Test that create_stripe_meter_event function exists and is callable."""
        from src.models.stripe_billing import create_stripe_meter_event
        from unittest.mock import AsyncMock, Mock

        # Create a mock session
        mock_session = Mock()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock the StripeMeterEvent to avoid actual model creation
        with patch('src.models.stripe_billing.StripeMeterEvent') as MockEvent:
            mock_instance = Mock()
            MockEvent.return_value = mock_instance

            # Call the function
            result = await create_stripe_meter_event(
                session=mock_session,
                tenant_id="test_tenant",
                event_name="test_event",
                quantity=100,
                idempotency_key="unique_key_123"
            )

            # Verify the function worked correctly
            mock_session.add.assert_called_once_with(mock_instance)
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once_with(mock_instance)
