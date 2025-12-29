"""
File Domain Exceptions

Custom exceptions for file-related operations.
Each exception has a single, clear purpose (Single Responsibility).
"""

from typing import List, Optional


class FileValidationError(Exception):
    """
    Base exception for file validation errors.

    Provides structured error information for API responses.
    """

    def __init__(
        self,
        message: str,
        errors: Optional[List[str]] = None,
        code: str = "FILE_VALIDATION_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]
        self.code = code

    def to_dict(self) -> dict:
        """Convert exception to API-friendly dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "errors": self.errors,
        }


class UnsupportedFileTypeError(FileValidationError):
    """
    Raised when an unsupported file type is uploaded.

    Provides information about what types ARE supported.
    """

    def __init__(self, file_type: str, supported_types: List[str]):
        self.file_type = file_type
        self.supported_types = supported_types
        message = (
            f"File type '{file_type}' is not supported. "
            f"Supported types: {', '.join(supported_types)}"
        )
        super().__init__(
            message=message,
            errors=[message],
            code="UNSUPPORTED_FILE_TYPE",
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["file_type"] = self.file_type
        result["supported_types"] = self.supported_types
        return result


class FileTooLargeError(FileValidationError):
    """
    Raised when a file exceeds the maximum allowed size.

    Provides information about the actual size and limit.
    """

    def __init__(self, actual_size_bytes: int, max_size_bytes: int):
        self.actual_size_bytes = actual_size_bytes
        self.max_size_bytes = max_size_bytes
        actual_mb = actual_size_bytes / (1024 * 1024)
        max_mb = max_size_bytes / (1024 * 1024)
        message = (
            f"File size {actual_mb:.1f}MB exceeds maximum allowed size of {max_mb:.1f}MB"
        )
        super().__init__(
            message=message,
            errors=[message],
            code="FILE_TOO_LARGE",
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["actual_size_bytes"] = self.actual_size_bytes
        result["max_size_bytes"] = self.max_size_bytes
        return result


class InvalidFileContentError(FileValidationError):
    """
    Raised when file content doesn't match expected format.

    For example, a .csv file that doesn't contain valid CSV data.
    """

    def __init__(self, filename: str, expected_format: str, reason: str):
        self.filename = filename
        self.expected_format = expected_format
        self.reason = reason
        message = (
            f"File '{filename}' does not contain valid {expected_format} content: {reason}"
        )
        super().__init__(
            message=message,
            errors=[message],
            code="INVALID_FILE_CONTENT",
        )


class FileSecurityError(FileValidationError):
    """
    Raised when a file fails security validation.

    Examples: malware detection, path traversal attempts
    """

    def __init__(self, filename: str, security_issue: str):
        self.filename = filename
        self.security_issue = security_issue
        message = f"File '{filename}' failed security validation: {security_issue}"
        super().__init__(
            message=message,
            errors=[message],
            code="FILE_SECURITY_ERROR",
        )
