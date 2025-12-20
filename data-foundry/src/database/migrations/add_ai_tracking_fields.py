"""
Database migration to add AI tracking fields to data_records table.
"""

import asyncio
from sqlalchemy import text
from src.database.connection import db_connection
from src.core.config import settings


async def upgrade():
    """Add new AI tracking fields to data_records table."""
    async with db_connection.get_session() as session:
        try:
            # Add AI processing metadata fields
            await session.execute(text("""
                ALTER TABLE data_records
                ADD COLUMN IF NOT EXISTS ai_model VARCHAR(100),
                ADD COLUMN IF NOT EXISTS ai_request_id VARCHAR(100),
                ADD COLUMN IF NOT EXISTS ai_tokens_used INTEGER,
                ADD COLUMN IF NOT EXISTS ai_cost VARCHAR(20),
                ADD COLUMN IF NOT EXISTS ai_processing_time_ms FLOAT;
            """))

            # Add provenance metadata fields
            await session.execute(text("""
                ALTER TABLE data_records
                ADD COLUMN IF NOT EXISTS provenance_metadata JSONB,
                ADD COLUMN IF NOT EXISTS processing_history JSONB;
            """))

            # Create indexes for frequently queried fields
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_data_records_ai_model
                ON data_records(ai_model);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_data_records_ai_request_id
                ON data_records(ai_request_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_data_records_tenant_ai_model
                ON data_records(tenant_id, ai_model);
            """))

            await session.commit()
            print("Migration completed successfully")

        except Exception as e:
            await session.rollback()
            print(f"Migration failed: {str(e)}")
            raise


async def downgrade():
    """Remove AI tracking fields from data_records table."""
    async with db_connection.get_session() as session:
        try:
            # Drop indexes first
            await session.execute(text("""
                DROP INDEX IF EXISTS idx_data_records_ai_model;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_data_records_ai_request_id;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_data_records_tenant_ai_model;
            """))

            # Remove columns
            await session.execute(text("""
                ALTER TABLE data_records
                DROP COLUMN IF EXISTS ai_model,
                DROP COLUMN IF EXISTS ai_request_id,
                DROP COLUMN IF EXISTS ai_tokens_used,
                DROP COLUMN IF EXISTS ai_cost,
                DROP COLUMN IF EXISTS ai_processing_time_ms,
                DROP COLUMN IF EXISTS provenance_metadata,
                DROP COLUMN IF EXISTS processing_history;
            """))

            await session.commit()
            print("Downgrade completed successfully")

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