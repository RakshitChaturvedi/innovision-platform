"""
socket io server for real time alert & notification delivery. namespace /alerts.
"""
import logging
import socketio

from sqlalchemy import text
from shared.platform_client.db import get_session_factory
from .config import settings
from .reconnect import fetch_missed_alerts

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio)

_session_factory = get_session_factory(settings.database_url)

def _decode_jwt(token: str) -> dict:
    import jwt as pyjwt
    return pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

@sio.on("connect", namespace="/alerts")
async def connect(sid, environ, auth):
    token = (auth or {}).get("token")
    if not token:
        logger.warning("socket_connect_no_token sid=%s", sid)
        return False
    try:
        user = _decode_jwt(token)
    except Exception as e:
        logger.warning("socket_auth_failed sid=%s error=%s", sid, e)
        return False

    user_id = user["sub"]
    await sio.save_session(sid, 
                           {
                               "user_id": user_id, 
                               "role": user["role"], 
                               "camera_ids": set(user.get("camera_ids", []))
                            },
                           namespace="/alerts")

    # Automatically enter user's private notification room
    await sio.enter_room(sid, f"user:{user_id}", namespace="/alerts")
    return True

@sio.on("join", namespace="/alerts")
async def join(sid, data):
    session = await sio.get_session(sid, namespace="/alerts")
    requested_camera_ids = data.get("camera_ids", [])
    role = session["role"]
    allowed_camera_ids = session["camera_ids"]

    if role not in ("superadmin", "admin", "org_admin"):
        unauthorized = set(requested_camera_ids) - allowed_camera_ids
        if unauthorized:
            logger.warning(
                "socket_unauthorized_camera_join sid=%s cameras=%s",
                sid,
                list(unauthorized),
            )
            return {"error": "unauthorized_camera", "camera_ids": list(unauthorized)}

    last_seen = data.get("last_seen_timestamp")
    for camera_id in requested_camera_ids:
        await sio.enter_room(
            sid,
            f"camera:{camera_id}",
            namespace="/alerts",
        )

    if last_seen:
        missed = await fetch_missed_alerts(
            _session_factory,
            requested_camera_ids,
            last_seen,
        )
        for alert in missed:
            await sio.emit(
                "alert:missed",
                alert,
                to=sid,
                namespace="/alerts",
            )
    logger.info("socket_joined sid=%s cameras=%d", sid, len(requested_camera_ids))

@sio.on("disconnect", namespace="/alerts")
async def disconnect(sid):
    logger.info("socket_disconnected sid=%s", sid)

def _serialize(data_row: dict) -> dict:
    out = {}
    for k, v in data_row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex"):
            out[k] = str(v)
        else:
            out[k] = v
    return out

async def push_alert(alert_row: dict) -> None:
    camera_room = f"camera:{alert_row['camera_id']}"
    await sio.emit("alert:new", _serialize(alert_row), room=camera_room, namespace="/alerts")

async def push_alert_update(alert_row: dict) -> None:
    camera_room = f"camera:{alert_row['camera_id']}"
    await sio.emit("alert:updated", _serialize(alert_row), room=camera_room, namespace="/alerts")

async def push_user_notification(user_id: str, notification_row: dict) -> None:
    user_room = f"user:{user_id}"
    await sio.emit("notification:new", _serialize(notification_row), room=user_room, namespace="/alerts")