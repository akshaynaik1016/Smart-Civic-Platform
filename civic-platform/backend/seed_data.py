"""
Smart Civic Intelligence Platform — Database Seed Script
=========================================================
Run from the backend/ directory:
    python3 seed_data.py

Requirements:
    pip install faker asyncpg sqlalchemy[asyncio]
    (all already in requirements.txt)

Safe to run multiple times — skips records that already exist.

Fixes vs original seed_data.py (validated against models.py):
  FIX 1 — Category: icon= renamed to icon_url=
           Model has: icon_url: Mapped[Optional[str]] = mapped_column(Text)
           There is no "icon" column.

  FIX 2 — Complaint: removed category=issue_cat.value
           Model has no "category" column. The FK is category_id (already set).

  FIX 3 — Complaint: removed duplicate is_duplicate=False kwarg
           Python raises TypeError: keyword argument repeated.
"""
from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone

try:
    from faker import Faker
except ImportError:
    print("ERROR: Faker not installed.  pip install faker")
    sys.exit(1)

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_password
from app.models.models import (
    AIAnalysis,
    AuditAction,
    AuditLog,
    Category,
    Complaint,
    ComplaintStatus,
    ComplaintStatusHistory,
    ComplaintSupporter,
    IssueCategory,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    Officer,
    Report,
    ReportStatus,
    ReportType,
    Resolution,
    SeverityLevel,
    User,
    UserRole,
    UserStatus,
)

fake = Faker("en_IN")
random.seed(42)

NOW = datetime.now(timezone.utc)

# ── Hubballi-Dharwad geography ─────────────────────────────────────────────────
WARDS = list(range(1, 21))

ADDRESSES = [
    ("Keshwapur, Hubballi",         15.3730, 75.1100),
    ("Vidyanagar, Hubballi",        15.3600, 75.1350),
    ("Deshpande Nagar, Hubballi",   15.3500, 75.1200),
    ("Gokul Road, Hubballi",        15.3800, 75.1050),
    ("Navanagar, Hubli",            15.3430, 75.1280),
    ("Tarihal, Hubballi",           15.3900, 75.0950),
    ("Kusugal Road, Hubballi",      15.3650, 75.1400),
    ("Unkal, Hubballi",             15.3750, 75.1450),
    ("Hebbal, Hubballi",            15.3550, 75.1150),
    ("Bhagyanagar, Hubballi",       15.3480, 75.1320),
    ("Aiwan-E-Shahi, Dharwad",      15.4589, 75.0078),
    ("PB Road, Dharwad",            15.4500, 74.9990),
    ("Saptapur, Dharwad",           15.4640, 75.0020),
    ("Kalyan Nagar, Dharwad",       15.4700, 74.9960),
    ("Vidyagiri, Dharwad",          15.4420, 75.0130),
    ("Shivaji Nagar, Hubballi",     15.3610, 75.1260),
    ("Hosur Cross, Hubballi",       15.3690, 75.1180),
    ("BVB College Road, Hubli",     15.3770, 75.1310),
    ("New Cotton Market, Hubli",    15.3520, 75.1230),
    ("Court Circle, Dharwad",       15.4530, 75.0050),
]

DEPARTMENTS = [
    "Roads & Infrastructure",
    "Solid Waste Management",
    "Water & Sanitation",
    "Electrical & Streetlights",
    "Parks & Public Spaces",
]

DESIGNATIONS = [
    "Junior Engineer",
    "Assistant Engineer",
    "Executive Engineer",
    "Sanitation Inspector",
    "Field Supervisor",
]

# FIX 1: key renamed from "icon" to "icon_url" to match Category.icon_url column
CATEGORY_META = {
    IssueCategory.POTHOLE: {
        "display_name": "Pothole",
        "description":  "Road potholes and surface damage affecting vehicle movement",
        "icon_url":     "🕳️",
        "color_hex":    "#E53E3E",
        "sla_hours":    48,
        "sort_order":   1,
    },
    IssueCategory.GARBAGE: {
        "display_name": "Garbage Accumulation",
        "description":  "Overflowing bins, uncollected waste, illegal dumping",
        "icon_url":     "🗑️",
        "color_hex":    "#D69E2E",
        "sla_hours":    24,
        "sort_order":   2,
    },
    IssueCategory.WATER_LEAKAGE: {
        "display_name": "Water Leakage",
        "description":  "Pipeline leaks, water waste, drainage issues",
        "icon_url":     "💧",
        "color_hex":    "#3182CE",
        "sla_hours":    12,
        "sort_order":   3,
    },
    IssueCategory.OPEN_MANHOLE: {
        "display_name": "Open Manhole",
        "description":  "Uncovered manholes posing danger to pedestrians and vehicles",
        "icon_url":     "⚠️",
        "color_hex":    "#DD6B20",
        "sla_hours":    6,
        "sort_order":   4,
    },
    IssueCategory.BROKEN_STREETLIGHT: {
        "display_name": "Broken Streetlight",
        "description":  "Non-functional street lights creating safety hazards",
        "icon_url":     "💡",
        "color_hex":    "#805AD5",
        "sla_hours":    48,
        "sort_order":   5,
    },
    IssueCategory.FALLEN_TREE: {
        "display_name": "Fallen Tree",
        "description":  "Trees blocking roads or causing property damage",
        "icon_url":     "🌳",
        "color_hex":    "#38A169",
        "sla_hours":    4,
        "sort_order":   6,
    },
    IssueCategory.DAMAGED_ROAD_SIGN: {
        "display_name": "Damaged Road Sign",
        "description":  "Missing or damaged traffic and road signs",
        "icon_url":     "🚸",
        "color_hex":    "#F6AD55",
        "sla_hours":    72,
        "sort_order":   7,
    },
    IssueCategory.ILLEGAL_DUMPING: {
        "display_name": "Illegal Dumping",
        "description":  "Unauthorised waste disposal in public spaces",
        "icon_url":     "🚮",
        "color_hex":    "#FC8181",
        "sla_hours":    24,
        "sort_order":   8,
    },
    IssueCategory.OTHER: {
        "display_name": "Other",
        "description":  "Other civic issues not covered by specific categories",
        "icon_url":     "📌",
        "color_hex":    "#718096",
        "sla_hours":    72,
        "sort_order":   9,
    },
}

