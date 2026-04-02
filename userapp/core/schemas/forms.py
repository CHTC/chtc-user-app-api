from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from userapp.core.models.enum import FormStatusEnum, FormTypeEnum, PositionEnum
from userapp.core.schemas.general import BaseModel
from userapp.core.schemas.users import UserGet


class BaseFormTableSchema(BaseModel):
    """Schema for the database representation of a BaseForm."""
    id: Optional[int] = Field(default=None)
    form_type: FormTypeEnum
    created_by: int
    updated_by: int


class BaseFormGet(BaseModel):
    id: int
    status: FormStatusEnum
    created_by: UserGet = Field(validation_alias='created_by_user')
    created_at: datetime
    updated_by: UserGet = Field(validation_alias='updated_by_user')
    updated_at: datetime


class BaseFormPatch(BaseModel):
    status: FormStatusEnum


class UserFormTableSchema(BaseModel):
    """Schema for the database representation of a UserForm."""
    id: int
    pi_id: Optional[int] = Field(default=None)
    pi_name: Optional[str] = Field(default=None)
    pi_email: Optional[str] = Field(default=None)
    position: PositionEnum


class UserFormGet(BaseFormGet):
    pi_id: Optional[int] = Field(default=None)
    pi_name: Optional[str] = Field(default=None)
    pi_email: Optional[str] = Field(default=None)
    position: PositionEnum


class UserFormPost(BaseModel):
    pi_id: Optional[int] = Field(default=None)
    pi_name: Optional[str] = Field(default=None)
    pi_email: Optional[str] = Field(default=None)
    position: PositionEnum

    @model_validator(mode="after")
    def validate_pi_fields(self):
        has_pi_id = self.pi_id is not None
        has_pi_name = self.pi_name is not None
        has_pi_email = self.pi_email is not None

        if has_pi_id == (has_pi_name or has_pi_email):
            raise ValueError("Provide either pi_id or both pi_name and pi_email")

        if has_pi_name != has_pi_email:
            raise ValueError("pi_name and pi_email must be provided together")

        return self
