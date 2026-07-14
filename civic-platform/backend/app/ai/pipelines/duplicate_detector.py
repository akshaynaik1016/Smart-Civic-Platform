"""
DuplicateDetector
==================
Identifies whether a newly submitted complaint is a duplicate of an existing,
unresolved complaint.

Signals combined (weighted):
  • Geo proximity     (40%) — Haversine distance between coordinates
  • Image similarity  (40%) — perceptual hash (pHash) Hamming distance
  • Category match    (20%) — same detected issue category

A weighted score above the configured threshold flags the new complaint as a
duplicate and links it to the best-matching parent.

Image similarity uses perceptual hashing (pHash) rather than exact SHA-256
matching, since two photos of the *same* pothole taken from slightly
different angles will have different bytes but similar visual content.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from app.ai.config import ai_config
from app.ai.schemas import DuplicateCandidate, DuplicateCheckResult

logger = logging.getLogger(__name__)

_EARTH_RADIUS_M = 6_371_000.0


@dataclass
class ExistingComplaint:
    """Minimal shape the detector needs — populated by the calling service
    from the ComplaintRepository, so this module has no DB dependency."""
    id:               str
    complaint_number: str
    category:         str
    latitude:         float
    longitude:        float
    image_phash:      Optional[str]   # perceptual hash of the primary image
    created_at_days_ago: float


class DuplicateDetector:
    """Stateless — operates purely on data passed in by the caller."""

    def __init__(
        self,
        radius_metres: float = ai_config.duplicate_radius_metres,
        similarity_threshold: float = ai_config.duplicate_image_similarity_threshold,
        time_window_days: int = ai_config.duplicate_time_window_days,
    ) -> None:
        self._radius_m   = radius_metres
        self._sim_thresh  = similarity_threshold
        self._window_days = time_window_days

    # ── Public API ────────────────────────────────────────────────────────────

    def check(
        self,
        new_lat: float,
        new_lng: float,
        new_category: str,
        new_image_bytes: Optional[bytes],
        candidates: Sequence[ExistingComplaint],
    ) -> DuplicateCheckResult:
        """
        Compare a new complaint against a pre-filtered list of nearby existing
        complaints (the caller should already have queried by bounding box /
        Redis GEO search before calling this — this method does the precise
        scoring, not the initial spatial filter).
        """
        new_phash = self._compute_phash(new_image_bytes) if new_image_bytes else None

        scored: list[DuplicateCandidate] = []

        for c in candidates:
            if c.created_at_days_ago > self._window_days:
                continue   # too old — not a meaningful duplicate signal

            distance = self._haversine_metres(new_lat, new_lng, c.latitude, c.longitude)
            if distance > self._radius_m:
                continue   # outside search radius — skip entirely

            image_sim = self._phash_similarity(new_phash, c.image_phash)
            category_match = c.category == new_category

            score = self._weighted_score(distance, image_sim, category_match)

            scored.append(DuplicateCandidate(
                complaint_id=c.id,
                complaint_number=c.complaint_number,
                distance_metres=round(distance, 1),
                image_similarity=round(image_sim, 4),
                overall_score=round(score, 4),
                category_match=category_match,
            ))

        scored.sort(key=lambda x: x.overall_score, reverse=True)

        best = scored[0] if scored else None
        is_duplicate = bool(best and best.overall_score >= self._sim_thresh)

        return DuplicateCheckResult(
            is_duplicate=is_duplicate,
            best_match=best if is_duplicate else None,
            all_candidates=scored[:10],   # cap returned candidates
            checked_radius_metres=self._radius_m,
        )

    # ── Perceptual hashing ────────────────────────────────────────────────────

    @staticmethod
    def _compute_phash(image_bytes: bytes) -> Optional[str]:
        """
        Compute a perceptual hash (pHash) of an image.
        Returns a hex string, or None if hashing fails.
        """
        try:
            import io

            import imagehash
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            phash = imagehash.phash(img, hash_size=16)
            return str(phash)
        except ImportError:
            logger.warning(
                "imagehash library not installed — falling back to average hash via PIL only."
            )
            return DuplicateDetector._fallback_hash(image_bytes)
        except Exception as exc:
            logger.warning("pHash computation failed: %s", exc)
            return None

    @staticmethod
    def _fallback_hash(image_bytes: bytes) -> Optional[str]:
        """Crude fallback: downsample to 8×8 grayscale and threshold against mean."""
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((8, 8))
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            bits = "".join("1" if p > avg else "0" for p in pixels)
            return f"{int(bits, 2):016x}"
        except Exception:
            return None

    @staticmethod
    def _phash_similarity(hash_a: Optional[str], hash_b: Optional[str]) -> float:
        """
        Convert Hamming distance between two pHash hex strings into a
        0–1 similarity score. Returns 0.0 if either hash is missing.
        """
        if not hash_a or not hash_b:
            return 0.0
        try:
            int_a = int(hash_a, 16)
            int_b = int(hash_b, 16)
            xor = int_a ^ int_b
            hamming = bin(xor).count("1")
            max_bits = max(len(hash_a), len(hash_b)) * 4   # hex digit = 4 bits
            similarity = 1.0 - (hamming / max_bits)
            return max(0.0, similarity)
        except ValueError:
            return 0.0

    # ── Geo distance ──────────────────────────────────────────────────────────

    @staticmethod
    def _haversine_metres(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Great-circle distance between two lat/lng points, in metres."""
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lng2 - lng1)

        a = (
            math.sin(d_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return _EARTH_RADIUS_M * c

    # ── Score blending ────────────────────────────────────────────────────────

    def _weighted_score(
        self,
        distance_metres: float,
        image_similarity: float,
        category_match: bool,
    ) -> float:
        """
        Combine the three signals into one 0–1 confidence score.
        Distance is converted to a proximity score (1.0 at distance=0,
        decaying linearly to 0.0 at the configured radius).
        """
        proximity_score = max(0.0, 1.0 - (distance_metres / self._radius_m))
        category_score  = 1.0 if category_match else 0.0

        return (
            proximity_score * 0.40
            + image_similarity * 0.40
            + category_score * 0.20
        )

    # ── Public hashing helper (used by upload pipeline) ───────────────────────

    def compute_image_hash(self, image_bytes: bytes) -> Optional[str]:
        """Expose pHash computation for the service layer to store on upload."""
        return self._compute_phash(image_bytes)
