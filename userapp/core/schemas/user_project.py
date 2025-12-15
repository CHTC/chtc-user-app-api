from typing import Optional

from pydantic import field_serializer

from userapp.core.models.enum import RoleEnum
from userapp.core.schemas.general import BaseModel


class UserProjectBase(BaseModel):
    project_id: Optional[int] = None
    user_id: Optional[int] = None
    role: Optional['RoleEnum'] = None
    is_primary: Optional[bool] = False

    @field_serializer('role')
    def serialize_role(self, role: RoleEnum) -> str:
        return role.name if role is not None else None

class UserProjectCreate(UserProjectBase):
    pass

class UserProjectUpdate(UserProjectBase):
    pass

class UserProject(UserProjectBase):
    id: int
