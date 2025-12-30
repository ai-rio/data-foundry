"""
Test suite for migration 004: Add unique constraint on (transaction_id, tenant_id)

This test suite validates:
1. Migration upgrade path (forward migration)
2. Migration downgrade path (rollback)
3. Migration idempotency (safe to run multiple times)
4. Handling of existing duplicate data
5. Constraint enforcement after migration

Reference: P01-023 - Critical Database Fixes
Target Coverage: 100% of migration code
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from uuid import uuid4
from datetime import datetime
from decimal import Decimal

from src.database.connection import db_connection
from src.database.migrations import run_migrations_004_add_unique_constraint_aml_labels as migration_004
from src.models.aml_transaction_label import AMLTransactionLabel
from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    """Initialize database and provide async session."""
    await db_connection.initialize()

    async with db_connection.get_session() as session:
        # Clean up test data before each test
        await session.execute(text("DELETE FROM aml_transaction_labels"))
        await session.commit()
        yield session

    # Cleanup after test
    async with db_connection.get_session() as cleanup_session:
        await cleanup_session.execute(text("DELETE FROM aml_transaction_labels"))
        await cleanup_session.commit()


@pytest.mark.integration
class TestMigration004Upgrade:
    """Test migration 004 upgrade path."""

    async def test_upgrade_on_clean_database(self, db_session):
        """Test migration upgrade on a database with no duplicates."""
        # Run upgrade
        await migration_004.upgrade()

        # Verify unique constraint was added
        result = await db_session.execute(text("""
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = 'aml_transaction_labels'
              AND constraint_name = 'uq_aml_transaction_labels_txn_tenant'
        """))
        constraint = result.fetchone()

        assert constraint is not None, "Unique constraint should be created"
        assert constraint[1] == 'UNIQUE', "Constraint should be of type UNIQUE"

    async def test_upgrade_with_existing_duplicates(self, db_session):
        """Test migration upgrade handles existing duplicate data gracefully."""
        # Insert duplicate records
        txn_id = str(uuid4())
        tenant_id = "tenant_001"

        # Create 3 duplicate labels for same transaction+tenant
        for i in range(3):
            label = AMLTransactionLabel(
                id=str(uuid4()),
                transaction_id=txn_id,
                tenant_id=tenant_id,
                job_id="job_001",
                risk_level=AMLRiskLevel.HIGH,
                typology="ML",
                confidence_score=Decimal("0.85"),
                ai_reasoning="Test reasoning",
                expert_review_status=AMLExpertReviewStatus.PENDING,
                is_deleted=False
            )
            db_session.add(label)

        await db_session.commit()

        # Verify 3 duplicates exist before migration
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id AND is_deleted = FALSE
        """), {"txn_id": txn_id, "tenant_id": tenant_id})
        count_before = result.scalar()
        assert count_before == 3, "Should have 3 duplicates before migration"

        # Run upgrade (should clean up duplicates)
        await migration_004.upgrade()

        # Verify only 1 record remains (most recent)
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id AND is_deleted = FALSE
        """), {"txn_id": txn_id, "tenant_id": tenant_id})
        count_after = result.scalar()
        assert count_after == 1, "Should have only 1 record after duplicate cleanup"

        # Verify 2 duplicates were soft-deleted
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id AND is_deleted = TRUE
        """), {"txn_id": txn_id, "tenant_id": tenant_id})
        deleted_count = result.scalar()
        assert deleted_count == 2, "Should have 2 soft-deleted duplicates"

    async def test_upgrade_constraint_enforcement(self, db_session):
        """Test that unique constraint is enforced after migration."""
        # Run upgrade
        await migration_004.upgrade()

        # Insert first record
        txn_id = str(uuid4())
        tenant_id = "tenant_002"

        label1 = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,
            tenant_id=tenant_id,
            job_id="job_001",
            risk_level=AMLRiskLevel.MEDIUM,
            typology="TF",
            confidence_score=Decimal("0.75"),
            ai_reasoning="Test reasoning for constraint",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )
        db_session.add(label1)
        await db_session.commit()

        # Attempt to insert duplicate (should fail with unique constraint violation)
        label2 = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,  # Same transaction_id
            tenant_id=tenant_id,    # Same tenant_id
            job_id="job_002",
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.90"),
            ai_reasoning="Different reasoning",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )
        db_session.add(label2)

        # Should raise unique constraint violation
        with pytest.raises(Exception) as exc_info:
            await db_session.commit()

        # Verify error is a unique constraint violation
        error_msg = str(exc_info.value).lower()
        assert "unique" in error_msg or "duplicate" in error_msg, \
            "Error should indicate unique constraint violation"

    async def test_upgrade_idempotency(self, db_session):
        """Test that running upgrade multiple times is safe (idempotent)."""
        # Run upgrade first time
        await migration_004.upgrade()

        # Run upgrade second time (should not fail)
        try:
            await migration_004.upgrade()
        except Exception as e:
            pytest.fail(f"Second upgrade run should be idempotent but failed: {e}")

        # Verify constraint still exists (only one copy)
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name = 'aml_transaction_labels'
              AND constraint_name = 'uq_aml_transaction_labels_txn_tenant'
        """))
        constraint_count = result.scalar()
        assert constraint_count == 1, "Should have exactly 1 unique constraint"


@pytest.mark.integration
class TestMigration004Downgrade:
    """Test migration 004 downgrade path."""

    async def test_downgrade_removes_constraint(self, db_session):
        """Test that downgrade properly removes the unique constraint."""
        # First run upgrade to add constraint
        await migration_004.upgrade()

        # Verify constraint exists
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name = 'aml_transaction_labels'
              AND constraint_name = 'uq_aml_transaction_labels_txn_tenant'
        """))
        assert result.scalar() == 1, "Constraint should exist after upgrade"

        # Run downgrade
        await migration_004.downgrade()

        # Verify constraint was removed
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name = 'aml_transaction_labels'
              AND constraint_name = 'uq_aml_transaction_labels_txn_tenant'
        """))
        assert result.scalar() == 0, "Constraint should be removed after downgrade"

    async def test_downgrade_restores_partial_index(self, db_session):
        """Test that downgrade restores the original partial unique index."""
        # Run upgrade then downgrade
        await migration_004.upgrade()
        await migration_004.downgrade()

        # Verify partial unique index was restored
        result = await db_session.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'aml_transaction_labels'
              AND indexname = 'idx_aml_transaction_labels_uniq_transaction'
        """))
        index = result.fetchone()

        assert index is not None, "Partial unique index should be restored"

    async def test_downgrade_allows_duplicates_again(self, db_session):
        """Test that duplicates are allowed again after downgrade."""
        # Run upgrade then downgrade
        await migration_004.upgrade()
        await migration_004.downgrade()

        # Insert first record
        txn_id = str(uuid4())
        tenant_id = "tenant_003"

        label1 = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,
            tenant_id=tenant_id,
            job_id="job_001",
            risk_level=AMLRiskLevel.LOW,
            typology="FRAUD",
            confidence_score=Decimal("0.65"),
            ai_reasoning="First label",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_deleted=False
        )
        db_session.add(label1)
        await db_session.commit()

        # Insert duplicate (should succeed after downgrade)
        label2 = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,  # Same transaction_id
            tenant_id=tenant_id,    # Same tenant_id
            job_id="job_002",
            risk_level=AMLRiskLevel.MEDIUM,
            typology="ML",
            confidence_score=Decimal("0.70"),
            ai_reasoning="Second label (duplicate)",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_deleted=False
        )
        db_session.add(label2)

        # Should succeed (no unique constraint)
        try:
            await db_session.commit()
        except Exception as e:
            pytest.fail(f"Duplicate insertion should succeed after downgrade but failed: {e}")

        # Verify both records exist
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id AND is_deleted = FALSE
        """), {"txn_id": txn_id, "tenant_id": tenant_id})
        count = result.scalar()
        assert count == 2, "Both records should exist after downgrade"


@pytest.mark.integration
class TestMigration004EdgeCases:
    """Test migration 004 edge cases and error scenarios."""

    async def test_upgrade_with_many_duplicates(self, db_session):
        """Test migration handles large number of duplicates efficiently."""
        # Insert 10 duplicates for same transaction+tenant
        txn_id = str(uuid4())
        tenant_id = "tenant_004"

        for i in range(10):
            label = AMLTransactionLabel(
                id=str(uuid4()),
                transaction_id=txn_id,
                tenant_id=tenant_id,
                job_id=f"job_{i:03d}",
                risk_level=AMLRiskLevel.HIGH,
                typology="ML",
                confidence_score=Decimal("0.80"),
                ai_reasoning=f"Reasoning {i}",
                expert_review_status=AMLExpertReviewStatus.PENDING,
                is_deleted=False
            )
            db_session.add(label)

        await db_session.commit()

        # Run upgrade
        await migration_004.upgrade()

        # Verify only 1 active record remains
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id AND is_deleted = FALSE
        """), {"txn_id": txn_id, "tenant_id": tenant_id})
        assert result.scalar() == 1, "Should have 1 active record"

        # Verify 9 were soft-deleted
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id AND is_deleted = TRUE
        """), {"txn_id": txn_id, "tenant_id": tenant_id})
        assert result.scalar() == 9, "Should have 9 soft-deleted records"

    async def test_upgrade_preserves_most_recent(self, db_session):
        """Test that migration keeps the most recent duplicate."""
        import asyncio

        # Insert duplicates with different timestamps
        txn_id = str(uuid4())
        tenant_id = "tenant_005"

        # Oldest record
        label_old = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,
            tenant_id=tenant_id,
            job_id="job_old",
            risk_level=AMLRiskLevel.LOW,
            typology="FRAUD",
            confidence_score=Decimal("0.50"),
            ai_reasoning="Old reasoning",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_deleted=False
        )
        db_session.add(label_old)
        await db_session.commit()

        # Small delay to ensure different timestamp
        await asyncio.sleep(0.1)

        # Newest record
        label_new = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,
            tenant_id=tenant_id,
            job_id="job_new",
            risk_level=AMLRiskLevel.CRITICAL,
            typology="TF",
            confidence_score=Decimal("0.95"),
            ai_reasoning="New reasoning (should be kept)",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_deleted=False
        )
        db_session.add(label_new)
        await db_session.commit()

        # Run upgrade
        await migration_004.upgrade()

        # Verify the newest record was kept
        result = await db_session.execute(text("""
            SELECT ai_reasoning FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id AND is_deleted = FALSE
        """), {"txn_id": txn_id, "tenant_id": tenant_id})
        kept_reasoning = result.scalar()

        assert kept_reasoning == "New reasoning (should be kept)", \
            "Migration should keep the most recent record"

    async def test_upgrade_different_tenants_same_transaction(self, db_session):
        """Test that same transaction_id across different tenants is allowed."""
        # Run upgrade first
        await migration_004.upgrade()

        # Same transaction_id, different tenant_id should be allowed
        txn_id = str(uuid4())

        label1 = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,
            tenant_id="tenant_A",
            job_id="job_001",
            risk_level=AMLRiskLevel.MEDIUM,
            typology="ML",
            confidence_score=Decimal("0.70"),
            ai_reasoning="Tenant A reasoning",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )
        db_session.add(label1)
        await db_session.commit()

        # Different tenant, same transaction (should succeed)
        label2 = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=txn_id,  # Same transaction_id
            tenant_id="tenant_B",   # Different tenant_id
            job_id="job_002",
            risk_level=AMLRiskLevel.HIGH,
            typology="TF",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Tenant B reasoning",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )
        db_session.add(label2)

        # Should succeed (different tenant_id)
        try:
            await db_session.commit()
        except Exception as e:
            pytest.fail(f"Same transaction_id with different tenant_id should be allowed: {e}")

        # Verify both records exist
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """), {"txn_id": txn_id})
        assert result.scalar() == 2, "Both records should exist (different tenants)"
