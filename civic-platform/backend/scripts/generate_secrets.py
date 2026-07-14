#!/usr/bin/env python3
"""
generate_secrets.py
=====================
Generates cryptographically strong values for every secret-like field in
Settings, printed in .env format ready to paste. Run this once per
environment (development/staging/production each need their OWN values —
never share a SECRET_KEY across environments).

Usage:
    python scripts/generate_secrets.py                  # print to stdout
    python scripts/generate_secrets.py > backend/.env.new  # redirect to a file,
                                                            # then merge non-secret
                                                            # fields in manually
"""

from __future__ import annotations

import secrets
import sys
from datetime import datetime, timezone


def generate_password(length: int = 32) -> str:
    """URL-safe password — fine for Redis/Postgres AUTH, env-var-friendly."""
    return secrets.token_urlsafe(length)


def generate_key(length: int = 64) -> str:
    """Longer value for JWT/app secret keys — these get hashed/signed against,
    so more entropy is cheap insurance."""
    return secrets.token_urlsafe(length)


def main() -> None:
    secret_key = generate_key()
    jwt_secret_key = generate_key()

    # Guard against the one-in-a-very-large-number collision that the
    # validator explicitly checks for (SECRET_KEY != JWT_SECRET_KEY)
    while jwt_secret_key == secret_key:
        jwt_secret_key = generate_key()

    output = f"""\
# ══════════════════════════════════════════════════════════════════════════════
# Generated secrets — {datetime.now(timezone.utc).isoformat()}
# ══════════════════════════════════════════════════════════════════════════════
# These values have real entropy and will pass secrets_validator.py's checks.
# They are NOT yet a complete .env — merge with backend/.env.example for the
# non-secret fields (HOST, PORT, rate limits, etc.), then fill in third-party
# credentials (AWS, Firebase, SMTP, Sentry, Google Maps) by hand — those
# can't be generated, they have to come from the actual provider.
#
# Generate a SEPARATE set of these for each of development/staging/production.
# Never reuse one environment's secrets in another.

SECRET_KEY={secret_key}
JWT_SECRET_KEY={jwt_secret_key}

POSTGRES_PASSWORD={generate_password()}
REDIS_PASSWORD={generate_password()}

FLOWER_PASSWORD={generate_password(16)}
PGADMIN_PASSWORD={generate_password(16)}
"""
    sys.stdout.write(output)


if __name__ == "__main__":
    main()
