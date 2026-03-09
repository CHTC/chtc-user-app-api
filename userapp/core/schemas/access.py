from datetime import datetime
from typing import Optional, Any

from userapp.core.schemas.general import BaseModel
from userapp.core.models.enum import HttpRequestMethodEnum


class AccessGet(BaseModel):
    id: int
    user_id: Optional[int]
    token_id: Optional[int]
    method: HttpRequestMethodEnum
    route: str
    query_string: Optional[str]
    payload: Any
    status: int
    created_at: datetime
