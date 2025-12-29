"""
File Domain Module

Contains value objects, interfaces, and validators for file handling.
Follows Single Responsibility Principle - each component has one job.
"""

from .value_objects import (
    FileMetadata,
    FileType,
    ComplexityTier,
    ValidationResult,
)
from .interfaces import IFileValidator
from .validators import (
    FileTypeValidator,
    FileSizeValidator,
    ComplexityDetector,
)
from .exceptions import (
    FileValidationError,
    UnsupportedFileTypeError,
    FileTooLargeError,
)

__all__ = [
    "FileMetadata",
    "FileType",
    "ComplexityTier",
    "ValidationResult",
    "IFileValidator",
    "FileTypeValidator",
    "FileSizeValidator",
    "ComplexityDetector",
    "FileValidationError",
    "UnsupportedFileTypeError",
    "FileTooLargeError",
]
