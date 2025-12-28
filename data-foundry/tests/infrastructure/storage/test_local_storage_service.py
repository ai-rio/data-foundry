"""
Tests for LocalStorageService

TDD tests for the local filesystem storage implementation.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.infrastructure.storage.local_storage_service import LocalStorageService
from src.domain.storage.value_objects import PresignedUrl, StorageMetadata
from src.domain.storage.exceptions import StorageError, StorageNotFoundError


@pytest.fixture
def temp_storage_path():
    """Create a temporary directory for storage tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def storage(temp_storage_path):
    """Create LocalStorageService with temp directory."""
    return LocalStorageService(base_path=temp_storage_path)


class TestLocalStorageServiceCreation:
    """Tests for LocalStorageService initialization."""

    def test_create_service(self, temp_storage_path):
        """Should create service with base path."""
        service = LocalStorageService(base_path=temp_storage_path)

        assert service._base_path == Path(temp_storage_path)

    def test_creates_base_directory(self, temp_storage_path):
        """Should create base directory if not exists."""
        new_path = Path(temp_storage_path) / "new_subdir"

        LocalStorageService(base_path=str(new_path))

        assert new_path.exists()


class TestLocalStorageServiceUpload:
    """Tests for LocalStorageService.upload()."""

    @pytest.mark.asyncio
    async def test_upload_creates_file(self, storage, temp_storage_path):
        """Should create file with content."""
        content = b"test content"

        await storage.upload(
            key="tenant/job/data.csv",
            data=content,
        )

        file_path = Path(temp_storage_path) / "tenant" / "job" / "data.csv"
        assert file_path.exists()
        assert file_path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_upload_returns_file_url(self, storage, temp_storage_path):
        """Should return file:// URL."""
        result = await storage.upload(
            key="tenant/job/data.csv",
            data=b"content",
        )

        assert result.startswith("file://")
        assert "tenant/job/data.csv" in result

    @pytest.mark.asyncio
    async def test_upload_creates_parent_dirs(self, storage, temp_storage_path):
        """Should create parent directories."""
        await storage.upload(
            key="deep/nested/path/file.txt",
            data=b"content",
        )

        file_path = Path(temp_storage_path) / "deep" / "nested" / "path" / "file.txt"
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_upload_stores_metadata(self, storage, temp_storage_path):
        """Should store metadata in sidecar file."""
        await storage.upload(
            key="file.txt",
            data=b"content",
            metadata={"tenant_id": "tenant-123"},
            content_type="text/plain",
        )

        meta_path = Path(temp_storage_path) / "file.txt.meta"
        assert meta_path.exists()

        import json
        meta = json.loads(meta_path.read_text())
        assert meta["content_type"] == "text/plain"
        assert meta["metadata"]["tenant_id"] == "tenant-123"

    @pytest.mark.asyncio
    async def test_upload_prevents_path_traversal(self, storage, temp_storage_path):
        """Should prevent path traversal attacks."""
        # Attempt path traversal
        await storage.upload(
            key="../../../etc/passwd",
            data=b"malicious",
        )

        # Should NOT create file outside base path
        assert not Path("/etc/passwd").exists() or Path("/etc/passwd").read_bytes() != b"malicious"

        # Should create inside base path (with .. stripped)
        safe_path = Path(temp_storage_path) / "etc" / "passwd"
        assert safe_path.exists()


class TestLocalStorageServiceDownloadUrl:
    """Tests for LocalStorageService.download_url()."""

    @pytest.mark.asyncio
    async def test_download_url_returns_presigned(self, storage):
        """Should return PresignedUrl."""
        await storage.upload("file.txt", b"content")

        result = await storage.download_url("file.txt")

        assert isinstance(result, PresignedUrl)
        assert result.url.startswith("file://")
        assert result.method == "GET"
        assert result.bucket == "local"

    @pytest.mark.asyncio
    async def test_download_url_not_found(self, storage):
        """Should raise StorageNotFoundError for missing file."""
        with pytest.raises(StorageNotFoundError):
            await storage.download_url("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_download_url_sets_expiry(self, storage):
        """Should set expiry time."""
        await storage.upload("file.txt", b"content")

        result = await storage.download_url("file.txt", expires_in_seconds=3600)

        assert not result.is_expired


class TestLocalStorageServiceDelete:
    """Tests for LocalStorageService.delete()."""

    @pytest.mark.asyncio
    async def test_delete_existing(self, storage, temp_storage_path):
        """Should delete existing file."""
        await storage.upload("file.txt", b"content")
        file_path = Path(temp_storage_path) / "file.txt"
        assert file_path.exists()

        result = await storage.delete("file.txt")

        assert result is True
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, storage):
        """Should return False for non-existent file."""
        result = await storage.delete("nonexistent.txt")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_removes_metadata(self, storage, temp_storage_path):
        """Should also delete metadata sidecar."""
        await storage.upload(
            "file.txt",
            b"content",
            metadata={"key": "value"},
        )
        meta_path = Path(temp_storage_path) / "file.txt.meta"
        assert meta_path.exists()

        await storage.delete("file.txt")

        assert not meta_path.exists()


