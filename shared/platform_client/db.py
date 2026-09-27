from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from functools import lru_cache

@lru_cache
def get_engine(database_url: str):
    return create_async_engine(database_url, pool_size=10, max_overflow=5, pool_pre_ping=True)

def get_session_factory(database_url: str):
    engine = get_engine(database_url)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)