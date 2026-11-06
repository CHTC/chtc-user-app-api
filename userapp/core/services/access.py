"""Helpers shared by the access-object routes (submit nodes, group access)"""
from datetime import datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.core.models.enum import AuditActionEnum
from userapp.core.models.tables import Project, SubmitNode
from userapp.core.services import audit
from userapp.core.services.membership import ancestor_group_ids, member_of_paths


def actor_id(user_token) -> int | None:
    # API tokens and ALLOW_ADMIN_ACCESS have no user behind them, so those act as the system
    return user_token.user_id if user_token else None


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


async def apply_and_audit(
    session: AsyncSession,
    row,
    values: dict,
    *,
    entity: str,
    actor: int | None,
    group_id_after=lambda row: None,
) -> dict:
    """Set the given fields on row and write one metadata_changed entry for those that changed.
    Returns the changes (empty when nothing changed, in which case nothing is logged)."""

    changes = {}
    for field, new in values.items():
        old = getattr(row, field)
        if old != new:
            changes[field] = {"old": _json_value(old), "new": _json_value(new)}
            setattr(row, field, new)
    if changes:
        await session.flush()
        await audit.log(
            session,
            action=AuditActionEnum.metadata_changed,
            actor_id=actor,
            group_id=group_id_after(row),
            details={"entity": entity, "entity_id": row.id, "changes": changes},
        )
    return changes


async def group_access(session: AsyncSession, group_id: int) -> dict:
    """Every access object that reaches this group: the ones that reference it, and the ones that
    reference a group it is a member of (directly or not). via holds the paths, from the
    referenced group down to this one, that make the second kind apply."""

    via_by_group: dict[int, list[list[int]]] = {group_id: []}
    paths = await member_of_paths(session, group_id)
    for ancestor_id in await ancestor_group_ids(session, group_id):
        via_by_group[ancestor_id] = paths.get(ancestor_id, [])
    ids = list(via_by_group)

    projects = []
    for project in (await session.execute(
        select(Project).where((Project.pi_group_id.in_(ids)) | (Project.project_group_id.in_(ids)))
    )).scalars():
        for role, referenced in (("pi_group", project.pi_group_id), ("project_group", project.project_group_id)):
            if referenced in via_by_group:
                projects.append({
                    "project_id": project.id,
                    "name": project.name,
                    "display_name": project.display_name,
                    "as": role,
                    "group_id": referenced,
                    "via": via_by_group[referenced],
                })
    projects.sort(key=lambda p: (p["project_id"], p["as"]))

    submit_nodes = [
        {"id": node.id, "name": node.name, "group_id": node.group_id, "via": via_by_group[node.group_id]}
        for node in (await session.execute(
            select(SubmitNode).where(SubmitNode.group_id.in_(ids)).order_by(SubmitNode.id)
        )).scalars()
    ]

    return {"projects": projects, "submit_nodes": submit_nodes}
