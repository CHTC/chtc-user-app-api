from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.api.util import create_one_endpoint, send_email
from userapp.core.models.enum import RoleEnum
from userapp.core.models.tables import UserForm as UserFormTable, UserGroup, UserProject
from userapp.core.schemas.user_application_form import UserFormPatch
from userapp.core.schemas.user_project import UserProjectTableSchema
from userapp.api.routes._util import _patch_user_submit_nodes

async def on_user_form_submit(session: AsyncSession, form_id: int, form: UserFormPatch) -> None:
    user_form = await session.scalar(
        select(UserFormTable)
        .where(UserFormTable.id == form_id)
    )
    user = user_form.base_form.created_by_user

    # Try sending the user an email
    try:
        send_email("chtc@cs.wisc.edu", user.email1, "CHTC Account Application Received", "Thank you for requesting an account at CHTC! The CHTC Facilitation Staff will reach out to you within 2-3 business days. Contact us at chtc@cs.wisc.edu if you don't hear back from us after 3 business days.")
    except:
        # we don't care if the email send fails
        pass

async def on_user_form_accept(session: AsyncSession, form_id: int, form: UserFormPatch) -> None:
    user_form = await session.scalar(
        select(UserFormTable)
        .where(UserFormTable.id == form_id)
    )
    if user_form is None:
        raise HTTPException(status_code=404, detail=f"User form with id {form_id} not found")

    if user_form.base_form.created_by is None:
        raise HTTPException(status_code=400, detail=f"User form {form_id} has no associated user")

    user = user_form.base_form.created_by_user
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_form.base_form.created_by} not found")

    user.active = True

    # If we are not preserving the users data dump all of their groups
    if not form.preserve_existing_data:

        user.position = form.user_position

        if not (form.project_id and form.user_position and form.submit_nodes):
            raise HTTPException(
                status_code=400,
                detail="project_id, user_position, and submit_nodes must be provided to accept a user form",
            )

        # Clear out projects, and groups
        await _clear_user_projects(session, user)
        await _clear_user_groups(session, user)
        # Add in the approved project
        await create_one_endpoint(
            session,
            UserProject,
            UserProjectTableSchema(
                user_id=user.id,
                project_id=form.project_id,
                role=RoleEnum.MEMBER,
                is_primary=True,
            ),
        )
        # Update to the set of approved submit nodes
        await _patch_user_submit_nodes(session, user, form.submit_nodes)


async def _clear_user_projects(session: AsyncSession, user) -> None:
    await session.execute(
        UserProject.__table__.delete().where(UserProject.user_id == user.id)
    )


async def _clear_user_groups(session: AsyncSession, user) -> None:
    await session.execute(
        UserGroup.__table__.delete().where(UserGroup.user_id == user.id)
    )
