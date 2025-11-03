from fastapi import APIRouter, Depends
from sqlalchemy import select
from starlette.responses import Response

from api.db import get_async_session
import api.models as m
import api.schemas as s
from api.query_parser import get_filter_query_params
from api.util import list_endpoint

router = APIRouter(
    prefix="/users",
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_users(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params)) -> list[s.User]:
    return await list_endpoint(m.User, s.User, response, filter_query_params, page, page_size)


# @router.get("/{user_id}/groups")
# async def get_user_groups(user_id: int) -> list[s.Group]:
#     """Get groups for a user"""
#
#     async with get_async_session() as session:
#         result = await session.execute(
#             select(m.Group)
#             .join(m.UserGroup, m.Group.id == m.UserGroup.group_id)
#             .where(m.UserGroup.user_id == user_id)
#         )
#         groups = result.scalars().all()
#         return [s.Group.model_validate(group) for group in groups]
#
#
# @router.get("/{user_id}/projects")
# async def get_user_projects(user_id: int):
#     """Get a specific project for a user"""
#
#     async with get_async_session() as session:
#         result = await session.execute(
#             select(m.Project)
#             .join(m.UserProject, m.Project.id == m.UserProject.project_id)
#             .where(m.UserProject.user_id == user_id)
#         )
#         projects = result.scalars().all()
#         return [s.Project.model_validate(project) for project in projects]
#
#
# @router.get("/{user_id}/notes")
# async def get_user_notes(user_id: int):
#     """Get notes for a user"""
#
#     async with get_async_session() as session:
#         result = await session.execute(
#             select(m.Note)
#             .join(m.UserNote, m.Note.id == m.UserNote.note_id)
#             .where(m.UserNote.user_id == user_id)
#         )
#         notes = result.scalars().all()
#         return [s.Note.model_validate(note) for note in notes]
#
#
# @router.get("/{user_id}/submit_nodes")
# async def get_user_submit_nodes(user_id: int):
#     """Get submit nodes for a user"""
#
#     async with get_async_session() as session:
#         result = await session.execute(
#             select(m.SubmitNode)
#             .join(m.UserSubmit, m.SubmitNode.id == m.UserSubmit.submit_node_id)
#             .where(m.UserSubmit.user_id == user_id)
#         )
#         submit_nodes = result.scalars().all()
#         return [s.SubmitNode.model_validate(submit_node) for submit_node in submit_nodes]
