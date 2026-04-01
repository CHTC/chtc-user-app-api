from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from userapp.api.routes.security import check_is_admin, check_is_authenticated, get_user_from_cookie
from userapp.api.util import create_one_endpoint, update_one_endpoint
from userapp.core.models.enum import FormStatusEnum, FormTypeEnum
from userapp.core.models.tables import BaseForm as BaseFormTable, UserForm as UserFormTable
from userapp.core.schemas.forms import BaseFormGet, UserFormGet, UserFormPost, BaseFormPatch, BaseFormTableSchema, UserFormTableSchema
from userapp.core.schemas.users import UserGet
from userapp.db import get_async_session, session_generator

router = APIRouter(
    prefix="/forms",
    tags=["Forms"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


async def on_user_form_accept(form_id: int, session_maker: async_sessionmaker[AsyncSession]) -> None:
    async with session_maker() as session:
        async with session.begin():
            user_form = await session.get(UserFormTable, form_id)
            if user_form is None:
                raise ValueError(f"User form with id {form_id} not found")

            # todo: actual logic


form_triggers = {
    FormTypeEnum.USER: on_user_form_accept,
}


@router.post("/users", status_code=201)
async def create_user_form(
    form: UserFormPost,
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
    _=Depends(check_is_authenticated)
) -> UserFormGet:
    base_form_schema = BaseFormTableSchema(
        form_type=FormTypeEnum.USER,
        created_by=user_token.user_id,
        updated_by=user_token.user_id,
    )
    created_base_form: BaseFormTable = await create_one_endpoint(session, BaseFormTable, base_form_schema)

    user_form_schema = UserFormTableSchema(id=created_base_form.id, netid=form.netid)
    created_user_form: UserFormTable = await create_one_endpoint(session, UserFormTable, user_form_schema)

    # get the user objects for the created_by and updated_by fields
    await session.refresh(created_base_form)
    user = UserGet.model_validate(created_base_form.created_by_user)

    return UserFormGet.model_construct(
        id=created_base_form.id,
        status=created_base_form.status,
        created_by=user,
        created_at=created_base_form.created_at,
        updated_by=user,
        updated_at=created_base_form.updated_at,
        netid=created_user_form.netid,
    )


@router.patch("/{form_id}", status_code=200)
async def update_form_status(
    request: Request,
    form_id: int,
    form: BaseFormPatch,
    background_tasks: BackgroundTasks,
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
    _=Depends(check_is_admin),
) -> BaseFormGet:
    original_form = await session.get(BaseFormTable, form_id)
    if original_form is None:
        raise HTTPException(status_code=404, detail="Item not found")
    
    original_status = original_form.status
    if original_status == FormStatusEnum.APPROVED:
        raise HTTPException(status_code=400, detail="Approved forms cannot be modified")

    base_form: BaseFormTable = await update_one_endpoint(session, BaseFormTable, form_id, form)

    if original_status != FormStatusEnum.APPROVED and base_form.status == FormStatusEnum.APPROVED:
        # trigger background task
        trigger = form_triggers.get(base_form.form_type)
        if trigger:
            background_tasks.add_task(trigger, form_id=base_form.id, session_maker=get_async_session(request))

    if user_token:
        # client could have authenticated through token
        # todo: consider adding user_id of token creator to a token?
        base_form.updated_by = user_token.user_id
        await session.flush()

    # refresh to get returned fields and relationships populated
    await session.refresh(
        base_form,
        attribute_names=['form_type', 'status', 'created_at', 'updated_at', 'created_by_user', 'updated_by_user'],
    )
    created_by = UserGet.model_validate(base_form.created_by_user)
    updated_by = UserGet.model_validate(base_form.updated_by_user)

    return BaseFormGet.model_construct(
        id=base_form.id,
        status=base_form.status,
        created_by=created_by,
        created_at=base_form.created_at,
        updated_by=updated_by,
        updated_at=base_form.updated_at,
    )
