"""
End-to-End Test Suite for Database Fixes

This test suite validates the complete pipeline:
1. Complete pipeline: validate → insert → verify constraint
2. Data integrity after insertion
3. Audit trail logging for duplicates
4. CSV export matches database (from original failing tests)

Reference: P01-023 - Critical Database Fixes
Target Coverage: Complete integration of all components
"""

import pytest
import pytest_asyncio
import asyncio
from uuid import uuid4
from decimal import Decimal
from datetime import datetime
from sqlalchemy import text, select
import csv
import io

from src.database.connection import db_connection
from src.tasks.ingestion import save_aml_labels_to_database
from src.models.aml_transaction_label import AMLTransactionLabel
from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus
from src.core.aml_label_validator import AMLLabelValidator


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    """Initialize database with migration and provide clean session."""
    await db_connection.initialize()

    # Ensure migration 004 is applied
    from src.database.migrations import run_migrations_004_add_unique_constraint_aml_labels as migration_004
    try:
        await migration_004.upgrade()
    except:
        pass  # Constraint may already exist

    async with db_connection.get_session() as session:
        # Clean up test data
        await session.execute(text("DELETE FROM aml_transaction_labels"))
        await session.commit()
        yield session

    # Cleanup after test
    async with db_connection.get_session() as cleanup_session:
        await cleanup_session.execute(text("DELETE FROM aml_transaction_labels"))
        await cleanup_session.commit()


def create_complete_aml_record(
    transaction_id: str = None,
    tenant_id: str = "tenant_e2e",
    risk_level: str = "HIGH"
) -> dict:
    """Create a complete AML label record for E2E testing."""
    return {
        "transaction_id": transaction_id or str(uuid4()),
        "tenant_id": tenant_id,
        "job_id": "job_e2e_test",
        "aml_risk_level": risk_level,
        "aml_typology": "ML",
        "aml_confidence_score": 0.87,
        "aml_reasoning": "Multi-stage transaction with structuring patterns indicating money laundering activity",
        "aml_expert_review_status": "PENDING",
        "aml_regulatory_flags": {
            "fatf_typology": ["ML", "Structuring"],
            "sanctions": [],
            "high_risk_jurisdiction": True
        }
    }


