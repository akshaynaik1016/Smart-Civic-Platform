"""
AuthRepository — Redis-backed storage for:
  • OTP codes (with attempt counting and expiry)
  • JWT blacklist (on logout)
  • Refresh token registry (per user/device)
  • Login attempt throttling (brute-force protection)
  • FCM device token storage

All keys use the same naming scheme as cache/keys/cache_keys.py so that
the Redis caching layer and the auth layer never collide.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Optional

from app.core.config import settings


class AuthRepository:
    """
    Thin async wrapper around Redis that owns all auth-related keys.
    Accepts a redis.asyncio.Redis client injected at construction time.
    """

    # Key TTLs
    OTP_TTL_SECONDS:          int = 300        # 5 min
    OTP_MAX_ATTEMPTS:         int = 3
    LOGIN_WINDOW_SECONDS:     int = 60
    LOGIN_MAX_ATTEMPTS:       int = 10
    ACCESS_BLACKLIST_DEFAULT: int = 3600       # fallback if token TTL unknown
    REFRESH_TTL_SECONDS:      int = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86_400
    SESSION_TTL_SECONDS:      int = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86_400

    # Key prefixes — must not overlap with cache/ module keys
    _PFX_OTP       = "auth:otp"
    _PFX_BLACKLIST = "blacklist:jwt"
    _PFX_REFRESH   = "auth:refresh"
    _PFX_SESSION   = "session:user"
    _PFX_ATTEMPTS  = "auth:attempts"
    _PFX_FCM       = "auth:fcm"

    def __init__(self, redis) -> None:
        self._r = redis

    # ── OTP ──────────────────────────────────────────────────────────────────

    def _otp_key(self, identifier: str, purpose: str) -> str:
        return f"{self._PFX_OTP}:{purpose}:{identifier.lower()}"

    async def store_otp(
        self,
        identifier: str,
        otp_code: str,
        purpose: str = "verify",
        ttl: int = OTP_TTL_SECONDS,
    ) -> None:
        """Store OTP payload as a Redis hash with attempt counter."""
        key = self._otp_key(identifier, purpose)
        pipe = self._r.pipeline()
        pipe.hset(key, mapping={
            "code":     otp_code,
            "attempts": 0,
            "max":      self.OTP_MAX_ATTEMPTS,
        })
        pipe.expire(key, ttl)
        await pipe.execute()

    async def generate_otp(
        self,
        identifier: str,
        purpose: str = "verify",
        length: int = 6,
        ttl: int = OTP_TTL_SECONDS,
    ) -> str:
        """Generate a cryptographically random numeric OTP, store it, and return it."""
        code = "".join(str(secrets.randbelow(10)) for _ in range(length))
        await self.store_otp(identifier, code, purpose, ttl)
        return code

    async def verify_otp(
        self,
        identifier: str,
        submitted_code: str,
        purpose: str = "verify",
    ) -> tuple[bool, str]:
        """
        Validate an OTP.
        Returns (True, "ok") | (False, reason)
        where reason ∈ {"expired", "invalid", "max_attempts"}
        """
        key = self._otp_key(identifier, purpose)
        payload = await self._r.hgetall(key)

        if not payload:
            return False, "expired"

        attempts    = int(payload.get(b"attempts", payload.get("attempts", 0)))
        max_allowed = int(payload.get(b"max", payload.get("max", self.OTP_MAX_ATTEMPTS)))

        if attempts >= max_allowed:
            await self._r.delete(key)
            return False, "max_attempts"

        stored_code = (payload.get(b"code") or payload.get("code") or b"").decode() \
            if isinstance(payload.get(b"code", ""), bytes) else str(payload.get("code", ""))

        if not hmac.compare_digest(stored_code, submitted_code):
            # Increment attempt counter atomically
            remaining_ttl = await self._r.ttl(key)
            await self._r.hset(key, "attempts", attempts + 1)
            if remaining_ttl > 0:
                await self._r.expire(key, remaining_ttl)
            return False, "invalid"

        # Correct — consume the OTP
        await self._r.delete(key)
        return True, "ok"

    async def delete_otp(self, identifier: str, purpose: str = "verify") -> None:
        await self._r.delete(self._otp_key(identifier, purpose))

    # ── JWT blacklist ─────────────────────────────────────────────────────────

    async def blacklist_token(self, jti: str, ttl_seconds: int) -> None:
        """Blacklist a JWT by its unique ID until it naturally expires."""
        if ttl_seconds > 0:
            await self._r.set(f"{self._PFX_BLACKLIST}:{jti}", "1", ex=ttl_seconds)

    async def is_token_blacklisted(self, jti: str) -> bool:
        return bool(await self._r.exists(f"{self._PFX_BLACKLIST}:{jti}"))

    # ── Refresh tokens ────────────────────────────────────────────────────────

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _refresh_key(self, user_id: str, device_id: str) -> str:
        return f"{self._PFX_REFRESH}:{user_id}:{device_id}"

    async def store_refresh_token(
        self,
        user_id: str,
        refresh_token: str,
        device_id: str = "default",
    ) -> None:
        """Store a hashed refresh token for a device."""
        key = self._refresh_key(user_id, device_id)
        await self._r.set(key, self._hash_token(refresh_token), ex=self.REFRESH_TTL_SECONDS)

    async def validate_refresh_token(
        self,
        user_id: str,
        refresh_token: str,
        device_id: str = "default",
    ) -> bool:
        stored = await self._r.get(self._refresh_key(user_id, device_id))
        if not stored:
            return False
        stored_str = stored.decode() if isinstance(stored, bytes) else stored
        return hmac.compare_digest(stored_str, self._hash_token(refresh_token))

    async def revoke_refresh_token(self, user_id: str, device_id: str = "default") -> None:
        await self._r.delete(self._refresh_key(user_id, device_id))

    async def revoke_all_refresh_tokens(self, user_id: str) -> int:
        """Remove all refresh tokens for a user across all devices."""
        pattern = f"{self._PFX_REFRESH}:{user_id}:*"
        keys = []
        async for key in self._r.scan_iter(pattern, count=50):
            keys.append(key)
        if keys:
            return await self._r.delete(*keys)
        return 0

    # ── Session (profile snapshot) ────────────────────────────────────────────

    async def store_session(self, user_id: str, payload: dict) -> None:
        """Cache user profile snapshot to avoid DB hits on every request."""
        import json
        key = f"{self._PFX_SESSION}:{user_id}"
        await self._r.set(key, json.dumps(payload, default=str), ex=self.SESSION_TTL_SECONDS)

    async def get_session(self, user_id: str) -> Optional[dict]:
        import json
        raw = await self._r.get(f"{self._PFX_SESSION}:{user_id}")
        if not raw:
            return None
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)

    async def delete_session(self, user_id: str) -> None:
        await self._r.delete(f"{self._PFX_SESSION}:{user_id}")

    async def refresh_session_ttl(self, user_id: str) -> None:
        await self._r.expire(f"{self._PFX_SESSION}:{user_id}", self.SESSION_TTL_SECONDS)

    # ── Login attempt throttling ──────────────────────────────────────────────

    def _attempts_key(self, identifier: str) -> str:
        return f"{self._PFX_ATTEMPTS}:{identifier}"

    async def record_failed_attempt(self, identifier: str) -> int:
        """Increment failed login counter. Returns new count."""
        key = self._attempts_key(identifier)
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.LOGIN_WINDOW_SECONDS, nx=True)
        results = await pipe.execute()
        return results[0]

    async def get_failed_attempts(self, identifier: str) -> int:
        raw = await self._r.get(self._attempts_key(identifier))
        return int(raw) if raw else 0

    async def is_login_blocked(self, identifier: str) -> bool:
        return (await self.get_failed_attempts(identifier)) >= self.LOGIN_MAX_ATTEMPTS

    async def clear_failed_attempts(self, identifier: str) -> None:
        await self._r.delete(self._attempts_key(identifier))

    async def get_block_ttl(self, identifier: str) -> int:
        """Return seconds until the block expires."""
        return max(0, await self._r.ttl(self._attempts_key(identifier)))

    # ── FCM device tokens ─────────────────────────────────────────────────────

    def _fcm_key(self, user_id: str, device_id: str) -> str:
        return f"{self._PFX_FCM}:{user_id}:{device_id}"

    async def store_fcm_token(
        self, user_id: str, device_id: str, fcm_token: str
    ) -> None:
        key = self._fcm_key(user_id, device_id)
        await self._r.set(key, fcm_token, ex=self.SESSION_TTL_SECONDS)

    async def get_fcm_token(self, user_id: str, device_id: str) -> Optional[str]:
        raw = await self._r.get(self._fcm_key(user_id, device_id))
        if not raw:
            return None
        return raw.decode() if isinstance(raw, bytes) else raw

    async def get_all_fcm_tokens(self, user_id: str) -> list[str]:
        """Retrieve all device FCM tokens for a user (for broadcast push)."""
        pattern = f"{self._PFX_FCM}:{user_id}:*"
        tokens = []
        async for key in self._r.scan_iter(pattern, count=20):
            raw = await self._r.get(key)
            if raw:
                tokens.append(raw.decode() if isinstance(raw, bytes) else raw)
        return tokens

    async def delete_fcm_token(self, user_id: str, device_id: str) -> None:
        await self._r.delete(self._fcm_key(user_id, device_id))
