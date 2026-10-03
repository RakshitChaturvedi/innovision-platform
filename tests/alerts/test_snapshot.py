"""
Tests for GET /alerts/{alert_id}/snapshot endpoint and alert management security/404 handling.
Uses a fake Minio client — no running MinIO needed.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from minio.error import S3Error

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

FAKE_USER = {"sub": "user-001", "role": "operator", "camera_ids": ["cam-1"]}
ALERT_ID = "alert-uuid-0001"
FRAME_REF = "uc3/alerts/2026-09-28/snap.jpg"
PUBLIC_ENDPOINT = "localhost:9000"
PRESIGNED_URL = "http://localhost:9000/innovision-snapshots/uc3/alerts/2026-09-28/snap.jpg?X-Amz-Signature=abc"


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
        # Alert with frame_reference & camera_id cam-1
        await conn.exec_driver_sql(
            "INSERT INTO alerts (id, alert_id, camera_id, frame_reference, source_uc, severity, title, description, source_event_id, alert_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("row-1", ALERT_ID, "cam-1", FRAME_REF, "uc3", "high", "PPE", "desc", "ev-1", "ppe_violation"),
        )
        # Alert without frame_reference
        await conn.exec_driver_sql(
            "INSERT INTO alerts (id, alert_id, camera_id, frame_reference, source_uc, severity, title, description, source_event_id, alert_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("row-2", "alert-no-snap", "cam-1", None, "uc3", "low", "No snap", "desc", "ev-2", "ppe_violation"),
        )
        # Alert on forbidden camera
        await conn.exec_driver_sql(
            "INSERT INTO alerts (id, alert_id, camera_id, frame_reference, source_uc, severity, title, description, source_event_id, alert_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("row-3", "alert-forbidden-cam", "cam-forbidden", "uc1/alerts/snap.jpg", "uc1", "low", "Forbidden", "desc", "ev-3", "ppe_violation"),
        )

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


def build_app(db_factory, user=FAKE_USER):
    from services.alert_management.src.router import router, get_db
    from services.auth.src.rbac import get_current_user
    import services.alert_management.src.router as router_module

    app = FastAPI()

    async def _fake_db():
        async with db_factory() as s:
            yield s

    async def _fake_user(authorization: str = ""):
        return user

    app.include_router(router)
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user
    if hasattr(router_module, 'get_current_user'):
        app.dependency_overrides[router_module.get_current_user] = _fake_user
    return app


@pytest.mark.asyncio
async def test_snapshot_returns_presigned_url(db_factory):
    """Alert with frame_reference → 200 with presigned URL using public endpoint."""
    app = build_app(db_factory)

    fake_minio = MagicMock()
    fake_minio.presigned_get_object = MagicMock(return_value=PRESIGNED_URL)

    with patch("services.alert_management.src.router._minio_public", fake_minio):
        with TestClient(app) as client:
            resp = client.get(f"/alerts/{ALERT_ID}/snapshot")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert PUBLIC_ENDPOINT in body["url"]
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
async def test_snapshot_403_forbidden_camera(db_factory):
    """Snapshot for alert on camera user has no access to → 403."""
    app = build_app(db_factory)
    with TestClient(app) as client:
        resp = client.get("/alerts/alert-forbidden-cam/snapshot")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_snapshot_404_object_missing_in_minio(db_factory):
    """Missing object in MinIO (S3Error NoSuchKey) → 404."""
    app = build_app(db_factory)

    s3_err = S3Error("NoSuchKey", "The specified key does not exist.", "resource", "request_id", "host_id", None)
    fake_minio = MagicMock()
    fake_minio.presigned_get_object = MagicMock(side_effect=s3_err)

    with patch("services.alert_management.src.router._minio_public", fake_minio):
        with TestClient(app) as client:
            resp = client.get(f"/alerts/{ALERT_ID}/snapshot")

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_acknowledge_unknown_returns_404(db_factory):
    """Unknown alert_id acknowledge → 404."""
    app = build_app(db_factory)
    with patch("services.alert_management.src.router.write_audit_entry", new=MagicMock()):
        with TestClient(app) as client:
            resp = client.patch("/alerts/does-not-exist/acknowledge")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_resolve_unknown_returns_404(db_factory):
    """Unknown alert_id resolve → 404."""
    app = build_app(db_factory)
    with patch("services.alert_management.src.router.write_audit_entry", new=MagicMock()):
        with TestClient(app) as client:
            resp = client.patch("/alerts/does-not-exist/resolve")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_acknowledge_forbidden_camera_returns_403(db_factory):
    """Acknowledge on alert from forbidden camera → 403."""
    app = build_app(db_factory)
    with patch("services.alert_management.src.router.write_audit_entry", new=MagicMock()):
        with TestClient(app) as client:
            resp = client.patch("/alerts/alert-forbidden-cam/acknowledge")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_status_counts(db_factory):
    """GET /alerts/status-counts returns status count breakdown."""
    admin_user = {"sub": "admin-001", "role": "admin", "camera_ids": []}
    app = build_app(db_factory, user=admin_user)
    with TestClient(app) as client:
        resp = client.get("/alerts/status-counts")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "pending" in data
    assert "acknowledged" in data
    assert "resolved" in data
