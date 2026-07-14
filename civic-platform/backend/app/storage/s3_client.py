"""
S3 client factory
===================
Builds a properly-configured boto3 S3 client, separated out from
StorageService so the connection/retry configuration is in exactly one
place and is independently testable.

Why this exists as its own module rather than living inline in
StorageService._get_client(): the original inline version
(`boto3.client("s3", ...)` with no further config) inherits boto3's
defaults — 3 retries with `legacy` mode, no explicit connection pool size,
no read/connect timeout. Under real load (e.g. an officer dashboard bulk-
exporting CSV with embedded presigned URLs, or the AI pipeline downloading
an image for re-analysis) that's not configuration, it's an accident
waiting to happen: a hung connection to S3 can stall a request thread with
no timeout to release it.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_client = None


def get_s3_client():
    """
    Return a process-wide singleton boto3 S3 client with sane production
    defaults. Thread-safe lazy initialisation — boto3 clients are
    thread-safe once constructed, but construction itself is not
    guaranteed to be, hence the lock.
    """
    global _client

    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:   # re-check after acquiring the lock
            return _client

        import boto3
        from botocore.config import Config

        boto_config = Config(
            region_name=settings.AWS_REGION,
            # Adaptive retry mode backs off and retries on throttling
            # (503 SlowDown) as well as transient network errors — the
            # `legacy` default boto3 mode only retries a narrower set.
            retries={"max_attempts": 4, "mode": "adaptive"},
            connect_timeout=5,
            read_timeout=20,
            max_pool_connections=25,
        )

        _client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=boto_config,
        )
        logger.info(
            "S3 client initialised (region=%s, bucket=%s)",
            settings.AWS_REGION, settings.AWS_S3_BUCKET,
        )

    return _client


def get_s3_resource():
    """
    Return the higher-level boto3 S3 *resource* — used for multipart
    upload via TransferManager, which the resource/Bucket API exposes
    more conveniently than the raw client API.
    """
    import boto3

    return boto3.resource(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


def reset_client() -> None:
    """Used by tests to force re-construction with fresh settings/mocks."""
    global _client
    with _client_lock:
        _client = None


def is_s3_configured() -> bool:
    return bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY)
