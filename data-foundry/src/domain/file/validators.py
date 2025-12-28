"""
File Domain Validators

Concrete validator implementations following Single Responsibility Principle.
Each validator does exactly one thing and does it well.

SOLID Principles:
- Single Responsibility: Each validator has one job
- Open/Closed: New validators can be added without modifying existing ones
- Liskov Substitution: All validators can be used interchangeably via IFileValidator
"""

from typing import List, Optional, Set

from .interfaces import IFileValidator
from .value_objects import (
    ComplexityTier,
    FileMetadata,
    FileType,
    ValidationResult,
)


class FileTypeValidator(IFileValidator):
    """
    Single Responsibility: Validates that file type is allowed.

    This validator only checks the file extension/type against
    a list of allowed types. It does not validate content.
    """

    # Default allowed types - can be overridden in constructor
    DEFAULT_ALLOWED_TYPES: Set[FileType] = {
        FileType.CSV,
        FileType.JSON,
        FileType.XLSX,
        FileType.PDF,
        FileType.PARQUET,
    }

    def __init__(self, allowed_types: Optional[Set[FileType]] = None):
        """
        Initialize with optional custom allowed types.

        Args:
            allowed_types: Set of FileType enums that are allowed.
                          Defaults to CSV, JSON, XLSX, PDF, Parquet.
        """
        self.allowed_types = allowed_types or self.DEFAULT_ALLOWED_TYPES

    async def validate(self, file: FileMetadata) -> ValidationResult:
        """
        Validate that the file type is allowed.

        Args:
            file: FileMetadata to validate

        Returns:
            ValidationResult with success or error
        """
        file_type = file.file_type

        if file_type is None:
            # Unknown file type
            allowed_extensions = [ft.value for ft in self.allowed_types]
            return ValidationResult.failure(
                errors=[
                    f"Unknown file type for '{file.name}'. "
                    f"Allowed types: {', '.join(allowed_extensions)}"
                ]
            )

        if file_type not in self.allowed_types:
            allowed_extensions = [ft.value for ft in self.allowed_types]
            return ValidationResult.failure(
                errors=[
                    f"File type '{file_type.value}' is not allowed. "
                    f"Allowed types: {', '.join(allowed_extensions)}"
                ]
            )

        return ValidationResult.success(data={"file_type": file_type.value})


class FileSizeValidator(IFileValidator):
    """
    Single Responsibility: Validates that file size is within limits.

    This validator only checks file size. It does not validate
    type or content.
    """

    # Default max size: 100MB
    DEFAULT_MAX_SIZE_BYTES: int = 100 * 1024 * 1024

    def __init__(
        self,
        max_size_bytes: Optional[int] = None,
        min_size_bytes: int = 1,
    ):
        """
        Initialize with optional size limits.

        Args:
            max_size_bytes: Maximum file size in bytes. Default 100MB.
            min_size_bytes: Minimum file size in bytes. Default 1 byte.
        """
        self.max_size_bytes = max_size_bytes or self.DEFAULT_MAX_SIZE_BYTES
        self.min_size_bytes = min_size_bytes

    async def validate(self, file: FileMetadata) -> ValidationResult:
        """
        Validate that the file size is within allowed limits.

        Args:
            file: FileMetadata to validate

        Returns:
            ValidationResult with success or error
        """
        errors = []
        warnings = []

        if file.size < self.min_size_bytes:
            errors.append(
                f"File '{file.name}' is empty or too small "
                f"(minimum {self.min_size_bytes} bytes)"
            )

        if file.size > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            errors.append(
                f"File '{file.name}' is too large: {file.size_mb:.1f}MB "
                f"exceeds maximum of {max_mb:.1f}MB"
            )

        # Add warning for large files (>50MB) even if under limit
        if file.size > 50 * 1024 * 1024 and not errors:
            warnings.append(
                f"Large file detected ({file.size_mb:.1f}MB). "
                "Processing may take longer."
            )

        if errors:
            return ValidationResult.failure(errors=errors, warnings=warnings)

        return ValidationResult.success(
            data={"size_bytes": file.size, "size_mb": file.size_mb},
            warnings=warnings,
        )


