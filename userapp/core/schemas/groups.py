from pydantic import AfterValidator, ConfigDict, Field
from typing import Optional, Annotated
import re

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
    point_of_contact: Optional[str] = Field(default=None)
    unix_gid: Optional[int] = Field(default=None)
    has_groupdir: Optional[bool] = Field(default=None)


class GroupPost(BaseModel):

    name: Annotated[str, AfterValidator(group_name_validator)]
    point_of_contact: Optional[str] = Field(default=None)
    unix_gid: Optional[int] = Field(default=None)
    has_groupdir: Optional[bool] = Field(default=None)

class GroupPatch(BaseModel):

    name: Annotated[Optional[str], AfterValidator(group_name_validator)] = Field(default=None)
    point_of_contact: Optional[str] = Field(default=None)
    unix_gid: Optional[int] = Field(default=None)
    has_groupdir: Optional[bool] = Field(default=None)

class GroupGet(BaseModel):

    id: int
    name: str
    point_of_contact: Optional[str] = Field(default=None)
    unix_gid: Optional[int] = Field(default=None)
    has_groupdir: bool
