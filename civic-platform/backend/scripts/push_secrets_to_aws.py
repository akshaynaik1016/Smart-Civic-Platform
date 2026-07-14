#!/usr/bin/env python3
"""
push_secrets_to_aws.py
=======================
One-time (or per-rotation) helper: reads a local .env-format file and pushes
it into AWS Secrets Manager as a single JSON secret, matching the format
app/core/secrets_provider.py expects to read back.

This is the *only* place a real .env file should ever be involved in a
production deployment — used once, locally, by whoever holds the
credentials, to seed or update the managed secret. It is never committed,
never shipped in an image, and never present on the production host itself
(the host fetches from Secrets Manager directly at container startup).

Usage:
    python scripts/push_secrets_to_aws.py \\
        --env-file backend/.env.production \\
        --secret-name civic-platform/production \\
        --region ap-south-1

    # Dry run — show what would be pushed without actually calling AWS
    python scripts/push_secrets_to_aws.py --env-file backend/.env.production --dry-run

Requires AWS credentials in the environment (AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY, or an assumed role) with secretsmanager:CreateSecret
and secretsmanager:PutSecretValue on the target secret name.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Fields that should NEVER be pushed even if present in the .env file —
# these are compose-level / build-time values, not application secrets,
# and don't belong in the Secrets Manager blob app/core/secrets_provider.py
# injects into the API/worker process environment.
_EXCLUDED_KEYS = {
    "APP_ENV",          # set explicitly by the deploy environment, not the secret
    "DEBUG",
    "RELOAD",
    "DOCS_ENABLED",
    "HOST",
    "PORT",
    "WORKERS",
}


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser — KEY=VALUE per line, '#' comments, quoted values."""
    result: dict[str, str] = {}
    if not path.exists():
        print(f"error: env file not found: {path}", file=sys.stderr)
        sys.exit(1)

    for lineno, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            print(f"warning: skipping malformed line {lineno}: {raw_line!r}", file=sys.stderr)
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Strip matching surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        if key in _EXCLUDED_KEYS:
            continue
        if not value:
            continue   # don't push empty placeholders — let the provider's
                       # defaults or per-environment overrides handle them

        result[key] = value

    return result


def push_to_secrets_manager(
    secret_name: str,
    payload: dict[str, str],
    region: str,
    description: str,
) -> None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("secretsmanager", region_name=region)
    secret_string = json.dumps(payload, indent=2, sort_keys=True)

    try:
        client.put_secret_value(SecretId=secret_name, SecretString=secret_string)
        print(f"Updated existing secret: {secret_name}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            client.create_secret(
                Name=secret_name,
                SecretString=secret_string,
                Description=description,
            )
            print(f"Created new secret: {secret_name}")
        else:
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", required=True, type=Path, help="Path to the local .env file to push")
    parser.add_argument("--secret-name", required=True, help="AWS Secrets Manager secret name, e.g. civic-platform/production")
    parser.add_argument("--region", default="ap-south-1", help="AWS region (default: ap-south-1)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be pushed without calling AWS")
    args = parser.parse_args()

    payload = parse_env_file(args.env_file)

    if not payload:
        print("error: no usable key=value pairs found in env file — aborting.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(payload)} secret field(s) from {args.env_file}")
    print(f"Excluded (compose/build-time, not secrets): {sorted(_EXCLUDED_KEYS)}")

    if args.dry_run:
        print("\n--dry-run: the following JSON would be pushed to "
              f"'{args.secret_name}' in region '{args.region}':\n")
        redacted = {k: ("***" if len(v) > 4 else v) for k, v in payload.items()}
        print(json.dumps(redacted, indent=2, sort_keys=True))
        print("\n(Values redacted above for display — full values would be sent unredacted to AWS.)")
        return

    confirm = input(
        f"\nThis will push {len(payload)} secret(s) to AWS Secrets Manager as "
        f"'{args.secret_name}' in '{args.region}'. Continue? [y/N] "
    )
    if confirm.strip().lower() != "y":
        print("Aborted.")
        return

    push_to_secrets_manager(
        secret_name=args.secret_name,
        payload=payload,
        region=args.region,
        description="Smart Civic Intelligence Platform — application secrets "
                     "(consumed by app/core/secrets_provider.py)",
    )
    print(
        "\nDone. Services with SECRETS_PROVIDER=aws_secrets_manager will pick "
        "this up on their next restart. Trigger one with:\n"
        "  gh workflow run deploy.yml -f environment=production -f image_tag=<current-sha>"
    )


if __name__ == "__main__":
    main()
