"""
Upload API Router

FastAPI router for file upload endpoints.

Phase 2 Integration:
- PostgreSQL JobRepository for persistent job tracking
- Real PrefectClient for triggering Prefect flows
- Backward compatible with unit tests (use their own InMemoryJobRepository fixtures)
"""

import logging
import os
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.upload.contracts import (
    UploadResponseContract,
    ValidationErrorContract,
    UploadMetadataContract,
)
from src.application.upload_service import UploadService, UploadResponse
from src.application.upload_pipeline import UploadPipeline, PipelineResult, PrefectClient
from src.domain.file.exceptions import FileValidationError
from src.domain.storage.exceptions import StorageError
from src.database.connection import db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


# -----------------------------------------------------------------
# Dependency Injection
# -----------------------------------------------------------------

async def get_db_session() -> AsyncSession:
    """
    Dependency: Get async database session.

    SOLID: Dependency Inversion - inject session as dependency.
    This enables PostgreSQL persistence while maintaining test isolation.

    Returns:
        AsyncSession: SQLAlchemy async session from connection pool
    """
    async with db_connection.get_session() as session:
        yield session


async def get_upload_service(
    session: AsyncSession = Depends(get_db_session),
) -> UploadService:
    """
    Dependency: Get configured UploadService with PostgreSQL persistence.

    SOLID:
    - Dependency Inversion: Session injected as dependency
    - Single Responsibility: Only creates and wires UploadService

    Args:
        session: Async database session from get_db_session dependency

    Returns:
        UploadService configured with PostgreSQL JobRepository
    """
    from src.application.file_validation_service import FileValidationService
    from src.infrastructure.storage.local_storage_service import LocalStorageService
    from src.infrastructure.repositories.job_repository import JobRepository

    # Create default validator
    validator = FileValidationService()

    # For development, use local storage
    storage = LocalStorageService()

    # Use PostgreSQL repository with injected session
    job_repo = JobRepository(session)

    return UploadService(
        validator=validator._composite,  # Use the composite validator
        storage=storage,
        job_repo=job_repo,
    )


async def get_upload_pipeline(
    session: AsyncSession = Depends(get_db_session),
) -> UploadPipeline:
    """
    Dependency: Get configured UploadPipeline with real Prefect integration.

    Phase 2 Integration:
    - PostgreSQL JobRepository for persistent job tracking
    - Real PrefectClient for triggering Prefect flows
    - Job status updates handled by flow (job_id passed to flow)

    SOLID:
    - Dependency Inversion: Session injected, not created
    - Single Responsibility: Only handles dependency wiring
    - Interface Segregation: Uses IJobRepository interface

    Args:
        session: Async database session from get_db_session dependency

    Returns:
        UploadPipeline configured with real Prefect and PostgreSQL
    """
    from src.application.file_validation_service import FileValidationService
    from src.application.job_tracking_service import JobTrackingService
    from src.infrastructure.storage.local_storage_service import LocalStorageService
    from src.infrastructure.repositories.job_repository import JobRepository

    validator = FileValidationService()
    storage = LocalStorageService()

    # Use PostgreSQL repository with injected session
    job_repo = JobRepository(session)

    upload_service = UploadService(
        validator=validator._composite,
        storage=storage,
        job_repo=job_repo,
    )

    job_service = JobTrackingService(repo=job_repo)

    # Use real PrefectClient for Phase 2 integration
    # Get Prefect API URL from environment (default to local development server)
    prefect_api_url = os.environ.get("PREFECT_API_URL", "http://localhost:4200/api")

    prefect_client = PrefectClient(
        api_url=prefect_api_url,
        job_service=job_service,
    )

    logger.info(
        f"UploadPipeline configured with PostgreSQL JobRepository "
        f"and PrefectClient (api_url={prefect_api_url})"
    )

    return UploadPipeline(
        upload_service=upload_service,
        job_service=job_service,
        prefect_client=prefect_client,
    )


