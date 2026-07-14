"""
StorageService — AWS S3 (or S3-compatible) media storage.

Handles:
  • Uploading complaint images (with thumbnail generation)
  • Generating presigned download URLs
  • Deleting objects on complaint deletion
  • Computing SHA-256 image hash (for duplicate detection)

If AWS credentials are not configured the service operates in
"local filesystem" mode — files are written to /tmp/civic_uploads/
and CDN URLs become relative paths. This is only for dev/test.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.storage.s3_client import get_s3_client, is_s3_configured
from app.storage.s3_errors import translate_s3_error, with_s3_retry

logger = logging.getLogger(__name__)

_LOCAL_DIR = Path("/tmp/civic_uploads")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _compress_image(data: bytes, content_type: str, max_px: int = 1920) -> bytes:
    """Resize image so neither dimension exceeds max_px. Returns JPEG bytes."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")

        w, h = img.size
        if w > max_px or h > max_px:
            img.thumbnail((max_px, max_px), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("Image compression failed — using original: %s", exc)
        return data


def _make_thumbnail(data: bytes, size: int = 320) -> bytes:
    """Generate a small JPEG thumbnail."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("Thumbnail generation failed: %s", exc)
        return data


def _image_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        return img.size  # (width, height)
    except Exception:
        return None, None


def _compute_phash(data: bytes) -> Optional[str]:
    """Perceptual hash for visual-similarity duplicate detection (cheap to store alongside SHA-256)."""
    try:
        import imagehash
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        return str(imagehash.phash(img, hash_size=16))
    except Exception as exc:
        logger.debug("pHash computation skipped: %s", exc)
        return None


def sniff_image_type(data: bytes) -> Optional[str]:
    """
    Return the real image MIME type based on file signature (magic bytes),
    independent of the client-supplied Content-Type header, which can be
    spoofed or simply wrong.
    """
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class StorageService:
    """Async-friendly S3 storage with local fallback."""

    def __init__(self) -> None:
        self._use_s3 = is_s3_configured()
        self._bucket = settings.AWS_S3_BUCKET
        self._cdn    = settings.AWS_S3_CDN_URL.rstrip("/") if settings.AWS_S3_CDN_URL else ""
        self._region = settings.AWS_REGION
        self._client = None

    def _get_client(self):
        if self._client is None and self._use_s3:
            self._client = get_s3_client()
        return self._client

    # ── Public API ────────────────────────────────────────────────────────────

    async def upload_complaint_image(
        self,
        complaint_id: str,
        image_bytes: bytes,
        content_type: str,
        original_filename: str = "",
        is_resolution: bool = False,
    ) -> dict:
        """
        Upload an image and its thumbnail for a complaint.

        Returns:
            {
                "s3_key":         str,
                "s3_bucket":      str,
                "cdn_url":        str,
                "thumbnail_url":  str,
                "image_hash":     str,     # SHA-256 of ORIGINAL bytes
                "file_size_bytes":int,
                "width_px":       int | None,
                "height_px":      int | None,
                "mime_type":      str,
            }
        """
        image_hash = _sha256(image_bytes)
        ext        = _ext_from_content_type(content_type)
        folder     = "resolutions" if is_resolution else "complaints"
        uid        = uuid.uuid4().hex

        # Validate the real file type — never trust the client header alone
        real_type = sniff_image_type(image_bytes)
        if real_type is None:
            logger.warning("Could not verify image signature — proceeding with declared content_type=%s", content_type)
        elif real_type != content_type:
            logger.info("Declared content_type=%s did not match sniffed=%s — using sniffed value", content_type, real_type)
            content_type = real_type

        # Compress main image
        compressed = _compress_image(image_bytes, content_type)
        width, height = _image_dimensions(compressed)
        phash = _compute_phash(compressed)

        # Build keys
        main_key  = f"{folder}/{complaint_id}/{uid}.jpg"
        thumb_key = f"{folder}/{complaint_id}/{uid}_thumb.jpg"
        thumbnail  = _make_thumbnail(compressed)

        if self._use_s3:
            cdn_url       = await self._s3_upload(main_key,  compressed, "image/jpeg")
            thumbnail_url = await self._s3_upload(thumb_key, thumbnail,  "image/jpeg")
        else:
            cdn_url       = self._local_save(main_key,  compressed)
            thumbnail_url = self._local_save(thumb_key, thumbnail)

        return {
            "s3_key":          main_key,
            "s3_bucket":       self._bucket,
            "cdn_url":         cdn_url,
            "thumbnail_url":   thumbnail_url,
            "image_hash":      image_hash,
            "file_size_bytes": len(compressed),
            "width_px":        width,
            "height_px":       height,
            "mime_type":       "image/jpeg",
            "original_filename": original_filename,
            # Sidecar payload merged into ComplaintImage.bounding_boxes by the
            # caller until AI analysis overwrites it with real detection boxes.
            # Carrying the pHash here lets the duplicate detector reuse it
            # without recomputing on every comparison.
            "_phash": phash,
        }

    async def presigned_urls_batch(
        self, s3_keys: list[str], expiry: int = 3600
    ) -> dict[str, str]:
        """Generate presigned URLs for multiple keys in one call (avoids N sequential round-trips)."""
        if not s3_keys:
            return {}
        if not self._use_s3:
            return {k: f"/local/{k}" for k in s3_keys}

        import asyncio
        loop = asyncio.get_event_loop()

        async def _one(key: str) -> tuple[str, str]:
            url = await loop.run_in_executor(
                None,
                lambda: self._get_client().generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=expiry,
                ),
            )
            return key, url

        results = await asyncio.gather(*[_one(k) for k in s3_keys])
        return dict(results)

    async def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        public: bool = False,
    ) -> str:
        """Generic upload — returns the CDN / local URL."""
        if self._use_s3:
            return await self._s3_upload(key, data, content_type, public=public)
        return self._local_save(key, data)

    async def presigned_url(self, s3_key: str, expiry: int = 3600) -> str:
        """
        Generate a download URL for `s3_key`. Routes through CloudFront
        (CDN edge caching, bucket hostname hidden from clients) when
        CLOUDFRONT_DOMAIN/CLOUDFRONT_KEY_PAIR_ID/CLOUDFRONT_PRIVATE_KEY are
        configured; otherwise falls back to a direct S3 presigned URL,
        identical to this method's original behaviour.
        """
        if not self._use_s3:
            return f"/local/{s3_key}"

        import asyncio

        @with_s3_retry(context=f"Presigned URL for '{s3_key}'")
        def _presign() -> str:
            return self._get_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": s3_key},
                ExpiresIn=expiry,
            )

        loop = asyncio.get_event_loop()
        s3_url = await loop.run_in_executor(None, _presign)

        from app.storage.cloudfront_signer import generate_signed_url_with_fallback

        return generate_signed_url_with_fallback(s3_key, s3_url, expiry)

    async def delete_object(self, s3_key: str) -> None:
        """Delete a single object from S3 / local storage."""
        if self._use_s3:
            import asyncio

            loop = asyncio.get_event_loop()

            def _delete():
                try:
                    self._get_client().delete_object(Bucket=self._bucket, Key=s3_key)
                except Exception as exc:
                    # A delete on an already-missing object is fine — S3's
                    # delete_object is idempotent and returns 204 even for
                    # a key that doesn't exist, so anything raised here is
                    # a genuine infrastructure problem worth surfacing.
                    raise translate_s3_error(exc, context=f"Delete of '{s3_key}'") from exc

            await loop.run_in_executor(None, _delete)
        else:
            path = _LOCAL_DIR / s3_key
            if path.exists():
                path.unlink()

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _s3_upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        public: bool = False,
    ) -> str:
        import asyncio

        extra: dict = {"ContentType": content_type}
        if public:
            extra["ACL"] = "public-read"

        @with_s3_retry(context=f"Upload of '{key}'")
        def _put():
            self._get_client().put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                **extra,
            )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _put)
        if self._cdn:
            return f"{self._cdn}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

    def _local_save(self, key: str, data: bytes) -> str:
        path = _LOCAL_DIR / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"/local/{key}"

    @staticmethod
    def compute_hash(data: bytes) -> str:
        return _sha256(data)


def _ext_from_content_type(ct: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png":  "png",
        "image/webp": "webp",
        "image/heic": "jpg",
    }.get(ct, "jpg")