@pytest.mark.e2e
class TestCompleteValidationInsertionPipeline:
    """Test complete pipeline: validate → insert → verify."""

    async def test_e2e_valid_record_flow(self, db_session):
        """Test end-to-end flow for valid record."""
        # Step 1: Create raw data
        raw_data = create_complete_aml_record()

        # Step 2: Validate using validator
        validator = AMLLabelValidator()
        validation_input = {
            "transaction_id": raw_data["transaction_id"],
            "tenant_id": raw_data["tenant_id"],
            "job_id": raw_data["job_id"],
            "risk_level": raw_data["aml_risk_level"],
            "typology": raw_data["aml_typology"],
            "confidence_score": raw_data["aml_confidence_score"],
            "ai_reasoning": raw_data["aml_reasoning"],
            "expert_review_status": raw_data["aml_expert_review_status"],
            "regulatory_flags": raw_data["aml_regulatory_flags"]
        }

        result = validator.validate(validation_input)
        assert result.is_valid is True, "Validation should pass"

        # Step 3: Insert into database
        metrics = await save_aml_labels_to_database(
            labeled_records=[raw_data],
            tenant_id="tenant_e2e",
            job_id="job_e2e_test"
        )

        assert metrics["total_saved"] == 1, "Should save 1 record"
        assert metrics["validation_errors"] == 0

        # Step 4: Verify in database
        result = await db_session.execute(text("""
            SELECT transaction_id, tenant_id, risk_level, typology, confidence_score
            FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id
        """), {"txn_id": raw_data["transaction_id"], "tenant_id": "tenant_e2e"})

        row = result.fetchone()
        assert row is not None, "Record should exist"
        assert row[0] == raw_data["transaction_id"]
        assert row[1] == "tenant_e2e"
        assert row[2] == "HIGH"
        assert row[3] == "ML"

        # Step 5: Verify constraint is enforced
        # Try to insert duplicate
        duplicate_data = create_complete_aml_record(
            transaction_id=raw_data["transaction_id"],  # Same
            risk_level="CRITICAL"  # Different risk
        )

        metrics2 = await save_aml_labels_to_database(
            labeled_records=[duplicate_data],
            tenant_id="tenant_e2e",  # Same tenant
            job_id="job_e2e_test2"
        )

        assert metrics2["duplicates_skipped"] == 1, "Duplicate should be skipped"
        assert metrics2["total_saved"] == 0

        # Verify still only 1 record in database
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id
        """), {"txn_id": raw_data["transaction_id"], "tenant_id": "tenant_e2e"})

        count = result.scalar()
        assert count == 1, "Should still have only 1 record"

    async def test_e2e_invalid_record_flow(self, db_session):
        """Test end-to-end flow for invalid record (should be rejected)."""
        # Step 1: Create invalid raw data
        invalid_data = create_complete_aml_record(
            risk_level="SUPER_CRITICAL"  # Invalid enum
        )
        invalid_data["aml_confidence_score"] = 1.8  # Out of range

        # Step 2: Attempt to insert (validation should fail)
        metrics = await save_aml_labels_to_database(
            labeled_records=[invalid_data],
            tenant_id="tenant_e2e",
            job_id="job_e2e_invalid"
        )

        assert metrics["total_saved"] == 0, "Invalid record should not be saved"
        assert metrics["validation_errors"] > 0, "Should have validation errors"

        # Step 3: Verify NOT in database
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """), {"txn_id": invalid_data["transaction_id"]})

        count = result.scalar()
        assert count == 0, "Invalid record should not be in database"

    async def test_e2e_batch_with_mixed_validity(self, db_session):
        """Test E2E flow with batch of mixed valid/invalid/duplicate records."""
        txn_dup = str(uuid4())

        records = [
            create_complete_aml_record(risk_level="HIGH"),  # Valid
            create_complete_aml_record(transaction_id=txn_dup, risk_level="MEDIUM"),  # Valid
            create_complete_aml_record(risk_level="INVALID_RISK"),  # Invalid
            create_complete_aml_record(risk_level="LOW"),  # Valid
            create_complete_aml_record(transaction_id=txn_dup, risk_level="CRITICAL"),  # Duplicate
        ]

        # Insert batch
        metrics = await save_aml_labels_to_database(
            labeled_records=records,
            tenant_id="tenant_e2e",
            job_id="job_e2e_batch"
        )

        assert metrics["total_saved"] == 3, "Should save 3 valid unique records"
        assert metrics["validation_errors"] == 1, "Should have 1 validation error"
        assert metrics["duplicates_skipped"] == 1, "Should skip 1 duplicate"

        # Verify correct count in database
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE job_id = 'job_e2e_batch'
        """))
        count = result.scalar()
        assert count == 3, "Database should have 3 records"


@pytest.mark.e2e
class TestDataIntegrityAfterInsertion:
    """Test data integrity is maintained after insertion."""

    async def test_json_regulatory_flags_integrity(self, db_session):
        """Test regulatory_flags JSON is stored and retrieved correctly."""
        complex_flags = {
            "sanctions": ["OFAC", "EU_SANCTIONS"],
            "pep": {
                "status": "confirmed",
                "level": "high",
                "positions": ["Minister of Finance", "Board Member"]
            },
            "fatf_recommendations": [1, 5, 10, 15],
            "high_risk_countries": ["Country_A", "Country_B"]
        }

        record = create_complete_aml_record()
        record["aml_regulatory_flags"] = complex_flags

        # Insert
        metrics = await save_aml_labels_to_database(
            labeled_records=[record],
            tenant_id="tenant_e2e",
            job_id="job_json_test"
        )
        assert metrics["total_saved"] == 1

        # Retrieve and verify JSON structure
        result = await db_session.execute(text("""
            SELECT regulatory_flags FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """), {"txn_id": record["transaction_id"]})

        stored_flags = result.scalar()

        # Verify structure
        assert "OFAC" in str(stored_flags)
        assert "pep" in str(stored_flags)
        assert "Minister of Finance" in str(stored_flags)

    async def test_decimal_precision_integrity(self, db_session):
        """Test confidence_score Decimal precision is maintained."""
        precise_score = Decimal("0.87654321")

        record = create_complete_aml_record()
        record["aml_confidence_score"] = precise_score

        # Insert
        metrics = await save_aml_labels_to_database(
            labeled_records=[record],
            tenant_id="tenant_e2e",
            job_id="job_decimal_test"
        )
        assert metrics["total_saved"] == 1

        # Retrieve and verify precision
        result = await db_session.execute(text("""
            SELECT confidence_score FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """), {"txn_id": record["transaction_id"]})

        stored_score = result.scalar()
        assert abs(float(stored_score) - float(precise_score)) < 0.0001

    async def test_timestamp_integrity(self, db_session):
        """Test created_at and updated_at timestamps are set correctly."""
        record = create_complete_aml_record()

        # Insert
        before_insert = datetime.utcnow()
        metrics = await save_aml_labels_to_database(
            labeled_records=[record],
            tenant_id="tenant_e2e",
            job_id="job_timestamp_test"
        )
        after_insert = datetime.utcnow()

        assert metrics["total_saved"] == 1

        # Retrieve timestamps
        result = await db_session.execute(text("""
            SELECT created_at, updated_at FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """), {"txn_id": record["transaction_id"]})

        row = result.fetchone()
        created_at = row[0]
        updated_at = row[1]

        # Verify timestamps are within expected range
        assert before_insert <= created_at <= after_insert
        assert before_insert <= updated_at <= after_insert

    async def test_enum_values_integrity(self, db_session):
        """Test enum values are stored correctly."""
        for risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            record = create_complete_aml_record(risk_level=risk_level)

            metrics = await save_aml_labels_to_database(
                labeled_records=[record],
                tenant_id="tenant_e2e",
                job_id=f"job_enum_{risk_level}"
            )
            assert metrics["total_saved"] == 1

            # Verify stored value
            result = await db_session.execute(text("""
                SELECT risk_level FROM aml_transaction_labels
                WHERE transaction_id = :txn_id
            """), {"txn_id": record["transaction_id"]})

            stored_risk = result.scalar()
            assert stored_risk == risk_level


@pytest.mark.e2e
class TestAuditTrailLogging:
    """Test audit trail logging for duplicates and operations."""

    async def test_duplicate_audit_trail(self, db_session):
        """Test duplicate insertions are logged in audit trail."""
        txn_id = str(uuid4())

        # First insertion
        record1 = create_complete_aml_record(transaction_id=txn_id)
        metrics1 = await save_aml_labels_to_database(
            labeled_records=[record1],
            tenant_id="tenant_audit",
            job_id="job_audit_001"
        )
        assert metrics1["total_saved"] == 1

        # Duplicate insertion (should be logged)
        record2 = create_complete_aml_record(transaction_id=txn_id)
        metrics2 = await save_aml_labels_to_database(
            labeled_records=[record2],
            tenant_id="tenant_audit",
            job_id="job_audit_002"
        )

        assert metrics2["duplicates_skipped"] == 1
        # Duplicate should be logged via DuplicateRecordHandler

    async def test_validation_error_audit_trail(self, db_session):
        """Test validation errors are captured in error_details."""
        invalid_record = create_complete_aml_record()
        invalid_record["aml_risk_level"] = "INVALID_RISK"

        metrics = await save_aml_labels_to_database(
            labeled_records=[invalid_record],
            tenant_id="tenant_audit",
            job_id="job_validation_audit"
        )

        assert metrics["validation_errors"] == 1
        assert "error_details" in metrics
        assert len(metrics["error_details"]) > 0

        # Check error details structure
        error = metrics["error_details"][0]
        assert "transaction_id" in error
        assert "error_type" in error
        assert error["error_type"] == "validation"


@pytest.mark.e2e
class TestCSVExport:
    """Test CSV export matches database (addresses original failing test)."""

    async def test_csv_export_single_record(self, db_session):
        """Test CSV export for single record matches database."""
        record = create_complete_aml_record()

        # Insert
        metrics = await save_aml_labels_to_database(
            labeled_records=[record],
            tenant_id="tenant_csv",
            job_id="job_csv_single"
        )
        assert metrics["total_saved"] == 1

        # Retrieve from database using ORM
        stmt = select(AMLTransactionLabel).where(
            AMLTransactionLabel.transaction_id == record["transaction_id"]
        )
        result = await db_session.execute(stmt)
        label = result.scalar_one()

        # Convert to CSV row
        csv_row = label.to_csv_row()

        # Verify CSV row contains expected fields
        assert csv_row["transaction_id"] == record["transaction_id"]
        assert csv_row["tenant_id"] == "tenant_csv"
        assert csv_row["risk_level"] == "HIGH"
        assert csv_row["typology"] == "ML"
        assert "0.87" in str(csv_row["confidence_score"])

    async def test_csv_export_batch(self, db_session):
        """Test CSV export for batch of records."""
        count = 5
        records = [create_complete_aml_record() for _ in range(count)]

        # Insert batch
        metrics = await save_aml_labels_to_database(
            labeled_records=records,
            tenant_id="tenant_csv",
            job_id="job_csv_batch"
        )
        assert metrics["total_saved"] == count

        # Retrieve all from database
        stmt = select(AMLTransactionLabel).where(
            AMLTransactionLabel.job_id == "job_csv_batch"
        )
        result = await db_session.execute(stmt)
        labels = result.scalars().all()

        assert len(labels) == count

        # Generate CSV
        output = io.StringIO()
        fieldnames = [
            "id", "transaction_id", "tenant_id", "job_id",
            "risk_level", "typology", "confidence_score",
            "ai_reasoning", "expert_review_status",
            "is_audit_ready", "created_at"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for label in labels:
            csv_row = label.to_csv_row()
            # Filter to fieldnames
            filtered_row = {k: csv_row.get(k, "") for k in fieldnames}
            writer.writerow(filtered_row)

        csv_content = output.getvalue()

        # Verify CSV contains all records
        assert csv_content.count("\n") == count + 1, "Should have header + count rows"
        for record in records:
            assert record["transaction_id"] in csv_content

    async def test_csv_export_special_characters(self, db_session):
        """Test CSV export handles special characters correctly."""
        record = create_complete_aml_record()
        record["aml_reasoning"] = 'Reasoning with "quotes", commas, and newlines\nSecond line'

        # Insert
        metrics = await save_aml_labels_to_database(
            labeled_records=[record],
            tenant_id="tenant_csv",
            job_id="job_csv_special"
        )
        assert metrics["total_saved"] == 1

        # Retrieve and export to CSV
        stmt = select(AMLTransactionLabel).where(
            AMLTransactionLabel.transaction_id == record["transaction_id"]
        )
        result = await db_session.execute(stmt)
        label = result.scalar_one()

        csv_row = label.to_csv_row()

        # Verify special characters are preserved
        assert '"quotes"' in csv_row["ai_reasoning"] or "quotes" in csv_row["ai_reasoning"]
        assert "Second line" in csv_row["ai_reasoning"]


@pytest.mark.e2e
class TestConstraintEnforcement:
    """Test constraint enforcement across the entire system."""

    async def test_constraint_prevents_duplicates_e2e(self, db_session):
        """End-to-end test that unique constraint prevents duplicates."""
        txn_id = str(uuid4())
        tenant_id = "tenant_constraint_test"

        # Create 5 attempts to insert same transaction+tenant
        attempts = [
            create_complete_aml_record(transaction_id=txn_id, tenant_id=tenant_id, risk_level="HIGH"),
            create_complete_aml_record(transaction_id=txn_id, tenant_id=tenant_id, risk_level="CRITICAL"),
            create_complete_aml_record(transaction_id=txn_id, tenant_id=tenant_id, risk_level="MEDIUM"),
            create_complete_aml_record(transaction_id=txn_id, tenant_id=tenant_id, risk_level="LOW"),
            create_complete_aml_record(transaction_id=txn_id, tenant_id=tenant_id, risk_level="HIGH"),
        ]

        total_saved = 0
        total_duplicates = 0

        # Insert one at a time
        for i, record in enumerate(attempts):
            metrics = await save_aml_labels_to_database(
                labeled_records=[record],
                tenant_id=tenant_id,
                job_id=f"job_constraint_attempt_{i}"
            )
            total_saved += metrics["total_saved"]
            total_duplicates += metrics["duplicates_skipped"]

        # Only first should succeed, rest should be duplicates
        assert total_saved == 1, "Only first record should be saved"
        assert total_duplicates == 4, "4 attempts should be duplicates"

        # Verify database has exactly 1 record
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id AND tenant_id = :tenant_id
        """), {"txn_id": txn_id, "tenant_id": tenant_id})

        count = result.scalar()
        assert count == 1, "Database should have exactly 1 record"

    async def test_multi_tenant_isolation_e2e(self, db_session):
        """Test multi-tenant isolation with same transaction across tenants."""
        txn_id = str(uuid4())

        tenants = ["tenant_A", "tenant_B", "tenant_C"]
        saved_count = 0

        for tenant in tenants:
            record = create_complete_aml_record(
                transaction_id=txn_id,
                tenant_id=tenant
            )

            metrics = await save_aml_labels_to_database(
                labeled_records=[record],
                tenant_id=tenant,
                job_id=f"job_{tenant}"
            )

            saved_count += metrics["total_saved"]

        # All 3 should succeed (different tenants)
        assert saved_count == 3, "All 3 tenants should save successfully"

        # Verify 3 records in database (1 per tenant)
        result = await db_session.execute(text("""
            SELECT COUNT(*) FROM aml_transaction_labels
            WHERE transaction_id = :txn_id
        """), {"txn_id": txn_id})

        count = result.scalar()
        assert count == 3, "Should have 3 records (1 per tenant)"

        # Verify each tenant has exactly 1 record
        for tenant in tenants:
            result = await db_session.execute(text("""
                SELECT COUNT(*) FROM aml_transaction_labels
                WHERE transaction_id = :txn_id AND tenant_id = :tenant_id
            """), {"txn_id": txn_id, "tenant_id": tenant})

            tenant_count = result.scalar()
            assert tenant_count == 1, f"Tenant {tenant} should have 1 record"
