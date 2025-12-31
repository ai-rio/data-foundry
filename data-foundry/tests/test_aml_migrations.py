#!/usr/bin/env python3
"""
Test script for AML migrations P01-002.

This script tests:
1. Migration 001: aml_transaction_labels table creation
2. Migration 002: aml_audit_trail tables creation
3. Rollback functionality for both migrations
4. Schema correctness (columns, indexes, constraints)
5. Idempotency (can re-run safely)

Usage:
    python test_aml_migrations.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text, inspect
from src.database.connection import db_connection
from src.core.config import settings


class MigrationTester:
    """Test harness for AML migrations."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def assert_true(self, condition: bool, message: str):
        """Assert a condition is true."""
        if condition:
            print(f"  ✓ {message}")
            self.passed += 1
        else:
            print(f"  ✗ {message}")
            self.failed += 1
            self.errors.append(message)

    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        async with db_connection.get_session() as session:
            result = await session.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = '{table_name}'
                )
            """))
            return result.scalar()

    async def index_exists(self, index_name: str) -> bool:
        """Check if an index exists."""
        async with db_connection.get_session() as session:
            result = await session.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE indexname = '{index_name}'
                )
            """))
            return result.scalar()

    async def constraint_exists(self, table_name: str, constraint_name: str) -> bool:
        """Check if a constraint exists."""
        async with db_connection.get_session() as session:
            result = await session.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = '{table_name}'
                    AND constraint_name = '{constraint_name}'
                )
            """))
            return result.scalar()

    async def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists."""
        async with db_connection.get_session() as session:
            result = await session.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                    AND column_name = '{column_name}'
                )
            """))
            return result.scalar()

    async def get_column_type(self, table_name: str, column_name: str) -> str:
        """Get the data type of a column."""
        async with db_connection.get_session() as session:
            result = await session.execute(text(f"""
                SELECT data_type, udt_name
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                AND column_name = '{column_name}'
            """))
            row = result.first()
            return row[0] if row else None

    async def test_migration_001_upgrade(self):
        """Test migration 001 upgrade."""
        print("\n" + "="*70)
        print("TEST: Migration 001 - Upgrade (aml_transaction_labels)")
        print("="*70)

        # Import and run migration
        from src.database.migrations import add_aml_transaction_labels_table as m001
        await m001.upgrade()

        # Test table exists
        exists = await self.table_exists("aml_transaction_labels")
        self.assert_true(exists, "Table 'aml_transaction_labels' created")

        # Test columns exist
        columns = [
            "id", "transaction_id", "tenant_id", "risk_level", "typology",
            "confidence_score", "ai_reasoning", "expert_review_status",
            "regulatory_flags", "is_audit_ready", "is_deleted",
            "created_at", "updated_at", "version_id"
        ]
        for col in columns:
            exists = await self.column_exists("aml_transaction_labels", col)
            self.assert_true(exists, f"Column '{col}' exists")

        # Test indexes exist
        indexes = [
            "idx_aml_transaction_labels_tenant_id",
            "idx_aml_transaction_labels_transaction_id",
            "idx_aml_transaction_labels_risk_level",
            "idx_aml_transaction_labels_expert_review_status",
            "idx_aml_transaction_labels_created_at",
            "idx_aml_transaction_labels_is_deleted",
            "idx_aml_transaction_labels_uniq_transaction",
        ]
        for idx in indexes:
            exists = await self.index_exists(idx)
            self.assert_true(exists, f"Index '{idx}' created")

        # Test constraints exist
        constraints = [
            "check_aml_confidence_score",
            "check_aml_risk_level",
            "check_aml_expert_review_status",
        ]
        for constraint in constraints:
            exists = await self.constraint_exists("aml_transaction_labels", constraint)
            self.assert_true(exists, f"Constraint '{constraint}' created")

        # Test data types
        confidence_type = await self.get_column_type("aml_transaction_labels", "confidence_score")
        self.assert_true(confidence_type == "numeric", f"confidence_score is DECIMAL/NUMERIC (got: {confidence_type})")

        regulatory_type = await self.get_column_type("aml_transaction_labels", "regulatory_flags")
        self.assert_true(regulatory_type == "jsonb", f"regulatory_flags is JSONB (got: {regulatory_type})")

    async def test_migration_001_idempotency(self):
        """Test that migration 001 is idempotent."""
        print("\n" + "="*70)
        print("TEST: Migration 001 - Idempotency (can re-run safely)")
        print("="*70)

        # Run migration again
        from src.database.migrations import add_aml_transaction_labels_table as m001

        try:
            await m001.upgrade()
            self.assert_true(True, "Migration 001 can be re-run without errors")
        except Exception as e:
            self.assert_true(False, f"Migration 001 idempotency failed: {str(e)}")

    async def test_migration_001_downgrade(self):
        """Test migration 001 downgrade."""
        print("\n" + "="*70)
        print("TEST: Migration 001 - Downgrade (rollback)")
        print("="*70)

        from src.database.migrations import add_aml_transaction_labels_table as m001
        await m001.downgrade()

        # Test table dropped
        exists = await self.table_exists("aml_transaction_labels")
        self.assert_true(not exists, "Table 'aml_transaction_labels' dropped")

        # Test indexes dropped
        exists = await self.index_exists("idx_aml_transaction_labels_tenant_id")
        self.assert_true(not exists, "Indexes dropped")

    async def test_migration_002_upgrade(self):
        """Test migration 002 upgrade."""
        print("\n" + "="*70)
        print("TEST: Migration 002 - Upgrade (audit trail tables)")
        print("="*70)

        # Run migration 001 first (dependency)
        from src.database.migrations import add_aml_transaction_labels_table as m001
        await m001.upgrade()

        # Run migration 002
        from src.database.migrations import add_aml_audit_trail_tables as m002
        await m002.upgrade()

        # Test tables exist
        tables = [
            "aml_expert_reviews",
            "aml_audit_reports",
            "aml_labeling_methodology",
        ]
        for table in tables:
            exists = await self.table_exists(table)
            self.assert_true(exists, f"Table '{table}' created")

        # Test aml_expert_reviews columns
        expert_columns = [
            "id", "aml_transaction_label_id", "tenant_id", "expert_id",
            "expert_decision", "reasoning", "confidence_level",
            "reviewed_at", "is_deleted", "created_at"
        ]
        for col in expert_columns:
            exists = await self.column_exists("aml_expert_reviews", col)
            self.assert_true(exists, f"aml_expert_reviews.{col} exists")

        # Test aml_audit_reports columns
        audit_columns = [
            "id", "tenant_id", "job_id", "transaction_count",
            "labeled_count", "expert_reviewed_count", "kappa_coefficient",
            "agreement_level", "generated_at", "report_url",
            "is_deleted", "created_at"
        ]
        for col in audit_columns:
            exists = await self.column_exists("aml_audit_reports", col)
            self.assert_true(exists, f"aml_audit_reports.{col} exists")

        # Test aml_labeling_methodology columns
        methodology_columns = [
            "id", "tenant_id", "version", "description",
            "risk_thresholds", "typologies", "regulatory_references",
            "created_by", "created_at", "status", "is_deleted"
        ]
        for col in methodology_columns:
            exists = await self.column_exists("aml_labeling_methodology", col)
            self.assert_true(exists, f"aml_labeling_methodology.{col} exists")

        # Test indexes
        expert_indexes = [
            "idx_aml_expert_reviews_tenant_id",
            "idx_aml_expert_reviews_label_id",
            "idx_aml_expert_reviews_expert_id",
            "idx_aml_expert_reviews_created_at",
            "idx_aml_expert_reviews_is_deleted",
        ]
        for idx in expert_indexes:
            exists = await self.index_exists(idx)
            self.assert_true(exists, f"Index '{idx}' created")

        audit_indexes = [
            "idx_aml_audit_reports_tenant_id",
            "idx_aml_audit_reports_job_id",
            "idx_aml_audit_reports_created_at",
            "idx_aml_audit_reports_is_deleted",
        ]
        for idx in audit_indexes:
            exists = await self.index_exists(idx)
            self.assert_true(exists, f"Index '{idx}' created")

        methodology_indexes = [
            "idx_aml_labeling_methodology_tenant_id",
            "idx_aml_labeling_methodology_version",
            "idx_aml_labeling_methodology_status",
            "idx_aml_labeling_methodology_is_deleted",
            "idx_aml_labeling_methodology_uniq",
        ]
        for idx in methodology_indexes:
            exists = await self.index_exists(idx)
            self.assert_true(exists, f"Index '{idx}' created")

        # Test constraints
        expert_constraints = [
            "check_aml_expert_confidence_level",
            "check_aml_expert_decision",
        ]
        for constraint in expert_constraints:
            exists = await self.constraint_exists("aml_expert_reviews", constraint)
            self.assert_true(exists, f"Constraint '{constraint}' created")

        audit_constraints = [
            "check_aml_audit_transaction_count",
            "check_aml_audit_labeled_count",
            "check_aml_audit_reviewed_count",
            "check_aml_audit_kappa_coefficient",
            "check_aml_audit_agreement_level",
        ]
        for constraint in audit_constraints:
            exists = await self.constraint_exists("aml_audit_reports", constraint)
            self.assert_true(exists, f"Constraint '{constraint}' created")

        methodology_constraints = [
            "check_aml_methodology_status",
        ]
        for constraint in methodology_constraints:
            exists = await self.constraint_exists("aml_labeling_methodology", constraint)
            self.assert_true(exists, f"Constraint '{constraint}' created")

    async def test_migration_002_idempotency(self):
        """Test that migration 002 is idempotent."""
        print("\n" + "="*70)
        print("TEST: Migration 002 - Idempotency (can re-run safely)")
        print("="*70)

        from src.database.migrations import add_aml_audit_trail_tables as m002

        try:
            await m002.upgrade()
            self.assert_true(True, "Migration 002 can be re-run without errors")
        except Exception as e:
            self.assert_true(False, f"Migration 002 idempotency failed: {str(e)}")

    async def test_migration_002_downgrade(self):
        """Test migration 002 downgrade."""
        print("\n" + "="*70)
        print("TEST: Migration 002 - Downgrade (rollback)")
        print("="*70)

        from src.database.migrations import add_aml_audit_trail_tables as m002
        await m002.downgrade()

        # Test tables dropped
        tables = [
            "aml_expert_reviews",
            "aml_audit_reports",
            "aml_labeling_methodology",
        ]
        for table in tables:
            exists = await self.table_exists(table)
            self.assert_true(not exists, f"Table '{table}' dropped")

    async def run_all_tests(self):
        """Run all migration tests."""
        print("\n" + "="*70)
        print("AML MIGRATIONS TEST SUITE - P01-002")
        print("="*70)
        print(f"Database: {settings.database_url_sync}")
        print("="*70)

        # Initialize database connection
        await db_connection.initialize()

        try:
            # Test migration 001
            await self.test_migration_001_upgrade()
            await self.test_migration_001_idempotency()
            await self.test_migration_001_downgrade()

            # Test migration 002
            await self.test_migration_002_upgrade()
            await self.test_migration_002_idempotency()
            await self.test_migration_002_downgrade()

        finally:
            # Cleanup: ensure we're in clean state
            await db_connection.close()

        # Print summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")

        if self.failed > 0:
            print("\nFailed tests:")
            for error in self.errors:
                print(f"  ✗ {error}")
            print("\n❌ TESTS FAILED")
            return False
        else:
            print("\n✅ ALL TESTS PASSED")
            return True


async def main():
    """Main entry point."""
    tester = MigrationTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
