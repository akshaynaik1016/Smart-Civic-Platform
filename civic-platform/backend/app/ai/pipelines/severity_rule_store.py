"""
SeverityRuleStore
==================
Allows municipal admins to retune severity thresholds at runtime, without a
code deploy. Rules are stored in Redis (JSON), with the hard-coded values in
app/ai/config.py serving as the fallback default for any category that
hasn't been customised.

This matters operationally: after a model goes live, an admin might observe
that "garbage" is being over-flagged as critical and want to raise the
high_max threshold from 0.30 to 0.40 — that should be a settings change,
not a pull request.

Redis key: ai:severity_rules:{category}     (no TTL — persists until changed)
Redis key: ai:severity_rules:_meta           (last_updated_by, last_updated_at)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.ai.config import SEVERITY_RULES, SeverityRule, IssueClass

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "ai:severity_rules"


# ─── Pydantic wire format ─────────────────────────────────────────────────────

class SeverityRuleOverride(BaseModel):
    """
    Admin-supplied override for one category's severity thresholds.

    area_low_max:    fraction of image area — at/below this → "low"
    area_medium_max: at/below this → "medium" (must be > area_low_max)
    area_high_max:   at/below this → "high"; above → "critical"
    count_bonus_every: every N extra same-class detections bumps severity +1 level
    """
    area_low_max:      float = Field(gt=0, lt=1)
    area_medium_max:   float = Field(gt=0, lt=1)
    area_high_max:     float = Field(gt=0, lt=1)
    count_bonus_every: int   = Field(default=3, ge=1, le=20)

    @field_validator("area_medium_max")
    @classmethod
    def _medium_above_low(cls, v: float, info) -> float:
        low = info.data.get("area_low_max")
        if low is not None and v <= low:
            raise ValueError("area_medium_max must be greater than area_low_max")
        return v

    @field_validator("area_high_max")
    @classmethod
    def _high_above_medium(cls, v: float, info) -> float:
        medium = info.data.get("area_medium_max")
        if medium is not None and v <= medium:
            raise ValueError("area_high_max must be greater than area_medium_max")
        return v

    def to_severity_rule(self) -> SeverityRule:
        return SeverityRule(
            area_thresholds=(self.area_low_max, self.area_medium_max, self.area_high_max),
            count_bonus_every=self.count_bonus_every,
        )

    @classmethod
    def from_severity_rule(cls, rule: SeverityRule) -> "SeverityRuleOverride":
        low, medium, high = rule.area_thresholds
        return cls(
            area_low_max=low, area_medium_max=medium, area_high_max=high,
            count_bonus_every=rule.count_bonus_every,
        )


class SeverityRuleSet(BaseModel):
    """Full ruleset response — all 8 categories plus metadata."""
    rules: dict[str, SeverityRuleOverride]
    customised_categories: list[str] = Field(default_factory=list)
    last_updated_by: Optional[str] = None
    last_updated_at: Optional[str] = None


# ─── Store ────────────────────────────────────────────────────────────────────

class SeverityRuleStore:
    """
    Redis-backed override store with graceful fallback to the hard-coded
    defaults in app/ai/config.py. SeverityEngine should call get_active_rules()
    once per request rather than reading SEVERITY_RULES directly, so that
    admin overrides take effect immediately.
    """

    def __init__(self, redis) -> None:
        self._r = redis

    def _key(self, category: str) -> str:
        return f"{_REDIS_PREFIX}:{category}"

    def _meta_key(self) -> str:
        return f"{_REDIS_PREFIX}:_meta"

    async def get_active_rules(self) -> dict[str, SeverityRule]:
        """
        Return the effective ruleset: defaults overlaid with any admin
        customisations found in Redis. This is what SeverityEngine consumes.
        """
        merged = dict(SEVERITY_RULES)   # start from hard-coded defaults

        try:
            for category in [c.value for c in IssueClass]:
                raw = await self._r.get(self._key(category))
                if raw:
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    override = SeverityRuleOverride(**data)
                    merged[category] = override.to_severity_rule()
        except Exception as exc:
            logger.warning("SeverityRuleStore.get_active_rules fell back to defaults: %s", exc)
            return dict(SEVERITY_RULES)

        return merged

    async def get_full_ruleset(self) -> SeverityRuleSet:
        """Return all rules (defaults + overrides) plus metadata, for the admin UI."""
        active = await self.get_active_rules()
        customised: list[str] = []

        try:
            for category in [c.value for c in IssueClass]:
                if await self._r.exists(self._key(category)):
                    customised.append(category)

            meta_raw = await self._r.get(self._meta_key())
            meta = json.loads(meta_raw.decode() if isinstance(meta_raw, bytes) else meta_raw) if meta_raw else {}
        except Exception as exc:
            logger.warning("SeverityRuleStore.get_full_ruleset metadata lookup failed: %s", exc)
            meta = {}

        return SeverityRuleSet(
            rules={
                cat: SeverityRuleOverride.from_severity_rule(rule)
                for cat, rule in active.items()
            },
            customised_categories=customised,
            last_updated_by=meta.get("updated_by"),
            last_updated_at=meta.get("updated_at"),
        )

    async def set_override(
        self,
        category: str,
        override: SeverityRuleOverride,
        updated_by: str,
    ) -> None:
        """Persist an admin override for one category."""
        if category not in [c.value for c in IssueClass]:
            raise ValueError(f"Unknown issue category: '{category}'")

        await self._r.set(self._key(category), override.model_dump_json())
        await self._r.set(
            self._meta_key(),
            json.dumps({
                "updated_by": updated_by,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "category":   category,
            }),
        )
        logger.info(
            "Severity rule override set for '%s' by %s: %s",
            category, updated_by, override.model_dump(),
        )

    async def reset_category(self, category: str, updated_by: str) -> None:
        """Remove an override, reverting that category to the hard-coded default."""
        await self._r.delete(self._key(category))
        await self._r.set(
            self._meta_key(),
            json.dumps({
                "updated_by": updated_by,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "category":   category,
                "action":     "reset",
            }),
        )
        logger.info("Severity rule for '%s' reset to default by %s", category, updated_by)

    async def reset_all(self, updated_by: str) -> None:
        """Clear all overrides — revert the entire platform to default rules."""
        for category in [c.value for c in IssueClass]:
            await self._r.delete(self._key(category))
        await self._r.set(
            self._meta_key(),
            json.dumps({
                "updated_by": updated_by,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "action":     "reset_all",
            }),
        )
        logger.info("All severity rules reset to defaults by %s", updated_by)