class TestLocalStorageServiceExists:
    """Tests for LocalStorageService.exists()."""

    @pytest.mark.asyncio
    async def test_exists_true(self, storage):
        """Should return True for existing file."""
        await storage.upload("file.txt", b"content")

        result = await storage.exists("file.txt")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, storage):
        """Should return False for non-existent file."""
        result = await storage.exists("nonexistent.txt")

        assert result is False


class TestLocalStorageServiceGetMetadata:
    """Tests for LocalStorageService.get_metadata()."""

    @pytest.mark.asyncio
    async def test_get_metadata_existing(self, storage):
        """Should return metadata for existing file."""
        content = b"test content"
        await storage.upload(
            "file.txt",
            content,
            metadata={"key": "value"},
            content_type="text/plain",
        )

        result = await storage.get_metadata("file.txt")

        assert isinstance(result, StorageMetadata)
        assert result.key == "file.txt"
        assert result.size_bytes == len(content)
        assert result.content_type == "text/plain"
        assert result.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_metadata_nonexistent(self, storage):
        """Should return None for non-existent file."""
        result = await storage.get_metadata("nonexistent.txt")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_metadata_size_mb(self, storage):
        """Should calculate size_mb correctly."""
        content = b"x" * (1024 * 1024)  # 1MB
        await storage.upload("large.txt", content)

        result = await storage.get_metadata("large.txt")

        assert result.size_mb == 1.0


class TestLocalStorageServiceHealthCheck:
    """Tests for LocalStorageService.health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, storage):
        """Should return True when storage is accessible."""
        result = await storage.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, temp_storage_path):
        """Should return False when storage is inaccessible."""
        # Remove the storage directory
        shutil.rmtree(temp_storage_path)

        storage = LocalStorageService(base_path=temp_storage_path)
        # Now make it unwritable
        import os
        os.chmod(temp_storage_path, 0o000)

        try:
            result = await storage.health_check()
            assert result is False
        finally:
            os.chmod(temp_storage_path, 0o755)


class TestLocalStorageServiceListObjects:
    """Tests for LocalStorageService.list_objects()."""

    @pytest.mark.asyncio
    async def test_list_objects_with_prefix(self, storage):
        """Should list objects with prefix."""
        await storage.upload("tenant-1/file1.txt", b"content")
        await storage.upload("tenant-1/file2.txt", b"content")
        await storage.upload("tenant-2/file3.txt", b"content")

        result = await storage.list_objects("tenant-1/")

        assert len(result) == 2
        assert all(m.key.startswith("tenant-1/") for m in result)

    @pytest.mark.asyncio
    async def test_list_objects_max_keys(self, storage):
        """Should respect max_keys limit."""
        for i in range(5):
            await storage.upload(f"file{i}.txt", b"content")

        result = await storage.list_objects("", max_keys=3)

        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_list_objects_empty(self, storage):
        """Should return empty list for no matches."""
        result = await storage.list_objects("nonexistent/")

        assert result == []


class TestLocalStorageServiceClearAll:
    """Tests for LocalStorageService.clear_all()."""

    @pytest.mark.asyncio
    async def test_clear_all(self, storage, temp_storage_path):
        """Should remove all stored files."""
        await storage.upload("file1.txt", b"content")
        await storage.upload("file2.txt", b"content")

        storage.clear_all()

        assert not (Path(temp_storage_path) / "file1.txt").exists()
        assert not (Path(temp_storage_path) / "file2.txt").exists()

    def test_clear_all_recreates_base_dir(self, storage, temp_storage_path):
        """Should recreate base directory after clearing."""
        storage.clear_all()

        assert Path(temp_storage_path).exists()
