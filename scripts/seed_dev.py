import asyncio, os, uuid

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from services.auth.src.jwt import hash_password

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL_LOCAL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

DEV_PASSWORD = "admin123"

CAMERAS = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Test Camera UC1",
        "location": "Development",
        "video_path": "/app/test_data/videos/uc1.mp4",
        "use_cases": ["uc1"],
        "fps": 10,
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "Test Camera UC2",
        "location": "Development",
        "video_path": "/app/test_data/videos/uc2.mp4",
        "use_cases": ["uc2"],
        "fps": 10,
    },
    {
        "id": "00000000-0000-0000-0000-000000000003",
        "name": "Test Camera UC3",
        "location": "Development",
        "video_path": "/app/test_data/videos/uc3.mp4",
        "use_cases": ["uc3"],
        "fps": 10,
    },
    {
        "id": "00000000-0000-0000-0000-000000000004",
        "name": "Test Camera UC4",
        "location": "Development",
        "video_path": "/app/test_data/videos/uc4.mp4",
        "use_cases": ["uc4"],
        "fps": 10,
    },
]

USERS = [
    {
        "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "name": "Platform Admin",
        "email": "admin@innovision.com",
        "password": DEV_PASSWORD,
        "role": "superadmin",
        "camera_ids": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
            "00000000-0000-0000-0000-000000000004",
        ],
    },
    {
        "id": "ffffffff-ffff-ffff-ffff-fffffffffff1",
        "name": "Development Operator",
        "email": "operator@innovision.com",
        "password": DEV_PASSWORD,
        "role": "operator",
        "camera_ids": [
            "00000000-0000-0000-0000-000000000001",
        ],
    },
    {
        "id": "ffffffff-ffff-ffff-ffff-fffffffffff2",
        "name": "Development Viewer",
        "email": "viewer@innovision.com",
        "password": DEV_PASSWORD,
        "role": "viewer",
        "camera_ids": [
            "00000000-0000-0000-0000-000000000001",
        ],
    },
    {
        "id": "ffffffff-ffff-ffff-ffff-fffffffffff3",
        "name": "Development Admin",
        "email": "devadmin@innovision.com",
        "password": DEV_PASSWORD,
        "role": "admin",
        "camera_ids": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
    },
]

async def seed_cameras(session):
    for camera in CAMERAS:
        await session.execute(
            text(
                """
                INSERT INTO cameras
                    (id, name, location, rtsp_url, status, use_cases, fps)
                VALUES
                    (:id, :name, :location, :video_path, 'offline', :use_cases, :fps)
                ON CONFLICT (id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    location = EXCLUDED.location,
                    rtsp_url = EXCLUDED.rtsp_url,
                    use_cases = EXCLUDED.use_cases,
                    fps = EXCLUDED.fps,
                    updated_at = now()
                """
            ),
            camera,
        )
        print(
            f"Camera ready: {camera['name']} "
            f"→ {camera['video_path']}"
        )

async def seed_users(session):
    for user in USERS:
        password_hash = hash_password(user["password"])
        await session.execute(
            text(
                """
                INSERT INTO users
                    (id, name, email, password_hash, role, camera_ids)
                VALUES
                    (:id, :name, :email, :password_hash, :role, :camera_ids)
                ON CONFLICT (email)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role,
                    camera_ids = EXCLUDED.camera_ids,
                    updated_at = now()
                """
            ),
            {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "password_hash": password_hash,
                "role": user["role"],
                "camera_ids": [
                    uuid.UUID(camera_id)
                    for camera_id in user["camera_ids"]
                ],
            },
        )
        print(
            f"User ready: {user['email']} "
            f"({user['role']})"
        )

async def main():
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as session:
            await seed_cameras(session)
            await seed_users(session)

        print()
        print("Development seed completed.")
        print()
        print(f"Development password: {DEV_PASSWORD}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())