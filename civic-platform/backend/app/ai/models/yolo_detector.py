"""
YOLOv8Detector
==============
Wraps Ultralytics YOLOv8 for civic-issue object detection.

Responsibilities:
  • Lazy, singleton model loading (loaded once per process, reused across requests)
  • Preprocessing (EXIF rotation fix, RGB conversion)
  • Running inference and converting raw results into typed Detection objects
  • Selecting device (CUDA if available, else CPU)
  • Graceful fallback when the model file is missing (returns empty detections
    with a warning rather than crashing the API)

This class is intentionally synchronous internally (Ultralytics is sync);
the calling service runs it in a thread pool to avoid blocking the event loop.
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Optional

from app.ai.config import ai_config, CLASS_NAMES
from app.ai.schemas import BoundingBox, Detection, DetectionResult

logger = logging.getLogger(__name__)


class YOLOv8Detector:
    """Singleton-style wrapper around an Ultralytics YOLO model."""

    _instance: Optional["YOLOv8Detector"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialised", False):
            return
        self._model = None
        self._device = "cpu"
        self._model_loaded = False
        self._load_error: Optional[str] = None
        self._initialised = True
        self._load_model()

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        model_path = Path(ai_config.model_path)

        if not model_path.exists():
            self._load_error = (
                f"YOLOv8 model file not found at '{model_path}'. "
                "Detection will return empty results until a trained model "
                "is placed at this path."
            )
            logger.warning(self._load_error)
            return

        try:
            import torch
            from ultralytics import YOLO

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = YOLO(str(model_path))
            self._model.to(self._device)
            self._model_loaded = True
            logger.info(
                "YOLOv8 model loaded: %s (device=%s, classes=%d)",
                model_path, self._device, len(CLASS_NAMES),
            )
        except Exception as exc:
            self._load_error = f"Failed to load YOLOv8 model: {exc}"
            logger.error(self._load_error)

    @property
    def is_ready(self) -> bool:
        return self._model_loaded

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # ── Preprocessing ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_image(image_bytes: bytes):
        """Open image bytes, apply EXIF orientation fix, return PIL Image + (w,h)."""
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)   # respect camera rotation metadata
        img = img.convert("RGB")
        return img, img.size  # (width, height)

    # ── Inference ─────────────────────────────────────────────────────────────

    def detect(self, image_bytes: bytes) -> DetectionResult:
        """
        Run object detection on raw image bytes.
        Returns a DetectionResult — empty (not an exception) if the model
        isn't loaded or no objects are found above the confidence threshold.
        """
        start = time.perf_counter()

        try:
            image, (width, height) = self._load_image(image_bytes)
        except Exception as exc:
            logger.error("Failed to decode image for detection: %s", exc)
            return DetectionResult(inference_time_ms=0)

        if not self._model_loaded:
            # Graceful degradation — citizen can still submit, just without AI tagging
            return DetectionResult(
                image_width=width,
                image_height=height,
                inference_time_ms=int((time.perf_counter() - start) * 1000),
            )

        try:
            results = self._model.predict(
                source=image,
                conf=ai_config.confidence_threshold,
                iou=ai_config.iou_threshold,
                imgsz=ai_config.inference_image_size,
                max_det=ai_config.max_detections,
                device=self._device,
                verbose=False,
            )
        except Exception as exc:
            logger.error("YOLOv8 inference failed: %s", exc)
            return DetectionResult(
                image_width=width,
                image_height=height,
                inference_time_ms=int((time.perf_counter() - start) * 1000),
            )

        detections = self._parse_results(results, width, height)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        primary_label, primary_conf = self._select_primary(detections)

        return DetectionResult(
            detections=detections,
            primary_category=primary_label,
            primary_confidence=primary_conf,
            inference_time_ms=elapsed_ms,
            model_name="yolov8n-civic",
            model_version=self._model_version(),
            image_width=width,
            image_height=height,
        )

    # ── Result parsing ────────────────────────────────────────────────────────

    def _parse_results(self, results, img_w: int, img_h: int) -> list[Detection]:
        """Convert Ultralytics Results object into normalised Detection list."""
        detections: list[Detection] = []

        if not results:
            return detections

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return detections

        names = result.names if hasattr(result, "names") else {
            i: name for i, name in enumerate(CLASS_NAMES)
        }

        for box in boxes:
            try:
                cls_idx = int(box.cls.item())
                conf    = float(box.conf.item())
                label   = names.get(cls_idx, f"class_{cls_idx}")

                xyxy = box.xyxy[0].tolist()   # [x1, y1, x2, y2] in pixels
                x1, y1, x2, y2 = xyxy

                bbox = BoundingBox(
                    x1=max(0.0, min(1.0, x1 / img_w)),
                    y1=max(0.0, min(1.0, y1 / img_h)),
                    x2=max(0.0, min(1.0, x2 / img_w)),
                    y2=max(0.0, min(1.0, y2 / img_h)),
                )
                detections.append(Detection(label=label, confidence=conf, bbox=bbox))
            except Exception as exc:
                logger.warning("Skipping malformed detection box: %s", exc)
                continue

        return detections

    @staticmethod
    def _select_primary(detections: list[Detection]) -> tuple[Optional[str], float]:
        """Pick the highest-confidence detection as the complaint's primary category."""
        if not detections:
            return None, 0.0
        best = max(detections, key=lambda d: d.confidence)
        return best.label, best.confidence

    def _model_version(self) -> str:
        path = Path(ai_config.model_path)
        return path.stem or "v1.0.0"

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        return {
            "model_loaded": self._model_loaded,
            "device":       self._device,
            "model_path":   ai_config.model_path,
            "classes":      CLASS_NAMES,
            "error":        self._load_error,
        }


# Module-level singleton accessor
_detector_instance: Optional[YOLOv8Detector] = None


def get_detector() -> YOLOv8Detector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = YOLOv8Detector()
    return _detector_instance
