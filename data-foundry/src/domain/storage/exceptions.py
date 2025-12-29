"""
Storage Domain Exceptions

Custom exceptions for storage operations.
Each exception has a single, clear purpose (Single Responsibility).
"""

from typing import Optional


class StorageError(Exception):
    """
    Base exception for storage-related errors.

    Provides structured error information for API responses
    and logging.
    """

    def __init__(
        self,
        message: str,
        key: Optional[str] = None,
        original_error: Optional[Exception] = None,
        code: str = "STORAGE_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.key = key
        self.original_error = original_error
        self.code = code

    def to_dict(self) -> dict:
        """Convert exception to API-friendly dictionary."""
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.key:
            result["key"] = self.key
        return result


class StorageConnectionError(StorageError):
    """
    Raised when storage service is unavailable.

    This indicates a connectivity issue, not a problem with
    the specific file operation.
    """

    def __init__(
        self,
        message: str = "Storage service is unavailable",
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            original_error=original_error,
            code="STORAGE_CONNECTION_ERROR",
        )


class StorageNotFoundError(StorageError):
    """
    Raised when a requested file doesn't exist in storage.
    """

    def __init__(self, key: str):
        super().__init__(
            message=f"File not found in storage: {key}",
            key=key,
            code="STORAGE_NOT_FOUND",
        )


class StorageQuotaExceededError(StorageError):
    """
    Raised when storage quota is exceeded.
    """

    def __init__(
        self,
        tenant_id: str,
        current_usage_bytes: int,
        quota_bytes: int,
    ):
        self.tenant_id = tenant_id
        self.current_usage_bytes = current_usage_bytes
        self.quota_bytes = quota_bytes

        current_mb = current_usage_bytes / (1024 * 1024)
        quota_mb = quota_bytes / (1024 * 1024)

        super().__init__(
            message=(
                f"Storage quota exceeded for tenant {tenant_id}. "
                f"Current usage: {current_mb:.1f}MB, Quota: {quota_mb:.1f}MB"
            ),
            code="STORAGE_QUOTA_EXCEEDED",
        )


class StoragePermissionError(StorageError):
    """
    Raised when there's a permission issue with storage operations.
    """

    def __init__(
        self,
        key: str,
        operation: str,
    ):
        self.operation = operation
        super().__init__(
            message=f"Permission denied for {operation} on {key}",
            key=key,
            code="STORAGE_PERMISSION_DENIED",
        )
