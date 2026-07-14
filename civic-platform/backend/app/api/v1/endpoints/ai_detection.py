"""
AI Detection API
=================
POST   /ai/analyze                — run full pipeline on an uploaded image (citizen flow)
GET    /ai/health                 — model load status, device, configured classes
POST   /ai/complaints/{id}/reanalyze — re-run AI on a complaint's primary image (officer/admin)
GET    /ai/complaints/{id}/analysis  — fetch the stored AIAnalysis row
"""

from __future__ import annotations

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.v1.dependencies.auth import CurrentUser, DbDep, OfficerRequired
from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.repositories.complaint_repository import ComplaintRepository
from app.schemas.schemas import MessageResponse
from app.services.storage_service import StorageService, sniff_image_type

router = APIRouter(prefix="/ai", tags=["AI Detection"])


# ── Dependency helpers ─────────────────────────────────────────────────────────

async def _get_orchestrator(db: DbDep):
    from app.ai.orchestration_service import AIOrchestrationService
    repo = ComplaintRepository(db)
    return AIOrchestrationService(db=db, repo=repo, storage=StorageService())


OrchestratorDep = Annotated[object, Depends(_get_orchestrator)]


def _validate_upload(content: bytes, declared_type: str) -> None:
    if len(content) > settings.max_upload_bytes:
        raise BadRequestError(f"Image exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit.")
    real_type = sniff_image_type(content)
    if real_type is None:
        raise BadRequestError("File does not appear to be a valid JPEG, PNG, or WebP image.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/analyze",
    summary="Run AI detection on a candidate complaint photo before submission",
    status_code=status.HTTP_200_OK,
)
async def analyze_image(
    current_user: CurrentUser,
    orchestrator: OrchestratorDep,
    image:        UploadFile = File(..., description="Photo of the civic issue"),
    latitude:     float      = Form(...),
    longitude:    float      = Form(...),
    category_hint: Optional[str] = Form(
    None,
    description="Citizen-selected category, used as fallback",
    ),
    address: Optional[str] = Form(
        None,
        description="Human-readable address for description text",
    ),
) -> dict:
    """
    Pre-submission analysis. The mobile app calls this right after the camera
    capture / gallery pick, *before* the complaint record is created, so the
    citizen can review the AI's category, severity, and generated description
    on the "AI Detection Result" screen.

    No complaint_id exists yet at this point, so no AIAnalysis row is persisted —
    that happens once the complaint is actually submitted via the complaints API,
    which calls AIOrchestrationService.analyse_complaint_image with the real
    complaint_id and image_id.
    """
    content = await image.read()
    _validate_upload(content, image.content_type or "")

    from app.ai.models.yolo_detector import get_detector
    from app.ai.pipelines.severity_engine import SeverityEngine
    from app.ai.pipelines.description_generator import DescriptionGenerator
    import asyncio

    detector = get_detector()
    loop = asyncio.get_event_loop()
    detection = await loop.run_in_executor(None, detector.detect, content)

    severity = SeverityEngine().predict(detection, historical_repeat_count=0)
    description = DescriptionGenerator().generate(detection, severity, address)

    return {
        "category":        detection.primary_category or category_hint,
        "confidence":       detection.primary_confidence,
        "severity":        severity.severity,
        "severity_reasoning": severity.reasoning,
        "description":     description.text,
        "bounding_boxes":  [
            {"label": d.label, "confidence": d.confidence, "bbox": d.bbox.as_list()}
            for d in detection.detections
        ],
        "inference_time_ms": detection.inference_time_ms,
        "model_version":    detection.model_version,
        "ai_available":     detector.is_ready,
    }


@router.get(
    "/health",
    summary="AI model health check",
)
async def ai_health(orchestrator: OrchestratorDep) -> dict:
    """Returns model load status — used by the monitoring dashboard and /health rollup."""
    return orchestrator.health_check()


@router.post(
    "/complaints/{complaint_id}/reanalyze",
    response_model=MessageResponse,
    summary="Re-run AI analysis on an existing complaint (officer/admin)",
)
async def reanalyze_complaint(
    complaint_id: str,
    officer:       OfficerRequired,
    orchestrator:  OrchestratorDep,
    db:            DbDep,
) -> dict:
    """
    Useful when a citizen disputes the AI's original classification, or when
    a newer model version has been deployed and historical complaints should
    be re-scored.
    """
    repo = ComplaintRepository(db)
    complaint = await repo.get_by_id(complaint_id, detail=True)
    if not complaint:
        raise NotFoundError("Complaint", complaint_id)

    images = await repo.get_images(complaint_id)
    primary = next((i for i in images if i.is_primary), images[0] if images else None)
    if not primary:
        raise BadRequestError("Complaint has no images to analyze.")

    storage = StorageService()
    # Re-fetch image bytes via presigned URL → download, or local path read
    import httpx
    url = await storage.presigned_url(primary.s3_key)
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=15.0) if url.startswith("http") else None
    image_bytes = resp.content if resp else b""

    await orchestrator.analyse_complaint_image(
        complaint_id=complaint_id,
        image_bytes=image_bytes,
        latitude=float(complaint.latitude),
        longitude=float(complaint.longitude),
        category_hint=complaint.category,
        location_text=complaint.address,
        image_id=str(primary.id),
    )
    await db.commit()

    return {"message": "Complaint re-analyzed successfully."}


@router.get(
    "/complaints/{complaint_id}/analysis",
    summary="Fetch the stored AI analysis result for a complaint",
)
async def get_analysis(
    complaint_id: str,
    current_user:  CurrentUser,
    db:            DbDep,
) -> dict:
    repo = ComplaintRepository(db)
    analysis = await repo.get_ai_analysis(complaint_id)
    if not analysis:
        raise NotFoundError("AI analysis", complaint_id)

    return {
        "detected_category":      analysis.detected_category,
        "confidence_score":       float(analysis.confidence_score),
        "severity_predicted":     analysis.severity_predicted,
        "severity_confidence":    float(analysis.severity_confidence) if analysis.severity_confidence else None,
        "generated_description":  analysis.generated_description,
        "is_duplicate":           analysis.is_duplicate,
        "similar_complaint_ids":  analysis.similar_complaint_ids,
        "similarity_score":       float(analysis.similarity_score) if analysis.similarity_score else None,
        "model_name":             analysis.model_name,
        "model_version":          analysis.model_version,
        "inference_time_ms":      analysis.inference_time_ms,
        "bounding_boxes":         analysis.bounding_boxes,
        "created_at":             analysis.created_at.isoformat(),
    }
