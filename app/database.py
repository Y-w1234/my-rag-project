"""
数据库引擎和会话管理。
使用 SQLite + aiosqlite，零配置，无需额外服务。
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Windows 上 aiosqlite 不支持绝对路径 URL
# 使用相对于 CWD 的相对路径
_db_rel = os.path.join("data", "rag_app.db")
DATABASE_URL = f"sqlite+aiosqlite:///{_db_rel.replace(os.sep, '/')}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
