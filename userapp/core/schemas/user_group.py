from datetime import datetime
from typing import Optional

from userapp.core.models.enum import EntityManagerEnum
from userapp.core.schemas.general import BaseModel

class UserGroupBase(BaseModel):
    group_id: int
    user_id: int
    managed_by: EntityManagerEnum
    created_at: datetime
    updated_at: datetime


class UserGroupGet(BaseModel):
    group_id: int
    user_id: int
    managed_by: EntityManagerEnum
    created_at: datetime
    updated_at: datetime


class UserGroupPatch(BaseModel):
    managed_by: Optional[EntityManagerEnum] = None


class UserGroupPost(BaseModel):
    user_id: int
    managed_by: Optional[EntityManagerEnum] = None


class ManagedUserGroupPut(BaseModel):
    """Used by a managed endpoint which has a url explicit managed_by and group_id"""

    user_id: int

class UserGroupCreate(BaseModel):
    user_id: int
    group_id: int