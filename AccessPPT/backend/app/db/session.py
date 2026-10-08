from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Async engine for FastAPI
is_sqlite = "sqlite" in settings.DATABASE_URL
async_engine_kwargs = {"echo": settings.APP_DEBUG}
if not is_sqlite:
    async_engine_kwargs.update({"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20})

async_engine = create_async_engine(
    settings.DATABASE_URL,
    **async_engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Sync engine for Celery workers
is_sync_sqlite = "sqlite" in settings.DATABASE_SYNC_URL
sync_engine_kwargs = {"echo": False}
if not is_sync_sqlite:
    sync_engine_kwargs.update({"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10})

sync_engine = create_engine(
    settings.DATABASE_SYNC_URL,
    **sync_engine_kwargs,
)

SyncSessionLocal = sessionmaker(
    sync_engine,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
