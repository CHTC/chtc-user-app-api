from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.core.models.tables import User, UserProject, UserGroup, SubmitNode
from userapp.core.models.views import JoinedProjectView, UserGroupView
from userapp.core.schemas.user_project import UserProjectPatch
from userapp.core.schemas.user_group import UserGroupPatch
from userapp.core.schemas.user_submit import UserSubmitPost


async def _patch_user_submit_nodes(
    session: AsyncSession,
    user: User,
    new_submit_nodes: list[UserSubmitPost],
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

    current_group_ids = set((await session.execute(
        select(UserGroup.group_id).where(UserGroup.user_id == user.id)
    )).scalars().all())

    to_add = target_group_ids - current_group_ids
    to_remove = (current_group_ids & submit_node_group_ids) - target_group_ids

    for group_id in to_add:
        session.add(UserGroup(user_id=user.id, group_id=group_id))

    if to_remove:
        await session.execute(
            delete(UserGroup).where(
                UserGroup.user_id == user.id,
                UserGroup.group_id.in_(to_remove),
            )
        )

    await session.flush()


async def _patch_user_project(
    session: AsyncSession,
    user_id: int,
    project_id: int,
    patch: UserProjectPatch,
) -> JoinedProjectView:
    """Patch the UserProject row identified by (user_id, project_id) and return
    the matching row from the joined_projects view. Raises 404 if no such
    membership exists."""

    row = await session.scalar(
        select(UserProject).where(
            UserProject.user_id == user_id,
            UserProject.project_id == project_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} is not a member of project {project_id}",
        )

    # Iterate set fields and copy native Python values (e.g. Enum members)
    # straight to the ORM row. Avoid model_dump() here: model_dump() runs any
    # @field_serializer on the schema, which can downgrade an Enum member to
    # its .value string and break SQLAlchemy's name-based enum binding (the
    # Postgres entity_manager_enum type stores .name, not .value).
    for key in patch.model_fields_set:
        setattr(row, key, getattr(patch, key))
    await session.flush()

    view_row = await session.scalar(
        select(JoinedProjectView).where(
            JoinedProjectView.id == user_id,
            JoinedProjectView.project_id == project_id,
        )
    )
    return view_row


async def _patch_user_group(
    session: AsyncSession,
    user_id: int,
    group_id: int,
    patch: UserGroupPatch,
) -> UserGroupView:
    """Patch the UserGroup row identified by (user_id, group_id) and return the
    matching row from the user_group_memberships view. Raises 404 if no such
    membership exists."""

    row = await session.scalar(
        select(UserGroup).where(
            UserGroup.user_id == user_id,
            UserGroup.group_id == group_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} is not a member of group {group_id}",
        )

    # See note in _patch_user_project: avoid model_dump() so Enum members are
    # passed to SQLAlchemy as members (bound by .name) rather than as their
    # serialized .value strings.
    for key in patch.model_fields_set:
        setattr(row, key, getattr(patch, key))
    await session.flush()

    view_row = await session.scalar(
        select(UserGroupView).where(
            UserGroupView.user_id == user_id,
            UserGroupView.group_id == group_id,
        )
    )
    return view_row
