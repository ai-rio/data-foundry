"""
Test suite for Database Error Handler - Error classification and handling

This test suite validates:
1. Unique constraint violation detection
2. Foreign key violation detection
3. Timeout error detection
4. Connection error detection
5. Error message clarity and user-friendliness
6. Retry eligibility determination

Reference: P01-023 - Critical Database Fixes
Target Coverage: >95% of error handler code
"""

import pytest
from unittest.mock import Mock

from src.core.database_error_handler import (
    DatabaseErrorHandler,
    DuplicateRecordHandler,
    DatabaseError,
    DatabaseErrorType
)


class TestDatabaseErrorHandlerClassification:
    """Test error classification by type."""

    def setup_method(self):
        """Initialize error handler for each test."""
        self.handler = DatabaseErrorHandler()

    def test_unique_violation_by_pgcode(self):
        """Test unique constraint violation detected by PostgreSQL error code."""
        # Mock PostgreSQL unique violation error
        mock_error = Mock()
        mock_error.pgcode = "23505"  # unique_violation
        mock_error.__str__ = lambda self: 'duplicate key value violates unique constraint "uq_aml_transaction_labels_txn_tenant"'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.UNIQUE_VIOLATION
        assert db_error.is_duplicate() is True
        assert db_error.is_retryable() is False

    def test_unique_violation_by_message_pattern(self):
        """Test unique constraint violation detected by error message pattern."""
        # Mock error without pgcode but with unique violation message
        mock_error = Mock(spec=[])  # No pgcode attribute
        mock_error.__str__ = lambda self: 'duplicate key value violates unique constraint'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.UNIQUE_VIOLATION
        assert db_error.is_duplicate() is True

    def test_foreign_key_violation_by_pgcode(self):
        """Test foreign key violation detected by PostgreSQL error code."""
        mock_error = Mock()
        mock_error.pgcode = "23503"  # foreign_key_violation
        mock_error.__str__ = lambda self: 'violates foreign key constraint "fk_tenant_id"'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.FOREIGN_KEY_VIOLATION
        assert db_error.is_duplicate() is False
        assert db_error.is_retryable() is False

    def test_not_null_violation_by_pgcode(self):
        """Test NOT NULL violation detected by PostgreSQL error code."""
        mock_error = Mock()
        mock_error.pgcode = "23502"  # not_null_violation
        mock_error.__str__ = lambda self: 'null value in column "tenant_id" violates not-null constraint'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.NOT_NULL_VIOLATION
        assert db_error.is_retryable() is False

    def test_check_violation_by_pgcode(self):
        """Test CHECK constraint violation detected by PostgreSQL error code."""
        mock_error = Mock()
        mock_error.pgcode = "23514"  # check_violation
        mock_error.__str__ = lambda self: 'new row violates check constraint "confidence_score_range"'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.CHECK_VIOLATION

    def test_connection_error_by_pgcode(self):
        """Test connection error detected by PostgreSQL error code."""
        mock_error = Mock()
        mock_error.pgcode = "08006"  # connection_failure
        mock_error.__str__ = lambda self: 'connection to server was lost'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.CONNECTION_ERROR
        assert db_error.is_retryable() is True, "Connection errors should be retryable"

    def test_timeout_error_by_pgcode(self):
        """Test timeout error detected by PostgreSQL error code."""
        mock_error = Mock()
        mock_error.pgcode = "57014"  # query_canceled
        mock_error.__str__ = lambda self: 'canceling statement due to statement timeout'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.TIMEOUT_ERROR
        assert db_error.is_retryable() is True, "Timeout errors should be retryable"

    def test_connection_error_by_message_pattern(self):
        """Test connection error detected by error message pattern."""
        mock_error = Mock(spec=[])
        mock_error.__str__ = lambda self: 'connection refused on port 5432'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.CONNECTION_ERROR
        assert db_error.is_retryable() is True

    def test_timeout_by_message_pattern(self):
        """Test timeout detected by error message pattern."""
        mock_error = Mock(spec=[])
        mock_error.__str__ = lambda self: 'query timed out after 30 seconds'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.TIMEOUT_ERROR
        assert db_error.is_retryable() is True

    def test_unknown_error_classification(self):
        """Test unknown errors are classified as UNKNOWN_ERROR."""
        mock_error = Mock(spec=[])
        mock_error.__str__ = lambda self: 'some unexpected database error'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.error_type == DatabaseErrorType.UNKNOWN_ERROR
        assert db_error.is_retryable() is False


