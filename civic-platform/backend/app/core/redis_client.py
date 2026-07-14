"""Redis client singleton — init, ping, close, used across the entire backend."""
from __future__ import annotations
import logging
from typing import Optional
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError
from app.core.config import settings

logger = logging.getLogger(__name__)
_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None

def _build_pool() -> ConnectionPool:
    return ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_connect_timeout=5, socket_timeout=5, socket_keepalive=True,
        retry=Retry(ExponentialBackoff(cap=10, base=1), retries=3),
        retry_on_error=[ConnectionError, TimeoutError],
        decode_responses=True,
    )

async def init_redis() -> None:
    global _pool, _client
    _pool = _build_pool()
    _client = Redis(connection_pool=_pool)
    logger.info("Redis initialised — %s", settings.REDIS_URL)

async def close_redis() -> None:
    global _pool, _client
    if _client: await _client.aclose(); _client = None
    if _pool:   await _pool.aclose();   _pool   = None

async def ping_redis() -> bool:
    try: return bool(await redis_client.ping())
    except Exception as exc: logger.error("Redis ping failed: %s", exc); return False

class _LazyRedis:
    def __getattr__(self, name: str):
        if _client is None:
            raise RuntimeError("Redis not initialised. Call init_redis() on startup.")
        return getattr(_client, name)

redis_client: Redis = _LazyRedis()  # type: ignore[assignment]
