"""
Health — lightweight FastAPI application that exposes a ``/health``
endpoint reporting the ingestion service status and active worker count.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Module-level registry — set by the orchestrator in main.py
_active_workers: dict[str, Any] = {}


def register_workers(workers: dict[str, Any]) -> None:
    """Point the health module at the live worker dictionary."""
    global _active_workers
    _active_workers = workers


app = FastAPI(title="Ingestion Service", version="2.0.0-phase2")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "service": "ingestion",
        "phase": "2",
        "active_cameras": len(_active_workers),
        "camera_ids": [str(cid) for cid in _active_workers],
    }
