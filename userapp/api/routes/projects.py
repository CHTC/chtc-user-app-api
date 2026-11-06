from fastapi import APIRouter, Response, Depends, HTTPException
from sqlalchemy import delete, select

from userapp.core.schemas.project_note import ProjectNotePost
from userapp.core.schemas.user_note import UserNoteTableSchema
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin, check_can_edit_project, \
    check_can_administer_project_members, get_user_from_cookie, is_admin
from userapp.api.routes._util import json_value
from userapp.api.util import list_endpoint, get_one_endpoint, create_one_endpoint, update_one_endpoint, \
    delete_one_endpoint, list_select_stmt
from userapp.core.schemas.projects import ProjectGet, ProjectGetFull, ProjectPost, ProjectPatch
from userapp.api.load_options import project_load_options
from userapp.core.schemas.user_project import UserProjectPost, ProjectPiPost, ProjectGroupMemberPost
from userapp.core.schemas.groups import GroupMemberGet
from userapp.core.schemas.note import NoteGet, NoteTableSchema, NotePost, NoteGetFull
from userapp.core.schemas.general import JoinedProjectView as JoinedProjectViewSchema, \
    GroupMembersView as GroupMembersViewSchema
from userapp.core.models.enum import AuditActionEnum
from userapp.core.models.tables import Project as ProjectTable, Note as NoteTable, UserNote, GroupEffectiveMember, \
    GroupMember
from userapp.core.services import audit, membership
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable, \
    GroupMembersView as GroupMembersViewTable
from userapp.core.schemas.users import UserGet

# Rebuild fields that use forward references to avoid circular imports
NoteGet.model_rebuild(_types_namespace={'UserGet': UserGet})
NoteGetFull.model_rebuild(_types_namespace={'UserGet': UserGet})
ProjectGet.model_rebuild(_types_namespace={'UserGet': UserGet})
ProjectGetFull.model_rebuild(_types_namespace={'UserGet': UserGet})
JoinedProjectViewSchema.model_rebuild(_types_namespace={'UserGet': UserGet})

# Fields only staff may change; a PI edits the rest of the project's metadata
STAFF_ONLY_PROJECT_FIELDS = {"pi_group_id", "project_group_id", "accounting_group", "staff1", "staff2", "ticket"}

# Staff-only routes get this per route because the viewing and editing routes below are open to
# PIs and project administrators
staff_only = [Depends(check_is_admin)]

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


def _actor_id(user_token) -> int | None:
    # API tokens and ALLOW_ADMIN_ACCESS have no user behind them, so those act as the system
    return user_token.user_id if user_token else None


