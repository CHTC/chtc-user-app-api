from datetime import datetime
from typing import Optional, TYPE_CHECKING
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, model_validator, Field, EmailStr, computed_field

from userapp.core.models.enum import RoleEnum, PositionEnum, FormStatusEnum, FormTypeEnum


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def empty_strs_to_none(cls, values):
        if isinstance(values, dict):
            return {k: (None if v == '' else v) for k, v in values.items()}
        return values

class Relationship(BaseModel):
    """Used to post entities to groups by id"""
    id: int

class PiProjectView(BaseModel):
    user_id: int
    name: Optional[str] = Field(default=None)
    project_id: int
    project_name: str
    email1: Optional[EmailStr] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    netid: Optional[str] = Field(default=None)

class JoinedProjectView(BaseModel):
    id: Optional[int] = Field(default=None)
    project_id: Optional[int] = Field(default=None)
    project_name: Optional[str] = Field(default=None)
    project_staff1: Optional["UserGet"] = Field(default=None, validation_alias='staff1_user')
    project_staff2: Optional["UserGet"] = Field(default=None, validation_alias='staff2_user')
    project_status: Optional[str] = Field(default=None)
    project_last_contact: Optional[datetime] = Field(default=None)
    project_accounting_group: Optional[str] = Field(default=None)
    is_primary: Optional[bool] = Field(default=None)
    name: str
    username: Optional[str] = Field(default=None)
    email1: Optional[EmailStr] = Field(default=None)
    email2: Optional[EmailStr] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    netid_exp_datetime: Optional[datetime] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    is_admin: Optional[bool] = Field(default=None)
    active: Optional[bool] = Field(default=None)
    date: Optional[datetime] = Field(default=None)
    unix_uid: Optional[int] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)
    role: Optional[RoleEnum] = Field(default=None)
    last_note_ticket: Optional[str] = Field(default=None)

    @computed_field
    @property
    def auth_netid(self) -> Optional[bool]:
        return self.active and self.netid is not None and self.username == self.netid

    @computed_field
    @property
    def auth_username(self) -> Optional[bool]:
        return self.active and self.netid is not None and self.username is not None and self.netid != self.username

class UserApplicationView(BaseModel):
    # BaseForm fields
    id: int
    form_type: FormTypeEnum
    status: FormStatusEnum
    created_at: datetime
    updated_at: datetime

    # UserForm fields
    email: Optional[EmailStr] = Field(default=None)
    pi_id: Optional[int] = Field(default=None)
    pi_name: Optional[str] = Field(default=None)
    pi_email: Optional[EmailStr] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)
    content: Optional[dict] = Field(default=None)

class UserApplicationViewFull(UserApplicationView):
    # Relationships
    created_by: Optional["UserGet"] = Field(default=None, validation_alias='created_by_user')
    updated_by: Optional["UserGet"] = Field(default=None, validation_alias='updated_by_user')
    pi_user: Optional["UserGet"] = Field(default=None, validation_alias='pi_user')
