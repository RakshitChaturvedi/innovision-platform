"""
Autonomous Platform Bootstrap Script for Clean/Fresh Systems.
Executes:
1. PostgreSQL availability check
2. Alembic migration execution to HEAD
3. Camera seed reconciliation (with demo video paths for zero-camera environments)
4. MinIO availability check & bucket creation
5. Redis availability check & stream/consumer group creation
"""
import os
import sys
import time
import logging

from alembic.config import Config
from alembic import command
from minio import Minio
from minio.error import S3Error
import redis
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("platform.init")

def get_env(key: str, default: str) -> str:
    return os.environ.get(key, default)

def wait_for_postgres(sync_db_url: str, max_retries: int = 30) -> None:
    logger.info("Waiting for PostgreSQL connection...")
    engine = create_engine(sync_db_url)
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✓ PostgreSQL is ready and accepting queries.")
            return
        except Exception as e:
            logger.info(f"  Postgres not ready yet ({i+1}/{max_retries}): {e}")
            time.sleep(2)
    raise RuntimeError("PostgreSQL did not become ready in time.")

def run_migrations() -> None:
    logger.info("Executing database migrations via Alembic...")
    ini_path = "migrations/alembic.ini" if os.path.exists("migrations/alembic.ini") else "/app/migrations/alembic.ini"
    alembic_cfg = Config(ini_path)
    command.upgrade(alembic_cfg, "head")
    logger.info("✓ Database migrations applied to HEAD.")

def seed_cameras(sync_db_url: str) -> None:
    logger.info("Reconciling seed cameras...")
    engine = create_engine(sync_db_url)
    seed_sql = text("""
        INSERT INTO cameras (id, name, location, status, use_cases, rtsp_url)
        VALUES
            ('00000000-0000-0000-0000-000000000001', 'Camera 1 (Floor A)', 'Shop Floor A', 'online', ARRAY['uc1'], '/app/test_data/videos/uc1.mp4'),
            ('00000000-0000-0000-0000-000000000002', 'Camera 2 (Boiler Room)', 'Boiler Room West', 'online', ARRAY['uc2'], '/app/test_data/videos/uc2.mp4'),
            ('00000000-0000-0000-0000-000000000003', 'Camera 3 (Safety Zone)', 'Assembly Bay 3', 'online', ARRAY['uc3'], '/app/test_data/videos/uc3.mp4'),
            ('00000000-0000-0000-0000-000000000004', 'Camera 4 (Gate Perimeter)', 'Vehicle Gate B', 'online', ARRAY['uc4'], '/app/test_data/videos/uc4.mp4')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            location = EXCLUDED.location,
            status = 'online',
            rtsp_url = EXCLUDED.rtsp_url;
    """)
    with engine.begin() as conn:
        conn.execute(seed_sql)
    logger.info("✓ Seed cameras reconciled with active demo stream paths.")

def init_minio(endpoint: str, access_key: str, secret_key: str, max_retries: int = 30) -> None:
    logger.info(f"Connecting to MinIO ({endpoint})...")
    client = Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=False,
    )
    for i in range(max_retries):
        try:
            client.list_buckets()
            break
        except Exception as e:
            logger.info(f"  MinIO not ready yet ({i+1}/{max_retries}): {e}")
            time.sleep(2)
    else:
        raise RuntimeError("MinIO did not become ready in time.")

    buckets = [
        "innovision-frames",
        "innovision-snapshots",
        "innovision-evidence",
        "innovision-reports",
    ]
    for b in buckets:
        try:
            if not client.bucket_exists(b):
                client.make_bucket(b)
                logger.info(f"  Created MinIO bucket: {b}")
            else:
                logger.info(f"  MinIO bucket exists: {b}")
        except S3Error as e:
            logger.error(f"  Failed bucket {b}: {e}")
            raise
    logger.info("✓ MinIO buckets verified.")

def init_redis(redis_url: str, max_retries: int = 30) -> None:
    logger.info(f"Connecting to Redis ({redis_url})...")
    r = redis.Redis.from_url(redis_url, decode_responses=True)
    for i in range(max_retries):
        try:
            r.ping()
            break
        except Exception as e:
            logger.info(f"  Redis not ready yet ({i+1}/{max_retries}): {e}")
            time.sleep(1)
    else:
        raise RuntimeError("Redis did not become ready in time.")

    streams = {
        "alerts:live": ["alert_management_group"],
        "alerts:dead_letter": ["dead_letter_review_group"],
        "incidents:live": ["incident_management_group"],
        "notifications:live": ["notification_group"],
        "frames:00000000-0000-0000-0000-000000000001": ["uc1_v2_group"],
        "frames:00000000-0000-0000-0000-000000000002": ["uc2_fire_smoke_cg"],
        "frames:00000000-0000-0000-0000-000000000003": ["uc3_ppe_group"],
    }
    for stream, groups in streams.items():
        for group in groups:
            try:
                r.xgroup_create(stream, group, id="0", mkstream=True)
                logger.info(f"  Created stream group: {stream} -> {group}")
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"  Stream group exists: {stream} -> {group}")
                else:
                    logger.error(f"  Stream group error: {e}")
                    raise
    logger.info("✓ Redis streams and consumer groups verified.")

def main():
    logger.info("==================================================")
    logger.info("   INNOVISION PLATFORM BOOTSTRAP INITIALIZATION   ")
    logger.info("==================================================")

    db_url = get_env("DATABASE_URL", "postgresql+asyncpg://innovision:changeme@postgres:5432/innovision_platform")
    sync_db_url = db_url.replace("+asyncpg", "").replace("+psycopg2", "")

    redis_host = get_env("REDIS_HOST", "redis")
    redis_port = get_env("REDIS_PORT", "6379")
    redis_url = f"redis://{redis_host}:{redis_port}"

    minio_endpoint = get_env("MINIO_ENDPOINT", "minio:9000")
    minio_access = get_env("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret = get_env("MINIO_SECRET_KEY", "changeme")

    wait_for_postgres(sync_db_url)
    run_migrations()
    seed_cameras(sync_db_url)
    init_minio(minio_endpoint, minio_access, minio_secret)
    init_redis(redis_url)

    logger.info("==================================================")
    logger.info("✓ PLATFORM BOOTSTRAP COMPLETE — ALL SYSTEMS READY")
    logger.info("==================================================")

if __name__ == "__main__":
    main()
