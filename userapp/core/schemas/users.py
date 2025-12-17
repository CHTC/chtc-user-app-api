from pydantic import EmailStr, AfterValidator, field_serializer, model_validator, ConfigDict, Field
from typing import Optional, Annotated
from datetime import datetime
import re

from userapp.core.schemas.general import JoinedProjectView
from userapp.core.schemas.note import NoteGet
from userapp.core.schemas.user_submit import UserSubmitGet, UserSubmitPost
from userapp.core.schemas.general import BaseModel
from userapp.core.models.enum import RoleEnum, PositionEnum


def user_password_validator(password: str) -> str | None:
    if password is None:
        return password
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long.")
    if not re.search(r'[A-Z]', password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r'[a-z]', password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r'[0-9]', password):
        raise ValueError("Password must contain at least one digit.")
    return password


def user_name_validator(username: str) -> str:
    if not re.fullmatch(r'[^:,]*', username):
        raise ValueError("Username cannot contain the characters ':' or ','.")
    return username

class UserTableSchema(BaseModel):
    """Used to represent a user as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    name: str
    email1: EmailStr
    email2: Optional[EmailStr] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    netid_exp_datetime: Optional[datetime] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    is_admin: Optional[bool] = Field(default=None)
    auth_netid: Optional[bool] = Field(default=None)
    auth_username: Optional[bool] = Field(default=None)
    date: Optional[datetime] = Field(default=None)
    unix_uid: Optional[int] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None


class UserGet(BaseModel):

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    username: Optional[str] = Field(default=None)
    name: str
    email1: EmailStr
    email2: Optional[EmailStr] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    netid_exp_datetime: Optional[datetime] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    is_admin: Optional[bool] = Field(default=None)
    auth_netid: Optional[bool] = Field(default=None)
    auth_username: Optional[bool] = Field(default=None)
    date: Optional[datetime] = Field(default=None)
    unix_uid: Optional[int] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

class UserGetFull(UserGet):

    notes: list["NoteGet"] = Field(default=[])
    submit_nodes: list["UserSubmitGet"] = Field(default=[])
    projects: list["JoinedProjectView"] = Field(default=[])

class UserPost(BaseModel):

    model_config = ConfigDict(extra='ignore')

    username: Annotated[Optional[str], AfterValidator(user_name_validator)] = Field(default=None)
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = Field(default=None)
    name: str
    email1: EmailStr
    email2: Optional[EmailStr] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    netid_exp_datetime: Optional[datetime] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    is_admin: Optional[bool] = Field(default=None)
    auth_netid: Optional[bool] = Field(default=None)
    auth_username: Optional[bool] = Field(default=None)
    unix_uid: Optional[int] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

    @model_validator(mode="after")
    def check_auth_username_requires_username_and_password(self):
        if self.auth_username and not (self.username and self.password):
            raise ValueError("If auth_username is True, both username and password must be provided.")
        return self

    @model_validator(mode="after")
    def check_auth_netid_requires_netid(self):
        if self.auth_netid and not self.netid:
            raise ValueError("If auth_netid is True, netid must be provided.")
        return self


class UserPostFull(UserPost):

    primary_project_id: int
    primary_project_role: RoleEnum
    submit_nodes: Optional[list["UserSubmitPost"]] = Field(default=[])


class UserPatch(BaseModel):

    model_config = ConfigDict(extra='ignore')

    username: Optional[str] = Field(default=None)
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = Field(default=None)
    name: Annotated[Optional[str], AfterValidator(user_name_validator)] = Field(default=None)
    email1: Optional[EmailStr] = Field(default=None)
    email2: Optional[EmailStr] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    netid_exp_datetime: Optional[datetime] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    is_admin: Optional[bool] = Field(default=None)
    auth_netid: Optional[bool] = Field(default=None)
    auth_username: Optional[bool] = Field(default=None)
    unix_uid: Optional[int] = Field(default=None)
    position: Optional[PositionEnum] = Field(default=None)

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

class UserPatchFull(UserPatch):

    submit_nodes: Optional[list[UserSubmitPost]] = Field(default=[])

class RestrictedUserPatch(BaseModel):
    """Used to allow a user to self update limited information"""

    model_config = ConfigDict(extra='ignore')

    name: Optional[str] = Field(default=None)
    email1: Optional[EmailStr] = Field(default=None)
    email2: Optional[EmailStr] = Field(default=None)
    phone1: Optional[str] = Field(default=None)
    phone2: Optional[str] = Field(default=None)
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = Field(default=None)
