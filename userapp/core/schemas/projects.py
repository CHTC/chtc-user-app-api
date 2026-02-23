from datetime import datetime
from typing import Optional

from pydantic import HttpUrl, field_serializer, ConfigDict, Field

from userapp.core.schemas.general import BaseModel

class ProjectTableSchema(BaseModel):
    """Used to represent a project as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id:  Optional[int] = Field(default=None)
    name: str
    pi: Optional[int] = Field(default=None)
    staff1: Optional[int] = Field(default=None)
    staff2: Optional[int] = Field(default=None)
    status: Optional[str] = Field(default=None)
    access: Optional[str] = Field(default=None)
    accounting_group: str
    url: Optional[HttpUrl] = Field(default=None)
    date: Optional[datetime] = Field(default=None)
    ticket: Optional[int] = Field(default=None)
    last_contact: Optional[datetime] = Field(default=None)

class ProjectGet(ProjectTableSchema):

    staff1: Optional["UserMin"] = Field(default=None, validation_alias='staff1_user')
    staff2: Optional["UserMin"] = Field(default=None, validation_alias='staff2_user')

    @field_serializer('url')
    def serialize_url(self, url):
        return str(url) if url is not None else None

class ProjectPost(BaseModel):

    name: str
    pi: Optional[int] = Field(default=None)
    staff1: Optional[int] = Field(default=None)
    staff2: Optional[int] = Field(default=None)
    status: Optional[str] = Field(default=None)
    access: Optional[str] = Field(default=None)
    accounting_group: str
    url: Optional[HttpUrl] = Field(default=None)
    ticket: Optional[int] = Field(default=None)
    last_contact: Optional[datetime] = Field(default=None)

    @field_serializer('url')
    def serialize_url(self, url):
        return str(url) if url is not None else None

class ProjectPatch(BaseModel):

    name: Optional[str] = Field(default=None)
    pi: Optional[int] = Field(default=None)
    staff1: Optional[int] = Field(default=None)
    staff2: Optional[int] = Field(default=None)
    status: Optional[str] = Field(default=None)
    access: Optional[str] = Field(default=None)
    accounting_group: Optional[str] = Field(default=None)
    url: Optional[HttpUrl] = Field(default=None)
    ticket: Optional[int] = Field(default=None)
    last_contact: Optional[datetime] = Field(default=None)

    @field_serializer('url')
    def serialize_url(self, url):
        return str(url) if url is not None else None
