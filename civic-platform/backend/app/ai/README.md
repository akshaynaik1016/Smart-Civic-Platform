# AI Detection Module

YOLOv8-based object detection pipeline for the Smart Civic Intelligence Platform.

## Pipeline stages

```
image bytes
    │
    ▼
YOLOv8Detector            (app/ai/models/yolo_detector.py)
    │  → DetectionResult: list[Detection], primary_category, primary_confidence
    ▼
SeverityEngine             (app/ai/pipelines/severity_engine.py)
    │  → SeverityResult: severity, confidence, reasoning
    ▼
DuplicateDetector          (app/ai/pipelines/duplicate_detector.py)
    │  → DuplicateCheckResult: is_duplicate, best_match, all_candidates
    ▼
DescriptionGenerator       (app/ai/pipelines/description_generator.py)
    │  → GeneratedDescription: text, template_id
    ▼
AIOrchestrationService      (app/ai/orchestration_service.py)
       persists AIAnalysis row + updates Complaint.ai_* fields
```

## Detected classes (must match training label order)

| Index | Class                | SLA weight | Intrinsic risk |
|-------|-----------------------|-----------:|:--------------:|
| 0     | pothole               | medium     |                 |
| 1     | garbage               | medium     |                 |
| 2     | water_leakage         | high       | ✓               |
| 3     | open_manhole          | critical   | ✓               |
| 4     | broken_streetlight    | medium     |                 |
| 5     | fallen_tree           | high       |                 |
| 6     | damaged_road_sign     | medium     |                 |
| 7     | illegal_dumping       | medium     |                 |

## Model file

Place a trained YOLOv8 `.pt` weights file at the path configured by
`YOLO_MODEL_PATH` (default `models/yolov8n-civic.pt`). If the file is
missing, the detector logs a warning and returns empty results rather
than crashing — citizens can still submit complaints with manually
selected categories.

### Training your own model

```bash
pip install ultralytics
yolo train data=civic_dataset.yaml model=yolov8n.pt epochs=100 imgsz=640
```

`civic_dataset.yaml` must list the 8 classes in the exact order shown
above (see `app/ai/config.py::CLASS_NAMES`).

## Severity calculation

Severity blends four signals (see `severity_engine.py`):

1. **Bounding-box area** relative to image — calibrated per-class thresholds
2. **Detection count** — multiple instances bump severity up
3. **Intrinsic risk** — open manholes / water leaks escalate even when small
4. **Historical recurrence** — 3+ unresolved reports at the same spot in 90 days

## Duplicate detection

Combines three weighted signals into one 0–1 score:

- Geo proximity (40%) — Haversine distance, decays linearly to 0 at `DUPLICATE_RADIUS_METRES`
- Image similarity (40%) — perceptual hash (pHash) Hamming distance
- Category match (20%) — binary

Threshold: `DUPLICATE_IMAGE_SIMILARITY_THRESHOLD` (default 0.85)

## Description generation

Template + slot-filling, not an LLM call — deterministic, offline, zero
hallucination risk for official municipal records. ~20 templates across
8 categories, varied by severity-driven urgency clause and detected size.

## Configuration (.env)

```
YOLO_MODEL_PATH=models/yolov8n-civic.pt
YOLO_CONFIDENCE_THRESHOLD=0.75
DUPLICATE_RADIUS_METRES=500.0
DUPLICATE_IMAGE_SIMILARITY_THRESHOLD=0.85
```

## Dependencies

```
ultralytics==8.2.18
torch==2.3.0
torchvision==0.18.0
opencv-python-headless==4.9.0.80
Pillow==10.3.0
ImageHash==4.3.1
```

## Running tests

```bash
pytest tests/ai/test_ai_pipeline.py -v
```

Tests use hand-built `DetectionResult` fixtures — no trained model file
is required to run the test suite.
