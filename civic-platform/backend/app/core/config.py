"""
Application configuration loaded from environment variables.
All secrets are read from .env — never hard-coded.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BeforeValidator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors(v: Any) -> list[str]:
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [i.strip() for i in v.split(",") if i.strip()]
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME:        str  = "Smart Civic Intelligence Platform"
    APP_VERSION:     str  = "1.0.0"
    APP_ENV:         Literal["development", "staging", "production"] = "development"
    DEBUG:           bool = False
    SECRET_KEY:      str  = secrets.token_urlsafe(64)
    API_V1_PREFIX:   str  = "/api/v1"
    DOCS_ENABLED:    bool = True

    # Server
    HOST:            str  = "0.0.0.0"
    PORT:            int  = 8000
    WORKERS:         int  = 4
    RELOAD:          bool = False

    # Database
    DATABASE_URL:    str  = "postgresql+asyncpg://civic:civic@localhost:5432/civic_platform"
    DATABASE_POOL_SIZE:    int  = 20
    DATABASE_MAX_OVERFLOW: int  = 10
    DATABASE_POOL_TIMEOUT: int  = 30
    DATABASE_POOL_RECYCLE: int  = 3600
    DATABASE_ECHO:         bool = False

    # Redis
    REDIS_URL:             str  = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int  = 50

    # JWT
    JWT_SECRET_KEY:                    str  = secrets.token_urlsafe(64)
    JWT_ALGORITHM:                     str  = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES:   int  = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS:     int  = 7

    # CORS
    ALLOWED_ORIGINS: Annotated[list[str], BeforeValidator(_parse_cors)] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # AWS S3
    AWS_ACCESS_KEY_ID:       str  = ""
    AWS_SECRET_ACCESS_KEY:   str  = ""
    AWS_REGION:              str  = "ap-south-1"
    AWS_S3_BUCKET:           str  = "smart-civic-media"
    AWS_S3_CDN_URL:          str  = ""
    AWS_S3_PRESIGNED_EXPIRY: int  = 3600

    # CloudFront (optional — CDN-aware signed URLs instead of direct S3 presigned URLs)
    # Leave all three blank to use direct S3 presigned URLs (the default, no CDN required).
    CLOUDFRONT_DOMAIN:       str  = ""    # e.g. "d123abc.cloudfront.net" or a custom domain
    CLOUDFRONT_KEY_PAIR_ID:  str  = ""    # from the CloudFront key group / trusted key group
    CLOUDFRONT_PRIVATE_KEY:  str  = ""    # PEM content, pasted as a single env var (like FIREBASE_CREDENTIALS_JSON)

    # Firebase
    FIREBASE_CREDENTIALS_JSON: str  = ""
    FIREBASE_PROJECT_ID:       str  = ""

    # Sentry
    SENTRY_DSN: str = ""

    # AI
    YOLO_MODEL_PATH:                      str   = "models/yolov8n-civic.pt"
    YOLO_CONFIDENCE_THRESHOLD:            float = 0.75
    DUPLICATE_RADIUS_METRES:              float = 500.0
    DUPLICATE_IMAGE_SIMILARITY_THRESHOLD: float = 0.85

    # Rate limiting
    RATE_LIMIT_DEFAULT:        str = "100/minute"
    RATE_LIMIT_AUTH:           str = "10/minute"
    RATE_LIMIT_COMPLAINT_POST: str = "5/minute"
    RATE_LIMIT_AI_PROCESS:     str = "3/minute"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE:     int = 100

    # File upload
    MAX_UPLOAD_SIZE_MB:  int       = 10
    ALLOWED_IMAGE_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp", "image/heic"]

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_URL: str = "redis://localhost:6379/2"

    # Email
    SMTP_HOST:     str  = "smtp.gmail.com"
    SMTP_PORT:     int  = 587
    SMTP_USER:     str  = ""
    SMTP_PASSWORD: str  = ""
    EMAIL_FROM:    str  = "noreply@smartcivic.gov.in"

    # Google Maps
    GOOGLE_MAPS_API_KEY: str = ""

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _validate_db_url(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
