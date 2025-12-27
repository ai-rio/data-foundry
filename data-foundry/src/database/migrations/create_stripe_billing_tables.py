"""
Database migration to create Stripe billing tables.

This migration creates tables for Stripe subscription and meter event tracking,
following the existing pattern from create_usage_tracking_tables.py.

Quality improvements for P1-001:
- Foreign key constraints to tenants table
- Row-Level Security (RLS) for tenant isolation
- CHECK constraints for status validation
- Audit trail fields (created_by, updated_by)
- Composite indexes for query performance
"""

import asyncio
from sqlalchemy import text
from src.database.connection import db_connection
from src.core.config import settings


async def upgrade():
    """
    Create Stripe billing tables with all security and quality improvements.

    Creates:
    - stripe_subscriptions: Tracks subscription status and billing periods
    - stripe_meter_events: Tracks metered usage events sent to Stripe

    Quality enhancements:
    - FK constraints to tenants(tenant_id) ON DELETE CASCADE
    - RLS enabled with tenant isolation policies
    - CHECK constraints for status field validation
    - Audit trail fields (created_by, updated_by)
    - Composite indexes on (tenant_id, status)
    """
    async with db_connection.get_session() as session:
        try:
            # Create stripe_subscriptions table with all enhancements
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS stripe_subscriptions (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) NOT NULL,
                    stripe_subscription_id VARCHAR(255) UNIQUE NOT NULL,
                    stripe_customer_id VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    current_period_start TIMESTAMP,
                    current_period_end TIMESTAMP,
                    cancel_at_period_end BOOLEAN DEFAULT FALSE,
                    tier VARCHAR(50),
                    created_by VARCHAR(100),
                    updated_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),

                    -- Foreign key constraint
                    CONSTRAINT fk_stripe_subscriptions_tenant
                        FOREIGN KEY (tenant_id)
                        REFERENCES tenants(tenant_id)
                        ON DELETE CASCADE,

                    -- Check constraint for status validation
                    CONSTRAINT chk_stripe_subscriptions_status
                        CHECK (status IN ('active', 'canceled', 'past_due', 'trialing', 'incomplete'))
                );
            """))

            # Create stripe_meter_events table with all enhancements
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS stripe_meter_events (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) NOT NULL,
                    event_name VARCHAR(100) NOT NULL,
                    quantity INTEGER NOT NULL,
                    batch_id VARCHAR(255),
                    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
                    stripe_response JSONB,
                    status VARCHAR(50) NOT NULL,
                    error_message TEXT,
                    created_by VARCHAR(100),
                    updated_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW(),
                    retried_at TIMESTAMP,
                    retry_count INTEGER DEFAULT 0,

                    -- Foreign key constraint
                    CONSTRAINT fk_stripe_meter_events_tenant
                        FOREIGN KEY (tenant_id)
                        REFERENCES tenants(tenant_id)
                        ON DELETE CASCADE,

                    -- Check constraint for status validation
                    CONSTRAINT chk_stripe_meter_events_status
                        CHECK (status IN ('pending', 'succeeded', 'failed'))
                );
            """))

            # Create single-column indexes for stripe_subscriptions
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_subscriptions_tenant
                ON stripe_subscriptions(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_subscriptions_status
                ON stripe_subscriptions(status);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_subscriptions_stripe_id
                ON stripe_subscriptions(stripe_subscription_id);
            """))

            # Create single-column indexes for stripe_meter_events
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_meter_events_tenant
                ON stripe_meter_events(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_meter_events_status
                ON stripe_meter_events(status);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_meter_events_idempotency
                ON stripe_meter_events(idempotency_key);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_meter_events_batch
                ON stripe_meter_events(batch_id);
            """))

            # Create composite indexes for performance (tenant_id, status)
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_subscriptions_tenant_status
                ON stripe_subscriptions(tenant_id, status);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_meter_events_tenant_status
                ON stripe_meter_events(tenant_id, status);
            """))

            # Enable Row-Level Security on both tables
            await session.execute(text("""
                ALTER TABLE stripe_subscriptions ENABLE ROW LEVEL SECURITY;
            """))

            await session.execute(text("""
                ALTER TABLE stripe_subscriptions FORCE ROW LEVEL SECURITY;
            """))

            await session.execute(text("""
                ALTER TABLE stripe_meter_events ENABLE ROW LEVEL SECURITY;
            """))

            await session.execute(text("""
                ALTER TABLE stripe_meter_events FORCE ROW LEVEL SECURITY;
            """))

            # Create RLS policies for tenant isolation on stripe_subscriptions
            await session.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policy
                        WHERE polname = 'tenant_isolation_stripe_subscriptions'
                    ) THEN
                        CREATE POLICY tenant_isolation_stripe_subscriptions
                        ON stripe_subscriptions FOR ALL TO PUBLIC
                        USING (tenant_id = current_setting('app.tenant_id', true))
                        WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
                    END IF;
                END $$;
            """))

            # Create RLS policies for tenant isolation on stripe_meter_events
            await session.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policy
                        WHERE polname = 'tenant_isolation_stripe_meter_events'
                    ) THEN
                        CREATE POLICY tenant_isolation_stripe_meter_events
                        ON stripe_meter_events FOR ALL TO PUBLIC
                        USING (tenant_id = current_setting('app.tenant_id', true))
                        WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
                    END IF;
                END $$;
            """))

            # Add comments to tables
            await session.execute(text("""
                COMMENT ON TABLE stripe_subscriptions IS 'Tracks Stripe subscription status and billing periods with RLS and audit trail';
            """))

            await session.execute(text("""
                COMMENT ON TABLE stripe_meter_events IS 'Tracks metered usage events sent to Stripe for billing with RLS and audit trail';
            """))

            # Add comments to key columns
            await session.execute(text("""
                COMMENT ON COLUMN stripe_subscriptions.stripe_subscription_id IS 'Unique Stripe subscription identifier';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN stripe_subscriptions.cancel_at_period_end IS 'Whether subscription will cancel at period end';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN stripe_subscriptions.created_by IS 'User who created the subscription record';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN stripe_subscriptions.updated_by IS 'User who last updated the subscription record';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN stripe_meter_events.idempotency_key IS 'Unique key to prevent duplicate Stripe events';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN stripe_meter_events.stripe_response IS 'Stripe API response data (JSONB)';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN stripe_meter_events.created_by IS 'User who created the event record';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN stripe_meter_events.updated_by IS 'User who last updated the event record';
            """))

            await session.commit()
            print("Stripe billing tables created successfully with all quality improvements")

        except Exception as e:
            await session.rollback()
            print(f"Migration failed: {str(e)}")
            raise


async def downgrade():
    """
    Drop Stripe billing tables.

    Drops tables in reverse order to handle dependencies.
    """
    async with db_connection.get_session() as session:
        try:
            # Drop RLS policies first
            await session.execute(text("""
                DROP POLICY IF EXISTS tenant_isolation_stripe_subscriptions
                ON stripe_subscriptions;
            """))

            await session.execute(text("""
                DROP POLICY IF EXISTS tenant_isolation_stripe_meter_events
                ON stripe_meter_events;
            """))

            # Drop tables in reverse order
            await session.execute(text("DROP TABLE IF EXISTS stripe_meter_events CASCADE;"))
            await session.execute(text("DROP TABLE IF EXISTS stripe_subscriptions CASCADE;"))

            await session.commit()
            print("Stripe billing tables dropped successfully")

        except Exception as e:
            await session.rollback()
            print(f"Downgrade failed: {str(e)}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())
