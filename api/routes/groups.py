# Signed off by Cannon Lock 2025-11-03

from fastapi import APIRouter, Depends, Response, HTTPException
from typing import List

from sqlalchemy import select, delete
from sqlalchemy.exc import DBAPIError, IntegrityError

from api.db import get_async_session
from api.query_parser import get_filter_query_params
from api.schemas import Relationship
from api.util import list_endpoint, get_one_endpoint, create_one_endpoint, update_one_endpoint, list_select_stmt, \
    delete_one_endpoint
import api.models as m
import api.schemas as s

router = APIRouter(
    prefix="/groups",
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_groups(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params)) -> list[s.Group]:
    async with get_async_session() as session:
        with session.begin() :
            return await list_endpoint(session, m.Group, s.Group, response, filter_query_params, page, page_size)


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: int) -> None:
    """Delete a group by ID"""
    async with get_async_session() as session:
        with session.begin():
            await delete_one_endpoint(session, m.Group, group_id)

@router.get("/{group_id}")
async def get_group(group_id: int) -> s.Group:
    async with get_async_session() as session:
        with session.begin():
            return await get_one_endpoint(session, m.Group, s.Group, group_id)


@router.post("", status_code=201)
async def create_group(group: s.GroupCreate) -> s.Group:
    async with get_async_session() as session:
        with session.begin():
            return await create_one_endpoint(session, m.Group, s.Group, group)


@router.put("/{group_id}", status_code=200)
async def update_group(group_id: int, group: s.GroupUpdate) -> s.Group:
    async with get_async_session() as session:
        with session.begin():
            return await update_one_endpoint(session, m.Group, s.Group, group_id, group)


@router.get("/{group_id}/users")
async def get_group_users(group_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params)) -> List[s.User]:
    """Get users associated with a group"""

    select_stmt = select(*m.User.__table__.columns).join(m.UserGroup).where(m.UserGroup.group_id == group_id)
    async with get_async_session() as session:
        with session.begin():
            return await list_select_stmt(session, select_stmt, m.User, s.User, response, filter_query_params, page, page_size)


@router.post("/{group_id}/users", status_code=200)
async def add_user_to_group(group_id: int, user: Relationship) -> dict:
    """Add user to a group"""

    async with get_async_session() as session:
        async with session.begin():
            user_group = m.UserGroup(user_id=user.id, group_id=group_id)
            session.add(user_group)
        return {"message": "Users added to group successfully"}


@router.delete("/{group_id}/users/{user_id}", status_code=204)
async def remove_user_from_group(group_id: int, user_id: int) -> None:
    """Remove user from a group"""

    async with get_async_session() as session:
        async with session.begin():
            try:
                result = await session.execute(
                    delete(m.UserGroup).where(
                        m.UserGroup.group_id == group_id,
                        m.UserGroup.user_id == user_id
                    )
                )
            except (DBAPIError, IntegrityError) as e:
                if e.orig:
                    error_message = f"Database error: {e.orig}"
                else:
                    error_message = f"Database error: {str(e)}"
                raise HTTPException(status_code=400, detail=error_message)

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not associated with this group")
