from datetime import datetime
from typing import Optional

from pydantic import field_serializer

from userapp.core.models.enum import EntityManagerEnum
from userapp.core.schemas.general import BaseModel

class UserGroupBase(BaseModel):
    group_id: int
    user_id: int
    managed_by: EntityManagerEnum
    created_at: datetime
    updated_at: datetime

    @field_serializer('managed_by')
    def serialize_managed_by(self, managed_by: EntityManagerEnum) -> str:
        return managed_by.name if managed_by is not None else None


class UserGroupGet(BaseModel):
    group_id: int
    user_id: int
    managed_by: EntityManagerEnum
    created_at: datetime
    updated_at: datetime

    @field_serializer('managed_by')
    def serialize_managed_by(self, managed_by: EntityManagerEnum) -> str:
        return managed_by.name if managed_by is not None else None


class UserGroupPatch(BaseModel):
    managed_by: Optional[EntityManagerEnum] = None

    @field_serializer('managed_by')
    def serialize_managed_by(self, managed_by: EntityManagerEnum) -> str:
        return managed_by.name if managed_by is not None else None


class UserGroupPost(BaseModel):
    user_id: int
    managed_by: Optional[EntityManagerEnum] = None

    @field_serializer('managed_by')
    def serialize_managed_by(self, managed_by: EntityManagerEnum) -> str:
        return managed_by.name if managed_by is not None else None

