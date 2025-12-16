from typing import Optional

from pydantic import Field

from userapp.core.schemas.general import BaseModel

class SubmitNodeTableSchema(BaseModel):
    """Used to represent a submit node as stored in the database"""

    id: Optional[int] = Field(default=None)
    name: str

class SubmitNodeGet(SubmitNodeTableSchema):
    """Exact same as SubmitNodeTableSchema for now, but kept separate for future changes"""
    pass

class SubmitNodePost(BaseModel):
    name: str

class SubmitNodePatch(BaseModel):
    name: str
