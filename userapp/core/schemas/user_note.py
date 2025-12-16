from typing import Optional

from pydantic import Field

from userapp.core.schemas.general import BaseModel

class UserNoteTableSchema(BaseModel):
    """Used to represent a user-note association as stored in the database"""

    project_id: int
    note_id: int
    user_id: Optional[int] = Field(default=None)
