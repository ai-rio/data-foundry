"""
Tests for UploadPipeline

TDD tests for the upload pipeline integration layer.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.application.upload_pipeline import (
    UploadPipeline,
    PipelineResult,
    MockPrefectClient,
    IPrefectClient,
)
from src.application.upload_service import UploadService, UploadResponse
from src.application.job_tracking_service import JobTrackingService
from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.file.value_objects import ValidationResult
from src.domain.file.exceptions import FileValidationError
from src.infrastructure.repositories.job_repository import InMemoryJobRepository


class TestPipelineCreation:
    """Tests for UploadPipeline initialization."""

    def test_create_pipeline_with_prefect(self):
        """Should create pipeline with Prefect client."""
        mock_upload = MagicMock(spec=UploadService)
        mock_jobs = MagicMock(spec=JobTrackingService)
        mock_prefect = MockPrefectClient()

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=mock_jobs,
            prefect_client=mock_prefect,
        )

        assert pipeline._prefect is mock_prefect

    def test_create_pipeline_without_prefect(self):
        """Should create pipeline without Prefect client."""
        mock_upload = MagicMock(spec=UploadService)
        mock_jobs = MagicMock(spec=JobTrackingService)

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=mock_jobs,
            prefect_client=None,
        )

        assert pipeline._prefect is None


class TestPipelineExecution:
    """Tests for UploadPipeline.execute()."""

    @pytest.fixture
    def repo(self):
        return InMemoryJobRepository()

    @pytest.fixture
    def job_service(self, repo):
        return JobTrackingService(repo)

    @pytest.mark.asyncio
    async def test_execute_uploads_file(self, job_service):
        """Should call upload service."""
        # Create the job first
        job = await job_service.create_job("tenant-123", "data.csv", 1024)

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.return_value = UploadResponse(
            job_id=job.id,
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime.utcnow(),
        )

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
        )

        content = b"test content"
        await pipeline.execute(
            file_bytes=content,
            filename="data.csv",
            tenant_id="tenant-123",
        )

        mock_upload.upload_file.assert_called_once()
        call_kwargs = mock_upload.upload_file.call_args[1]
        assert call_kwargs["file_bytes"] == content
        assert call_kwargs["filename"] == "data.csv"
        assert call_kwargs["tenant_id"] == "tenant-123"

    @pytest.mark.asyncio
    async def test_execute_returns_pipeline_result(self, job_service, repo):
        """Should return PipelineResult."""
        # Create a job
        job = await job_service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.return_value = UploadResponse(
            job_id=job.id,
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime.utcnow(),
        )

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
        )

        result = await pipeline.execute(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            auto_start=False,
        )

        assert isinstance(result, PipelineResult)
        assert result.upload_response.job_id == job.id
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_starts_processing_when_auto_start(self, job_service, repo):
        """Should start processing when auto_start is True."""
        job = await job_service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.return_value = UploadResponse(
            job_id=job.id,
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime.utcnow(),
        )

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
        )

        result = await pipeline.execute(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            auto_start=True,
        )

        assert result.job.status == JobStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_execute_no_processing_when_auto_start_false(self, job_service, repo):
        """Should not start processing when auto_start is False."""
        job = await job_service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.return_value = UploadResponse(
            job_id=job.id,
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime.utcnow(),
        )

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
        )

        result = await pipeline.execute(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            auto_start=False,
        )

        assert result.job.status == JobStatus.PENDING


class TestPipelinePrefectIntegration:
    """Tests for Prefect client integration."""

    @pytest.fixture
    def repo(self):
        return InMemoryJobRepository()

    @pytest.fixture
    def job_service(self, repo):
        return JobTrackingService(repo)

    @pytest.mark.asyncio
    async def test_execute_triggers_prefect(self, job_service, repo):
        """Should trigger Prefect flow when client available."""
        job = await job_service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.return_value = UploadResponse(
            job_id=job.id,
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime.utcnow(),
        )

        mock_prefect = MockPrefectClient()

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
            prefect_client=mock_prefect,
        )

        result = await pipeline.execute(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            vertical="healthcare",
            auto_start=True,
        )

        assert len(mock_prefect.triggered_flows) == 1
        triggered = mock_prefect.triggered_flows[0]
        assert triggered["job_id"] == job.id
        assert triggered["vertical"] == "healthcare"
        assert result.flow_run_id is not None

    @pytest.mark.asyncio
    async def test_execute_no_prefect_when_not_auto_start(self, job_service, repo):
        """Should not trigger Prefect when auto_start is False."""
        job = await job_service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.return_value = UploadResponse(
            job_id=job.id,
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime.utcnow(),
        )

        mock_prefect = MockPrefectClient()

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
            prefect_client=mock_prefect,
        )

        await pipeline.execute(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            auto_start=False,
        )

        assert len(mock_prefect.triggered_flows) == 0

    @pytest.mark.asyncio
    async def test_prefect_failure_does_not_fail_pipeline(self, job_service, repo):
        """Pipeline should succeed even if Prefect fails."""
        job = await job_service.create_job(
            tenant_id="tenant-123",
            file_name="data.csv",
            file_size=1024,
        )

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.return_value = UploadResponse(
            job_id=job.id,
            filename="data.csv",
            size_bytes=1024,
            complexity_tier="simple",
            estimated_cost=Decimal("0.50"),
            status="pending",
            storage_key="tenant/job/data.csv",
            created_at=datetime.utcnow(),
        )

        # Create a failing Prefect client
        failing_prefect = AsyncMock(spec=IPrefectClient)
        failing_prefect.trigger_ingestion.side_effect = Exception("Prefect unavailable")

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
            prefect_client=failing_prefect,
        )

        result = await pipeline.execute(
            file_bytes=b"content",
            filename="data.csv",
            tenant_id="tenant-123",
            auto_start=True,
        )

        # Pipeline should still succeed but with error message
        assert result.error is not None
        assert "trigger failed" in result.error.lower()
        assert result.job.status == JobStatus.PROCESSING


class TestPipelineErrorHandling:
    """Tests for error handling in pipeline."""

    @pytest.fixture
    def repo(self):
        return InMemoryJobRepository()

    @pytest.fixture
    def job_service(self, repo):
        return JobTrackingService(repo)

    @pytest.mark.asyncio
    async def test_upload_failure_raises(self, job_service):
        """Should raise error when upload fails."""
        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.side_effect = FileValidationError(
            message="Invalid file",
            errors=["File type not allowed"],
        )

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
        )

        with pytest.raises(ValueError) as exc_info:
            await pipeline.execute(
                file_bytes=b"content",
                filename="data.csv",
                tenant_id="tenant-123",
            )

        assert "Upload failed" in str(exc_info.value)


class TestPipelineResult:
    """Tests for PipelineResult value object."""

    def test_success_property_true(self):
        """success should be True when no error."""
        mock_upload = MagicMock(spec=UploadResponse)
        mock_job = MagicMock(spec=ProcessingJob)

        result = PipelineResult(
            upload_response=mock_upload,
            job=mock_job,
            flow_run_id="flow-123",
            error=None,
        )

        assert result.success is True

    def test_success_property_false(self):
        """success should be False when error present."""
        mock_upload = MagicMock(spec=UploadResponse)
        mock_job = MagicMock(spec=ProcessingJob)

        result = PipelineResult(
            upload_response=mock_upload,
            job=mock_job,
            flow_run_id=None,
            error="Something went wrong",
        )

        assert result.success is False

    def test_to_dict(self):
        """Should convert to dictionary."""
        mock_upload = MagicMock(spec=UploadResponse)
        mock_upload.to_dict.return_value = {"job_id": "job-123"}

        mock_job = MagicMock(spec=ProcessingJob)
        mock_job.id = "job-123"
        mock_job.status = JobStatus.PENDING

        result = PipelineResult(
            upload_response=mock_upload,
            job=mock_job,
            flow_run_id="flow-123",
            error=None,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["job_id"] == "job-123"
        assert data["flow_run_id"] == "flow-123"


class TestBatchExecution:
    """Tests for UploadPipeline.execute_batch()."""

    @pytest.fixture
    def repo(self):
        return InMemoryJobRepository()

    @pytest.fixture
    def job_service(self, repo):
        return JobTrackingService(repo)

    @pytest.mark.asyncio
    async def test_execute_batch_multiple_files(self, job_service, repo):
        """Should process multiple files."""
        jobs = []
        for i in range(3):
            job = await job_service.create_job(
                tenant_id="tenant-123",
                file_name=f"file{i}.csv",
                file_size=1024,
            )
            jobs.append(job)

        # Mock upload to return different job IDs
        responses = []
        for job in jobs:
            responses.append(UploadResponse(
                job_id=job.id,
                filename=f"{job.file_name}",
                size_bytes=1024,
                complexity_tier="simple",
                estimated_cost=Decimal("0.50"),
                status="pending",
                storage_key=f"tenant/job/{job.file_name}",
                created_at=datetime.utcnow(),
            ))

        mock_upload = AsyncMock(spec=UploadService)
        mock_upload.upload_file.side_effect = responses

        pipeline = UploadPipeline(
            upload_service=mock_upload,
            job_service=job_service,
        )

        files = [
            (b"content0", "file0.csv"),
            (b"content1", "file1.csv"),
            (b"content2", "file2.csv"),
        ]

        results = await pipeline.execute_batch(
            files=files,
            tenant_id="tenant-123",
            auto_start=False,
        )

        assert len(results) == 3
        assert all(isinstance(r, PipelineResult) for r in results)


class TestMockPrefectClient:
    """Tests for MockPrefectClient."""

    @pytest.mark.asyncio
    async def test_trigger_ingestion(self):
        """Should record triggered flows."""
        client = MockPrefectClient()

        flow_run_id = await client.trigger_ingestion(
            job_id="job-123",
            vertical="healthcare",
            file_name="data.csv",
            tenant_id="tenant-456",
        )

        assert flow_run_id is not None
        assert len(client.triggered_flows) == 1
        assert client.triggered_flows[0]["job_id"] == "job-123"
        assert client.triggered_flows[0]["vertical"] == "healthcare"
        assert client.triggered_flows[0]["tenant_id"] == "tenant-456"
