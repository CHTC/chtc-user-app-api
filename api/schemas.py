from pydantic import BaseModel as PydanticBaseModel, EmailStr, AfterValidator, ConfigDict, HttpUrl, field_serializer
from typing import Optional, Annotated
from datetime import datetime

from api.validators import group_name_validator, note_ticket_validator, user_password_validator, user_name_validator
from api.models import RoleEnum, PositionEnum

class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(extra='ignore', from_attributes=True)

class Relationship(BaseModel):
    """Used to post entities to groups by id"""
    id: int

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

class NoteBase(BaseModel):
    ticket: Annotated[Optional[str], AfterValidator(note_ticket_validator)] = None
    note: Optional[str] = None
    author: Optional[str] = None
    date: Optional[datetime] = None

class NoteCreate(NoteBase):
    users: list[int] # Notes have to be associated with at least one user

class NoteUpdate(NoteBase):
    pass

class Note(NoteBase):
    id: int
    users: list['User'] = []

class PIProjectBase(BaseModel):
    project_id: Optional[int] = None
    pi_id: Optional[int] = None

class PIProjectCreate(PIProjectBase):
    pass

class PIProjectUpdate(PIProjectBase):
    pass

class PIProject(PIProjectBase):
    id: int

class ProjectBase(BaseModel):
    name: str
    pi: Optional[int] = None
    staff1: Optional[str] = None
    staff2: Optional[str] = None
    status: Optional[str] = None
    access: Optional[str] = None
    accounting_group: str = None
    url: Optional[HttpUrl] = None
    date: Optional[datetime] = None
    ticket: Optional[int] = None
    last_contact: Optional[datetime] = None

    @field_serializer('url')
    def serialize_url(self, url):
        return str(url) if url is not None else None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(ProjectBase):
    pass

class Project(ProjectBase):
    id: int

class SubmitNodeBase(BaseModel):
    name: str

class SubmitNodeCreate(SubmitNodeBase):
    pass

class SubmitNodeUpdate(SubmitNodeBase):
    pass

class SubmitNode(SubmitNodeBase):
    id: int

class UserBase(BaseModel):
    username: Optional[str] = None
    name: Annotated[Optional[str], AfterValidator(user_name_validator)] = None
    email1: Optional[EmailStr] = None
    email2: Optional[EmailStr] = None
    netid: Optional[str] = None
    netid_exp_datetime: Optional[datetime] = None
    phone1: Optional[str] = None
    phone2: Optional[str] = None
    is_admin: Optional[bool] = None
    auth_netid: Optional[bool] = None
    auth_username: Optional[bool] = None
    date: Optional[datetime] = None
    unix_uid: Optional[int] = None
    position: Optional[PositionEnum] = None

    @field_serializer('position')
    def serialize_position(self, position: PositionEnum) -> str:
        return position.name if position is not None else None

class UserCreate(UserBase):
    email1: EmailStr
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = None
    primary_project_id: int
    primary_project_role: RoleEnum

class UserCreateIntermediate(UserBase):
    """Used for the intermediate step when creating a new user, after pulling out project data"""
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = None

class UserUpdate(UserBase):
    password: Annotated[Optional[str], AfterValidator(user_password_validator)] = None

class User(UserBase):
    id: int

class UserGroupBase(BaseModel):
    group_id: int
    user_id: int

class UserGroupCreate(UserGroupBase):
    pass

class UserGroupUpdate(UserGroupBase):
    pass

class UserGroup(UserGroupBase):
    id: int

class UserNoteBase(BaseModel):
    project_id: Optional[int] = None
    note_id: int
    user_id: Optional[int] = None

class UserNoteCreate(UserNoteBase):
    pass

class UserNoteUpdate(UserNoteBase):
    pass

class UserNote(UserNoteBase):
    id: int

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

class UserSubmitBase(BaseModel):
    user_id: int
    submit_node_id: int
    for_auth_netid: Optional[bool] = None
    disk_quota: Optional[int] = None
    hpc_diskquota: Optional[int] = 100
    hpc_inodequota: Optional[int] = 50000
    hpc_joblimit: Optional[int] = 10
    hpc_corelimit: Optional[int] = 720
    hpc_fairshare: Optional[int] = 100

class UserSubmitCreate(UserSubmitBase):
    pass

class UserSubmitUpdate(UserSubmitBase):
    pass

class UserSubmit(UserSubmitBase):
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
