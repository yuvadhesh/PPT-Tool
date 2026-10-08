"""
Storage Service — S3-compatible storage using boto3.
Configured for MinIO by default.
"""
import io
import uuid
from typing import Optional
import boto3
from botocore.exceptions import ClientError
from botocore.client import Config

from app.core.config import settings
from app.core.logging import logger


class StorageService:
    def __init__(self):
        self._client = None
        self._s3_available = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT if not settings.S3_USE_SSL else None,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=1,
                    read_timeout=1,
                    retries={"max_attempts": 1},
                ),
            )
        return self._client

    def _check_s3(self) -> bool:
        if self._s3_available is not None:
            return self._s3_available
        import socket
        from urllib.parse import urlparse
        try:
            parsed = urlparse(settings.S3_ENDPOINT)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if settings.S3_USE_SSL else 9000)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                if s.connect_ex((host, port)) != 0:
                    self._s3_available = False
                    return False
            client = self._get_client()
            client.head_bucket(Bucket=settings.S3_BUCKET)
            self._s3_available = True
        except Exception:
            self._s3_available = False
        return self._s3_available

    def _local_path_for_key(self, key: str) -> str:
        import os
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "media_storage"))
        full_path = os.path.join(base_dir, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        return full_path

    def upload_file(
        self,
        file_data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes to S3, falling back to local disk if S3 is unavailable."""
        if not self._check_s3():
            local_path = self._local_path_for_key(key)
            with open(local_path, "wb") as f:
                f.write(file_data)
            return key

        try:
            client = self._get_client()
            client.put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
            logger.info("Uploaded file to S3", key=key, size=len(file_data))
            return key
        except Exception as e:
            logger.warning("S3 upload failed, saving to local disk", error=str(e), key=key)
            local_path = self._local_path_for_key(key)
            with open(local_path, "wb") as f:
                f.write(file_data)
            return key

    def upload_from_path(
        self,
        file_path: str,
        key: str,
        content_type: str = "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ) -> str:
        """Upload a file from disk path to S3 or local fallback."""
        with open(file_path, "rb") as f:
            data = f.read()
        return self.upload_file(data, key, content_type)

    def download_file(self, key: str) -> Optional[bytes]:
        """Download a file from S3 or local fallback."""
        import os
        if not self._check_s3():
            local_path = self._local_path_for_key(key)
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    return f.read()
            return None

        try:
            client = self._get_client()
            response = client.get_object(Bucket=settings.S3_BUCKET, Key=key)
            return response["Body"].read()
        except Exception as e:
            logger.info("S3 download failed, checking local disk", key=key, error=str(e))
            local_path = self._local_path_for_key(key)
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    return f.read()
            logger.error("File not found in S3 or local disk", key=key)
            return None

    def download_to_path(self, key: str, local_path: str) -> bool:
        """Download a file from S3 or local disk to a local path."""
        data = self.download_file(key)
        if data is None:
            return False
        with open(local_path, "wb") as f:
            f.write(data)
        return True

    def generate_presigned_url(self, key: str, expiry_seconds: int = 3600) -> Optional[str]:
        """Generate a pre-signed URL for temporary download access."""
        if not self._check_s3():
            return None
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.S3_BUCKET, "Key": key},
                ExpiresIn=expiry_seconds,
            )
            return url
        except Exception as e:
            logger.error("Failed to generate presigned URL", key=key, error=str(e))
            return None

    def delete_file(self, key: str) -> bool:
        """Delete a file from S3 or local disk."""
        deleted = False
        import os
        if self._check_s3():
            try:
                client = self._get_client()
                client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
                deleted = True
            except Exception as e:
                logger.error("S3 delete failed", key=key, error=str(e))

        local_path = self._local_path_for_key(key)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                deleted = True
            except Exception:
                pass
        return deleted

    def make_key(self, prefix: str, filename: str) -> str:
        """Generate a unique S3 key."""
        unique = str(uuid.uuid4())
        return f"{prefix}/{unique}/{filename}"


storage_service = StorageService()
