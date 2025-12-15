from pydantic import AfterValidator
from typing import Optional, Annotated
import re

from userapp.core.schemas.general import BaseModel

def group_name_validator(name: str) -> str:
    if not re.fullmatch(r'[a-zA-Z0-9_-]*', name):
        raise ValueError(
            "Group name must be a valid identifier (alphanumeric and underscores only, cannot start with a digit).")
    if len(name) > 32:
        raise ValueError("Group name must be at most 32 characters long.")
    return name

class GroupBase(BaseModel):
    name: Annotated[str, AfterValidator(group_name_validator)]
    point_of_contact: Optional[str] = None
    unix_gid: Optional[int] = None
    has_groupdir: Optional[bool] = True

class GroupCreate(GroupBase):
    pass

class GroupUpdate(GroupBase):
    pass

class Group(GroupBase):
    id: int
