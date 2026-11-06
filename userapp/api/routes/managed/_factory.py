"""Factory for creating managed-sync routers.

Both the Manifest and Morgridge AD sync routers are structurally identical; they
differ only in the EntityManagerEnum value they own and in their URL prefix / tag.
This module exposes a single ``create_managed_router`` factory that builds a
fully-formed APIRouter with both PUT endpoints wired up.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from userapp.core.models.enum import AuditActionEnum, EntityManagerEnum
from userapp.core.models.tables import GroupMember, Project, Group, User
from userapp.core.models.views import (
    JoinedProjectView as JoinedProjectViewTable,
    GroupMembersView as GroupMembersViewTable,
)
from userapp.core.schemas.general import JoinedProjectView, GroupMembersView
from userapp.core.schemas.user_group import ManagedUserGroupPut
from userapp.core.schemas.user_project import ManagedUserProjectPut
from userapp.core.schemas.users import UserGet
from userapp.core.services import audit, membership
from userapp.api.routes._util import set_primary_project
from userapp.api.routes.security import check_is_admin, get_user_from_cookie
from userapp.db import session_generator

# Rebuild schemas that contain forward references once at import time.
JoinedProjectView.model_rebuild(_types_namespace={"UserGet": UserGet})


async def _sync_direct_users(session, group: Group, manager: EntityManagerEnum, desired: set[int], actor_id: int | None) -> None:
    """Hand the group to *manager* and make its direct user members equal to *desired*.

    managed_by lives on the group: a group the application manages is claimed by the first sync
    that touches it, one another system manages is refused with 409. Member groups are left
    alone, the sync only owns user members. actor_id is the logged-in caller, None for an API token."""

    if group.managed_by not in (EntityManagerEnum.APPLICATION, manager):
        raise HTTPException(status_code=409, detail=f"Group {group.id} is managed by {group.managed_by.value}")
    if group.managed_by != manager:
        old = group.managed_by
        group.managed_by = manager
        await session.flush()
        await audit.log(
            session,
            action=AuditActionEnum.metadata_changed,
            actor_id=actor_id,
            group_id=group.id,
            details={
                "entity": "group",
                "entity_id": group.id,
                "changes": {"managed_by": {"old": old.value, "new": manager.value}},
                "reason": "managed_sync",
            },
        )

    existing = set((await session.execute(
        select(GroupMember.member_user_id).where(
            GroupMember.group_id == group.id,
            GroupMember.member_user_id.is_not(None),
        )
    )).scalars())

    for user_id in existing - desired:
        await membership.remove_member(session, group_id=group.id, actor_id=actor_id, user_id=user_id)

    for user_id in desired - existing:
        await membership.add_member(session, group_id=group.id, actor_id=actor_id, user_id=user_id)


def create_managed_router(
    prefix: str,
    tags: List[str],
    manager: EntityManagerEnum,
) -> APIRouter:
    """Return an APIRouter with ``PUT /projects/{id}/users`` and
    ``PUT /groups/{id}/users`` endpoints that perform idempotent full-replace
    syncs restricted to *manager*-owned rows.

    Args:
        prefix:  URL prefix for the router (e.g. ``"/manifest"``).
        tags:    OpenAPI tags list.
        manager: The ``EntityManagerEnum`` value that owns the rows this router
                 may create / update / delete.
    """
    router = APIRouter(
        prefix=prefix,
        tags=tags,
        dependencies=[Depends(check_is_admin)],
        responses={404: {"description": "Not found"}},
    )

    # ------------------------------------------------------------------ #
    #  Projects                                                            #
    # ------------------------------------------------------------------ #

    @router.put("/projects/{project_id}/users", response_model=List[JoinedProjectView])
    async def sync_project_users(
        project_id: int,
        users: List[ManagedUserProjectPut],
        session=Depends(session_generator),
        user_token=Depends(get_user_from_cookie),
    ) -> List[JoinedProjectView]:
        f"""Replace the direct user members of a project's project group with this list.

        The project group becomes {manager.name}-managed (409 if another system manages it).
        Users no longer in the list are removed; new users are inserted;
        is_primary sets or clears the listed users' primary project.
        Returns the project group's direct members.
        """
        # Validate the project exists
        project = await session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate the project has a member group
        if project.project_group_id is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} has no project group")

        # Reject duplicate user_ids in the request
        desired = {entry.user_id: entry for entry in users}
        if len(desired) != len(users):
            raise HTTPException(status_code=422, detail="Duplicate user_id values in request")

        # Validate all user_ids exist before making any changes
        users_result = await session.execute(
            select(User.id).where(User.id.in_(desired.keys()))
        )
        found_ids = set(users_result.scalars())
        missing = set(desired.keys()) - found_ids
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"User(s) not found: {sorted(missing)}",
            )

        actor_id = user_token.user_id if user_token else None
        group = await session.get(Group, project.project_group_id)
        await _sync_direct_users(session, group, manager, set(desired.keys()), actor_id)

        # is_primary lives on the user, so a sync can only set or clear it for users it lists;
        # users it removes keep their primary project
        for user_id, entry in desired.items():
            user = await session.get(User, user_id)
            if entry.is_primary:
                await set_primary_project(session, user, project_id, actor_id)
            elif user.primary_project_id == project_id:
                await set_primary_project(session, user, None, actor_id)

        # Flush so the view reflects the changes
        await session.flush()

        result = await session.execute(
            select(JoinedProjectViewTable).where(
                JoinedProjectViewTable.project_id == project_id,
                JoinedProjectViewTable.direct.is_(True),
            )
            # The users loaded above eagerly loaded their joined_projects rows before the sync;
            # without this the identity map hands back those stale rows
            .execution_options(populate_existing=True)
        )
        return result.scalars().all()

    # ------------------------------------------------------------------ #
    #  Groups                                                              #
    # ------------------------------------------------------------------ #

    @router.put("/groups/{group_id}/users", response_model=List[GroupMembersView])
    async def sync_group_users(
        group_id: int,
        users: List[ManagedUserGroupPut],
        session=Depends(session_generator),
        user_token=Depends(get_user_from_cookie),
    ) -> List[GroupMembersView]:
        f"""Replace the direct user members of a group with this list.

        The group becomes {manager.name}-managed (409 if another system manages it).
        Users no longer in the list are removed; new users are inserted.
        Returns the group's direct members.
        """
        # Validate the group exists
        group = await session.get(Group, group_id)
        if group is None or group.deleted_at is not None:
            raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

        # Reject duplicate user_ids in the request
        desired_list = [entry.user_id for entry in users]
        desired = set(desired_list)
        if len(desired) != len(desired_list):
            raise HTTPException(status_code=422, detail="Duplicate user_id values in request")

        # Validate all user_ids exist before making any changes
        if desired:
            users_result = await session.execute(
                select(User.id).where(User.id.in_(desired))
            )
            found_ids = set(users_result.scalars())
            missing = desired - found_ids
            if missing:
                raise HTTPException(
                    status_code=404,
                    detail=f"User(s) not found: {sorted(missing)}",
                )

        await _sync_direct_users(session, group, manager, desired, user_token.user_id if user_token else None)

        # Flush so the view reflects the changes
        await session.flush()

        result = await session.execute(
            select(GroupMembersViewTable).where(
                GroupMembersViewTable.group_id == group_id,
                GroupMembersViewTable.direct.is_(True),
            )
        )
        return result.scalars().all()

    return router

