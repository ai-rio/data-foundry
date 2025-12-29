"""
Tests for UploadService

TDD tests for the file upload application service.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.upload_service import UploadService, UploadResponse, UploadServiceFactory
from src.domain.file.value_objects import FileMetadata, ValidationResult, ComplexityTier
from src.domain.file.interfaces import IFileValidator
from src.domain.file.exceptions import FileValidationError
from src.domain.storage.interfaces import IStorageService
from src.domain.storage.exceptions import StorageError
from src.domain.processing_job.repository import IJobRepository
from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.infrastructure.repositories.job_repository import InMemoryJobRepository


@pytest.fixture
def mock_validator():
    """Create mock file validator."""
    validator = AsyncMock(spec=IFileValidator)
    validator.validate.return_value = ValidationResult.success(
        data={"tier": "simple", "file_type": "csv"}
    )
    return validator


@pytest.fixture
def mock_storage():
    """Create mock storage service."""
    storage = AsyncMock(spec=IStorageService)
    storage.upload.return_value = "https://example.com/files/key"
    return storage


@pytest.fixture
def repo():
    """Create in-memory job repository."""
    return InMemoryJobRepository()


@pytest.fixture
def upload_service(mock_validator, mock_storage, repo):
    """Create upload service with mocked dependencies."""
    return UploadService(
        validator=mock_validator,
        storage=mock_storage,
        job_repo=repo,
    )


class TestUploadServiceCreation:
    """Tests for UploadService initialization."""

    def test_create_service(self, mock_validator, mock_storage, repo):
        """Should create service with dependencies."""
        service = UploadService(
            validator=mock_validator,
            storage=mock_storage,
            job_repo=repo,
        )

        assert service._validator is mock_validator
        assert service._storage is mock_storage
        assert service._job_repo is repo


class TestUploadServiceUpload:
    """Tests for UploadService.upload_file()."""

    @pytest.mark.asyncio
    async def test_upload_valid_file(self, upload_service, mock_validator, mock_storage, repo):
        """Should upload valid file and create job."""
        content = b"col1,col2\nval1,val2"

        response = await upload_service.upload_file(
            file_bytes=content,
            filename="data.csv",
            tenant_id="tenant-123",
        )

        assert isinstance(response, UploadResponse)
        assert response.filename == "data.csv"
        assert response.size_bytes == len(content)
        assert response.job_id is not None
        assert response.status == "pending"

        # Verify job was created
        job = await repo.get(response.job_id)
        assert job is not None
        assert job.tenant_id == "tenant-123"

    @pytest.mark.asyncio
    async def test_upload_validates_file(self, upload_service, mock_validator):
        """Should call validator with file metadata."""
        content = b"content"

        await upload_service.upload_file(
            file_bytes=content,
            filename="data.csv",
            tenant_id="tenant-123",
        )

        mock_validator.validate.assert_called_once()
        call_args = mock_validator.validate.call_args
        file_metadata = call_args[0][0]
        assert isinstance(file_metadata, FileMetadata)
        assert file_metadata.name == "data.csv"

    @pytest.mark.asyncio
    async def test_upload_raises_on_validation_failure(self, upload_service, mock_validator):
        """Should raise FileValidationError if validation fails."""
        mock_validator.validate.return_value = ValidationResult.failure(
            errors=["File type not allowed"]
        )

        with pytest.raises(FileValidationError) as exc_info:
            await upload_service.upload_file(
                file_bytes=b"content",
                filename="malware.exe",
                tenant_id="tenant-123",
            )

        assert "File type not allowed" in str(exc_info.value.errors)

    @pytest.mark.asyncio
    async def test_upload_calls_storage(self, upload_service, mock_storage):
        """Should upload file to storage."""
        content = b"content"

        response = await upload_service.upload_file(
            file_bytes=content,
            filename="data.csv",
            tenant_id="tenant-123",
        )

        mock_storage.upload.assert_called_once()
        call_kwargs = mock_storage.upload.call_args[1]
        assert call_kwargs["data"] == content
        assert "tenant-123" in call_kwargs["key"]

    @pytest.mark.asyncio
    async def test_upload_extracts_complexity_tier(self, upload_service, mock_validator):
        """Should extract complexity tier from validation result."""
        mock_validator.validate.return_value = ValidationResult.success(
            data={"tier": "complex"}
        )

        response = await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
        )

        assert response.complexity_tier == "complex"

    @pytest.mark.asyncio
    async def test_upload_calculates_estimated_cost(self, upload_service, mock_validator):
        """Should calculate estimated cost based on tier and size."""
        mock_validator.validate.return_value = ValidationResult.success(
            data={"tier": "simple"}
        )

        response = await upload_service.upload_file(
            file_bytes=b"a" * (1024 * 1024),  # 1MB
            filename="data.csv",
            tenant_id="tenant-123",
        )

        assert response.estimated_cost > Decimal("0")

    @pytest.mark.asyncio
    async def test_upload_with_content_type(self, upload_service, mock_storage):
        """Should pass content type to storage."""
        await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            content_type="text/csv",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert call_kwargs["content_type"] == "text/csv"

    @pytest.mark.asyncio
    async def test_upload_with_metadata(self, upload_service, repo):
        """Should include metadata in job."""
        response = await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            metadata={"vertical": "healthcare"},
        )

        job = await repo.get(response.job_id)
        assert job.metadata.get("vertical") == "healthcare"


class TestUploadServiceStorageFailure:
    """Tests for storage failure handling."""

    @pytest.mark.asyncio
    async def test_storage_failure_marks_job_failed(self, mock_validator, mock_storage, repo):
        """Should mark job as failed if storage upload fails."""
        mock_storage.upload.side_effect = StorageError(
            message="Connection failed",
            code="CONNECTION_ERROR",
            key="test/key",
        )

        service = UploadService(
            validator=mock_validator,
            storage=mock_storage,
            job_repo=repo,
        )

        with pytest.raises(StorageError):
            await service.upload_file(
                file_bytes=b"content",
                filename="data.csv",
                tenant_id="tenant-123",
            )

        # Check job was marked as failed
        jobs = await repo.list_by_tenant("tenant-123")
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.FAILED
        assert "Connection failed" in jobs[0].error_message


class TestUploadServiceContentTypeDetection:
    """Tests for content type detection."""

    @pytest.mark.asyncio
    async def test_detect_csv_content_type(self, upload_service, mock_storage):
        """Should detect text/csv for .csv files."""
        await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert call_kwargs["content_type"] == "text/csv"

    @pytest.mark.asyncio
    async def test_detect_json_content_type(self, upload_service, mock_storage):
        """Should detect application/json for .json files."""
        await upload_service.upload_file(
            file_bytes=b"{}",
            filename="data.json",
            tenant_id="tenant-123",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert call_kwargs["content_type"] == "application/json"

    @pytest.mark.asyncio
    async def test_detect_xlsx_content_type(self, upload_service, mock_storage):
        """Should detect correct MIME type for .xlsx files."""
        await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.xlsx",
            tenant_id="tenant-123",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert "spreadsheet" in call_kwargs["content_type"]

    @pytest.mark.asyncio
    async def test_fallback_content_type(self, upload_service, mock_storage):
        """Should use octet-stream for unknown extensions."""
        await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.unknown",
            tenant_id="tenant-123",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert call_kwargs["content_type"] == "application/octet-stream"


class TestUploadServiceStorageKey:
    """Tests for storage key generation."""

    @pytest.mark.asyncio
    async def test_storage_key_includes_tenant(self, upload_service, mock_storage):
        """Storage key should include tenant ID."""
        await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert "tenant-123" in call_kwargs["key"]

    @pytest.mark.asyncio
    async def test_storage_key_includes_job_id(self, upload_service, mock_storage, repo):
        """Storage key should include job ID."""
        response = await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert response.job_id in call_kwargs["key"]

    @pytest.mark.asyncio
    async def test_storage_key_includes_filename(self, upload_service, mock_storage):
        """Storage key should include filename."""
        await upload_service.upload_file(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
        )

        call_kwargs = mock_storage.upload.call_args[1]
        assert "data.csv" in call_kwargs["key"]


class TestUploadResponse:
    """Tests for UploadResponse value object."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        from datetime import datetime

        response = UploadResponse(
            job_id="job-123",
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        result = response.to_dict()

        assert result["job_id"] == "job-123"
        assert result["filename"] == "data.csv"
        assert result["size_bytes"] == 1024
        assert result["complexity_tier"] == "simple"
        assert result["estimated_cost"] == "0.50"
        assert result["status"] == "pending"
        assert result["storage_key"] == "tenant/job/data.csv"
        assert "2025-01-01" in result["created_at"]


class TestUploadServiceFactory:
    """Tests for UploadServiceFactory."""

    def test_create_service(self, mock_validator, mock_storage, repo):
        """Should create service with provided dependencies."""
        service = UploadServiceFactory.create(
            validator=mock_validator,
            storage=mock_storage,
            job_repo=repo,
        )

        assert isinstance(service, UploadService)
