from sqlalchemy.ext.asyncio import AsyncSession

from userapp.core.models.enum import AuditActionEnum
from userapp.core.models.tables import AuditLog


async def log(
    session: AsyncSession,
    *,
    action: AuditActionEnum,
    actor_id: int | None,
    group_id: int | None = None,
    member_user_id: int | None = None,
    member_group_id: int | None = None,
    caused_by: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Append an audit row in the caller's transaction. Flushes so .id can be used as caused_by
    on the entries this one triggers. Rows are never updated or deleted by the application."""

    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        group_id=group_id,
        member_user_id=member_user_id,
        member_group_id=member_group_id,
        caused_by=caused_by,
        details=details,
    )
    session.add(entry)
    await session.flush()
    return entry