async def get_current_tenant(
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    """
    Dependency: Get current tenant ID from request header or default.

    In production, this would extract tenant from JWT token.
    For development/testing, reads from X-Tenant-ID header.

    Args:
        x_tenant_id: Optional tenant ID from X-Tenant-ID header

    Returns:
        The tenant ID from header, or default "test-tenant-001" if not provided
    """
    if x_tenant_id:
        return x_tenant_id
    return "test-tenant-001"


# -----------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------

@router.post(
    "",
    response_model=UploadResponseContract,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file for processing",
    responses={
        201: {"description": "File uploaded successfully"},
        400: {"model": ValidationErrorContract, "description": "Validation error"},
        413: {"description": "File too large"},
        500: {"description": "Storage error"},
    },
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    vertical: Optional[str] = Form(default="general"),
    auto_start: Optional[bool] = Form(default=True),
    service: UploadService = Depends(get_upload_service),
    tenant_id: str = Depends(get_current_tenant),
) -> UploadResponseContract:
    """
    Upload a file for processing.

    Accepts multipart form data with the file and optional metadata.

    - **file**: The file to upload (CSV, JSON, XLSX, PDF, Parquet)
    - **vertical**: Industry vertical for specialized processing
    - **auto_start**: Whether to immediately start processing

    Returns job information for tracking processing status.
    """
    logger.info(f"Upload request: {file.filename} from tenant {tenant_id}")

    try:
        # Read file content
        file_bytes = await file.read()

        if len(file_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file uploaded",
            )

        # Upload via service
        response = await service.upload_file(
            file_bytes=file_bytes,
            filename=file.filename,
            tenant_id=tenant_id,
            content_type=file.content_type,
            metadata={
                "vertical": vertical,
                "auto_start": str(auto_start),
            },
        )

        return UploadResponseContract(
            job_id=response.job_id,
            filename=response.filename,
            size_bytes=response.size_bytes,
            complexity_tier=response.complexity_tier,
            estimated_cost=str(response.estimated_cost),
            status=response.status,
            storage_key=response.storage_key,
            created_at=response.created_at,
        )

    except FileValidationError as e:
        logger.warning(f"Validation failed: {e.errors}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )

    except StorageError as e:
        logger.error(f"Storage error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "STORAGE_ERROR",
                "message": "Failed to store file",
            },
        )

    except Exception as e:
        logger.exception(f"Unexpected error during upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            },
        )


@router.post(
    "/with-processing",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Upload file and start processing",
)
async def upload_and_process(
    file: UploadFile = File(...),
    vertical: Optional[str] = Form(default="general"),
    pipeline: UploadPipeline = Depends(get_upload_pipeline),
    tenant_id: str = Depends(get_current_tenant),
) -> dict:
    """
    Upload file and immediately start processing.

    This endpoint:
    1. Validates and stores the file
    2. Creates a processing job
    3. Triggers the processing pipeline

    Returns complete pipeline result including flow run ID.
    """
    logger.info(f"Upload+process request: {file.filename}")

    try:
        file_bytes = await file.read()

        result = await pipeline.execute(
            file_bytes=file_bytes,
            filename=file.filename,
            tenant_id=tenant_id,
            vertical=vertical,
            auto_start=True,
        )

        return result.to_dict()

    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )

    except Exception as e:
        logger.exception(f"Pipeline error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "PIPELINE_ERROR",
                "message": str(e),
            },
        )


@router.get(
    "/supported-types",
    summary="Get supported file types",
)
async def get_supported_types() -> dict:
    """
    Get list of supported file types and size limits.

    Returns configuration information about allowed uploads.
    """
    from src.domain.file.value_objects import FileType
    from src.domain.file.validators import FileSizeValidator

    return {
        "supported_types": [ft.value for ft in FileType],
        "max_size_bytes": FileSizeValidator.DEFAULT_MAX_SIZE_BYTES,
        "max_size_mb": FileSizeValidator.DEFAULT_MAX_SIZE_BYTES / (1024 * 1024),
    }
