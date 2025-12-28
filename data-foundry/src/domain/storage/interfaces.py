"""
Storage Domain Interfaces

Abstract interface for storage operations.
Follows Interface Segregation and Dependency Inversion principles.

SOLID Principles:
- Interface Segregation: Only essential storage methods exposed
- Dependency Inversion: Application depends on this interface, not implementations
- Liskov Substitution: R2, S3, GCS implementations can all substitute
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict

from .value_objects import PresignedUrl, StorageMetadata


class IStorageService(ABC):
    """
    Interface for object storage operations.

    This interface is intentionally minimal (Interface Segregation).
    It exposes only the core operations needed for file storage:
    - upload: Store a file
    - download: Generate presigned download URL
    - delete: Remove a file
    - exists: Check if a file exists
    - health_check: Verify connectivity

    Implementations:
    - R2StorageService (Cloudflare R2)
    - S3StorageService (AWS S3)
    - LocalStorageService (Development/Testing)
    """

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload file to storage.

        Args:
            key: Storage key (path) for the file
            data: File content as bytes
            metadata: Optional metadata to attach to the object
            content_type: MIME type of the content

        Returns:
            URL or key of the uploaded file

        Raises:
            StorageError: If upload fails
            StorageConnectionError: If storage is unavailable
        """
        pass

    @abstractmethod
    async def download_url(
        self,
        key: str,
        expires_in_seconds: int = 3600,
    ) -> PresignedUrl:
        """
        Generate a presigned URL for downloading a file.

        Args:
            key: Storage key of the file
            expires_in_seconds: URL validity duration (default 1 hour)

        Returns:
            PresignedUrl with the download URL and expiry info

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageError: If URL generation fails
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a file from storage.

        Args:
            key: Storage key of the file to delete

        Returns:
            True if deleted, False if file didn't exist

        Raises:
            StorageError: If deletion fails
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            key: Storage key to check

        Returns:
            True if file exists, False otherwise

        Raises:
            StorageError: If check fails
        """
        pass

    @abstractmethod
    async def get_metadata(self, key: str) -> Optional[StorageMetadata]:
        """
        Get metadata for a stored file.

        Args:
            key: Storage key of the file

        Returns:
            StorageMetadata if file exists, None otherwise

        Raises:
            StorageError: If metadata retrieval fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if storage service is healthy and accessible.

        Returns:
            True if storage is accessible, False otherwise
        """
        pass

    @abstractmethod
    async def list_objects(
        self,
        prefix: str,
        max_keys: int = 1000,
    ) -> list[StorageMetadata]:
        """
        List objects with a given prefix.

        Args:
            prefix: Key prefix to filter by (e.g., tenant_id/)
            max_keys: Maximum number of keys to return

        Returns:
            List of StorageMetadata for matching objects

        Raises:
            StorageError: If listing fails
        """
        pass
