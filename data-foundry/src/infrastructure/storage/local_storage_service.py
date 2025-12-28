"""
Local Storage Service

Local filesystem implementation of IStorageService for development/testing.

SOLID Principles:
- Liskov Substitution: Can substitute for R2StorageService
- Single Responsibility: Only handles local file operations
"""

import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

from src.domain.storage.interfaces import IStorageService
from src.domain.storage.value_objects import PresignedUrl, StorageMetadata
from src.domain.storage.exceptions import StorageError, StorageNotFoundError

logger = logging.getLogger(__name__)


class LocalStorageService(IStorageService):
    """
    Local Filesystem Storage Service

    Implements IStorageService using local filesystem.
    Useful for development and testing without cloud dependencies.

    Note: This is NOT suitable for production use as it:
    - Doesn't support real presigned URLs (returns file:// paths)
    - Has no multi-node support
    - Has no durability guarantees
    """

    def __init__(self, base_path: str = "/tmp/data_foundry_storage"):
        """
        Initialize local storage.

        Args:
            base_path: Root directory for storage
        """
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"LocalStorageService initialized at: {self._base_path}")

    def _get_full_path(self, key: str) -> Path:
        """Get full filesystem path for a key."""
        # Security: Prevent path traversal
        clean_key = key.replace("..", "").lstrip("/")
        return self._base_path / clean_key

    async def upload(
        self,
        key: str,
        data: bytes,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload file to local storage.

        Args:
            key: Storage key (path)
            data: File content
            metadata: Optional metadata (stored as sidecar file)
            content_type: Optional MIME type

        Returns:
            File path URL
        """
        try:
            full_path = self._get_full_path(key)

            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            full_path.write_bytes(data)

            # Store metadata in sidecar file
            if metadata or content_type:
                import json
                meta_path = full_path.with_suffix(full_path.suffix + ".meta")
                meta_data = {
                    "content_type": content_type,
                    "metadata": metadata or {},
                    "uploaded_at": datetime.utcnow().isoformat(),
                }
                meta_path.write_text(json.dumps(meta_data))

            logger.info(f"Uploaded {len(data)} bytes to {key}")

            # Return file:// URL
            return f"file://{full_path}"

        except Exception as e:
            logger.error(f"Local upload failed: {e}")
            raise StorageError(
                message=f"Upload failed: {str(e)}",
                key=key,
                original_error=e,
            )

    async def download_url(
        self,
        key: str,
        expires_in_seconds: int = 3600,
    ) -> PresignedUrl:
        """
        Get "presigned" URL (file path) for download.

        Args:
            key: Storage key
            expires_in_seconds: Ignored for local storage

        Returns:
            PresignedUrl with file:// URL
        """
        full_path = self._get_full_path(key)

        if not full_path.exists():
            raise StorageNotFoundError(key=key)

        # Local storage doesn't have real expiry
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

        return PresignedUrl(
            url=f"file://{full_path}",
            expires_at=expires_at,
            method="GET",
            bucket="local",
            key=key,
        )

    async def delete(self, key: str) -> bool:
        """
        Delete file from local storage.

        Args:
            key: Storage key

        Returns:
            True if deleted, False if didn't exist
        """
        full_path = self._get_full_path(key)

        if not full_path.exists():
            return False

        try:
            full_path.unlink()

            # Also delete metadata sidecar if exists
            meta_path = full_path.with_suffix(full_path.suffix + ".meta")
            if meta_path.exists():
                meta_path.unlink()

            logger.info(f"Deleted: {key}")
            return True

        except Exception as e:
            logger.error(f"Delete failed: {e}")
            raise StorageError(
                message=f"Delete failed: {str(e)}",
                key=key,
                original_error=e,
            )

    async def exists(self, key: str) -> bool:
        """
        Check if file exists.

        Args:
            key: Storage key

        Returns:
            True if exists
        """
        full_path = self._get_full_path(key)
        return full_path.exists()

    async def get_metadata(self, key: str) -> Optional[StorageMetadata]:
        """
        Get metadata for file.

        Args:
            key: Storage key

        Returns:
            StorageMetadata if exists, None otherwise
        """
        full_path = self._get_full_path(key)

        if not full_path.exists():
            return None

        stat = full_path.stat()

        # Try to read sidecar metadata
        content_type = "application/octet-stream"
        metadata = {}

        meta_path = full_path.with_suffix(full_path.suffix + ".meta")
        if meta_path.exists():
            import json
            try:
                meta_data = json.loads(meta_path.read_text())
                content_type = meta_data.get("content_type", content_type)
                metadata = meta_data.get("metadata", {})
            except Exception:
                pass

        return StorageMetadata(
            key=key,
            size_bytes=stat.st_size,
            content_type=content_type,
            last_modified=datetime.fromtimestamp(stat.st_mtime),
            metadata=metadata,
        )

    async def health_check(self) -> bool:
        """
        Check if local storage is accessible.

        Returns:
            True if healthy
        """
        try:
            # Try to write and read a test file
            test_path = self._base_path / ".health_check"
            test_path.write_text("ok")
            content = test_path.read_text()
            test_path.unlink()
            return content == "ok"
        except Exception as e:
            logger.warning(f"Local storage health check failed: {e}")
            return False

    async def list_objects(
        self,
        prefix: str,
        max_keys: int = 1000,
    ) -> List[StorageMetadata]:
        """
        List objects with given prefix.

        Args:
            prefix: Key prefix filter
            max_keys: Maximum keys to return

        Returns:
            List of StorageMetadata
        """
        prefix_path = self._get_full_path(prefix)

        if not prefix_path.parent.exists():
            return []

        objects = []
        base_len = len(str(self._base_path)) + 1

        # Walk directory
        for path in prefix_path.parent.glob("**/*"):
            if path.is_file() and not path.suffix == ".meta":
                key = str(path)[base_len:]

                if key.startswith(prefix):
                    metadata = await self.get_metadata(key)
                    if metadata:
                        objects.append(metadata)

                    if len(objects) >= max_keys:
                        break

        return objects

    def clear_all(self) -> None:
        """
        Clear all stored files.

        WARNING: This deletes all data!
        Only for testing purposes.
        """
        if self._base_path.exists():
            shutil.rmtree(self._base_path)
            self._base_path.mkdir(parents=True, exist_ok=True)
            logger.warning("Cleared all local storage")
