"""
Database migrations including Row-Level Security (RLS) setup
"""

import asyncio
from typing import List

from sqlmodel import SQLModel
from sqlalchemy import text
from src.core.config import settings
from src.database.connection import db_connection

# Import all models to ensure they're registered with SQLModel.metadata
from src.models.data_record import DataRecord
from src.models.processed_data import ProcessedData
from src.models.human_review_queue import HumanReviewQueue
from src.models.user import User, UserRole, UserStatus
from src.models.tenant import Tenant, TenantStatus
from src.infrastructure.repositories.job_repository import ProcessingJobDB


async def create_tables():
    """Create all database tables."""
    SQLModel.metadata.create_all(db_connection._sync_engine)


async def create_indexes():
    """Create database indexes for performance."""
    async with db_connection.get_connection() as conn:
        # Tenant-specific indexes
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_records_tenant_id
            ON data_records(tenant_id);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed_data_tenant_id
            ON processed_data(tenant_id);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_human_review_queue_tenant_id
            ON human_review_queue(tenant_id);
        """)

        # Performance indexes
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_records_status
            ON data_records(status);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed_data_confidence
            ON processed_data(confidence_score);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_human_review_queue_status
            ON human_review_queue(status);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_human_review_queue_priority
            ON human_review_queue(priority);
        """)


async def create_rls_policies():
    """Create Row-Level Security (RLS) policies."""
    async with db_connection.get_connection() as conn:
        # Enable RLS on all tables
        tables = [
            "data_records",
            "processed_data",
            "human_review_queue",
            "users",
            "tenants",
        ]

        for table in tables:
            # Force RLS to apply even to table owner
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # Create policy for data_records with proper PostgreSQL syntax
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy
                    WHERE polname = 'tenant_isolation_data_records'
                ) THEN
                    CREATE POLICY tenant_isolation_data_records
                    ON data_records FOR ALL TO PUBLIC
                    USING (tenant_id = current_setting('app.tenant_id', true))
                    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
                END IF;
            END $$;
        """)

        # Create policy for processed_data with proper PostgreSQL syntax
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy
                    WHERE polname = 'tenant_isolation_processed_data'
                ) THEN
                    CREATE POLICY tenant_isolation_processed_data
                    ON processed_data FOR ALL TO PUBLIC
                    USING (tenant_id = current_setting('app.tenant_id', true))
                    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
                END IF;
            END $$;
        """)

        # Create policy for human_review_queue with proper PostgreSQL syntax
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy
                    WHERE polname = 'tenant_isolation_human_review_queue'
                ) THEN
                    CREATE POLICY tenant_isolation_human_review_queue
                    ON human_review_queue FOR ALL TO PUBLIC
                    USING (tenant_id = current_setting('app.tenant_id', true))
                    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
                END IF;
            END $$;
        """)

        # Create policy for users with proper PostgreSQL syntax
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy
                    WHERE polname = 'tenant_isolation_users'
                ) THEN
                    CREATE POLICY tenant_isolation_users
                    ON users FOR ALL TO PUBLIC
                    USING (tenant_id = current_setting('app.tenant_id', true))
                    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
                END IF;
            END $$;
        """)

        # Create policy for tenants with proper PostgreSQL syntax
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy
                    WHERE polname = 'allow_all_tenants'
                ) THEN
                    CREATE POLICY allow_all_tenants
                    ON tenants FOR ALL TO PUBLIC
                    USING (true)
                    WITH CHECK (true);
                END IF;
            END $$;
        """)

        # Create RLS function for automatic tenant setting
        await conn.execute("""
            CREATE OR REPLACE FUNCTION set_tenant_id()
            RETURNS trigger AS $$
            BEGIN
                NEW.tenant_id = current_setting('app.tenant_id', true);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER;
        """)

        # Create triggers for automatic tenant setting
        tables_with_tenant_id = [
            "data_records",
            "processed_data",
            "human_review_queue",
            "users",
        ]

        for table in tables_with_tenant_id:
            await conn.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'set_tenant_id_{table}'
                    ) THEN
                        CREATE TRIGGER set_tenant_id_{table}
                        BEFORE INSERT OR UPDATE ON {table}
                        FOR EACH ROW EXECUTE FUNCTION set_tenant_id();
                    END IF;
                END $$;
            """)


async def seed_test_data():
    """Seed test data for development."""
    if settings.ENVIRONMENT != "development":
        return

    from src.models.user import User, UserRole, UserStatus
    from src.models.tenant import Tenant, TenantStatus
    from src.core.security import get_password_hash

    # First, create tenants using a regular session (tenants table allows all access)
    async with db_connection.get_session() as session:
        # Create test tenants
        tenant1 = Tenant(
            tenant_id="tenant_001",
            name="Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=50,
            max_data_records=1000000,
            storage_limit_gb=100.0,
        )

        tenant2 = Tenant(
            tenant_id="tenant_002",
            name="Demo Inc",
            status=TenantStatus.ACTIVE,
            max_users=100,
            max_data_records=500000,
            storage_limit_gb=50.0,
        )

        session.add(tenant1)
        session.add(tenant2)
        await session.commit()

    # Now create users using tenant-aware sessions for proper RLS
    # Users for tenant_001
    async with db_connection.get_tenant_connection("tenant_001") as conn:
        await conn.execute("""
            INSERT INTO users (user_id, email, tenant_id, hashed_password, role, status, first_name, last_name)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, "user_001", "admin@testcorp.com", "tenant_001", get_password_hash("testpass123"), "ADMIN", "ACTIVE", "Admin", "User")

        await conn.execute("""
            INSERT INTO users (user_id, email, tenant_id, hashed_password, role, status, first_name, last_name)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, "user_002", "analyst@testcorp.com", "tenant_001", get_password_hash("testpass123"), "ANALYST", "ACTIVE", "Data", "Analyst")

    # Users for tenant_002
    async with db_connection.get_tenant_connection("tenant_002") as conn:
        await conn.execute("""
            INSERT INTO users (user_id, email, tenant_id, hashed_password, role, status, first_name, last_name)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, "user_003", "viewer@demoinc.com", "tenant_002", get_password_hash("testpass123"), "VIEWER", "ACTIVE", "View", "User")


async def run_migrations():
    """Run all database migrations."""
    # Initialize database connection first
    print("Initializing database connection...")
    await db_connection.initialize()

    print("Creating database tables...")
    await create_tables()

    print("Creating database indexes...")
    await create_indexes()

    print("Setting up Row-Level Security policies...")
    await create_rls_policies()

    print("Seeding test data...")
    await seed_test_data()

    print("Database migrations completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migrations())