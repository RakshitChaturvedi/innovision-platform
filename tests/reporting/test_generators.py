"""
Tests for reporting generators and pdf_writer.
No Postgres or MinIO needed — sessions are faked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------
DATE_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
DATE_END   = datetime(2026, 9, 30, tzinfo=timezone.utc)

SAMPLE_INCIDENTS = [
    {
        "id": "inc-1",
        "alert_id": "a-1",
        "title": "PPE Violation",
        "status": "resolved",
        "source_uc": "uc3",
        "alert_type": "ppe_violation",
        "severity": "high",
        "alert_created_at": datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
        "resolved_at": datetime(2026, 9, 10, 8, 30, tzinfo=timezone.utc),
        "camera_id": "00000000-0000-0000-0000-000000000003",
    },
    {
        "id": "inc-2",
        "alert_id": "a-2",
        "title": "Intruder",
        "status": "active",
        "source_uc": "uc1",
        "alert_type": "intruder_detected",
        "severity": "critical",
        "alert_created_at": datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc),
        "resolved_at": None,
        "camera_id": "00000000-0000-0000-0000-000000000001",
    },
]


def _make_session_factory(return_value):
    """Returns an async context-manager session factory that yields a fake session."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            fetchall=MagicMock(return_value=[
                MagicMock(_mapping=row) for row in return_value
            ])
        )
    )
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=mock_session)


# ---------------------------------------------------------------------------
# Test: incident_report generator no longer returns None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_incident_report_returns_dict():
    """generate_incident_report must return a dict, not None (shadow-function bug)."""
    from unittest.mock import patch

    factory = _make_session_factory(SAMPLE_INCIDENTS)

    with patch(
        "services.reporting.src.generators.incident_report.incidents_in_range",
        new=AsyncMock(return_value=SAMPLE_INCIDENTS),
    ):
        from services.reporting.src.generators.incident_report import generate_incident_report
        result = await generate_incident_report(factory, DATE_START, DATE_END)

    assert result is not None, "generate_incident_report must not return None"
    assert result["report_type"] == "incident_summary"
    assert result["total_incidents"] == 2
    assert result["by_source_uc"]["uc3"] == 1
    assert result["by_source_uc"]["uc1"] == 1
    # Only inc-1 has resolved_at
    assert result["avg_resolution_minutes"] == 30.0


@pytest.mark.asyncio
async def test_incident_report_no_shadow_incidents_in_range():
    """The local incidents_in_range shadow is gone — import comes from aggregator."""
    import services.reporting.src.generators.incident_report as mod
    import inspect
    # The module should NOT define its own incidents_in_range
    assert not hasattr(mod, "incidents_in_range") or \
        mod.incidents_in_range.__module__ != mod.__name__, \
        "incidents_in_range must not be defined locally in incident_report.py"


# ---------------------------------------------------------------------------
# Test: pdf_writer renders nested dicts and lists (not just scalars)
# ---------------------------------------------------------------------------
def test_pdf_writer_includes_nested_content():
    """PDF must contain content from dict and list fields, not just scalar summary."""
    from services.reporting.src.pdf_writer import write_pdf

    data = {
        "report_type": "incident_summary",
        "date_start": "2026-09-01",
        "date_end": "2026-09-30",
        "total_incidents": 2,
        "by_source_uc": {"uc3": 1, "uc1": 1},
        "avg_resolution_minutes": 30.0,
        "incidents": SAMPLE_INCIDENTS,
    }

    pdf_bytes = write_pdf("incident_summary", data)

    assert len(pdf_bytes) > 2000, "PDF is suspiciously small — likely nearly empty"
    # PDF magic bytes
    assert pdf_bytes[:4] == b"%PDF", "Output is not a valid PDF"


def test_pdf_writer_alert_summary():
    """Alert summary with multiple dict fields produces a non-trivial PDF."""
    from services.reporting.src.pdf_writer import write_pdf

    data = {
        "report_type": "alert_volume",
        "date_start": "2026-09-01",
        "date_end": "2026-09-30",
        "total_alerts": 42,
        "by_source_uc": {"uc3": 30, "uc1": 12},
        "by_severity": {"high": 25, "medium": 17},
        "by_alert_type": {"ppe_violation": 30, "intruder_detected": 12},
        "by_camera": {"Test Camera UC3": 30, "Test Camera UC1": 12},
        "by_day": {"2026-09-10": 10, "2026-09-11": 15, "2026-09-12": 17},
    }

    pdf_bytes = write_pdf("alert_volume", data)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Test: UC3 URL default is correct
# ---------------------------------------------------------------------------
def test_uc3_url_default():
    """UC3 PPE metrics URL must point at host.docker.internal:8030, not uc3_api:8000."""
    from services.reporting.src.config import ReportingSettings
    s = ReportingSettings()
    assert "uc3_api" not in s.uc3_ppe_metrics_url, \
        "UC3 URL still points at non-existent uc3_api container"
    assert "8030" in s.uc3_ppe_metrics_url or "host.docker.internal" in s.uc3_ppe_metrics_url
