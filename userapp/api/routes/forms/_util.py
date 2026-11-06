from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.api.util import create_one_endpoint, format_escaped_template, send_email
from userapp.core.models.tables import UserForm as UserFormTable, GroupMember, Project
from userapp.core.schemas.user_application_form import UserFormPatch
from userapp.core.services import membership
from userapp.api.routes._util import _patch_user_submit_nodes, set_primary_project

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

async def on_user_form_accept(session: AsyncSession, form_id: int, form: UserFormPatch, actor_id: int | None = None) -> None:
    """actor_id is the staff member approving the form (None for an API token)"""

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

        # Clear out the user's direct group memberships (project and submit node groups alike)
        await _clear_user_memberships(session, user, actor_id)
        # Add in the approved project: membership of its project group, and it becomes primary
        project = await session.get(Project, form.project_id)
        if project is None or project.project_group_id is None:
            raise HTTPException(status_code=400, detail=f"Project {form.project_id} not found or has no project group")
        await membership.add_member(session, group_id=project.project_group_id, actor_id=actor_id, user_id=user.id)
        await set_primary_project(session, user, project.id, actor_id)
        # Grant access to the approved submit nodes via their associated groups
        await _patch_user_submit_nodes(session, user, form.submit_nodes, actor_id=actor_id)

    user.active = True
    await session.flush()

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


async def _clear_user_memberships(session: AsyncSession, user, actor_id: int | None) -> None:
    group_ids = (await session.execute(
        select(GroupMember.group_id).where(GroupMember.member_user_id == user.id)
    )).scalars().all()
    for group_id in group_ids:
        await membership.remove_member(session, group_id=group_id, actor_id=actor_id, user_id=user.id)
