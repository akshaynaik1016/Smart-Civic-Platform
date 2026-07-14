# CI/CD Pipeline — Smart Civic Intelligence Platform

## Pipeline overview

```
push/PR ──┬─▶ backend-ci.yml    (lint, mypy, pytest+Postgres/Redis, pip-audit)
          ├─▶ dashboard-ci.yml  (eslint, tsc, vite build, npm audit)
          ├─▶ mobile-ci.yml     (flutter analyze, test, debug APK)
          ├─▶ pr-checks.yml     (title lint, auto-label, size label)
          └─▶ codeql.yml        (static analysis, weekly + on PR)
                    │
                    ▼  (on push to main, gated on CI success)
            docker-build.yml
                    │  builds + pushes ghcr.io images, tagged by SHA
                    │  Trivy scans both images for CVEs
                    ▼
            (manual) deploy.yml ──▶ staging  (no approval required)
                                ──▶ production (requires reviewer approval —
                                                 configure in Settings → Environments)

git tag v1.0.0 ──▶ release.yml  (signed APK/AAB + draft GitHub Release)
```

## Why deploy is manual but build is automatic

Every push to `main` produces a deployable image — but *deploying* it is a
deliberate `workflow_dispatch` action, not automatic. This means:
- You can merge small fixes to `main` all day without triggering production changes
- Rollback is "redeploy the previous SHA tag," not "revert a commit and rebuild"
- Production additionally requires a GitHub Environment approval (configure
  this once in repo Settings — see below)

## Required repository secrets

Configure these under **Settings → Secrets and variables → Actions**:

| Secret                      | Used by              | Purpose                                      |
|------------------------------|----------------------|-----------------------------------------------|
| `CODECOV_TOKEN`              | backend-ci, mobile-ci| Coverage upload (optional — works without it)|
| `DEPLOY_SSH_KEY`              | deploy.yml            | Private key for SSH access to target host    |
| `DEPLOY_SSH_USER`             | deploy.yml            | SSH username on target host                  |
| `STAGING_HOST`                | deploy.yml            | Staging server hostname/IP                   |
| `STAGING_DEPLOY_PATH`         | deploy.yml            | Path to the repo checkout on staging host     |
| `PROD_HOST`                    | deploy.yml            | Production server hostname/IP                |
| `PROD_DEPLOY_PATH`             | deploy.yml            | Path to the repo checkout on production host  |
| `ANDROID_KEYSTORE_BASE64`     | release.yml            | `base64 -w0 civic-release.jks`                |
| `ANDROID_KEYSTORE_PASSWORD`   | release.yml            | Keystore password                              |
| `ANDROID_KEY_PASSWORD`        | release.yml            | Key password                                   |
| `ANDROID_KEY_ALIAS`           | release.yml            | Key alias                                      |

`GITHUB_TOKEN` is provided automatically by Actions — no setup needed for
GHCR push/pull or release drafting.

## One-time setup: GitHub Environments

Production deploys should require human approval. Configure this once:

1. **Settings → Environments → New environment** → name it `production`
2. Under **Deployment protection rules**, enable **Required reviewers** and
   add at least one team member
3. Repeat for `staging` if you want the same gate there (optional —
   `deploy.yml` works without it, just without the approval pause)

## One-time setup: target host

`deploy.yml` assumes the target host already has:
- Docker + Docker Compose v2 installed
- A checkout of this repo at the path in `*_DEPLOY_PATH`
- `backend/.env` populated with real production secrets (never committed —
  see `backend/.env.example`)
- The SSH public key corresponding to `DEPLOY_SSH_KEY` added to
  `~/.ssh/authorized_keys` for `DEPLOY_SSH_USER`

```bash
# One-time, on the target host
git clone <repo-url> /opt/civic-platform
cd /opt/civic-platform
cp .env.example .env
cp backend/.env.example backend/.env
# edit backend/.env with real secrets
make cert-init   # if this is the production host with a real domain
```

## Branch strategy this pipeline assumes

- `develop` — integration branch, feature PRs target this
- `main` — always deployable; merging here triggers an image build
- `release/*` — cut from `main` for release stabilization (pr-checks.yml
  allows these to target `main` directly without the "are you sure" warning)
- `v*.*.*` tags — cut from `main`, trigger `release.yml`

## Running checks locally before pushing

```bash
# Backend
cd backend
ruff check app/ tests/
black --check app/ tests/
mypy app/ --ignore-missing-imports
pytest tests/ -v

# Dashboard
cd civic-dashboard
npm run lint
npx tsc --noEmit
npm run build

# Mobile
cd civic-platform/flutter_app
flutter analyze
flutter test
```

## Rollback procedure

```bash
# Find the previous working SHA from a past docker-build.yml run summary,
# or from deploy.yml's "Deployment summary" step output
gh workflow run deploy.yml -f environment=production -f image_tag=<previous-sha>
```

`deploy.yml` also auto-rolls-back on its own if the post-deploy health check
fails — the manual path above is for rolling back something that *passed*
its health check but is misbehaving in a way the check doesn't catch.
