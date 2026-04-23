from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.api.util import create_one_endpoint, format_escaped_template, send_email
from userapp.core.models.enum import RoleEnum
from userapp.core.models.tables import UserForm as UserFormTable, UserGroup, UserProject
from userapp.core.schemas.user_application_form import UserFormPatch
from userapp.core.schemas.user_project import UserProjectTableSchema
from userapp.api.routes._util import _patch_user_submit_nodes

CHTC_NO_REPLY_EMAIL = "no-reply@chtc.wisc.edu"
CHTC_TICKETING_EMAIL = "chtc@cs.wisc.edu"

ON_USER_FORM_SUBMIT_EMAIL_TEMPLATE = """
Dear {name},

Thank you for requesting an account at CHTC! The CHTC Facilitation Staff will reach out to you within 2-3 business days. Contact us at chtc@cs.wisc.edu if you don't hear back from us after 3 business days.

Best,
The CHTC Research Computing Facilitation team
""".strip()

ON_USER_FORM_APPROVAL_EMAIL_TEMPLATE = """
Dear {name},

This is an automated message to inform you that your CHTC account has been approved.

A facilitator will follow up with instructions on how to get started within 1-2 business days.
If you do not receive the instructions, please send a new email to chtc@cs.wisc.edu. 

Best,
The CHTC Research Computing Facilitation team
""".strip()

async def on_user_form_submit(session: AsyncSession, form_id: int, user_form: UserFormTable) -> None:

    # Get an email for the application submission
    user = user_form.base_form.created_by_user
    email = user.email1 or user_form.email
    if email is None:
        raise HTTPException(status_code=400, detail="User form must have an email address if user account does not.")

    # Try sending the user an email
    try:
        text = format_escaped_template(
            ON_USER_FORM_SUBMIT_EMAIL_TEMPLATE,
            name=user.name or "user",
        )
        send_email(CHTC_NO_REPLY_EMAIL, email, "CHTC Account Request", text, CHTC_TICKETING_EMAIL, reply_to=CHTC_TICKETING_EMAIL)
    except Exception:
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

    # Set the users email if not already set
    if user.email1 is None:
        if form.email is None:
            raise HTTPException(status_code=400, detail="User has no email address and no email provided in form patch")
        user.email1 = form.email

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
    
    # Try sending the user an email
    try:
        text = format_escaped_template(
            ON_USER_FORM_APPROVAL_EMAIL_TEMPLATE,
            name=user.name or "user",
        )
        send_email(CHTC_NO_REPLY_EMAIL, user.email1, "CHTC Account Approved", text, reply_to=CHTC_TICKETING_EMAIL)
    except Exception as e:
        print(e)
        # we don't care if the email send fails
        pass


async def _clear_user_projects(session: AsyncSession, user) -> None:
    await session.execute(
        UserProject.__table__.delete().where(UserProject.user_id == user.id)
    )


async def _clear_user_groups(session: AsyncSession, user) -> None:
    await session.execute(
        UserGroup.__table__.delete().where(UserGroup.user_id == user.id)
    )
