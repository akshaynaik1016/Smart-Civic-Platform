"""
Tests for app.storage.multipart — large-file upload/download via boto3
TransferConfig.

Mocks the boto3 client itself (upload_fileobj/download_fileobj) since the
point of this test file is verifying our TransferConfig wiring, error
translation, and async-via-executor pattern — not boto3's own multipart
correctness, which is boto3's problem to test.

Run:
    pytest tests/storage/test_multipart.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.storage import multipart
from app.storage.s3_errors import StorageError


@pytest.fixture
def mock_s3_client():
    client = MagicMock()
    with patch("app.storage.multipart.get_s3_client", return_value=client):
        yield client


class TestBuildTransferConfig:

    def test_returns_a_transfer_config_with_expected_threshold(self):
        config = multipart._build_transfer_config()
        assert config.multipart_threshold == multipart._MULTIPART_THRESHOLD_BYTES
        assert config.multipart_chunksize == multipart._MULTIPART_THRESHOLD_BYTES

    def test_uses_threads_and_limits_concurrency(self):
        config = multipart._build_transfer_config()
        assert config.use_threads is True
        assert config.max_concurrency == 4


class TestUploadLargeFile:

    @pytest.mark.asyncio
    async def test_uploads_small_file_below_threshold(self, mock_s3_client):
        small_data = b"x" * 1024   # 1KB — well below the 8MB threshold
        url = await multipart.upload_large_file("reports/small.pdf", small_data)

        mock_s3_client.upload_fileobj.assert_called_once()
        _, kwargs = mock_s3_client.upload_fileobj.call_args
        assert url is not None

    @pytest.mark.asyncio
    async def test_passes_bucket_and_key_correctly(self, mock_s3_client):
        with patch.object(multipart.settings, "AWS_S3_BUCKET", "civic-test-bucket"):
            await multipart.upload_large_file("reports/q2-summary.pdf", b"data")
            args, _ = mock_s3_client.upload_fileobj.call_args
            # upload_fileobj(fileobj, bucket, key, ...)
            assert args[1] == "civic-test-bucket"
            assert args[2] == "reports/q2-summary.pdf"

    @pytest.mark.asyncio
    async def test_passes_content_type_in_extra_args(self, mock_s3_client):
        await multipart.upload_large_file(
            "reports/export.csv", b"a,b,c\n1,2,3", content_type="text/csv",
        )
        _, kwargs = mock_s3_client.upload_fileobj.call_args
        assert kwargs["ExtraArgs"]["ContentType"] == "text/csv"

    @pytest.mark.asyncio
    async def test_passes_metadata_when_provided(self, mock_s3_client):
        await multipart.upload_large_file(
            "reports/export.csv", b"data",
            metadata={"generated-by": "officer-123"},
        )
        _, kwargs = mock_s3_client.upload_fileobj.call_args
        assert kwargs["ExtraArgs"]["Metadata"] == {"generated-by": "officer-123"}

    @pytest.mark.asyncio
    async def test_omits_metadata_key_when_not_provided(self, mock_s3_client):
        await multipart.upload_large_file("reports/export.csv", b"data")
        _, kwargs = mock_s3_client.upload_fileobj.call_args
        assert "Metadata" not in kwargs["ExtraArgs"]

    @pytest.mark.asyncio
    async def test_passes_progress_callback_through(self, mock_s3_client):
        callback = MagicMock()
        await multipart.upload_large_file("reports/big.pdf", b"data", progress_callback=callback)
        _, kwargs = mock_s3_client.upload_fileobj.call_args
        assert kwargs["Callback"] is callback

    @pytest.mark.asyncio
    async def test_returns_cdn_url_when_configured(self, mock_s3_client):
        with patch.object(multipart.settings, "AWS_S3_CDN_URL", "https://cdn.smartcivic.gov.in"):
            url = await multipart.upload_large_file("reports/q2.pdf", b"data")
            assert url == "https://cdn.smartcivic.gov.in/reports/q2.pdf"

    @pytest.mark.asyncio
    async def test_returns_direct_s3_url_when_no_cdn_configured(self, mock_s3_client):
        with patch.object(multipart.settings, "AWS_S3_CDN_URL", ""), \
             patch.object(multipart.settings, "AWS_S3_BUCKET", "civic-bucket"), \
             patch.object(multipart.settings, "AWS_REGION", "ap-south-1"):
            url = await multipart.upload_large_file("reports/q2.pdf", b"data")
            assert url == "https://civic-bucket.s3.ap-south-1.amazonaws.com/reports/q2.pdf"

    @pytest.mark.asyncio
    async def test_translates_boto3_errors_via_s3_errors_module(self, mock_s3_client):
        class FakeClientError(Exception):
            def __init__(self):
                self.response = {"Error": {"Code": "EntityTooLarge"}}

        mock_s3_client.upload_fileobj.side_effect = FakeClientError()

        with pytest.raises(Exception) as exc_info:
            await multipart.upload_large_file("reports/huge.pdf", b"data")

        # Should have gone through translate_s3_error, not propagated the
        # raw FakeClientError straight through.
        assert not isinstance(exc_info.value, FakeClientError)

    @pytest.mark.asyncio
    async def test_unmapped_error_becomes_storage_error(self, mock_s3_client):
        mock_s3_client.upload_fileobj.side_effect = ConnectionError("network partition")

        with pytest.raises(StorageError):
            await multipart.upload_large_file("reports/x.pdf", b"data")


class TestDownloadLargeFile:

    @pytest.mark.asyncio
    async def test_downloads_and_returns_bytes(self, mock_s3_client):
        expected_content = b"the full file contents"

        def fake_download(bucket, key, buf):
            buf.write(expected_content)

        mock_s3_client.download_fileobj.side_effect = fake_download

        result = await multipart.download_large_file("complaints/abc/photo.jpg")
        assert result == expected_content

    @pytest.mark.asyncio
    async def test_passes_correct_bucket_and_key(self, mock_s3_client):
        with patch.object(multipart.settings, "AWS_S3_BUCKET", "civic-test-bucket"):
            mock_s3_client.download_fileobj.side_effect = lambda b, k, buf: buf.write(b"x")
            await multipart.download_large_file("complaints/xyz/photo.jpg")
            args, _ = mock_s3_client.download_fileobj.call_args
            assert args[0] == "civic-test-bucket"
            assert args[1] == "complaints/xyz/photo.jpg"

    @pytest.mark.asyncio
    async def test_translates_not_found_errors(self, mock_s3_client):
        class FakeClientError(Exception):
            def __init__(self):
                self.response = {"Error": {"Code": "NoSuchKey"}}

        mock_s3_client.download_fileobj.side_effect = FakeClientError()

        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await multipart.download_large_file("complaints/missing/photo.jpg")

    @pytest.mark.asyncio
    async def test_empty_file_downloads_as_empty_bytes(self, mock_s3_client):
        mock_s3_client.download_fileobj.side_effect = lambda b, k, buf: None
        result = await multipart.download_large_file("empty-object.txt")
        assert result == b""
