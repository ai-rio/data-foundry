"""
Database Error Handler - Production-grade error handling for database operations

This module implements the Dependency Inversion Principle by providing
high-level error handling abstractions that don't depend on low-level
database driver details.

SOLID Principles Applied:
- S (Single Responsibility): Only handles database error interpretation and recovery
- O (Open/Closed): Extensible through error handler registration
- L (Liskov Substitution): All error handlers follow same interface
- I (Interface Segregation): Focused interface for error handling
- D (Dependency Inversion): Depends on error abstractions, not specific drivers

Reference: P01-023 - Proper constraint violation handling
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Type
from enum import Enum
import re


class DatabaseErrorType(Enum):
    """Classification of database errors."""
    UNIQUE_VIOLATION = "unique_violation"
    FOREIGN_KEY_VIOLATION = "foreign_key_violation"
    NOT_NULL_VIOLATION = "not_null_violation"
    CHECK_VIOLATION = "check_violation"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT_ERROR = "timeout_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class DatabaseError:
    """
    Structured representation of a database error.

    Attributes:
        error_type: Classified error type
        message: Human-readable error message
        detail: Additional error details
        constraint_name: Name of violated constraint (if applicable)
        table_name: Table where error occurred (if applicable)
        column_name: Column where error occurred (if applicable)
        original_exception: Original exception object
    """
    error_type: DatabaseErrorType
    message: str
    detail: Optional[str] = None
    constraint_name: Optional[str] = None
    table_name: Optional[str] = None
    column_name: Optional[str] = None
    original_exception: Optional[Exception] = None

    def is_duplicate(self) -> bool:
        """Check if this is a duplicate/unique constraint violation."""
        return self.error_type == DatabaseErrorType.UNIQUE_VIOLATION

    def is_retryable(self) -> bool:
        """Check if this error is retryable (transient failure)."""
        return self.error_type in {
            DatabaseErrorType.CONNECTION_ERROR,
            DatabaseErrorType.TIMEOUT_ERROR
        }


class DatabaseErrorHandler:
    """
    Handles and interprets database errors for production use.

    This handler:
    - Classifies database errors by type
    - Extracts meaningful information from error messages
    - Provides user-friendly error messages
    - Determines retry eligibility
    - Logs errors with appropriate context

    Example:
        >>> handler = DatabaseErrorHandler()
        >>> try:
        ...     await session.execute(insert_stmt, params)
        ... except Exception as e:
        ...     db_error = handler.handle_error(e)
        ...     if db_error.is_duplicate():
        ...         logger.warning(f"Duplicate record: {db_error.message}")
        ...     else:
        ...         logger.error(f"Database error: {db_error.message}")
    """

    # PostgreSQL error codes (SQLSTATE codes)
    # https://www.postgresql.org/docs/current/errcodes-appendix.html
    POSTGRES_ERROR_CODES = {
        "23505": DatabaseErrorType.UNIQUE_VIOLATION,  # unique_violation
        "23503": DatabaseErrorType.FOREIGN_KEY_VIOLATION,  # foreign_key_violation
        "23502": DatabaseErrorType.NOT_NULL_VIOLATION,  # not_null_violation
        "23514": DatabaseErrorType.CHECK_VIOLATION,  # check_violation
        "08000": DatabaseErrorType.CONNECTION_ERROR,  # connection_exception
        "08003": DatabaseErrorType.CONNECTION_ERROR,  # connection_does_not_exist
        "08006": DatabaseErrorType.CONNECTION_ERROR,  # connection_failure
        "57014": DatabaseErrorType.TIMEOUT_ERROR,  # query_canceled
    }

    def handle_error(self, exception: Exception) -> DatabaseError:
        """
        Handle and classify a database error.

        Args:
            exception: The caught exception

        Returns:
            DatabaseError with classification and details
        """
        # Try to extract PostgreSQL error code
        error_code = self._extract_postgres_error_code(exception)

        if error_code:
            error_type = self.POSTGRES_ERROR_CODES.get(
                error_code,
                DatabaseErrorType.UNKNOWN_ERROR
            )
        else:
            # Fallback to pattern matching on error message
            error_type = self._classify_by_message(exception)

        # Extract constraint information
        constraint_info = self._extract_constraint_info(exception)

        # Build user-friendly message
        message = self._build_user_message(error_type, exception, constraint_info)

        return DatabaseError(
            error_type=error_type,
            message=message,
            detail=str(exception),
            constraint_name=constraint_info.get("constraint_name"),
            table_name=constraint_info.get("table_name"),
            column_name=constraint_info.get("column_name"),
            original_exception=exception
        )

    def _extract_postgres_error_code(self, exception: Exception) -> Optional[str]:
        """Extract PostgreSQL SQLSTATE error code from exception."""
        # asyncpg.exceptions.UniqueViolationError has pgcode attribute
        if hasattr(exception, "pgcode"):
            return exception.pgcode

        # Check if it's wrapped in another exception
        if hasattr(exception, "__cause__") and hasattr(exception.__cause__, "pgcode"):
            return exception.__cause__.pgcode

        # Try to extract from error message
        error_str = str(exception)
        code_match = re.search(r'\(SQLSTATE (\d+)\)', error_str)
        if code_match:
            return code_match.group(1)

        return None

    def _classify_by_message(self, exception: Exception) -> DatabaseErrorType:
        """Classify error by matching patterns in error message."""
        error_str = str(exception).lower()

        if any(keyword in error_str for keyword in ["unique", "duplicate", "already exists"]):
            return DatabaseErrorType.UNIQUE_VIOLATION

        if "foreign key" in error_str or "violates foreign key constraint" in error_str:
            return DatabaseErrorType.FOREIGN_KEY_VIOLATION

        if "not null" in error_str or "null value in column" in error_str:
            return DatabaseErrorType.NOT_NULL_VIOLATION

        if "check constraint" in error_str or "violates check constraint" in error_str:
            return DatabaseErrorType.CHECK_VIOLATION

        if any(keyword in error_str for keyword in ["connection", "connect", "disconnected"]):
            return DatabaseErrorType.CONNECTION_ERROR

        if any(keyword in error_str for keyword in ["timeout", "timed out", "query canceled"]):
            return DatabaseErrorType.TIMEOUT_ERROR

        return DatabaseErrorType.UNKNOWN_ERROR

    def _extract_constraint_info(self, exception: Exception) -> Dict[str, Optional[str]]:
        """Extract constraint name, table, and column from error message."""
        info: Dict[str, Optional[str]] = {
            "constraint_name": None,
            "table_name": None,
            "column_name": None
        }

        error_str = str(exception)

        # Extract constraint name
        # Pattern: Key (column1, column2)=(value1, value2) already exists.
        # Pattern: violates unique constraint "constraint_name"
        constraint_match = re.search(r'constraint "([^"]+)"', error_str)
        if constraint_match:
            info["constraint_name"] = constraint_match.group(1)

        # Extract table name
        # Pattern: table "table_name"
        table_match = re.search(r'table "([^"]+)"', error_str)
        if table_match:
            info["table_name"] = table_match.group(1)

        # Extract column names from Key clause
        # Pattern: Key (transaction_id, tenant_id)=(value1, value2)
        key_match = re.search(r'Key \(([^)]+)\)', error_str)
        if key_match:
            info["column_name"] = key_match.group(1)

        return info

    def _build_user_message(
        self,
        error_type: DatabaseErrorType,
        exception: Exception,
        constraint_info: Dict[str, Optional[str]]
    ) -> str:
        """Build a user-friendly error message."""
        if error_type == DatabaseErrorType.UNIQUE_VIOLATION:
            constraint = constraint_info.get("constraint_name", "unique constraint")
            columns = constraint_info.get("column_name", "unknown columns")
            return (
                f"Duplicate record detected. A record with the same {columns} already exists. "
                f"Constraint: {constraint}"
            )

        if error_type == DatabaseErrorType.FOREIGN_KEY_VIOLATION:
            constraint = constraint_info.get("constraint_name", "foreign key constraint")
            return (
                f"Foreign key constraint violated: {constraint}. "
                "Referenced record does not exist or cannot be deleted due to dependencies."
            )

        if error_type == DatabaseErrorType.NOT_NULL_VIOLATION:
            column = constraint_info.get("column_name", "unknown column")
            return f"Required field '{column}' cannot be null."

        if error_type == DatabaseErrorType.CHECK_VIOLATION:
            constraint = constraint_info.get("constraint_name", "check constraint")
            return f"Data validation failed: {constraint}. Value does not meet requirements."

        if error_type == DatabaseErrorType.CONNECTION_ERROR:
            return "Database connection error. Please retry or contact support if issue persists."

        if error_type == DatabaseErrorType.TIMEOUT_ERROR:
            return "Database operation timed out. Please retry with smaller batch size."

        # Unknown error - provide original message
        return f"Database error: {str(exception)}"


class DuplicateRecordHandler:
    """
    Specialized handler for duplicate record scenarios.

    This handler provides specific logic for handling duplicate
    AML transaction labels, including:
    - Detecting duplicates
    - Logging for audit trail
    - Decision on whether to skip or update
    """

    def __init__(self, logger=None):
        """
        Initialize duplicate handler.

        Args:
            logger: Optional logger for audit trail
        """
        self.logger = logger
        self._duplicate_count = 0

    def handle_duplicate(
        self,
        db_error: DatabaseError,
        record_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle a duplicate record scenario.

        Args:
            db_error: The database error with duplicate info
            record_data: The data that triggered the duplicate

        Returns:
            Dictionary with handling result:
            {
                "action": "skipped",  # or "updated"
                "reason": "duplicate_detected",
                "transaction_id": "...",
                "tenant_id": "..."
            }
        """
        self._duplicate_count += 1

        transaction_id = record_data.get("transaction_id", "unknown")
        tenant_id = record_data.get("tenant_id", "unknown")

        # Log for audit trail
        if self.logger:
            self.logger.warning(
                f"Duplicate AML label detected: "
                f"transaction_id={transaction_id}, tenant_id={tenant_id}. "
                f"Constraint: {db_error.constraint_name}. "
                f"Action: Skipping duplicate (ON CONFLICT DO NOTHING behavior)"
            )

        return {
            "action": "skipped",
            "reason": "duplicate_detected",
            "transaction_id": transaction_id,
            "tenant_id": tenant_id,
            "constraint": db_error.constraint_name,
            "duplicate_number": self._duplicate_count
        }

    def get_duplicate_count(self) -> int:
        """Get total number of duplicates handled."""
        return self._duplicate_count

    def reset_count(self) -> None:
        """Reset duplicate counter."""
        self._duplicate_count = 0
