from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from userapp.api.routes.security import check_is_admin, check_is_authenticated, get_user_from_cookie
from userapp.api.util import create_one_endpoint, update_one_endpoint
from userapp.core.models.enum import FormTypeEnum
from userapp.core.models.tables import BaseForm as BaseFormTable, UserForm as UserFormTable
from userapp.core.schemas.forms import UserFormGet, UserFormPost, UserFormPut, BaseFormTableSchema, UserFormTableSchema
from userapp.core.schemas.users import UserGet
from userapp.db import session_generator

router = APIRouter(
    prefix="/forms",
    tags=["Forms"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


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

    await session.refresh(created_base_form, attribute_names=['created_by_user', 'updated_by_user'])
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


@router.put("/users/{form_id}", status_code=200)
async def update_user_form_status(
    form_id: int,
    form: UserFormPut,
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
    _=Depends(check_is_admin),
) -> UserFormGet:
    base_form: BaseFormTable = await update_one_endpoint(session, BaseFormTable, form_id, form)

    user_form = await session.scalar(select(UserFormTable).where(UserFormTable.id == form_id))
    if user_form is None:
        raise HTTPException(status_code=404, detail="User form not found")

    if user_token:
        # admin could be token
        base_form.updated_by = user_token.user_id
        await session.flush()

    await session.refresh(base_form)
    created_by = UserGet.model_validate(base_form.created_by_user)
    updated_by = UserGet.model_validate(base_form.updated_by_user)

    return UserFormGet.model_construct(
        id=user_form.id,
        status=base_form.status,
        created_by=created_by,
        created_at=base_form.created_at,
        updated_by=updated_by,
        updated_at=base_form.updated_at,
        netid=user_form.netid,
    )
