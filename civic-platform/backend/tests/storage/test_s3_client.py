"""
Tests for app.storage.s3_client — the boto3 client/resource factory.

These mock boto3 itself rather than hitting real AWS, since the point of
this test file is verifying *our* wiring (singleton caching, config values
passed through, thread-safety of lazy init) — not boto3's own correctness.

Run:
    pytest tests/storage/test_s3_client.py -v
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from app.storage import s3_client


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Every test starts from a clean slate — the module-level _client
    singleton must not leak between tests."""
    s3_client.reset_client()
    yield
    s3_client.reset_client()


class TestIsS3Configured:

    def test_true_when_both_credentials_present(self):
        with patch.object(s3_client.settings, "AWS_ACCESS_KEY_ID", "AKIAEXAMPLE"), \
             patch.object(s3_client.settings, "AWS_SECRET_ACCESS_KEY", "secretvalue"):
            assert s3_client.is_s3_configured() is True

    def test_false_when_access_key_missing(self):
        with patch.object(s3_client.settings, "AWS_ACCESS_KEY_ID", ""), \
             patch.object(s3_client.settings, "AWS_SECRET_ACCESS_KEY", "secretvalue"):
            assert s3_client.is_s3_configured() is False

    def test_false_when_secret_key_missing(self):
        with patch.object(s3_client.settings, "AWS_ACCESS_KEY_ID", "AKIAEXAMPLE"), \
             patch.object(s3_client.settings, "AWS_SECRET_ACCESS_KEY", ""):
            assert s3_client.is_s3_configured() is False

    def test_false_when_both_missing(self):
        with patch.object(s3_client.settings, "AWS_ACCESS_KEY_ID", ""), \
             patch.object(s3_client.settings, "AWS_SECRET_ACCESS_KEY", ""):
            assert s3_client.is_s3_configured() is False


class TestGetS3Client:

    def test_returns_a_client(self):
        with patch("boto3.client") as mock_boto_client:
            mock_boto_client.return_value = MagicMock(name="s3-client")
            result = s3_client.get_s3_client()
            assert result is mock_boto_client.return_value

    def test_singleton_returns_same_instance_on_repeated_calls(self):
        with patch("boto3.client") as mock_boto_client:
            mock_boto_client.return_value = MagicMock(name="s3-client")
            first = s3_client.get_s3_client()
            second = s3_client.get_s3_client()
            assert first is second
            # boto3.client should only have been called ONCE despite two
            # get_s3_client() calls — this is the entire point of the
            # singleton pattern this module implements.
            mock_boto_client.assert_called_once()

    def test_passes_region_and_credentials_from_settings(self):
        with patch("boto3.client") as mock_boto_client, \
             patch.object(s3_client.settings, "AWS_REGION", "ap-south-1"), \
             patch.object(s3_client.settings, "AWS_ACCESS_KEY_ID", "AKIATEST"), \
             patch.object(s3_client.settings, "AWS_SECRET_ACCESS_KEY", "secrettest"):
            s3_client.get_s3_client()
            _, kwargs = mock_boto_client.call_args
            assert kwargs["aws_access_key_id"] == "AKIATEST"
            assert kwargs["aws_secret_access_key"] == "secrettest"

    def test_configures_adaptive_retry_mode(self):
        """The whole point of this module existing instead of an inline
        boto3.client() call — verify the retry/timeout config is actually
        being passed, not just that *some* client comes back."""
        with patch("boto3.client") as mock_boto_client:
            s3_client.get_s3_client()
            _, kwargs = mock_boto_client.call_args
            boto_config = kwargs["config"]
            assert boto_config.retries["mode"] == "adaptive"
            assert boto_config.retries["max_attempts"] == 4

    def test_configures_connect_and_read_timeouts(self):
        with patch("boto3.client") as mock_boto_client:
            s3_client.get_s3_client()
            _, kwargs = mock_boto_client.call_args
            boto_config = kwargs["config"]
            assert boto_config.connect_timeout == 5
            assert boto_config.read_timeout == 20

    def test_thread_safe_concurrent_initialisation_only_constructs_once(self):
        """Simulate two threads racing to initialise the singleton —
        boto3.client() should still only be called once."""
        call_count = {"n": 0}
        construction_started = threading.Event()
        release_construction = threading.Event()

        def slow_boto_client(*args, **kwargs):
            call_count["n"] += 1
            construction_started.set()
            release_construction.wait(timeout=2)
            return MagicMock(name=f"client-{call_count['n']}")

        with patch("boto3.client", side_effect=slow_boto_client):
            results = []

            def worker():
                results.append(s3_client.get_s3_client())

            t1 = threading.Thread(target=worker)
            t1.start()
            construction_started.wait(timeout=2)

            # t2 starts while t1 is still "inside" boto3.client() —
            # it must block on the lock rather than also constructing.
            t2 = threading.Thread(target=worker)
            t2.start()

            release_construction.set()
            t1.join(timeout=2)
            t2.join(timeout=2)

            assert call_count["n"] == 1
            assert results[0] is results[1]


class TestGetS3Resource:

    def test_returns_a_resource_each_call(self):
        """Unlike get_s3_client(), the resource factory is NOT cached as a
        singleton — verify it constructs fresh each time via boto3.resource."""
        with patch("boto3.resource") as mock_boto_resource:
            mock_boto_resource.return_value = MagicMock(name="s3-resource")
            result = s3_client.get_s3_resource()
            assert result is mock_boto_resource.return_value
            mock_boto_resource.assert_called_once_with(
                "s3",
                aws_access_key_id=s3_client.settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=s3_client.settings.AWS_SECRET_ACCESS_KEY,
                region_name=s3_client.settings.AWS_REGION,
            )


class TestResetClient:

    def test_reset_forces_reconstruction(self):
        with patch("boto3.client") as mock_boto_client:
            mock_boto_client.side_effect = [
                MagicMock(name="first"), MagicMock(name="second"),
            ]
            first = s3_client.get_s3_client()
            s3_client.reset_client()
            second = s3_client.get_s3_client()

            assert first is not second
            assert mock_boto_client.call_count == 2
