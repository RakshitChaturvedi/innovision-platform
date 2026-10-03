"""
Combines UC compliance readiness and metrics data across UC1-UC4 into one
cross-UC compliance report.

Each use-case URL call handles failures gracefully so an unreachable UC source
never causes the overall report generation to fail.
"""
import logging
import httpx
from datetime import datetime
from ..config import settings

logger = logging.getLogger(__name__)


async def generate_compliance_summary(
    session_factory, date_start: datetime, date_end: datetime, camera_ids: list[str] | None = None,
) -> dict:
    uc1_data, uc2_data, uc3_data, uc4_data = {}, {}, {}, {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(settings.uc1_compliance_url)
            resp.raise_for_status()
            uc1_data = resp.json()
        except Exception as e:
            logger.warning("uc1_compliance_fetch_failed error=%s", e)
            uc1_data = {"error": "UC1 compliance data unavailable", "status": "source_unavailable"}

        try:
            resp = await client.get(settings.uc2_compliance_url)
            resp.raise_for_status()
            uc2_data = resp.json()
        except Exception as e:
            logger.warning("uc2_compliance_fetch_failed error=%s", e)
            uc2_data = {"error": "UC2 compliance data unavailable", "status": "source_unavailable"}

        try:
            resp = await client.get(settings.uc3_ppe_metrics_url)
            resp.raise_for_status()
            uc3_data = resp.json()
        except Exception as e:
            logger.warning("uc3_ppe_fetch_failed error=%s", e)
            uc3_data = {"error": "UC3 PPE data unavailable", "status": "source_unavailable"}

        try:
            resp = await client.get(settings.uc4_compliance_url)
            resp.raise_for_status()
            uc4_data = resp.json()
        except Exception as e:
            logger.warning("uc4_compliance_fetch_failed error=%s", e)
            uc4_data = {"error": "UC4 compliance data unavailable", "status": "source_unavailable"}

    return {
        "report_type": "compliance_summary",
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "dpdp_readiness": uc1_data,
        "uc2_compliance": uc2_data,
        "ppe_compliance": uc3_data,
        "uc4_compliance": uc4_data,
    }