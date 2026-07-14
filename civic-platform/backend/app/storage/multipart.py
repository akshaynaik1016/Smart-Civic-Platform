"""
Multipart upload
==================
boto3's `put_object` is fine for the compressed complaint photos
StorageService already handles (a few hundred KB after compression to
1920px/JPEG-82). It is NOT fine for anything larger — a generated PDF
monthly report, an officer's bulk CSV export with embedded data, or an
uncompressed "before/after" resolution photo set a citizen might upload
at full camera resolution before compression kicks in.

AWS's own guidance is to use multipart upload above 100MB, and the
`TransferConfig`-based `upload_fileobj`/`upload_file` helpers handle the
multipart orchestration (splitting into parts, parallel part upload,
abort-on-failure cleanup) automatically — this module just wires that up
with this platform's conventions (key naming, error translation, the
async-via-executor pattern the rest of storage_service.py already uses).
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

from app.core.config import settings
from app.storage.s3_client import get_s3_client
from app.storage.s3_errors import translate_s3_error

logger = logging.getLogger(__name__)

# Above this size, boto3's TransferConfig will automatically split into
# multipart upload; below it, a single PUT is used. 8MB matches S3's own
# minimum multipart part size, so there's no benefit to multipart below it.
_MULTIPART_THRESHOLD_BYTES = 8 * 1024 * 1024


def _build_transfer_config():
    from boto3.s3.transfer import TransferConfig

    return TransferConfig(
        multipart_threshold=_MULTIPART_THRESHOLD_BYTES,
        multipart_chunksize=_MULTIPART_THRESHOLD_BYTES,
        max_concurrency=4,
        use_threads=True,
    )


async def upload_large_file(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    *,
    metadata: Optional[dict[str, str]] = None,
    progress_callback: Optional[callable] = None,
) -> str:
    """
    Upload a file of any size, using multipart automatically above the
    threshold. Returns the resulting object's URL (CDN-prefixed if
    configured, otherwise the direct S3 URL).

    `progress_callback`, if given, is called with the cumulative bytes
    uploaded so far — useful for a future "report generation progress"
    UI, though nothing currently wires it up to a websocket/SSE endpoint.
    """
    loop = asyncio.get_event_loop()

    def _do_upload() -> None:
        client = get_s3_client()
        config = _build_transfer_config()

        extra_args: dict = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = metadata

        fileobj = io.BytesIO(data)

        try:
            client.upload_fileobj(
                fileobj,
                settings.AWS_S3_BUCKET,
                key,
                Config=config,
                ExtraArgs=extra_args,
                Callback=progress_callback,
            )
        except Exception as exc:
            raise translate_s3_error(exc, context=f"Multipart upload of '{key}'") from exc

    await loop.run_in_executor(None, _do_upload)

    logger.info(
        "Uploaded %s (%d bytes, %s)",
        key, len(data),
        "multipart" if len(data) >= _MULTIPART_THRESHOLD_BYTES else "single-part",
    )

    if settings.AWS_S3_CDN_URL:
        return f"{settings.AWS_S3_CDN_URL.rstrip('/')}/{key}"
    return f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"


async def download_large_file(key: str) -> bytes:
    """
    Download an object of any size via streaming, rather than a single
    `get_object` call that buffers the whole body in memory at once
    inside botocore before handing it back. Used by report generation
    when re-reading a previously uploaded artifact, and by the AI
    re-analysis endpoint when fetching a stored complaint photo back
    for a second inference pass.
    """
    loop = asyncio.get_event_loop()

    def _do_download() -> bytes:
        client = get_s3_client()
        buf = io.BytesIO()
        try:
            client.download_fileobj(settings.AWS_S3_BUCKET, key, buf)
        except Exception as exc:
            raise translate_s3_error(exc, context=f"Download of '{key}'") from exc
        return buf.getvalue()

    return await loop.run_in_executor(None, _do_download)
