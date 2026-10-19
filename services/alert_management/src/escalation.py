import logging
import redis

try:
    from celery import Celery
    celery_app = Celery("alert_escalation", broker=settings.celery_broker_url)
    _task_deco = celery_app.task
except ImportError:
    celery_app = None
    def _task_deco(*args, **kwargs):
        def wrapper(fn):
            fn.apply_async = lambda *a, **kw: None
            return fn
        return wrapper

from sqlalchemy import create_engine, text
from .config import settings

logger = logging.getLogger(__name__)

@_task_deco(name="alert_management.escalation_check")
def escalation_check(alert_row_id: str, level: int = 1):
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)

    with engine.connect() as conn:
        row  = conn.execute(text("""
            SELECT status, severity, camera_id FROM alerts WHERE id = :id
        """), {"id": alert_row_id}).fetchone()

        if not row:
            logger.warning("escalation_alert_not_found id=%s", alert_row_id)
            return
        if row.status != "pending":
            logger.info("escalation_stopped_already_handled id=%s status=%s", alert_row_id, row.status)
            return
        logger.warning("alert_escalating id=%s level=%d severity=%s", alert_row_id, level, row.severity)

        r = redis.Redis(host=settings.redis_host, port=settings.redis_port)
        r.xadd(settings.notifications_stream, {
            "alert_id": alert_row_id,
            "camera_id": str(row.camera_id),
            "level": str(level),
            "severity": row.severity
        })

    if level == 1:
        escalation_check.apply_async(args=[alert_row_id, 2], countdown=settings.escalation_level_2_delay_s)
    elif level == 2:
        escalation_check.apply_async(args=[alert_row_id, 3], countdown=settings.escalation_level_3_delay_s)
