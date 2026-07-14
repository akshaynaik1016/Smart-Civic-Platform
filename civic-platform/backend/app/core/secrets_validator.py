"""
Secrets validation
====================
Runs once at application startup (called from app.main's lifespan) to catch
the single most common production incident class: the app boots fine
because every Pydantic field has a default, but those defaults are
development placeholders — a shared SECRET_KEY, an empty SMTP password,
"changeme" as the Redis password — and nobody notices until something goes
wrong in a way that's actually exploitable.

Philosophy: in development, warn and continue (so `make dev` works out of
the box with zero configuration). In production, the same conditions are
fatal — the process refuses to start rather than serve traffic with weak
secrets.

This does NOT replace a real secrets manager — see
backend/app/core/secrets_provider.py for fetching actual secret *values*
from AWS Secrets Manager. This module validates whatever values end up in
`settings`, regardless of where they came from.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only needed for type hints — avoids forcing every caller of this
    # module to have pydantic/pydantic-settings importable, which matters
    # for lightweight tooling/test contexts that want to validate a plain
    # settings-like object without pulling in the full app config chain.
    from app.core.config import Settings

logger = logging.getLogger(__name__)


# ─── Known-insecure default values that must never reach production ─────────

_KNOWN_PLACEHOLDER_VALUES = {
    "changeme",
    "change_this_in_production",
    "replace_with_a_long_random_string",
    "replace_with_a_separate_long_random_string",
    "civic",          # the default POSTGRES_PASSWORD in docker-compose.yml
    "admin",
    "password",
    "secret",
}

_MIN_SECRET_LENGTH = 32   # bytes of entropy we expect from token_urlsafe(64)-style keys


@dataclass
class ValidationIssue:
    field: str
    severity: str          # "fatal" | "warning"
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def fatal_issues(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "fatal"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_safe_to_start(self) -> bool:
        return len(self.fatal_issues) == 0


def _looks_like_placeholder(value: str) -> bool:
    if not value:
        return True
    if value.lower() in _KNOWN_PLACEHOLDER_VALUES:
        return True
    # Catches "civic_test", "civic123", etc. — anything that's just the
    # word "civic" with trivial decoration, which is what every example
    # file in this repo uses.
    if re.fullmatch(r"civic[_\-]?(test|dev|local)?[0-9]*", value.lower()):
        return True
    return False


def _has_sufficient_entropy(value: str) -> bool:
    return len(value) >= _MIN_SECRET_LENGTH


# ─── Per-environment rule sets ────────────────────────────────────────────────
# Severity in development is always capped at "warning" regardless of what's
# listed here — see validate_settings() below.

def _check_secret_keys(settings: Settings, report: ValidationReport) -> None:
    for field_name in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = getattr(settings, field_name)
        if _looks_like_placeholder(value):
            report.issues.append(ValidationIssue(
                field=field_name, severity="fatal",
                message=f"{field_name} is a placeholder/default value. "
                        f"Generate a real one: python -c \"import secrets; print(secrets.token_urlsafe(64))\"",
            ))
        elif not _has_sufficient_entropy(value):
            report.issues.append(ValidationIssue(
                field=field_name, severity="fatal",
                message=f"{field_name} is shorter than {_MIN_SECRET_LENGTH} characters — "
                        "insufficient entropy for production use.",
            ))

    if settings.SECRET_KEY == settings.JWT_SECRET_KEY:
        report.issues.append(ValidationIssue(
            field="SECRET_KEY/JWT_SECRET_KEY", severity="fatal",
            message="SECRET_KEY and JWT_SECRET_KEY must be distinct values — "
                    "reusing one secret for two purposes doubles the blast radius of a leak.",
        ))


def _check_database_and_redis(settings: Settings, report: ValidationReport) -> None:
    if "civic:civic@" in settings.DATABASE_URL or ":civic@" in settings.DATABASE_URL:
        report.issues.append(ValidationIssue(
            field="DATABASE_URL", severity="fatal",
            message="DATABASE_URL still contains the default 'civic/civic' credentials.",
        ))

    if "localhost" in settings.DATABASE_URL and settings.is_production:
        report.issues.append(ValidationIssue(
            field="DATABASE_URL", severity="warning",
            message="DATABASE_URL points to localhost in a production environment — "
                    "confirm this isn't accidentally bypassing the managed DB.",
        ))

    if ":changeme@" in settings.REDIS_URL or settings.REDIS_URL.startswith("redis://localhost") and not "@" in settings.REDIS_URL:
        report.issues.append(ValidationIssue(
            field="REDIS_URL", severity="fatal" if settings.is_production else "warning",
            message="REDIS_URL has no password (or uses the 'changeme' default) — "
                    "Redis holds JWT blacklists, OTPs, and rate-limit counters; an "
                    "unauthenticated instance is a real exposure.",
        ))


def _check_cors(settings: Settings, report: ValidationReport) -> None:
    if settings.is_production:
        for origin in settings.ALLOWED_ORIGINS:
            if origin in ("*", "http://localhost:3000", "http://localhost:5173"):
                report.issues.append(ValidationIssue(
                    field="ALLOWED_ORIGINS", severity="fatal",
                    message=f"ALLOWED_ORIGINS contains '{origin}' in production. "
                            "Restrict to the actual dashboard/mobile origins.",
                ))


def _check_docs_exposure(settings: Settings, report: ValidationReport) -> None:
    if settings.is_production and settings.DOCS_ENABLED:
        report.issues.append(ValidationIssue(
            field="DOCS_ENABLED", severity="warning",
            message="Swagger/ReDoc are enabled in production — exposes the full API "
                    "schema publicly. Set DOCS_ENABLED=false unless intentionally public.",
        ))


def _check_external_integrations(settings: Settings, report: ValidationReport) -> None:
    if settings.is_production:
        if not settings.AWS_ACCESS_KEY_ID:
            report.issues.append(ValidationIssue(
                field="AWS_ACCESS_KEY_ID", severity="warning",
                message="No AWS credentials configured in production — StorageService "
                        "will fall back to local-filesystem storage, which does not "
                        "survive container restarts.",
            ))
        if not settings.SENTRY_DSN:
            report.issues.append(ValidationIssue(
                field="SENTRY_DSN", severity="warning",
                message="No Sentry DSN configured in production — unhandled exceptions "
                        "will only be visible in container logs.",
            ))
        if not settings.SMTP_USER:
            report.issues.append(ValidationIssue(
                field="SMTP_USER", severity="warning",
                message="No SMTP credentials configured — OTP/status emails will be "
                        "logged instead of sent. Citizens will not be able to verify "
                        "their accounts via email.",
            ))


# ─── Public entry point ────────────────────────────────────────────────────────

def validate_settings(settings: Settings) -> ValidationReport:
    """
    Run every check. Severities are as defined above EXCEPT that outside of
    production, every "fatal" is downgraded to "warning" — development and
    staging-without-real-data should never be blocked from starting, only
    nagged in the logs.
    """
    report = ValidationReport()

    _check_secret_keys(settings, report)
    _check_database_and_redis(settings, report)
    _check_cors(settings, report)
    _check_docs_exposure(settings, report)
    _check_external_integrations(settings, report)

    if not settings.is_production:
        for issue in report.issues:
            issue.severity = "warning"

    return report


def validate_or_raise(settings: Settings) -> None:
    """
    Call this from the FastAPI lifespan on startup. Logs every issue found;
    raises RuntimeError (preventing the app from starting) if any are fatal.
    """
    report = validate_settings(settings)

    for issue in report.warnings:
        logger.warning("[config] %s: %s", issue.field, issue.message)

    for issue in report.fatal_issues:
        logger.error("[config] FATAL — %s: %s", issue.field, issue.message)

    if not report.is_safe_to_start:
        names = ", ".join(i.field for i in report.fatal_issues)
        raise RuntimeError(
            f"Refusing to start in {settings.APP_ENV} with insecure configuration "
            f"({len(report.fatal_issues)} fatal issue(s): {names}). "
            f"See the error log above for remediation steps."
        )

    if report.warnings:
        logger.info(
            "[config] Startup validation passed with %d warning(s) — see above.",
            len(report.warnings),
        )
    else:
        logger.info("[config] Startup validation passed with no issues.")
