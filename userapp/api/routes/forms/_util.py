from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.api.util import create_one_endpoint, format_escaped_template, send_email
from userapp.core.models.enum import RoleEnum
from userapp.core.models.tables import UserForm as UserFormTable, UserGroup, UserProject
from userapp.core.schemas.user_application_form import UserFormPatch
from userapp.core.schemas.user_project import UserProjectTableSchema
from userapp.api.routes._util import _patch_user_submit_nodes

ON_USER_FORM_SUBMIT_EMAIL_TEMPLATE = """
Dear {name},

Thank you for requesting an account at CHTC! The CHTC Facilitation Staff will reach out to you within 2-3 business days. Contact us at chtc@cs.wisc.edu if you don't hear back from us after 3 business days.

Best,
The CHTC Research Computing Facilitation team
""".strip()

ON_USER_FORM_APPROVAL_EMAIL_TEMPLATE = """
Dear {name},

Thanks for getting in touch with the Center for High Throughput Computing (CHTC)! Based on your application form, we have created your account on our High Throughput Computing (HTC) system and on our High Performance Computing (HPC) system. It will be ready to use within the next couple hours. To log in, use your campus NetID and password to SSH into the login servers.

For HTC:
• Use ap2001.chtc.wisc.edu

For HPC:
• Use spark-login.chtc.wisc.edu

You will need to be on the campus internet or VPN to access the servers.

For information on how to get started, visit the following pages of our website:
• How to log in: https://chtc.cs.wisc.edu/uw-research-computing/connecting
• How to prepare and submit HTC jobs: https://chtc.cs.wisc.edu/uw-research-computing/htcondor-job-submission
• How to prepare and submit HPC jobs: https://chtc.cs.wisc.edu/uw-research-computing/hpc-job-submission

We have many guides on our website to help you with a variety of topics, including how to set up your software, organize job submissions, and handle large data: https://chtc.cs.wisc.edu/uw-research-computing/htc/guides.html and https://chtc.cs.wisc.edu/uw-research-computing/hpc/guides.html

CHTC’s mission is to accelerate research by providing access to computing and data capacity and to provide personalized support to individual researchers. After reviewing the materials above, please schedule an initial consultation with us to answer any questions you may have about getting started by using this link: go.wisc.edu/schedule-chtc. This could be right away, if you’re not sure where to start, or after a few weeks of experimentation. It’s up to you!

You can also reach out for support by emailing chtc@cs.wisc.edu or stopping by our Zoom office hours on Tuesdays 10:30 AM - 12:00 PM and Thursdays 3:00 PM - 4:30 PM, online at go.wisc.edu/chtc-officehours. Active system issues are reported via our status page at https://status.chtc.wisc.edu.

Please don’t hesitate to reach out with any questions you have about getting started!

Best,
The CHTC Research Computing Facilitation team
""".strip()

async def on_user_form_submit(session: AsyncSession, form_id: int, form: None) -> None:
    user_form = await session.scalar(
        select(UserFormTable)
        .where(UserFormTable.id == form_id)
    )
    user = user_form.base_form.created_by_user

    # Try sending the user an email
    try:
        text = format_escaped_template(
            ON_USER_FORM_SUBMIT_EMAIL_TEMPLATE,
            name=user.name or "user",
        )
        send_email("chtc@cs.wisc.edu", user.email1, "CHTC Account Application Received", text)
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
        send_email("chtc@cs.wisc.edu", user.email1, "CHTC Account Application Approved", text)
    except Exception:
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