class TestDatabaseErrorHandlerConstraintExtraction:
    """Test extraction of constraint information from error messages."""

    def setup_method(self):
        """Initialize error handler for each test."""
        self.handler = DatabaseErrorHandler()

    def test_extract_constraint_name(self):
        """Test extraction of constraint name from error message."""
        mock_error = Mock()
        mock_error.pgcode = "23505"
        mock_error.__str__ = lambda self: 'duplicate key violates unique constraint "uq_aml_transaction_labels_txn_tenant"'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.constraint_name == "uq_aml_transaction_labels_txn_tenant"

    def test_extract_table_name(self):
        """Test extraction of table name from error message."""
        mock_error = Mock()
        mock_error.pgcode = "23505"
        mock_error.__str__ = lambda self: 'duplicate key in table "aml_transaction_labels"'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.table_name == "aml_transaction_labels"

    def test_extract_column_names(self):
        """Test extraction of column names from Key clause."""
        mock_error = Mock()
        mock_error.pgcode = "23505"
        mock_error.__str__ = lambda self: 'Key (transaction_id, tenant_id)=(txn_123, tenant_001) already exists.'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.column_name == "transaction_id, tenant_id"

    def test_extract_all_constraint_info(self):
        """Test extraction of complete constraint information."""
        mock_error = Mock()
        mock_error.pgcode = "23505"
        mock_error.__str__ = lambda self: (
            'duplicate key value violates unique constraint "uq_aml_transaction_labels_txn_tenant" '
            'on table "aml_transaction_labels"\n'
            'Key (transaction_id, tenant_id)=(txn_abc123, tenant_fintech_001) already exists.'
        )

        db_error = self.handler.handle_error(mock_error)

        assert db_error.constraint_name == "uq_aml_transaction_labels_txn_tenant"
        assert db_error.table_name == "aml_transaction_labels"
        assert "transaction_id, tenant_id" in db_error.column_name


class TestDatabaseErrorHandlerUserMessages:
    """Test user-friendly error message generation."""

    def setup_method(self):
        """Initialize error handler for each test."""
        self.handler = DatabaseErrorHandler()

    def test_unique_violation_message(self):
        """Test user-friendly message for unique constraint violation."""
        mock_error = Mock()
        mock_error.pgcode = "23505"
        mock_error.__str__ = lambda self: (
            'duplicate key violates unique constraint "uq_aml_transaction_labels_txn_tenant"\n'
            'Key (transaction_id, tenant_id)=(txn_001, tenant_001) already exists.'
        )

        db_error = self.handler.handle_error(mock_error)

        assert "Duplicate record detected" in db_error.message
        assert "transaction_id, tenant_id" in db_error.message
        assert "uq_aml_transaction_labels_txn_tenant" in db_error.message

    def test_foreign_key_violation_message(self):
        """Test user-friendly message for foreign key violation."""
        mock_error = Mock()
        mock_error.pgcode = "23503"
        mock_error.__str__ = lambda self: 'violates foreign key constraint "fk_tenant_id"'

        db_error = self.handler.handle_error(mock_error)

        assert "Foreign key constraint violated" in db_error.message
        assert "fk_tenant_id" in db_error.message
        assert "Referenced record" in db_error.message or "dependencies" in db_error.message

    def test_not_null_violation_message(self):
        """Test user-friendly message for NOT NULL violation."""
        mock_error = Mock()
        mock_error.pgcode = "23502"
        mock_error.__str__ = lambda self: 'null value in column "risk_level" violates not-null constraint'

        db_error = self.handler.handle_error(mock_error)

        assert "cannot be null" in db_error.message
        # May contain column name in message

    def test_check_violation_message(self):
        """Test user-friendly message for CHECK constraint violation."""
        mock_error = Mock()
        mock_error.pgcode = "23514"
        mock_error.__str__ = lambda self: 'check constraint "confidence_score_range" violated'

        db_error = self.handler.handle_error(mock_error)

        assert "Data validation failed" in db_error.message
        assert "confidence_score_range" in db_error.message

    def test_connection_error_message(self):
        """Test user-friendly message for connection error."""
        mock_error = Mock()
        mock_error.pgcode = "08006"
        mock_error.__str__ = lambda self: 'connection lost'

        db_error = self.handler.handle_error(mock_error)

        assert "Database connection error" in db_error.message
        assert "retry" in db_error.message.lower()

    def test_timeout_error_message(self):
        """Test user-friendly message for timeout error."""
        mock_error = Mock()
        mock_error.pgcode = "57014"
        mock_error.__str__ = lambda self: 'query timed out'

        db_error = self.handler.handle_error(mock_error)

        assert "timed out" in db_error.message
        assert "retry" in db_error.message.lower() or "smaller batch" in db_error.message.lower()


