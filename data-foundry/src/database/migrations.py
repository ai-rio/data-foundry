"""
Database migrations including Row-Level Security (RLS) setup
"""

import asyncio
from typing import List

from sqlmodel import SQLModel
from src.core.config import settings
from src.database.connection import db_connection


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
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

        # Create policy for data_records
        await conn.execute("""
            CREATE POLICY IF NOT EXISTS tenant_isolation_data_records
            ON data_records
            FOR ALL
            TO PUBLIC
            USING (tenant_id = current_setting('app.tenant_id', true));
        """)

        # Create policy for processed_data
        await conn.execute("""
            CREATE POLICY IF NOT EXISTS tenant_isolation_processed_data
            ON processed_data
            FOR ALL
            TO PUBLIC
            USING (tenant_id = current_setting('app.tenant_id', true));
        """)

        # Create policy for human_review_queue
        await conn.execute("""
            CREATE POLICY IF NOT EXISTS tenant_isolation_human_review_queue
            ON human_review_queue
            FOR ALL
            TO PUBLIC
            USING (tenant_id = current_setting('app.tenant_id', true));
        """)

        # Create policy for users (allow users to see their own tenant's users)
        await conn.execute("""
            CREATE POLICY IF NOT EXISTS tenant_isolation_users
            ON users
            FOR ALL
            TO PUBLIC
            USING (tenant_id = current_setting('app.tenant_id', true));
        """)

        # Create policy for tenants (allow all access - tenants table is special)
        await conn.execute("""
            CREATE POLICY IF NOT EXISTS allow_all_tenants
            ON tenants
            FOR ALL
            TO PUBLIC
            USING (true);
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
                CREATE TRIGGER IF NOT EXISTS set_tenant_id_{table}
                BEFORE INSERT OR UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION set_tenant_id();
            """)


async def seed_test_data():
    """Seed test data for development."""
    if settings.ENVIRONMENT != "development":
        return

    from src.models.user import User, UserRole, UserStatus
    from src.models.tenant import Tenant, TenantStatus
    from src.core.security import get_password_hash

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

        # Create test users
        user1 = User(
            user_id="user_001",
            email="admin@testcorp.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            first_name="Admin",
            last_name="User",
        )

        user2 = User(
            user_id="user_002",
            email="analyst@testcorp.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            first_name="Data",
            last_name="Analyst",
        )

        user3 = User(
            user_id="user_003",
            email="viewer@demoinc.com",
            tenant_id="tenant_002",
            hashed_password=get_password_hash("testpass123"),
            role=UserRole.VIEWER,
            status=UserStatus.ACTIVE,
            first_name="View",
            last_name="User",
        )

        session.add(user1)
        session.add(user2)
        session.add(user3)
        await session.commit()


async def run_migrations():
    """Run all database migrations."""
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