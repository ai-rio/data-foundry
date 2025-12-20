"""
Migration runner for Data Foundry database.

This script runs all database migrations in the correct order to ensure
proper database schema setup and upgrades.
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Tuple
from sqlalchemy import text
from src.database.connection import db_connection
from src.core.config import settings

# Import all migration modules
from . import add_ai_tracking_fields
from . import create_usage_tracking_tables
from . import enhance_tenant_user_models


class Migration:
    """Represents a single database migration."""

    def __init__(self, name: str, module, description: str):
        self.name = name
        self.module = module
        self.description = description

    async def upgrade(self):
        """Run the migration upgrade."""
        print(f"\n{'='*60}")
        print(f"Running migration: {self.name}")
        print(f"Description: {self.description}")
        print(f"{'='*60}")
        await self.module.upgrade()
        print(f"✅ Migration {self.name} completed successfully")

    async def downgrade(self):
        """Run the migration downgrade."""
        print(f"\n{'='*60}")
        print(f"Downgrading migration: {self.name}")
        print(f"{'='*60}")
        await self.module.downgrade()
        print(f"✅ Migration {self.name} downgraded successfully")


# Define migration order - IMPORTANT: Order matters!
MIGRATIONS: List[Migration] = [
    Migration(
        "add_ai_tracking_fields",
        add_ai_tracking_fields,
        "Add AI tracking fields to data_records table"
    ),
    Migration(
        "enhance_tenant_user_models",
        enhance_tenant_user_models,
        "Enhance tenant and user models with billing and feature flags"
    ),
    Migration(
        "create_usage_tracking_tables",
        create_usage_tracking_tables,
        "Create usage tracking and billing tables"
    ),
]


async def create_migration_table():
    """Create the migrations tracking table."""
    async with db_connection.get_session() as session:
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(255) UNIQUE NOT NULL,
                executed_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))
        await session.commit()


async def get_executed_migrations() -> set:
    """Get the set of already executed migrations."""
    async with db_connection.get_session() as session:
        result = await session.execute(text(
            "SELECT migration_name FROM schema_migrations"
        ))
        return {row[0] for row in result.fetchall()}


async def mark_migration_executed(migration_name: str):
    """Mark a migration as executed."""
    async with db_connection.get_session() as session:
        await session.execute(text(
            "INSERT INTO schema_migrations (migration_name) VALUES (:name)",
            {"name": migration_name}
        ))
        await session.commit()


async def mark_migration_rolled_back(migration_name: str):
    """Remove a migration from the executed list."""
    async with db_connection.get_session() as session:
        await session.execute(text(
            "DELETE FROM schema_migrations WHERE migration_name = :name",
            {"name": migration_name}
        ))
        await session.commit()


async def run_upgrades(target_migration: str = None):
    """Run all pending migrations or up to a specific migration."""
    await create_migration_table()
    executed = await get_executed_migrations()

    print(f"\n🚀 Starting database migrations...")
    print(f"Already executed: {len(executed)} migrations")

    for migration in MIGRATIONS:
        if migration.name in executed:
            print(f"⏭️  Skipping {migration.name} (already executed)")
            continue

        if target_migration and migration.name != target_migration:
            continue

        await migration.upgrade()
        await mark_migration_executed(migration.name)

        if target_migration and migration.name == target_migration:
            break

    print(f"\n✅ All migrations completed successfully!")


async def run_single_downgrade(migration_name: str):
    """Run a single migration downgrade."""
    await create_migration_table()
    executed = await get_executed_migrations()

    if migration_name not in executed:
        print(f"❌ Migration {migration_name} was not executed")
        return False

    # Find the migration
    migration = next((m for m in MIGRATIONS if m.name == migration_name), None)
    if not migration:
        print(f"❌ Migration {migration_name} not found")
        return False

    await migration.downgrade()
    await mark_migration_rolled_back(migration_name)
    return True


async def run_downgrades(target_migration: str = None):
    """Rollback migrations in reverse order."""
    await create_migration_table()
    executed = await get_executed_migrations()

    print(f"\n🔄 Rolling back database migrations...")

    # Run migrations in reverse order
    for migration in reversed(MIGRATIONS):
        if migration.name not in executed:
            continue

        await migration.downgrade()
        await mark_migration_rolled_back(migration.name)

        if target_migration and migration.name == target_migration:
            break

    print(f"\n✅ Rollback completed successfully!")


async def show_status():
    """Show the current migration status."""
    await create_migration_table()
    executed = await get_executed_migrations()

    print(f"\n📊 Migration Status")
    print(f"{'='*60}")
    print(f"Total migrations: {len(MIGRATIONS)}")
    print(f"Executed: {len(executed)}")
    print(f"Pending: {len(MIGRATIONS) - len(executed)}")
    print(f"\nMigration List:")
    print(f"{'='*60}")

    for migration in MIGRATIONS:
        status = "✅ Executed" if migration.name in executed else "⏳ Pending"
        print(f"{status:12} {migration.name:35} - {migration.description}")


async def reset_database():
    """Reset the entire database (dangerous!)."""
    print("\n⚠️  WARNING: This will reset the entire database!")
    print("All data will be permanently lost.")

    confirm = input("\nType 'RESET' to confirm: ")
    if confirm != "RESET":
        print("❌ Reset cancelled")
        return

    print("\n🔄 Resetting database...")

    # Drop all tables in the correct order
    async with db_connection.get_session() as session:
        # Drop usage tracking tables first
        await session.execute(text("DROP TABLE IF EXISTS billing_events CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS cost_alerts CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS audit_logs CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS tenant_usage CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS token_usage CASCADE;"))

        # Drop main tables
        await session.execute(text("DROP TABLE IF EXISTS human_review_queue CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS processed_data CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS data_records CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
        await session.execute(text("DROP TABLE IF EXISTS tenants CASCADE;"))

        # Drop migrations table
        await session.execute(text("DROP TABLE IF EXISTS schema_migrations CASCADE;"))

        await session.commit()

    print("✅ Database reset completed")

    # Run all migrations
    await run_upgrades()


async def main():
    """Main entry point."""
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    target = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        if command == "upgrade":
            await run_upgrades(target)
        elif command == "downgrade":
            if target:
                await run_single_downgrade(target)
            else:
                await run_downgrades()
        elif command == "status":
            await show_status()
        elif command == "reset":
            await reset_database()
        else:
            print(f"Unknown command: {command}")
            print("\nAvailable commands:")
            print("  upgrade [migration] - Run all pending migrations or specific one")
            print("  downgrade [migration] - Rollback last or specific migration")
            print("  status - Show migration status")
            print("  reset - Reset entire database (dangerous!)")
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())