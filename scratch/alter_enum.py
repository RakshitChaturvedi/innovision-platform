import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def run():
    db_url = os.getenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform")
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'open'"))
        await conn.execute(text("ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'investigating'"))
    await engine.dispose()
    print("Enum incident_status updated successfully!")

if __name__ == "__main__":
    asyncio.run(run())