COMPLAINT_TEMPLATES = {
    IssueCategory.POTHOLE: [
        ("Large pothole near {landmark}",
         "A large pothole has developed near {landmark} on {address}. "
         "It is approximately {size} cm deep and is causing damage to vehicles. "
         "Immediate repair is required."),
        ("Road surface damage at {address}",
         "Multiple potholes have formed at {address}. The road surface has severely "
         "deteriorated, making it dangerous for two-wheelers especially during night time."),
    ],
    IssueCategory.GARBAGE: [
        ("Garbage overflow at {address}",
         "The garbage bin near {landmark} at {address} has been overflowing for "
         "{days} days. The accumulated waste is causing a foul smell and health hazard."),
        ("Uncollected waste near {landmark}",
         "Waste has not been collected for several days at {address}. "
         "Stray animals are scattering the garbage, creating a sanitation problem."),
    ],
    IssueCategory.WATER_LEAKAGE: [
        ("Water pipeline leaking at {address}",
         "A water pipeline is leaking continuously at {address} near {landmark}. "
         "Significant water is being wasted. The leaking water has also damaged the road surface."),
        ("Burst water pipe causing flooding near {landmark}",
         "A burst water pipe at {address} is causing water to flood the road. "
         "Pedestrians and vehicles are unable to pass safely."),
    ],
    IssueCategory.OPEN_MANHOLE: [
        ("Open manhole cover missing at {address}",
         "A manhole cover is missing at {address} near {landmark}. "
         "This is extremely dangerous for pedestrians, cyclists and motorists, "
         "especially at night when visibility is poor."),
        ("Damaged manhole lid near {landmark}",
         "The manhole cover at {address} is broken and partially open. "
         "Two-wheelers and pedestrians are at serious risk of injury."),
    ],
    IssueCategory.BROKEN_STREETLIGHT: [
        ("Street light not working at {address}",
         "{count} street lights have been non-functional at {address} near {landmark} "
         "for the past {days} days. The area is completely dark at night, "
         "making it unsafe for residents."),
        ("Damaged lamp post near {landmark}",
         "A street light pole at {address} has been damaged and is leaning dangerously. "
         "It poses a risk to passing vehicles and pedestrians."),
    ],
    IssueCategory.FALLEN_TREE: [
        ("Tree fallen blocking road at {address}",
         "A large tree has fallen across the road at {address} near {landmark}. "
         "It is completely blocking traffic. Immediate removal is required."),
        ("Broken tree branch hanging dangerously near {landmark}",
         "A large branch is hanging dangerously from a tree at {address}. "
         "It could fall any moment causing injury or property damage."),
    ],
    IssueCategory.DAMAGED_ROAD_SIGN: [
        ("Road sign missing at {address}",
         "The road sign at {address} near {landmark} has been missing for {days} days. "
         "This is causing confusion among drivers and increasing risk of accidents."),
        ("Damaged traffic sign near {landmark}",
         "A traffic sign at {address} has been vandalized and is no longer readable. "
         "Replacement is urgently needed."),
    ],
    IssueCategory.ILLEGAL_DUMPING: [
        ("Illegal waste dumping at {address}",
         "Construction and household waste has been illegally dumped at {address} "
         "near {landmark}. The dump site has been growing for {days} days. "
         "It is blocking the footpath and causing a health hazard."),
        ("Large dump of debris near {landmark}",
         "Someone has been dumping debris and old furniture at {address}. "
         "The garbage has been attracting rodents and stray animals."),
    ],
    IssueCategory.OTHER: [
        ("Civic issue reported at {address}",
         "A civic issue has been observed at {address} near {landmark}. "
         "The matter requires attention from the municipal corporation."),
    ],
}

AI_DESCRIPTIONS = {
    IssueCategory.POTHOLE: (
        "AI detected road surface damage with {conf:.0%} confidence. "
        "Estimated pothole depth suggests {severity} severity. Immediate repair recommended."
    ),
    IssueCategory.GARBAGE: (
        "AI analysis detected accumulated waste material at the reported location "
        "with {conf:.0%} confidence. Severity classified as {severity} based on volume estimation."
    ),
    IssueCategory.WATER_LEAKAGE: (
        "Water leakage detected in uploaded image with {conf:.0%} confidence. "
        "Severity: {severity}. Pipeline repair required."
    ),
    IssueCategory.OPEN_MANHOLE: (
        "Open manhole detected with {conf:.0%} confidence. Classified as "
        "{severity} severity — immediate safety action required."
    ),
    IssueCategory.BROKEN_STREETLIGHT: (
        "Non-functional streetlight infrastructure detected with {conf:.0%} confidence. "
        "Severity: {severity}."
    ),
    IssueCategory.FALLEN_TREE: (
        "Fallen tree or obstruction detected with {conf:.0%} confidence. "
        "Severity classified as {severity}. Road clearance required."
    ),
    IssueCategory.DAMAGED_ROAD_SIGN: (
        "Damaged or missing road sign detected with {conf:.0%} confidence. Severity: {severity}."
    ),
    IssueCategory.ILLEGAL_DUMPING: (
        "Illegal waste dump detected with {conf:.0%} confidence. "
        "Volume estimate suggests {severity} severity."
    ),
    IssueCategory.OTHER: (
        "Civic issue detected with {conf:.0%} confidence. Severity: {severity}."
    ),
}

