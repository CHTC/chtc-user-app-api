from fastapi import APIRouter, Response, Depends
from sqlalchemy import delete, select

from api.query_parser import get_filter_query_params
from api.util import list_endpoint, get_one_endpoint, create_one_endpoint, update_one_endpoint, delete_one_endpoint
from api import models as m
from api import schemas as s
from api.db import get_async_session

router = APIRouter(
    prefix="/projects",
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_projects(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params)) -> list[s.Project]:
    return await list_endpoint(m.Project, s.Project, response, filter_query_params, page, page_size)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int) -> None:

    # Delete the notes associated with the project
    async with get_async_session() as session:
        async with session.begin():
            await get_one_endpoint(m.Project, s.Project, project_id)

            await session.execute(
                delete(m.Note)
                .where(
                    m.Note.id.in_(
                        select(m.UserNote.note_id)
                        .where(m.UserNote.project_id == project_id)
                    )
                )
            )


@router.get("/{project_id}")
async def get_project(project_id: int) -> s.Project:
    return await get_one_endpoint(m.Project, s.Project, project_id)


@router.post("", status_code=201)
async def create_project(project: s.ProjectCreate) -> s.Project:
    return await create_one_endpoint(m.Project, s.Project, project)


@router.put("/{project_id}", status_code=200)
async def update_project(project_id: int, project: s.ProjectUpdate) -> s.Project:
    return await update_one_endpoint(m.Project, s.Project, project_id, project)


@router.post("/{project_id}/notes", status_code=200)
async def add_note_to_project(project_id: int, note: s.NoteCreate) -> s.Note:
    """Add a note to a project"""

    async with get_async_session() as session:
        async with session.begin():

            new_note = await create_one_endpoint(m.Note, s.Note, note)

            # Add the mapping to the project
            project_note = m.UserNote(
                project_id=project_id,
                note_id=new_note.id
            )
            session.add(project_note)

            session.rollback()

            return new_note


@router.delete("/{project_id}/notes/{note_id}", status_code=204)
async def delete_note_from_project(project_id: int, note_id: int):
    """Delete a note from a project"""

    async with get_async_session() as session:
        async with session.begin():
            await session.execute(
                delete(m.ProjectNote)
                .where(
                    m.ProjectNote.project_id == project_id,
                    m.ProjectNote.note_id == note_id
                )
            )
        return Response(status_code=204)


@router.delete("/{project_id}/user/{user_id}", status_code=204)
async def delete_user_from_project(project_id: int, user_id: int):
    """Delete a user from a project"""

    async with get_async_session() as session:
        async with session.begin():

            # Delete the user to project mapping
            await session.execute(
                delete(m.ProjectUser)
                .where(
                    m.ProjectUser.project_id == project_id,
                    m.ProjectUser.user_id == user_id
                )
            )

            # Delete any notes associated with the user for the project
            await session.execute(
                delete(m.UserNote)
                .where(
                    m.UserNote.project_id == project_id,
                    m.UserNote.user_id == user_id
                )
            )

            # Delete any orphaned notes for the project (notes without any associated users)
            await session.execute(
                delete(m.Note)
                .where(
                    m.Note.id.in_(
                        select(m.Note.id)
                        .join(m.UserNote, isouter=True)
                        .where(
                            m.UserNote.project_id == project_id,
                            m.UserNote.user_id == None
                        )
                    )
                )
            )

        return Response(status_code=204)