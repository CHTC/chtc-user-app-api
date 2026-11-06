from pydantic import ConfigDict

from userapp.core.schemas.general import BaseModel


class UserProjectPost(BaseModel):
    """Add a user to a project's project group"""

    user_id: int


class ManagedUserProjectPut(BaseModel):
    """Used by a managed endpoint which has a url explicit managed_by"""

    # role is gone (PIs are members of the project's pi group); callers that still send it are told
    model_config = ConfigDict(extra='forbid')

    user_id: int
    is_primary: bool = False


class ProjectPiPost(BaseModel):
    """Add a user to a project's pi group"""

    user_id: int


class ProjectGroupMemberPost(BaseModel):
    """Add a group as a direct member of a project's project group or pi group"""

    group_id: int
