"""
R2 Storage Service

Cloudflare R2 implementation of IStorageService.
R2 is S3-compatible, so we use boto3 with custom endpoint.

SOLID Principles:
- Liskov Substitution: Can replace any IStorageService
- Single Responsibility: Only handles R2 storage operations
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

from src.domain.storage.interfaces import IStorageService
from src.domain.storage.value_objects import PresignedUrl, StorageMetadata
from src.domain.storage.exceptions import (
    StorageError,
    StorageConnectionError,
    StorageNotFoundError,
)

logger = logging.getLogger(__name__)


class R2StorageService(IStorageService):
    """
    Cloudflare R2 Storage Service

    Implements IStorageService using Cloudflare R2 (S3-compatible API).

    Features:
    - S3-compatible API via boto3
    - Presigned URLs for secure file access
    - Automatic retry for transient failures
    - Health checks for monitoring

    Configuration:
    - R2_ACCOUNT_ID: Cloudflare account ID
    - R2_ACCESS_KEY_ID: R2 access key
    - R2_SECRET_ACCESS_KEY: R2 secret key
    - R2_BUCKET_NAME: Target bucket name
    """

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        region: str = "auto",
    ):
        """
        Initialize R2 storage service.

        Args:
            account_id: Cloudflare account ID
            access_key_id: R2 access key ID
            secret_access_key: R2 secret access key
            bucket_name: R2 bucket name
            region: Region (default: auto)
        """
        self._bucket = bucket_name
        self._account_id = account_id

        # Build R2 endpoint URL
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

        # Configure boto3 client for R2
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

        logger.info(f"R2StorageService initialized for bucket: {bucket_name}")

    async def upload(
        self,
        key: str,
        data: bytes,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload file to R2.

        Args:
            key: Storage key (path)
            data: File content
            metadata: Optional metadata dict
            content_type: Optional MIME type

        Returns:
            URL of uploaded object

        Raises:
            StorageError: If upload fails
        """
        try:
            put_params = {
                "Bucket": self._bucket,
                "Key": key,
                "Body": data,
            }

            if metadata:
                put_params["Metadata"] = metadata

            if content_type:
                put_params["ContentType"] = content_type

            self._client.put_object(**put_params)

            logger.info(f"Uploaded {len(data)} bytes to {key}")

            # Return presigned URL for the uploaded object
            presigned = await self.download_url(key)
            return presigned.url

        except NoCredentialsError as e:
            logger.error("R2 credentials not configured")
            raise StorageConnectionError(
                message="Storage credentials not configured",
                original_error=e,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"R2 upload failed: {error_code} - {e}")
            raise StorageError(
                message=f"Upload failed: {error_code}",
                key=key,
                original_error=e,
            )
        except Exception as e:
            logger.error(f"Unexpected error during upload: {e}")
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
        Generate presigned URL for downloading.

        Args:
            key: Storage key
            expires_in_seconds: URL validity (default 1 hour)

        Returns:
            PresignedUrl with download URL

        Raises:
            StorageNotFoundError: If key doesn't exist
            StorageError: If URL generation fails
        """
        try:
            # Verify object exists
            exists = await self.exists(key)
            if not exists:
                raise StorageNotFoundError(key=key)

            # Generate presigned URL
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in_seconds,
            )

            expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

            return PresignedUrl(
                url=url,
                expires_at=expires_at,
                method="GET",
                bucket=self._bucket,
                key=key,
            )

        except StorageNotFoundError:
            raise
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise StorageError(
                message="Failed to generate download URL",
                key=key,
                original_error=e,
            )

    async def delete(self, key: str) -> bool:
        """
        Delete file from R2.

        Args:
            key: Storage key

        Returns:
            True if deleted, False if didn't exist

        Raises:
            StorageError: If deletion fails
        """
        try:
            # Check if exists first
            exists = await self.exists(key)
            if not exists:
                return False

            self._client.delete_object(
                Bucket=self._bucket,
                Key=key,
            )

            logger.info(f"Deleted object: {key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete {key}: {e}")
            raise StorageError(
                message="Delete failed",
                key=key,
                original_error=e,
            )

    async def exists(self, key: str) -> bool:
        """
        Check if file exists in R2.

        Args:
            key: Storage key

        Returns:
            True if exists, False otherwise
        """
        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=key,
            )
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return False
            # Other errors should be raised
            raise StorageError(
                message="Failed to check object existence",
                key=key,
                original_error=e,
            )

    async def get_metadata(self, key: str) -> Optional[StorageMetadata]:
        """
        Get metadata for a stored file.

        Args:
            key: Storage key

        Returns:
            StorageMetadata if exists, None otherwise
        """
        try:
            response = self._client.head_object(
                Bucket=self._bucket,
                Key=key,
            )

            return StorageMetadata(
                key=key,
                size_bytes=response["ContentLength"],
                content_type=response.get("ContentType", "application/octet-stream"),
                last_modified=response["LastModified"],
                etag=response.get("ETag", "").strip('"'),
                metadata=response.get("Metadata", {}),
            )

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return None
            raise StorageError(
                message="Failed to get metadata",
                key=key,
                original_error=e,
            )

    async def health_check(self) -> bool:
        """
        Check if R2 is accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return True
        except Exception as e:
            logger.warning(f"R2 health check failed: {e}")
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
        try:
            response = self._client.list_objects_v2(
                Bucket=self._bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
            )

            objects = []
            for obj in response.get("Contents", []):
                objects.append(
                    StorageMetadata(
                        key=obj["Key"],
                        size_bytes=obj["Size"],
                        content_type="application/octet-stream",  # list doesn't return content type
                        last_modified=obj["LastModified"],
                        etag=obj.get("ETag", "").strip('"'),
                    )
                )

            return objects

        except ClientError as e:
            logger.error(f"Failed to list objects: {e}")
            raise StorageError(
                message="Failed to list objects",
                original_error=e,
            )


class R2StorageServiceFactory:
    """
    Factory for creating R2StorageService instances.

    Handles configuration loading from environment.
    """

    @staticmethod
    def from_config() -> R2StorageService:
        """
        Create R2StorageService from environment configuration.

        Returns:
            Configured R2StorageService

        Raises:
            ValueError: If required config is missing
        """
        import os

        account_id = os.getenv("R2_ACCOUNT_ID")
        access_key = os.getenv("R2_ACCESS_KEY_ID")
        secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        bucket = os.getenv("R2_BUCKET_NAME")

        if not all([account_id, access_key, secret_key, bucket]):
            raise ValueError(
                "Missing R2 configuration. Required: "
                "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME"
            )

        return R2StorageService(
            account_id=account_id,
            access_key_id=access_key,
            secret_access_key=secret_key,
            bucket_name=bucket,
        )
