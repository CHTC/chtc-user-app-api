from fastapi import APIRouter, Depends
from sqlalchemy import select
from starlette.responses import Response
from passlib.hash import sha256_crypt

from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import is_admin
from userapp.api.util import list_endpoint, delete_one_endpoint, get_one_endpoint, create_one_endpoint, \
    list_select_stmt, update_one_endpoint
from userapp.core.schemas.users import User as UserSchema, UserCreateFull, UserCreateSimple
from userapp.core.schemas.user_project import UserProjectCreate
from userapp.core.schemas.general import JoinedProjectView as JoinedProjectViewSchema
from userapp.core.schemas.user_submit import UserSubmit as UserSubmitSchema
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable, UserSubmitNodesView as UserSubmitNodesViewTable
from userapp.core.models.tables import User as UserTable, UserProject, UserSubmit as UserSubmitTable

router = APIRouter(
    prefix="/users",
    tags=["User"],
    dependencies=[Depends(is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_users(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[UserSchema]:
    return await list_endpoint(session, UserTable, response, filter_query_params, page, page_size)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session=Depends(session_generator)) -> None:
    await delete_one_endpoint(session, UserTable, user_id)


@router.get("/{user_id}")
async def get_user(user_id: int, session=Depends(session_generator)) -> UserSchema:
    return await get_one_endpoint(session, UserTable, user_id)


@router.post("", status_code=201)
async def create_user(user: UserCreateFull, session=Depends(session_generator)) -> UserSchema:

    # Create the user
    user_data_only = UserCreateSimple(**user.model_dump())
    user_data_only.password = sha256_crypt.hash(user.password)
    created_user = await create_one_endpoint(session, UserTable, user_data_only)
    await session.flush()

    # Create the project association
    user_project_schema = UserProjectCreate(project_id=user.primary_project_id, role=user.primary_project_role, is_primary=True, user_id=created_user.id)
    user_project_model = UserProject(**user_project_schema.model_dump())
    session.add(user_project_model)

    # Create the submit node associations
    for submit_node in user.submit_nodes:
        user_submit_model = UserSubmitTable(
            user_id=created_user.id,
            **submit_node.model_dump()
        )
        session.add(user_submit_model)

    await session.refresh(created_user)

    return created_user

@router.put("/{user_id}")
async def update_user(user_id: int, user: UserCreateFull, session=Depends(session_generator)) -> UserSchema:
    """Update a user"""

    return await update_one_endpoint(session, UserTable, user_id, **user.model_dump())



@router.get("/{user_id}/projects")
async def get_user_projects(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[JoinedProjectViewSchema]:
    """Get projects associated with a user"""

    filter_query_params.append(('user_id', f"eq.{user_id}"))
    return await list_endpoint(session, JoinedProjectViewTable, response, filter_query_params, page, page_size)


@router.get("/{user_id}/submit_nodes")
async def get_user_submit_nodes(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[UserSubmitSchema]:
    """Get submit nodes associated with a user"""

    select_stmt = select(UserSubmitNodesViewTable).where(UserSubmitNodesViewTable.user_id == user_id)
    return await list_select_stmt(session, select_stmt, UserSubmitNodesViewTable, response, filter_query_params, page, page_size)
