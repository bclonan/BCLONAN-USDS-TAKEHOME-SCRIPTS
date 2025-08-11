"""Storage abstraction for uploading scraped artifacts to remote backends.

Currently supports:
 - Local noop (default)
 - Amazon S3 (requires boto3 and credentials)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, Any
import shutil
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    def upload(self, local_path: str, remote_path: Optional[str] = None) -> str:
        """Upload a local file; return a URL or identifier."""
        ...  # pragma: no cover


@dataclass
class NoopStorage:
    base_url: str = ""

    def upload(self, local_path: str, remote_path: Optional[str] = None) -> str:
        logger.debug("NoopStorage: skipping upload for %s", local_path)
        return local_path


@dataclass
class S3Storage:
    bucket: str
    prefix: str = "ecfr"
    public: bool = True
    _client: Any = None  # lazy

    def _ensure_client(self):
        if self._client is None:
            try:
                import boto3  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("boto3 not installed. Install with 'pip install ecfr-scraper[storage]'.") from e
            self._client = boto3.client("s3")
        return self._client

    def upload(self, local_path: str, remote_path: Optional[str] = None) -> str:
        client = self._ensure_client()
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)
        key = remote_path or f"{self.prefix}/{os.path.basename(local_path)}"
        extra = {"ACL": "public-read"} if self.public else {}
        logger.info("Uploading %s to s3://%s/%s", local_path, self.bucket, key)
        client.upload_file(local_path, self.bucket, key, ExtraArgs=extra or None)
        if self.public:
            return f"https://{self.bucket}.s3.amazonaws.com/{key}"
        return f"s3://{self.bucket}/{key}"


def build_storage(backend: str | None, bucket: str | None = None, prefix: str = "ecfr", public: bool = True) -> StorageBackend:
    if backend == "s3":
        if not bucket:
            raise ValueError("S3 backend requires --storage-bucket")
        return S3Storage(bucket=bucket, prefix=prefix, public=public)
    if backend == "folder":
        if not bucket:
            raise ValueError("Folder backend requires --storage-bucket to specify target directory path")
        return FolderStorage(root=bucket, prefix=prefix)
    return NoopStorage()


@dataclass
class FolderStorage:
    """Copy files into a designated folder (static artifact staging).

    The 'bucket' argument from CLI is repurposed as the absolute or relative
    path to the root folder. A base URL can be applied later when serving
    (e.g. GitHub Pages, Netlify, S3 website) by post-processing the manifest.
    """
    root: str
    prefix: str = "ecfr"

    def upload(self, local_path: str, remote_path: Optional[str] = None) -> str:
        target_root = Path(self.root).expanduser().resolve()
        target_root.mkdir(parents=True, exist_ok=True)
        filename = os.path.basename(local_path)
        rel_key = remote_path or f"{self.prefix}/{filename}"
        dest_path = target_root / rel_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest_path)
        logger.info("Copied %s -> %s", local_path, dest_path)
        return str(dest_path)
