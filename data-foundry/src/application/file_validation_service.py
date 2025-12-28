"""
File Validation Application Service

Orchestrates file validation by composing domain validators.
Follows Composition over Inheritance principle.

SOLID Principles:
- Single Responsibility: Only handles validation orchestration
- Open/Closed: New validators can be added without modifying this code
- Dependency Inversion: Depends on IFileValidator interface
"""

import hashlib
import logging
from typing import List, Optional

from src.domain.file.interfaces import IFileValidator, IFileContentValidator
from src.domain.file.value_objects import FileMetadata, ValidationResult
from src.domain.file.validators import (
    FileTypeValidator,
    FileSizeValidator,
    ComplexityDetector,
    FilenameSanitizer,
    CompositeFileValidator,
)

logger = logging.getLogger(__name__)


class FileValidationService:
    """
    Application Service: File Validation

    Orchestrates the validation of uploaded files using multiple validators.
    This service composes validators and provides a unified validation interface.

    Composability: Validators can be added, removed, or reordered via constructor.

    Example:
        service = FileValidationService(
            validators=[
                FilenameSanitizer(),
                FileTypeValidator(),
                FileSizeValidator(),
                ComplexityDetector(),
            ]
        )
        result = await service.validate(file_metadata)
    """

    def __init__(
        self,
        validators: Optional[List[IFileValidator]] = None,
        content_validators: Optional[List[IFileContentValidator]] = None,
    ):
        """
        Initialize with list of validators.

        Args:
            validators: List of IFileValidator to run on metadata
            content_validators: List of IFileContentValidator to run on content
        """
        # Default validators if none provided
        if validators is None:
            validators = self._default_validators()

        self._validators = validators
        self._content_validators = content_validators or []

        # Wrap in composite for unified execution
        self._composite = CompositeFileValidator(self._validators)

        logger.info(
            f"FileValidationService initialized with {len(self._validators)} "
            f"metadata validators and {len(self._content_validators)} content validators"
        )

    @staticmethod
    def _default_validators() -> List[IFileValidator]:
        """Create default validator chain."""
        return [
            FilenameSanitizer(),
            FileTypeValidator(),
            FileSizeValidator(max_size_bytes=100 * 1024 * 1024),  # 100MB
            ComplexityDetector(),
        ]

    async def validate(
        self,
        file: FileMetadata,
        fail_fast: bool = False,
    ) -> ValidationResult:
        """
        Validate file metadata using all configured validators.

        Args:
            file: FileMetadata to validate
            fail_fast: If True, stop on first failure

        Returns:
            ValidationResult combining all validator results
        """
        logger.debug(f"Validating file: {file.name} ({file.size_mb:.2f}MB)")

        result = await self._composite.validate(file, fail_fast=fail_fast)

        if result.valid:
            logger.info(f"File validation passed: {file.name}")
        else:
            logger.warning(f"File validation failed: {file.name} - {result.errors}")

        return result

    async def validate_with_content(
        self,
        file: FileMetadata,
        content: bytes,
        fail_fast: bool = False,
    ) -> ValidationResult:
        """
        Validate file metadata AND content.

        First validates metadata, then if passing, validates content.

        Args:
            file: FileMetadata to validate
            content: Raw file content
            fail_fast: If True, stop on first failure

        Returns:
            ValidationResult combining all validations
        """
        # First validate metadata
        result = await self.validate(file, fail_fast=fail_fast)

        if not result.valid and fail_fast:
            return result

        # Then validate content
        for validator in self._content_validators:
            content_result = await validator.validate_content(file, content)
            result = result.merge(content_result)

            if not content_result.valid and fail_fast:
                break

        return result

    async def compute_checksum(self, content: bytes) -> str:
        """
        Compute SHA-256 checksum of file content.

        Args:
            content: File content

        Returns:
            Hex digest of SHA-256 hash
        """
        return hashlib.sha256(content).hexdigest()

    def add_validator(self, validator: IFileValidator) -> None:
        """
        Add a validator to the chain.

        Open/Closed: Extend functionality without modifying existing code.

        Args:
            validator: Validator to add
        """
        self._validators.append(validator)
        self._composite = CompositeFileValidator(self._validators)
        logger.info(f"Added validator: {validator.__class__.__name__}")

    def add_content_validator(self, validator: IFileContentValidator) -> None:
        """
        Add a content validator.

        Args:
            validator: Content validator to add
        """
        self._content_validators.append(validator)
        logger.info(f"Added content validator: {validator.__class__.__name__}")


class FileValidationServiceFactory:
    """
    Factory for creating FileValidationService instances.

    Provides pre-configured service instances for common use cases.
    """

    @staticmethod
    def create_strict() -> FileValidationService:
        """Create service with strict validation rules."""
        return FileValidationService(
            validators=[
                FilenameSanitizer(),
                FileTypeValidator(),
                FileSizeValidator(max_size_bytes=50 * 1024 * 1024),  # 50MB
                ComplexityDetector(),
            ]
        )

    @staticmethod
    def create_permissive() -> FileValidationService:
        """Create service with permissive validation rules."""
        from src.domain.file.value_objects import FileType

        return FileValidationService(
            validators=[
                FilenameSanitizer(),
                FileTypeValidator(
                    allowed_types={
                        FileType.CSV,
                        FileType.JSON,
                        FileType.XLSX,
                        FileType.PDF,
                        FileType.PARQUET,
                    }
                ),
                FileSizeValidator(max_size_bytes=200 * 1024 * 1024),  # 200MB
                ComplexityDetector(),
            ]
        )

    @staticmethod
    def create_for_testing() -> FileValidationService:
        """Create service for testing (minimal validation)."""
        return FileValidationService(
            validators=[
                FileTypeValidator(),
                FileSizeValidator(max_size_bytes=10 * 1024 * 1024),  # 10MB
            ]
        )
