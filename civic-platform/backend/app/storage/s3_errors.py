"""
S3 error handling
====================
The single biggest gap in the original StorageService: every S3 call
(`put_object`, `get_object`, `delete_object`, presigned URL generation)
propagated boto3's raw `ClientError`/`EndpointConnectionError` straight up
to the caller. In practice that meant:

  • A throttled S3 request (503 SlowDown under burst load) became an
    unhandled 500 with a boto3 stack trace leaking into the API response,
    instead of a transient error worth retrying.
  • A genuinely missing bucket/object (e.g. an officer re-fetching an
    image whose underlying S3 object was deleted out-of-band) looked
    identical, in the logs, to a credentials misconfiguration.
  • Nothing distinguished "retry this" from "stop and tell the user."

This module gives every storage call a single retry policy and maps
boto3's error codes onto the app's existing exception hierarchy
(app.core.exceptions) so a controller/service calling StorageService
doesn't need to know boto3 exists at all.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Callable, TypeVar

from app.core.exceptions import (
    BadRequestError,
    InternalError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Error codes worth retrying — transient/throttling conditions where the
# same request will likely succeed seconds later.
_RETRYABLE_CODES = {
    "SlowDown",                  # S3 throttling under burst load
    "RequestTimeout",
    "RequestTimeTooSkewed",
    "InternalError",             # S3-side transient fault
    "ServiceUnavailable",
    "Throttling",
    "ThrottlingException",
}

# Error codes that mean "this object/bucket genuinely doesn't exist" —
# map to the app's NotFoundError rather than a generic 500.
_NOT_FOUND_CODES = {
    "NoSuchKey",
    "NoSuchBucket",
    "404",
}

# Error codes that mean the caller did something invalid (oversized object,
# malformed key, unsupported storage class) — map to BadRequestError.
_BAD_REQUEST_CODES = {
    "InvalidArgument",
    "EntityTooLarge",
    "KeyTooLongError",
    "InvalidObjectState",
}


class StorageError(InternalError):
    """Raised for S3 failures that aren't cleanly mappable to a 4xx —
    genuine infrastructure problems (bad credentials, region mismatch,
    network partition) that the caller can't fix by changing their request."""

    def __init__(self, message: str, original_code: str | None = None):
        super().__init__(message)
        self.original_code = original_code


def _extract_error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


def translate_s3_error(exc: Exception, *, context: str = "S3 operation") -> Exception:
    """
    Convert a boto3/botocore exception into the appropriate app exception.
    Called from within the retry wrapper once retries are exhausted, or
    directly by callers that need translation without retry (e.g. a
    single delete that shouldn't be retried if the object is just gone).
    """
    code = _extract_error_code(exc)

    if code in _NOT_FOUND_CODES:
        return NotFoundError("Storage object", code)

    if code in _BAD_REQUEST_CODES:
        return BadRequestError(f"{context} failed: {code}")

    # NoCredentialsError, EndpointConnectionError, and anything else
    # botocore can raise that doesn't carry a response.Error.Code —
    # these are infrastructure problems, not user-fixable input problems.
    logger.error("%s failed with unmapped error: %s (code=%s)", context, exc, code)
    return StorageError(
        f"{context} failed due to a storage infrastructure error. "
        "This has been logged for investigation.",
        original_code=code,
    )


def with_s3_retry(
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.5,
    context: str = "S3 operation",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for the synchronous boto3 call functions that run inside
    `loop.run_in_executor(...)`. Retries on throttling/transient errors
    with exponential backoff; immediately translates and raises on
    anything non-retryable (no point retrying a 403 or a malformed key).

    NOTE: the S3 client itself is also configured with botocore's adaptive
    retry mode (see app/storage/s3_client.py) — this decorator's retry is
    specifically for errors that survive botocore's own retry budget, or
    for operations (like our own composed multi-call flows) where we want
    a coarser, slightly different retry policy than botocore's per-request
    one.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 — intentionally broad, translated below
                    code = _extract_error_code(exc)
                    last_exc = exc

                    if code not in _RETRYABLE_CODES or attempt == max_attempts:
                        raise translate_s3_error(exc, context=context) from exc

                    delay = base_delay_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "%s attempt %d/%d failed with retryable code=%s — retrying in %.1fs",
                        context, attempt, max_attempts, code, delay,
                    )
                    time.sleep(delay)

            # Unreachable in practice (the loop always returns or raises),
            # but keeps type checkers happy and fails loudly if it ever is.
            raise translate_s3_error(last_exc, context=context)  # type: ignore[arg-type]

        return wrapper

    return decorator
