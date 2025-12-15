from typing import Optional

from userapp.core.schemas.general import BaseModel

class PIProjectBase(BaseModel):
    project_id: Optional[int] = None
    pi_id: Optional[int] = None

class PIProjectCreate(PIProjectBase):
    pass

class PIProjectUpdate(PIProjectBase):
    pass

class PIProject(PIProjectBase):
    id: int
