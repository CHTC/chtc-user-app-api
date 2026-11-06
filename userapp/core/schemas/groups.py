from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, ConfigDict, Field, model_validator
import re

from userapp.core.models.enum import EntityManagerEnum
from userapp.core.schemas.general import BaseModel


def group_name_validator(name: str) -> str:
    if name is None:
        return name

    if not re.fullmatch(r'[a-zA-Z0-9_-]*', name):
        raise ValueError(
            "Group name must be a valid identifier (alphanumeric and underscores only, cannot start with a digit).")
    if len(name) > 32:
        raise ValueError("Group name must be at most 32 characters long.")
    return name


class GroupTableSchema(BaseModel):
    """Used to represent a group as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    name: str
    unix_gid: Optional[int] = Field(default=None)
    owner_group_id: Optional[int] = Field(default=None)
    description: Optional[str] = Field(default=None)
    managed_by: EntityManagerEnum = EntityManagerEnum.APPLICATION
    deleted_at: Optional[datetime] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)


class GroupPost(BaseModel):

    name: Annotated[str, AfterValidator(group_name_validator)]
    unix_gid: Optional[int] = Field(default=None)
    description: Optional[str] = Field(default=None)
    # The external system that syncs the group's user members, or APPLICATION for none
    managed_by: EntityManagerEnum = EntityManagerEnum.APPLICATION
    owner_group_id: Optional[int] = Field(default=None)
    # "owners" / "owners_and_managers" also create the administrator groups that own the new group
    administration: Literal["none", "owners", "owners_and_managers"] = "none"


class GroupPatch(BaseModel):
    """Body of PUT /groups/{id}. Only fields that are sent change; owners may only send description."""

    name: Annotated[Optional[str], AfterValidator(group_name_validator)] = Field(default=None)
    unix_gid: Optional[int] = Field(default=None)
    description: Optional[str] = Field(default=None)
    managed_by: Optional[EntityManagerEnum] = Field(default=None)
    owner_group_id: Optional[int] = Field(default=None)


class GroupGet(BaseModel):

    id: int
    name: str
    unix_gid: Optional[int] = Field(default=None)
    owner_group_id: Optional[int] = Field(default=None)
    description: Optional[str] = Field(default=None)
    managed_by: EntityManagerEnum
    deleted_at: Optional[datetime] = Field(default=None)
    created_at: datetime
    updated_at: datetime


class GroupMemberPost(BaseModel):
    """Add a user or a group as a direct member; exactly one of user_id / group_id"""

    user_id: Optional[int] = Field(default=None)
    group_id: Optional[int] = Field(default=None)

    @model_validator(mode="after")
    def check_exactly_one_member(self):
        if (self.user_id is None) == (self.group_id is None):
            raise ValueError("Exactly one of user_id or group_id must be provided.")
        return self


class GroupMemberGet(BaseModel):
    """A direct membership row"""

    id: int
    group_id: int
    member_user: Optional["UserGet"] = Field(default=None)
    member_group: Optional[GroupGet] = Field(default=None)
    created_at: datetime


class GroupMemberOfGet(BaseModel):
    """A group that contains another group, and every path through which it does"""

    group: GroupGet
    paths: list[list[int]]
