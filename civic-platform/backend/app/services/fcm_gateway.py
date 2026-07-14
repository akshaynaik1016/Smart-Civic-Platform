"""
FCMGateway
==========
Firebase Cloud Messaging delivery layer.

Responsibilities:
  • Lazy-initialize the Firebase Admin SDK once per process
  • Send single-device push notifications
  • Batch-send to multiple tokens in one FCM call (up to 500 per batch)
  • Send to FCM topics (e.g. "ward_9_officers")
  • Subscribe / unsubscribe tokens to topics
  • Parse FCM error codes and classify as retryable vs permanent failures
  • Gracefully degrade when Firebase credentials are absent (dev mode)

FCM error code reference:
  UNREGISTERED / INVALID_ARGUMENT → permanent failure, remove token
  QUOTA_EXCEEDED / INTERNAL / UNAVAILABLE → retry with backoff
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class FCMErrorKind(str, Enum):
    """Classification of FCM errors to decide retry vs discard."""
    PERMANENT  = "permanent"   # bad token — remove from DB
    RETRYABLE  = "retryable"   # rate-limit or server error — retry later
    UNKNOWN    = "unknown"


# Map FCM error codes → retry decision
_FCM_ERROR_MAP: dict[str, FCMErrorKind] = {
    "UNREGISTERED":      FCMErrorKind.PERMANENT,
    "INVALID_ARGUMENT":  FCMErrorKind.PERMANENT,
    "SENDER_ID_MISMATCH":FCMErrorKind.PERMANENT,
    "QUOTA_EXCEEDED":    FCMErrorKind.RETRYABLE,
    "UNAVAILABLE":       FCMErrorKind.RETRYABLE,
    "INTERNAL":          FCMErrorKind.RETRYABLE,
    "MESSAGE_RATE_EXCEEDED": FCMErrorKind.RETRYABLE,
}


@dataclass
class FCMResult:
    success:        bool
    message_id:     Optional[str] = None
    error_code:     Optional[str] = None
    error_kind:     FCMErrorKind  = FCMErrorKind.UNKNOWN
    raw_error:      Optional[str] = None

    @property
    def is_permanent_failure(self) -> bool:
        return self.error_kind == FCMErrorKind.PERMANENT

    @property
    def is_retryable_failure(self) -> bool:
        return not self.success and self.error_kind == FCMErrorKind.RETRYABLE


@dataclass
class FCMBatchResult:
    total:     int
    successes: int
    failures:  int
    results:   list[FCMResult] = field(default_factory=list)
    # Tokens that should be removed from the DB (UNREGISTERED etc.)
    invalid_tokens: list[str] = field(default_factory=list)


class FCMGateway:
    """Thin async wrapper around firebase_admin.messaging."""

    def __init__(self) -> None:
        self._initialized = False
        self._messaging   = None
        self._enabled     = bool(settings.FIREBASE_CREDENTIALS_JSON)

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init(self) -> bool:
        """Lazy-initialize Firebase Admin SDK. Returns True if available."""
        if self._initialized:
            return self._messaging is not None

        self._initialized = True

        if not self._enabled:
            logger.info("FCM not configured — push notifications disabled (dev mode)")
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            if not firebase_admin._apps:
                creds_raw = settings.FIREBASE_CREDENTIALS_JSON.strip()

                # Support both JSON string and file path
                if creds_raw.startswith("{"):
                    cred_dict = json.loads(creds_raw)
                    cred = credentials.Certificate(cred_dict)
                else:
                    cred = credentials.Certificate(creds_raw)

                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized")

            self._messaging = messaging
            return True

        except Exception as exc:
            logger.error("FCM initialization failed: %s", exc)
            self._messaging = None
            return False

    # ── Single-device push ────────────────────────────────────────────────────

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        image_url: Optional[str] = None,
        priority: str = "high",
        badge: Optional[int] = None,
        sound: str = "default",
    ) -> FCMResult:
        """
        Send a push notification to a single device token.

        Returns FCMResult. Never raises — all errors are captured.
        """
        if not self._init():
            return FCMResult(success=False, error_code="FCM_DISABLED",
                             error_kind=FCMErrorKind.UNKNOWN)
        try:
            import asyncio

            msg = self._build_message(
                token=token,
                title=title,
                body=body,
                data=data,
                image_url=image_url,
                priority=priority,
                badge=badge,
                sound=sound,
            )
            loop = asyncio.get_event_loop()
            msg_id = await loop.run_in_executor(None, self._messaging.send, msg)
            return FCMResult(success=True, message_id=msg_id)

        except Exception as exc:
            return self._parse_error(exc)

    # ── Batch push ────────────────────────────────────────────────────────────

    async def send_multicast(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict] = None,
        image_url: Optional[str] = None,
        priority: str = "high",
    ) -> FCMBatchResult:
        """
        Send the same message to multiple device tokens (up to 500 per call).
        Automatically splits larger batches.
        """
        if not tokens:
            return FCMBatchResult(total=0, successes=0, failures=0)

        if not self._init():
            return FCMBatchResult(
                total=len(tokens), successes=0, failures=len(tokens),
                results=[FCMResult(success=False, error_code="FCM_DISABLED") for _ in tokens],
            )

        # FCM batch limit is 500
        BATCH = 500
        combined = FCMBatchResult(total=len(tokens), successes=0, failures=0)

        for chunk_start in range(0, len(tokens), BATCH):
            chunk = tokens[chunk_start : chunk_start + BATCH]
            result = await self._send_multicast_chunk(
                chunk, title, body, data, image_url, priority
            )
            combined.successes    += result.successes
            combined.failures     += result.failures
            combined.results      += result.results
            combined.invalid_tokens += result.invalid_tokens

        return combined

    async def _send_multicast_chunk(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict],
        image_url: Optional[str],
        priority: str,
    ) -> FCMBatchResult:
        import asyncio

        try:
            msg = self._messaging.MulticastMessage(
                tokens=tokens,
                notification=self._messaging.Notification(
                    title=title, body=body, image=image_url,
                ),
                android=self._messaging.AndroidConfig(priority=priority),
                apns=self._messaging.APNSConfig(
                    payload=self._messaging.APNSPayload(
                        aps=self._messaging.Aps(sound="default"),
                    )
                ),
                data={k: str(v) for k, v in (data or {}).items()},
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self._messaging.send_each_for_multicast, msg
            )

            results   = []
            invalid   = []
            successes = 0
            failures  = 0

            for i, resp in enumerate(response.responses):
                if resp.success:
                    results.append(FCMResult(success=True, message_id=resp.message_id))
                    successes += 1
                else:
                    parsed = self._parse_error(resp.exception)
                    results.append(parsed)
                    failures += 1
                    if parsed.is_permanent_failure:
                        invalid.append(tokens[i])

            return FCMBatchResult(
                total=len(tokens), successes=successes,
                failures=failures, results=results, invalid_tokens=invalid,
            )

        except Exception as exc:
            err = self._parse_error(exc)
            return FCMBatchResult(
                total=len(tokens), successes=0, failures=len(tokens),
                results=[err] * len(tokens),
            )

    # ── Topic messaging ───────────────────────────────────────────────────────

    async def send_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> FCMResult:
        """
        Send to an FCM topic (e.g. 'admin_alerts', 'ward_9').
        All devices subscribed to the topic receive the message.
        """
        if not self._init():
            return FCMResult(success=False, error_code="FCM_DISABLED")

        try:
            import asyncio

            msg = self._messaging.Message(
                topic=topic,
                notification=self._messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
            )
            loop = asyncio.get_event_loop()
            msg_id = await loop.run_in_executor(None, self._messaging.send, msg)
            return FCMResult(success=True, message_id=msg_id)

        except Exception as exc:
            return self._parse_error(exc)

    # ── Topic subscription ────────────────────────────────────────────────────

    async def subscribe_to_topic(self, tokens: list[str], topic: str) -> bool:
        if not self._init() or not tokens:
            return False
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._messaging.subscribe_to_topic(tokens, topic),
            )
            logger.debug("FCM subscribe: %d success, %d fail",
                         response.success_count, response.failure_count)
            return response.success_count > 0

        except Exception as exc:
            logger.warning("FCM subscribe failed: %s", exc)
            return False

    async def unsubscribe_from_topic(self, tokens: list[str], topic: str) -> bool:
        if not self._init() or not tokens:
            return False
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._messaging.unsubscribe_from_topic(tokens, topic),
            )
            return True

        except Exception as exc:
            logger.warning("FCM unsubscribe failed: %s", exc)
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_message(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict],
        image_url: Optional[str],
        priority: str,
        badge: Optional[int],
        sound: str,
    ):
        apns_payload = self._messaging.APNSPayload(
            aps=self._messaging.Aps(
                sound=sound,
                badge=badge,
            )
        )
        return self._messaging.Message(
            token=token,
            notification=self._messaging.Notification(
                title=title,
                body=body,
                image=image_url,
            ),
            android=self._messaging.AndroidConfig(
                priority=priority,
                notification=self._messaging.AndroidNotification(
                    sound=sound,
                    default_sound=True,
                    default_vibrate_timings=True,
                ),
            ),
            apns=self._messaging.APNSConfig(payload=apns_payload),
            data={k: str(v) for k, v in (data or {}).items()},
        )

    @staticmethod
    def _parse_error(exc: Exception) -> FCMResult:
        msg = str(exc)
        # Firebase SDK wraps errors in FirebaseError with error_code attribute
        code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
        code_str = str(code).upper() if code else msg.upper()

        # Extract the short code from dotted names like "messaging/unregistered"
        if "/" in code_str:
            code_str = code_str.split("/")[-1]

        kind = _FCM_ERROR_MAP.get(code_str, FCMErrorKind.UNKNOWN)
        logger.warning("FCM error [%s]: %s", code_str, msg)
        return FCMResult(
            success=False,
            error_code=code_str,
            error_kind=kind,
            raw_error=msg,
        )

    @property
    def is_available(self) -> bool:
        return self._init()


# Singleton — one per process
fcm_gateway = FCMGateway()
