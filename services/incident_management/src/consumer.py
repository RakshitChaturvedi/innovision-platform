"""
Incidents are created by Alert Management (incident_trigger.py), not here. this consumer exists 
as an extension point for future automated incident actions — e.g. auto-closing incidents whose
triggering alert condition resolves upstream (an intruder leaving the zone, a fire being cleared).
"""
import logging

logger = logging.getLogger(__name__)

class IncidentAutoResolveConsumer:
    #Placeholder consumer. Currently a no-op loop, kept as an explicit file (not deleted) so the extension point is documented in code, not just in this comment.
    async def start(self) -> None:
        logger.info("incident_auto_resolve_consumer_idle (no-op in Phase 3)")