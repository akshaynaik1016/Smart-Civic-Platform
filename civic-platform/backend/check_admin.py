import asyncio
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.models import User
from app.core.security import verify_password


async def main():
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.email == "admin@smartcivic.com")
            )
        ).scalar_one_or_none()

        if not user:
            print("Admin not found")
            return

        print("Email:", user.email)
        print("Role:", user.role)
        print("Status:", user.status)
        print("Verified:", user.email_verified)
        print("Password matches Admin@123456:",
              verify_password("Admin@123456", user.password_hash))


asyncio.run(main())
