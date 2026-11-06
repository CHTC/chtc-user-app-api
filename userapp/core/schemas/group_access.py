from typing import Literal, Optional

from pydantic import ConfigDict, Field

from userapp.core.schemas.general import BaseModel


class GroupAccessProject(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    project_id: int
    name: str
    display_name: Optional[str] = Field(default=None)
    # "as" is a keyword, so the attribute is as_ and the JSON key is "as"
    as_: Literal["pi_group", "project_group"] = Field(alias="as")
    # The group that is referenced: the one asked about or one it is a member of
    group_id: int
    # Paths from group_id down to the group asked about; empty when group_id is that group
    via: list[list[int]]


class GroupAccessSubmitNode(BaseModel):
    id: int
    name: Optional[str] = Field(default=None)
    group_id: int
    via: list[list[int]]


class GroupAccessGet(BaseModel):
    projects: list[GroupAccessProject]
    submit_nodes: list[GroupAccessSubmitNode]