WORK_DONE_TEMPLATES = {
    IssueCategory.POTHOLE: [
        "Road surface was excavated to remove loose material. Bituminous concrete applied in layers "
        "and compacted. Surface finished with hot-mix asphalt.",
        "Pothole filled using cold-patch asphalt mix. Surface levelled and compacted. "
        "Area barricaded during repair.",
    ],
    IssueCategory.GARBAGE: [
        "Accumulated waste collected and transported to municipal solid waste facility. "
        "Area cleaned and disinfected. New bin provided.",
        "Garbage cleared from the site. Surrounding area swept and sanitised. "
        "Residents advised on proper disposal.",
    ],
    IssueCategory.WATER_LEAKAGE: [
        "Damaged pipeline section isolated and replaced with new PVC pipe. "
        "Joint sealed with appropriate fittings. Water supply restored.",
        "Leaking valve replaced. Pipeline pressure tested. Area dried and road patched where necessary.",
    ],
    IssueCategory.OPEN_MANHOLE: [
        "New heavy-duty manhole cover installed as per HDMC specifications. "
        "Frame secured with cement mortar. Area inspected for additional hazards.",
        "Damaged manhole cover replaced. Surrounding road surface repaired. Safety barriers removed.",
    ],
    IssueCategory.BROKEN_STREETLIGHT: [
        "Faulty LED lamp module replaced. Electrical connections inspected and tightened. "
        "Streetlight tested and confirmed operational.",
        "Damaged pole replaced with new GI pole. New LED fitting installed. "
        "Electrical connection to grid restored.",
    ],
    IssueCategory.FALLEN_TREE: [
        "Fallen tree cut into sections using chainsaw. Logs and branches cleared from road. "
        "Area swept and opened for traffic.",
        "Damaged tree branch removed safely. Remaining tree trimmed to prevent future hazard. Debris cleared.",
    ],
    IssueCategory.DAMAGED_ROAD_SIGN: [
        "New road sign fabricated and installed on new post as per IRC specifications. "
        "Retroreflective sheeting used for night visibility.",
        "Damaged sign removed and replaced. Post concreted in. Sign aligned as per road geometry.",
    ],
    IssueCategory.ILLEGAL_DUMPING: [
        "Illegal dump cleared using municipal vehicles. Waste segregated and transported to "
        "designated facility. Area cleaned with disinfectant.",
        "Large-scale illegal dump removed over two days. Site fenced temporarily to prevent "
        "re-dumping. Area restored.",
    ],
    IssueCategory.OTHER: [
        "Issue investigated and addressed by concerned department. Area inspected and cleared.",
    ],
}

CITIZEN_FEEDBACK_TEMPLATES = [
    "The issue has been completely resolved. Thank you for the quick response!",
    "Work has been done but the quality could be better. Hope it lasts.",
    "Repair looks good. Appreciate the timely action by HDMC.",
    "Issue is resolved. The officer was professional and efficient.",
    "Problem fixed but took longer than expected. Overall satisfied.",
    "Excellent work! The road is now safe for everyone.",
    "The repair is satisfactory. Good job by the maintenance team.",
    "Issue resolved adequately. The area is clean and safe now.",
]

INDIAN_FIRST_NAMES = [
    "Arun", "Vijay", "Ramesh", "Suresh", "Mahesh", "Rajesh", "Ganesh",
    "Priya", "Deepa", "Kavitha", "Sunita", "Rekha", "Meena", "Lakshmi",
    "Ravi", "Kumar", "Prakash", "Srinivas", "Nagaraj", "Basavaraj",
    "Shivakumar", "Manjunath", "Siddaramaiah", "Chandrakala", "Pushpa",
    "Anand", "Venkatesh", "Sanjay", "Neha", "Pooja", "Asha", "Usha",
    "Girish", "Harish", "Sunil", "Anil", "Kiran", "Mohan", "Gopal",
]

INDIAN_LAST_NAMES = [
    "Patil", "Desai", "Kulkarni", "Joshi", "Naik", "Shetty", "Nayak",
    "Gupta", "Sharma", "Reddy", "Kumar", "Singh", "Rao", "Hegde",
    "Kamat", "Shenoy", "Gowda", "Hosamani", "Angadi", "Wali",
    "Hiremath", "Sajjan", "Itagi", "Munavalli", "Bhosale",
]

OFFICER_FIRST_NAMES = ["Vinod", "Santosh", "Chandrashekhar", "Nirmala", "Amruta"]
OFFICER_LAST_NAMES  = ["Patil", "Kulkarni", "Desai", "Naik", "Hiremath"]


def rnd_name(first_list=INDIAN_FIRST_NAMES, last_list=INDIAN_LAST_NAMES) -> str:
    return f"{random.choice(first_list)} {random.choice(last_list)}"


def rnd_phone() -> str:
    return f"+91{random.randint(7000000000, 9999999999)}"


def rnd_past(days_max: int = 60) -> datetime:
    return NOW - timedelta(
        days=random.uniform(0, days_max),
        hours=random.uniform(0, 24),
    )


def severity_weights() -> SeverityLevel:
    return random.choices(
        [SeverityLevel.LOW, SeverityLevel.MEDIUM, SeverityLevel.HIGH, SeverityLevel.CRITICAL],
        weights=[20, 45, 25, 10],
    )[0]


def status_weights() -> ComplaintStatus:
    return random.choices(
        [
            ComplaintStatus.SUBMITTED,
            ComplaintStatus.PENDING_REVIEW,
            ComplaintStatus.ASSIGNED,
            ComplaintStatus.IN_PROGRESS,
            ComplaintStatus.RESOLVED,
            ComplaintStatus.VERIFIED,
            ComplaintStatus.CLOSED,
            ComplaintStatus.REJECTED,
        ],
        weights=[8, 5, 12, 15, 25, 20, 10, 5],
    )[0]


