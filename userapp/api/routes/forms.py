from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from userapp.api.routes.security import check_is_admin, get_current_user, get_user_from_cookie
from userapp.api.util import create_one_endpoint, update_one_endpoint
from userapp.core.models.enum import FormTypeEnum
from userapp.core.models.tables import BaseForm as BaseFormTable, UserForm as UserFormTable
from userapp.core.schemas.forms import UserFormGet, UserFormPost, UserFormPut, BaseFormTableSchema, UserFormTableSchema
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
) -> UserFormGet:
    base_form_schema = BaseFormTableSchema(
        form_type=FormTypeEnum.USER,
        created_by=user_token.user_id,
        updated_by=user_token.user_id,
    )
    created_base_form = cast(BaseFormTableSchema, await create_one_endpoint(session, BaseFormTable, base_form_schema))

    user_form_schema = UserFormTableSchema(id=created_base_form.id, netid=form.netid)
    created_user_form = cast(UserFormTableSchema, await create_one_endpoint(session, UserFormTable, user_form_schema))

    return UserFormGet(
        id=created_base_form.id,
        status=created_base_form.status,
        created_by=created_base_form.created_by,
        created_at=created_base_form.created_at,
        updated_by=created_base_form.updated_by,
        updated_at=created_base_form.updated_at,
        netid=created_user_form.netid,
    )


@router.put("/users/{form_id}", status_code=200)
async def update_user_form_status(
    form_id: int,
    form: UserFormPut,
    session=Depends(session_generator),
    _=Depends(check_is_admin),
) -> UserFormGet:
    updated_base_form = await update_one_endpoint(session, BaseFormTable, form_id, form)

    user_form = await session.scalar(select(UserFormTable).where(UserFormTable.id == form_id))
    if user_form is None:
        raise HTTPException(status_code=404, detail="User form not found")

    return UserFormGet(
        id=updated_base_form.id,
        status=updated_base_form.status,
        created_by=updated_base_form.created_by,
        created_at=updated_base_form.created_at,
        updated_by=updated_base_form.updated_by,
        updated_at=updated_base_form.updated_at,
        netid=user_form.netid,
    )
