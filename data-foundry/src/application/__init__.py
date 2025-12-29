"""
Application Layer - Data Foundry

This package contains application services that orchestrate domain logic.
Services in this layer:
- Depend on domain interfaces (Dependency Inversion)
- Coordinate between domain objects
- Handle cross-cutting concerns (logging, transactions)
- Define use case boundaries

SOLID Principles Applied:
- Single Responsibility: Each service handles one use case area
- Open/Closed: Services extensible via dependency injection
- Dependency Inversion: Depend on abstractions, not implementations
"""

from .file_validation_service import FileValidationService
from .upload_service import UploadService
from .job_tracking_service import JobTrackingService
from .upload_pipeline import UploadPipeline

__all__ = [
    "FileValidationService",
    "UploadService",
    "JobTrackingService",
    "UploadPipeline",
]
