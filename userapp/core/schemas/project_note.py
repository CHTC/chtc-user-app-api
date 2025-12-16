from pydantic import Field

from userapp.core.schemas.note import NotePost

class ProjectNotePost(NotePost):

    users: list[int] = Field(default=[]) # Notes have to be associated with at least one user
