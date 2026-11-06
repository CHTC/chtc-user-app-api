from datetime import datetime
from enum import Enum

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.core.models.enum import AuditActionEnum
from userapp.core.models.tables import User, GroupMember, SubmitNode
from userapp.core.schemas.user_submit import UserSubmitPost
from userapp.core.services import audit, membership


def json_value(value):
    """Audit details are JSONB, which has neither datetime nor enum"""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


async def set_primary_project(session: AsyncSession, user: User, project_id: int | None, actor_id: int | None) -> None:
    """Sets users.primary_project_id and audits the change. The primary project need not match a
    current membership, so nothing else changes. The user is the entry's member so it shows up on
    their own log."""

    old = user.primary_project_id
    if old == project_id:
        return
    user.primary_project_id = project_id
    await session.flush()
    await audit.log(
        session,
        action=AuditActionEnum.metadata_changed,
        actor_id=actor_id,
        member_user_id=user.id,
        details={"entity": "user", "entity_id": user.id, "changes": {"primary_project_id": {"old": old, "new": project_id}}},
    )


async def _patch_user_submit_nodes(
    session: AsyncSession,
    user: User,
    new_submit_nodes: list[UserSubmitPost],
    actor_id: int | None = None,
) -> None:
    """Ensures the user's group memberships match the requested submit nodes. Submit node
    access is derived from group membership (SubmitNode.group_id), so granting/revoking a
    submit node means adding/removing the user from that submit node's group. A submit node's
    group is only removed if no other requested submit node still depends on it, and groups
    unrelated to any submit node are never touched."""

    requested_ids = {sn.submit_node_id for sn in new_submit_nodes}

    submit_nodes = (await session.execute(
        select(SubmitNode).where(SubmitNode.id.in_(requested_ids))
    )).scalars().all() if requested_ids else []
    submit_nodes_by_id = {sn.id: sn for sn in submit_nodes}

    missing_ids = requested_ids - submit_nodes_by_id.keys()
    if missing_ids:
        raise HTTPException(status_code=400, detail=f"Unknown submit node id(s): {sorted(missing_ids)}")

    ungrouped = [sn.name for sn in submit_nodes_by_id.values() if sn.group_id is None]
    if ungrouped:
        raise HTTPException(
            status_code=400,
            detail=f"Submit node(s) {ungrouped} have no associated group and cannot be assigned",
        )

    target_group_ids = {sn.group_id for sn in submit_nodes_by_id.values()}

    # Every group_id that any submit node depends on - scopes which of the
    # user's current groups are "submit node groups" eligible for removal.
    submit_node_group_ids = set((await session.execute(
        select(SubmitNode.group_id).where(SubmitNode.group_id.isnot(None))
    )).scalars().all())

    # Only direct memberships are this function's to change; access the user has through
    # another group is not touched.
    current_group_ids = set((await session.execute(
        select(GroupMember.group_id).where(GroupMember.member_user_id == user.id)
    )).scalars().all())

    to_add = target_group_ids - current_group_ids
    to_remove = (current_group_ids & submit_node_group_ids) - target_group_ids

    for group_id in to_add:
        await membership.add_member(session, group_id=group_id, actor_id=actor_id, user_id=user.id)

    for group_id in to_remove:
        await membership.remove_member(session, group_id=group_id, actor_id=actor_id, user_id=user.id)

    await session.flush()
