from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload
from starlette.responses import Response

from userapp.core.schemas.groups import GroupGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin, is_admin, is_user, check_is_user
from userapp.api.util import list_endpoint, delete_one_endpoint, get_one_endpoint, create_one_endpoint, \
    list_select_stmt, update_one_endpoint
from userapp.core.schemas.users import UserGet, UserPost, UserPatch, UserPostFull, UserPatchFull, \
    RestrictedUserPatch, UserTableSchema, UserGetFull
from userapp.core.schemas.user_project import UserProjectPost, UserProjectTableSchema, UserProjectPatch
from userapp.core.schemas.user_group import UserGroupPatch
from userapp.core.schemas.general import JoinedProjectView as JoinedProjectViewSchema, UserGroupView as UserGroupViewSchema
from userapp.core.schemas.note import NoteGet
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable, \
    UserGroupView as UserGroupViewTable
from userapp.core.models.tables import User as UserTable, UserProject, Group, UserGroup, Note as NoteTable
from userapp.api.load_options import user_load_options
from userapp.api.routes._util import _patch_user_project, _patch_user_group

# Rebuild field for those that would cause circular imports
NoteGet.model_rebuild(_types_namespace={'UserGet': UserGet})
JoinedProjectViewSchema.model_rebuild(_types_namespace={'UserGet': UserGet})
UserGroupViewSchema.model_rebuild(_types_namespace={'UserGet': UserGet})


router = APIRouter(
    prefix="/users",
    tags=["User"],
    dependencies=[],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


@router.get("")
async def get_users(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), check_is_admin=Depends(check_is_admin)) -> list[UserGetFull]:
    return await list_endpoint(session, UserTable, response, filter_query_params, page, page_size, load_options=user_load_options)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session=Depends(session_generator), check_is_admin=Depends(check_is_admin)) -> None:
    await delete_one_endpoint(session, UserTable, user_id)


@router.get("/{user_id}")
async def get_user(user_id: int, session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> UserGetFull:
    return await get_one_endpoint(session, UserTable, user_id, load_options=user_load_options)


@router.post("", status_code=201)
async def create_user(user: UserPostFull, session=Depends(session_generator), check_is_admin=Depends(check_is_admin)) -> UserGetFull:

    # Create the user
    user_data_only = UserTableSchema(**user.model_dump())
    created_user = await create_one_endpoint(session, UserTable, user_data_only, load_options=user_load_options)
    created_user_id = created_user.id

    # Create the project association
    user_project_schema = UserProjectTableSchema(project_id=user.primary_project_id, role=user.primary_project_role, is_primary=True, user_id=created_user.id)
    await create_one_endpoint(session, UserProject, user_project_schema)

    await session.flush()

    # Expire the user to force a fresh load from the database
    session.expire(created_user)
    created_user = await get_one_endpoint(session, UserTable, created_user_id, load_options=user_load_options)

    return created_user

@router.patch("/{user_id}")
async def update_user(user_id: int, user: UserPatchFull, session=Depends(session_generator), is_user=Depends(is_user), is_admin=Depends(is_admin)) -> UserGetFull:
    """Update a user"""

    # If the user is updating themselves but is not an admin, restrict what they can update
    if is_user and not is_admin:
        user_update_schema = RestrictedUserPatch(
            **user.model_dump(exclude_unset=True)
        )
        return await update_one_endpoint(session, UserTable, user_id, user_update_schema, load_options=user_load_options)

    elif is_admin:
        # Update user
        user_data_only = UserPatch(**user.model_dump(exclude_unset=True))
        updated_user = await update_one_endpoint(session, UserTable, user_id, user_data_only, load_options=user_load_options)

        # Expire the instance to force a fresh load from the database
        session.expire(updated_user)
        updated_user = await get_one_endpoint(session, UserTable, user_id, load_options=user_load_options)

        return updated_user

    raise HTTPException(status_code=404, detail="User not found")


@router.get("/{user_id}/projects")
async def get_user_projects(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> list[JoinedProjectViewSchema]:
    """Get projects associated with a user"""

    filter_query_params.append(('id', f"eq.{user_id}"))
    return await list_endpoint(session, JoinedProjectViewTable, response, filter_query_params, page, page_size)


@router.get("/{user_id}/groups")
async def get_user_groups(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> list[UserGroupViewSchema]:
    """Get groups associated with a user"""

    # Join Group to User via the UserGroups association table and filter by user_id
    select_stmt = select(UserGroupViewTable).where(UserGroupViewTable.user_id == user_id)
    return await list_select_stmt(session, select_stmt, UserGroupViewTable, response, filter_query_params, page, page_size)


@router.patch("/{user_id}/projects/{project_id}")
async def patch_user_project(
    user_id: int,
    project_id: int,
    patch: UserProjectPatch,
    session=Depends(session_generator),
    check_is_admin=Depends(check_is_admin),
) -> JoinedProjectViewSchema:
    """Patch a user's membership in a project (role, is_primary, managed_by)."""
    return await _patch_user_project(session, user_id, project_id, patch)


@router.patch("/{user_id}/groups/{group_id}")
async def patch_user_group(
    user_id: int,
    group_id: int,
    patch: UserGroupPatch,
    session=Depends(session_generator),
    check_is_admin=Depends(check_is_admin),
) -> UserGroupViewSchema:
    """Patch a user's membership in a group (managed_by)."""
    return await _patch_user_group(session, user_id, group_id, patch)

