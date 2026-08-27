"""
Writes one row to notification_log per delivery attempt.
This is the audit trail answering "did anyone actually get notified?"
Separate from the platform audit_log — this is delivery-specific detail
(channel, success/failure) rather than a general platform action record.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def log_delivery(
    session: AsyncSession,
    alert_row_id: str,
    user_id: str | None,
    channel: str,
    success: bool,
    error: str | None = None,
) -> None:
    await session.execute(text("""
        INSERT INTO notification_log (id, alert_id, user_id, channel, status, error, sent_at)
        VALUES (:id, :alert_id, :user_id, :channel, :status, :error, now())
    """), {
        "id": str(uuid.uuid4()),
        "alert_id": alert_row_id,
        "user_id": user_id,
        "channel": channel,
        "status": "sent" if success else "failed",
        "error": error,
    })