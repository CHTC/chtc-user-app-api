from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from userapp.api.routes.security import check_is_admin, check_is_authenticated, get_user_from_cookie
from userapp.api.util import create_one_endpoint, list_endpoint, list_select_stmt, update_one_endpoint
from userapp.core.models.enum import FormStatusEnum, FormTypeEnum
from userapp.core.models.tables import BaseForm as BaseFormTable, User as UserTable, UserForm as UserFormTable
from userapp.core.schemas.forms import BaseFormGet, UserFormGet, UserFormPost, UserFormPatch, BaseFormTableSchema, UserFormTableSchema
from userapp.core.schemas.users import UserGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params

router = APIRouter(
    prefix="/forms",
    tags=["Forms"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


# Eagerly load created_by_user and updated_by_user to avoid async issues
_base_form_load_options = [
    selectinload(BaseFormTable.created_by_user),
    selectinload(BaseFormTable.updated_by_user),
]


async def on_user_form_accept(session: AsyncSession, form_id: int, form: UserFormPatch) -> None:
    user_form = await session.get(UserFormTable, form_id)
    if user_form is None:
        raise ValueError(f"User form with id {form_id} not found")
    
    if not (form.project_id and form.project_position and form.submit_nodes):
        raise ValueError("project_id and project_position must be provided to accept a user form")

    # set active=true


form_triggers = {
    (FormTypeEnum.USER, FormStatusEnum.PENDING, FormStatusEnum.APPROVED): on_user_form_accept,
    (FormTypeEnum.USER, FormStatusEnum.PENDING, FormStatusEnum.DENIED): None,
    (FormTypeEnum.USER, FormStatusEnum.DENIED, FormStatusEnum.APPROVED): on_user_form_accept,
}


def _serialize_user_application(base_form: BaseFormTable, user_form: UserFormTable) -> UserFormGet:
    return UserFormGet.model_construct(
        id=base_form.id,
        status=base_form.status,
        created_by=UserGet.model_validate(base_form.created_by_user) if base_form.created_by_user else None,
        created_at=base_form.created_at,
        updated_by=UserGet.model_validate(base_form.updated_by_user) if base_form.updated_by_user else None,
        updated_at=base_form.updated_at,
        pi_id=user_form.pi_id,
        pi_name=user_form.pi_name,
        pi_email=user_form.pi_email,
        position=user_form.position,
    )


async def _get_user_application(session: AsyncSession, form_id: int) -> UserFormGet:
    select_stmt = (
        select(BaseFormTable, UserFormTable)
        .join(UserFormTable, BaseFormTable.id == UserFormTable.id)
        .where(BaseFormTable.id == form_id)
        .options(*_base_form_load_options)
    )
    result = await session.execute(select_stmt)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")

    base_form, user_form = row
    return _serialize_user_application(base_form, user_form)


@router.get("")
async def get_forms(
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
    _=Depends(check_is_admin),
) -> list[BaseFormGet]:
    return await list_endpoint(
        session,
        BaseFormTable,
        response,
        filter_query_params,
        page,
        page_size,
        load_options=_base_form_load_options,
    )


@router.get("/user-applications")
async def get_user_applications(
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
    _=Depends(check_is_admin),
) -> list[UserFormGet]:
    return await list_select_stmt(
        session=session,
        select_stmt=(
            select(BaseFormTable, UserFormTable)
            .join(UserFormTable, BaseFormTable.id == UserFormTable.id)
            .where(BaseFormTable.form_type == FormTypeEnum.USER)
        ),
        model=BaseFormTable,
        response=response,
        filter_query_params=filter_query_params,
        page=page,
        page_size=page_size,
        load_options=_base_form_load_options,
        row_mapper=lambda row: _serialize_user_application(row[0], row[1]),
    )


@router.post("/user-applications", status_code=201)
async def create_user_form(
    form: UserFormPost,
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
    _=Depends(check_is_authenticated)
) -> UserFormGet:
    if form.pi_id is not None:
        pi = await session.get(UserTable, form.pi_id)
        if pi is None:
            raise HTTPException(status_code=400, detail=f"PI with id {form.pi_id} does not exist")

    base_form_schema = BaseFormTableSchema(
        form_type=FormTypeEnum.USER,
        created_by=user_token.user_id,
        updated_by=user_token.user_id,
    )
    
    created_base_form: BaseFormTable = await create_one_endpoint(
        session,
        BaseFormTable,
        base_form_schema,
        load_options=_base_form_load_options,
    )

    user_form_schema = UserFormTableSchema(
        id=created_base_form.id,
        pi_id=form.pi_id,
        pi_name=form.pi_name,
        pi_email=form.pi_email,
        position=form.position,
    )
    created_user_form: UserFormTable = await create_one_endpoint(session, UserFormTable, user_form_schema)

    return _serialize_user_application(created_base_form, created_user_form)


@router.patch("/user-applications/{form_id}", status_code=200)
async def update_form_status(
    form_id: int,
    form: UserFormPatch,
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
    _=Depends(check_is_admin),
) -> UserFormGet:
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
        # TODO: consider adding user_id of token creator to a token?
        base_form.updated_by = user_token.user_id
        await session.flush()

    trigger = form_triggers.get(transition_key)
    if trigger:
        trigger(session, base_form.id, form)

    session.expire(base_form)
    return await _get_user_application(session, form_id)
