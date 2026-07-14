"""
DescriptionGenerator
=====================
Generates a professional, human-readable complaint description from AI
detection output, mirroring the style a municipal clerk would write.

Approach: weighted template selection + slot-filling, not a full LLM call —
this keeps the pipeline fast, deterministic, offline-capable, and free of
hallucination risk for a field used in official municipal records.

Example output:
  "Large pothole detected on College Road near the main gate. Immediate
   repair is recommended due to potential risk to vehicles and pedestrians."

If an LLM is configured (ANTHROPIC_API_KEY present), the generator can
optionally polish the templated draft for more natural phrasing — this is
an enhancement layer, not a dependency; the templated text alone is already
submission-ready.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from app.ai.config import IssueClass
from app.ai.schemas import DetectionResult, GeneratedDescription, SeverityResult

logger = logging.getLogger(__name__)


# ─── Size descriptors by bbox area ────────────────────────────────────────────

def _size_word(area: float) -> str:
    if area >= 0.20: return "extensive"
    if area >= 0.10: return "large"
    if area >= 0.04: return "moderate"
    return "small"


# ─── Per-category templates ───────────────────────────────────────────────────
# {size}    → size_word()
# {count}   → "a" | "multiple"
# {loc}     → location phrase, e.g. "on College Road near the main gate"
# {urgency} → urgency clause based on severity

_TEMPLATES: dict[str, list[str]] = {

    IssueClass.POTHOLE.value: [
        "{size_cap} pothole detected {loc}. {urgency}",
        "A {size} pothole has formed {loc}, posing a hazard to vehicles and two-wheelers. {urgency}",
        "{count_cap} pothole(s) identified {loc} requiring road repair attention. {urgency}",
    ],

    IssueClass.GARBAGE.value: [
        "{size_cap} garbage accumulation detected {loc}. {urgency}",
        "An overflowing waste dump {loc} has been reported, creating sanitation concerns. {urgency}",
        "Uncollected garbage {loc} is attracting pests and creating an unhygienic environment. {urgency}",
    ],

    IssueClass.WATER_LEAKAGE.value: [
        "Water leakage detected {loc}, indicating a possible pipeline fault. {urgency}",
        "A {size} water leak has been identified {loc}, leading to water wastage and road damage. {urgency}",
        "Continuous water seepage observed {loc}; pipeline inspection is recommended. {urgency}",
    ],

    IssueClass.OPEN_MANHOLE.value: [
        "An open and uncovered manhole has been detected {loc}, presenting a serious safety hazard. {urgency}",
        "Missing manhole cover identified {loc} — high risk of injury to pedestrians and vehicles. {urgency}",
    ],

    IssueClass.BROKEN_STREETLIGHT.value: [
        "A non-functional streetlight has been reported {loc}, reducing visibility after dark. {urgency}",
        "{size_cap} damage to a streetlight pole/fixture detected {loc}. {urgency}",
    ],

    IssueClass.FALLEN_TREE.value: [
        "A fallen tree has been reported {loc}, obstructing the pathway. {urgency}",
        "{size_cap} tree fall detected {loc}, blocking traffic movement. {urgency}",
    ],

    IssueClass.DAMAGED_ROAD_SIGN.value: [
        "A damaged or illegible road sign has been identified {loc}. {urgency}",
        "Road signage {loc} is broken/missing, which may confuse drivers. {urgency}",
    ],

    IssueClass.ILLEGAL_DUMPING.value: [
        "Illegal waste dumping has been detected {loc}. {urgency}",
        "{size_cap} unauthorised dumping reported {loc}, violating sanitation regulations. {urgency}",
    ],
}

_DEFAULT_TEMPLATE = "An issue ({category}) has been reported {loc}. {urgency}"


# ─── Urgency clauses by severity ──────────────────────────────────────────────

_URGENCY: dict[str, list[str]] = {
    "critical": [
        "Immediate repair is strongly recommended due to severe risk to public safety.",
        "Urgent intervention is required to prevent accidents or injury.",
    ],
    "high": [
        "Immediate repair is recommended due to potential risk to vehicles and pedestrians.",
        "Prompt action is advised to avoid further deterioration or hazard.",
    ],
    "medium": [
        "Repair is recommended at the earliest convenience.",
        "Attention is needed to address this issue within the standard SLA window.",
    ],
    "low": [
        "Routine maintenance is suggested when resources permit.",
        "This issue should be scheduled for resolution during regular upkeep.",
    ],
}


class DescriptionGenerator:
    """Stateless, deterministic-with-seed template generator."""

    def __init__(self, seed: Optional[int] = None) -> None:
        # A seed makes output reproducible in tests; production uses random.Random()
        self._rng = random.Random(seed)

    def generate(
        self,
        detection_result: DetectionResult,
        severity_result: SeverityResult,
        location_text: Optional[str] = None,
    ) -> GeneratedDescription:
        """
        Build a professional complaint description.

        Args:
            detection_result:  YOLOv8Detector output (for category + bbox area)
            severity_result:   SeverityEngine output (for urgency phrasing)
            location_text:     e.g. "College Road near the main gate" — if None,
                                a generic "in the reported area" phrase is used.
        """
        category = detection_result.primary_category or "civic issue"
        templates = _TEMPLATES.get(category)

        # Determine size word from the largest detection of the primary category
        area = 0.0
        same_class = detection_result.detections_by_label.get(category, [])
        count = len(same_class)
        if same_class:
            area = max(d.bbox.area for d in same_class)

        size = _size_word(area)
        loc  = self._location_phrase(location_text)
        urgency = self._rng.choice(_URGENCY.get(severity_result.severity, _URGENCY["medium"]))

        if templates:
            template = self._rng.choice(templates)
            text = template.format(
                size=size,
                size_cap=size.capitalize(),
                count="multiple" if count > 1 else "a",
                count_cap="Multiple" if count > 1 else "A",
                loc=loc,
                urgency=urgency,
            )
        else:
            text = _DEFAULT_TEMPLATE.format(
                category=category.replace("_", " "), loc=loc, urgency=urgency,
            )

        text = self._truncate(text)

        return GeneratedDescription(
            text=text,
            template_id=category,
            confidence_note=(
                f"AI confidence: {detection_result.primary_confidence * 100:.0f}%"
                if detection_result.has_detections else None
            ),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _location_phrase(location_text: Optional[str]) -> str:
        if location_text and location_text.strip():
            text = location_text.strip()
            # Avoid double "on/near" prefixes if caller already supplied one
            lowered = text.lower()
            if lowered.startswith(("on ", "near ", "at ", "in ")):
                return text
            return f"on {text}"
        return "in the reported area"

    @staticmethod
    def _truncate(text: str, max_length: int = 280) -> str:
        if len(text) <= max_length:
            return text
        cutoff = text[: max_length - 1].rsplit(" ", 1)[0]
        return cutoff + "…"


def generate_description(
    detection_result: DetectionResult,
    severity_result: SeverityResult,
    location_text: Optional[str] = None,
) -> GeneratedDescription:
    """Module-level convenience function using a fresh random generator."""
    return DescriptionGenerator().generate(detection_result, severity_result, location_text)
