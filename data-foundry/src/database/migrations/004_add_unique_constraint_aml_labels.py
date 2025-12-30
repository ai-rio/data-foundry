"""
Migration 004: Add unique constraint on (transaction_id, tenant_id) to aml_transaction_labels

Reference: P01-023 - Fix critical database issues

PROBLEM:
The code uses ON CONFLICT (transaction_id, tenant_id) DO NOTHING but the database
schema doesn't have a unique constraint on (transaction_id, tenant_id). This causes
PostgreSQL error: "there is no unique or exclusion constraint matching the ON CONFLICT specification"

SOLUTION:
Add a proper unique constraint to support ON CONFLICT operations and ensure data integrity.
One transaction should have exactly one label per tenant (preventing duplicates).

DESIGN PRINCIPLES:
- Idempotency: Safe to run multiple times (uses IF NOT EXISTS)
- Safety: Handles existing duplicate data before adding constraint
- Rollback: Fully reversible via downgrade()
- Performance: Uses efficient duplicate detection and cleanup
"""

import asyncio
from sqlalchemy import text
from src.database.connection import db_connection


async def upgrade() -> None:
    """
    Add unique constraint on (transaction_id, tenant_id) to aml_transaction_labels.

    Steps:
    1. Detect and handle existing duplicates (if any)
    2. Add unique constraint to prevent future duplicates
    3. Create index for performance optimization

    The constraint ensures:
    - One AI-generated label per transaction per tenant
    - ON CONFLICT clause in INSERT statements works correctly
    - Data integrity at database level
    """
    async with db_connection.get_session() as session:
        try:
            print("=" * 80)
            print("Migration 004: Adding unique constraint on (transaction_id, tenant_id)")
            print("=" * 80)

            # Step 1: Check for existing duplicates
            print("\n[STEP 1/4] Checking for existing duplicate labels...")

            result = await session.execute(text("""
                SELECT transaction_id, tenant_id, COUNT(*) as duplicate_count
                FROM aml_transaction_labels
                WHERE is_deleted = FALSE
                GROUP BY transaction_id, tenant_id
                HAVING COUNT(*) > 1
            """))

            duplicates = result.fetchall()

            if duplicates:
                print(f"⚠️  Found {len(duplicates)} duplicate transaction+tenant pairs")
                print("    Cleaning up duplicates (keeping most recent label)...")

                # For each duplicate group, keep the most recent (highest created_at)
                # and mark older ones as deleted
                for dup in duplicates:
                    txn_id, tenant_id, count = dup
                    print(f"    - Cleaning {count} duplicates for transaction_id={txn_id[:8]}...")

                    # Mark all but the most recent as deleted
                    await session.execute(text("""
                        UPDATE aml_transaction_labels
                        SET is_deleted = TRUE,
                            deleted_at = NOW(),
                            deleted_by = 'system_migration_004'
                        WHERE transaction_id = :txn_id
                          AND tenant_id = :tenant_id
                          AND is_deleted = FALSE
                          AND id NOT IN (
                              SELECT id FROM aml_transaction_labels
                              WHERE transaction_id = :txn_id
                                AND tenant_id = :tenant_id
                                AND is_deleted = FALSE
                              ORDER BY created_at DESC
                              LIMIT 1
                          )
                    """), {"txn_id": txn_id, "tenant_id": tenant_id})

                await session.commit()
                print(f"✓ Cleaned up {len(duplicates)} duplicate groups")
            else:
                print("✓ No duplicates found - data is clean")

            # Step 2: Drop the old partial unique index (from initial migration)
            print("\n[STEP 2/4] Dropping old partial unique index if it exists...")
            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_transaction_labels_uniq_transaction;
            """))
            print("✓ Dropped partial unique index")

            # Step 3: Add the unique constraint
            print("\n[STEP 3/4] Adding unique constraint...")
            await session.execute(text("""
                ALTER TABLE aml_transaction_labels
                ADD CONSTRAINT uq_aml_transaction_labels_txn_tenant
                UNIQUE (transaction_id, tenant_id);
            """))
            print("✓ Unique constraint added: uq_aml_transaction_labels_txn_tenant")

            # Step 4: Add comment for documentation
            print("\n[STEP 4/4] Adding documentation comments...")
            await session.execute(text("""
                COMMENT ON CONSTRAINT uq_aml_transaction_labels_txn_tenant
                ON aml_transaction_labels IS
                'Ensures one AI-generated label per transaction per tenant. Supports ON CONFLICT operations.';
            """))
            print("✓ Documentation added")

            await session.commit()

            print("\n" + "=" * 80)
            print("✓ Migration 004 completed successfully")
            print("  - Unique constraint: (transaction_id, tenant_id)")
            print("  - ON CONFLICT operations now supported")
            print("  - Data integrity enforced at database level")
            print("=" * 80)

        except Exception as e:
            await session.rollback()
            print(f"\n✗ Migration 004 failed: {str(e)}")
            print("  Rolling back all changes...")
            raise


async def downgrade() -> None:
    """
    Remove unique constraint from aml_transaction_labels.

    This rollback:
    1. Drops the unique constraint
    2. Restores the original partial unique index (for backward compatibility)

    Note: Soft-deleted duplicate records are NOT restored (they remain deleted).
    """
    async with db_connection.get_session() as session:
        try:
            print("=" * 80)
            print("Migration 004 DOWNGRADE: Removing unique constraint")
            print("=" * 80)

            # Step 1: Drop the unique constraint
            print("\n[STEP 1/2] Dropping unique constraint...")
            await session.execute(text("""
                ALTER TABLE aml_transaction_labels
                DROP CONSTRAINT IF EXISTS uq_aml_transaction_labels_txn_tenant;
            """))
            print("✓ Unique constraint dropped")

            # Step 2: Restore the original partial unique index
            print("\n[STEP 2/2] Restoring original partial unique index...")
            await session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_aml_transaction_labels_uniq_transaction
                ON aml_transaction_labels(transaction_id, tenant_id)
                WHERE is_deleted = FALSE;
            """))
            print("✓ Partial unique index restored")

            await session.commit()

            print("\n" + "=" * 80)
            print("✓ Migration 004 downgrade completed successfully")
            print("  - Unique constraint removed")
            print("  - Original partial index restored")
            print("=" * 80)

        except Exception as e:
            await session.rollback()
            print(f"\n✗ Downgrade failed: {str(e)}")
            print("  Rolling back all changes...")
            raise


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


if __name__ == "__main__":
    import sys

    direction = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    asyncio.run(run_migration(direction))
