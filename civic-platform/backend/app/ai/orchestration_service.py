"""
AIOrchestrationService
=======================
The single entry point the rest of the backend calls to run the full AI
pipeline on a newly uploaded complaint image:

    image bytes
        → YOLOv8Detector            (object detection)
        → SeverityEngine            (severity prediction)
        → DuplicateDetector         (duplicate check against nearby complaints)
        → DescriptionGenerator      (professional description text)
        → AIAnalysis row persisted  (via ComplaintRepository)

Heavy CPU/GPU work (YOLOv8 inference) is offloaded to a thread pool so the
async event loop is never blocked. Each stage is independently testable —
this class only orchestrates and persists.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import ai_config
from app.ai.models.yolo_detector import get_detector
from app.ai.pipelines.description_generator import DescriptionGenerator
from app.ai.pipelines.duplicate_detector import DuplicateDetector, ExistingComplaint
from app.ai.pipelines.severity_engine import SeverityEngine
from app.ai.schemas import FullAnalysisResult
from app.repositories.complaint_repository import ComplaintRepository
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class AIOrchestrationService:
    def __init__(
        self,
        db:      AsyncSession,
        repo:    ComplaintRepository,
        storage: Optional[StorageService] = None,
    ) -> None:
        self._db      = db
        self._repo    = repo
        self._storage = storage or StorageService()

        self._severity_engine    = SeverityEngine()
        self._duplicate_detector = DuplicateDetector()
        self._description_gen    = DescriptionGenerator()

    # ── Public API ────────────────────────────────────────────────────────────

    async def analyse_complaint_image(
        self,
        complaint_id: str,
        image_bytes: bytes,
        latitude: float,
        longitude: float,
        category_hint: Optional[str] = None,
        location_text: Optional[str] = None,
        image_id: Optional[str] = None,
    ) -> FullAnalysisResult:
        """
        Run the complete AI pipeline and persist an AIAnalysis row.

        Args:
            complaint_id:   the complaint this analysis belongs to
            image_bytes:    raw uploaded image
            latitude/longitude: complaint location, used for duplicate search
            category_hint:  citizen-selected category (used if AI confidence is low)
            location_text:  human address string, for description generation
            image_id:       the ComplaintImage row ID, if already uploaded
        """
        pipeline_start = time.perf_counter()

        # 1. Detection (CPU-bound — run in thread pool)
        detector = get_detector()
        loop = asyncio.get_event_loop()
        detection_result = await loop.run_in_executor(
            None, detector.detect, image_bytes
        )

        # Fall back to citizen-selected category if AI found nothing
        if not detection_result.has_detections and category_hint:
            logger.info(
                "No AI detections for complaint %s — falling back to citizen category '%s'",
                complaint_id, category_hint,
            )

        # 2. Historical repeat count for this location+category (90-day window)
        repeat_count = await self._get_historical_repeat_count(
            latitude, longitude,
            detection_result.primary_category or category_hint or "other",
        )

        # 3. Severity prediction
        severity_result = self._severity_engine.predict(
            detection_result, historical_repeat_count=repeat_count,
        )

        # 4. Duplicate detection
        nearby = await self._get_nearby_complaints_for_dup_check(
            latitude, longitude, complaint_id,
        )
        duplicate_result = await loop.run_in_executor(
            None,
            self._duplicate_detector.check,
            latitude, longitude,
            detection_result.primary_category or category_hint or "other",
            image_bytes,
            nearby,
        )

        # 5. Description generation (cheap — runs inline)
        description_result = self._description_gen.generate(
            detection_result, severity_result, location_text,
        )

        # 6. Image hash for storage / future duplicate lookups
        image_hash = StorageService.compute_hash(image_bytes)

        total_ms = int((time.perf_counter() - pipeline_start) * 1000)

        result = FullAnalysisResult(
            detection=detection_result,
            severity=severity_result,
            duplicate=duplicate_result,
            description=description_result,
            image_hash=image_hash,
            total_pipeline_time_ms=total_ms,
        )

        # 7. Persist AIAnalysis row
        await self._persist_analysis(complaint_id, image_id, result)

        logger.info(
            "AI pipeline complete for complaint %s in %dms "
            "(category=%s, severity=%s, duplicate=%s)",
            complaint_id, total_ms,
            detection_result.primary_category, severity_result.severity,
            duplicate_result.is_duplicate,
        )

        return result

    # ── Historical context ───────────────────────────────────────────────────

    async def _get_historical_repeat_count(
        self, lat: float, lng: float, category: str,
    ) -> int:
        """Count unresolved complaints of the same category near this location
        in the last 90 days — used to detect recurring problem spots."""
        try:
            nearby = await self._repo.find_nearby(
                lat, lng, radius_km=0.1, limit=50, open_only=False,
            )
            from datetime import datetime, timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            return sum(
                1 for c in nearby
                if c.category == category and c.created_at >= cutoff
            )
        except Exception as exc:
            logger.warning("Historical repeat-count lookup failed: %s", exc)
            return 0

    async def _get_nearby_complaints_for_dup_check(
        self, lat: float, lng: float, exclude_complaint_id: str,
    ) -> list[ExistingComplaint]:
        """
        Fetch nearby open complaints (excluding the one currently being
        analysed) and adapt them into the lightweight ExistingComplaint
        shape the DuplicateDetector expects.
        """
        try:
            from datetime import datetime, timezone

            nearby = await self._repo.find_nearby(
                lat, lng,
                radius_km=ai_config.duplicate_radius_metres / 1000.0,
                limit=30,
                open_only=True,
            )
            now = datetime.now(timezone.utc)
            out: list[ExistingComplaint] = []
            for c in nearby:
                if str(c.id) == str(exclude_complaint_id):
                    continue
                phash = await self._get_primary_image_phash(str(c.id))
                age_days = (now - c.created_at).total_seconds() / 86_400
                out.append(ExistingComplaint(
                    id=str(c.id),
                    complaint_number=c.complaint_number,
                    category=c.category,
                    latitude=float(c.latitude),
                    longitude=float(c.longitude),
                    image_phash=phash,
                    created_at_days_ago=age_days,
                ))
            return out
        except Exception as exc:
            logger.warning("Nearby-complaint lookup for duplicate check failed: %s", exc)
            return []

    async def _get_primary_image_phash(self, complaint_id: str) -> Optional[str]:
        """
        Look up the stored perceptual hash for a complaint's primary image.
        Stored as part of ComplaintImage.bounding_boxes JSONB sidecar data
        under the key '_phash' to avoid a schema migration.
        """
        try:
            images = await self._repo.get_images(complaint_id)
            for img in images:
                if img.is_primary and img.bounding_boxes:
                    return img.bounding_boxes.get("_phash")
        except Exception:
            pass
        return None

    # ── Persistence ───────────────────────────────────────────────────────────

    async def _persist_analysis(
        self,
        complaint_id: str,
        image_id: Optional[str],
        result: FullAnalysisResult,
    ) -> None:
        bboxes_payload = [
            {
                "label":      d.label,
                "confidence": d.confidence,
                "bbox":       d.bbox.as_list(),
            }
            for d in result.detection.detections
        ]

        await self._repo.save_ai_analysis(
            complaint_id=complaint_id,
            image_id=image_id,
            detected_category=result.detection.primary_category,
            confidence_score=result.detection.primary_confidence or 0.0,
            severity_predicted=result.severity.severity,
            severity_confidence=result.severity.confidence,
            bounding_boxes=bboxes_payload,
            generated_description=result.description.text,
            description_model="template-v1",
            duplicate_checked=True,
            is_duplicate=result.duplicate.is_duplicate,
            similar_complaint_ids=(
                [c.complaint_id for c in result.duplicate.all_candidates]
                if result.duplicate.all_candidates else None
            ),
            similarity_score=(
                result.duplicate.best_match.overall_score
                if result.duplicate.best_match else None
            ),
            model_name=result.detection.model_name,
            model_version=result.detection.model_version,
            inference_time_ms=result.detection.inference_time_ms,
            raw_output={
                "pipeline_time_ms": result.total_pipeline_time_ms,
                "severity_reasoning": result.severity.reasoning,
                "contributing_factors": result.severity.contributing_factors,
            },
            processing_status="completed",
        )

        # Update the complaint row itself with AI-derived fields
        from datetime import datetime, timezone

        await self._repo.update_fields(
            complaint_id,
            ai_description=result.description.text,
            ai_confidence=result.detection.primary_confidence or None,
            ai_processed_at=datetime.now(timezone.utc),
            ai_model_version=result.detection.model_version,
            severity=result.severity.severity,
        )

        # If the AI is confident enough that this is a duplicate, actually
        # execute the merge (support transfer, close child, notify citizen) —
        # not just flag it. Borderline candidates are left as-is for officer
        # review via DuplicateMergeService.get_pending_review_queue().
        if result.duplicate.is_duplicate and result.duplicate.best_match:
            await self._auto_merge_if_confident(
                complaint_id=complaint_id,
                parent_complaint_id=result.duplicate.best_match.complaint_id,
                similarity_score=result.duplicate.best_match.overall_score,
            )

    async def _auto_merge_if_confident(
        self,
        complaint_id: str,
        parent_complaint_id: str,
        similarity_score: float,
    ) -> None:
        """Delegate to DuplicateMergeService so the merge is a real,
        auditable, notified operation rather than a silent field write."""
        try:
            from app.ai.pipelines.duplicate_merge_service import DuplicateMergeService
            from app.services.audit_service import AuditService
            from app.services.notification_service import NotificationService

            child = await self._repo.get_by_id(complaint_id, detail=True)
            if not child:
                return

            merge_service = DuplicateMergeService(
                db=self._db,
                repo=self._repo,
                notifier=NotificationService(self._db),
                audit=AuditService(self._db),
            )
            await merge_service.auto_merge(
                child_complaint=child,
                parent_complaint_id=parent_complaint_id,
                similarity_score=similarity_score,
            )
        except Exception as exc:
            logger.error(
                "Auto-merge failed for complaint %s → %s: %s. "
                "Complaint will remain open for manual review.",
                complaint_id, parent_complaint_id, exc,
            )

    # ── Health check ──────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        return get_detector().health_check()
