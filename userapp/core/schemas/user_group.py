from userapp.core.schemas.general import BaseModel


class ManagedUserGroupPut(BaseModel):
    """Used by a managed endpoint which has a url explicit managed_by and group_id"""

    user_id: int
