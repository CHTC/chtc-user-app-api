from datetime import datetime
from typing import Optional
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, model_validator, Field, EmailStr, computed_field

from userapp.core.models.enum import RoleEnum, PositionEnum


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

class Login(BaseModel):
    username: str
    password: str

class PiProjectView(BaseModel):
    user_id: int
    username: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    project_id: int
    project_name: str
    email1: Optional[str] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    netid: Optional[str] = Field(default=None)

class JoinedProjectView(BaseModel):
    id: Optional[int] = Field(default=None)
    project_id: Optional[int] = Field(default=None)
    project_name: Optional[str] = Field(default=None)
    project_staff1: Optional[str] = Field(default=None)
    project_staff2: Optional[str] = Field(default=None)
    project_status: Optional[str] = Field(default=None)
    project_last_contact: Optional[datetime] = Field(default=None)
    project_accounting_group: Optional[str] = Field(default=None)
    is_primary: Optional[bool] = Field(default=None)
    username: Optional[str] = Field(default=None)
    name: str
    email1: EmailStr
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
        """Backwards compatibility: maps to active field"""
        return self.active

    @computed_field
    @property
    def auth_username(self) -> bool:
        """Backwards compatibility: always returns False"""
        return False