def priority_score(severity: SeverityLevel, support_count: int, sla_breached: bool) -> float:
    base = {"low": 10, "medium": 20, "high": 30, "critical": 40}.get(severity.value, 20)
    return min(100.0, base + min(support_count * 2, 20) + (30 if sla_breached else 0))


# ══════════════════════════════════════════════════════════════════════════════
# SEED FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def seed_categories(session) -> dict[str, Category]:
    count = (await session.execute(select(func.count()).select_from(Category))).scalar()
    if count > 0:
        print(f"  ✓ Categories already exist ({count} rows) — skipping")
        rows = (await session.execute(select(Category))).scalars().all()
        return {r.name: r for r in rows}

    print("  Creating categories …")
    cats: dict[str, Category] = {}
    for issue_cat, meta in CATEGORY_META.items():
        cat = Category(
            name=issue_cat.value,
            display_name=meta["display_name"],
            description=meta["description"],
            icon_url=meta["icon_url"],   # FIX 1 applied here
            color_hex=meta["color_hex"],
            sla_hours=meta["sla_hours"],
            is_active=True,
            sort_order=meta["sort_order"],
        )
        session.add(cat)
        cats[issue_cat.value] = cat

    await session.flush()
    print(f"    → Created {len(cats)} categories")
    return cats


async def seed_admin(session) -> User:
    existing = (
        await session.execute(
            select(User).where(User.role == UserRole.ADMIN.value).limit(1)
        )
    ).scalar_one_or_none()

    if existing:
        print(f"  ✓ Admin already exists ({existing.email}) — skipping")
        return existing

    print("  Creating admin user …")
    admin = User(
        email="admin@smartcivic.gov.in",
        phone="+919900000001",
        password_hash=hash_password("Admin@123456"),
        full_name="HDMC Administrator",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
        city="Hubballi",
        state="Karnataka",
        pincode="580020",
        email_verified=True,
        phone_verified=True,
        email_verified_at=NOW - timedelta(days=365),
        phone_verified_at=NOW - timedelta(days=365),
        preferred_language="en",
        total_complaints=0,
        resolved_complaints=0,
        reputation_score=100.0,
        last_login_at=NOW - timedelta(hours=2),
        last_active_at=NOW - timedelta(minutes=30),
    )
    session.add(admin)
    await session.flush()
    print(f"    → Admin created: {admin.email} / Admin@123456")
    return admin


async def seed_citizens(session, count: int = 30) -> list[User]:
    existing_count = (
        await session.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.CITIZEN.value)
        )
    ).scalar()

    if existing_count >= count:
        print(f"  ✓ Citizens already exist ({existing_count} rows) — skipping")
        return (
            await session.execute(select(User).where(User.role == UserRole.CITIZEN.value))
        ).scalars().all()

    needed = count - existing_count
    print(f"  Creating {needed} citizen users …")

    used_emails: set[str] = set()
    used_phones: set[str] = set()
    citizens: list[User] = []
    attempts = 0

    while len(citizens) < needed and attempts < needed * 5:
        attempts += 1
        full_name  = rnd_name()
        base_email = full_name.lower().replace(" ", ".") + str(random.randint(10, 999))
        email      = f"{base_email}@gmail.com"
        phone      = rnd_phone()

        if email in used_emails or phone in used_phones:
            continue
        used_emails.add(email)
        used_phones.add(phone)

        addr    = random.choice(ADDRESSES)
        total   = random.randint(0, 15)
        resolved = random.randint(0, total)
        rep     = min(100.0, round(40 + resolved * 4 + random.uniform(-5, 10), 2))
        joined  = NOW - timedelta(days=random.randint(30, 365))

        user = User(
            email=email,
            phone=phone,
            password_hash=hash_password("Citizen@123"),
            full_name=full_name,
            role=UserRole.CITIZEN.value,
            status=UserStatus.ACTIVE.value,
            city="Hubballi" if "Hubballi" in addr[0] else "Dharwad",
            state="Karnataka",
            pincode=random.choice(["580020", "580021", "580025", "580001", "580003"]),
            ward_id=random.choice(WARDS),
            email_verified=True,
            phone_verified=True,
            email_verified_at=joined,
            phone_verified_at=joined,
            preferred_language=random.choice(["en", "kn"]),
            total_complaints=total,
            resolved_complaints=resolved,
            reputation_score=rep,
            last_login_at=rnd_past(7),
            last_active_at=rnd_past(3),
        )
        session.add(user)
        citizens.append(user)

    await session.flush()
    print(f"    → Created {len(citizens)} citizens  (password: Citizen@123)")
    return citizens


