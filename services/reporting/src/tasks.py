"""
Celery task for async PDF generation.
Async because cross-UC aggregation over a wide date range can take
real time — the operator shouldn't block an HTTP request on it.
"""
import asyncio
import logging
from datetime import datetime
from celery import Celery
from sqlalchemy import create_engine, text

from shared.platform_client.db import get_session_factory
from .config import settings
from .generators.incident_report import generate_incident_report
from .generators.alert_summary import generate_alert_summary
from .generators.camera_health import generate_camera_health
from .generators.compliance_summary import generate_compliance_summary
from .pdf_writer import write_pdf
from .storage import upload_report

logger = logging.getLogger(__name__)
celery_app = Celery("reporting", broker=settings.celery_broker_url)

GENERATORS = {
    "incident_summary": generate_incident_report,
    "alert_volume": generate_alert_summary,
    "camera_health": generate_camera_health,
    "compliance_summary": generate_compliance_summary,
}


@celery_app.task(name="reporting.generate_report_task")
def generate_report_task(
    report_id: str, report_type: str, date_start: str, date_end: str,
    camera_ids: list[str] | None = None,
):
    generator = GENERATORS.get(report_type)
    if not generator:
        logger.error("unknown_report_type type=%s report_id=%s", report_type, report_id)
        _update_status(report_id, "failed")
        return

    try:
        session_factory = get_session_factory(settings.database_url)
        data = asyncio.run(generator(
            session_factory=session_factory,
            date_start=datetime.fromisoformat(date_start),
            date_end=datetime.fromisoformat(date_end),
            camera_ids=camera_ids,
        ))

        pdf_bytes = write_pdf(report_type, data)
        object_key = f"{datetime.now().strftime('%Y-%m')}/{report_id}.pdf"
        upload_report(object_key, pdf_bytes)
        _update_status(report_id, "complete", object_key)

        logger.info("report_generated id=%s type=%s", report_id, report_type)
    except Exception as e:
        logger.error("report_generation_failed id=%s error=%s", report_id, e)
        _update_status(report_id, "failed")


def _update_status(report_id: str, status: str, object_key: str | None = None) -> None:
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                UPDATE reports SET status = :status, object_key = :object_key,
                    completed_at = CASE WHEN :status = 'complete' THEN now() ELSE completed_at END
                WHERE id = :id
            """), {"status": status, "object_key": object_key, "id": report_id})