class TestDatabaseErrorHandlerRetryEligibility:
    """Test determination of retry eligibility for errors."""

    def setup_method(self):
        """Initialize error handler for each test."""
        self.handler = DatabaseErrorHandler()

    def test_connection_error_is_retryable(self):
        """Test connection errors are marked as retryable."""
        mock_error = Mock()
        mock_error.pgcode = "08006"
        mock_error.__str__ = lambda self: 'connection failed'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.is_retryable() is True

    def test_timeout_error_is_retryable(self):
        """Test timeout errors are marked as retryable."""
        mock_error = Mock()
        mock_error.pgcode = "57014"
        mock_error.__str__ = lambda self: 'timeout'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.is_retryable() is True

    def test_unique_violation_not_retryable(self):
        """Test unique constraint violations are not retryable."""
        mock_error = Mock()
        mock_error.pgcode = "23505"
        mock_error.__str__ = lambda self: 'duplicate key'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.is_retryable() is False

    def test_foreign_key_violation_not_retryable(self):
        """Test foreign key violations are not retryable."""
        mock_error = Mock()
        mock_error.pgcode = "23503"
        mock_error.__str__ = lambda self: 'foreign key violation'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.is_retryable() is False

    def test_unknown_error_not_retryable(self):
        """Test unknown errors are not marked as retryable by default."""
        mock_error = Mock(spec=[])
        mock_error.__str__ = lambda self: 'unknown error'

        db_error = self.handler.handle_error(mock_error)

        assert db_error.is_retryable() is False


