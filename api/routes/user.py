from fastapi import APIRouter, Depends
from sqlalchemy import select
from starlette.responses import Response

from api.db import session_generator
import api.models as m
import api.schemas as s
from api.query_parser import get_filter_query_params
from api.routes.security import is_admin
from api.util import list_endpoint, delete_one_endpoint, get_one_endpoint, create_one_endpoint, list_select_stmt

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
async def get_users(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[s.User]:
    return await list_endpoint(session, m.User, s.User, response, filter_query_params, page, page_size)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session=Depends(session_generator)) -> None:
    await delete_one_endpoint(session, m.User, user_id)


@router.get("/{user_id}")
async def get_user(user_id: int, session=Depends(session_generator)) -> s.User:
    return await get_one_endpoint(session, m.User, s.User, user_id)


@router.post("", status_code=201)
async def create_user(user: s.UserCreate, session=Depends(session_generator)) -> s.User:
    user_only = s.UserCreateIntermediate(**user.model_dump())

    # Create the user
    created_user = await create_one_endpoint(session, m.User, s.User, user_only)
    await session.flush()

    # Create the project association
    user_project_schema = s.UserProjectCreate(project_id=user.primary_project_id, role=user.primary_project_role, is_primary=True, user_id=created_user.id)
    user_project_model = m.UserProject(**user_project_schema.model_dump())
    session.add(user_project_model)

    return created_user

@router.get("/{user_id}/projects")
async def get_user_projects(user_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[s.JoinedProjectView]:
    """Get projects associated with a user"""

    filter_query_params.append(('user_id', f"eq.{user_id}"))
    return await list_endpoint(session, m.JoinedProjectView, s.JoinedProjectView, response, filter_query_params, page, page_size)


