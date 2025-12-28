"""
Tests for FileValidationService

TDD tests for the file validation orchestration service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.file_validation_service import (
    FileValidationService,
    FileValidationServiceFactory,
)
from src.domain.file.value_objects import (
    FileMetadata,
    ValidationResult,
    FileType,
)
from src.domain.file.interfaces import IFileValidator, IFileContentValidator


@pytest.fixture
def csv_file():
    """Create CSV file metadata for testing."""
    return FileMetadata(name="data.csv", size=1024, content_type="text/csv")


@pytest.fixture
def large_file():
    """Create large file metadata (150MB)."""
    return FileMetadata(
        name="large.csv",
        size=150 * 1024 * 1024,
        content_type="text/csv",
    )


class TestFileValidationServiceCreation:
    """Tests for FileValidationService creation and initialization."""

    def test_create_with_defaults(self):
        """Should create service with default validators."""
        service = FileValidationService()

        # Should have default validators
        assert len(service._validators) == 4  # Sanitizer, Type, Size, Complexity

    def test_create_with_custom_validators(self):
        """Should accept custom validators."""
        mock_validator = MagicMock(spec=IFileValidator)
        service = FileValidationService(validators=[mock_validator])

        assert len(service._validators) == 1
        assert service._validators[0] is mock_validator

    def test_create_with_content_validators(self):
        """Should accept content validators."""
        mock_content = MagicMock(spec=IFileContentValidator)
        service = FileValidationService(content_validators=[mock_content])

        assert len(service._content_validators) == 1

    def test_add_validator(self):
        """Should allow adding validators at runtime."""
        service = FileValidationService(validators=[])
        mock_validator = MagicMock(spec=IFileValidator)

        service.add_validator(mock_validator)

        assert mock_validator in service._validators


class TestFileValidationServiceValidation:
    """Tests for FileValidationService.validate()."""

    @pytest.mark.asyncio
    async def test_validate_valid_file(self, csv_file):
        """Valid file should pass validation."""
        service = FileValidationService()

        result = await service.validate(csv_file)

        assert result.valid is True

    @pytest.mark.asyncio
    async def test_validate_calls_all_validators(self, csv_file):
        """Should call all configured validators."""
        mock_v1 = AsyncMock(spec=IFileValidator)
        mock_v1.validate.return_value = ValidationResult.success()
        mock_v2 = AsyncMock(spec=IFileValidator)
        mock_v2.validate.return_value = ValidationResult.success()

        service = FileValidationService(validators=[mock_v1, mock_v2])
        await service.validate(csv_file)

        mock_v1.validate.assert_called_once()
        mock_v2.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_aggregates_errors(self, csv_file):
        """Should aggregate errors from multiple validators."""
        mock_v1 = AsyncMock(spec=IFileValidator)
        mock_v1.validate.return_value = ValidationResult.failure(errors=["Error 1"])
        mock_v2 = AsyncMock(spec=IFileValidator)
        mock_v2.validate.return_value = ValidationResult.failure(errors=["Error 2"])

        service = FileValidationService(validators=[mock_v1, mock_v2])
        result = await service.validate(csv_file, fail_fast=False)

        assert result.valid is False
        assert len(result.errors) >= 2

    @pytest.mark.asyncio
    async def test_validate_fail_fast(self, csv_file):
        """Fail fast should stop on first failure."""
        mock_v1 = AsyncMock(spec=IFileValidator)
        mock_v1.validate.return_value = ValidationResult.failure(errors=["Error 1"])
        mock_v2 = AsyncMock(spec=IFileValidator)
        mock_v2.validate.return_value = ValidationResult.success()

        service = FileValidationService(validators=[mock_v1, mock_v2])
        result = await service.validate(csv_file, fail_fast=True)

        assert result.valid is False
        # Second validator should not be called
        mock_v2.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_merges_data(self, csv_file):
        """Should merge data from all validators."""
        mock_v1 = AsyncMock(spec=IFileValidator)
        mock_v1.validate.return_value = ValidationResult.success(data={"key1": "val1"})
        mock_v2 = AsyncMock(spec=IFileValidator)
        mock_v2.validate.return_value = ValidationResult.success(data={"key2": "val2"})

        service = FileValidationService(validators=[mock_v1, mock_v2])
        result = await service.validate(csv_file)

        assert result.valid is True
        assert result.data.get("key1") == "val1"
        assert result.data.get("key2") == "val2"


class TestFileValidationServiceContentValidation:
    """Tests for FileValidationService.validate_with_content()."""

    @pytest.mark.asyncio
    async def test_validate_with_content_runs_both(self, csv_file):
        """Should run metadata and content validators."""
        mock_meta = AsyncMock(spec=IFileValidator)
        mock_meta.validate.return_value = ValidationResult.success()
        mock_content = AsyncMock(spec=IFileContentValidator)
        mock_content.validate_content.return_value = ValidationResult.success()

        service = FileValidationService(
            validators=[mock_meta],
            content_validators=[mock_content],
        )

        content = b"col1,col2\nval1,val2"
        result = await service.validate_with_content(csv_file, content)

        assert result.valid is True
        mock_meta.validate.assert_called_once()
        mock_content.validate_content.assert_called_once_with(csv_file, content)

    @pytest.mark.asyncio
    async def test_content_validation_skipped_on_metadata_fail(self, csv_file):
        """Content validation should be skipped if metadata fails with fail_fast."""
        mock_meta = AsyncMock(spec=IFileValidator)
        mock_meta.validate.return_value = ValidationResult.failure(errors=["Error"])
        mock_content = AsyncMock(spec=IFileContentValidator)
        mock_content.validate_content.return_value = ValidationResult.success()

        service = FileValidationService(
            validators=[mock_meta],
            content_validators=[mock_content],
        )

        result = await service.validate_with_content(
            csv_file, b"content", fail_fast=True
        )

        assert result.valid is False
        mock_content.validate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_content_validation_runs_without_fail_fast(self, csv_file):
        """Content validation should run even if metadata fails without fail_fast."""
        mock_meta = AsyncMock(spec=IFileValidator)
        mock_meta.validate.return_value = ValidationResult.failure(errors=["Error"])
        mock_content = AsyncMock(spec=IFileContentValidator)
        mock_content.validate_content.return_value = ValidationResult.success()

        service = FileValidationService(
            validators=[mock_meta],
            content_validators=[mock_content],
        )

        result = await service.validate_with_content(
            csv_file, b"content", fail_fast=False
        )

        assert result.valid is False
        mock_content.validate_content.assert_called_once()


class TestFileValidationServiceChecksum:
    """Tests for FileValidationService.compute_checksum()."""

    @pytest.mark.asyncio
    async def test_compute_checksum(self):
        """Should compute SHA-256 checksum."""
        service = FileValidationService(validators=[])
        content = b"test content"

        checksum = await service.compute_checksum(content)

        # Known SHA-256 for "test content"
        expected = "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"
        assert checksum == expected
        assert len(checksum) == 64  # SHA-256 produces 64 hex chars

    @pytest.mark.asyncio
    async def test_compute_checksum_empty(self):
        """Should handle empty content."""
        service = FileValidationService(validators=[])
        content = b""

        checksum = await service.compute_checksum(content)

        # Known SHA-256 for empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert checksum == expected


class TestFileValidationServiceFactory:
    """Tests for FileValidationServiceFactory."""

    def test_create_strict(self):
        """Should create service with strict settings."""
        service = FileValidationServiceFactory.create_strict()

        assert isinstance(service, FileValidationService)
        # Strict has 50MB limit - check via validator config
        assert len(service._validators) == 4

    def test_create_permissive(self):
        """Should create service with permissive settings."""
        service = FileValidationServiceFactory.create_permissive()

        assert isinstance(service, FileValidationService)
        assert len(service._validators) == 4

    def test_create_for_testing(self):
        """Should create minimal service for testing."""
        service = FileValidationServiceFactory.create_for_testing()

        assert isinstance(service, FileValidationService)
        # Testing has fewer validators
        assert len(service._validators) == 2
