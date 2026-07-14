"""
Tests for app.core.secrets_validator.

Uses a lightweight stand-in object rather than the real Settings class so
these tests don't require a full Pydantic Settings construction — they
exercise the validator's actual decision logic in isolation.

Run:
    pytest tests/test_secrets_validator.py -v
"""

from __future__ import annotations

import secrets as _secrets

import pytest

from app.core import secrets_validator as sv


class _FakeSettings:
    """Mimics the subset of Settings attributes the validator reads."""

    def __init__(self, **overrides):
        defaults = dict(
            APP_ENV="development",
            SECRET_KEY="replace_with_a_long_random_string",
            JWT_SECRET_KEY="replace_with_a_separate_long_random_string",
            DATABASE_URL="postgresql+asyncpg://civic:civic@postgres:5432/civic_platform",
            REDIS_URL="redis://:changeme@redis:6379/0",
            ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173"],
            DOCS_ENABLED=True,
            AWS_ACCESS_KEY_ID="",
            SENTRY_DSN="",
            SMTP_USER="",
        )
        defaults.update(overrides)
        for key, value in defaults.items():
            setattr(self, key, value)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


def _secure_production_settings(**overrides) -> _FakeSettings:
    base = dict(
        APP_ENV="production",
        SECRET_KEY=_secrets.token_urlsafe(64),
        JWT_SECRET_KEY=_secrets.token_urlsafe(64),
        DATABASE_URL=f"postgresql+asyncpg://produser:{_secrets.token_urlsafe(20)}@db.internal:5432/civic",
        REDIS_URL=f"redis://:{_secrets.token_urlsafe(20)}@redis.internal:6379/0",
        ALLOWED_ORIGINS=["https://smartcivic.gov.in"],
        DOCS_ENABLED=False,
        AWS_ACCESS_KEY_ID="AKIAEXAMPLE",
        SENTRY_DSN="https://example@sentry.io/1",
        SMTP_USER="noreply@smartcivic.gov.in",
    )
    base.update(overrides)
    return _FakeSettings(**base)


class TestPlaceholderDetection:

    @pytest.mark.parametrize("value", [
        "changeme", "civic", "admin", "password", "secret",
        "civic_test", "civic123", "civic-dev", "", None,
    ])
    def test_known_placeholders_detected(self, value):
        assert sv._looks_like_placeholder(value or "") is True

    def test_real_random_value_not_flagged(self):
        real = _secrets.token_urlsafe(32)
        assert sv._looks_like_placeholder(real) is False


class TestEntropyCheck:

    def test_short_value_insufficient(self):
        assert sv._has_sufficient_entropy("short") is False

    def test_long_value_sufficient(self):
        assert sv._has_sufficient_entropy(_secrets.token_urlsafe(64)) is True


class TestProductionDefaults:
    """The exact defaults shipped in backend/.env.example must be caught."""

    def test_shipped_defaults_are_fatal_in_production(self):
        s = _FakeSettings(APP_ENV="production")
        report = sv.validate_settings(s)
        assert report.is_safe_to_start is False
        flagged_fields = {i.field for i in report.fatal_issues}
        assert "SECRET_KEY" in flagged_fields
        assert "JWT_SECRET_KEY" in flagged_fields
        assert "DATABASE_URL" in flagged_fields
        assert "REDIS_URL" in flagged_fields

    def test_same_defaults_downgrade_to_warnings_in_development(self):
        s = _FakeSettings(APP_ENV="development")
        report = sv.validate_settings(s)
        assert report.is_safe_to_start is True
        assert len(report.fatal_issues) == 0
        assert len(report.warnings) > 0

    def test_validate_or_raise_blocks_production_startup(self):
        s = _FakeSettings(APP_ENV="production")
        with pytest.raises(RuntimeError, match="Refusing to start"):
            sv.validate_or_raise(s)

    def test_validate_or_raise_allows_development_startup(self):
        s = _FakeSettings(APP_ENV="development")
        sv.validate_or_raise(s)   # should not raise


class TestSecureProductionConfig:

    def test_well_configured_production_passes_with_no_issues(self):
        s = _secure_production_settings()
        report = sv.validate_settings(s)
        assert report.is_safe_to_start is True
        assert len(report.issues) == 0

    def test_validate_or_raise_does_not_raise_for_secure_config(self):
        s = _secure_production_settings()
        sv.validate_or_raise(s)   # should not raise


class TestDuplicateSecretKeys:

    def test_reusing_secret_key_as_jwt_key_is_fatal(self):
        shared = _secrets.token_urlsafe(64)
        s = _secure_production_settings(SECRET_KEY=shared, JWT_SECRET_KEY=shared)
        report = sv.validate_settings(s)
        fields = {i.field for i in report.fatal_issues}
        assert "SECRET_KEY/JWT_SECRET_KEY" in fields

    def test_distinct_keys_pass(self):
        s = _secure_production_settings()
        report = sv.validate_settings(s)
        fields = {i.field for i in report.issues}
        assert "SECRET_KEY/JWT_SECRET_KEY" not in fields


class TestCorsValidation:

    def test_localhost_origin_fatal_in_production(self):
        s = _secure_production_settings(ALLOWED_ORIGINS=["http://localhost:3000"])
        report = sv.validate_settings(s)
        assert any(i.field == "ALLOWED_ORIGINS" for i in report.fatal_issues)

    def test_wildcard_origin_fatal_in_production(self):
        s = _secure_production_settings(ALLOWED_ORIGINS=["*"])
        report = sv.validate_settings(s)
        assert any(i.field == "ALLOWED_ORIGINS" for i in report.fatal_issues)

    def test_real_domain_passes(self):
        s = _secure_production_settings(ALLOWED_ORIGINS=["https://smartcivic.gov.in"])
        report = sv.validate_settings(s)
        assert not any(i.field == "ALLOWED_ORIGINS" for i in report.issues)


class TestExternalIntegrationWarnings:
    """These are warnings, not fatals — production should start, just be nagged."""

    def test_missing_aws_credentials_is_warning_not_fatal(self):
        s = _secure_production_settings(AWS_ACCESS_KEY_ID="")
        report = sv.validate_settings(s)
        assert report.is_safe_to_start is True
        assert any(i.field == "AWS_ACCESS_KEY_ID" and i.severity == "warning" for i in report.issues)

    def test_missing_sentry_dsn_is_warning(self):
        s = _secure_production_settings(SENTRY_DSN="")
        report = sv.validate_settings(s)
        assert any(i.field == "SENTRY_DSN" and i.severity == "warning" for i in report.issues)

    def test_missing_smtp_is_warning(self):
        s = _secure_production_settings(SMTP_USER="")
        report = sv.validate_settings(s)
        assert any(i.field == "SMTP_USER" and i.severity == "warning" for i in report.issues)


class TestDocsExposure:

    def test_docs_enabled_in_production_is_warning(self):
        s = _secure_production_settings(DOCS_ENABLED=True)
        report = sv.validate_settings(s)
        assert any(i.field == "DOCS_ENABLED" for i in report.issues)
        assert report.is_safe_to_start is True   # warning, not fatal

    def test_docs_disabled_in_production_no_issue(self):
        s = _secure_production_settings(DOCS_ENABLED=False)
        report = sv.validate_settings(s)
        assert not any(i.field == "DOCS_ENABLED" for i in report.issues)
