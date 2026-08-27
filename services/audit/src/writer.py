"""
The append-only audit log writer.
Imported as a shared library by Auth, Alert Management, Incident
Management, and Camera Registry — called SYNCHRONOUSLY inside their
own request handlers, in the same transaction as the action being
audited wherever possible.

Deliberately takes a session_factory rather than an existing session
in most call sites shown here, because those call sites are firing
after their own transaction has already committed (e.g. router.py
patterns above) — this opens a fresh short-lived transaction just
for the audit row. Where the call site is ALREADY inside an open
transaction (see alert_management/consumer.py), pass that session's
factory but be aware the audit write there commits with the outer
transaction since it uses the same session.
"""
import logging
import uuid
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def write_audit_entry(
    session_factory,
    service: str,
    action: str,
    entity_type: str,
    entity_id: str,
    user_id: str | None = None,
    source_uc: str | None = None,
    metadata: dict | None = None,
    session = None
) -> None:
    async def _write(session):
        await session.execute(
            text("""
                INSERT INTO audit_log
                    (id, service, action, entity_type, entity_id,
                     user_id, source_uc, metadata, timestamp)
                VALUES
                    (:id, :service, :action, :entity_type, :entity_id,
                     :user_id, :source_uc, :metadata, now())
            """),
            {
                "id": str(uuid.uuid4()),
                "service": service,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "user_id": user_id,
                "source_uc": source_uc,
                "metadata": metadata or {},
            },
        )
    if session is not None:
        await _write(session)
    else:
        async with session_factory() as new_session:
            async with new_session.begin():
                await _write(new_session)