class ComplexityDetector(IFileValidator):
    """
    Single Responsibility: Detects file complexity tier.

    This validator always succeeds (it's detecting, not validating).
    It adds complexity tier information to the validation result data.

    Complexity tiers are used for:
    - Cost estimation
    - Processing time estimation
    - Queue priority assignment
    """

    # Size thresholds for complexity tiers
    SIMPLE_THRESHOLD_BYTES: int = 5 * 1024 * 1024      # 5MB
    MODERATE_THRESHOLD_BYTES: int = 50 * 1024 * 1024   # 50MB

    def __init__(
        self,
        simple_threshold: Optional[int] = None,
        moderate_threshold: Optional[int] = None,
    ):
        """
        Initialize with optional custom thresholds.

        Args:
            simple_threshold: Max bytes for SIMPLE tier. Default 5MB.
            moderate_threshold: Max bytes for MODERATE tier. Default 50MB.
                               Files larger than this are COMPLEX.
        """
        self.simple_threshold = simple_threshold or self.SIMPLE_THRESHOLD_BYTES
        self.moderate_threshold = moderate_threshold or self.MODERATE_THRESHOLD_BYTES

    async def validate(self, file: FileMetadata) -> ValidationResult:
        """
        Detect complexity tier for the file.

        Args:
            file: FileMetadata to analyze

        Returns:
            ValidationResult (always success) with complexity tier in data
        """
        tier = self._detect_tier(file)

        return ValidationResult.success(
            data={
                "tier": tier.value,
                "complexity_tier": tier,
                "estimated_cost_per_mb": tier.base_cost_multiplier,
                "estimated_processing_seconds": tier.estimated_processing_seconds,
            }
        )

    def _detect_tier(self, file: FileMetadata) -> ComplexityTier:
        """
        Determine complexity tier based on file characteristics.

        Currently based on file size, but could be extended to consider:
        - File type (PDFs need OCR = more complex)
        - Content structure
        - Schema complexity
        """
        # Size-based detection
        if file.size < self.simple_threshold:
            return ComplexityTier.SIMPLE
        elif file.size < self.moderate_threshold:
            return ComplexityTier.MODERATE
        else:
            return ComplexityTier.COMPLEX


class CompositeFileValidator(IFileValidator):
    """
    Composition Pattern: Combines multiple validators into one.

    This allows building complex validation chains while keeping
    each individual validator simple and focused.

    Composability Principle: Validators can be combined in any order.
    """

    def __init__(self, validators: List[IFileValidator]):
        """
        Initialize with a list of validators to execute.

        Args:
            validators: List of IFileValidator implementations.
                       Executed in order; stops on first failure
                       if fail_fast=True.
        """
        self.validators = validators

    async def validate(
        self,
        file: FileMetadata,
        fail_fast: bool = False,
    ) -> ValidationResult:
        """
        Run all validators on the file.

        Args:
            file: FileMetadata to validate
            fail_fast: If True, stop on first validation failure.
                      If False, run all validators and collect all errors.

        Returns:
            ValidationResult combining all validator results
        """
        combined_result = ValidationResult.success()

        for validator in self.validators:
            result = await validator.validate(file)
            combined_result = combined_result.merge(result)

            if fail_fast and not result.valid:
                break

        return combined_result


class FilenameSanitizer(IFileValidator):
    """
    Single Responsibility: Validates filename for security issues.

    Checks for:
    - Path traversal attempts (../)
    - Null bytes
    - Excessive length
    - Forbidden characters
    """

    MAX_FILENAME_LENGTH: int = 255
    FORBIDDEN_PATTERNS: List[str] = ["../", "..\\", "\x00", "<", ">", "|"]

    async def validate(self, file: FileMetadata) -> ValidationResult:
        """
        Validate filename for security issues.

        Args:
            file: FileMetadata to validate

        Returns:
            ValidationResult with security validation outcome
        """
        errors = []
        warnings = []

        # Check length
        if len(file.name) > self.MAX_FILENAME_LENGTH:
            errors.append(
                f"Filename too long ({len(file.name)} chars). "
                f"Maximum is {self.MAX_FILENAME_LENGTH}."
            )

        # Check for forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in file.name:
                errors.append(
                    f"Filename contains forbidden pattern: {pattern!r}"
                )

        # Check for unusual characters (warning, not error)
        if not file.name.replace(".", "").replace("-", "").replace("_", "").replace(" ", "").isalnum():
            warnings.append(
                "Filename contains special characters that may cause issues."
            )

        if errors:
            return ValidationResult.failure(errors=errors, warnings=warnings)

        return ValidationResult.success()
