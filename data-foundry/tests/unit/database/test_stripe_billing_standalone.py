"""
Standalone test runner for Stripe billing implementation.

This bypasses the root conftest import issues by directly testing the implementation.
"""

import sys
import os
from unittest.mock import Mock, AsyncMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Mock problematic imports before loading other modules
sys.modules['structlog'] = Mock()
sys.modules['jose'] = Mock()
sys.modules['jose.jwt'] = Mock()


def test_stripe_subscription_model():
    """Test StripeSubscription model definition."""
    from src.models.stripe_billing import StripeSubscription

    print("Testing StripeSubscription model...")

    # Check table name
    assert StripeSubscription.__tablename__ == "stripe_subscriptions", \
        f"Expected table name 'stripe_subscriptions', got '{StripeSubscription.__tablename__}'"

    # Check required fields
    required_fields = [
        "id", "tenant_id", "stripe_subscription_id", "stripe_customer_id",
        "status", "current_period_start", "current_period_end",
        "cancel_at_period_end", "tier", "created_at", "updated_at"
    ]

    for field in required_fields:
        assert hasattr(StripeSubscription, field), f"Missing field: {field}"

    print("  ✓ StripeSubscription model verified")
    return True


def test_stripe_meter_event_model():
    """Test StripeMeterEvent model definition."""
    from src.models.stripe_billing import StripeMeterEvent

    print("Testing StripeMeterEvent model...")

    # Check table name
    assert StripeMeterEvent.__tablename__ == "stripe_meter_events", \
        f"Expected table name 'stripe_meter_events', got '{StripeMeterEvent.__tablename__}'"

    # Check required fields
    required_fields = [
        "id", "tenant_id", "event_name", "quantity", "batch_id",
        "idempotency_key", "stripe_response", "status", "error_message",
        "created_at", "retried_at", "retry_count"
    ]

    for field in required_fields:
        assert hasattr(StripeMeterEvent, field), f"Missing field: {field}"

    print("  ✓ StripeMeterEvent model verified")
    return True


def test_models_exported():
    """Test that models are exported from __init__.py."""
    print("Testing model exports...")

    from src.models import (
        StripeSubscription, StripeMeterEvent,
        create_stripe_subscription, create_stripe_meter_event
    )

    assert StripeSubscription is not None
    assert StripeMeterEvent is not None
    assert create_stripe_subscription is not None
    assert create_stripe_meter_event is not None

    print("  ✓ All models exported correctly")
    return True


def test_migration_file_content():
    """Test that migration file contains required SQL."""
    print("Testing migration file content...")

    migration_path = 'src/database/migrations/create_stripe_billing_tables.py'
    with open(migration_path, 'r') as f:
        content = f.read()

    # Verify table creation
    assert 'CREATE TABLE IF NOT EXISTS stripe_subscriptions' in content, \
        "Missing stripe_subscriptions table creation"
    assert 'CREATE TABLE IF NOT EXISTS stripe_meter_events' in content, \
        "Missing stripe_meter_events table creation"

    # Verify unique constraints
    assert 'stripe_subscription_id VARCHAR(255) UNIQUE' in content, \
        "Missing UNIQUE constraint on stripe_subscription_id"
    assert 'idempotency_key VARCHAR(255) UNIQUE' in content, \
        "Missing UNIQUE constraint on idempotency_key"

    # Verify indexes
    assert 'idx_stripe_subscriptions_tenant' in content, \
        "Missing idx_stripe_subscriptions_tenant index"
    assert 'idx_stripe_subscriptions_status' in content, \
        "Missing idx_stripe_subscriptions_status index"
    assert 'idx_stripe_meter_events_tenant' in content, \
        "Missing idx_stripe_meter_events_tenant index"
    assert 'idx_stripe_meter_events_status' in content, \
        "Missing idx_stripe_meter_events_status index"

    # Verify upgrade and downgrade functions
    assert 'async def upgrade():' in content, \
        "Missing upgrade() function"
    assert 'async def downgrade():' in content, \
        "Missing downgrade() function"

    # Verify JSONB column
    assert 'stripe_response JSONB' in content, \
        "Missing stripe_response JSONB column"

    print("  ✓ Migration file content verified")
    return True


def test_schema_requirements():
    """Test that schema matches requirements."""
    print("Testing schema requirements...")

    migration_path = 'src/database/migrations/create_stripe_billing_tables.py'
    with open(migration_path, 'r') as f:
        content = f.read()

    # Verify stripe_subscriptions columns
    required_subscription_columns = [
        'id SERIAL PRIMARY KEY',
        'tenant_id VARCHAR(50) NOT NULL',
        'stripe_subscription_id VARCHAR(255) UNIQUE NOT NULL',
        'stripe_customer_id VARCHAR(255) NOT NULL',
        'status VARCHAR(50) NOT NULL',
        'current_period_start TIMESTAMP',
        'current_period_end TIMESTAMP',
        'cancel_at_period_end BOOLEAN DEFAULT FALSE',
        'tier VARCHAR(50)',
        'created_at TIMESTAMP DEFAULT NOW()',
        'updated_at TIMESTAMP DEFAULT NOW()',
    ]

    for col in required_subscription_columns:
        assert col in content, f"Missing column in stripe_subscriptions: {col}"

    # Verify stripe_meter_events columns
    required_event_columns = [
        'id SERIAL PRIMARY KEY',
        'tenant_id VARCHAR(50) NOT NULL',
        'event_name VARCHAR(100) NOT NULL',
        'quantity INTEGER NOT NULL',
        'batch_id VARCHAR(255)',
        'idempotency_key VARCHAR(255) UNIQUE NOT NULL',
        'stripe_response JSONB',
        'status VARCHAR(50) NOT NULL',
        'error_message TEXT',
        'created_at TIMESTAMP DEFAULT NOW()',
        'retried_at TIMESTAMP',
        'retry_count INTEGER DEFAULT 0',
    ]

    for col in required_event_columns:
        assert col in content, f"Missing column in stripe_meter_events: {col}"

    print("  ✓ Schema requirements verified")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("STRIPE BILLING IMPLEMENTATION TESTS")
    print("="*60 + "\n")

    tests = [
        test_stripe_subscription_model,
        test_stripe_meter_event_model,
        test_models_exported,
        test_migration_file_content,
        test_schema_requirements,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