class TestDuplicateRecordHandler:
    """Test specialized duplicate record handling."""

    def setup_method(self):
        """Initialize duplicate handler for each test."""
        self.mock_logger = Mock()
        self.handler = DuplicateRecordHandler(logger=self.mock_logger)

    def test_handle_duplicate_logs_warning(self):
        """Test handling duplicate logs warning message."""
        # Create a mock database error
        db_error = DatabaseError(
            error_type=DatabaseErrorType.UNIQUE_VIOLATION,
            message="Duplicate detected",
            constraint_name="uq_aml_transaction_labels_txn_tenant"
        )

        record_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "risk_level": "HIGH"
        }

        result = self.handler.handle_duplicate(db_error, record_data)

        # Verify logger was called
        assert self.mock_logger.warning.called
        call_args = self.mock_logger.warning.call_args[0][0]
        assert "Duplicate AML label detected" in call_args
        assert "txn_001" in call_args
        assert "tenant_001" in call_args

    def test_handle_duplicate_returns_metadata(self):
        """Test handling duplicate returns proper metadata."""
        db_error = DatabaseError(
            error_type=DatabaseErrorType.UNIQUE_VIOLATION,
            message="Duplicate detected",
            constraint_name="uq_test_constraint"
        )

        record_data = {
            "transaction_id": "txn_abc",
            "tenant_id": "tenant_xyz"
        }

        result = self.handler.handle_duplicate(db_error, record_data)

        assert result["action"] == "skipped"
        assert result["reason"] == "duplicate_detected"
        assert result["transaction_id"] == "txn_abc"
        assert result["tenant_id"] == "tenant_xyz"
        assert result["constraint"] == "uq_test_constraint"
        assert "duplicate_number" in result

    def test_handle_duplicate_tracks_count(self):
        """Test handling duplicate tracks total count."""
        db_error = DatabaseError(
            error_type=DatabaseErrorType.UNIQUE_VIOLATION,
            message="Duplicate",
            constraint_name="uq_test"
        )

        # Handle first duplicate
        self.handler.handle_duplicate(db_error, {"transaction_id": "txn_1", "tenant_id": "t1"})
        assert self.handler.get_duplicate_count() == 1

        # Handle second duplicate
        self.handler.handle_duplicate(db_error, {"transaction_id": "txn_2", "tenant_id": "t2"})
        assert self.handler.get_duplicate_count() == 2

        # Handle third duplicate
        self.handler.handle_duplicate(db_error, {"transaction_id": "txn_3", "tenant_id": "t3"})
        assert self.handler.get_duplicate_count() == 3

    def test_reset_duplicate_count(self):
        """Test resetting duplicate counter."""
        db_error = DatabaseError(
            error_type=DatabaseErrorType.UNIQUE_VIOLATION,
            message="Duplicate",
            constraint_name="uq_test"
        )

        # Add some duplicates
        for i in range(5):
            self.handler.handle_duplicate(
                db_error,
                {"transaction_id": f"txn_{i}", "tenant_id": "t1"}
            )

        assert self.handler.get_duplicate_count() == 5

        # Reset
        self.handler.reset_count()
        assert self.handler.get_duplicate_count() == 0

    def test_handle_duplicate_without_logger(self):
        """Test handling duplicate works without logger."""
        # Create handler without logger
        handler_no_logger = DuplicateRecordHandler(logger=None)

        db_error = DatabaseError(
            error_type=DatabaseErrorType.UNIQUE_VIOLATION,
            message="Duplicate",
            constraint_name="uq_test"
        )

        # Should not raise exception
        result = handler_no_logger.handle_duplicate(
            db_error,
            {"transaction_id": "txn_001", "tenant_id": "tenant_001"}
        )

        assert result["action"] == "skipped"

    def test_handle_duplicate_with_missing_ids(self):
        """Test handling duplicate with missing transaction/tenant IDs."""
        db_error = DatabaseError(
            error_type=DatabaseErrorType.UNIQUE_VIOLATION,
            message="Duplicate",
            constraint_name="uq_test"
        )

        # Record with missing IDs
        record_data = {"some_field": "value"}

        result = self.handler.handle_duplicate(db_error, record_data)

        # Should handle gracefully
        assert result["transaction_id"] == "unknown"
        assert result["tenant_id"] == "unknown"


class TestDatabaseErrorTypeEnum:
    """Test DatabaseErrorType enum values."""

    def test_all_error_types_exist(self):
        """Test all expected error types are defined."""
        expected_types = [
            "UNIQUE_VIOLATION",
            "FOREIGN_KEY_VIOLATION",
            "NOT_NULL_VIOLATION",
            "CHECK_VIOLATION",
            "CONNECTION_ERROR",
            "TIMEOUT_ERROR",
            "UNKNOWN_ERROR"
        ]

        for error_type in expected_types:
            assert hasattr(DatabaseErrorType, error_type), \
                f"DatabaseErrorType should have {error_type}"

    def test_error_type_values(self):
        """Test error type enum values are lowercase with underscores."""
        assert DatabaseErrorType.UNIQUE_VIOLATION.value == "unique_violation"
        assert DatabaseErrorType.FOREIGN_KEY_VIOLATION.value == "foreign_key_violation"
        assert DatabaseErrorType.CONNECTION_ERROR.value == "connection_error"


class TestDatabaseErrorDataclass:
    """Test DatabaseError dataclass functionality."""

    def test_database_error_creation(self):
        """Test creating DatabaseError instance."""
        error = DatabaseError(
            error_type=DatabaseErrorType.UNIQUE_VIOLATION,
            message="Test error",
            detail="Test detail",
            constraint_name="test_constraint",
            table_name="test_table",
            column_name="test_column"
        )

        assert error.error_type == DatabaseErrorType.UNIQUE_VIOLATION
        assert error.message == "Test error"
        assert error.detail == "Test detail"
        assert error.constraint_name == "test_constraint"
        assert error.table_name == "test_table"
        assert error.column_name == "test_column"

    def test_database_error_with_original_exception(self):
        """Test DatabaseError stores original exception."""
        original = Exception("Original error")

        error = DatabaseError(
            error_type=DatabaseErrorType.UNKNOWN_ERROR,
            message="Handled error",
            original_exception=original
        )

        assert error.original_exception is original
        assert str(error.original_exception) == "Original error"
