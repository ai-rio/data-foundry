"""
Database migration to add stripe_customers table.

This migration adds the missing stripe_customers table that was
not included in P1-001 (create_stripe_billing_tables.py).

P1-002 Requirement: StripeService base with Customer CRUD operations

Table Features:
- Maps tenant_id to stripe_customer_id for bidirectional lookup
- Caches customer email and name from Stripe for query efficiency
- Foreign key to tenants(tenant_id) with CASCADE delete
- Unique constraints on both tenant_id and stripe_customer_id
- Indexes for optimal query performance
- Audit trail fields (created_by, updated_by)
- Row-Level Security (RLS) for tenant isolation
"""

import asyncio
import logging
from sqlalchemy import text
from src.database.connection import db_connection
from src.core.config import settings

logger = logging.getLogger(__name__)


async def upgrade():
    """
    Create stripe_customers table with all security and quality improvements.

    Table structure:
    - id: Serial primary key
    - tenant_id: Unique, indexed, FK to tenants(tenant_id)
    - stripe_customer_id: Unique, indexed Stripe customer ID
    - email: Cached customer email (optional)
    - name: Cached customer name (optional)
    - created_by, updated_by: Audit trail
    - created_at, updated_at: Timestamps

    Security features:
    - Foreign key constraint with CASCADE delete
    - Unique constraints on tenant_id and stripe_customer_id
    - Indexes on tenant_id and stripe_customer_id
    - RLS enabled with tenant isolation policy
    """
    async with db_connection.get_session() as session:
        try:
            # Create stripe_customers table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS stripe_customers (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) UNIQUE NOT NULL,
                    stripe_customer_id VARCHAR(255) UNIQUE NOT NULL,
                    email VARCHAR(255),
                    name VARCHAR(255),
                    created_by VARCHAR(100),
                    updated_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),

                    -- Foreign key constraint to tenants table
                    CONSTRAINT fk_stripe_customers_tenant
                        FOREIGN KEY (tenant_id)
                        REFERENCES tenants(tenant_id)
                        ON DELETE CASCADE
                );
            """))
            logger.info("Created stripe_customers table")

            # Create index on tenant_id
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_customers_tenant
                ON stripe_customers(tenant_id);
            """))
            logger.info("Created index on stripe_customers.tenant_id")

            # Create index on stripe_customer_id
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_stripe_customers_stripe_id
                ON stripe_customers(stripe_customer_id);
            """))
            logger.info("Created index on stripe_customers.stripe_customer_id")

            # Enable Row-Level Security
            await session.execute(text("""
                ALTER TABLE stripe_customers ENABLE ROW LEVEL SECURITY;
            """))
            logger.info("Enabled RLS on stripe_customers")

            # Force RLS (ensure policies are always applied)
            await session.execute(text("""
                ALTER TABLE stripe_customers FORCE ROW LEVEL SECURITY;
            """))
            logger.info("Forced RLS on stripe_customers")

            # Create RLS policy for tenant isolation
            await session.execute(text("""
                CREATE POLICY tenant_isolation_stripe_customers
                ON stripe_customers FOR ALL
                TO PUBLIC
                USING (tenant_id = current_setting('app.tenant_id', true))
                WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
            """))
            logger.info("Created RLS policy for stripe_customers tenant isolation")

            # Create trigger to update updated_at timestamp
            await session.execute(text("""
                CREATE OR REPLACE FUNCTION update_stripe_customers_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
            """))

            await session.execute(text("""
                CREATE TRIGGER trigger_update_stripe_customers_updated_at
                BEFORE UPDATE ON stripe_customers
                FOR EACH ROW
                EXECUTE FUNCTION update_stripe_customers_updated_at();
            """))
            logger.info("Created updated_at trigger for stripe_customers")

            await session.commit()
            logger.info("Successfully added stripe_customers table")

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to add stripe_customers table: {e}")
            raise


async def downgrade():
    """
    Rollback the migration by dropping stripe_customers table.
    """
    async with db_connection.get_session() as session:
        try:
            # Drop trigger
            await session.execute(text("""
                DROP TRIGGER IF EXISTS trigger_update_stripe_customers_updated_at
                ON stripe_customers;
            """))

            # Drop function
            await session.execute(text("""
                DROP FUNCTION IF EXISTS update_stripe_customers_updated_at();
            """))

            # Drop RLS policy
            await session.execute(text("""
                DROP POLICY IF EXISTS tenant_isolation_stripe_customers
                ON stripe_customers;
            """))

            # Drop table (indexes are dropped automatically)
            await session.execute(text("""
                DROP TABLE IF EXISTS stripe_customers CASCADE;
            """))

            await session.commit()
            logger.info("Successfully dropped stripe_customers table")

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to drop stripe_customers table: {e}")
            raise


async def main():
    """
    Main function to run the migration.
    """
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        logger.info("Running downgrade: removing stripe_customers table")
        await downgrade()
    else:
        logger.info("Running upgrade: adding stripe_customers table")
        await upgrade()


if __name__ == "__main__":
    asyncio.run(main())
