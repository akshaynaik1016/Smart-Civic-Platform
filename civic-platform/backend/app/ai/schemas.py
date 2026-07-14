"""
Typed data structures passed between AI pipeline stages.

Detection → Severity → Duplicate Check → Description Generation
all communicate through these schemas so each stage is independently testable.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalised bounding box — coordinates as fractions of image width/height (0–1)."""
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    def as_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]


class Detection(BaseModel):
    """One detected object instance."""
    label:       str
    confidence:  float = Field(ge=0, le=1)
    bbox:        BoundingBox


class DetectionResult(BaseModel):
    """Full output of the YOLOv8 inference stage for one image."""
    detections:        list[Detection] = Field(default_factory=list)
    primary_category:  Optional[str]   = None     # highest-confidence class overall
    primary_confidence: float          = 0.0
    inference_time_ms: int             = 0
    model_name:        str             = "yolov8n"
    model_version:     str             = "v1.0.0"
    image_width:        Optional[int]  = None
    image_height:       Optional[int]  = None

    @property
    def has_detections(self) -> bool:
        return len(self.detections) > 0

    @property
    def detections_by_label(self) -> dict[str, list[Detection]]:
        out: dict[str, list[Detection]] = {}
        for d in self.detections:
            out.setdefault(d.label, []).append(d)
        return out


class SeverityResult(BaseModel):
    """Output of the severity-prediction stage."""
    severity:           str    # low | medium | high | critical
    confidence:         float = Field(ge=0, le=1)
    reasoning:           str   = ""     # human-readable explanation
    contributing_factors: dict[str, float] = Field(default_factory=dict)


class DuplicateCandidate(BaseModel):
    """One potential duplicate match against an existing complaint."""
    complaint_id:     str
    complaint_number: str
    distance_metres:  float
    image_similarity: float = Field(ge=0, le=1)
    overall_score:    float = Field(ge=0, le=1)
    category_match:   bool


class DuplicateCheckResult(BaseModel):
    """Output of the duplicate-detection stage."""
    is_duplicate:        bool
    best_match:          Optional[DuplicateCandidate] = None
    all_candidates:      list[DuplicateCandidate]     = Field(default_factory=list)
    checked_radius_metres: float = 0.0


class GeneratedDescription(BaseModel):
    """Output of the NLP description generator."""
    text:        str
    template_id: str
    confidence_note: Optional[str] = None    # e.g. "AI confidence: 93%"


class FullAnalysisResult(BaseModel):
    """The complete bundle returned by the AI orchestration pipeline."""
    detection:   DetectionResult
    severity:    SeverityResult
    duplicate:   DuplicateCheckResult
    description: GeneratedDescription
    image_hash:  str
    total_pipeline_time_ms: int = 0