async def seed_officers(session, admin: User, count: int = 5) -> list[tuple[User, Officer]]:
    existing_count = (
        await session.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.OFFICER.value)
        )
    ).scalar()

    if existing_count >= count:
        print(f"  ✓ Officers already exist ({existing_count} rows) — skipping")
        rows = (
            await session.execute(
                select(User, Officer)
                .join(Officer, Officer.user_id == User.id)
                .where(User.role == UserRole.OFFICER.value)
            )
        ).all()
        return [(u, o) for u, o in rows]

    needed = count - existing_count
    print(f"  Creating {needed} officer users …")

    used_badges: set[str] = set()
    existing_badges = (await session.execute(select(Officer.badge_number))).scalars().all()
    used_badges.update(existing_badges)

    pairs: list[tuple[User, Officer]] = []

    for i in range(needed):
        fn    = OFFICER_FIRST_NAMES[i % len(OFFICER_FIRST_NAMES)]
        ln    = OFFICER_LAST_NAMES[i % len(OFFICER_LAST_NAMES)]
        email = f"officer{i + existing_count + 1}@hdmc.gov.in"
        phone = f"+91800000{str(i + existing_count + 1).zfill(4)}"
        badge = f"HDMC{str(1000 + i + existing_count + 1)}"

        while badge in used_badges:
            badge = f"HDMC{str(random.randint(1000, 9999))}"
        used_badges.add(badge)

        dept       = DEPARTMENTS[i % len(DEPARTMENTS)]
        assigned   = random.randint(5, 15)
        resolved_c = random.randint(3, assigned)
        avg_days   = round(random.uniform(1.5, 6.0), 2)
        perf       = min(100.0, round((resolved_c / max(assigned, 1)) * 60 + (7 / avg_days) * 40, 2))
        ward_slice = WARDS[i * 4: i * 4 + 4] or WARDS[:4]
        cat_ids    = list(range(1, random.randint(3, 6)))

        user = User(
            email=email,
            phone=phone,
            password_hash=hash_password("Officer@123"),
            full_name=f"{fn} {ln}",
            role=UserRole.OFFICER.value,
            status=UserStatus.ACTIVE.value,
            city="Hubballi",
            state="Karnataka",
            pincode="580020",
            email_verified=True,
            phone_verified=True,
            email_verified_at=NOW - timedelta(days=180),
            phone_verified_at=NOW - timedelta(days=180),
            preferred_language="en",
            total_complaints=0,
            resolved_complaints=0,
            reputation_score=85.0,
            last_login_at=rnd_past(2),
            last_active_at=rnd_past(1),
        )
        session.add(user)
        await session.flush()

        officer = Officer(
            user_id=user.id,
            badge_number=badge,
            department=dept,
            designation=DESIGNATIONS[i % len(DESIGNATIONS)],
            ward_ids=ward_slice,
            category_ids=cat_ids,
            is_available=random.choice([True, True, True, False]),
            max_complaints=20,
            total_assigned=assigned,
            total_resolved=resolved_c,
            avg_resolution_days=avg_days,
            performance_score=perf,
        )
        session.add(officer)
        await session.flush()
        pairs.append((user, officer))

    print(f"    → Created {needed} officers  (password: Officer@123)")
    return pairs


