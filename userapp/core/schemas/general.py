from typing import Optional
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, model_validator, Field

from userapp.core.models.enum import RoleEnum

class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def empty_strs_to_none(cls, values):
        if isinstance(values, dict):
            return {k: (None if v == '' else v) for k, v in values.items()}
        return values

class Relationship(BaseModel):
    """Used to post entities to groups by id"""
    id: int

class Login(BaseModel):
    username: str
    password: str

class PiProjectView(BaseModel):
    user_id: int
    username: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    project_id: int
    project_name: str

class JoinedProjectView(BaseModel):
    user_id: int
    user_name: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    email1: str
    phone1: Optional[str] = Field(default=None)
    netid: Optional[str] = Field(default=None)
    project_id: int
    project_name: str
    role: RoleEnum
    last_note_ticket: Optional[str] = Field(default=None)