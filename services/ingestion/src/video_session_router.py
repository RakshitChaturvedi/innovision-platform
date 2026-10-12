"""
Video Session Router (Ingestion Service) — Internal endpoints for session playback execution.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from services.ingestion.src.video_session_manager import VideoSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["video-sessions"])

# Singleton manager instance initialized in main.py lifespan
session_manager: Optional[VideoSessionManager] = None


class StartSessionRequest(BaseModel):
    session_id: str
    effective_analytics: List[str] = []
    fps: Optional[float] = None


class CreateExistingFileRequest(BaseModel):
    camera_id: str
    organization_id: Optional[str] = None
    source_path: str
    filename: Optional[str] = None
    target_fps: float = 10.0


@router.post("/start")
async def start_session(body: StartSessionRequest) -> Dict[str, Any]:
    if session_manager is None:
        raise HTTPException(status_code=503, detail="Video session manager not initialized")

    try:
        return await session_manager.start_session_processing(
            session_id=body.session_id,
            effective_analytics=body.effective_analytics,
            playback_fps=body.fps,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("start_session_failed session_id=%s", body.session_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/stop")
async def stop_session(session_id: str) -> Dict[str, Any]:
    if session_manager is None:
        raise HTTPException(status_code=503, detail="Video session manager not initialized")

    try:
        return await session_manager.stop_session(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("stop_session_failed session_id=%s", session_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/status")
async def get_session_status(session_id: str) -> Dict[str, Any]:
    if session_manager is None:
        raise HTTPException(status_code=503, detail="Video session manager not initialized")

    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    return session


@router.post("/create-from-file")
async def create_session_from_file(body: CreateExistingFileRequest) -> Dict[str, Any]:
    if session_manager is None:
        raise HTTPException(status_code=503, detail="Video session manager not initialized")

    try:
        return await session_manager.create_session_from_existing(
            camera_id=body.camera_id,
            organization_id=body.organization_id,
            source_path=body.source_path,
            original_filename=body.filename,
            target_fps=body.target_fps,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("create_session_from_file_failed")
        raise HTTPException(status_code=500, detail=str(e))
