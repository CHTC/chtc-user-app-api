"""Factory for creating managed-sync routers.

Both the Manifest and Morgridge AD sync routers are structurally identical; they
differ only in the EntityManagerEnum value they own and in their URL prefix / tag.
This module exposes a single ``create_managed_router`` factory that builds a
fully-formed APIRouter with both PUT endpoints wired up.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select

from userapp.core.models.enum import EntityManagerEnum
from userapp.core.models.tables import UserProject, UserGroup, Project, Group, User
from userapp.core.models.views import (
    JoinedProjectView as JoinedProjectViewTable,
    UserGroupView as UserGroupViewTable,
)
from userapp.core.schemas.general import JoinedProjectView, UserGroupView
from userapp.core.schemas.user_group import ManagedUserGroupPut
from userapp.core.schemas.user_project import ManagedUserProjectPut
from userapp.core.schemas.users import UserGet
from userapp.api.routes.security import check_is_admin
from userapp.api.util import with_db_error_handling
from userapp.db import session_generator

# Rebuild schemas that contain forward references once at import time.
JoinedProjectView.model_rebuild(_types_namespace={"UserGet": UserGet})
UserGroupView.model_rebuild(_types_namespace={"UserGet": UserGet})


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

    @with_db_error_handling
    @router.put("/projects/{project_id}/users", response_model=List[JoinedProjectView])
    async def sync_project_users(
        project_id: int,
        users: List[ManagedUserProjectPut],
        session=Depends(session_generator),
    ) -> List[JoinedProjectView]:
        f"""Replace the set of {manager.name}-managed members of a project.

        Rows owned by other managers are not touched.
        Users no longer in the list are removed; new users are inserted;
        existing users whose role or is_primary changed are updated.
        Users already claimed by another manager are silently skipped.
        Returns the full current set of {manager.name}-managed memberships for
        this project.
        """
        # Validate the project exists
        project = await session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Reject duplicate user_ids in the request
        desired = {entry.user_id: entry for entry in users}
        if len(desired) != len(users):
            raise HTTPException(status_code=422, detail="Duplicate user_id values in request")

        # Validate all user_ids exist before making any changes
        if desired:
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

        # Fetch existing manager-owned rows for this project
        existing_result = await session.execute(
            select(UserProject).where(
                UserProject.project_id == project_id,
                UserProject.managed_by == manager,
            )
        )
        existing = {row.user_id: row for row in existing_result.scalars().all()}

        to_remove = set(existing.keys()) - set(desired.keys())
        to_add = set(desired.keys()) - set(existing.keys())
        to_check = set(existing.keys()) & set(desired.keys())

        # Silently skip users already claimed by another manager
        if to_add:
            claimed_result = await session.execute(
                select(UserProject.user_id).where(
                    UserProject.project_id == project_id,
                    UserProject.user_id.in_(to_add),
                    UserProject.managed_by != manager,
                )
            )
            to_add -= set(claimed_result.scalars())

        # Remove members no longer in the list
        if to_remove:
            await session.execute(
                delete(UserProject).where(
                    UserProject.project_id == project_id,
                    UserProject.user_id.in_(to_remove),
                    UserProject.managed_by == manager,
                )
            )

        # Add new members
        for user_id in to_add:
            entry = desired[user_id]
            session.add(
                UserProject(
                    project_id=project_id,
                    user_id=user_id,
                    role=entry.role,
                    is_primary=entry.is_primary,
                    managed_by=manager,
                )
            )

        # Update members whose role or is_primary changed
        for user_id in to_check:
            row = existing[user_id]
            entry = desired[user_id]
            if row.role != entry.role or row.is_primary != entry.is_primary:
                row.role = entry.role
                row.is_primary = entry.is_primary

        # Flush so the view reflects the changes
        await session.flush()

        result = await session.execute(
            select(JoinedProjectViewTable).where(
                JoinedProjectViewTable.project_id == project_id,
                JoinedProjectViewTable.managed_by == manager,
            )
        )
        return result.scalars().all()

    # ------------------------------------------------------------------ #
    #  Groups                                                              #
    # ------------------------------------------------------------------ #

    @with_db_error_handling
    @router.put("/groups/{group_id}/users", response_model=List[UserGroupView])
    async def sync_group_users(
        group_id: int,
        users: List[ManagedUserGroupPut],
        session=Depends(session_generator),
    ) -> List[UserGroupView]:
        f"""Replace the set of {manager.name}-managed members of a group.

        Rows owned by other managers are not touched.
        Users no longer in the list are removed; new users are inserted.
        Users already claimed by another manager are silently skipped.
        Returns the full current set of {manager.name}-managed memberships for
        this group.
        """
        # Validate the group exists
        group = await session.get(Group, group_id)
        if group is None:
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

        # Fetch existing manager-owned rows for this group
        existing_result = await session.execute(
            select(UserGroup.user_id).where(
                UserGroup.group_id == group_id,
                UserGroup.managed_by == manager,
            )
        )
        existing = set(existing_result.scalars())

        to_remove = existing - desired
        to_add = desired - existing

        # Silently skip users already claimed by another manager
        if to_add:
            claimed_result = await session.execute(
                select(UserGroup.user_id).where(
                    UserGroup.group_id == group_id,
                    UserGroup.user_id.in_(to_add),
                    UserGroup.managed_by != manager,
                )
            )
            to_add -= set(claimed_result.scalars())

        # Remove members no longer in the list
        if to_remove:
            await session.execute(
                delete(UserGroup).where(
                    UserGroup.group_id == group_id,
                    UserGroup.user_id.in_(to_remove),
                    UserGroup.managed_by == manager,
                )
            )

        # Add new members
        for user_id in to_add:
            session.add(
                UserGroup(
                    group_id=group_id,
                    user_id=user_id,
                    managed_by=manager,
                )
            )

        # Flush so the view reflects the changes
        await session.flush()

        result = await session.execute(
            select(UserGroupViewTable).where(
                UserGroupViewTable.group_id == group_id,
                UserGroupViewTable.managed_by == manager,
            )
        )
        return result.scalars().all()

    return router

