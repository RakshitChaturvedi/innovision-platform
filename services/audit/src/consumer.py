"""
Reserved extension point.
Current design writes audit entries synchronously via writer.py
at the point of action (see module docstring there for why).
This consumer is kept as an explicit no-op so a future move to
event-sourced auditing (services publish to `audit:events`, this
consumer picks them up) has an obvious place to land without
restructuring the service.
"""
import logging

logger = logging.getLogger(__name__)


class AuditEventConsumer:
    async def start(self) -> None:
        logger.info("audit_event_consumer_idle (writer.py handles sync writes in Phase 3)")