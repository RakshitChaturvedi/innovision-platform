import uuid
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncGenerator
from sqlalchemy import text

from .config import settings
from .jwt import verify_password, hash_password, create_access_token, create_refresh_token, rotate_refresh_token
from .rbac import get_current_user, require_role, Role
from shared.platform_client.db import get_session_factory
from services.audit.src.writer import write_audit_entry

_session_factory = get_session_factory(settings.database_url)

router = APIRouter(prefix="/auth", tags=["auth"])

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session

@router.post("/login")
async def login(email: str, password: str, response: Response, db: AsyncSession = Depends(get_db)):
    row = await db.execute(text("""
        SELECT id, password_hash, role, organization_id, camera_ids, is_active FROM users WHERE email = :email
    """), {"email": email})
    user = row.fetchone()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if hasattr(user, "is_active") and user.is_active is False:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    org_id = str(user.organization_id) if user.organization_id else None
    camera_ids = [str(c) for c in (user.camera_ids or [])]

    access_token = create_access_token(str(user.id), user.role, camera_ids, org_id=org_id)
    refresh_token = await create_refresh_token(db, str(user.id))
    await db.commit()

    response.set_cookie("refresh_token", refresh_token,
                        httponly=True, secure=True, samesite="strict", max_age=7*24*3600)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": email,
            "role": user.role,
            "organization_id": org_id,
        }
    }

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

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.execute(text("""
        SELECT u.id, u.name, u.email, u.role, u.organization_id, u.is_active, u.created_at,
               o.name as organization_name, o.code as organization_code
        FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id
        WHERE u.id = :id
    """), {"id": user["sub"]})
    u = row.fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": str(u.id),
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "organization_id": str(u.organization_id) if u.organization_id else None,
        "organization_name": u.organization_name,
        "organization_code": u.organization_code,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }

# --- User Management Endpoints (Phase 6A) ---
@router.get("/users", dependencies=[Depends(require_role(Role.ADMIN))])
async def list_users(
    organization_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_role = user.get("role")
    current_org = user.get("org_id") or user.get("organization_id")

    conditions = []
    params = {}

    if current_role == Role.SUPERADMIN:
        if organization_id:
            conditions.append("u.organization_id = :org_id")
            params["org_id"] = organization_id
    else:
        # org_admin is restricted strictly to their own organization
        if not current_org:
            raise HTTPException(status_code=403, detail="User has no assigned organization")
        conditions.append("u.organization_id = :org_id")
        params["org_id"] = current_org

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = text(f"""
        SELECT u.id, u.name, u.email, u.role, u.organization_id, u.is_active, u.created_at, u.updated_at,
               o.name as organization_name, o.code as organization_code
        FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id
        {where_clause}
        ORDER BY u.created_at DESC
    """)
    rows = await db.execute(query, params)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "email": r.email,
            "role": r.role,
            "organization_id": str(r.organization_id) if r.organization_id else None,
            "organization_name": r.organization_name,
            "organization_code": r.organization_code,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows.fetchall()
    ]

