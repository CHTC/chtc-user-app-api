from datetime import datetime
from typing import Optional

from pydantic import Field

from userapp.core.models.enum import FormStatusEnum, FormTypeEnum
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
    created_by: Optional[UserGet] = Field(default=None, validation_alias='created_by_user')
    created_at: datetime
    updated_by: Optional[UserGet] = Field(default=None, validation_alias='updated_by_user')
    updated_at: datetime
