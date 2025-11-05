from fastapi import APIRouter, Response, Depends, HTTPException
from sqlalchemy import delete, select

from api.query_parser import get_filter_query_params
from api.routes.security import is_admin
from api.util import list_endpoint, get_one_endpoint, create_one_endpoint, update_one_endpoint, delete_one_endpoint, \
    list_select_stmt
from api import models as m
from api import schemas as s
from api.db import session_generator

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Depends(is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_projects(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[s.Project]:
    return await list_endpoint(session, m.Project, s.Project, response, filter_query_params, page, page_size)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, session=Depends(session_generator)) -> None:
    """Delete a project by ID"""

    await delete_one_endpoint(session, m.Project, project_id)

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
async def get_project(project_id: int, session=Depends(session_generator)) -> s.Project:
    return await get_one_endpoint(session, m.Project, s.Project, project_id)


@router.post("", status_code=201)
async def create_project(project: s.ProjectCreate, session=Depends(session_generator)) -> s.Project:
    return await create_one_endpoint(session, m.Project, s.Project, project)


@router.put("/{project_id}", status_code=200)
async def update_project(project_id: int, project: s.ProjectUpdate, session=Depends(session_generator)) -> s.Project:
    return await update_one_endpoint(session, m.Project, s.Project, project_id, project)


@router.get("/{project_id}/users")
async def get_project_users(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[s.JoinedProjectView]:
    """Get users associated with a project"""

    filter_query_params.append(('project_id', f"eq.{project_id}"))
    return await list_endpoint(session, m.JoinedProjectView, s.JoinedProjectView, response, filter_query_params, page, page_size)


@router.post("/{project_id}/users", status_code=201)
async def add_user_to_project(project_id: int, user_project: s.UserProjectCreate, session=Depends(session_generator)) -> dict:
    """Add user to a project"""

    # Check if the user exists
    existing_user = await session.get(m.User, user_project.user_id)
    if existing_user is None:
        raise HTTPException(status_code=404, detail=f"User with id ({user_project.user_id}) not found")

    # Create the mapping
    project_user = m.UserProject(**{**user_project.model_dump(), 'project_id': project_id})
    session.add(project_user)

    return {"message": f"User {user_project.user_id} added to project {project_id}"}


@router.delete("/{project_id}/users/{user_id}", status_code=204)
async def remove_user_from_project(project_id: int, user_id: int, session=Depends(session_generator)) -> None:
    """Remove user from a project"""

    result = await session.execute(
        delete(m.UserProject)
        .where(
            m.UserProject.project_id == project_id,
            m.UserProject.user_id == user_id
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found in project")


@router.get("/{project_id}/notes")
async def get_project_notes(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[s.Note]:
    """Get notes associated with a project"""

    select_stmt = select(m.Note).join(
        m.UserNote, m.Note.id == m.UserNote.note_id
    ).where(m.UserNote.project_id == project_id)
    return await list_select_stmt(session, select_stmt, m.Note, s.Note, response, filter_query_params, page, page_size)


@router.post("/{project_id}/notes", status_code=201)
async def add_note_to_project(project_id: int, note: s.NoteCreate, session=Depends(session_generator)) -> s.Note:
    """Add a note to a project"""

    note_schema_only = s.NoteBase(**note.model_dump(exclude={'users'}))
    new_note = await create_one_endpoint(session, m.Note, s.Note, note_schema_only)

    # Add the mapping to the project
    project_note = m.UserNote(
        project_id=project_id,
        note_id=new_note.id
    )
    session.add(project_note)

    # Add the users associated with the note
    for user_id in note.users:
        user_note = m.UserNote(
            project_id=project_id,
            user_id=user_id,
            note_id=new_note.id
        )
        session.add(user_note)

    await session.refresh(new_note)

    return new_note


@router.delete("/{project_id}/notes/{note_id}", status_code=204)
async def delete_note_from_project(project_id: int, note_id: int, session=Depends(session_generator)):
    """Delete a note from a project"""

    await session.execute(
        delete(m.ProjectNote)
        .where(
            m.ProjectNote.project_id == project_id,
            m.ProjectNote.note_id == note_id
        )
    )
