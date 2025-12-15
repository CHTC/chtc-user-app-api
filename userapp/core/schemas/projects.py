from datetime import datetime
from typing import Optional

from pydantic import HttpUrl, field_serializer

from userapp.core.schemas.general import BaseModel

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
