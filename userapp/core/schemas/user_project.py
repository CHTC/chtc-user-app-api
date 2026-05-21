from datetime import datetime
from typing import Optional

from pydantic import field_serializer, ConfigDict, Field

from userapp.core.models.enum import RoleEnum, EntityManagerEnum
from userapp.core.schemas.general import BaseModel

class UserProjectTableSchema(BaseModel):
    """Used to represent a user-project association as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id:  Optional[int] = Field(default=None)
    project_id: int
    user_id: int
    role: Optional[RoleEnum] = Field(default=None)
    is_primary: bool
    managed_by: Optional[EntityManagerEnum] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)

    @field_serializer('role')
    def serialize_role(self, role: RoleEnum) -> str:
        return role.name if role is not None else None

    @field_serializer('managed_by')
    def serialize_managed_by(self, managed_by: EntityManagerEnum) -> str:
        return managed_by.name if managed_by is not None else None

class UserProjectGet(UserProjectTableSchema):
    """Exact same as UserProjectTableSchema for now, but kept separate for future changes"""
    pass

class UserProjectPatch(BaseModel):

    role: Optional[RoleEnum] = None
    is_primary: Optional[bool] = None
    managed_by: Optional[EntityManagerEnum] = None

    @field_serializer('role')
    def serialize_role(self, role: RoleEnum) -> str:
        return role.name if role is not None else None

    @field_serializer('managed_by')
    def serialize_managed_by(self, managed_by: EntityManagerEnum) -> str:
        return managed_by.name if managed_by is not None else None


class UserProjectPost(BaseModel):
    user_id: int
    role: Optional[RoleEnum] = None
    is_primary: bool = False
    managed_by: Optional[EntityManagerEnum] = None

    @field_serializer('role')
    def serialize_role(self, role: RoleEnum) -> str:
        return role.name if role is not None else None

    @field_serializer('managed_by')
    def serialize_managed_by(self, managed_by: EntityManagerEnum) -> str:
        return managed_by.name if managed_by is not None else None


class ManagedUserProjectPut(BaseModel):
    """Used by a managed endpoint which has a url explicit managed_by"""

    user_id: int
    role: Optional[RoleEnum] = None
    is_primary: bool = False
