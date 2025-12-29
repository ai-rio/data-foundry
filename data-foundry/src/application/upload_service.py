"""
Upload Application Service

Orchestrates the file upload workflow:
1. Validate file
2. Create job record
3. Upload to storage
4. Return response

SOLID Principles:
- Single Responsibility: Orchestrates upload workflow only
- Dependency Inversion: Depends on interfaces, not implementations
- Open/Closed: New steps can be added via hooks/events
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.domain.file.interfaces import IFileValidator
from src.domain.file.value_objects import FileMetadata, ValidationResult, ComplexityTier
from src.domain.file.exceptions import FileValidationError
from src.domain.storage.interfaces import IStorageService
from src.domain.storage.exceptions import StorageError
from src.domain.storage.value_objects import StorageKey
from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.repository import IJobRepository
from src.domain.processing_job.value_objects import JobCost

logger = logging.getLogger(__name__)


@dataclass
class UploadResponse:
    """
    Value Object: Response from upload operation.

    Contains all information the client needs about the uploaded file
    and the created processing job.
    """
    job_id: str
    filename: str
    size_bytes: int
    complexity_tier: str
    estimated_cost: Decimal
    status: str
    storage_key: str
    created_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "complexity_tier": self.complexity_tier,
            "estimated_cost": str(self.estimated_cost),
            "status": self.status,
            "storage_key": self.storage_key,
            "created_at": self.created_at.isoformat(),
        }


class UploadService:
    """
    Application Service: File Upload

    Coordinates the complete file upload workflow:
    1. Validate the uploaded file (type, size, security)
    2. Detect complexity tier for cost estimation
    3. Create a processing job record
    4. Upload file to object storage (R2)
    5. Return upload response with job ID

    Dependency Inversion: All dependencies are injected as interfaces.
    """

    def __init__(
        self,
        validator: IFileValidator,
        storage: IStorageService,
        job_repo: IJobRepository,
    ):
        """
        Initialize with required dependencies.

        Args:
            validator: File validation service/composite validator
            storage: Object storage service (R2/S3)
            job_repo: Job repository for persistence
        """
        self._validator = validator
        self._storage = storage
        self._job_repo = job_repo

        logger.info("UploadService initialized")

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        tenant_id: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> UploadResponse:
        """
        Upload a file and create a processing job.

        This is the main entry point for file uploads.

        Args:
            file_bytes: Raw file content
            filename: Original filename
            tenant_id: Tenant identifier for multi-tenancy
            content_type: Optional MIME type
            metadata: Optional additional metadata

        Returns:
            UploadResponse with job details

        Raises:
            FileValidationError: If file validation fails
            StorageError: If storage upload fails
        """
        logger.info(f"Processing upload for tenant {tenant_id}: {filename}")

        # Step 1: Create file metadata
        file_metadata = self._create_metadata(
            filename=filename,
            size=len(file_bytes),
            content_type=content_type,
        )

        # Step 2: Validate file
        validation_result = await self._validator.validate(file_metadata)
        if not validation_result.valid:
            logger.warning(f"File validation failed: {validation_result.errors}")
            raise FileValidationError(
                message="File validation failed",
                errors=validation_result.errors,
            )

        # Step 3: Extract complexity tier from validation data
        tier = self._extract_tier(validation_result)

        # Step 4: Calculate cost estimate
        cost = JobCost.estimate(tier, len(file_bytes))

        # Step 5: Create job record (before upload for atomicity)
        job = ProcessingJob.create(
            tenant_id=tenant_id,
            file_name=filename,
            file_size=len(file_bytes),
            complexity_tier=tier,
            estimated_cost=cost.estimated_total,
        )

        if metadata:
            job.metadata.update(metadata)

        # Save job to get ID
        job = await self._job_repo.save(job)
        logger.debug(f"Created job {job.id} for upload")

        # Step 6: Upload to storage
        storage_key = self._build_storage_key(tenant_id, job.id, filename)

        # Use detected content type from metadata
        detected_content_type = file_metadata.content_type

        try:
            await self._storage.upload(
                key=storage_key,
                data=file_bytes,
                metadata={
                    "tenant_id": tenant_id,
                    "job_id": job.id,
                    "original_filename": filename,
                    "complexity_tier": tier,
                },
                content_type=detected_content_type,
            )
            logger.info(f"File uploaded to storage: {storage_key}")

        except StorageError as e:
            # Mark job as failed if storage upload fails
            logger.error(f"Storage upload failed: {e}")
            job.transition_to_failed(error_message=str(e))
            await self._job_repo.save(job)
            raise

        # Step 7: Update job with storage key
        # Re-fetch job to get latest version for optimistic locking
        job = await self._job_repo.get_by_id(job.id)
        job.file_key = storage_key
        job.version += 1  # Increment version for update
        await self._job_repo.save(job)

        logger.info(
            f"Upload complete for job {job.id}: "
            f"{filename} ({file_metadata.size_mb:.2f}MB, tier={tier})"
        )

        return UploadResponse(
            job_id=job.id,
            filename=filename,
            size_bytes=len(file_bytes),
            complexity_tier=tier,
            estimated_cost=cost.estimated_total,
            status=job.status.value,
            storage_key=storage_key,
            created_at=job.created_at,
        )

    def _create_metadata(
        self,
        filename: str,
        size: int,
        content_type: Optional[str],
    ) -> FileMetadata:
        """Create FileMetadata from upload parameters."""
        # Detect content type from extension if not provided
        if content_type is None:
            content_type = self._detect_content_type(filename)

        return FileMetadata(
            name=filename,
            size=size,
            content_type=content_type,
        )

    def _detect_content_type(self, filename: str) -> str:
        """Detect MIME type from filename extension."""
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        content_types = {
            "csv": "text/csv",
            "json": "application/json",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pdf": "application/pdf",
            "parquet": "application/x-parquet",
        }

        return content_types.get(extension, "application/octet-stream")

    def _extract_tier(self, validation_result: ValidationResult) -> str:
        """Extract complexity tier from validation result data."""
        if validation_result.data and "tier" in validation_result.data:
            return validation_result.data["tier"]

        # Fallback to moderate if not detected
        return ComplexityTier.MODERATE.value

    def _build_storage_key(
        self,
        tenant_id: str,
        job_id: str,
        filename: str,
    ) -> str:
        """Build storage key for uploaded file."""
        # Validate key segments
        key = StorageKey(
            tenant_id=tenant_id,
            job_id=job_id,
            filename=filename,
        )
        return key.full_path


class UploadServiceFactory:
    """
    Factory for creating UploadService instances.

    Handles dependency injection and configuration.
    """

    @staticmethod
    def create(
        validator: IFileValidator,
        storage: IStorageService,
        job_repo: IJobRepository,
    ) -> UploadService:
        """
        Create UploadService with provided dependencies.

        Args:
            validator: File validator
            storage: Storage service
            job_repo: Job repository

        Returns:
            Configured UploadService
        """
        return UploadService(
            validator=validator,
            storage=storage,
            job_repo=job_repo,
        )
