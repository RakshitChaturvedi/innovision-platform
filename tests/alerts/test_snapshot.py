"""
Tests for GET /alerts/{alert_id}/snapshot endpoint.
Uses a fake Minio client — no running MinIO needed.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        alert_id TEXT UNIQUE NOT NULL,
        camera_id TEXT,
        source_uc TEXT,
        alert_type TEXT,
        severity TEXT,
        title TEXT,
        description TEXT,
        source_event_id TEXT,
        frame_reference TEXT,
        frame_provider TEXT,
        status TEXT DEFAULT 'pending',
        metadata TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        acknowledged_at TEXT,
        acknowledged_by TEXT,
        resolved_at TEXT,
        resolved_by TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        service TEXT, action TEXT, entity_type TEXT,
        entity_id TEXT, user_id TEXT, source_uc TEXT,
        metadata TEXT, created_at TEXT DEFAULT (datetime('now'))
    )
    """,
]

FAKE_USER = {"sub": "user-001", "role": "operator", "camera_ids": []}
ALERT_ID = "alert-uuid-0001"
FRAME_REF = "uc3/alerts/2026-09-28/snap.jpg"
PRESIGNED_URL = "http://localhost:9000/innovision-snapshots/uc3/alerts/2026-09-28/snap.jpg?X-Amz-Signature=abc"


import pytest_asyncio


@pytest_asyncio.fixture(scope="module")
async def db_factory():
    from datetime import datetime, timezone
    from sqlalchemy import event as sa_event

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _now(conn, _):
        conn.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    async with engine.begin() as conn:
        for ddl in _DDL:
            await conn.exec_driver_sql(ddl)
        # Alert with frame_reference
        await conn.exec_driver_sql(
            "INSERT INTO alerts (id, alert_id, frame_reference, source_uc, severity, title, description, source_event_id, alert_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("row-1", ALERT_ID, FRAME_REF, "uc3", "high", "PPE", "desc", "ev-1", "ppe_violation"),
        )
        # Alert without frame_reference
        await conn.exec_driver_sql(
            "INSERT INTO alerts (id, alert_id, frame_reference, source_uc, severity, title, description, source_event_id, alert_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("row-2", "alert-no-snap", None, "uc3", "low", "No snap", "desc", "ev-2", "ppe_violation"),
        )

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


def build_app(db_factory):
    from services.alert_management.src.router import router, get_db
    from services.auth.src.rbac import get_current_user
    import services.alert_management.src.router as router_module

    app = FastAPI()

    async def _fake_db():
        async with db_factory() as s:
            yield s

    async def _fake_user(authorization: str = ""):
        return FAKE_USER

    app.include_router(router)
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user
    # Also override the router module's direct reference if it imported separately
    if hasattr(router_module, 'get_current_user'):
        app.dependency_overrides[router_module.get_current_user] = _fake_user
    return app


@pytest.mark.asyncio
async def test_snapshot_returns_presigned_url(db_factory):
    """Alert with frame_reference → 200 with presigned URL."""
    app = build_app(db_factory)

    fake_minio = MagicMock()
    fake_minio.presigned_get_object = MagicMock(return_value=PRESIGNED_URL)

    with patch("services.alert_management.src.router._minio_public", fake_minio):
        with TestClient(app) as client:
            resp = client.get(f"/alerts/{ALERT_ID}/snapshot")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["url"] == PRESIGNED_URL
    assert body["expires_in"] == 300


@pytest.mark.asyncio
async def test_snapshot_404_no_frame_reference(db_factory):
    """Alert with no frame_reference → 404."""
    app = build_app(db_factory)

    with TestClient(app) as client:
        resp = client.get("/alerts/alert-no-snap/snapshot")

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_snapshot_404_unknown_alert(db_factory):
    """Unknown alert_id → 404."""
    app = build_app(db_factory)

    with TestClient(app) as client:
        resp = client.get("/alerts/does-not-exist/snapshot")

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_snapshot_502_on_minio_error(db_factory):
    """MinIO raises → 502."""
    app = build_app(db_factory)

    fake_minio = MagicMock()
    fake_minio.presigned_get_object = MagicMock(side_effect=Exception("MinIO down"))

    with patch("services.alert_management.src.router._minio_public", fake_minio):
        with TestClient(app) as client:
            resp = client.get(f"/alerts/{ALERT_ID}/snapshot")

    assert resp.status_code == 502, resp.text
