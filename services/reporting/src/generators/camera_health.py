"""Camera uptime and reliability metrics."""
from datetime import datetime
from sqlalchemy import text


async def generate_camera_health(
    session_factory, date_start: datetime, date_end: datetime, camera_ids: list[str] | None = None,
) -> dict:
    async with session_factory() as session:
        camera_filter = "WHERE id = ANY(:camera_ids)" if camera_ids else ""
        params = {"camera_ids": camera_ids} if camera_ids else {}

        rows = await session.execute(text(f"""
            SELECT id, name, status, fps, created_at, updated_at
            FROM cameras {camera_filter}
        """), params)
        cameras = [dict(r._mapping) for r in rows.fetchall()]

    return {
        "report_type": "camera_health",
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "total_cameras": len(cameras),
        "online": sum(1 for c in cameras if c["status"] == "online"),
        "offline": sum(1 for c in cameras if c["status"] == "offline"),
        "reconnecting": sum(1 for c in cameras if c["status"] == "reconnecting"),
        "cameras": cameras,
    }