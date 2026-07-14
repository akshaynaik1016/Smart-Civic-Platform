"""
Tests for app.storage.s3_errors — error code translation and retry behaviour.

These tests construct fake botocore-shaped exceptions (an object with a
`.response = {"Error": {"Code": ...}}` attribute, which is exactly what
botocore.exceptions.ClientError exposes) rather than depending on boto3
actually being importable or making real AWS calls.

Run:
    pytest tests/storage/test_s3_errors.py -v
"""

from __future__ import annotations

import pytest

from app.core.exceptions import BadRequestError, NotFoundError
from app.storage.s3_errors import (
    StorageError,
    _extract_error_code,
    translate_s3_error,
    with_s3_retry,
)


class _FakeClientError(Exception):
    """Mimics botocore.exceptions.ClientError's response shape."""

    def __init__(self, code: str):
        self.response = {"Error": {"Code": code}}
        super().__init__(f"fake AWS error: {code}")


class _FakeUnshapedError(Exception):
    """Mimics errors with no .response attribute at all
    (e.g. NoCredentialsError, EndpointConnectionError)."""


class TestErrorCodeExtraction:

    def test_extracts_code_from_client_error_shape(self):
        exc = _FakeClientError("NoSuchKey")
        assert _extract_error_code(exc) == "NoSuchKey"

    def test_returns_none_for_unshaped_error(self):
        exc = _FakeUnshapedError("connection refused")
        assert _extract_error_code(exc) is None

    def test_returns_none_when_response_is_not_a_dict(self):
        exc = Exception("plain exception")
        assert _extract_error_code(exc) is None


class TestErrorTranslation:

    @pytest.mark.parametrize("code", ["NoSuchKey", "NoSuchBucket", "404"])
    def test_not_found_codes_map_to_not_found_error(self, code):
        result = translate_s3_error(_FakeClientError(code), context="Get object")
        assert isinstance(result, NotFoundError)

    @pytest.mark.parametrize("code", [
        "InvalidArgument", "EntityTooLarge", "KeyTooLongError", "InvalidObjectState",
    ])
    def test_bad_request_codes_map_to_bad_request_error(self, code):
        result = translate_s3_error(_FakeClientError(code), context="Upload")
        assert isinstance(result, BadRequestError)

    def test_unmapped_code_becomes_storage_error(self):
        result = translate_s3_error(_FakeClientError("AccessDenied"), context="Upload")
        assert isinstance(result, StorageError)
        assert result.original_code == "AccessDenied"

    def test_unshaped_error_becomes_storage_error(self):
        result = translate_s3_error(_FakeUnshapedError("network down"), context="Upload")
        assert isinstance(result, StorageError)
        assert result.original_code is None

    def test_context_is_included_in_storage_error_message(self):
        result = translate_s3_error(_FakeClientError("AccessDenied"), context="Avatar upload")
        assert "Avatar upload" in result.message


class TestRetryDecorator:

    def test_succeeds_on_first_attempt_with_no_error(self):
        calls = []

        @with_s3_retry(max_attempts=3, base_delay_seconds=0.001, context="op")
        def func():
            calls.append(1)
            return "ok"

        assert func() == "ok"
        assert len(calls) == 1

    def test_retries_on_slowdown_then_succeeds(self):
        calls = []

        @with_s3_retry(max_attempts=3, base_delay_seconds=0.001, context="op")
        def func():
            calls.append(1)
            if len(calls) < 3:
                raise _FakeClientError("SlowDown")
            return "ok"

        assert func() == "ok"
        assert len(calls) == 3

    def test_does_not_retry_non_retryable_codes(self):
        calls = []

        @with_s3_retry(max_attempts=5, base_delay_seconds=0.001, context="op")
        def func():
            calls.append(1)
            raise _FakeClientError("AccessDenied")

        with pytest.raises(StorageError):
            func()
        assert len(calls) == 1   # no retries attempted

    def test_exhausts_attempts_then_raises_translated_error(self):
        calls = []

        @with_s3_retry(max_attempts=2, base_delay_seconds=0.001, context="op")
        def func():
            calls.append(1)
            raise _FakeClientError("SlowDown")

        with pytest.raises(StorageError):
            func()
        assert len(calls) == 2   # exactly max_attempts, no more

    @pytest.mark.parametrize("code", [
        "RequestTimeout", "RequestTimeTooSkewed", "InternalError",
        "ServiceUnavailable", "Throttling", "ThrottlingException",
    ])
    def test_all_documented_retryable_codes_actually_retry(self, code):
        calls = []

        @with_s3_retry(max_attempts=2, base_delay_seconds=0.001, context="op")
        def func():
            calls.append(1)
            if len(calls) < 2:
                raise _FakeClientError(code)
            return "recovered"

        assert func() == "recovered"
        assert len(calls) == 2

    def test_preserves_function_metadata(self):
        @with_s3_retry(context="op")
        def my_function():
            """My docstring."""
            return None

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_passes_through_args_and_kwargs(self):
        @with_s3_retry(context="op")
        def func(a, b, c=None):
            return (a, b, c)

        assert func(1, 2, c=3) == (1, 2, 3)
