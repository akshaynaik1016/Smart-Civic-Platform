"""
AI module configuration.

Centralises everything the detection pipeline needs to know about:
  • the 8 civic issue classes the YOLOv8 model was trained on
  • per-class severity heuristics (object size, count thresholds)
  • confidence and NMS thresholds
  • inference device selection (CPU/GPU)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.core.config import settings


class IssueClass(str, Enum):
    """Must match the order the YOLOv8 model was trained on (class index = enum order)."""
    POTHOLE             = "pothole"
    GARBAGE             = "garbage"
    WATER_LEAKAGE        = "water_leakage"
    OPEN_MANHOLE         = "open_manhole"
    BROKEN_STREETLIGHT   = "broken_streetlight"
    FALLEN_TREE          = "fallen_tree"
    DAMAGED_ROAD_SIGN    = "damaged_road_sign"
    ILLEGAL_DUMPING      = "illegal_dumping"


# Index → class name, exactly as exported in data.yaml during training
CLASS_NAMES: list[str] = [c.value for c in IssueClass]
CLASS_INDEX: dict[str, int] = {name: i for i, name in enumerate(CLASS_NAMES)}


@dataclass(frozen=True)
class SeverityRule:
    """
    Defines how a detected object's bounding-box area (relative to the full
    image) and detection count map to a severity bucket for one class.

    area_thresholds: (low_max, medium_max, high_max) as fraction of image area.
                      Anything above high_max → critical.
    count_bonus:      severity bumps up one level per N additional detections
                       of the same class in the same image.
    """
    area_thresholds: tuple[float, float, float]
    count_bonus_every: int = 3


# Tuned heuristics per category — calibrated against sample civic imagery.
SEVERITY_RULES: dict[str, SeverityRule] = {
    IssueClass.POTHOLE.value:            SeverityRule((0.02, 0.06, 0.14)),
    IssueClass.GARBAGE.value:            SeverityRule((0.05, 0.15, 0.30), count_bonus_every=2),
    IssueClass.WATER_LEAKAGE.value:      SeverityRule((0.01, 0.04, 0.10)),
    IssueClass.OPEN_MANHOLE.value:       SeverityRule((0.005, 0.015, 0.04)),   # small area, high risk
    IssueClass.BROKEN_STREETLIGHT.value: SeverityRule((0.01, 0.03, 0.08)),
    IssueClass.FALLEN_TREE.value:        SeverityRule((0.08, 0.20, 0.40)),
    IssueClass.DAMAGED_ROAD_SIGN.value:  SeverityRule((0.01, 0.03, 0.07)),
    IssueClass.ILLEGAL_DUMPING.value:    SeverityRule((0.06, 0.18, 0.35), count_bonus_every=2),
}

# Classes that are inherently higher-risk regardless of size (safety hazards)
INTRINSIC_HIGH_RISK: set[str] = {
    IssueClass.OPEN_MANHOLE.value,
    IssueClass.WATER_LEAKAGE.value,
}


@dataclass(frozen=True)
class AIConfig:
    model_path:            str   = settings.YOLO_MODEL_PATH
    confidence_threshold:  float = settings.YOLO_CONFIDENCE_THRESHOLD
    iou_threshold:         float = 0.45          # NMS overlap threshold
    max_detections:        int   = 20
    inference_image_size:  int   = 640           # YOLOv8 standard input size
    device:                str   = "cpu"          # overridden at runtime if CUDA available

    # Duplicate detection
    duplicate_radius_metres: float = settings.DUPLICATE_RADIUS_METRES
    duplicate_image_similarity_threshold: float = settings.DUPLICATE_IMAGE_SIMILARITY_THRESHOLD
    duplicate_time_window_days: int = 30

    # Description generator
    description_max_length: int = 280


ai_config = AIConfig()
