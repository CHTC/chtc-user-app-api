from pydantic import ConfigDict, Field
from typing import Optional

from userapp.core.schemas.general import BaseModel


class TokenPermissionTableSchema(BaseModel):
    """Used to represent a group as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    token_id: int
    method: str
    route: str


class TokenPermissionPost(BaseModel):
    method: str
    route: str


class TokenPermissionGet(BaseModel):
    token_id: int
    method: str
    route: str
