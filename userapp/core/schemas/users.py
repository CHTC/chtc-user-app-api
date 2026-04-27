from pydantic import EmailStr, AfterValidator, field_serializer, model_validator, ConfigDict, Field, computed_field
from typing import Optional, Annotated
from datetime import datetime
import re

from userapp.core.schemas.general import JoinedProjectView, UserApplicationView as UserApplicationViewSchema
from userapp.core.schemas.note import NoteGet
from userapp.core.schemas.user_submit import UserSubmitGet, UserSubmitPost
from userapp.core.schemas.general import BaseModel
from userapp.core.schemas.groups import GroupGet
from userapp.core.models.enum import RoleEnum, PositionEnum


class UserTableSchema(BaseModel):
    """Used to represent a user as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    name: str
    username: str
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

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str | None:
        return position.name if position is not None else None


class UserGet(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    name: str
    username: str
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

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

    @computed_field
    @property
    def auth_netid(self) -> Optional[bool]:
        return self.active and self.netid == self.username

    @computed_field
    @property
    def auth_username(self) -> Optional[bool]:
        return self.active and self.netid != self.username

class UserGetFull(UserGet):

    notes: list["NoteGet"] = Field(default=[])
    submit_nodes: list["UserSubmitGet"] = Field(default=[])
    projects: list["JoinedProjectView"] = Field(default=[])
    groups: list["GroupGet"] = Field(default=[])
    user_forms: list["UserApplicationViewSchema"] = Field(default=[])

class UserPost(BaseModel):

    model_config = ConfigDict(extra='ignore')

    name: str
    username: str
    email1: Optional[EmailStr] = Field(default=None)
    email2: Optional[EmailStr] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    netid_exp_datetime: Optional[datetime] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    is_admin: Optional[bool] = Field(default=None)
    active: Optional[bool] = Field(default=None)
    unix_uid: Optional[int] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

    @model_validator(mode="after")
    def check_active_requires_netid(self):
        if self.active and not self.netid:
            raise ValueError("If active is True, netid must be provided.")
        if self.active and not self.username:
            raise ValueError("If active is True, username must be provided.")
        return self


class UserPostFull(UserPost):

    primary_project_id: int
    primary_project_role: RoleEnum
    submit_nodes: Optional[list["UserSubmitPost"]] = Field(default=[])


class UserPatch(BaseModel):

    model_config = ConfigDict(extra='ignore')

    name: Optional[str] = Field(default=None)
    email1: Optional[EmailStr] = Field(default=None)
    email2: Optional[EmailStr] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    netid_exp_datetime: Optional[datetime] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    is_admin: Optional[bool] = Field(default=None)
    active: Optional[bool] = Field(default=None)
    unix_uid: Optional[int] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

    @model_validator(mode="after")
    def check_active_requires_identity(self):
        if self.active:
            if 'netid' in self.model_fields_set and not self.netid:
                raise ValueError("If active is True, netid must be provided.")
            if 'username' in self.model_fields_set and not self.username:
                raise ValueError("If active is True, username must be provided.")
        return self

class UserPatchFull(UserPatch):

    submit_nodes: Optional[list[UserSubmitPost]] = Field(default=None)

class RestrictedUserPatch(BaseModel):
    """Used to allow a user to self update limited information"""

    model_config = ConfigDict(extra='ignore')

    name: Optional[str] = Field(default=None)
    email2: Optional[EmailStr] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
