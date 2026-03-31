from datetime import datetime
from typing import Optional

from pydantic import Field

from userapp.core.models.enum import FormStatusEnum, FormTypeEnum
from userapp.core.schemas.general import BaseModel


class BaseFormTableSchema(BaseModel):
    """Schema for the database representation of a BaseForm."""
    id: int
    form_type: FormTypeEnum
    name: str
    description: Optional[str] = Field(default=None)
    created_by: Optional[int] = Field(default=None)


class UserFormTableSchema(BaseModel):
    """Schema for the database representation of a UserForm."""
    id: int
    netid: str


class UserFormGet(BaseModel):
    id: int
    name: str
    description: Optional[str] = Field(default=None)
    status: FormStatusEnum
    created_by: Optional[int] = Field(default=None)
    created_at: datetime
    updated_at: datetime
    netid: str


class UserFormPost(BaseModel):
    name: str
    description: Optional[str] = Field(default=None)
    netid: str


class UserFormPut(BaseModel):
    status: FormStatusEnum
