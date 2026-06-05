"""
Thiết lập SQLAlchemy — Hỗ trợ SQLite (dev) và MySQL (prod).
Dùng async engine cho FastAPI, sync engine cho Celery tasks.
"""
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from server.config import DATABASE_URL

logger = logging.getLogger(__name__)

# ---------- BASE MODEL ----------
class Base(DeclarativeBase):
    pass

# ---------- PHÁT HIỆN LOẠI DATABASE ----------
_IS_SQLITE = "sqlite" in DATABASE_URL

# ---------- ASYNC ENGINE (cho FastAPI) ----------
async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------- SYNC ENGINE (cho Celery workers) ----------
# Chuyển đổi URL async → sync (aiosqlite → pysqlite, asyncmy → pymysql)
_sync_url = DATABASE_URL.replace("+aiosqlite", "").replace("+asyncmy", "+pymysql")
sync_engine = create_engine(
    _sync_url,
    echo=False,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
)


async def init_db():
    """Tạo tất cả bảng (dùng cho lần chạy đầu)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables created successfully.")


async def get_async_session():
    """Dependency: Inject AsyncSession vào FastAPI endpoints."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_session():
    """Tạo sync session cho Celery workers."""
    session = SyncSessionLocal()
    try:
        return session
    except Exception:
        session.close()
        raise