@router.post("/users", status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_user(
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_role = user.get("role")
    current_org = user.get("org_id") or user.get("organization_id")

    target_name = body.get("name")
    target_email = body.get("email")
    target_password = body.get("password")
    target_role = body.get("role", "org_admin")
    target_org_id = body.get("organization_id")

    if not target_name or not target_email or not target_password:
        raise HTTPException(status_code=400, detail="Name, email, and password are required")

    # Privilege escalation check: only SUPERADMIN can assign superadmin role
    if target_role == Role.SUPERADMIN and current_role != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Privilege escalation forbidden: cannot create SUPERADMIN users")

    # Organization scope check
    if current_role != Role.SUPERADMIN:
        if not current_org:
            raise HTTPException(status_code=403, detail="User has no assigned organization")
        target_org_id = current_org

    # Check email duplicate
    existing = await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": target_email})
    if existing.fetchone():
        raise HTTPException(status_code=409, detail="User with this email already exists")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(target_password)

    await db.execute(text("""
        INSERT INTO users (id, name, email, password_hash, role, organization_id, is_active, created_at, updated_at)
        VALUES (:id, :name, :email, :pw_hash, :role, :org_id, true, now(), now())
    """), {
        "id": user_id,
        "name": target_name,
        "email": target_email,
        "pw_hash": pw_hash,
        "role": target_role,
        "org_id": target_org_id
    })
    await db.commit()

    # Audit log entry
    await write_audit_entry(
        session_factory=_session_factory,
        service="auth",
        action="user_created",
        entity_type="user",
        entity_id=user_id,
        user_id=user["sub"],
        metadata={"email": target_email, "role": target_role, "organization_id": target_org_id}
    )

    return {
        "id": user_id,
        "name": target_name,
        "email": target_email,
        "role": target_role,
        "organization_id": target_org_id,
        "is_active": True,
    }

@router.get("/users/{user_id}", dependencies=[Depends(require_role(Role.ADMIN))])
async def get_user_detail(
    user_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_role = user.get("role")
    current_org = user.get("org_id") or user.get("organization_id")

    row = await db.execute(text("""
        SELECT u.id, u.name, u.email, u.role, u.organization_id, u.is_active, u.created_at, u.updated_at,
               o.name as organization_name
        FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id
        WHERE u.id = :id
    """), {"id": user_id})
    target = row.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if current_role != Role.SUPERADMIN:
        if str(target.organization_id) != str(current_org):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

    return {
        "id": str(target.id),
        "name": target.name,
        "email": target.email,
        "role": target.role,
        "organization_id": str(target.organization_id) if target.organization_id else None,
        "organization_name": target.organization_name,
        "is_active": target.is_active,
        "created_at": target.created_at.isoformat() if target.created_at else None,
    }

@router.put("/users/{user_id}", dependencies=[Depends(require_role(Role.ADMIN))])
async def update_user(
    user_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_role = user.get("role")
    current_org = user.get("org_id") or user.get("organization_id")

    row = await db.execute(text("SELECT id, role, organization_id FROM users WHERE id = :id"), {"id": user_id})
    target = row.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if current_role != Role.SUPERADMIN:
        if str(target.organization_id) != str(current_org):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

    new_role = body.get("role")
    new_name = body.get("name")
    new_org_id = body.get("organization_id")

    if new_role == Role.SUPERADMIN and current_role != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Privilege escalation forbidden: cannot promote user to SUPERADMIN")

    if current_role != Role.SUPERADMIN:
        new_org_id = target.organization_id

    updates = []
    params = {"id": user_id}

    if new_name:
        updates.append("name = :name")
        params["name"] = new_name
    if new_role:
        updates.append("role = :role")
        params["role"] = new_role
    if new_org_id is not None or current_role == Role.SUPERADMIN:
        updates.append("organization_id = :org_id")
        params["org_id"] = new_org_id

    if updates:
        updates.append("updated_at = now()")
        set_sql = ", ".join(updates)
        await db.execute(text(f"UPDATE users SET {set_sql} WHERE id = :id"), params)
        await db.commit()

        await write_audit_entry(
            session_factory=_session_factory,
            service="auth",
            action="user_updated",
            entity_type="user",
            entity_id=user_id,
            user_id=user["sub"],
            metadata={"updated_fields": list(params.keys())}
        )

    return {"status": "updated", "id": user_id}

@router.put("/users/{user_id}/status", dependencies=[Depends(require_role(Role.ADMIN))])
async def update_user_status(
    user_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_role = user.get("role")
    current_org = user.get("org_id") or user.get("organization_id")

    row = await db.execute(text("SELECT id, organization_id FROM users WHERE id = :id"), {"id": user_id})
    target = row.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if current_role != Role.SUPERADMIN:
        if str(target.organization_id) != str(current_org):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

    is_active = bool(body.get("is_active", True))

    await db.execute(text("UPDATE users SET is_active = :is_active, updated_at = now() WHERE id = :id"), {
        "id": user_id,
        "is_active": is_active
    })
    await db.commit()

    await write_audit_entry(
        session_factory=_session_factory,
        service="auth",
        action="user_status_changed",
        entity_type="user",
        entity_id=user_id,
        user_id=user["sub"],
        metadata={"is_active": is_active}
    )

    return {"status": "updated", "id": user_id, "is_active": is_active}