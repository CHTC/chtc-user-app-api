from pydantic import BaseModel as PydanticBaseModel, AfterValidator, ConfigDict, field_serializer
from typing import Optional, Annotated
from datetime import datetime

from userapp.core.schemas.general import BaseModel
from userapp.core.schemas.users import User


def note_ticket_validator(ticket: str) -> str:
    if not ticket.isalnum():
        raise ValueError("Ticket numbers must be alphanumeric with 9 characters or less")
    if len(ticket) > 9:
        raise ValueError("Ticket numbers must be alphanumeric with 9 characters or less")
    return ticket


class NoteBase(BaseModel):
    ticket: Annotated[Optional[str], AfterValidator(note_ticket_validator)] = None
    note: Optional[str] = None
    date: Optional[datetime] = None

class NoteCreate(NoteBase):
    users: list[int] # Notes have to be associated with at least one user

class NoteCreateRow(NoteBase):
    author: str

class NoteUpdate(NoteBase):
    pass

class Note(NoteBase):
    id: int
    author: Optional[str] = None
    users: list[User] = []