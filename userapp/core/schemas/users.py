from pydantic import EmailStr, AfterValidator, field_serializer
from typing import Optional, Annotated
from datetime import datetime
import re

from userapp.core.schemas.user_submit import UserSubmit, UserSubmitCreate, UserSubmitGetSlim, UserSubmitUpdate
from userapp.core.schemas.general import BaseModel
from userapp.core.models.enum import RoleEnum, PositionEnum


def user_password_validator(password: str) -> str:
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


class UserBase(BaseModel):
    username: Optional[str] = None
    name: Annotated[Optional[str], AfterValidator(user_name_validator)] = None
    email1: Optional[EmailStr] = None
    email2: Optional[EmailStr] = None
    netid: Optional[str] = None
    netid_exp_datetime: Optional[datetime] = None
    phone1: Optional[str] = None
    phone2: Optional[str] = None
    is_admin: Optional[bool] = None
    auth_netid: Optional[bool] = False
    auth_username: Optional[bool] = False
    date: Optional[datetime] = None
    unix_uid: Optional[int] = None
    position: Optional[PositionEnum] = None

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

class UserCreateSimple(UserBase):
    """Used to represent a simple user creation with only email and password"""
    email1: EmailStr
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = None

class UserCreateFull(UserCreateSimple):
    """Used when creating a new user along with their primary project and submit nodes"""
    primary_project_id: int
    primary_project_role: RoleEnum
    submit_nodes: Optional[list[UserSubmitCreate]] = []

class UserUpdate(UserBase):
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = None

class UserUpdateFull(UserUpdate):
    submit_nodes: Optional[list[UserSubmitUpdate]] = []

class User(UserBase):
    id: int
    submit_nodes: Optional[list[UserSubmitGetSlim]] = []