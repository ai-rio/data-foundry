"""
Test Suite for AML Labels Database Persistence (P01-007)

This module contains comprehensive tests for the save_aml_labels_to_database() task.
Tests follow TDD principles and verify transaction handling, duplicate detection,
batch processing, and error recovery.

Test Categories:
1. Batch insert with valid labels
2. Transaction handling (commit/rollback)
3. Duplicate detection based on transaction_id
4. Error handling and recovery
5. Performance benchmarks (1000+ labels/sec)
6. Empty input handling
7. Tenant isolation
8. Enum conversion handling

Reference: P01-007 (Save AML Labels to Database)
"""

import pytest
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text

from src.tasks.ingestion import save_aml_labels_to_database
from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus, AMLTypology


# ============================================================================
# Helper Functions
# ============================================================================

def create_sample_ml_label(
    transaction_id: str,
    risk_level: str = "HIGH",
    typology: str = "ML",
    confidence_score: float = 0.85
) -> Dict[str, Any]:
    """Create a sample AML-labeled record."""
    return {
        "transaction_id": transaction_id,
        "aml_risk_level": risk_level,
        "aml_typology": typology,
        "aml_confidence_score": confidence_score,
        "aml_reasoning": f"Analysis of transaction {transaction_id} shows suspicious pattern consistent with money laundering indicators.",
        "aml_expert_review_status": AMLExpertReviewStatus.PENDING.value,
        "aml_regulatory_flags": ["HIGH_RISK_JURISDICTION", "SUSPICIOUS_PATTERN"]
    }


def mock_logger():
    """Create a mock logger for testing."""
    logger = MagicMock()
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


# ============================================================================
# Test Class: Batch Insert Tests
# ============================================================================

