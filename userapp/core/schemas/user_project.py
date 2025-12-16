from typing import Optional

from pydantic import field_serializer, ConfigDict, Field

from userapp.core.models.enum import RoleEnum
from userapp.core.schemas.general import BaseModel

class UserProjectTableSchema(BaseModel):
    """Used to represent a user-project association as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id:  Optional[int] = Field(default=None)
    project_id: int
    user_id: int
    role: Optional[RoleEnum] = Field(default=None)
    is_primary: bool

    @field_serializer('role')
    def serialize_role(self, role: RoleEnum) -> str:
        return role.name if role is not None else None

class UserProjectGet(UserProjectTableSchema):
    """Exact same as UserProjectTableSchema for now, but kept separate for future changes"""
    pass

class UserProjectPatch(BaseModel):

    role: Optional[RoleEnum] = None
    is_primary: Optional[bool] = None

    @field_serializer('role')
    def serialize_role(self, role: RoleEnum) -> str:
        return role.name if role is not None else None

class UserProjectPost(BaseModel):
    user_id: int
    role: Optional[RoleEnum] = None
    is_primary: bool = False

    @field_serializer('role')
    def serialize_role(self, role: RoleEnum) -> str:
        return role.name if role is not None else None