async def seed_complaints(
    session,
    citizens: list[User],
    officers: list[tuple[User, Officer]],
    categories: dict[str, Category],
    admin: User,
    count: int = 150,
) -> list[Complaint]:
    existing = (await session.execute(select(func.count()).select_from(Complaint))).scalar()
    if existing >= count:
        print(f"  ✓ Complaints already exist ({existing} rows) — skipping")
        return (await session.execute(select(Complaint))).scalars().all()

    needed = count - existing
    print(f"  Creating {needed} complaints with AI analysis, status history, notifications …")

    issue_cats  = list(IssueCategory)
    cat_weights = [20, 18, 12, 10, 10, 8, 8, 9, 5]

    all_complaints: list[Complaint] = []
    complaint_counter = existing + 1

    for _ in range(needed):
        issue_cat = random.choices(issue_cats, weights=cat_weights)[0]
        cat_obj   = categories.get(issue_cat.value)
        if not cat_obj:
            continue

        citizen   = random.choice(citizens)
        severity  = severity_weights()
        status    = status_weights()
        addr_data = random.choice(ADDRESSES)
        ward      = random.choice(WARDS)

        lat = round(addr_data[1] + random.uniform(-0.005, 0.005), 7)
        lng = round(addr_data[2] + random.uniform(-0.005, 0.005), 7)

        templates = COMPLAINT_TEMPLATES.get(issue_cat, COMPLAINT_TEMPLATES[IssueCategory.OTHER])
        tmpl = random.choice(templates)
        fill = {
            "landmark": fake.last_name() + " Nagar",
            "address":  addr_data[0],
            "size":     random.randint(10, 40),
            "days":     random.randint(2, 14),
            "count":    random.randint(1, 5),
        }

        title = tmpl[0].format(**fill)[:255]
        desc  = tmpl[1].format(**fill)

        created_at   = rnd_past(60)
        sla_hrs      = cat_obj.sla_hours
        sla_deadline = created_at + timedelta(hours=sla_hrs)
        sla_breached = sla_deadline < NOW and status not in (
            ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED,
            ComplaintStatus.CLOSED, ComplaintStatus.REJECTED,
        )

        support_count = random.choices([0, 1, 2, 3, 5, 10], weights=[40, 20, 15, 10, 10, 5])[0]
        ai_conf       = round(random.uniform(0.70, 0.98), 4)
        ai_desc       = AI_DESCRIPTIONS.get(issue_cat, AI_DESCRIPTIONS[IssueCategory.OTHER]).format(
            conf=ai_conf, severity=severity.value
        )
        tags = [issue_cat.value, f"ward-{ward}", severity.value]

        is_assigned  = status in (
            ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS,
            ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED,
        )
        officer_pair = random.choice(officers) if is_assigned and officers else None
        officer_obj  = officer_pair[1] if officer_pair else None

        resolved_at         = None
        citizen_verified    = False
        citizen_verified_at = None
        citizen_rating      = None
        resolution_notes    = None

        if status in (ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED):
            resolved_at = created_at + timedelta(days=random.uniform(0.5, sla_hrs / 24 * 1.5))
            if status == ComplaintStatus.VERIFIED:
                citizen_verified    = True
                citizen_verified_at = resolved_at + timedelta(hours=random.uniform(2, 48))
                citizen_rating      = random.choices([3, 4, 5], weights=[20, 40, 40])[0]
            resolution_notes = random.choice([
                "Issue resolved as reported.",
                "Repair completed successfully.",
                "Work done as per specifications.",
                None,
            ])

        prio = round(priority_score(severity, support_count, sla_breached), 2)

        # FIX 2: removed category=issue_cat.value (no such column in Complaint model)
        # FIX 3: is_duplicate= appears only once
        complaint = Complaint(
            complaint_number=f"CMP-{2025}-{str(complaint_counter).zfill(5)}",
            citizen_id=citizen.id,
            officer_id=officer_obj.id if officer_obj else None,
            category_id=cat_obj.id,
            status=status.value,
            severity=severity.value,
            priority_score=prio,
            latitude=lat,
            longitude=lng,
            address=addr_data[0],
            ward_id=ward,
            landmark=fill["landmark"],
            title=title,
            description=desc,
            ai_description=ai_desc,
            tags=tags,
            support_count=support_count,
            ai_confidence=ai_conf,
            ai_processed_at=created_at + timedelta(minutes=random.uniform(0.5, 5)),
            ai_model_version="yolov8n-civic-v1.0.0",
            resolved_at=resolved_at,
            resolution_notes=resolution_notes,
            citizen_verified=citizen_verified,
            citizen_verified_at=citizen_verified_at,
            citizen_rating=citizen_rating,
            sla_deadline=sla_deadline,
            sla_breached=sla_breached,
            is_flagged=False,
            is_duplicate=False,
        )
        complaint.created_at = created_at
        complaint.updated_at = resolved_at or created_at

        session.add(complaint)
        await session.flush()

        # ── AIAnalysis ────────────────────────────────────────────────────────
        ai = AIAnalysis(
            complaint_id=complaint.id,
            detected_category=issue_cat.value,
            confidence_score=ai_conf,
            severity_predicted=severity.value,
            severity_confidence=round(random.uniform(0.75, 0.95), 4),
            bounding_boxes={
                "boxes": [[
                    round(random.uniform(0.1, 0.3), 3),
                    round(random.uniform(0.1, 0.3), 3),
                    round(random.uniform(0.6, 0.9), 3),
                    round(random.uniform(0.6, 0.9), 3),
                ]],
                "labels": [issue_cat.value],
                "scores": [ai_conf],
            },
            generated_description=ai_desc,
            description_model="template-v1",
            duplicate_checked=True,
            is_duplicate=False,
            similar_complaint_ids=[],
            model_name="yolov8n-civic",
            model_version="v1.0.0",
            inference_time_ms=random.randint(80, 350),
            raw_output={"pipeline_time_ms": random.randint(150, 600)},
            processing_status="completed",
        )
        ai.created_at = complaint.created_at
        session.add(ai)

        # ── Status history ────────────────────────────────────────────────────
        for h in build_status_history(complaint, citizen, officer_obj, created_at):
            session.add(h)

        # ── Resolution ────────────────────────────────────────────────────────
        if status in (ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED) and officer_obj:
            work_list = WORK_DONE_TEMPLATES.get(issue_cat, WORK_DONE_TEMPLATES[IssueCategory.OTHER])
            res = Resolution(
                complaint_id=complaint.id,
                officer_id=officer_obj.id,
                resolution_type=resolution_type_for(issue_cat),
                work_done=random.choice(work_list),
                materials_used=materials_for(issue_cat),
                contractor_name=random.choice([None, None, f"{fake.last_name()} Contractors"]),
                estimated_cost=round(random.uniform(500, 50000), 2),
                actual_cost=round(random.uniform(400, 55000), 2),
                started_at=created_at + timedelta(hours=random.uniform(4, 24)),
                completed_at=resolved_at,
                citizen_feedback=random.choice(CITIZEN_FEEDBACK_TEMPLATES) if citizen_verified else None,
                citizen_rating=citizen_rating,
                citizen_rated_at=citizen_verified_at,
            )
            res.created_at = complaint.created_at
            session.add(res)

        # ── Notifications ─────────────────────────────────────────────────────
        for n in build_notifications(complaint, citizen, officer_obj, created_at, resolved_at):
            session.add(n)

        all_complaints.append(complaint)
        complaint_counter += 1

        if len(all_complaints) % 20 == 0:
            await session.commit()
            print(f"    … {len(all_complaints)}/{needed} complaints committed")

    await session.commit()
    print(f"    → Created {len(all_complaints)} complaints")
    return all_complaints


def resolution_type_for(cat: IssueCategory) -> str:
    m = {
        IssueCategory.POTHOLE:            "road_repair",
        IssueCategory.GARBAGE:            "waste_removal",
        IssueCategory.WATER_LEAKAGE:      "pipeline_repair",
        IssueCategory.OPEN_MANHOLE:       "cover_replacement",
        IssueCategory.BROKEN_STREETLIGHT: "electrical_repair",
        IssueCategory.FALLEN_TREE:        "tree_removal",
        IssueCategory.DAMAGED_ROAD_SIGN:  "sign_replacement",
        IssueCategory.ILLEGAL_DUMPING:    "waste_removal",
    }
    return m.get(cat, "general_repair")


def materials_for(cat: IssueCategory) -> str | None:
    m = {
        IssueCategory.POTHOLE:            "Bituminous concrete, hot-mix asphalt",
        IssueCategory.GARBAGE:            "Disinfectant, protective gear",
        IssueCategory.WATER_LEAKAGE:      "PVC pipes, fittings, cement",
        IssueCategory.OPEN_MANHOLE:       "CI manhole cover, cement mortar",
        IssueCategory.BROKEN_STREETLIGHT: "LED lamp module, electrical fittings",
        IssueCategory.FALLEN_TREE:        "Chainsaw, vehicle for transport",
        IssueCategory.DAMAGED_ROAD_SIGN:  "Reflective sign board, GI post, cement",
        IssueCategory.ILLEGAL_DUMPING:    "Disinfectant, vehicles",
    }
    return m.get(cat)


