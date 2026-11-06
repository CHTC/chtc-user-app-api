from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import aggregate_order_by

from userapp.api.routes.security import check_is_admin
from userapp.core.models.tables import Group, GroupEffectiveMember, User
from userapp.core.schemas.unix_group import UnixGroupGet
from userapp.db import session_generator

router = APIRouter(
    prefix="/unix_groups",
    tags=["Unix Groups"],
    dependencies=[Depends(check_is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


@router.get("")
async def get_unix_groups(session=Depends(session_generator)) -> list[UnixGroupGet]:
    """Every live group with a unix_gid and the usernames of its effective members"""

    # Aggregated in one query: group_effective_members has a row per path, hence DISTINCT. The
    # FILTER drops users without a username, who have no unix account to be a member of.
    members = func.array_agg(aggregate_order_by(User.username.distinct(), User.username)).filter(User.username.is_not(None))
    stmt = (
        select(Group.id, Group.name, Group.unix_gid, members.label("members"))
        .outerjoin(GroupEffectiveMember, GroupEffectiveMember.group_id == Group.id)
        .outerjoin(User, User.id == GroupEffectiveMember.user_id)
        .where(Group.unix_gid.is_not(None), Group.deleted_at.is_(None))
        .group_by(Group.id)
        .order_by(Group.unix_gid)
    )
    rows = (await session.execute(stmt)).all()
    return [{"id": r.id, "name": r.name, "unix_gid": r.unix_gid, "members": r.members or []} for r in rows]
