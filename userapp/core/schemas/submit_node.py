# TODO: Remove this — entire module is dead; submit nodes replaced by SUBMIT_NODE groups.
# Only consumed by the now-disabled submit_nodes route, so this is never imported/loaded.
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
