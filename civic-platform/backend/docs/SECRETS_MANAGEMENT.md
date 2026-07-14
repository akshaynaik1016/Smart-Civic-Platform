# Environment Configuration & Secrets Management

## The three layers

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Prevention — .gitignore                                       │
│    Real .env/.jks/.json credential files can never be committed  │
│    in the first place. Only *.example templates are tracked.    │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│ 2. Supply — secrets_provider.py                                  │
│    Development: backend/.env (as it always has been)            │
│    Production:  AWS Secrets Manager, fetched at container        │
│                  startup before Settings() is ever constructed   │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│ 3. Verification — secrets_validator.py                           │
│    Runs in the FastAPI lifespan, regardless of which supply path │
│    above was used. Refuses to start in production if any secret  │
│    is a known placeholder, has insufficient entropy, or if CORS/ │
│    docs-exposure looks like a dev config that leaked through.    │
└─────────────────────────────────────────────────────────────────┘
```

Each layer is independently useful and the system degrades gracefully:
even if you skip layer 2 entirely and just hand-edit `backend/.env` on a
production box (layer 1's intended workflow for a small single-VM
deployment), layer 3 still catches the most common mistakes before they
ever serve traffic.

## Quick start — development

Nothing changes from before. `backend/.env.example` → copy to `backend/.env`
→ fill in values → `make dev`. The validator runs but downgrades every
finding to a warning in non-production environments, so a half-configured
dev setup still boots.

```bash
cp backend/.env.example backend/.env
python backend/scripts/generate_secrets.py   # generate real SECRET_KEY/JWT_SECRET_KEY
                                               # even for local dev — costs nothing,
                                               # avoids "works on my machine because
                                               # I never rotated the example value"
# paste the generated values into backend/.env, fill in the rest by hand
make dev
```

## Quick start — production, plain `.env` (smallest deployments)

```bash
python backend/scripts/generate_secrets.py > /tmp/generated.env
# merge generated.env's secret fields into a real backend/.env.production
# fill in AWS/Firebase/SMTP/Sentry/Google Maps credentials by hand
scp backend/.env.production prod-host:/opt/civic-platform/backend/.env
ssh prod-host "cd /opt/civic-platform && make prod"
```

The startup validator runs automatically and will refuse to boot if
anything in that file is still a placeholder — this is the safety net for
exactly the "copied .env.example and forgot to change something" mistake.

## Recommended — production via AWS Secrets Manager

This is the path that doesn't leave secret values sitting in plaintext on
the production host's disk.

```bash
# 1. Generate strong values and assemble a complete env file LOCALLY —
#    never on the production host itself
python backend/scripts/generate_secrets.py > /tmp/civic-secrets.env
cat backend/.env.example >> /tmp/civic-secrets.env   # then hand-edit to merge

# 2. Push to AWS Secrets Manager (dry-run first to review what would be sent)
python backend/scripts/push_secrets_to_aws.py \
  --env-file /tmp/civic-secrets.env \
  --secret-name civic-platform/production \
  --region ap-south-1 \
  --dry-run

python backend/scripts/push_secrets_to_aws.py \
  --env-file /tmp/civic-secrets.env \
  --secret-name civic-platform/production \
  --region ap-south-1

# 3. Securely delete the local plaintext file
shred -u /tmp/civic-secrets.env   # or `rm -P` on macOS

# 4. On the production host, backend/.env only needs ONE thing —
#    everything else comes from Secrets Manager at container startup:
echo "SECRETS_PROVIDER=aws_secrets_manager" > backend/.env
echo "AWS_SECRETS_MANAGER_SECRET_NAME=civic-platform/production" >> backend/.env
echo "APP_ENV=production" >> backend/.env

# 5. Grant the running container's IAM role read access —
#    see deploy/aws/secrets-manager-iam-policy.example.json
#    (read-only on this one secret ARN; the container itself can never
#     write to Secrets Manager, only the operator running step 2 can)

