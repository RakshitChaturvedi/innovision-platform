import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://innovision:changeme@127.0.0.1:5433/innovision_platform')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    print("Extensions created successfully")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
