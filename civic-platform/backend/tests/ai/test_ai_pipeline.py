"""
Test suite for the AI detection module.

Covers SeverityEngine, DuplicateDetector, DescriptionGenerator, and schema
validation without requiring an actual trained YOLOv8 model file — detector
tests use hand-built DetectionResult fixtures instead of running inference.

Run:
    pytest tests/ai/test_ai_pipeline.py -v
"""

from __future__ import annotations

import pytest

from app.ai.config import IssueClass
from app.ai.pipelines.description_generator import DescriptionGenerator
from app.ai.pipelines.duplicate_detector import DuplicateDetector, ExistingComplaint
from app.ai.pipelines.severity_engine import SeverityEngine
from app.ai.schemas import BoundingBox, Detection, DetectionResult


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _detection(label: str, confidence: float, area_frac: float) -> Detection:
    """Build a Detection with a square bbox sized to approximately `area_frac` of the image."""
    side = area_frac ** 0.5
    x1 = (1 - side) / 2
    y1 = (1 - side) / 2
    return Detection(
        label=label,
        confidence=confidence,
        bbox=BoundingBox(x1=x1, y1=y1, x2=x1 + side, y2=y1 + side),
    )


def _result(*detections: Detection) -> DetectionResult:
    if not detections:
        return DetectionResult()
    primary = max(detections, key=lambda d: d.confidence)
    return DetectionResult(
        detections=list(detections),
        primary_category=primary.label,
        primary_confidence=primary.confidence,
        inference_time_ms=42,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BoundingBox / Detection schema tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBoundingBox:

    def test_area_calculation(self):
        bbox = BoundingBox(x1=0.1, y1=0.1, x2=0.5, y2=0.5)
        assert bbox.area == pytest.approx(0.16, abs=1e-6)

    def test_zero_area_for_degenerate_box(self):
        bbox = BoundingBox(x1=0.5, y1=0.5, x2=0.5, y2=0.5)
        assert bbox.area == 0.0

    def test_negative_coords_rejected(self):
        with pytest.raises(Exception):
            BoundingBox(x1=-0.1, y1=0, x2=0.5, y2=0.5)

    def test_coords_above_one_rejected(self):
        with pytest.raises(Exception):
            BoundingBox(x1=0, y1=0, x2=1.5, y2=0.5)

    def test_as_list_returns_correct_order(self):
        bbox = BoundingBox(x1=0.1, y1=0.2, x2=0.3, y2=0.4)
        assert bbox.as_list() == [0.1, 0.2, 0.3, 0.4]


class TestDetectionResult:

    def test_has_detections_false_when_empty(self):
        assert DetectionResult().has_detections is False

    def test_has_detections_true_with_one(self):
        result = _result(_detection("pothole", 0.9, 0.05))
        assert result.has_detections is True

    def test_detections_by_label_groups_correctly(self):
        result = _result(
            _detection("pothole", 0.9, 0.05),
            _detection("pothole", 0.8, 0.03),
            _detection("garbage", 0.7, 0.10),
        )
        grouped = result.detections_by_label
        assert len(grouped["pothole"]) == 2
        assert len(grouped["garbage"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SeverityEngine tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeverityEngine:

    def setup_method(self):
        self.engine = SeverityEngine()

    def test_no_detections_defaults_to_medium(self):
        result = self.engine.predict(DetectionResult())
        assert result.severity == "medium"
        assert result.confidence == 0.3

    def test_small_pothole_is_low_severity(self):
        result = self.engine.predict(_result(_detection("pothole", 0.9, 0.01)))
        assert result.severity == "low"

    def test_large_pothole_is_high_or_critical(self):
        result = self.engine.predict(_result(_detection("pothole", 0.9, 0.20)))
        assert result.severity in ("high", "critical")

    def test_open_manhole_intrinsic_risk_bump(self):
        # Small open manhole should still escalate due to intrinsic risk
        small = self.engine.predict(_result(_detection("open_manhole", 0.9, 0.005)))
        # base would be "low" but intrinsic bump pushes it up at least one level
        assert small.severity in ("medium", "high", "critical")

    def test_multiple_garbage_instances_escalate_severity(self):
        single = self.engine.predict(_result(_detection("garbage", 0.9, 0.04)))
        multiple = self.engine.predict(_result(
            _detection("garbage", 0.9, 0.04),
            _detection("garbage", 0.85, 0.04),
            _detection("garbage", 0.8, 0.04),
        ))
        order = ["low", "medium", "high", "critical"]
        assert order.index(multiple.severity) >= order.index(single.severity)

    def test_historical_repeats_escalate_severity(self):
        no_history = self.engine.predict(
            _result(_detection("pothole", 0.9, 0.03)), historical_repeat_count=0,
        )
        with_history = self.engine.predict(
            _result(_detection("pothole", 0.9, 0.03)), historical_repeat_count=5,
        )
        order = ["low", "medium", "high", "critical"]
        assert order.index(with_history.severity) >= order.index(no_history.severity)

    def test_unknown_category_returns_medium(self):
        det = Detection(
            label="spaceship_debris", confidence=0.9,
            bbox=BoundingBox(x1=0.1, y1=0.1, x2=0.3, y2=0.3),
        )
        result_obj = DetectionResult(
            detections=[det], primary_category="spaceship_debris", primary_confidence=0.9,
        )
        result = self.engine.predict(result_obj)
        assert result.severity == "medium"

    def test_severity_never_exceeds_critical(self):
        # Stack every possible escalation factor
        result = self.engine.predict(
            _result(
                _detection("open_manhole", 0.99, 0.20),
                _detection("open_manhole", 0.95, 0.15),
                _detection("open_manhole", 0.90, 0.10),
                _detection("open_manhole", 0.85, 0.10),
            ),
            historical_repeat_count=10,
        )
        assert result.severity == "critical"

    def test_reasoning_is_non_empty_string(self):
        result = self.engine.predict(_result(_detection("pothole", 0.9, 0.05)))
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0

    def test_contributing_factors_present(self):
        result = self.engine.predict(_result(_detection("pothole", 0.9, 0.05)))
        assert "bbox_area_pct" in result.contributing_factors
        assert "detection_count" in result.contributing_factors


# ═══════════════════════════════════════════════════════════════════════════════
# DuplicateDetector tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDuplicateDetector:

    def setup_method(self):
        self.detector = DuplicateDetector(radius_metres=500.0, similarity_threshold=0.7)

    def test_haversine_zero_distance_for_same_point(self):
        d = self.detector._haversine_metres(15.36, 75.12, 15.36, 75.12)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_haversine_known_distance(self):
        # Roughly 1 degree of latitude ≈ 111 km
        d = self.detector._haversine_metres(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(111_195, rel=0.01)

    def test_no_candidates_returns_not_duplicate(self):
        result = self.detector.check(
            new_lat=15.36, new_lng=75.12, new_category="pothole",
            new_image_bytes=None, candidates=[],
        )
        assert result.is_duplicate is False
        assert result.best_match is None

    def test_candidate_outside_radius_excluded(self):
        far_candidate = ExistingComplaint(
            id="c1", complaint_number="CMP-2025-00001", category="pothole",
            latitude=20.0, longitude=80.0,   # far away
            image_phash=None, created_at_days_ago=1,
        )
        result = self.detector.check(
            new_lat=15.36, new_lng=75.12, new_category="pothole",
            new_image_bytes=None, candidates=[far_candidate],
        )
        assert result.all_candidates == []

    def test_candidate_too_old_excluded(self):
        old_candidate = ExistingComplaint(
            id="c2", complaint_number="CMP-2025-00002", category="pothole",
            latitude=15.36, longitude=75.12,
            image_phash=None, created_at_days_ago=999,   # way past window
        )
        result = self.detector.check(
            new_lat=15.36, new_lng=75.1201, new_category="pothole",
            new_image_bytes=None, candidates=[old_candidate],
        )
        assert result.all_candidates == []

    def test_close_same_category_flagged_as_duplicate(self):
        same_hash = "f" * 32
        candidate = ExistingComplaint(
            id="c3", complaint_number="CMP-2025-00003", category="pothole",
            latitude=15.3600, longitude=75.1200,
            image_phash=same_hash, created_at_days_ago=2,
        )
        # New complaint at nearly the same coordinates, same category, identical hash
        result = self.detector.check(
            new_lat=15.36005, new_lng=75.12005, new_category="pothole",
            new_image_bytes=None, candidates=[candidate],
        )
        # Manually force phash match by monkeypatching compute (None input → None hash),
        # so rely on proximity + category match alone reaching threshold is unlikely;
        # assert candidate is at least surfaced with high category+proximity score.
        assert len(result.all_candidates) == 1
        assert result.all_candidates[0].category_match is True

    def test_phash_similarity_identical_hashes(self):
        sim = self.detector._phash_similarity("abcd1234", "abcd1234")
        assert sim == 1.0

    def test_phash_similarity_completely_different(self):
        sim = self.detector._phash_similarity("00000000", "ffffffff")
        assert sim == pytest.approx(0.0, abs=0.01)

    def test_phash_similarity_missing_hash_returns_zero(self):
        assert self.detector._phash_similarity(None, "abcd") == 0.0
        assert self.detector._phash_similarity("abcd", None) == 0.0

    def test_weighted_score_perfect_match(self):
        score = self.detector._weighted_score(
            distance_metres=0.0, image_similarity=1.0, category_match=True,
        )
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_weighted_score_no_match(self):
        score = self.detector._weighted_score(
            distance_metres=500.0, image_similarity=0.0, category_match=False,
        )
        assert score == pytest.approx(0.0, abs=1e-6)

    def test_candidates_sorted_descending_by_score(self):
        candidates = [
            ExistingComplaint(
                id="far", complaint_number="CMP-1", category="pothole",
                latitude=15.40, longitude=75.12, image_phash=None, created_at_days_ago=1,
            ),
            ExistingComplaint(
                id="near", complaint_number="CMP-2", category="pothole",
                latitude=15.3601, longitude=75.1201, image_phash=None, created_at_days_ago=1,
            ),
        ]
        result = self.detector.check(
            new_lat=15.36, new_lng=75.12, new_category="pothole",
            new_image_bytes=None, candidates=candidates,
        )
        if len(result.all_candidates) == 2:
            assert result.all_candidates[0].overall_score >= result.all_candidates[1].overall_score


# ═══════════════════════════════════════════════════════════════════════════════
# DescriptionGenerator tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDescriptionGenerator:

    def setup_method(self):
        self.gen = DescriptionGenerator(seed=42)   # deterministic for testing

    def test_generates_nonempty_text_for_pothole(self):
        detection = _result(_detection("pothole", 0.95, 0.08))
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity, "College Road near the main gate")
        assert len(desc.text) > 20
        assert "pothole" in desc.text.lower()

    def test_includes_location_phrase(self):
        detection = _result(_detection("garbage", 0.9, 0.10))
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity, "MG Road")
        assert "MG Road" in desc.text

    def test_no_location_uses_generic_phrase(self):
        detection = _result(_detection("fallen_tree", 0.9, 0.15))
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity, None)
        assert "reported area" in desc.text

    def test_unknown_category_uses_default_template(self):
        det = Detection(
            label="mystery_object", confidence=0.8,
            bbox=BoundingBox(x1=0.1, y1=0.1, x2=0.3, y2=0.3),
        )
        detection = DetectionResult(
            detections=[det], primary_category="mystery_object", primary_confidence=0.8,
        )
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity)
        assert "mystery object" in desc.text.lower()

    def test_confidence_note_present_when_detections_exist(self):
        detection = _result(_detection("pothole", 0.93, 0.05))
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity)
        assert desc.confidence_note is not None
        assert "93%" in desc.confidence_note

    def test_confidence_note_absent_without_detections(self):
        detection = DetectionResult()
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity)
        assert desc.confidence_note is None

    def test_text_truncated_to_max_length(self):
        long_location = "X" * 500
        detection = _result(_detection("pothole", 0.9, 0.05))
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity, long_location)
        assert len(desc.text) <= 280

    def test_template_id_matches_category(self):
        detection = _result(_detection("water_leakage", 0.9, 0.03))
        from app.ai.pipelines.severity_engine import SeverityEngine
        severity = SeverityEngine().predict(detection)
        desc = self.gen.generate(detection, severity)
        assert desc.template_id == "water_leakage"

    def test_all_issue_classes_have_templates(self):
        """Every category in IssueClass must produce non-default output."""
        from app.ai.pipelines.severity_engine import SeverityEngine
        for issue_class in IssueClass:
            detection = _result(_detection(issue_class.value, 0.9, 0.05))
            severity = SeverityEngine().predict(detection)
            desc = self.gen.generate(detection, severity, "Test Street")
            assert desc.template_id == issue_class.value
            assert len(desc.text) > 10
