"""
Secrets provider — AWS Secrets Manager integration
=====================================================
In production, secrets should not live in a `.env` file sitting on a
server's disk — they should be fetched at startup from a managed secrets
store, where access is logged, rotation is possible without a redeploy,
and a compromised host doesn't mean a compromised secret-at-rest.

This module bridges that gap without requiring a rewrite of how Settings
is consumed everywhere else in the codebase:

  • Development / CI:  Settings loads from backend/.env as it always has —
                        AwsSecretsProvider is never invoked.
  • Staging/Production: if SECRETS_PROVIDER=aws_secrets_manager is set,
                        this module fetches a single JSON secret (containing
                        every sensitive field) and injects it into the
                        process environment *before* Settings() is
                        constructed, so Pydantic picks it up exactly as if
                        it had come from .env.

Design choice: one JSON secret per environment (e.g.
"civic-platform/production") rather than one secret per field. This keeps
IAM policy simple (one ARN to grant read access to) and keeps the AWS
console usable (you can see "what does production actually have configured"
in one place) at the cost of slightly coarser rotation granularity, which
is an acceptable trade for this platform's size.

Required IAM permission for the ECS task role / EC2 instance role:
    secretsmanager:GetSecretValue   on the specific secret ARN

Usage (called once, before Settings() is first constructed — see
app/core/config.py's get_settings()):

    from app.core.secrets_provider import load_secrets_into_environment
    load_secrets_into_environment()
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_SECRET_NAME_TEMPLATE = "civic-platform/{env}"


class SecretsProviderError(Exception):
    """Raised when secrets cannot be loaded and the app should not start."""


def _should_use_aws_secrets_manager() -> bool:
    return os.environ.get("SECRETS_PROVIDER", "").lower() == "aws_secrets_manager"


def _secret_name() -> str:
    explicit = os.environ.get("AWS_SECRETS_MANAGER_SECRET_NAME")
    if explicit:
        return explicit
    app_env = os.environ.get("APP_ENV", "production")
    return _DEFAULT_SECRET_NAME_TEMPLATE.format(env=app_env)


@lru_cache(maxsize=1)
def _fetch_secret_json(secret_name: str, region: str) -> dict:
    """
    Fetch and parse the secret. Cached for the lifetime of the process —
    this is called once at startup, not per-request. For rotation without
    a restart, see the rotation note at the bottom of this file.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as exc:
        raise SecretsProviderError(
            "boto3 is required to use SECRETS_PROVIDER=aws_secrets_manager "
            "(it should already be in requirements.txt for S3 storage support)."
        ) from exc

    client = boto3.client("secretsmanager", region_name=region)

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise SecretsProviderError(
            f"Failed to fetch secret '{secret_name}' from AWS Secrets Manager "
            f"(error: {error_code}). Check that the secret exists and the "
            f"running task/instance role has secretsmanager:GetSecretValue "
            f"on this specific ARN."
        ) from exc

    raw = response.get("SecretString")
    if not raw:
        raise SecretsProviderError(
            f"Secret '{secret_name}' has no SecretString value "
            f"(is it a binary secret? this provider only supports JSON string secrets)."
        )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretsProviderError(
            f"Secret '{secret_name}' is not valid JSON. Expected a flat "
            f"key-value object matching Settings field names, e.g. "
            f'{{"SECRET_KEY": "...", "DATABASE_URL": "...", ...}}'
        ) from exc

    if not isinstance(parsed, dict):
        raise SecretsProviderError(
            f"Secret '{secret_name}' must be a JSON object, got {type(parsed).__name__}."
        )

    return parsed


def load_secrets_into_environment(
    secret_name: Optional[str] = None,
    region: Optional[str] = None,
) -> int:
    """
    If SECRETS_PROVIDER=aws_secrets_manager is set, fetch the secret and
    inject every key into os.environ (without overwriting anything already
    explicitly set — e.g. APP_ENV itself, which has to be set before this
    function can even know which secret to fetch).

    Returns the number of variables injected. Returns 0 (no-op) if the
    provider isn't configured, which is the normal case in development.

    Call this exactly once, as early as possible in process startup —
    before app.core.config.get_settings() is first called anywhere.
    """
    if not _should_use_aws_secrets_manager():
        return 0

    name = secret_name or _secret_name()
    region = region or os.environ.get("AWS_REGION", "ap-south-1")

    logger.info("Loading secrets from AWS Secrets Manager: %s (region=%s)", name, region)

    secret_data = _fetch_secret_json(name, region)

    injected = 0
    for key, value in secret_data.items():
        if key in os.environ:
            # Something already set this explicitly (e.g. a Docker
            # environment: block) — that takes precedence over the
            # bulk secret, so an operator can still override a single
            # value without editing the whole JSON blob.
            continue
        os.environ[key] = str(value)
        injected += 1

    logger.info("Injected %d secret value(s) into the process environment.", injected)
    return injected


def clear_cache() -> None:
    """
    Used by the rotation endpoint / tests to force a re-fetch.
    Note: this only affects *future* calls to load_secrets_into_environment
    in the same process — it does NOT re-run Settings validation or update
    already-constructed Settings objects. A full secret rotation in a
    running fleet still requires a rolling restart; this codebase does not
    implement hot-reloading of SECRET_KEY/DATABASE_URL mid-process, which
    is the correct trade-off given how deeply those values are threaded
    through already-open DB connections and already-issued JWTs.
    """
    _fetch_secret_json.cache_clear()


# ─── Rotation note ────────────────────────────────────────────────────────────
#
# AWS Secrets Manager supports automatic rotation via a Lambda function for
# things like RDS credentials. For this platform's hand-managed JSON blob,
# rotation is a manual three-step process:
#
#   1. Update the secret value in the AWS console/CLI (e.g. new JWT_SECRET_KEY)
#   2. Trigger a rolling restart of the API/worker/beat services so they
#      each call load_secrets_into_environment() fresh on next boot
#      (gh workflow run deploy.yml -f environment=production -f image_tag=<current-sha>
#       redeploys the *same* image, which is enough to force a restart)
#   3. For JWT_SECRET_KEY specifically: rotating it invalidates every
#      currently-issued access/refresh token. Either accept that all users
#      get logged out, or implement a brief dual-key acceptance window in
#      app/core/security.py::decode_token() before flipping this — that's
#      intentionally NOT implemented here, since it adds real complexity
#      this platform's threat model doesn't yet justify.
