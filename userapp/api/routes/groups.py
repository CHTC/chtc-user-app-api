# Signed off by Cannon Lock 2025-11-03

from fastapi import APIRouter, Depends, Response, HTTPException
from typing import List

from sqlalchemy import select, delete

from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin
from userapp.api.util import list_endpoint, get_one_endpoint, create_one_endpoint, update_one_endpoint, list_select_stmt, \
    delete_one_endpoint, with_db_error_handling
from userapp.core.schemas.general import Relationship
from userapp.core.schemas.groups import GroupGet, GroupPost, GroupPatch
from userapp.core.schemas.users import UserGet
from userapp.core.models.tables import User as UserTable, Group as GroupTable, UserGroup


router = APIRouter(
    prefix="/groups",
    tags=["Groups"],
    dependencies=[Depends(check_is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_groups(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[GroupGet]:
    return await list_endpoint(session, GroupTable, response, filter_query_params, page, page_size)


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: int, session=Depends(session_generator)) -> None:
    await delete_one_endpoint(session, GroupTable, group_id)

@router.get("/{group_id}")
async def get_group(group_id: int, session=Depends(session_generator)) -> GroupGet:
    return await get_one_endpoint(session, GroupTable, group_id)


@router.post("", status_code=201)
async def create_group(group: GroupPost, session=Depends(session_generator)) -> GroupGet:
    return await create_one_endpoint(session, GroupTable, group)


@router.put("/{group_id}", status_code=200)
async def update_group(group_id: int, group: GroupPatch, session=Depends(session_generator)) -> GroupGet:
    return await update_one_endpoint(session, GroupTable, group_id, group)


@router.get("/{group_id}/users")
async def get_group_users(group_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> List[UserGet]:
    """Get users associated with a group"""

    select_stmt = select(UserTable).join(UserGroup).where(UserGroup.group_id == group_id)
    return await list_select_stmt(session, select_stmt, UserTable, response, filter_query_params, page, page_size)

@with_db_error_handling
@router.post("/{group_id}/users", status_code=201)
async def add_user_to_group(group_id: int, user: Relationship, session=Depends(session_generator)) -> dict:
    """Add user to a group"""

    user_group = UserGroup(user_id=user.id, group_id=group_id)
    session.add(user_group)
    return {"message": "Users added to group successfully"}


@with_db_error_handling
@router.delete("/{group_id}/users/{user_id}", status_code=204)
async def remove_user_from_group(group_id: int, user_id: int, session=Depends(session_generator)) -> None:
    """Remove user from a group"""

    result = await session.execute(
        delete(UserGroup).where(
            UserGroup.group_id == group_id,
            UserGroup.user_id == user_id
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found in group")
