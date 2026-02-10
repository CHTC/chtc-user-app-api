from pydantic import ConfigDict, Field
from typing import Optional

from userapp.core.schemas.general import BaseModel


class RouteGet(BaseModel):
    """Used to represent a route as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    route: str
    method: str
