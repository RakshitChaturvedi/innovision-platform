from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncGenerator
from sqlalchemy import text
from .config import settings
from .jwt import verify_password, create_access_token, create_refresh_token, rotate_refresh_token
from .rbac import get_current_user
from shared.platform_client.db import get_session_factory

_session_factory = get_session_factory(settings.database_url)

router = APIRouter(prefix="/auth", tags=["auth"])

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session

@router.post("/login")
async def login(email: str, password: str, response: Response, db: AsyncSession = Depends(get_db)):
    row = await db.execute(text("""
        SELECT id, password_hash, role, camera_ids FROM users WHERE email = :email
    """),{"email": email})
    user = row.fetchone()

    if not user or not verify_password(password, user.password_has):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(str(user.id), user.role, [str(c) for c in user.camera_ids])
    refresh_token = await create_refresh_token(db, str(user.id))

    response.set_cookie("refresh_token", refresh_token,
                        httponly=True, secure=True, samesite="strict", max_age=7*24*3600)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refresh")
async def refresh(session_id: str, refresh_token: str, db: AsyncSession = Depends(get_db)):
    result = await rotate_refresh_token(db, refresh_token, session_id)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access_token, new_refresh, user_id = result
    return {"access_token": access_token, "refresh_token": new_refresh}

@router.post("/logout")
async def logout(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("""
        UPDATE sessions SET revoked_at = now() WHERE user_id = :user_id AND revoked_at IS NULL
    """), {"user_id": user["sub"]})
    return {"status": "logged_out"}