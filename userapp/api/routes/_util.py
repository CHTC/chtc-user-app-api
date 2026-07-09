from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.api.util import create_one_endpoint
from userapp.core.models.enum import GroupTypeEnum
from userapp.core.models.tables import User, UserProject, UserGroup
from userapp.core.models.views import JoinedProjectView, UserGroupView
from userapp.core.schemas.user_project import UserProjectPatch
from userapp.core.schemas.user_group import UserGroupPatch
from userapp.core.schemas.user_group import UserGroupCreate  # see below


async def _patch_user_submit_node_groups(session: AsyncSession, user: User, new_submit_node_group_ids: list[int]):
    """Updates the passed in user to match the provided list of submit_nodes"""

    existing_group_ids = [g.group_id for g in user.groups]

    # Remove memberships not in the new list
    for existing_group in user.groups:
        if existing_group.type == GroupTypeEnum.SUBMIT_NODE and existing_group.group_id not in new_submit_node_group_ids:
            await session.execute(
                UserGroup.__table__.delete()
                .where(UserGroup.user_id == user.id)
                .where(UserGroup.group_id == existing_group.group_id)
            )

    # Add memberships that are missing
    for group_id in new_submit_node_group_ids:
        if group_id in existing_group_ids:
            continue
        await create_one_endpoint(
            session,
            UserGroup,
            UserGroupCreate(user_id=user.id, group_id=group_id),
        )


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
