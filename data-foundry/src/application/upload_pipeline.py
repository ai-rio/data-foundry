"""
Upload Pipeline - Integration Layer

Orchestrates the complete upload-to-processing flow:
1. Upload file via UploadService
2. Start processing via JobTrackingService
3. Trigger background processing (Prefect)

SOLID Principles:
- Single Responsibility: Pipeline coordination only
- Dependency Inversion: All services injected as interfaces
- Open/Closed: New pipeline stages via composition
"""

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from src.application.upload_service import UploadService, UploadResponse
from src.application.job_tracking_service import JobTrackingService
from src.domain.processing_job.aggregate import ProcessingJob

logger = logging.getLogger(__name__)


class IPrefectClient(Protocol):
    """
    Protocol for Prefect client integration.

    Defines the interface for triggering Prefect flows.
    Protocols allow duck typing with type safety.
    """

    async def trigger_ingestion(
        self,
        job_id: str,
        vertical: str,
        file_name: str,
        **kwargs,
    ) -> str:
        """
        Trigger the ingestion flow in Prefect.

        Args:
            job_id: Processing job ID
            vertical: Industry vertical for specialized processing
            file_name: Name of the uploaded file
            **kwargs: Additional flow parameters

        Returns:
            Flow run ID
        """
        ...


@dataclass
class PipelineResult:
    """
    Value Object: Result of pipeline execution.

    Contains the upload response, job details, and flow run info.
    """
    upload_response: UploadResponse
    job: ProcessingJob
    flow_run_id: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if pipeline executed successfully."""
        return self.error is None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "success": self.success,
            "upload": self.upload_response.to_dict(),
            "job_id": self.job.id,
            "job_status": self.job.status.value,
            "flow_run_id": self.flow_run_id,
            "error": self.error,
        }


class UploadPipeline:
    """
    Integration Service: Upload Pipeline

    Orchestrates the complete flow from file upload to processing start.

    Pipeline stages:
    1. upload_service.upload_file() - Validate and store file
    2. job_service.start_processing() - Transition job to PROCESSING
    3. prefect_client.trigger_ingestion() - Start background processing

    Dependency Inversion: All dependencies are injected interfaces.
    """

    def __init__(
        self,
        upload_service: UploadService,
        job_service: JobTrackingService,
        prefect_client: Optional[IPrefectClient] = None,
    ):
        """
        Initialize pipeline with required services.

        Args:
            upload_service: Service for file uploads
            job_service: Service for job tracking
            prefect_client: Optional Prefect client for flow triggering
        """
        self._upload = upload_service
        self._jobs = job_service
        self._prefect = prefect_client

        logger.info(
            f"UploadPipeline initialized "
            f"(prefect_client={'enabled' if prefect_client else 'disabled'})"
        )

    async def execute(
        self,
        file_bytes: bytes,
        filename: str,
        tenant_id: str,
        vertical: str = "general",
        auto_start: bool = True,
        metadata: Optional[dict] = None,
    ) -> PipelineResult:
        """
        Execute the upload pipeline.

        Args:
            file_bytes: Raw file content
            filename: Original filename
            tenant_id: Tenant identifier
            vertical: Industry vertical for specialized processing
            auto_start: If True, immediately start processing
            metadata: Optional additional metadata

        Returns:
            PipelineResult with execution details
        """
        logger.info(
            f"Executing upload pipeline: tenant={tenant_id}, "
            f"file={filename}, vertical={vertical}"
        )

        upload_response = None
        job = None
        flow_run_id = None
        error = None

        try:
            # Stage 1: Upload file
            upload_response = await self._upload.upload_file(
                file_bytes=file_bytes,
                filename=filename,
                tenant_id=tenant_id,
                metadata=metadata,
            )
            logger.debug(f"Stage 1 complete: upload -> job_id={upload_response.job_id}")

            # Get job for pipeline result
            job = await self._jobs.get_job_or_fail(upload_response.job_id)

            if auto_start:
                # Stage 2: Start processing
                job = await self._jobs.start_processing(upload_response.job_id)
                logger.debug(f"Stage 2 complete: job status -> {job.status}")

                # Stage 3: Trigger Prefect flow (if client available)
                if self._prefect:
                    try:
                        flow_run_id = await self._prefect.trigger_ingestion(
                            job_id=upload_response.job_id,
                            vertical=vertical,
                            file_name=filename,
                            tenant_id=tenant_id,
                            complexity_tier=upload_response.complexity_tier,
                        )
                        logger.debug(f"Stage 3 complete: flow_run_id={flow_run_id}")
                    except Exception as e:
                        # Don't fail pipeline if Prefect trigger fails
                        # Job is still uploaded and will be picked up by workers
                        logger.warning(f"Prefect trigger failed: {e}")
                        error = f"Processing queued but trigger failed: {e}"

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            error = str(e)

            # Try to mark job as failed if it was created
            if upload_response and job:
                try:
                    job = await self._jobs.mark_failed(
                        upload_response.job_id,
                        error_message=str(e),
                    )
                except Exception as fail_error:
                    logger.error(f"Failed to mark job as failed: {fail_error}")

        # Build result
        if upload_response is None:
            # Early failure - no upload response
            raise ValueError(f"Upload failed: {error}")

        return PipelineResult(
            upload_response=upload_response,
            job=job,
            flow_run_id=flow_run_id,
            error=error,
        )

    async def execute_batch(
        self,
        files: list[tuple[bytes, str]],  # (content, filename) pairs
        tenant_id: str,
        vertical: str = "general",
        auto_start: bool = True,
    ) -> list[PipelineResult]:
        """
        Execute pipeline for multiple files.

        Args:
            files: List of (content, filename) tuples
            tenant_id: Tenant identifier
            vertical: Industry vertical
            auto_start: If True, start processing immediately

        Returns:
            List of PipelineResult for each file
        """
        results = []

        for content, filename in files:
            try:
                result = await self.execute(
                    file_bytes=content,
                    filename=filename,
                    tenant_id=tenant_id,
                    vertical=vertical,
                    auto_start=auto_start,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Batch upload failed for {filename}: {e}")
                # Create error result
                # Note: This is a simplified error handling - production code
                # would need more sophisticated error recovery
                continue

        return results


class MockPrefectClient:
    """
    Mock Prefect client for testing.

    Implements IPrefectClient protocol for use in tests.
    """

    def __init__(self):
        self.triggered_flows = []

    async def trigger_ingestion(
        self,
        job_id: str,
        vertical: str,
        file_name: str,
        **kwargs,
    ) -> str:
        """Record the trigger call and return a mock flow run ID."""
        import uuid
        flow_run_id = str(uuid.uuid4())

        self.triggered_flows.append({
            "flow_run_id": flow_run_id,
            "job_id": job_id,
            "vertical": vertical,
            "file_name": file_name,
            **kwargs,
        })

        return flow_run_id