make prod
```

### How this actually wires together at runtime

`app/main.py`'s very first import is `secrets_provider.load_secrets_into_environment()`
— deliberately *before* `app.core.config` (and therefore Pydantic
`Settings()`) is imported anywhere. If `SECRETS_PROVIDER=aws_secrets_manager`
is set, this fetches the JSON secret and injects every key into
`os.environ`, so `Settings()` picks them up exactly as if they'd come from
a `.env` file — no changes needed anywhere else in the codebase that
already reads from `settings`.

If a value is already explicitly set in the environment (e.g. via a
`docker-compose.yml` `environment:` block), that takes precedence over
the bulk secret — useful for overriding a single value without touching
the whole JSON blob.

## Rotation

| Secret | Rotation process |
|---|---|
| `POSTGRES_PASSWORD` / `REDIS_PASSWORD` | Update in Secrets Manager → update the actual Postgres/Redis instance → rolling restart |
| `SECRET_KEY` | Update in Secrets Manager → rolling restart. No user-facing impact (not used for currently-issued tokens). |
| `JWT_SECRET_KEY` | Update in Secrets Manager → rolling restart. **Invalidates every currently-issued access/refresh token** — every logged-in user is logged out. A dual-key acceptance window is intentionally NOT implemented (see the comment at the bottom of `secrets_provider.py`) — this platform's size doesn't yet justify that complexity. |
| AWS/Firebase/SMTP credentials | Update in Secrets Manager → rolling restart |

Triggering a rolling restart without a code change:
```bash
gh workflow run deploy.yml -f environment=production -f image_tag=<current-sha>
```

## What the startup validator actually checks

See `backend/app/core/secrets_validator.py` for the full implementation.
Summary of checks and their production severity:

| Check | Severity | Why |
|---|---|---|
| `SECRET_KEY`/`JWT_SECRET_KEY` is a known placeholder | Fatal | These sign every session — a guessable value means forged tokens |
| `SECRET_KEY`/`JWT_SECRET_KEY` under 32 chars | Fatal | Insufficient entropy even if not a literal known placeholder |
| `SECRET_KEY` == `JWT_SECRET_KEY` | Fatal | One leak shouldn't compromise both purposes |
| `DATABASE_URL` contains default `civic`/`civic` credentials | Fatal | The literal default from `docker-compose.yml` |
| `REDIS_URL` has no password or uses `changeme` | Fatal | Redis holds JWT blacklists, OTPs, rate-limit counters |
| `ALLOWED_ORIGINS` contains `localhost` or `*` | Fatal | CORS misconfiguration in production |
| `DOCS_ENABLED=true` | Warning | Exposes the API schema publicly — sometimes intentional |
| No AWS credentials | Warning | Falls back to local-filesystem storage, which doesn't survive restarts |
| No Sentry DSN | Warning | Errors only visible in container logs |
| No SMTP credentials | Warning | OTP emails are logged instead of sent |

All "Fatal" severities are automatically downgraded to "Warning" outside
of `APP_ENV=production` — development and staging-without-real-data should
never be blocked from starting.

## Testing

```bash
cd backend
pytest tests/test_secrets_validator.py -v
```

These tests run automatically in `backend-ci.yml` on every push — a future
change that accidentally weakens a check (e.g. removing the CORS wildcard
check) would fail CI, not just be caught months later in a real incident.

## Files in this module

| File | Purpose |
|---|---|
| `.gitignore` (repo root) | Prevents real secrets from ever being committed |
| `backend/app/core/secrets_validator.py` | Startup-time fail-fast validation |
| `backend/app/core/secrets_provider.py` | AWS Secrets Manager → environment injection |
| `backend/scripts/generate_secrets.py` | Generates cryptographically strong values |
| `backend/scripts/push_secrets_to_aws.py` | One-time/per-rotation `.env` → Secrets Manager pusher |
| `backend/tests/test_secrets_validator.py` | Test coverage, runs in CI |
| `deploy/aws/secrets-manager-iam-policy.example.json` | Least-privilege IAM policy for the read-only consumer role |
| `backend/.env.example` | Documents every field, both supply paths |
