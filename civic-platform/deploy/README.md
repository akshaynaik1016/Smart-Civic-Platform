# Deployment Guide — Smart Civic Intelligence Platform

## Architecture

```
                    ┌─────────────┐
   Internet ───────▶│  edge       │  Nginx — TLS termination, rate limiting
                    │  (Nginx)    │  (production profile only)
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
      ┌───────────────┐         ┌───────────────┐
      │   dashboard    │         │      api       │  FastAPI (uvicorn, 4 workers)
      │ (React + Nginx)│         │   (Python 3.12) │
      └────────────────┘         └────────┬───────┘
                                           │
                       ┌───────────────────┼───────────────────┐
                       ▼                   ▼                   ▼
               ┌──────────────┐   ┌──────────────┐    ┌──────────────┐
               │   worker     │   │     beat      │    │   postgres   │
               │  (Celery)    │   │ (Celery beat) │    │  + PostGIS   │
               └──────┬───────┘   └──────┬────────┘    └──────────────┘
                      │                  │
                      └────────┬─────────┘
                                ▼
                        ┌──────────────┐
                        │    redis     │  cache · sessions · broker · rate limits
                        └──────────────┘
```

## Quick start (local development)

```bash
cp .env.example .env
cp backend/.env.example backend/.env
# edit backend/.env — at minimum set SECRET_KEY and JWT_SECRET_KEY

make dev
```

This starts the API with `--reload`, the dashboard with Vite's dev server
(hot module replacement), and exposes every service directly on localhost:

| Service     | URL                              |
|-------------|-----------------------------------|
| Dashboard   | http://localhost:5173             |
| API         | http://localhost:8000             |
| API docs    | http://localhost:8000/docs        |
| Flower      | http://localhost:5555             |
| pgAdmin     | http://localhost:5050              |

## Production deployment

```bash
cp .env.example .env
cp backend/.env.example backend/.env
# Fill in real secrets, AWS credentials, Firebase credentials, SMTP, etc.
# Set APP_ENV=production in backend/.env

make cert-init      # one-time: obtain Let's Encrypt certificates
make prod            # builds and starts the full stack with the edge proxy
make migrate          # apply database migrations
```

Production mode (`docker-compose.prod.yml`):
- Only the `edge` Nginx proxy is publicly exposed (ports 80/443)
- `api`, `postgres`, `redis`, and `dashboard` have no published ports —
  reachable only on the internal `civic-net` Docker network
- `DOCS_ENABLED=false` disables the public Swagger UI
- Resource limits are set per service (see `docker-compose.prod.yml`)
- Certbot auto-renews TLS certificates every 12 hours

## Pre-launch checklist

- [ ] `SECRET_KEY` and `JWT_SECRET_KEY` are unique, long, random values — never reuse the defaults
- [ ] `POSTGRES_PASSWORD` and `REDIS_PASSWORD` changed from defaults
- [ ] `ALLOWED_ORIGINS` restricted to the actual dashboard/mobile-app origins
- [ ] AWS S3 bucket created with appropriate CORS policy for image uploads
- [ ] Firebase service-account JSON configured for push notifications
- [ ] SMTP credentials configured (or accept that OTP/status emails are log-only)
- [ ] `YOLO_MODEL_PATH` points to an actual trained `.pt` file in `./models/`
- [ ] Sentry DSN configured for production error tracking
- [ ] DNS A/AAAA records point to the host running `edge`
- [ ] `make cert-init` run successfully before first production `make prod`
- [ ] Database backup cron job scheduled (`make backup` or external pg_dump)
- [ ] Firewall allows only 80/443 inbound; 5432/6379/8000 not exposed externally

## Common operations

```bash
make logs              # tail all service logs
make shell-api         # bash into the API container
make shell-db          # psql into the database
make backup            # dump DB to ./backups/
make restore           # restore from the most recent backup
make cert-renew        # force TLS certificate renewal
make test              # run the backend test suite
```

## Scaling

The `api` and `worker` services are stateless and can be horizontally scaled:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production up -d --scale api=3 --scale worker=2
```

Nginx's `upstream civic_api` block in `deploy/nginx/edge.conf` already
load-balances across however many `api` replicas are running.

## Rolling back

```bash
git checkout <previous-tag>
make prod    # rebuilds and restarts with the previous code
```

Database migrations are forward-only by default; if a release included a
destructive migration, restore from the pre-deploy backup instead of relying
on `alembic downgrade`.
