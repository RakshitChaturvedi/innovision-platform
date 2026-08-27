from fastapi import APIRouter, Depends
from collections.abc import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from services.auth.src.rbac import require_role, Role
from shared.platform_client.db import get_session_factory
from .config import settings

router = APIRouter(prefix="/audit", tags=["audit"])
_session_factory = get_session_factory(settings.database_url)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


@router.get("", dependencies=[Depends(require_role(Role.ADMIN))])
async def list_audit(
    service: str | None = None,
    entity_type: str | None = None,
    source_uc: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    conditions, params = [], {"limit": limit, "offset": offset}
    if service:
        conditions.append("service = :service"); params["service"] = service
    if entity_type:
        conditions.append("entity_type = :entity_type"); params["entity_type"] = entity_type
    if source_uc:
        conditions.append("source_uc = :source_uc"); params["source_uc"] = source_uc

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.execute(text(f"""
        SELECT * FROM audit_log {where}
        ORDER BY timestamp DESC LIMIT :limit OFFSET :offset
    """), params)
    return [dict(r._mapping) for r in rows.fetchall()]