def build_status_history(
    complaint: Complaint,
    citizen: User,
    officer: Officer | None,
    created_at: datetime,
) -> list[ComplaintStatusHistory]:
    status = ComplaintStatus(complaint.status)
    progression = {
        ComplaintStatus.SUBMITTED:      [ComplaintStatus.SUBMITTED],
        ComplaintStatus.AI_PROCESSING:  [ComplaintStatus.SUBMITTED, ComplaintStatus.AI_PROCESSING],
        ComplaintStatus.PENDING_REVIEW: [ComplaintStatus.SUBMITTED, ComplaintStatus.PENDING_REVIEW],
        ComplaintStatus.ASSIGNED: [
            ComplaintStatus.SUBMITTED, ComplaintStatus.PENDING_REVIEW, ComplaintStatus.ASSIGNED,
        ],
        ComplaintStatus.IN_PROGRESS: [
            ComplaintStatus.SUBMITTED, ComplaintStatus.PENDING_REVIEW,
            ComplaintStatus.ASSIGNED,  ComplaintStatus.IN_PROGRESS,
        ],
        ComplaintStatus.RESOLVED: [
            ComplaintStatus.SUBMITTED, ComplaintStatus.PENDING_REVIEW,
            ComplaintStatus.ASSIGNED,  ComplaintStatus.IN_PROGRESS, ComplaintStatus.RESOLVED,
        ],
        ComplaintStatus.VERIFIED: [
            ComplaintStatus.SUBMITTED, ComplaintStatus.PENDING_REVIEW,
            ComplaintStatus.ASSIGNED,  ComplaintStatus.IN_PROGRESS,
            ComplaintStatus.RESOLVED,  ComplaintStatus.VERIFIED,
        ],
        ComplaintStatus.CLOSED: [
            ComplaintStatus.SUBMITTED, ComplaintStatus.PENDING_REVIEW, ComplaintStatus.CLOSED,
        ],
        ComplaintStatus.REJECTED: [
            ComplaintStatus.SUBMITTED, ComplaintStatus.PENDING_REVIEW, ComplaintStatus.REJECTED,
        ],
    }

    steps       = progression.get(status, [ComplaintStatus.SUBMITTED])
    history     = []
    prev_status = None
    step_time   = created_at

    for step in steps:
        step_time  += timedelta(hours=random.uniform(1, 12))
        actor_id    = citizen.id
        officer_id  = None
        notes       = step_notes(step, officer)

        if step in (ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS,
                    ComplaintStatus.RESOLVED) and officer:
            actor_id   = officer.user_id
            officer_id = officer.id

        h = ComplaintStatusHistory(
            complaint_id=complaint.id,
            changed_by=actor_id,
            officer_id=officer_id,
            from_status=prev_status.value if prev_status else None,
            to_status=step.value,
            notes=notes,
        )
        h.created_at = step_time
        history.append(h)
        prev_status = step

    return history


def step_notes(status: ComplaintStatus, officer: Officer | None) -> str | None:
    m = {
        ComplaintStatus.SUBMITTED:      "Complaint submitted by citizen via mobile app.",
        ComplaintStatus.PENDING_REVIEW: "AI processing complete. Pending officer review.",
        ComplaintStatus.ASSIGNED:       (
            f"Assigned to officer {officer.badge_number}." if officer else "Assigned to officer."
        ),
        ComplaintStatus.IN_PROGRESS:    "Officer has commenced field inspection and repair work.",
        ComplaintStatus.RESOLVED:       "Repair/resolution work completed by the officer.",
        ComplaintStatus.VERIFIED:       "Citizen confirmed the issue has been resolved.",
        ComplaintStatus.CLOSED:         "Complaint closed by admin.",
        ComplaintStatus.REJECTED:       "Complaint rejected after review — not a valid civic issue.",
    }
    return m.get(status)


def build_notifications(
    complaint: Complaint,
    citizen: User,
    officer: Officer | None,
    created_at: datetime,
    resolved_at: datetime | None,
) -> list[Notification]:
    status  = ComplaintStatus(complaint.status)
    notifs  = []
    base_dt = created_at

    def notif(ntype, title, body, dt, is_read=False):
        n = Notification(
            recipient_id=citizen.id,
            complaint_id=complaint.id,
            type=ntype.value,
            title=title,
            body=body,
            data={"complaint_number": complaint.complaint_number},
            channel=NotificationChannel.IN_APP.value,
            status=NotificationStatus.READ.value if is_read else NotificationStatus.DELIVERED.value,
            sent_at=dt,
            delivered_at=dt + timedelta(seconds=random.randint(1, 30)),
            read_at=dt + timedelta(minutes=random.randint(5, 120)) if is_read else None,
            retry_count=0,
            scheduled_for=dt,
        )
        n.created_at = dt
        return n

    notifs.append(notif(
        NotificationType.COMPLAINT_SUBMITTED,
        "Complaint Received ✅",
        f"Your complaint {complaint.complaint_number} has been received and is being reviewed.",
        base_dt,
        is_read=True,
    ))

    if status in (ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS,
                  ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED) and officer:
        notifs.append(notif(
            NotificationType.COMPLAINT_ASSIGNED,
            "Officer Assigned 👮",
            f"Officer {officer.badge_number} has been assigned to your complaint "
            f"{complaint.complaint_number}.",
            base_dt + timedelta(hours=random.uniform(1, 24)),
            is_read=True,
        ))

    if status in (ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED) and resolved_at:
        notifs.append(notif(
            NotificationType.COMPLAINT_RESOLVED,
            "Issue Resolved — Please Verify ✔️",
            f"Your complaint {complaint.complaint_number} has been resolved. Please verify.",
            resolved_at,
            is_read=(status == ComplaintStatus.VERIFIED),
        ))

    return notifs