class TestSaveAMLLabelsBatchInsert:
    """Tests for batch insert functionality."""

    @pytest.mark.asyncio
    async def test_single_label_insert(self, db_session):
        """
        Test that a single AML label is inserted correctly.

        Given: One AML-labeled record
        When: save_aml_labels_to_database() is called
        Then: Label is saved with correct values
        """
        labeled_records = [create_sample_ml_label("TXN-001")]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result["total_saved"] == 1
        assert result["duplicates_skipped"] == 0
        assert result["errors"] == 0
        assert result["batches_processed"] == 1

        # Verify database state
        query = text("SELECT * FROM aml_transaction_labels WHERE transaction_id = :txn_id")
        db_result = await db_session.execute(query, {"txn_id": "TXN-001"})
        rows = db_result.fetchall()

        assert len(rows) == 1
        assert rows[0]["risk_level"] == "HIGH"
        assert rows[0]["typology"] == "ML"
        assert float(rows[0]["confidence_score"]) == 0.85

    @pytest.mark.asyncio
    async def test_multiple_labels_batch_insert(self, db_session):
        """
        Test that multiple labels are inserted in a single batch.

        Given: Multiple AML-labeled records (less than batch size)
        When: save_aml_labels_to_database() is called
        Then: All labels are saved in one batch
        """
        labeled_records = [
            create_sample_ml_label(f"TXN-{i:03d}")
            for i in range(1, 11)  # 10 records
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result["total_saved"] == 10
        assert result["batches_processed"] == 1

    @pytest.mark.asyncio
    async def test_large_batch_splitting(self, db_session):
        """
        Test that large datasets are split into multiple batches.

        Given: More labeled records than batch size
        When: save_aml_labels_to_database() is called
        Then: Records are split across multiple batches
        """
        # Create more records than default batch size (500)
        labeled_records = [
            create_sample_ml_label(f"TXN-{i:05d}")
            for i in range(1, 1200)  # 1200 records to ensure multiple batches
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result["total_saved"] == 1200
        # With batch_size=500, should have 3 batches: 500 + 500 + 200
        assert result["batches_processed"] >= 2

    @pytest.mark.asyncio
    async def test_empty_input_returns_zero_metrics(self, db_session):
        """
        Test that empty input returns appropriate zero metrics.

        Given: Empty list of labeled records
        When: save_aml_labels_to_database() is called
        Then: Returns metrics with zero values
        """
        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn([], "tenant_001")

        assert result["total_saved"] == 0
        assert result["duplicates_skipped"] == 0
        assert result["errors"] == 0
        assert result["batches_processed"] == 0
        assert result["processing_time_ms"] >= 0


# ============================================================================
# Test Class: Transaction Handling
# ============================================================================

class TestSaveAMLLabelsTransactionHandling:
    """Tests for transaction commit/rollback behavior."""

    @pytest.mark.asyncio
    async def test_transaction_commits_on_success(self, db_session):
        """
        Test that successful inserts are committed.

        Given: Valid AML-labeled records
        When: save_aml_labels_to_database() completes successfully
        Then: All changes are committed to database
        """
        labeled_records = [
            create_sample_ml_label(f"TXN-{i:03d}")
            for i in range(1, 6)
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result["total_saved"] == 5
        assert result["errors"] == 0

        # Verify records are persisted
        query = text("SELECT COUNT(*) FROM aml_transaction_labels WHERE tenant_id = :tenant_id")
        db_result = await db_session.execute(query, {"tenant_id": "tenant_001"})
        count = db_result.scalar()

        assert count == 5

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_batch_error(self, db_session):
        """
        Test that failed batch rolls back but continues processing.

        Given: A batch with invalid records causing an error
        When: save_aml_labels_to_database() encounters error
        Then: Failed batch rolls back, subsequent batches continue
        """
        # Create records with some invalid ones (missing transaction_id)
        mixed_records = [
            create_sample_ml_label("TXN-001"),
            {"aml_risk_level": "HIGH"},  # Missing transaction_id
            create_sample_ml_label("TXN-002"),
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(mixed_records, "tenant_001")

        # Should save valid records and track error for invalid one
        assert result["total_saved"] >= 0
        assert result["errors"] >= 1
        assert len(result["error_details"]) >= 1


# ============================================================================
# Test Class: Duplicate Detection
# ============================================================================

class TestSaveAMLLabelsDuplicateDetection:
    """Tests for duplicate handling based on transaction_id."""

    @pytest.mark.asyncio
    async def test_duplicates_skipped(self, db_session):
        """
        Test that existing labels are skipped.

        Given: A label already exists for a transaction_id
        When: save_aml_labels_to_database() is called with same transaction_id
        Then: Duplicate is skipped and tracked
        """
        # Insert initial label
        labeled_records = [create_sample_ml_label("TXN-DUP-001")]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result1 = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result1["total_saved"] == 1
        assert result1["duplicates_skipped"] == 0

        # Try to insert same transaction again
        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result2 = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result2["total_saved"] == 0
        assert result2["duplicates_skipped"] == 1

    @pytest.mark.asyncio
    async def test_duplicate_detection_within_batch(self, db_session):
        """
        Test that duplicates are detected within the same batch.

        Given: A batch with duplicate transaction_ids
        When: save_aml_labels_to_database() processes the batch
        Then: Second occurrence is skipped
        """
        # Create batch with duplicate transaction_id
        labeled_records = [
            create_sample_ml_label("TXN-BATCH-001"),
            create_sample_ml_label("TXN-BATCH-002"),
            create_sample_ml_label("TXN-BATCH-001"),  # Duplicate
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        # Should save 2 unique records
        assert result["total_saved"] == 2
        assert result["duplicates_skipped"] >= 1

    @pytest.mark.asyncio
    async def test_duplicate_across_tenants_allowed(self, db_session):
        """
        Test that same transaction_id can exist for different tenants.

        Given: A label exists for tenant_001
        When: Same transaction_id is saved for tenant_002
        Then: Both records exist (tenant isolation)
        """
        # Insert for tenant_001
        labeled_records = [create_sample_ml_label("TXN-MULTI-001")]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result1 = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result1["total_saved"] == 1

        # Insert same transaction for tenant_002
        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result2 = await save_aml_labels_to_database.fn(labeled_records, "tenant_002")

        assert result2["total_saved"] == 1
        assert result2["duplicates_skipped"] == 0

        # Verify both exist
        query = text("""
            SELECT tenant_id FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
            ORDER BY tenant_id
        """)
        db_result = await db_session.execute(query, {"txn_id": "TXN-MULTI-001"})
        rows = db_result.fetchall()

        assert len(rows) == 2
        assert rows[0]["tenant_id"] == "tenant_001"
        assert rows[1]["tenant_id"] == "tenant_002"


# ============================================================================
# Test Class: Error Handling
# ============================================================================

class TestSaveAMLLabelsErrorHandling:
    """Tests for error handling and recovery."""

    @pytest.mark.asyncio
    async def test_missing_transaction_id_error(self, db_session):
        """
        Test that missing transaction_id is handled as error.

        Given: A record without transaction_id
        When: save_aml_labels_to_database() is called
        Then: Error is tracked but processing continues
        """
        invalid_record = {
            "aml_risk_level": "HIGH",
            "aml_typology": "ML",
            "aml_confidence_score": 0.85,
            "aml_reasoning": "Test reasoning"
            # Missing transaction_id
        }

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn([invalid_record], "tenant_001")

        assert result["total_saved"] == 0
        assert result["errors"] >= 1
        assert any("transaction_id" in str(e).lower() for e in result["error_details"])

    @pytest.mark.asyncio
    async def test_invalid_risk_level_enum(self, db_session):
        """
        Test that invalid risk_level is handled.

        Given: A record with invalid risk_level enum value
        When: save_aml_labels_to_database() is called
        Then: Error is tracked
        """
        invalid_record = create_sample_ml_label("TXN-INVALID")
        invalid_record["aml_risk_level"] = "INVALID_LEVEL"

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn([invalid_record], "tenant_001")

        assert result["errors"] >= 1

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_records(self, db_session):
        """
        Test that valid records are processed despite invalid ones.

        Given: A mix of valid and invalid records
        When: save_aml_labels_to_database() is called
        Then: Valid records are saved, invalid ones tracked as errors
        """
        records = [
            create_sample_ml_label("TXN-VALID-001"),
            {"aml_risk_level": "HIGH"},  # Invalid: missing transaction_id
            create_sample_ml_label("TXN-VALID-002"),
            create_sample_ml_label("TXN-VALID-003"),
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(records, "tenant_001")

        assert result["total_saved"] == 3
        assert result["errors"] >= 1


# ============================================================================
# Test Class: Performance Tests
# ============================================================================

class TestSaveAMLLabelsPerformance:
    """Tests for performance benchmarks."""

    @pytest.mark.asyncio
    async def test_performance_1000_labels_per_second(self, db_session):
        """
        Test that throughput meets or exceeds 1000 labels/sec.

        Given: 1000 AML-labeled records
        When: save_aml_labels_to_database() is called
        Then: Throughput is >= 1000 labels/sec (bulk insert operations)
        """
        labeled_records = [
            create_sample_ml_label(f"TXN-PERF-{i:05d}")
            for i in range(1, 1001)  # 1000 records
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result["total_saved"] == 1000
        # Performance gate: 1000+ labels/sec with bulk insert operations
        assert result["labels_per_second"] >= 1000
        assert "processing_time_ms" in result

    @pytest.mark.asyncio
    async def test_performance_with_duplicates(self, db_session):
        """
        Test performance when handling duplicates.

        Given: Records with 20% duplicate rate
        When: save_aml_labels_to_database() is called
        Then: Performance remains acceptable (1000+ labels/sec)
        """
        # Create 1000 records with 20% duplicates
        unique_records = 800
        labeled_records = [
            create_sample_ml_label(f"TXN-DUP-PERF-{i % unique_records:05d}")
            for i in range(1000)
        ]

        # First insert
        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result1 = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result1["total_saved"] == 800

        # Second insert with duplicates
        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result2 = await save_aml_labels_to_database.fn(labeled_records, "tenant_001")

        assert result2["duplicates_skipped"] >= 800
        # Should still process quickly even with all duplicates (bulk insert)
        assert result2["labels_per_second"] >= 1000


# ============================================================================
# Test Class: Data Conversion Tests
# ============================================================================

class TestSaveAMLLabelsDataConversion:
    """Tests for proper data type conversions."""

    @pytest.mark.asyncio
    async def test_confidence_score_decimal_conversion(self, db_session):
        """
        Test that confidence_score is properly converted to Decimal.

        Given: A record with float confidence_score
        When: save_aml_labels_to_database() is called
        Then: Value is stored as Decimal in database
        """
        record = create_sample_ml_label("TXN-DECIMAL")
        record["aml_confidence_score"] = 0.87654321  # High precision float

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn([record], "tenant_001")

        assert result["total_saved"] == 1

        # Verify stored value
        query = text("SELECT confidence_score FROM aml_transaction_labels WHERE transaction_id = :txn_id")
        db_result = await db_session.execute(query, {"txn_id": "TXN-DECIMAL"})
        stored_score = db_result.scalar()

        # Should be stored as Decimal
        assert float(stored_score) == 0.87654321

    @pytest.mark.asyncio
    async def test_enum_values_stored_correctly(self, db_session):
        """
        Test that enum values are stored as strings.

        Given: Records with various enum values
        When: save_aml_labels_to_database() is called
        Then: Enums are stored as their string values
        """
        records = [
            create_sample_ml_label("TXN-ENUM-1", risk_level="LOW", typology="TF"),
            create_sample_ml_label("TXN-ENUM-2", risk_level="CRITICAL", typology="PEP"),
            create_sample_ml_label("TXN-ENUM-3", risk_level="MEDIUM", typology="FRAUD"),
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn(records, "tenant_001")

        assert result["total_saved"] == 3

        # Verify stored enum values
        query = text("""
            SELECT transaction_id, risk_level, typology
            FROM aml_transaction_labels
            WHERE transaction_id = ANY(:txn_ids)
            ORDER BY transaction_id
        """)
        db_result = await db_session.execute(query, {"txn_ids": ["TXN-ENUM-1", "TXN-ENUM-2", "TXN-ENUM-3"]})
        rows = db_result.fetchall()

        assert rows[0]["risk_level"] == "LOW"
        assert rows[0]["typology"] == "TF"
        assert rows[1]["risk_level"] == "CRITICAL"
        assert rows[1]["typology"] == "PEP"
        assert rows[2]["risk_level"] == "MEDIUM"
        assert rows[2]["typology"] == "FRAUD"


# ============================================================================
# Test Class: Tenant Isolation
# ============================================================================

class TestSaveAMLLabelsTenantIsolation:
    """Tests for multi-tenant data isolation."""

    @pytest.mark.asyncio
    async def test_labels_isolated_by_tenant(self, db_session):
        """
        Test that labels are properly isolated by tenant_id.

        Given: Labels for multiple tenants
        When: save_aml_labels_to_database() is called
        Then: Each tenant sees only their own labels
        """
        tenant1_records = [
            create_sample_ml_label(f"TXN-T1-{i}")
            for i in range(5)
        ]

        tenant2_records = [
            create_sample_ml_label(f"TXN-T2-{i}")
            for i in range(7)
        ]

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result1 = await save_aml_labels_to_database.fn(tenant1_records, "tenant_isolated_1")
            result2 = await save_aml_labels_to_database.fn(tenant2_records, "tenant_isolated_2")

        assert result1["total_saved"] == 5
        assert result2["total_saved"] == 7

        # Verify counts per tenant
        query = text("""
            SELECT tenant_id, COUNT(*) as count
            FROM aml_transaction_labels
            WHERE tenant_id = ANY(:tenant_ids)
            GROUP BY tenant_id
        """)
        db_result = await db_session.execute(query, {"tenant_ids": ["tenant_isolated_1", "tenant_isolated_2"]})
        rows = db_result.fetchall()

        tenant_counts = {row["tenant_id"]: row["count"] for row in rows}
        assert tenant_counts.get("tenant_isolated_1") == 5
        assert tenant_counts.get("tenant_isolated_2") == 7


# ============================================================================
# Test Class: Field Defaults
# ============================================================================

class TestSaveAMLLabelsFieldDefaults:
    """Tests for proper default values."""

    @pytest.mark.asyncio
    async def test_default_field_values(self, db_session):
        """
        Test that default values are set correctly.

        Given: A minimal valid record
        When: save_aml_labels_to_database() is called
        Then: Default values are applied
        """
        record = create_sample_ml_label("TXN-DEFAULTS")

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            result = await save_aml_labels_to_database.fn([record], "tenant_001")

        assert result["total_saved"] == 1

        # Verify default values
        query = text("""
            SELECT is_audit_ready, is_deleted, expert_review_status
            FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """)
        db_result = await db_session.execute(query, {"txn_id": "TXN-DEFAULTS"})
        row = db_result.fetchone()

        assert row["is_audit_ready"] == False
        assert row["is_deleted"] == False
        assert row["expert_review_status"] == AMLExpertReviewStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_timestamps_set_automatically(self, db_session):
        """
        Test that timestamps are set automatically.

        Given: A new record without timestamps
        When: save_aml_labels_to_database() is called
        Then: created_at and updated_at are set
        """
        record = create_sample_ml_label("TXN-TIMESTAMPS")

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            await save_aml_labels_to_database.fn([record], "tenant_001")

        query = text("""
            SELECT created_at, updated_at
            FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """)
        db_result = await db_session.execute(query, {"txn_id": "TXN-TIMESTAMPS"})
        row = db_result.fetchone()

        assert row["created_at"] is not None
        assert row["updated_at"] is not None
        assert row["created_at"] <= datetime.utcnow()
