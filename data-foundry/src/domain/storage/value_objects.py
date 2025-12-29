"""
Storage Domain Value Objects

Value objects for storage operations.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class StorageKey(BaseModel):
    """
    Value Object: Represents a storage key (path) in object storage.

    The key follows the pattern: {tenant_id}/{job_id}/{filename}
    This ensures tenant isolation and job association.
    """
    tenant_id: str = Field(..., min_length=1)
    job_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)

    model_config = {"frozen": True}  # Immutable

    @field_validator("tenant_id", "job_id")
    @classmethod
    def validate_path_segment(cls, v: str) -> str:
        """Ensure path segments don't contain dangerous characters."""
        if "/" in v or "\\" in v:
            raise ValueError("Path segment cannot contain slashes")
        if ".." in v:
            raise ValueError("Path segment cannot contain '..'")
        return v

    @property
    def full_path(self) -> str:
        """Get the full storage path."""
        return f"{self.tenant_id}/{self.job_id}/{self.filename}"

    def __str__(self) -> str:
        return self.full_path


class PresignedUrl(BaseModel):
    """
    Value Object: A presigned URL for temporary storage access.

    Presigned URLs allow temporary access to objects without
    exposing storage credentials.
    """
    url: str
    expires_at: datetime
    method: str = "GET"  # GET for download, PUT for upload
    bucket: str
    key: str

    model_config = {"frozen": True}  # Immutable

    @property
    def is_expired(self) -> bool:
        """Check if the URL has expired."""
        return datetime.utcnow() >= self.expires_at

    @property
    def seconds_until_expiry(self) -> int:
        """Get seconds until URL expires."""
        delta = self.expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds()))


class StorageMetadata(BaseModel):
    """
    Value Object: Metadata about a stored object.
    """
    key: str
    size_bytes: int
    content_type: str
    last_modified: datetime
    etag: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    model_config = {"frozen": True}  # Immutable

    @property
    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size_bytes / (1024 * 1024)
