"""
Combines UC1's DPDP compliance readiness data with UC3's PPE metrics
into one cross-UC compliance report.

This file makes the ONE sanctioned direct HTTP call from Platform
Services into UC-owned APIs — compliance reporting is explicitly a
platform-visible UC responsibility per the integration contract,
not an internal implementation detail being leaked.
"""
import logging
import httpx
from datetime import datetime
from ..config import settings

logger = logging.getLogger(__name__)


async def generate_compliance_summary(
    session_factory, date_start: datetime, date_end: datetime, camera_ids: list[str] | None = None,
) -> dict:
    uc1_data, uc3_data = {}, {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(settings.uc1_compliance_url)
            resp.raise_for_status()
            uc1_data = resp.json()
        except Exception as e:
            logger.warning("uc1_compliance_fetch_failed error=%s", e)
            uc1_data = {"error": "UC1 compliance data unavailable"}

        try:
            resp = await client.get(settings.uc3_ppe_metrics_url)
            resp.raise_for_status()
            uc3_data = resp.json()
        except Exception as e:
            logger.warning("uc3_ppe_fetch_failed error=%s", e)
            uc3_data = {"error": "UC3 PPE data unavailable"}

    return {
        "report_type": "compliance_summary",
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "dpdp_readiness": uc1_data,
        "ppe_compliance": uc3_data,
    }