import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload
from starlette.responses import Response

from userapp.core.schemas.groups import GroupGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin, is_admin, is_user, check_is_user, get_user_from_cookie, \
    is_group_administrator_of_any
from userapp.api.util import list_endpoint, delete_one_endpoint, get_one_endpoint, create_one_endpoint, \
    list_select_stmt, update_one_endpoint
from userapp.core.schemas.users import UserGet, UserPost, UserPatch, UserPostFull, UserPatchFull, \
    RestrictedUserPatch, UserTableSchema, UserGetFull, UserLookupGet
from userapp.core.schemas.general import JoinedProjectView as JoinedProjectViewSchema, UserGroupsView as UserGroupsViewSchema
from userapp.core.schemas.user_submit import UserSubmitGet
from userapp.core.schemas.note import NoteGet
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable, \
    UserSubmitView, UserGroupsView as UserGroupsViewTable
from userapp.core.models.tables import User as UserTable, Project as ProjectTable, Note as NoteTable
from userapp.core.models.enum import AuditActionEnum
from userapp.core.services import audit, membership
from userapp.api.load_options import user_load_options
from userapp.api.routes._util import _patch_user_submit_nodes, set_primary_project

# Rebuild field for those that would cause circular imports
NoteGet.model_rebuild(_types_namespace={'UserGet': UserGet})
JoinedProjectViewSchema.model_rebuild(_types_namespace={'UserGet': UserGet})
UserGroupsViewSchema.model_rebuild(_types_namespace={'UserGet': UserGet})


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


# The columns a PI or group owner may see and filter on when looking users up
_LOOKUP_COLUMNS = set(UserLookupGet.model_fields)


def _check_lookup_filters(filter_query_params: list[tuple[str, str]]) -> None:
    """Non-staff may filter only on the columns they can see; otherwise `phone1=like.608*`
    would reveal what the response hides"""

    for key, value in filter_query_params:
        # or=(name.ilike.x,netid.ilike.x): the column is what precedes the first dot of each term
        names = re.findall(r'(?:^|[(,])\s*(?:not\.)?(\w+)\.', value) if key in ("or", "and") else [key]
        for name in names:
            if name not in _LOOKUP_COLUMNS:
                raise HTTPException(status_code=400, detail=f"Filtering users on {name} is for staff")


@router.get("")
async def get_users(
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
    is_admin=Depends(is_admin),
    is_group_administrator=Depends(is_group_administrator_of_any),
) -> list[UserGetFull] | list[UserLookupGet]:
    """Staff get every user in full. A PI or group owner gets every user too, but only the fields
    needed to pick one to add to a group (id, name, username, netid, email1, active) and may filter
    on those only. Everyone else is refused."""

    if is_admin:
        return await list_endpoint(session, UserTable, response, filter_query_params, page, page_size, load_options=user_load_options)
    if not is_group_administrator:
        raise HTTPException(status_code=403, detail="User is not an admin")

    _check_lookup_filters(filter_query_params)
    rows = await list_endpoint(session, UserTable, response, filter_query_params, page, page_size)
    return [UserLookupGet.model_validate(row) for row in rows]


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session=Depends(session_generator), check_is_admin=Depends(check_is_admin)) -> None:
    await delete_one_endpoint(session, UserTable, user_id)


@router.get("/{user_id}")
async def get_user(user_id: int, session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> UserGetFull:
    return await get_one_endpoint(session, UserTable, user_id, load_options=user_load_options)


@router.post("", status_code=201)
async def create_user(user: UserPostFull, session=Depends(session_generator), check_is_admin=Depends(check_is_admin), user_token=Depends(get_user_from_cookie)) -> UserGetFull:

    actor_id = user_token.user_id if user_token else None

    # Checked before the insert so an unknown project is a 404 rather than a foreign key error
    project = None
    if user.primary_project_id is not None:
        project = await get_one_endpoint(session, ProjectTable, user.primary_project_id)
        if project.project_group_id is None:
            raise HTTPException(status_code=400, detail=f"Project {project.id} has no project group")

    # Create the user
    user_data_only = UserTableSchema(**user.model_dump())
    created_user = await create_one_endpoint(session, UserTable, user_data_only, load_options=user_load_options)
    created_user_id = created_user.id

    # Access to a project is membership in its project group; the primary project is stored on the user
    if project is not None:
        await membership.add_member(session, group_id=project.project_group_id, actor_id=actor_id, user_id=created_user_id)
        # The column was written by the insert, so audit it as the change from nothing
        await audit.log(
            session,
            action=AuditActionEnum.metadata_changed,
            actor_id=actor_id,
            member_user_id=created_user_id,
            details={"entity": "user", "entity_id": created_user_id, "changes": {"primary_project_id": {"old": None, "new": project.id}}},
        )

    # Grant access to the requested submit nodes via their associated groups
    await _patch_user_submit_nodes(session, created_user, user.submit_nodes or [], actor_id=actor_id)

    await session.flush()

    # Expire the user to force a fresh load from the database
    session.expire(created_user)
    created_user = await get_one_endpoint(session, UserTable, created_user_id, load_options=user_load_options)

    return created_user

@router.patch("/{user_id}")
async def update_user(user_id: int, user: UserPatchFull, session=Depends(session_generator), is_user=Depends(is_user), is_admin=Depends(is_admin), user_token=Depends(get_user_from_cookie)) -> UserGetFull:
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
        actor_id = user_token.user_id if user_token else None

        # The primary project goes through the helper so the change is audited; it need not be a
        # project the user belongs to
        patch_data = user_data_only.model_dump(exclude_unset=True)
        primary_sent = "primary_project_id" in patch_data
        new_primary = patch_data.pop("primary_project_id", None)
        if primary_sent and new_primary is not None:
            await get_one_endpoint(session, ProjectTable, new_primary)
        updated_user = await update_one_endpoint(session, UserTable, user_id, UserPatch(**patch_data), load_options=user_load_options)
        if primary_sent:
            await set_primary_project(session, updated_user, new_primary, actor_id)

        # Update Submit Nodes if patched
        if user.submit_nodes is not None:
            await _patch_user_submit_nodes(session, updated_user, user.submit_nodes, actor_id=actor_id)

        # Expire everything to force a fresh load: the view rows behind projects (is_primary) were
        # loaded before the change and the identity map would otherwise keep them
        session.expire_all()
        updated_user = await get_one_endpoint(session, UserTable, user_id, load_options=user_load_options)

        return updated_user

    raise HTTPException(status_code=404, detail="User not found")


@router.get("/{user_id}/projects")
async def get_user_projects(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> list[JoinedProjectViewSchema]:
    """Get projects associated with a user"""

    filter_query_params.append(('id', f"eq.{user_id}"))
    return await list_endpoint(session, JoinedProjectViewTable, response, filter_query_params, page, page_size)


@router.get("/{user_id}/submit_nodes")
async def get_user_submit_nodes(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> list[UserSubmitGet]:
    """Get submit nodes associated with a user"""

    select_stmt = select(UserSubmitView).where(UserSubmitView.user_id == user_id)
    return await list_select_stmt(session, select_stmt, UserSubmitView, response, filter_query_params, page, page_size)


@router.get("/{user_id}/groups")
async def get_user_groups(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> list[UserGroupsViewSchema]:
    """Get the groups a user is an effective member of, and how"""

    select_stmt = select(UserGroupsViewTable).where(UserGroupsViewTable.user_id == user_id)
    return await list_select_stmt(session, select_stmt, UserGroupsViewTable, response, filter_query_params, page, page_size)