async def seed_supporters(session, complaints: list[Complaint], citizens: list[User]) -> None:
    existing = (await session.execute(select(func.count()).select_from(ComplaintSupporter))).scalar()
    if existing > 0:
        print(f"  ✓ Complaint supporters already exist ({existing} rows) — skipping")
        return

    print("  Adding complaint supporters …")
    added = 0
    for complaint in complaints:
        if complaint.support_count <= 0:
            continue
        pool = [c for c in citizens if c.id != complaint.citizen_id]
        for supporter in random.sample(pool, min(complaint.support_count, len(pool))):
            session.add(ComplaintSupporter(
                complaint_id=complaint.id,
                user_id=supporter.id,
            ))
            added += 1

    await session.flush()
    print(f"    → Added {added} supporter relationships")


async def seed_reports(session, admin: User) -> None:
    existing = (await session.execute(select(func.count()).select_from(Report))).scalar()
    if existing > 0:
        print(f"  ✓ Reports already exist ({existing} rows) — skipping")
        return

    print("  Creating sample reports …")
    report_defs = [
        (ReportType.MONTHLY_SUMMARY,     "Monthly Summary — May 2025",            ReportStatus.READY,      {"months": 1}),
        (ReportType.CATEGORY_ANALYSIS,   "Category Analysis — Q1 2025",           ReportStatus.READY,      {}),
        (ReportType.WARD_ANALYSIS,       "Ward-wise Complaint Analysis",           ReportStatus.READY,      {}),
        (ReportType.OFFICER_PERFORMANCE, "Officer Performance Report — June 2025", ReportStatus.READY,      {}),
        (ReportType.RESOLUTION_RATE,     "Resolution Rate Trend",                  ReportStatus.GENERATING, {}),
        (ReportType.CUSTOM,              "Custom Pothole Export",                  ReportStatus.QUEUED,     {"filters": {"category": "pothole"}}),
    ]

    for rtype, title, rstatus, params in report_defs:
        queued_at = rnd_past(30)
        completed = (
            queued_at + timedelta(minutes=random.randint(1, 10))
            if rstatus == ReportStatus.READY else None
        )
        r = Report(
            generated_by=admin.id,
            type=rtype.value,
            title=title,
            description=f"Auto-generated {title.lower()} report.",
            parameters=params,
            status=rstatus.value,
            file_format="pdf",
            file_size_bytes=random.randint(50000, 500000) if rstatus == ReportStatus.READY else None,
            page_count=random.randint(3, 20)             if rstatus == ReportStatus.READY else None,
            summary={"total_complaints": random.randint(50, 200)} if rstatus == ReportStatus.READY else None,
            queued_at=queued_at,
            started_at=queued_at + timedelta(seconds=5) if rstatus != ReportStatus.QUEUED else None,
            completed_at=completed,
            expires_at=queued_at + timedelta(days=30)   if rstatus == ReportStatus.READY else None,
        )
        r.created_at = queued_at
        session.add(r)

    await session.flush()
    print(f"    → Created {len(report_defs)} reports")


async def seed_audit_logs(session, admin: User, citizens: list[User]) -> None:
    existing = (await session.execute(select(func.count()).select_from(AuditLog))).scalar()
    if existing > 0:
        print(f"  ✓ Audit logs already exist ({existing} rows) — skipping")
        return

    print("  Creating audit log entries …")
    entries = []
    for user in random.sample(citizens, min(10, len(citizens))):
        entries.append(AuditLog(
            user_id=user.id,
            action=AuditAction.LOGIN.value,
            resource_type="user",
            resource_id=user.id,
            ip_address=fake.ipv4(),
            user_agent="SmartCivic/1.0.0 (Android)",
            success=True,
            duration_ms=random.randint(50, 400),
        ))

    entries.append(AuditLog(
        user_id=admin.id,
        action=AuditAction.EXPORT.value,
        resource_type="complaints",
        resource_id=None,
        ip_address="10.0.0.1",
        user_agent="Mozilla/5.0 (Chrome Admin Dashboard)",
        success=True,
        duration_ms=820,
    ))

    for e in entries:
        e.created_at = rnd_past(30)
        session.add(e)

    await session.flush()
    print(f"    → Created {len(entries)} audit log entries")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    print("\n" + "=" * 60)
    print("  Smart Civic Intelligence Platform — Database Seeder")
    print("=" * 60)

    print("\n[0] Initialising database schema …")
    await init_db()
    print("    → Tables created / verified")

    async with AsyncSessionLocal() as session:
        print("\n[1] Categories")
        categories = await seed_categories(session)
        await session.commit()

        print("\n[2] Admin user")
        admin = await seed_admin(session)
        await session.commit()

        print("\n[3] Citizen users (30)")
        citizens = await seed_citizens(session, count=30)
        await session.commit()

        print("\n[4] Officer users (5)")
        officer_pairs = await seed_officers(session, admin, count=5)
        await session.commit()

        print("\n[5] Complaints + AI analysis + status history + notifications (150)")
        complaints = await seed_complaints(
            session, citizens, officer_pairs, categories, admin, count=150,
        )

        print("\n[6] Complaint supporters")
        await seed_supporters(session, complaints, citizens)
        await session.commit()

        print("\n[7] Reports")
        await seed_reports(session, admin)
        await session.commit()

        print("\n[8] Audit logs")
        await seed_audit_logs(session, admin, citizens)
        await session.commit()

    print("\n" + "=" * 60)
    print("  Seeding complete!")
    print("=" * 60)
    print("\n  Admin credentials:   admin@smartcivic.gov.in / Admin@123456")
    print("  Officer credentials: officer1@hdmc.gov.in   / Officer@123")
    print("  Citizen credentials: (see emails in DB)     / Citizen@123")
    print()


if __name__ == "__main__":
    asyncio.run(main())