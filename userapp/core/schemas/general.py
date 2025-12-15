from pydantic import BaseModel as PydanticBaseModel, ConfigDict

from userapp.core.models.enum import RoleEnum

class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(extra='ignore', from_attributes=True)

class Relationship(BaseModel):
    """Used to post entities to groups by id"""
    id: int

class Login(BaseModel):
    username: str
    password: str

class PiProjectView(BaseModel):
    user_id: int
    username: str
    name: str
    project_id: int
    project_name: str

class JoinedProjectView(BaseModel):
    user_id: int
    username: str
    email1: str
    phone1: str
    netid: str
    user_name: str
    project_id: int
    project_name: str
    role: RoleEnum
    last_note_ticket: str | None

