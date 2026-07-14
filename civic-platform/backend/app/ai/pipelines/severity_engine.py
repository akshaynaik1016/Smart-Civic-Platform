"""
SeverityEngine
==============
Predicts severity (low / medium / high / critical) for a detected civic issue.

Inputs combined:
  1. Object size      — bounding-box area as a fraction of the full image
  2. Detection count   — multiple instances of the same issue in one photo
  3. Intrinsic risk    — some categories (open manhole, water leakage) are
                          dangerous even when small
  4. Historical data   — if this location/category has a history of repeat
                          reports, severity is nudged up (recurring problem)

Returns a SeverityResult with a human-readable reasoning string so officers
can see *why* the AI assigned a given severity — important for trust and
for manual override decisions.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.ai.config import INTRINSIC_HIGH_RISK, SEVERITY_RULES, SeverityRule
from app.ai.schemas import Detection, DetectionResult, SeverityResult

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = ["low", "medium", "high", "critical"]


class SeverityEngine:
    """Stateless — all historical context is passed in by the caller."""

    def predict(
        self,
        detection_result: DetectionResult,
        historical_repeat_count: int = 0,
    ) -> SeverityResult:
        """
        Predict severity for the primary detected category.

        Args:
            detection_result:         Output of YOLOv8Detector.detect()
            historical_repeat_count:  Number of prior complaints at the same
                                       location+category in the last 90 days.
                                       Used to bump up severity for recurring
                                       unresolved issues.
        """
        if not detection_result.has_detections:
            return SeverityResult(
                severity="medium",
                confidence=0.3,
                reasoning="No AI detections available — defaulted to medium severity "
                          "pending manual review.",
            )

        primary_label = detection_result.primary_category
        same_class_detections = detection_result.detections_by_label.get(primary_label, [])

        rule = SEVERITY_RULES.get(primary_label)
        if rule is None:
            return SeverityResult(
                severity="medium",
                confidence=0.4,
                reasoning=f"No severity rule defined for category '{primary_label}'.",
            )

        # 1. Base severity from bounding-box area of the largest instance
        largest = max(same_class_detections, key=lambda d: d.bbox.area)
        area_level, area_idx = self._severity_from_area(largest.bbox.area, rule)

        # 2. Count bonus — many instances of the same issue (e.g. 6 garbage piles)
        count_bumps = self._count_bonus(len(same_class_detections), rule)

        # 3. Intrinsic risk bump — dangerous categories regardless of size
        intrinsic_bump = 1 if primary_label in INTRINSIC_HIGH_RISK else 0

        # 4. Historical recurrence bump — unresolved recurring issue
        history_bump = self._history_bonus(historical_repeat_count)

        final_idx = min(
            area_idx + count_bumps + intrinsic_bump + history_bump,
            len(_SEVERITY_ORDER) - 1,
        )
        final_severity = _SEVERITY_ORDER[final_idx]

        # Confidence: blend detection confidence with how decisive the area signal was
        confidence = round(
            min(0.99, largest.confidence * 0.7 + 0.3), 4
        )

        reasoning = self._build_reasoning(
            primary_label, largest, area_level, count_bumps,
            intrinsic_bump, history_bump, historical_repeat_count, final_severity,
        )

        return SeverityResult(
            severity=final_severity,
            confidence=confidence,
            reasoning=reasoning,
            contributing_factors={
                "bbox_area_pct":         round(largest.bbox.area * 100, 2),
                "detection_count":       len(same_class_detections),
                "intrinsic_risk_bump":   float(intrinsic_bump),
                "history_bump":          float(history_bump),
                "detection_confidence":  largest.confidence,
            },
        )

    # ── Helper calculations ───────────────────────────────────────────────────

    @staticmethod
    def _severity_from_area(area: float, rule: SeverityRule) -> tuple[str, int]:
        low_max, medium_max, high_max = rule.area_thresholds
        if area <= low_max:
            return "low", 0
        if area <= medium_max:
            return "medium", 1
        if area <= high_max:
            return "high", 2
        return "critical", 3

    @staticmethod
    def _count_bonus(count: int, rule: SeverityRule) -> int:
        """Every `count_bonus_every` extra detections bumps severity by 1 level."""
        if count <= 1:
            return 0
        extra = count - 1
        return min(extra // rule.count_bonus_every, 2)   # cap bump at +2 levels

    @staticmethod
    def _history_bonus(repeat_count: int) -> int:
        """3+ unresolved repeats at the same spot → escalate."""
        if repeat_count >= 5:
            return 2
        if repeat_count >= 3:
            return 1
        return 0

    @staticmethod
    def _build_reasoning(
        label: str,
        detection: Detection,
        area_level: str,
        count_bumps: int,
        intrinsic_bump: int,
        history_bump: int,
        repeat_count: int,
        final: str,
    ) -> str:
        parts = [
            f"Detected '{label}' covering {detection.bbox.area * 100:.1f}% of the image "
            f"(base severity: {area_level})."
        ]
        if count_bumps:
            parts.append(f"Multiple instances detected — severity raised by {count_bumps} level(s).")
        if intrinsic_bump:
            parts.append("Category is an intrinsic safety hazard — severity raised.")
        if history_bump:
            parts.append(
                f"{repeat_count} prior reports at this location/category in the last 90 days — "
                "treated as a recurring unresolved issue."
            )
        parts.append(f"Final severity: {final}.")
        return " ".join(parts)
