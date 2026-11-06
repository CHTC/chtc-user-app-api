from userapp.core.schemas.general import BaseModel


class UnixGroupGet(BaseModel):
    id: int
    name: str
    unix_gid: int
    members: list[str]
