import logging, uuid, bcrypt
import jwt as pyjwt

from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from .config import settings

logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_access_token(user_id: str, role: str, camera_ids: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "camera_ids": camera_ids,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access"
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> dict:
    return pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

async def create_refresh_token(session: AsyncSession, user_id: str) -> str:
    raw_token = str(uuid.uuid4())
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt(rounds=10)).decode()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    await session.execute(text("""
        INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at)
        VALUES (:id, :user_id, :hash, :expires_at)
    """), {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "hash": token_hash,
        "expires_at": expires_at
    })

    return raw_token

async def rotate_refresh_token(session: AsyncSession, old_raw_token: str, session_id: str) -> tuple[str, str, str] | None:
    # validate old refresh token, revoke it, issue new one. return none if invalid
    row = await session.execute(text("""
        SELECT s.id, s.refresh_token_hash, s.expires_at, s.revoked_at, u.id AS user_id,
                u.role, u.camera_ids
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = :session_id
    """), {"session_id": session_id})
    result = row.fetchone()

    if not result or result.revoked_at is not None:
        return None
    if result.expires_at < datetime.now(timezone.utc):
        return None
    if not bcrypt.checkpw(old_raw_token.encode(), result.refresh_token_hash.encode()):
        logger.warning("refresh_token_mismatch session_id=%s", session_id)
        return None

    async with session.begin():
        await session.execute(text("""UPDATE sessions SET revoked_at = now() WHERE id = :id"""),
                              {"id": session_id})
    new_refresh = await create_refresh_token(session, str(result.user_id))
    new_access = create_access_token(str(result.user_id), result.role, [str(c) for c in result.camera_ids])
    return new_access, new_refresh, str(result.user_id)