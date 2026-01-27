from datetime import datetime

from pydantic import AfterValidator, ConfigDict, Field
from typing import Optional, Annotated

from userapp.core.schemas.general import BaseModel

class TokenTableSchema(BaseModel):
    """Used to represent a group as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    created_by: int
    token: str
    description: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)

class TokenPost(BaseModel):

    description: Optional[str] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)

class TokenGetFull(BaseModel):

    id: int
    created_by: Optional[int]
    token: str
    description: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)

class TokenGet(BaseModel):
    id: int
    created_by: Optional[int]
    description: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)
