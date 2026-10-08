"""
Database seeder for AccessPPT.
Populates initial demo user only (clean slate - no sample presentations).
"""
import asyncio
import uuid
from sqlalchemy import select
from app.db.base import Base
from app.db.session import AsyncSessionLocal, sync_engine
from app.core.security import hash_password
from app.models.user import User
import app.models  # ensure all models registered


async def seed():
    # Ensure all tables are created
    Base.metadata.create_all(sync_engine)

    async with AsyncSessionLocal() as session:
        # Check if demo user exists
        stmt = select(User).where(User.email == "demo@accessppt.com")
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email="demo@accessppt.com",
                full_name="Demo User",
                hashed_password=hash_password("Password123!"),
                is_active=True,
                is_superuser=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"Created demo user: {user.email}")
        else:
            print(f"Demo user already exists: {user.email}")


if __name__ == "__main__":
    asyncio.run(seed())
