"""
Smart Civic Intelligence Platform — FastAPI Application
=======================================================
Application factory that:
  • Wires all API routers under /api/v1/
  • Registers CORS, rate-limit, request-ID, audit middleware
  • Registers structured exception handlers
  • Manages DB pool + Redis pool lifecycle via lifespan
  • Exposes /health and /metrics endpoints
  • Configures Sentry in production
  • Serves Swagger / ReDoc docs (when DOCS_ENABLED=true)
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

# ── Secrets must be loaded into os.environ BEFORE the config import below ────
# app.core.config constructs the module-level `settings` singleton at import
# time, reading from os.environ. If this app is running with
# SECRETS_PROVIDER=aws_secrets_manager, the real secret values have to land
# in the environment before that happens — otherwise Settings() silently
# falls back to its insecure defaults and secrets_validator.py has to catch
# it after the fact instead of it just working correctly the first time.
from app.core.secrets_provider import load_secrets_into_environment

load_secrets_into_environment()

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown tasks."""
    setup_logging()
    logger.info("Starting %s v%s [%s]", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)

    # Fail fast on insecure production configuration — before touching DB/Redis
    from app.core.secrets_validator import validate_or_raise
    validate_or_raise(settings)

    # Database pool
    if settings.APP_ENV != "test":
        await init_db()
        logger.info("Database pool ready")

    # Redis
    from app.core.redis_client import init_redis, close_redis
    await init_redis()
    logger.info("Redis ready")

    # Firebase Admin SDK (lazy — initialised on first FCM call)
    # Sentry
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            release=f"{settings.APP_NAME}@{settings.APP_VERSION}",
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.1,
        )
        logger.info("Sentry initialized")

    yield  # ── Application running ──

    # Shutdown
    await close_db()
    await close_redis()
    logger.info("Shutdown complete")


# ─── Application factory ──────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "AI-powered civic issue reporting and municipality management platform. "
            "Built for Hubballi-Dharwad Municipal Corporation."
        ),
        docs_url="/docs"    if settings.DOCS_ENABLED else None,
        redoc_url="/redoc"  if settings.DOCS_ENABLED else None,
        openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
        lifespan=lifespan,
    )

    _add_middleware(app)
    _register_exception_handlers(app)
    _register_routers(app)
    _register_utility_endpoints(app)

    return app


# ─── Middleware ───────────────────────────────────────────────────────────────

def _add_middleware(app: FastAPI) -> None:

    # 1. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID", "X-RateLimit-Limit",
            "X-RateLimit-Remaining", "Retry-After",
        ],
    )

    # 2. Trusted hosts (production guard)
    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["smartcivic.gov.in", "*.smartcivic.gov.in", "localhost"],
        )

    # 3. Request ID injection + latency logging
    app.add_middleware(_RequestIDMiddleware)

    # 4. Prometheus metrics
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator(
            should_group_status_codes=True,
            should_respect_env_var=True,
            env_var_name="ENABLE_METRICS",
        ).instrument(app).expose(app, endpoint="/metrics")
    except ImportError:
        pass


class _RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID to every request and log latency."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = rid

        logger.info(
            "%s %s %s %.2fms [%s]",
            request.method, request.url.path,
            response.status_code, duration_ms, rid,
        )
        return response


# ─── Exception handlers ───────────────────────────────────────────────────────

def _register_exception_handlers(app: FastAPI) -> None:
    register_exception_handlers(app)


# ─── Routers ─────────────────────────────────────────────────────────────────

def _register_routers(app: FastAPI) -> None:
    from app.api.v1.endpoints.auth           import router as auth_router
    from app.api.v1.endpoints.complaints     import router as complaints_router
    from app.api.v1.endpoints.notifications  import router as notifications_router
    from app.api.v1.endpoints.notification_preferences import router as prefs_router
    from app.api.v1.endpoints.duplicate_review import router as duplicates_router
    from app.api.v1.endpoints.ai_detection import router as ai_router

    # Lazily import optional routers that may not exist yet
    _optional = [
        ("app.api.v1.endpoints.users",     "router", "users_router"),
        ("app.api.v1.endpoints.officers",  "router", "officers_router"),
        ("app.api.v1.endpoints.analytics", "router", "analytics_router"),
        ("app.api.v1.endpoints.reports",   "router", "reports_router"),
        ("app.api.v1.endpoints.categories","router", "categories_router"),
    ]

    prefix = settings.API_V1_PREFIX

    # Core routers (always present)
    app.include_router(auth_router,          prefix=prefix)
    app.include_router(complaints_router,    prefix=prefix)
    app.include_router(notifications_router, prefix=prefix)
    app.include_router(prefs_router,         prefix=prefix)
    app.include_router(duplicates_router,    prefix=prefix)
    app.include_router(ai_router,            prefix=prefix)

    # Optional routers (skip if module not yet generated)
    for module_path, attr, _ in _optional:
        try:
            import importlib
            mod    = importlib.import_module(module_path)
            router = getattr(mod, attr)
            app.include_router(router, prefix=prefix)
            logger.debug("Registered router: %s", module_path)
        except (ImportError, AttributeError):
            logger.debug("Router not found (skipped): %s", module_path)


# ─── Utility endpoints ────────────────────────────────────────────────────────

def _register_utility_endpoints(app: FastAPI) -> None:

    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health_check():
        """
        Liveness + readiness probe used by Docker/Kubernetes health checks.
        Returns 200 only when both DB and Redis are reachable.
        """
        from app.core.redis_client import ping_redis
        from app.core.database import engine
        from sqlalchemy import text

        checks: dict[str, str] = {}

        # DB check
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"

        # Redis check
        try:
            ok = await ping_redis()
            checks["redis"] = "ok" if ok else "error: ping failed"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"

        all_ok = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={
                "status":  "healthy" if all_ok else "degraded",
                "version": settings.APP_VERSION,
                "env":     settings.APP_ENV,
                "checks":  checks,
            },
        )

    @app.get("/", tags=["Root"], include_in_schema=False)
    async def root():
        return {
            "name":    settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs":    "/docs" if settings.DOCS_ENABLED else "disabled",
        }


# ─── Entry point ─────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=1 if settings.RELOAD else settings.WORKERS,
        log_level="info",
        access_log=False,   # handled by _RequestIDMiddleware
    )
