from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from starlette.responses import Response

from userapp.core.schemas.groups import GroupGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin, is_admin, is_user, check_is_user
from userapp.api.util import list_endpoint, delete_one_endpoint, get_one_endpoint, create_one_endpoint, \
    list_select_stmt, update_one_endpoint
from userapp.core.schemas.users import UserGet, UserPost, UserPatch, UserPostFull, UserPatchFull, \
    RestrictedUserPatch, UserTableSchema, UserGetFull
from userapp.core.schemas.user_project import UserProjectPost, UserProjectTableSchema
from userapp.core.schemas.general import JoinedProjectView as JoinedProjectViewSchema
from userapp.core.schemas.user_submit import UserSubmitPost, UserSubmitTableSchema, UserSubmitGet
from userapp.core.schemas.note import NoteGet
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable, \
    UserSubmitNodesView as UserSubmitNodesViewTable, UserSubmitNodesView
from userapp.core.models.tables import User as UserTable, UserProject, UserSubmit, Group, UserGroup

# Rebuild field for those that would cause circular imports
NoteGet.model_rebuild()

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
    return await list_endpoint(session, UserTable, response, filter_query_params, page, page_size)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session=Depends(session_generator), check_is_admin=Depends(check_is_admin)) -> None:
    await delete_one_endpoint(session, UserTable, user_id)


@router.get("/{user_id}")
async def get_user(user_id: int, session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> UserGetFull:
    return await get_one_endpoint(session, UserTable, user_id)


@router.post("", status_code=201)
async def create_user(user: UserPostFull, session=Depends(session_generator), check_is_admin=Depends(check_is_admin)) -> UserGetFull:

    # Create the user
    user_data_only = UserTableSchema(**user.model_dump())
    created_user = await create_one_endpoint(session, UserTable, user_data_only)

    # Create the project association
    user_project_schema = UserProjectTableSchema(project_id=user.primary_project_id, role=user.primary_project_role, is_primary=True, user_id=created_user.id)
    await create_one_endpoint(session, UserProject, user_project_schema)

    # Create the submit node associations
    for submit_node in user.submit_nodes:

        # Create nodes for both auth_netid True and False to simplify logic
        for for_auth_netid in [True, False]:

            user_submit_model = UserSubmitTableSchema(
                user_id=created_user.id,
                for_auth_netid=for_auth_netid,
                **submit_node.model_dump(),
            )
            await create_one_endpoint(session, UserSubmit, user_submit_model)

    await session.flush()
    await session.refresh(created_user)

    return created_user

@router.patch("/{user_id}")
async def update_user(user_id: int, user: UserPatchFull, session=Depends(session_generator), is_user=Depends(is_user), is_admin=Depends(is_admin)) -> UserGetFull:
    """Update a user"""

    # If the user is updating themselves but is not an admin, restrict what they can update
    if is_user and not is_admin:
        user_update_schema = RestrictedUserPatch(
            **user.model_dump(exclude_unset=True)
        )
        return await update_one_endpoint(session, UserTable, user_id, user_update_schema)

    elif is_admin:

        # Update user
        user_data_only = UserPatch(**user.model_dump(exclude_unset=True))
        updated_user = await update_one_endpoint(session, UserTable, user_id, user_data_only)

        # Update Submit Nodes
        for existing_submit_node in updated_user.submit_nodes:
            if existing_submit_node.submit_node_id not in [sn.submit_node_id for sn in user.submit_nodes]:

                # I blame the lack of uniformity on the previous db design
                delete_stmt = (
                    UserSubmit.__table__.delete()
                    .where(UserSubmit.user_id == user_id)
                    .where(UserSubmit.submit_node_id == existing_submit_node.submit_node_id)
                )
                await session.execute(delete_stmt)

        # Add Submit Nodes from the update
        for submit_node in user.submit_nodes:

            if submit_node.submit_node_id in [sn.submit_node_id for sn in updated_user.submit_nodes]:
                continue  # Already exists

            # Create nodes for both auth_netid True and False to simplify logic
            for for_auth_netid in [True, False]:

                user_submit_model = UserSubmitTableSchema(
                    user_id=user_id,
                    for_auth_netid=for_auth_netid,
                    **submit_node.model_dump(),
                )
                await create_one_endpoint(session, UserSubmit, user_submit_model)

        await session.refresh(updated_user)

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

    select_stmt = select(UserSubmitNodesViewTable).where(UserSubmitNodesViewTable.user_id == user_id)
    return await list_select_stmt(session, select_stmt, UserSubmitNodesViewTable, response, filter_query_params, page, page_size)


@router.get("/{user_id}/groups")
async def get_user_groups(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), check_is_user=Depends(check_is_user)) -> list[GroupGet]:
    """Get groups associated with a user"""

    # Join Group to User via the UserGroups association table and filter by user_id
    select_stmt = (
        select(Group)
        .join(UserGroup, Group.id == UserGroup.group_id)
        .join(UserTable, UserGroup.user_id == UserTable.id)
        .where(UserTable.id == user_id)
    )
    return await list_select_stmt(session, select_stmt, Group, response, filter_query_params, page, page_size)
