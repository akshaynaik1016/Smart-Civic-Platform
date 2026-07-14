"""
Tests for app.storage.cloudfront_signer.

RSA signing itself is exercised with a real, throwaway test keypair
(generated at module import time) rather than mocked — verifying the
actual cryptography wiring (PEM loading, PKCS1v15+SHA1 signing) is the
entire point of this module, so mocking it out would test nothing.

Run:
    pytest tests/storage/test_cloudfront_signer.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.storage import cloudfront_signer


# ─── Throwaway RSA keypair for signing tests — never used for anything real ───

def _generate_test_keypair() -> tuple[str, str]:
    """Returns (private_key_pem, public_key_pem) for a fresh 2048-bit RSA key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


_TEST_PRIVATE_KEY_PEM, _TEST_PUBLIC_KEY_PEM = _generate_test_keypair()


@pytest.fixture
def configured_cloudfront():
    """Patch settings so is_cloudfront_configured() returns True with our
    throwaway test key."""
    with patch.object(cloudfront_signer.settings, "CLOUDFRONT_DOMAIN", "d123example.cloudfront.net"), \
         patch.object(cloudfront_signer.settings, "CLOUDFRONT_KEY_PAIR_ID", "APKAEXAMPLE123"), \
         patch.object(cloudfront_signer.settings, "CLOUDFRONT_PRIVATE_KEY", _TEST_PRIVATE_KEY_PEM):
        yield


@pytest.fixture
def unconfigured_cloudfront():
    with patch.object(cloudfront_signer.settings, "CLOUDFRONT_DOMAIN", ""), \
         patch.object(cloudfront_signer.settings, "CLOUDFRONT_KEY_PAIR_ID", ""), \
         patch.object(cloudfront_signer.settings, "CLOUDFRONT_PRIVATE_KEY", ""):
        yield


class TestIsCloudfrontConfigured:

    def test_true_when_all_three_fields_present(self, configured_cloudfront):
        assert cloudfront_signer.is_cloudfront_configured() is True

    def test_false_when_nothing_configured(self, unconfigured_cloudfront):
        assert cloudfront_signer.is_cloudfront_configured() is False

    def test_false_when_only_domain_set(self):
        with patch.object(cloudfront_signer.settings, "CLOUDFRONT_DOMAIN", "d123.cloudfront.net"), \
             patch.object(cloudfront_signer.settings, "CLOUDFRONT_KEY_PAIR_ID", ""), \
             patch.object(cloudfront_signer.settings, "CLOUDFRONT_PRIVATE_KEY", ""):
            assert cloudfront_signer.is_cloudfront_configured() is False

    def test_false_when_only_domain_and_key_pair_id_set(self):
        with patch.object(cloudfront_signer.settings, "CLOUDFRONT_DOMAIN", "d123.cloudfront.net"), \
             patch.object(cloudfront_signer.settings, "CLOUDFRONT_KEY_PAIR_ID", "APKA123"), \
             patch.object(cloudfront_signer.settings, "CLOUDFRONT_PRIVATE_KEY", ""):
            assert cloudfront_signer.is_cloudfront_configured() is False


class TestGenerateSignedUrl:

    def test_raises_when_not_configured(self, unconfigured_cloudfront):
        with pytest.raises(RuntimeError, match="not configured"):
            cloudfront_signer.generate_signed_url("complaints/abc/photo.jpg")

    def test_produces_a_url_pointing_at_cloudfront_domain(self, configured_cloudfront):
        url = cloudfront_signer.generate_signed_url("complaints/abc/photo.jpg")
        assert url.startswith("https://d123example.cloudfront.net/complaints/abc/photo.jpg")

    def test_signed_url_contains_expiry_and_signature_params(self, configured_cloudfront):
        url = cloudfront_signer.generate_signed_url("complaints/abc/photo.jpg", expiry_seconds=600)
        assert "Expires=" in url
        assert "Signature=" in url
        assert "Key-Pair-Id=APKAEXAMPLE123" in url

    def test_different_keys_yield_different_signatures(self, configured_cloudfront):
        url_a = cloudfront_signer.generate_signed_url("complaints/abc/photo.jpg")

        other_private_pem, _ = _generate_test_keypair()
        with patch.object(cloudfront_signer.settings, "CLOUDFRONT_PRIVATE_KEY", other_private_pem):
            url_b = cloudfront_signer.generate_signed_url("complaints/abc/photo.jpg")

        sig_a = url_a.split("Signature=")[1].split("&")[0]
        sig_b = url_b.split("Signature=")[1].split("&")[0]
        assert sig_a != sig_b

    def test_object_key_with_special_characters_is_included(self, configured_cloudfront):
        url = cloudfront_signer.generate_signed_url("resolutions/complaint-123/before & after.jpg")
        assert "resolutions/complaint-123/" in url


class TestGenerateSignedUrlWithFallback:

    def test_falls_back_when_not_configured(self, unconfigured_cloudfront):
        fallback = "https://my-bucket.s3.ap-south-1.amazonaws.com/key.jpg?presigned=1"
        result = cloudfront_signer.generate_signed_url_with_fallback(
            "complaints/abc/photo.jpg", fallback,
        )
        assert result == fallback

    def test_uses_cloudfront_when_configured_and_signing_succeeds(self, configured_cloudfront):
        fallback = "https://my-bucket.s3.ap-south-1.amazonaws.com/key.jpg?presigned=1"
        result = cloudfront_signer.generate_signed_url_with_fallback(
            "complaints/abc/photo.jpg", fallback,
        )
        assert result != fallback
        assert "d123example.cloudfront.net" in result

    def test_falls_back_on_signing_exception_rather_than_raising(self, configured_cloudfront):
        fallback = "https://my-bucket.s3.ap-south-1.amazonaws.com/key.jpg?presigned=1"
        with patch.object(
            cloudfront_signer, "generate_signed_url",
            side_effect=ValueError("corrupted key material"),
        ):
            result = cloudfront_signer.generate_signed_url_with_fallback(
                "complaints/abc/photo.jpg", fallback,
            )
        assert result == fallback

    def test_never_raises_even_with_malformed_private_key(self):
        with patch.object(cloudfront_signer.settings, "CLOUDFRONT_DOMAIN", "d123.cloudfront.net"), \
             patch.object(cloudfront_signer.settings, "CLOUDFRONT_KEY_PAIR_ID", "APKA123"), \
             patch.object(cloudfront_signer.settings, "CLOUDFRONT_PRIVATE_KEY", "not a real PEM at all"):
            fallback = "https://fallback.example.com/key.jpg"
            result = cloudfront_signer.generate_signed_url_with_fallback(
                "some/key.jpg", fallback,
            )
            assert result == fallback


class TestLoadPrivateKey:

    def test_loads_valid_pem_successfully(self, configured_cloudfront):
        key = cloudfront_signer._load_private_key()
        assert key is not None
        assert hasattr(key, "sign")

    def test_raises_on_malformed_pem(self):
        with patch.object(cloudfront_signer.settings, "CLOUDFRONT_PRIVATE_KEY", "garbage-not-pem"):
            with pytest.raises(Exception):
                cloudfront_signer._load_private_key()
