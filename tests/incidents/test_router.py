"""
Tests for incident management router.
Uses SQLite + aiosqlite — no Postgres needed.
Auth is bypassed via dependency_overrides on get_current_user
(require_role internally Depends on it, so the override propagates automatically).
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------
_DDL = [
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY,
        alert_id TEXT,
        title TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        assigned_to TEXT,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        resolved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS incident_timeline (
        id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        user_id TEXT,
        action TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT,
        note TEXT,
        timestamp TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        service TEXT,
        action TEXT,
        entity_type TEXT,
        entity_id TEXT,
        user_id TEXT,
        source_uc TEXT,
        metadata TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """,
]

FAKE_USER = {"sub": "user-001", "role": "operator", "camera_ids": []}
INCIDENT_ID = "inc-0001"
UNKNOWN_ID  = "inc-9999"


@pytest_asyncio.fixture(scope="module")
async def db_factory():
    from datetime import datetime, timezone

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # SQLite doesn't have now() — register it so the router's raw SQL works
    from sqlalchemy import event as sa_event

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _register_now(dbapi_conn, _):
        dbapi_conn.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    async with engine.begin() as conn:
        for ddl in _DDL:
            await conn.exec_driver_sql(ddl)
        await conn.exec_driver_sql(
            "INSERT INTO incidents (id, title, status) VALUES (?, ?, ?)",
            (INCIDENT_ID, "Test Incident", "active"),
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


def build_app(db_factory):
    """Build the FastAPI app with auth and DB overridden."""
    from services.incident_management.src.router import router, get_db
    from services.auth.src.rbac import get_current_user

    app = FastAPI()

    async def _fake_db():
        async with db_factory() as session:
            yield session

    async def _fake_user(authorization: str = ""):
        return FAKE_USER

    app.include_router(router)
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_status_success(db_factory):
    """status update transitions active→acknowledged and returns 200."""
    app = build_app(db_factory)
    with patch("services.incident_management.src.router.write_audit_entry", new=AsyncMock()):
        with TestClient(app) as client:
            resp = client.patch(
                f"/incidents/{INCIDENT_ID}/status",
                params={"new_status": "acknowledged"},
            )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_update_status_unknown_returns_404(db_factory):
    app = build_app(db_factory)
    with patch("services.incident_management.src.router.write_audit_entry", new=AsyncMock()):
        with TestClient(app) as client:
            resp = client.patch(
                f"/incidents/{UNKNOWN_ID}/status",
                params={"new_status": "acknowledged"},
            )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_assign_success(db_factory):
    app = build_app(db_factory)
    with patch("services.incident_management.src.router.write_audit_entry", new=AsyncMock()):
        with TestClient(app) as client:
            resp = client.patch(
                f"/incidents/{INCIDENT_ID}/assign",
                params={"assignee_id": "op-42"},
            )
    assert resp.status_code == 200, resp.text
    assert resp.json()["assigned_to"] == "op-42"


@pytest.mark.asyncio
async def test_assign_unknown_returns_404(db_factory):
    app = build_app(db_factory)
    with patch("services.incident_management.src.router.write_audit_entry", new=AsyncMock()):
        with TestClient(app) as client:
            resp = client.patch(
                f"/incidents/{UNKNOWN_ID}/assign",
                params={"assignee_id": "op-42"},
            )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_add_note_unknown_returns_404(db_factory):
    app = build_app(db_factory)
    with patch("services.incident_management.src.router.write_audit_entry", new=AsyncMock()):
        with TestClient(app) as client:
            resp = client.post(
                f"/incidents/{UNKNOWN_ID}/notes",
                params={"note": "test note"},
            )
    assert resp.status_code == 404, resp.text