async def _get_project_or_404(session, project_id: int) -> ProjectTable:
    project = await session.get(ProjectTable, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def check_can_view_project(project_id: int, session=Depends(session_generator), is_admin=Depends(is_admin), user_token=Depends(get_user_from_cookie)) -> None:
    """Staff, an effective member of the pi group, or an administrator of the project group.
    Local to this module because security.py only knows the edit and member-administration rules."""

    if is_admin:
        return
    project = await _get_project_or_404(session, project_id)
    if user_token:
        if project.pi_group_id is not None:
            is_pi = await session.scalar(
                select(GroupEffectiveMember.user_id).where(
                    GroupEffectiveMember.group_id == project.pi_group_id,
                    GroupEffectiveMember.user_id == user_token.user_id,
                ).limit(1)
            )
            if is_pi is not None:
                return
        if project.project_group_id is not None \
                and await membership.is_group_administrator(session, user_token.user_id, project.project_group_id):
            return
    raise HTTPException(status_code=403, detail="User may not view this project")


@router.get("", dependencies=staff_only)
async def get_projects(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[ProjectGetFull]:
    return await list_endpoint(session, ProjectTable, response, filter_query_params, page, page_size, load_options=project_load_options)


@router.delete("/{project_id}", status_code=204, dependencies=staff_only)
async def delete_project(project_id: int, session=Depends(session_generator)) -> None:
    """Delete a project by ID. Its groups stay: they are ordinary groups that other things may reference.
    users.primary_project_id is set to NULL by the database."""

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


@router.get("/{project_id}", dependencies=[Depends(check_can_view_project)])
async def get_project(project_id: int, session=Depends(session_generator)) -> ProjectGetFull:
    return await get_one_endpoint(session, ProjectTable,  project_id, load_options=project_load_options)


@router.post("", status_code=201, dependencies=staff_only)
async def create_project(project: ProjectPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> ProjectGetFull:
    actor_id = _actor_id(user_token)

    # Groups handed in must exist before anything is created
    for group_id in (project.pi_group_id, project.project_group_id):
        if group_id is not None:
            await membership.get_live_group(session, group_id)

    created = ProjectTable(**project.model_dump(exclude={"pi_ids"}))
    session.add(created)
    await session.flush()
    await session.refresh(created)
    pi_group_id, project_group_id = created.pi_group_id, created.project_group_id

    if pi_group_id is None and project_group_id is None:
        await membership.create_project_groups(session, actor_id=actor_id, project=created)
    else:
        # Only the group that is missing is created, around the one staff supplied
        slug = membership.slugify_group_name(created.name) or "project"
        created_for = {"entity": "project", "entity_id": created.id}
        if pi_group_id is None:
            pi_group = await membership.create_group(
                session, actor_id=actor_id, name=await membership.unique_group_name(session, slug, "_pi"),
                created_for={**created_for, "role": "pi"},
            )
            created.pi_group_id = pi_group.id
        elif project_group_id is None:
            managers = await membership.create_group(
                session, actor_id=actor_id, name=await membership.unique_group_name(session, slug, "_managers"),
                owner_group_id=pi_group_id, created_for={**created_for, "role": "managers"},
            )
            project_group = await membership.create_group(
                session, actor_id=actor_id, name=await membership.unique_group_name(session, slug),
                owner_group_id=managers.id, created_for={**created_for, "role": "project"},
            )
            await membership.add_member(session, group_id=managers.id, actor_id=actor_id, member_group_id=pi_group_id)
            await membership.add_member(session, group_id=project_group.id, actor_id=actor_id, member_group_id=pi_group_id)
            created.project_group_id = project_group.id
        await session.flush()

    for pi_id in dict.fromkeys(project.pi_ids or []):
        await membership.add_member(session, group_id=created.pi_group_id, actor_id=actor_id, user_id=pi_id)

    return await get_one_endpoint(session, ProjectTable, created.id, load_options=project_load_options)


@router.put("/{project_id}", status_code=200, dependencies=[Depends(check_can_edit_project)])
async def update_project(project_id: int, project: ProjectPatch, session=Depends(session_generator), is_admin=Depends(is_admin), user_token=Depends(get_user_from_cookie)) -> ProjectGetFull:
    """Staff change anything; a PI changes everything but the group pointers, accounting group, staff and ticket"""

    if not is_admin and project.model_fields_set & STAFF_ONLY_PROJECT_FIELDS:
        raise HTTPException(
            status_code=403,
            detail=f"Only staff can change {sorted(project.model_fields_set & STAFF_ONLY_PROJECT_FIELDS)}",
        )

    for group_id in (project.pi_group_id, project.project_group_id):
        if group_id is not None:
            await membership.get_live_group(session, group_id)

    db_project = await _get_project_or_404(session, project_id)
    changes = {}
    for field, new in project.model_dump(exclude_unset=True).items():
        old = getattr(db_project, field)
        if old != new:
            changes[field] = {"old": json_value(old), "new": json_value(new)}

    updated = await update_one_endpoint(session, ProjectTable, project_id, project, load_options=project_load_options)

    if changes:
        await audit.log(
            session,
            action=AuditActionEnum.metadata_changed,
            actor_id=_actor_id(user_token),
            details={"entity": "project", "entity_id": project_id, "changes": changes},
        )
    return updated


@router.get("/{project_id}/users", dependencies=[Depends(check_can_view_project)])
async def get_project_users(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[JoinedProjectViewSchema]:
    """Get users associated with a project"""

    filter_query_params.append(('project_id', f"eq.{project_id}"))
    return await list_endpoint(session, JoinedProjectViewTable, response, filter_query_params, page, page_size)


async def _group_id_of(session, project_id: int, column: str, label: str) -> int:
    project = await _get_project_or_404(session, project_id)
    group_id = getattr(project, column)
    if group_id is None:
        raise HTTPException(status_code=400, detail=f"Project {project_id} has no {label}")
    return group_id


async def _remove_direct_user(session, group_id: int, user_id: int, actor_id: int | None, label: str) -> None:
    """remove_member, except that the 404 says when the user still has access through another group"""

    row = await session.scalar(
        select(GroupMembersViewTable).where(GroupMembersViewTable.group_id == group_id, GroupMembersViewTable.user_id == user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"User is not a member of this project's {label}")
    if not row.direct:
        # Paths start at this group; the groups below it are what the caller can act on
        through = ", ".join(" > ".join(path[1:]) for path in row.path_names)
        raise HTTPException(
            status_code=404,
            detail=f"User is not a direct member of this project's {label}; access comes through {through}",
        )

    await membership.remove_member(session, group_id=group_id, actor_id=actor_id, user_id=user_id)


@router.post("/{project_id}/users", status_code=201, dependencies=[Depends(check_can_administer_project_members)])
async def add_user_to_project(project_id: int, user_project: UserProjectPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> dict:
    """Add user to a project"""

    await membership.add_member(
        session,
        group_id=await _group_id_of(session, project_id, "project_group_id", "project group"),
        actor_id=_actor_id(user_token),
        user_id=user_project.user_id,
    )

    return {"message": f"User {user_project.user_id} added to project {project_id}"}


@router.delete("/{project_id}/users/{user_id}", status_code=204, dependencies=[Depends(check_can_administer_project_members)])
async def remove_user_from_project(project_id: int, user_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> None:
    """Remove a user's direct membership of the project group. The user's primary project is kept."""

    await _remove_direct_user(
        session, await _group_id_of(session, project_id, "project_group_id", "project group"),
        user_id, _actor_id(user_token), "group",
    )


@router.get("/{project_id}/pis", dependencies=[Depends(check_can_view_project)])
async def get_project_pis(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[GroupMembersViewSchema]:
    """Users in the project's pi group, directly or through another group"""

    project = await _get_project_or_404(session, project_id)
    # A project without a pi group has no PIs; the filter matches nothing
    filter_query_params.append(('group_id', f"eq.{project.pi_group_id if project.pi_group_id is not None else -1}"))
    return await list_endpoint(session, GroupMembersViewTable, response, filter_query_params, page, page_size)


@router.post("/{project_id}/pis", status_code=201, dependencies=staff_only)
async def add_pi_to_project(project_id: int, pi: ProjectPiPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> dict:
    await membership.add_member(
        session,
        group_id=await _group_id_of(session, project_id, "pi_group_id", "pi group"),
        actor_id=_actor_id(user_token),
        user_id=pi.user_id,
    )
    return {"message": f"User {pi.user_id} added as a PI of project {project_id}"}


@router.delete("/{project_id}/pis/{user_id}", status_code=204, dependencies=staff_only)
async def remove_pi_from_project(project_id: int, user_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> None:
    await _remove_direct_user(
        session, await _group_id_of(session, project_id, "pi_group_id", "pi group"),
        user_id, _actor_id(user_token), "pi group",
    )


async def _direct_group_members(session, project_id: int, column: str, response, filter_query_params, page, page_size) -> list[GroupMemberGet]:
    """The groups that are direct members of one of the project's groups. Their users show up in
    /users and /pis with the path that grants access; this lists the group rows themselves."""

    project = await _get_project_or_404(session, project_id)
    group_id = getattr(project, column)
    # A project without the group has no member groups; the filter matches nothing
    select_stmt = select(GroupMember).where(
        GroupMember.group_id == (group_id if group_id is not None else -1),
        GroupMember.member_group_id.is_not(None),
    )
    return await list_select_stmt(
        session, select_stmt, GroupMember, response, filter_query_params, page, page_size,
        default_order_by=[GroupMember.id],
    )


@router.get("/{project_id}/groups", dependencies=[Depends(check_can_view_project)])
async def get_project_groups(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[GroupMemberGet]:
    """Groups that are direct members of the project's project group"""

    return await _direct_group_members(session, project_id, "project_group_id", response, filter_query_params, page, page_size)


@router.post("/{project_id}/groups", status_code=201, dependencies=[Depends(check_can_administer_project_members)])
async def add_group_to_project(project_id: int, member: ProjectGroupMemberPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> GroupMemberGet:
    """Add a group to the project's project group; its effective members gain the project's access"""

    return await membership.add_member(
        session,
        group_id=await _group_id_of(session, project_id, "project_group_id", "project group"),
        actor_id=_actor_id(user_token),
        member_group_id=member.group_id,
    )


@router.delete("/{project_id}/groups/{member_id}", status_code=204, dependencies=[Depends(check_can_administer_project_members)])
async def remove_group_from_project(project_id: int, member_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> None:
    await membership.remove_member(
        session,
        group_id=await _group_id_of(session, project_id, "project_group_id", "project group"),
        actor_id=_actor_id(user_token),
        member_group_id=member_id,
    )


@router.get("/{project_id}/pi_groups", dependencies=[Depends(check_can_view_project)])
async def get_project_pi_groups(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[GroupMemberGet]:
    """Groups that are direct members of the project's pi group"""

    return await _direct_group_members(session, project_id, "pi_group_id", response, filter_query_params, page, page_size)


@router.post("/{project_id}/pi_groups", status_code=201, dependencies=staff_only)
async def add_pi_group_to_project(project_id: int, member: ProjectGroupMemberPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> GroupMemberGet:
    """Add a group to the project's pi group; its effective members become PIs"""

    return await membership.add_member(
        session,
        group_id=await _group_id_of(session, project_id, "pi_group_id", "pi group"),
        actor_id=_actor_id(user_token),
        member_group_id=member.group_id,
    )


@router.delete("/{project_id}/pi_groups/{member_id}", status_code=204, dependencies=staff_only)
async def remove_pi_group_from_project(project_id: int, member_id: int, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> None:
    await membership.remove_member(
        session,
        group_id=await _group_id_of(session, project_id, "pi_group_id", "pi group"),
        actor_id=_actor_id(user_token),
        member_group_id=member_id,
    )


@router.get("/{project_id}/notes", dependencies=staff_only)
async def get_project_notes(project_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[NoteGetFull]:
    """Get notes associated with a project"""

    select_stmt = select(NoteTable).join(
        UserNote, NoteTable.id == UserNote.note_id
    ).where(UserNote.project_id == project_id)
    return await list_select_stmt(session, select_stmt, NoteTable, response, filter_query_params, page, page_size)


@router.get("/{project_id}/notes/{note_id}", dependencies=staff_only)
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


@router.post("/{project_id}/notes", status_code=201, dependencies=staff_only)
async def add_note_to_project(project_id: int, note: ProjectNotePost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> NoteGetFull:
    """Add a note to a project"""

    note_row = NoteTableSchema(**{**note.model_dump(), 'author_id': user_token.user_id if user_token else None})
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

@router.put("/{project_id}/notes/{note_id}", dependencies=staff_only)
async def update_note_in_project(project_id: int, note_id: int, note: ProjectNotePost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> NoteGetFull:
    """Update a note in a project"""

    # Update the note content
    note_row = NoteTableSchema(**{**note.model_dump(), 'author_id': user_token.user_id if user_token else None})
    updated_note = await update_one_endpoint(session, NoteTable, note_id, note_row)

    # Update the user associations
    await session.execute(
        delete(UserNote)
        .where(
            UserNote.project_id == project_id,
            UserNote.note_id == note_id,
            UserNote.user_id.is_not(None)
        )
    )

    user_project_notes = [
        UserNoteTableSchema(
            project_id=project_id,
            user_id=x,
            note_id=note_id
        ) for x in note.users
    ]

    for user_note in user_project_notes:
        await create_one_endpoint(session, UserNote, user_note)

    # Flush the associations and refresh the note to load them in
    await session.flush()
    await session.refresh(updated_note)

    return updated_note


@router.delete("/{project_id}/notes/{note_id}", status_code=204, dependencies=staff_only)
async def delete_note_from_project(project_id: int, note_id: int, session=Depends(session_generator)):
    """Delete a note from a project"""

    await session.execute(
        delete(UserNote)
        .where(
            UserNote.project_id == project_id,
            UserNote.note_id == note_id
        )
    )

