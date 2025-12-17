from fastapi import APIRouter, Response, Depends, HTTPException
from sqlalchemy import delete, select

from userapp.core.schemas.project_note import ProjectNotePost
from userapp.core.schemas.user_note import UserNoteTableSchema
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin, user
from userapp.api.util import list_endpoint, get_one_endpoint, create_one_endpoint, update_one_endpoint, delete_one_endpoint, \
    list_select_stmt
from userapp.core.schemas.projects import ProjectGet, ProjectPost, ProjectPatch
from userapp.core.schemas.user_project import UserProjectPost, UserProjectTableSchema
from userapp.core.schemas.note import NoteGet, NoteTableSchema, NotePost, NoteGetFull
from userapp.core.schemas.general import JoinedProjectView as JoinedProjectViewSchema
from userapp.core.models.tables import Project as ProjectTable, Note as NoteTable, UserNote, User, UserProject
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable
from userapp.core.schemas.users import UserGet

# Rebuild field for those that would cause circular imports
NoteGetFull.model_rebuild()

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Depends(check_is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_projects(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[ProjectGet]:
    x = await list_endpoint(session, ProjectTable, response, filter_query_params, page, page_size)
    return x


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, session=Depends(session_generator)) -> None:
    """Delete a project by ID"""

    await delete_one_endpoint(session, ProjectTable, project_id)

    await session.execute(
        delete(NoteTable)
        .where(
            NoteTable.id.in_(
                select(UserNote.note_id)
                .where(UserNote.project_id == project_id)
            )
        )
    )


@router.get("/{project_id}")
async def get_project(project_id: int, session=Depends(session_generator)) -> ProjectGet:
    return await get_one_endpoint(session, ProjectTable,  project_id)


@router.post("", status_code=201)
async def create_project(project: ProjectPost, session=Depends(session_generator)) -> ProjectGet:
    return await create_one_endpoint(session, ProjectTable,  project)


@router.put("/{project_id}", status_code=200)
async def update_project(project_id: int, project: ProjectPatch, session=Depends(session_generator)) -> ProjectGet:
    return await update_one_endpoint(session, ProjectTable,  project_id, project)


@router.get("/{project_id}/users")
async def get_project_users(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[JoinedProjectViewSchema]:
    """Get users associated with a project"""

    filter_query_params.append(('project_id', f"eq.{project_id}"))
    return await list_endpoint(session, JoinedProjectViewTable, response, filter_query_params, page, page_size)


@router.post("/{project_id}/users", status_code=201)
async def add_user_to_project(project_id: int, user_project: UserProjectPost, session=Depends(session_generator)) -> dict:
    """Add user to a project"""

    # Check if the user exists
    existing_user = await get_one_endpoint(session, User, user_project.user_id)
    if existing_user is None:
        raise HTTPException(status_code=404, detail=f"User with id ({user_project.user_id}) not found")

    # Create the mapping
    project_user = UserProjectTableSchema(**{**user_project.model_dump(), 'project_id': project_id})
    await create_one_endpoint(session, UserProject, project_user)

    return {"message": f"User {user_project.user_id} added to project {project_id}"}


@router.delete("/{project_id}/users/{user_id}", status_code=204)
async def remove_user_from_project(project_id: int, user_id: int, session=Depends(session_generator)) -> None:
    """Remove user from a project"""

    result = await session.execute(
        delete(UserProject)
        .where(
            UserProject.project_id == project_id,
            UserProject.user_id == user_id
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found in project")


@router.get("/{project_id}/notes")
async def get_project_notes(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[NoteGetFull]:
    """Get notes associated with a project"""

    select_stmt = select(NoteTable).join(
        UserNote, NoteTable.id == UserNote.note_id
    ).where(UserNote.project_id == project_id)
    return await list_select_stmt(session, select_stmt, NoteTable, response, filter_query_params, page, page_size)


@router.get("/{project_id}/notes/{note_id}")
async def get_project_note(project_id: int, note_id: int, session=Depends(session_generator)) -> NoteGetFull:
    """Get a specific note associated with a project"""

    select_stmt = select(NoteTable).join(
        UserNote, NoteTable.id == UserNote.note_id
    ).where(
        UserNote.project_id == project_id,
        UserNote.note_id == note_id
    )
    result = await session.scalar(select_stmt)
    if result is None:
        raise HTTPException(status_code=404, detail="Note not found in project")
    return result


@router.post("/{project_id}/notes", status_code=201)
async def add_note_to_project(project_id: int, note: ProjectNotePost, session=Depends(session_generator), user=Depends(user)) -> NoteGetFull:
    """Add a note to a project"""

    note_row = NoteTableSchema(**{**note.model_dump(), 'author': user.username})
    new_note = await create_one_endpoint(session, NoteTable, note_row)

    # Associate this note to the project
    project_note = UserNoteTableSchema(
        project_id=project_id,
        note_id=new_note.id
    )
    user_project_notes = [
        UserNoteTableSchema(
            project_id=project_id,
            user_id=x,
            note_id=new_note.id
        ) for x in note.users
    ]

    # Associate this note to the provided users
    for user_note in [project_note, *user_project_notes]:
        await create_one_endpoint(session, UserNote, user_note)

    # Flush the associations and refresh the note to load them in
    await session.flush()
    await session.refresh(new_note)

    return new_note


@router.delete("/{project_id}/notes/{note_id}", status_code=204)
async def delete_note_from_project(project_id: int, note_id: int, session=Depends(session_generator)):
    """Delete a note from a project"""

    await session.execute(
        delete(UserNote)
        .where(
            UserNote.project_id == project_id,
            UserNote.note_id == note_id
        )
    )

