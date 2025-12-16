from pydantic import BaseModel as PydanticBaseModel, AfterValidator, ConfigDict, field_serializer, Field
from typing import Optional, Annotated
from datetime import datetime

from userapp.core.schemas.general import BaseModel

def note_ticket_validator(ticket: str) -> str | None:

    # Allow None tickets
    if ticket is None:
        return ticket

    if not ticket.isalnum():
        raise ValueError("Ticket numbers must be alphanumeric with 9 characters or less")
    if len(ticket) > 9:
        raise ValueError("Ticket numbers must be alphanumeric with 9 characters or less")
    return ticket

class NoteTableSchema(BaseModel):

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    note: str
    author: Optional[str] = Field(default=None)
    ticket: Optional[str] = Field(default=None)
    date: Optional[datetime] = Field(default=None)

class NoteGet(BaseModel):

    id: int
    note: str
    author: Optional[str] = Field(default=None)
    ticket: Annotated[Optional[str], AfterValidator(note_ticket_validator)] = Field(default=None)
    date: Optional[datetime] = Field(default=None)

class NoteGetFull(NoteGet):
    users: list["UserGet"] = Field(default=[]) # Notes have to be associated with at least one user

class NotePost(BaseModel):

    note: str
    ticket: Annotated[Optional[str], AfterValidator(note_ticket_validator)] = Field(default=None)
