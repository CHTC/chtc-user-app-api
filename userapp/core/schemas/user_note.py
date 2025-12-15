# Doubt we ever need this, but for completeness...

from typing import Optional

from userapp.core.schemas.general import BaseModel


class UserNoteBase(BaseModel):
    project_id: Optional[int] = None
    note_id: int
    user_id: Optional[int] = None

class UserNoteCreate(UserNoteBase):
    pass

class UserNoteUpdate(UserNoteBase):
    pass

class UserNote(UserNoteBase):
    id: int
