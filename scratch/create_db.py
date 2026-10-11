import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres@127.0.0.1:5432/postgres")
    try:
        await conn.execute("CREATE USER innovision WITH PASSWORD 'changeme' SUPERUSER;")
        print("Created user innovision")
    except Exception as e:
        print("User error/exists:", e)
    
    try:
        await conn.execute("CREATE DATABASE innovision_platform OWNER innovision;")
        print("Created database innovision_platform")
    except Exception as e:
        print("DB error/exists:", e)
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
