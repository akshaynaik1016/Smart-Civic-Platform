import uuid
from app.core.security import hash_password
from app.core.database import SessionLocal
from app.models.models import User, UserRole, UserStatus

db = SessionLocal()

user = User(
    id=str(uuid.uuid4()),
    full_name="Administrator",
    email="admin@smartcivic.com",
    password_hash=hash_password("admin123"),
    role=UserRole.ADMIN,
    status=UserStatus.ACTIVE,
    city="Hubballi",
    state="Karnataka",
    preferred_language="en",
    email_verified=True,
    phone_verified=True,
)

db.add(user)
db.commit()

print("Admin created successfully!")
