
from fastapi import APIRouter, Depends, Response, HTTPException
from sqlalchemy import select

from userapp.core.models.enum import AuditActionEnum
from userapp.core.models.tables import Group as GroupTable, GroupMember
from userapp.core.models.views import GroupMembersView
from userapp.core.schemas.general import GroupMembersView as GroupMembersViewSchema
from userapp.core.schemas.groups import GroupGet, GroupPost, GroupPatch, GroupMemberGet, GroupMemberPost, \
    GroupMemberOfGet
from userapp.core.schemas.group_access import GroupAccessGet
from userapp.core.schemas.users import UserGet
from userapp.core.services import audit, membership
from userapp.core.services.access import group_access
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes._util import json_value as _json_value
from userapp.api.routes.security import check_is_admin, check_can_administer_group, \
    check_can_view_group, get_user_from_cookie, is_admin
from userapp.api.util import list_select_stmt, get_one_endpoint

GroupMemberGet.model_rebuild(_types_namespace={'UserGet': UserGet})


router = APIRouter(
    prefix="/groups",
    tags=["Groups"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


def _actor_id(user_token) -> int | None:
    # API tokens and ALLOW_ADMIN_ACCESS have no user behind them, so those act as the system
    return user_token.user_id if user_token else None


@router.get("")
async def get_groups(
    response: Response,
    page: int = 0,
    page_size: int = 100,
    include_deleted: bool = False,
    administered: bool = False,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
    is_admin=Depends(is_admin),
    user_token=Depends(get_user_from_cookie),
) -> list[GroupGet]:
    """Staff list every group. A PI or group owner lists every live group too (they pick from it
    when adding a member group), or with administered=true only the groups they administer. A
    user who administers nothing gets an empty list. Deleted groups are left out unless staff
    ask for them."""

    if not is_admin and user_token is None:
        raise HTTPException(status_code=403, detail="User is not an admin")

    # include_deleted and administered are this route's own parameters, not column filters
    filter_query_params = [param for param in filter_query_params if param[0] not in ("include_deleted", "administered")]

    select_stmt = select(GroupTable)
    if is_admin:
        if not include_deleted:
            select_stmt = select_stmt.where(GroupTable.deleted_at.is_(None))
    else:
        select_stmt = select_stmt.where(GroupTable.deleted_at.is_(None))
        ids = await membership.administrable_group_ids(session, user_token.user_id)
        if administered or not ids:
            select_stmt = select_stmt.where(GroupTable.id.in_(ids))

    return await list_select_stmt(
        session, select_stmt, GroupTable, response, filter_query_params, page, page_size,
        default_order_by=[GroupTable.id],
    )


@router.post("", status_code=201, dependencies=[Depends(check_is_admin)])
async def create_group(group: GroupPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> GroupGet:
    return await membership.create_group(
        session,
        actor_id=_actor_id(user_token),
        name=group.name,
        unix_gid=group.unix_gid,
        description=group.description,
        managed_by=group.managed_by,
        owner_group_id=group.owner_group_id,
        administration=group.administration,
    )


@router.get("/{group_id}", dependencies=[Depends(check_can_view_group)])
async def get_group(group_id: int, session=Depends(session_generator)) -> GroupGet:
    return await get_one_endpoint(session, GroupTable, group_id)


@router.put("/{group_id}", status_code=200, dependencies=[Depends(check_is_admin)])
async def update_group(
    group_id: int,
    group: GroupPatch,
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
) -> GroupGet:
    """Staff only: owners administer a group's members, never its metadata"""

    sent = group.model_fields_set
    if "name" in sent and group.name is None:
        raise HTTPException(status_code=400, detail="A group's name cannot be removed")
    if "managed_by" in sent and group.managed_by is None:
        raise HTTPException(status_code=400, detail="managed_by cannot be removed; use APPLICATION for a group no system syncs")

    actor_id = _actor_id(user_token)
    db_group = await membership.get_live_group(session, group_id)

    # Ownership goes through the service: it holds the lock and checks for loops
    if "owner_group_id" in sent:
        await membership.set_owner_group(session, group_id=group_id, owner_group_id=group.owner_group_id, actor_id=actor_id)

    changes = {}
    for field in ("name", "unix_gid", "description", "managed_by"):
        if field not in sent:
            continue
        old, new = getattr(db_group, field), getattr(group, field)
        if old != new:
            changes[field] = {"old": _json_value(old), "new": _json_value(new)}
            setattr(db_group, field, new)

    if changes:
        await session.flush()
        await audit.log(
            session,
            action=AuditActionEnum.metadata_changed,
            actor_id=actor_id,
            group_id=group_id,
            details={"entity": "group", "entity_id": group_id, "changes": changes},
        )

    await session.refresh(db_group)
    return db_group


@router.post("/{group_id}/unix_gid", dependencies=[Depends(check_is_admin)])
async def allocate_group_unix_gid(group_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> GroupGet:
    """Give the group the lowest free unix gid, the way new groups used to get one on insert"""

    return await membership.allocate_unix_gid(session, group_id=group_id, actor_id=_actor_id(user_token))


@router.delete("/{group_id}", status_code=204, dependencies=[Depends(check_is_admin)])
async def delete_group(group_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> None:
    """Soft delete: removes the group's memberships and clears everything that pointed at it"""

    await membership.delete_group(session, group_id=group_id, actor_id=_actor_id(user_token))


@router.get("/{group_id}/members", dependencies=[Depends(check_can_view_group)])
async def get_group_members(
    group_id: int,
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
) -> list[GroupMembersViewSchema]:
    """Every user with access through the group, and how (direct, or the group paths that grant it)"""

    await get_one_endpoint(session, GroupTable, group_id)

    select_stmt = select(GroupMembersView).where(GroupMembersView.group_id == group_id)
    return await list_select_stmt(
        session, select_stmt, GroupMembersView, response, filter_query_params, page, page_size,
        default_order_by=[GroupMembersView.user_id],
    )


@router.get("/{group_id}/direct_members", dependencies=[Depends(check_can_view_group)])
async def get_group_direct_members(
    group_id: int,
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
) -> list[GroupMemberGet]:
    """The membership rows of this group: the users and groups added to it directly"""

    await get_one_endpoint(session, GroupTable, group_id)

    select_stmt = select(GroupMember).where(GroupMember.group_id == group_id)
    return await list_select_stmt(
        session, select_stmt, GroupMember, response, filter_query_params, page, page_size,
        default_order_by=[GroupMember.id],
    )


@router.post("/{group_id}/members", status_code=201)
async def add_group_member(
    group_id: int,
    member: GroupMemberPost,
    session=Depends(session_generator),
    can_administer=Depends(check_can_administer_group),
    user_token=Depends(get_user_from_cookie),
) -> GroupMemberGet:
    """Add a user or a group as a direct member"""

    return await membership.add_member(
        session,
        group_id=group_id,
        actor_id=_actor_id(user_token),
        user_id=member.user_id,
        member_group_id=member.group_id,
    )


@router.delete("/{group_id}/members/users/{user_id}", status_code=204, dependencies=[Depends(check_can_administer_group)])
async def remove_group_user_member(group_id: int, user_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> None:
    await membership.remove_member(session, group_id=group_id, actor_id=_actor_id(user_token), user_id=user_id)


@router.delete("/{group_id}/members/groups/{member_id}", status_code=204, dependencies=[Depends(check_can_administer_group)])
async def remove_group_group_member(group_id: int, member_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> None:
    await membership.remove_member(session, group_id=group_id, actor_id=_actor_id(user_token), member_group_id=member_id)


@router.get("/{group_id}/access", dependencies=[Depends(check_can_view_group)])
async def get_group_access(group_id: int, session=Depends(session_generator)) -> GroupAccessGet:
    """Every access object the group is associated with: the projects and submit nodes that reference
    it, and those that reference a group it is a member of (with the paths that make them apply).
    A deleted group is still readable here, its access is simply empty."""

    await get_one_endpoint(session, GroupTable, group_id)
    return await group_access(session, group_id)


@router.get("/{group_id}/member_of", dependencies=[Depends(check_can_view_group)])
async def get_group_member_of(group_id: int, session=Depends(session_generator)) -> list[GroupMemberOfGet]:
    """The groups this group is a member of, directly or through other groups, with every path"""

    await get_one_endpoint(session, GroupTable, group_id)

    paths = await membership.member_of_paths(session, group_id)
    if not paths:
        return []
    groups = (await session.execute(
        select(GroupTable).where(GroupTable.id.in_(paths.keys())).order_by(GroupTable.id)
    )).scalars().all()
    return [{"group": group, "paths": paths[group.id]} for group in groups]
