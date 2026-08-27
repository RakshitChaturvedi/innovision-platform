"""Alert volume grouped by UC, type, severity, camera, and day."""
from datetime import datetime
from collections import defaultdict
from ..aggregator import alerts_in_range


async def generate_alert_summary(
    session_factory, date_start: datetime, date_end: datetime, camera_ids: list[str] | None = None,
) -> dict:
    async with session_factory() as session:
        alerts = await alerts_in_range(session, date_start, date_end, camera_ids)

    by_uc = defaultdict(int)
    by_severity = defaultdict(int)
    by_type = defaultdict(int)
    by_camera = defaultdict(int)
    by_day = defaultdict(int)

    for a in alerts:
        by_uc[a["source_uc"]] += 1
        by_severity[a["severity"]] += 1
        by_type[a["alert_type"]] += 1
        by_camera[a["camera_name"]] += 1
        by_day[a["created_at"].strftime("%Y-%m-%d")] += 1

    return {
        "report_type": "alert_volume",
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "total_alerts": len(alerts),
        "by_source_uc": dict(by_uc),
        "by_severity": dict(by_severity),
        "by_alert_type": dict(by_type),
        "by_camera": dict(by_camera),
        "by_day": dict(sorted(by_day.items())),
    }