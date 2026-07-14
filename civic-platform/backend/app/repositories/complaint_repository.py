"""
ComplaintRepository
===================
Every database operation that touches complaints and related tables.
Pure data-access — no business logic, no HTTP concerns.

Tables owned:
  complaints · complaint_images · complaint_status_history
  complaint_supporters · ai_analysis · resolutions · categories
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, desc, asc, func, or_, select, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    AIAnalysis,
    Category,
    Complaint,
    ComplaintImage,
    ComplaintStatus,
    ComplaintStatusHistory,
    ComplaintSupporter,
    IssueCategory,
    Officer,
    Resolution,
    SeverityLevel,
    User,
)


# ─── eager-load option sets ─────────────────────────────────────────────────

_LIST_OPTIONS = [
    selectinload(Complaint.citizen),
    selectinload(Complaint.officer).selectinload(Officer.user),
    selectinload(Complaint.category_obj),
    selectinload(Complaint.images),
]

_DETAIL_OPTIONS = _LIST_OPTIONS + [
    selectinload(Complaint.status_history).selectinload(
        ComplaintStatusHistory.changed_by_user
    ),
    selectinload(Complaint.ai_analysis),
    selectinload(Complaint.resolution),
    selectinload(Complaint.supporters),
]


class ComplaintRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Sequence number ──────────────────────────────────────────────────────

    async def next_complaint_number(self) -> str:
        """Generate human-readable ID e.g. CMP-2025-04821."""
        result = await self._db.execute(
            text("SELECT nextval('complaint_seq')")
        )
        seq = result.scalar()
        year = datetime.now(timezone.utc).year
        return f"CMP-{year}-{seq:05d}"

    # ── Create ───────────────────────────────────────────────────────────────

    async def create(self, **kwargs) -> Complaint:
        complaint = Complaint(**kwargs)
        self._db.add(complaint)
        await self._db.flush()
        await self._db.refresh(complaint)
        return complaint

    # ── Single-row lookups ───────────────────────────────────────────────────

    async def get_by_id(
        self,
        complaint_id: str,
        *,
        detail: bool = False,
        include_deleted: bool = False,
    ) -> Optional[Complaint]:
        opts = _DETAIL_OPTIONS if detail else _LIST_OPTIONS
        q = (
            select(Complaint)
            .options(*opts)
            .where(Complaint.id == complaint_id)
        )
        if not include_deleted:
            q = q.where(Complaint.deleted_at.is_(None))
        result = await self._db.execute(q)
        return result.scalar_one_or_none()

    async def get_by_number(self, complaint_number: str) -> Optional[Complaint]:
        q = (
            select(Complaint)
            .options(*_DETAIL_OPTIONS)
            .where(
                Complaint.complaint_number == complaint_number,
                Complaint.deleted_at.is_(None),
            )
        )
        return (await self._db.execute(q)).scalar_one_or_none()

    # ── Paginated list ────────────────────────────────────────────────────────

    async def list_complaints(
        self,
        *,
        status: Optional[ComplaintStatus] = None,
        severity: Optional[SeverityLevel] = None,
        category: Optional[IssueCategory] = None,
        ward_id: Optional[int] = None,
        officer_id: Optional[str] = None,
        citizen_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        is_duplicate: Optional[bool] = None,
        sla_breached: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[Sequence[Complaint], int]:
        """Return (complaints, total_count)."""
        filters = [Complaint.deleted_at.is_(None)]

        if status:
            filters.append(Complaint.status == status)
        if severity:
            filters.append(Complaint.severity == severity)
        if category:
            filters.append(Complaint.category == category)
        if ward_id is not None:
            filters.append(Complaint.ward_id == ward_id)
        if officer_id:
            filters.append(Complaint.officer_id == officer_id)
        if citizen_id:
            filters.append(Complaint.citizen_id == citizen_id)
        if date_from:
            filters.append(Complaint.created_at >= date_from)
        if date_to:
            filters.append(Complaint.created_at <= date_to)
        if is_duplicate is not None:
            filters.append(Complaint.is_duplicate == is_duplicate)
        if sla_breached is not None:
            filters.append(Complaint.sla_breached == sla_breached)
        if search:
            term = f"%{search}%"
            filters.append(
                or_(
                    Complaint.title.ilike(term),
                    Complaint.description.ilike(term),
                    Complaint.complaint_number.ilike(term),
                    Complaint.address.ilike(term),
                )
            )

        total = (
            await self._db.execute(
                select(func.count()).where(and_(*filters))
            )
        ).scalar() or 0

        _sort_map = {
            "created_at":    Complaint.created_at,
            "updated_at":    Complaint.updated_at,
            "priority_score":Complaint.priority_score,
            "severity":      Complaint.severity,
            "status":        Complaint.status,
            "support_count": Complaint.support_count,
        }
        col = _sort_map.get(sort_by, Complaint.created_at)
        order = desc(col) if sort_order == "desc" else asc(col)

        rows = (
            await self._db.execute(
                select(Complaint)
                .options(*_LIST_OPTIONS)
                .where(and_(*filters))
                .order_by(order)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).scalars().all()

        return rows, total

    # ── Geo / nearby ─────────────────────────────────────────────────────────

    async def find_nearby(
        self,
        lat: float,
        lng: float,
        radius_km: float = 5.0,
        limit: int = 50,
        open_only: bool = True,
    ) -> Sequence[Complaint]:
        """
        Haversine-based nearby query using PostgreSQL.
        Requires PostGIS OR pure-SQL approximation.
        Falls back to bounding-box approximation when PostGIS is unavailable.
        """
        # 1° lat ≈ 111 km; 1° lng ≈ 111 km × cos(lat)
        import math as _m
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * _m.cos(_m.radians(lat)))

        filters = [
            Complaint.deleted_at.is_(None),
            Complaint.latitude.between(lat - lat_delta, lat + lat_delta),
            Complaint.longitude.between(lng - lng_delta, lng + lng_delta),
        ]
        if open_only:
            filters.append(
                Complaint.status.not_in([
                    ComplaintStatus.RESOLVED,
                    ComplaintStatus.VERIFIED,
                    ComplaintStatus.CLOSED,
                    ComplaintStatus.REJECTED,
                ])
            )

        rows = (
            await self._db.execute(
                select(Complaint)
                .options(*_LIST_OPTIONS)
                .where(and_(*filters))
                .order_by(Complaint.priority_score.desc())
                .limit(limit)
            )
        ).scalars().all()
        return rows

    # ── Update ───────────────────────────────────────────────────────────────

    async def update_fields(self, complaint_id: str, **kwargs) -> Optional[Complaint]:
        await self._db.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(**kwargs)
        )
        return await self.get_by_id(complaint_id, detail=True)

    async def update_status(
        self,
        complaint_id: str,
        new_status: ComplaintStatus,
        **extra_fields,
    ) -> Optional[Complaint]:
        values = {"status": new_status, **extra_fields}
        if new_status in (ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED):
            if "resolved_at" not in values:
                values["resolved_at"] = datetime.now(timezone.utc)
        return await self.update_fields(complaint_id, **values)

    async def assign_officer(
        self, complaint_id: str, officer_id: str
    ) -> Optional[Complaint]:
        return await self.update_fields(
            complaint_id,
            officer_id=officer_id,
            status=ComplaintStatus.ASSIGNED,
        )

    async def bulk_assign(
        self, complaint_ids: list[str], officer_id: str
    ) -> int:
        result = await self._db.execute(
            update(Complaint)
            .where(
                Complaint.id.in_(complaint_ids),
                Complaint.deleted_at.is_(None),
            )
            .values(
                officer_id=officer_id,
                status=ComplaintStatus.ASSIGNED,
            )
        )
        return result.rowcount

    async def soft_delete(self, complaint_id: str) -> None:
        await self._db.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )

    # ── Priority score ────────────────────────────────────────────────────────

    async def recalculate_priority(self, complaint_id: str) -> float:
        """
        Priority score (0–100) = severity_weight + sla_urgency + support_bonus.
        Stored on the complaint for cheap sorting.
        """
        c = await self.get_by_id(complaint_id)
        if not c:
            return 0.0

        sev_weights = {
            SeverityLevel.CRITICAL: 40,
            SeverityLevel.HIGH:     30,
            SeverityLevel.MEDIUM:   20,
            SeverityLevel.LOW:      10,
        }
        base = sev_weights.get(c.severity, 20)

        # SLA urgency: 0–30 based on how close to deadline
        sla_bonus = 0
        if c.sla_deadline:
            now = datetime.now(timezone.utc)
            hours_left = (c.sla_deadline - now).total_seconds() / 3600
            if hours_left < 0:
                sla_bonus = 30      # breached
            elif hours_left < 4:
                sla_bonus = 25
            elif hours_left < 12:
                sla_bonus = 15
            elif hours_left < 24:
                sla_bonus = 5

        # Support count bonus: up to 20 points
        support_bonus = min(c.support_count * 2, 20)

        # Duplicate penalty
        duplicate_penalty = 10 if c.is_duplicate else 0

        score = max(0.0, min(100.0, base + sla_bonus + support_bonus - duplicate_penalty))
        await self.update_fields(complaint_id, priority_score=score)
        return score

    # ── SLA management ────────────────────────────────────────────────────────

    async def mark_sla_breached(self, complaint_id: str) -> None:
        await self.update_fields(complaint_id, sla_breached=True)

    async def get_sla_at_risk(
        self, hours_threshold: int = 4
    ) -> Sequence[Complaint]:
        """Return open complaints whose SLA deadline is within `hours_threshold` hours."""
        from sqlalchemy import text as sqla_text
        cutoff = text(f"NOW() + INTERVAL '{hours_threshold} hours'")
        q = (
            select(Complaint)
            .options(*_LIST_OPTIONS)
            .where(
                Complaint.deleted_at.is_(None),
                Complaint.sla_deadline.is_not(None),
                Complaint.sla_deadline <= cutoff,
                Complaint.sla_breached == False,
                Complaint.status.not_in([
                    ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED,
                    ComplaintStatus.CLOSED,   ComplaintStatus.REJECTED,
                ]),
            )
            .order_by(Complaint.sla_deadline.asc())
        )
        return (await self._db.execute(q)).scalars().all()

    # ── Status history ────────────────────────────────────────────────────────

    async def add_status_history(
        self,
        complaint_id: str,
        changed_by_id: str,
        from_status: Optional[ComplaintStatus],
        to_status: ComplaintStatus,
        notes: Optional[str] = None,
        officer_id: Optional[str] = None,
    ) -> ComplaintStatusHistory:
        entry = ComplaintStatusHistory(
            complaint_id=complaint_id,
            changed_by=changed_by_id,
            officer_id=officer_id,
            from_status=from_status,
            to_status=to_status,
            notes=notes,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def get_status_history(
        self, complaint_id: str
    ) -> Sequence[ComplaintStatusHistory]:
        q = (
            select(ComplaintStatusHistory)
            .options(selectinload(ComplaintStatusHistory.changed_by_user))
            .where(ComplaintStatusHistory.complaint_id == complaint_id)
            .order_by(ComplaintStatusHistory.created_at.asc())
        )
        return (await self._db.execute(q)).scalars().all()

    # ── Images ────────────────────────────────────────────────────────────────

    async def add_image(self, **kwargs) -> ComplaintImage:
        img = ComplaintImage(**kwargs)
        self._db.add(img)
        await self._db.flush()
        await self._db.refresh(img)
        return img

    async def get_images(self, complaint_id: str) -> Sequence[ComplaintImage]:
        q = select(ComplaintImage).where(
            ComplaintImage.complaint_id == complaint_id
        )
        return (await self._db.execute(q)).scalars().all()

    async def get_image_by_id(self, image_id: str) -> Optional[ComplaintImage]:
        return (
            await self._db.execute(
                select(ComplaintImage).where(ComplaintImage.id == image_id)
            )
        ).scalar_one_or_none()

    async def delete_image(self, image_id: str) -> None:
        await self._db.execute(
            delete(ComplaintImage).where(ComplaintImage.id == image_id)
        )

    async def find_by_image_hash(self, image_hash: str) -> Optional[ComplaintImage]:
        return (
            await self._db.execute(
                select(ComplaintImage).where(ComplaintImage.image_hash == image_hash)
            )
        ).scalar_one_or_none()

    # ── Supporters ────────────────────────────────────────────────────────────

    async def add_supporter(self, complaint_id: str, user_id: str) -> bool:
        """Returns True if newly added, False if already exists."""
        existing = (
            await self._db.execute(
                select(ComplaintSupporter).where(
                    ComplaintSupporter.complaint_id == complaint_id,
                    ComplaintSupporter.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return False
        self._db.add(ComplaintSupporter(
            complaint_id=complaint_id, user_id=user_id
        ))
        await self._db.flush()
        # Increment counter
        await self._db.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(support_count=Complaint.support_count + 1)
        )
        return True

    async def remove_supporter(self, complaint_id: str, user_id: str) -> bool:
        """Returns True if removed, False if not found."""
        result = await self._db.execute(
            delete(ComplaintSupporter).where(
                ComplaintSupporter.complaint_id == complaint_id,
                ComplaintSupporter.user_id == user_id,
            )
        )
        if result.rowcount:
            await self._db.execute(
                update(Complaint)
                .where(Complaint.id == complaint_id)
                .values(
                    support_count=func.greatest(Complaint.support_count - 1, 0)
                )
            )
            return True
        return False

    async def is_supporter(self, complaint_id: str, user_id: str) -> bool:
        result = await self._db.execute(
            select(func.count()).where(
                ComplaintSupporter.complaint_id == complaint_id,
                ComplaintSupporter.user_id == user_id,
            )
        )
        return (result.scalar() or 0) > 0

    # ── AI Analysis ───────────────────────────────────────────────────────────

    async def save_ai_analysis(self, **kwargs) -> AIAnalysis:
        analysis = AIAnalysis(**kwargs)
        self._db.add(analysis)
        await self._db.flush()
        return analysis

    async def get_ai_analysis(self, complaint_id: str) -> Optional[AIAnalysis]:
        return (
            await self._db.execute(
                select(AIAnalysis).where(
                    AIAnalysis.complaint_id == complaint_id
                )
            )
        ).scalar_one_or_none()

    # ── Resolution ────────────────────────────────────────────────────────────

    async def create_resolution(self, **kwargs) -> Resolution:
        res = Resolution(**kwargs)
        self._db.add(res)
        await self._db.flush()
        return res

    async def get_resolution(self, complaint_id: str) -> Optional[Resolution]:
        return (
            await self._db.execute(
                select(Resolution).where(
                    Resolution.complaint_id == complaint_id
                )
            )
        ).scalar_one_or_none()

    async def update_resolution(self, complaint_id: str, **kwargs) -> Optional[Resolution]:
        await self._db.execute(
            update(Resolution)
            .where(Resolution.complaint_id == complaint_id)
            .values(**kwargs)
        )
        return await self.get_resolution(complaint_id)

    # ── Categories ────────────────────────────────────────────────────────────

    async def get_all_categories(self, active_only: bool = True) -> Sequence[Category]:
        q = select(Category).order_by(Category.sort_order.asc())
        if active_only:
            q = q.where(Category.is_active == True)
        return (await self._db.execute(q)).scalars().all()

    async def get_category_by_name(self, name: IssueCategory) -> Optional[Category]:
        return (
            await self._db.execute(
                select(Category).where(Category.name == name)
            )
        ).scalar_one_or_none()

    async def get_category_by_id(self, cat_id: int) -> Optional[Category]:
        return (
            await self._db.execute(
                select(Category).where(Category.id == cat_id)
            )
        ).scalar_one_or_none()

    # ── Analytics queries ─────────────────────────────────────────────────────

    async def count_by_status(self) -> dict[str, int]:
        rows = (
            await self._db.execute(
                select(Complaint.status, func.count().label("n"))
                .where(Complaint.deleted_at.is_(None))
                .group_by(Complaint.status)
            )
        ).all()
        return {r.status: r.n for r in rows}

    async def count_by_category(self) -> list[dict]:
        rows = (
            await self._db.execute(
                select(
                    Category.display_name,
                    func.count().label("total"),
                    func.count()
                    .filter(
                        Complaint.status.in_([
                            ComplaintStatus.RESOLVED,
                            ComplaintStatus.VERIFIED,
                        ])
                    )
                    .label("resolved"),
                )
                .select_from(Complaint).join(Category, Complaint.category_id == Category.id)
                .where(Complaint.deleted_at.is_(None))
                .group_by(Category.display_name)
                .order_by(func.count().desc())
            )
        ).all()
        return [

            {

                "category": r.display_name,

                "total": r.total,

                "resolved": r.resolved,

            }

            for r in rows

        ]
    async def count_by_ward(self) -> list[dict]:
        rows = (
            await self._db.execute(
                select(
                    Complaint.ward_id,
                    func.count().label("total"),
                    func.count()
                    .filter(Complaint.status.in_([ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED]))
                    .label("resolved"),
                )
                .where(Complaint.deleted_at.is_(None), Complaint.ward_id.is_not(None))
                .group_by(Complaint.ward_id)
                .order_by(func.count().desc())
            )
        ).all()
        return [{"ward_id": r.ward_id, "total": r.total, "resolved": r.resolved} for r in rows]

    async def monthly_trend(self, months: int = 6) -> list[dict]:
        rows = (
            await self._db.execute(
                text("""
                    SELECT
                        TO_CHAR(created_at, 'Mon YYYY') AS month,
                        DATE_TRUNC('month', created_at)  AS month_date,
                        COUNT(*) AS submitted,
                        COUNT(*) FILTER (WHERE status IN ('RESOLVED','VERIFIED')) AS resolved,
                        COUNT(*) FILTER (WHERE status NOT IN ('RESOLVED','VERIFIED','CLOSED','REJECTED')) AS pending
                    FROM complaints
                    WHERE deleted_at IS NULL
                      AND created_at >= NOW() - (:months * INTERVAL '1 month')
                    GROUP BY month_date, month
                    ORDER BY month_date ASC
                """).bindparams(months=months)
            )
        ).all()
        return [
            {
                "month":     r.month,
                "submitted": r.submitted,
                "resolved":  r.resolved,
                "pending":   r.pending,
            }
            for r in rows
        ]

    async def heatmap_points(self) -> list[dict]:
        rows = (
            await self._db.execute(
                select(
                    Complaint.latitude,
                    Complaint.longitude,
                    func.count().label("weight"),
                )
                .where(
                    Complaint.deleted_at.is_(None),
                    Complaint.status.not_in([
                        ComplaintStatus.CLOSED, ComplaintStatus.REJECTED
                    ]),
                )
                .group_by(
                    func.round(Complaint.latitude, 3),
                    func.round(Complaint.longitude, 3),
                    Complaint.latitude,
                    Complaint.longitude,
                )
            )
        ).all()
        return [{"lat": float(r.latitude), "lng": float(r.longitude), "weight": r.weight} for r in rows]

    async def severity_distribution(self) -> list[dict]:
        total_q = select(func.count()).where(Complaint.deleted_at.is_(None))
        total = (await self._db.execute(total_q)).scalar() or 1
        rows = (
            await self._db.execute(
                select(Complaint.severity, func.count().label("cnt"))
                .where(Complaint.deleted_at.is_(None))
                .group_by(Complaint.severity)
            )
        ).all()
        return [
            {
                "severity":   r.severity,
                "count":      r.cnt,
                "percentage": round((r.cnt / total) * 100, 2),
            }
            for r in rows
        ]

    async def count_resolved_today(self) -> int:
        result = await self._db.execute(
            select(func.count()).where(
                Complaint.deleted_at.is_(None),
                Complaint.status.in_([ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED]),
                func.date(Complaint.resolved_at) == func.current_date(),
            )
        )
        return result.scalar() or 0

    async def avg_resolution_days(self) -> float:
        result = await self._db.execute(
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        Complaint.resolved_at - Complaint.created_at
                    ) / 86400
                )
            ).where(
                Complaint.deleted_at.is_(None),
                Complaint.resolved_at.is_not(None),
            )
        )
        val = result.scalar()
        return round(float(val), 2) if val else 0.0

    # ── CSV export ────────────────────────────────────────────────────────────

    async def export_rows(
        self,
        filters: dict,
        limit: int = 50_000,
    ) -> Sequence[Complaint]:
        """Fetch up to `limit` rows for CSV/Excel export."""
        all_complaints, _ = await self.list_complaints(
            **filters,
            page=1,
            page_size=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        return all_complaints
