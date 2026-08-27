"""Cross-UC incident summary — alert-to-resolution lifecycle."""
from datetime import datetime
from sqlalchemy  import text
from ..aggregator import incidents_in_range


async def incidents_in_range(
    session,
    date_start,
    date_end,
    camera_ids=None,
):
    camera_filter = ""
    params = {
        "start": date_start,
        "end": date_end,
    }

    if camera_ids:
        camera_filter = "AND a.camera_id = ANY(:camera_ids)"
        params["camera_ids"] = camera_ids

    rows = await session.execute(
        text(f"""
            SELECT
                i.*,
                a.source_uc,
                a.alert_type,
                a.severity,
                a.camera_id,
                a.created_at AS alert_created_at
            FROM incidents i
            JOIN alerts a ON a.id = i.alert_id
            WHERE a.created_at BETWEEN :start AND :end
            {camera_filter}
            ORDER BY a.created_at DESC
        """),
        params,
    )

async def generate_incident_report(
    session_factory, date_start: datetime, date_end: datetime, camera_ids: list[str] | None = None,
) -> dict:
    async with session_factory() as session:
        incidents = await incidents_in_range(session, date_start, date_end, camera_ids)

    by_uc: dict[str, int] = {}
    resolution_times = []
    for i in incidents:
        by_uc[i["source_uc"]] = by_uc.get(i["source_uc"], 0) + 1
        if i.get("resolved_at") and i.get("alert_created_at"):
            minutes = (i["resolved_at"] - i["alert_created_at"]).total_seconds() / 60
            resolution_times.append(minutes)

    return {
        "report_type": "incident_summary",
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "total_incidents": len(incidents),
        "by_source_uc": by_uc,
        "avg_resolution_minutes": (
            round(sum(resolution_times) / len(resolution_times), 1)
            if resolution_times else None
        ),
        "incidents": incidents,
    }