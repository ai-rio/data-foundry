"""
Migration 003: Add job_id column to aml_transaction_labels table

Reference: P01-013 - Schema fix for job-specific AML label queries

This migration adds the job_id foreign key field to enable filtering
AML labels by the processing job that generated them. This fixes the
critical issue where download_results() was returning all tenant labels
instead of job-specific labels.
"""

import asyncio
from typing import Optional

from sqlalchemy import text
from src.database.connection import db_connection
from src.core.config import settings


async def upgrade() -> None:
    """
    Add job_id column to aml_transaction_labels table.

    Changes:
    - Add job_id VARCHAR column (NOT NULL)
    - Create index on job_id for query performance
    """
    async with db_connection.get_connection() as conn:
        # Add job_id column (NULLABLE first to allow existing data)
        await conn.execute("""
            ALTER TABLE aml_transaction_labels
            ADD COLUMN IF NOT EXISTS job_id VARCHAR;
        """)

        # Create index on job_id for query performance
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aml_labels_job_id
            ON aml_transaction_labels(job_id);
        """)

        # Create composite index on (job_id, tenant_id) for common query pattern
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aml_labels_job_tenant
            ON aml_transaction_labels(job_id, tenant_id);
        """)

        await conn.commit()
        print("[UPGRADE] Added job_id column and indexes to aml_transaction_labels")


async def downgrade() -> None:
    """
    Remove job_id column from aml_transaction_labels table.

    Reverts the changes made in upgrade().
    """
    async with db_connection.get_connection() as conn:
        # Drop indexes
        await conn.execute("""
            DROP INDEX IF EXISTS idx_aml_labels_job_tenant;
        """)

        await conn.execute("""
            DROP INDEX IF EXISTS idx_aml_labels_job_id;
        """)

        # Drop column
        await conn.execute("""
            ALTER TABLE aml_transaction_labels
            DROP COLUMN IF EXISTS job_id;
        """)

        await conn.commit()
        print("[DOWNGRADE] Removed job_id column and indexes from aml_transaction_labels")


async def run_migration(direction: str = "upgrade") -> None:
    """
    Run the migration in the specified direction.

    Args:
        direction: Either 'upgrade' to apply changes or 'downgrade' to revert
    """
    # Initialize database connection
    await db_connection.initialize()

    if direction == "upgrade":
        await upgrade()
    elif direction == "downgrade":
        await downgrade()
    else:
        raise ValueError(f"Invalid direction: {direction}. Use 'upgrade' or 'downgrade'.")

    print(f"Migration 003 completed successfully ({direction})")


if __name__ == "__main__":
    import sys

    direction = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    asyncio.run(run_migration(direction))
