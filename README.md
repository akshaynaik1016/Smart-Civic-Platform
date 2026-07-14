# Smart Civic Intelligence Platform — Assembled Release

This is the **single, complete, coherent source tree** — assembled directly
from the live working filesystem (not re-merged from the individual zips
delivered earlier in this build), with three real architectural problems
fixed along the way. Extract this and you have the actual current state of
the project in one place.

## What changed in this assembly pass

### 1. Two competing auth/cache systems → one
`app/api/v1/endpoints/auth.py` was calling `cache.managers.session_cache.SessionCacheManager`
directly — an older, separate Redis implementation from earlier in this
project's history (`civic-platform/cache/`). Meanwhile `app/services/auth_service.py`
(built later, and what the `users`/`officers`/`notification_preferences`
routers all depend on) used a completely different OTP/session store via
`app/repositories/auth_repository.py` + `app/core/redis_client.py`.

These never talked to each other. An OTP issued through one path could not
be verified through the other. **`auth.py` has been fully rewritten to use
`AuthService`**, and the standalone `cache/` package has been retired
(moved to `_retired/cache_DEPRECATED/` on the build machine, not included
in this archive).

### 2. `complaints.py` bypassed `ComplaintService` entirely
664 lines reimplementing status transitions, officer assignment, and
support-counting directly against raw SQLAlchemy queries — meaning the
duplicate-merge workflow, SLA-aware priority scoring, audit logging, and
push/email notifications built into `ComplaintService` were never actually
reachable through the API. It also imported two modules that don't exist
(`app.workers.tasks.process_complaint_ai`, `app.services.ai_service.AIService`).
**Fully rewritten to delegate to `ComplaintService`** for every operation.
Image uploads are now synchronous within the request (errors surface to
the citizen immediately) rather than fire-and-forget background tasks that
failed silently.

### 3. A real syntax error blocking every import
`app/services/notification_service.py` had unescaped double quotes inside
a string literal (`"Your complaint "{title}" ..."`). This meant **the
entire backend failed to import**, full stop — not a logic bug, a `SyntaxError`
at module load. Fixed.

### 4. Stray build artifacts
Several literal directories named things like `{services,repositories,workers}`
existed on disk — shell brace-expansion typos from earlier `mkdir` commands
that got committed as real (empty) directories instead of expanding.
Removed from `backend/`, `database/`, and `flutter_app/`.

## Verification performed

Every `.py` file in `backend/app/`, `backend/tests/`, and `backend/scripts/`
(79 files) was compiled with `python3 -m py_compile` after all fixes — this
confirms there are no remaining syntax errors and no remaining import-time
`AttributeError`/`ModuleNotFoundError` issues from missing modules. This
does **not** mean the app has been run end-to-end against a real Postgres/Redis
instance — that's the next real step (see below).

## What this archive does NOT include

- `civic-platform/cache/` — the retired Redis cache package (superseded,
  see above). If you want to inspect it for reference, it's preserved in
  `_retired/cache_DEPRECATED/` on the original build machine but not
  shipped here.
- A populated `backend/.env` or `.env` — only the `.example` templates.
  Run `python backend/scripts/generate_secrets.py` first.
- `node_modules/`, Python virtual environments, or any build output —
  install dependencies fresh.

## Quick start

```bash
cd civic-platform
python backend/scripts/generate_secrets.py   # generate real secrets
cp .env.example .env
cp backend/.env.example backend/.env
# paste generated SECRET_KEY/JWT_SECRET_KEY/passwords into backend/.env

docker compose up -d postgres redis
docker compose logs -f postgres   # confirm schema loads with no errors

docker compose up api             # watch it boot — should reach "Startup
                                    # validation passed" and serve /health
```

Then open `http://localhost:8000/docs` — every router (`auth`, `complaints`,
`notifications`, `notification preferences`, `duplicates`, `ai`, `users`,
`officers`, `analytics`, `reports`, `categories`) should be listed. If any
are missing, check `docker compose logs api` for an import warning.

## Honest status — what's still unverified

- **Not yet run against a real database.** All fixes are confirmed via
  static compilation, not a live boot. The next concrete step is exactly
  what's described in "Quick start" above, on a machine with Docker.
- **No Alembic migrations directory exists.** The schema lives as raw SQL
  in `database/schema/`, loaded via Postgres's `docker-entrypoint-initdb.d`
  mechanism on first boot. `docker-compose.prod.yml` references
  `alembic upgrade head` in its deploy step — that will fail until either
  an `alembic/` directory is generated or that line is removed.
- **Maps/Geolocation service, the broader test suite, and full
  documentation set (SRS/SDD/UML) were never built** — these remain
  genuinely open from the original project scope.
