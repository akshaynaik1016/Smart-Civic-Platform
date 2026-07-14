import asyncio
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.models import User
from app.core.security import hash_password


async def main():
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.email == "admin@smartcivic.com")
            )
        ).scalar_one()

        user.password_hash = hash_password("Admin@123456")

        await session.commit()

        print("✅ Password reset successfully")


asyncio.run(main())
