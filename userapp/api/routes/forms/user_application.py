from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from userapp.api.routes.security import check_is_admin, check_is_authenticated, get_user_from_cookie
from userapp.api.util import create_one_endpoint, list_endpoint, list_select_stmt, update_one_endpoint, get_one_endpoint
from userapp.core.models.enum import FormStatusEnum, FormTypeEnum
from userapp.core.models.tables import BaseForm as BaseFormTable, Project as ProjectTable, \
    SubmitNode as SubmitNodeTable, User as UserTable, UserForm as UserFormTable, UserProject, UserSubmit
from userapp.core.models.views import UserApplicationView as UserApplicationViewTable
from userapp.core.schemas.general import UserApplicationViewFull as UserApplicationViewFullSchema
from userapp.core.schemas.forms import BaseFormTableSchema
from userapp.core.schemas.user_application_form import UserFormPost, UserFormPatch, UserFormTableSchema
from userapp.core.schemas.user_project import UserProjectTableSchema
from userapp.core.schemas.user_submit import UserSubmitTableSchema
from userapp.core.schemas.users import UserGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.forms._util import on_user_form_submit, on_user_form_accept

UserApplicationViewFullSchema.model_rebuild(_types_namespace={'UserGet': UserGet})

router = APIRouter(
    prefix="/user-applications",
    responses={
        404: {
            "description": "Not found"
        }
    }
)

form_triggers = {
    (FormTypeEnum.USER, None, FormStatusEnum.PENDING): on_user_form_submit,
    (FormTypeEnum.USER, FormStatusEnum.PENDING, FormStatusEnum.APPROVED): on_user_form_accept,
    (FormTypeEnum.USER, FormStatusEnum.PENDING, FormStatusEnum.DENIED): None,
    (FormTypeEnum.USER, FormStatusEnum.DENIED, FormStatusEnum.APPROVED): on_user_form_accept,
}

@router.get("")
async def get_user_applications(
        response: Response,
        page: int = 0,
        page_size: int = 100,
        filter_query_params=Depends(get_filter_query_params),
        session=Depends(session_generator),
        _=Depends(check_is_admin),
) -> list[UserApplicationViewFullSchema]:

    if not any(value.startswith("order_by.") for _, value in filter_query_params):
        filter_query_params.append(("id", "order_by.desc"))

    return await list_endpoint(
        session=session,
        model=UserApplicationViewTable,
        response=response,
        filter_query_params=filter_query_params,
        page=page,
        page_size=page_size
    )


@router.post("", status_code=201)
async def create_user_form(
        form: UserFormPost,
        session=Depends(session_generator),
        user_token=Depends(get_user_from_cookie),
        _=Depends(check_is_authenticated)
) -> UserApplicationViewFullSchema:

    # Check if this PI exists
    if form.pi_id is not None:
        pi = await session.get(UserTable, form.pi_id)
        if pi is None:
            raise HTTPException(status_code=400, detail=f"PI with id {form.pi_id} does not exist")

    # Check if the user already has a user form in pending state
    existing_form_result = await session.execute(
        select(BaseFormTable).where(
            BaseFormTable.created_by == user_token.user_id,
            BaseFormTable.status == FormStatusEnum.PENDING,
            BaseFormTable.form_type == FormTypeEnum.USER,
        )
    )
    existing_form = existing_form_result.scalar()
    if existing_form is not None:
        raise HTTPException(status_code=422, detail=f"User already has a pending form with id {existing_form.id}")

    # Check that the user is not already active
    user = await get_one_endpoint(session, UserTable, user_token.user_id)
    if user.active:
        raise HTTPException(status_code=422, detail=f"User is already active")

    # Create the base form
    base_form_schema = BaseFormTableSchema(
        form_type=FormTypeEnum.USER,
        created_by=user_token.user_id,
        updated_by=user_token.user_id,
    )
    created_base_form: BaseFormTable = await create_one_endpoint(
        session,
        BaseFormTable,
        base_form_schema,
    )

    # Create the user form
    form_content = {
        "how_chtc_can_help": form.how_chtc_can_help,
        "computing_type": form.computing_type,
        "mentor_name": form.mentor_name,
        "mentor_email": form.mentor_email,
        "marketing_attribution": form.marketing_attribution,
        "research_computing_area": form.research_computing_area,
        "software_link": form.software_link,
        "cpu_cores": form.cpu_cores,
        "memory_gb": form.memory_gb,
        "disk_space_gb": form.disk_space_gb,
        "calculation_runtime_hours": form.calculation_runtime_hours,
        "gpu_type": form.gpu_type,
        "calculation_quantity": form.calculation_quantity,
        "special_access": form.special_access,
        "extra_info": form.extra_info,
    }
    user_form_schema = UserFormTableSchema(
        id=created_base_form.id,
        email=form.email,
        pi_id=form.pi_id,
        pi_name=form.pi_name,
        pi_email=form.pi_email,
        position=form.position,
        content=form_content
    )
    user_form = await create_one_endpoint(session, UserFormTable, user_form_schema)

    # Flush session so we can get all the fields when we send the objects back as a view
    session.flush()

    # Trigger the None->Pending transition
    trigger = form_triggers.get((FormTypeEnum.USER, None, FormStatusEnum.PENDING))
    if trigger:
        await trigger(session, created_base_form.id, user_form)

    user_application_form = await get_one_endpoint(session, UserApplicationViewTable, created_base_form.id)
    return user_application_form


@router.patch("/{form_id}", status_code=200)
async def update_form_status(
        form_id: int,
        form: UserFormPatch,
        session=Depends(session_generator),
        user_token=Depends(get_user_from_cookie),
        _=Depends(check_is_admin),
) -> UserApplicationViewFullSchema:

    original_form = await session.get(BaseFormTable, form_id)
    if original_form is None:
        raise HTTPException(status_code=404, detail="Item not found")

    original_status = original_form.status
    if original_status == FormStatusEnum.APPROVED:
        raise HTTPException(status_code=400, detail="Approved forms cannot be modified")

    transition_key = (original_form.form_type, original_status, form.status)
    if form.status != original_status and transition_key not in form_triggers:
        raise HTTPException(status_code=400, detail="Cannot process input")

    base_form: BaseFormTable = await update_one_endpoint(session, BaseFormTable, form_id, form)

    if user_token:
        # client could have authenticated through token
        base_form.updated_by = user_token.user_id
        await session.flush()

    trigger = form_triggers.get(transition_key)
    if trigger:
        await trigger(session, base_form.id, form)

    session.expire(base_form)
    user_form = await session.get(UserFormTable, form_id)
    if user_form is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return await get_one_endpoint(session, UserApplicationViewTable, base_form.id)
