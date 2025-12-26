"""
Pytest configuration and fixtures for Stripe integration tests.

This module provides fixtures for database cleanup and Stripe service testing.
It ensures that data is properly cleaned up between test runs to prevent
unique constraint violations.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import AsyncGenerator

from src.database.connection import db_connection
from src.models.stripe_billing import (
    StripeCustomer,
    StripeSubscription,
    StripeMeterEvent,
)
from src.models.tenant import Tenant


@pytest_asyncio.fixture(scope="module", autouse=True)
async def clean_stripe_database():
    """
    Clean up Stripe billing data before and after each test MODULE.

    This is an autouse fixture that automatically runs for every test module
    in the integration test directory. It ensures that test data from
    previous runs doesn't cause unique constraint violations.

    Given: A database with potentially stale test data
    When: Any test module in the integration directory runs
    Then: All Stripe billing records are removed before and after the module runs

    Note: Using module scope to avoid event loop closure issues with
    pytest-asyncio's function-scoped event loops. Tests within a module
    should use unique identifiers to avoid conflicts.
    """
    # Initialize database connection (idempotent)
    try:
        await db_connection.initialize()
    except Exception:
        # Already initialized
        pass

    # Clean up before module tests run
    async with db_connection.get_session() as session:
        # Delete in order of dependencies to avoid foreign key violations
        # StripeMeterEvent depends on StripeCustomer
        await session.execute(text("DELETE FROM stripe_meter_events WHERE tenant_id LIKE 'stripe_%'"))
        await session.execute(text("DELETE FROM stripe_meter_events WHERE tenant_id LIKE 'test_%'"))
        await session.execute(text("DELETE FROM stripe_meter_events WHERE tenant_id LIKE 'tenant_%'"))

        # StripeSubscription depends on StripeCustomer
        await session.execute(text("DELETE FROM stripe_subscriptions WHERE tenant_id LIKE 'stripe_%'"))
        await session.execute(text("DELETE FROM stripe_subscriptions WHERE tenant_id LIKE 'test_%'"))
        await session.execute(text("DELETE FROM stripe_subscriptions WHERE tenant_id LIKE 'tenant_%'"))

        # StripeCustomer depends on Tenant
        await session.execute(text("DELETE FROM stripe_customers WHERE tenant_id LIKE 'stripe_%'"))
        await session.execute(text("DELETE FROM stripe_customers WHERE tenant_id LIKE 'test_%'"))
        await session.execute(text("DELETE FROM stripe_customers WHERE tenant_id LIKE 'tenant_%'"))

        # Finally, clean up test tenants
        await session.execute(text("DELETE FROM tenants WHERE tenant_id LIKE 'stripe_%'"))
        await session.execute(text("DELETE FROM tenants WHERE tenant_id LIKE 'test_%'"))
        await session.execute(text("DELETE FROM tenants WHERE tenant_id LIKE 'tenant_%'"))

        await session.commit()

    yield

    # Clean up after module tests run as well
    try:
        # Rollback any pending transactions first
        async with db_connection.get_session() as session:
            try:
                await session.rollback()
            except:
                pass

        # Now clean up
        async with db_connection.get_session() as session:
            await session.execute(text("DELETE FROM stripe_meter_events WHERE tenant_id LIKE 'stripe_%'"))
            await session.execute(text("DELETE FROM stripe_meter_events WHERE tenant_id LIKE 'test_%'"))
            await session.execute(text("DELETE FROM stripe_meter_events WHERE tenant_id LIKE 'tenant_%'"))
            await session.execute(text("DELETE FROM stripe_subscriptions WHERE tenant_id LIKE 'stripe_%'"))
            await session.execute(text("DELETE FROM stripe_subscriptions WHERE tenant_id LIKE 'test_%'"))
            await session.execute(text("DELETE FROM stripe_subscriptions WHERE tenant_id LIKE 'tenant_%'"))
            await session.execute(text("DELETE FROM stripe_customers WHERE tenant_id LIKE 'stripe_%'"))
            await session.execute(text("DELETE FROM stripe_customers WHERE tenant_id LIKE 'test_%'"))
            await session.execute(text("DELETE FROM stripe_customers WHERE tenant_id LIKE 'tenant_%'"))
            await session.execute(text("DELETE FROM tenants WHERE tenant_id LIKE 'stripe_%'"))
            await session.execute(text("DELETE FROM tenants WHERE tenant_id LIKE 'test_%'"))
            await session.execute(text("DELETE FROM tenants WHERE tenant_id LIKE 'tenant_%'"))
            await session.commit()
    except Exception:
        # Event loop might be closed during teardown, ignore cleanup errors
        pass


@pytest_asyncio.fixture
async def stripe_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a test database session with automatic cleanup.

    This fixture provides a clean database session for each test.
    Note: The clean_stripe_database autouse fixture handles cleanup.

    Given: The test database is initialized
    When: A test requests the stripe_db_session fixture
    Then: A clean database session is provided with all stale data removed
    """
    async with db_connection.get_session() as session:
        yield session
